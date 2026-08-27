"""Pobieranie napisów i metadanych filmu z serwisu YouTube.

Zgodnie z sekcją piętnastą CLAUDE.md pobieramy napisy, a nigdy sam film. Warstwy
pobierania są dwie i wzajemnie się zastępują, ponieważ obie biblioteki potrafią
przestać działać po zmianach po stronie serwisu:

1. ``youtube-transcript-api`` jest warstwą pierwszą. Jest lżejsza i sięga wprost
   po ścieżkę napisów.
2. ``yt-dlp`` jest warstwą zapasową dla napisów oraz jedynym źródłem metadanych
   filmu, czyli tytułu, kanału, długości i daty publikacji. Biblioteka pierwsza
   metadanych nie udostępnia.

Metadane i napisy są pobierane niezależnie. Awaria jednej rzeczy nie przekreśla
drugiej: film bez rozpoznanych metadanych nadal daje transkrypcję, a film
z metadanymi, ale bez napisów, kończy się kontrolowanym pominięciem.

Podział wyników jest zgodny z taksonomią z sekcji siódmej. Brak napisów to nie
błąd, tylko `PominietyFilm`, ponieważ transkrypcja mowy przyjdzie dopiero
w etapie dziewiątym. Film prywatny, usunięty, niedostępny w regionie albo
ograniczony wiekiem to `BladTrwaly` z komunikatem nazywającym przypadek.
Zablokowanie adresu przez serwis i błąd sieci to `BladPrzejsciowy`.

Moduł nie interpretuje treści napisów. Tekst z serwisu jest danymi, nigdy
instrukcją.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly
from gnb.core.youtube import adres_kanoniczny_filmu

JEZYKI_DOMYSLNE: tuple[str, ...] = ("pl", "en")

METODA_TRANSCRIPT_API = "youtube-transcript-api"
METODA_YT_DLP = "yt-dlp"

TYP_NAPISOW_RECZNE = "reczne"
TYP_NAPISOW_AUTOMATYCZNE = "automatyczne"
TYP_NAPISOW_TLUMACZONE = "tlumaczone automatycznie"

KOMUNIKAT_BRAK_NAPISOW = (
    "Film nie ma napisów w żadnym z wybranych języków, więc nie da się z niego "
    "pobrać tekstu. Źródło zostało pominięte. Transkrypcja mowy z samego dźwięku "
    "przyjdzie w etapie dziewiątym."
)

_FORMATY_NAPISOW_WEDLUG_PIERWSZENSTWA = ("json3", "vtt", "srv3", "srv1")
_WZORZEC_CZASU_VTT = re.compile(
    r"(?P<godziny>\d{2,}):(?P<minuty>\d{2}):(?P<sekundy>\d{2})[.,](?P<tysieczne>\d{3})\s*-->"
)
_ZNACZNIKI_VTT = ("WEBVTT", "NOTE", "STYLE", "REGION")


@dataclass(frozen=True, slots=True)
class SegmentNapisow:
    """Pojedynczy fragment napisów wraz z momentem jego rozpoczęcia."""

    poczatek_sekundy: float
    tekst: str


@dataclass(frozen=True, slots=True)
class Napisy:
    """Napisy jednego filmu w jednym języku."""

    jezyk: str
    typ: str
    segmenty: tuple[SegmentNapisow, ...]
    metoda: str = ""


@dataclass(frozen=True, slots=True)
class MetadaneFilmu:
    """Opis filmu potrzebny do manifestu i do nazwy pliku wynikowego."""

    identyfikator: str
    tytul: str | None = None
    kanal: str | None = None
    dlugosc_sekundy: int | None = None
    data_publikacji: str | None = None


@dataclass(frozen=True, slots=True)
class WynikYouTube:
    """Komplet danych jednego filmu: metadane oraz wybrane napisy."""

    identyfikator: str
    adres_kanoniczny: str
    metadane: MetadaneFilmu
    napisy: Napisy


@dataclass(frozen=True, slots=True)
class PominietyFilm:
    """Film świadomie pominięty, z powodem gotowym do pokazania użytkownikowi."""

    identyfikator: str
    adres_kanoniczny: str
    powod: str
    metadane: MetadaneFilmu | None = None


WynikPobraniaFilmu = WynikYouTube | PominietyFilm


@dataclass(frozen=True, slots=True)
class PreferencjeNapisow:
    """Kolejność wyboru napisów, wspólna dla obu warstw pobierania."""

    jezyki: tuple[str, ...] = JEZYKI_DOMYSLNE
    dopuszczaj_automatyczne: bool = True
    dopuszczaj_tlumaczone: bool = False


class WarstwaNapisow(Protocol):
    """Kontrakt warstwy pobierającej napisy."""

    nazwa: str

    def pobierz_napisy(
        self, identyfikator_filmu: str, preferencje: PreferencjeNapisow
    ) -> Napisy | None:
        """Zwraca wybrane napisy albo wartość pustą, gdy film ich nie ma."""
        ...


class WarstwaMetadanych(Protocol):
    """Kontrakt warstwy pobierającej metadane filmu."""

    nazwa: str

    def pobierz_metadane(self, identyfikator_filmu: str) -> MetadaneFilmu:
        """Zwraca metadane filmu."""
        ...


class PobieraczYouTube:
    """Pobiera napisy i metadane filmu, korzystając z warstw wzajemnie zapasowych.

    Warstwy można podmienić, i właśnie tak robią testy: podstawiają atrapy
    zwracające przygotowane dane, dzięki czemu żaden test nie sięga do sieci.
    """

    def __init__(
        self,
        preferencje: PreferencjeNapisow | None = None,
        *,
        warstwy_napisow: tuple[WarstwaNapisow, ...] | None = None,
        warstwa_metadanych: WarstwaMetadanych | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self._preferencje = preferencje if preferencje is not None else PreferencjeNapisow()
        self._warstwy_napisow = warstwy_napisow
        self._warstwa_metadanych = warstwa_metadanych
        self._log = log if log is not None else logging.getLogger(__name__)

    def pobierz(self, identyfikator_filmu: str) -> WynikPobraniaFilmu:
        """Pobiera metadane i napisy jednego filmu."""
        adres = adres_kanoniczny_filmu(identyfikator_filmu)
        metadane = self._metadane(identyfikator_filmu)
        napisy = self._napisy(identyfikator_filmu)

        if napisy is None:
            return PominietyFilm(
                identyfikator=identyfikator_filmu,
                adres_kanoniczny=adres,
                powod=KOMUNIKAT_BRAK_NAPISOW,
                metadane=metadane,
            )
        return WynikYouTube(
            identyfikator=identyfikator_filmu,
            adres_kanoniczny=adres,
            metadane=metadane,
            napisy=napisy,
        )

    def _metadane(self, identyfikator_filmu: str) -> MetadaneFilmu:
        """Pobiera metadane filmu. Niepowodzenie nie przerywa pracy nad napisami."""
        warstwa = self._warstwa_metadanych
        if warstwa is None:
            warstwa = WarstwaYtDlp()
        try:
            return warstwa.pobierz_metadane(identyfikator_filmu)
        except BladTrwaly:
            raise
        except BladPrzejsciowy as blad:
            self._log.warning(
                "Nie udało się pobrać metadanych filmu %s warstwą %s: %s",
                identyfikator_filmu,
                warstwa.nazwa,
                blad.komunikat,
            )
            return MetadaneFilmu(identyfikator=identyfikator_filmu)

    def _napisy(self, identyfikator_filmu: str) -> Napisy | None:
        """Próbuje kolejnych warstw, aż któraś zwróci napisy albo stwierdzi ich brak.

        Awaria warstwy, czyli błąd przejściowy, oznacza próbę warstwy następnej.
        Stwierdzenie braku napisów jest natomiast odpowiedzią wiążącą i kończy
        poszukiwanie, bo obie warstwy pytają ten sam serwis o to samo.
        """
        warstwy = self._warstwy_napisow
        if warstwy is None:
            warstwy = (WarstwaTranscriptApi(), WarstwaYtDlp())

        ostatni_blad: BladPrzejsciowy | None = None
        for warstwa in warstwy:
            try:
                return warstwa.pobierz_napisy(identyfikator_filmu, self._preferencje)
            except BladTrwaly:
                raise
            except BladPrzejsciowy as blad:
                ostatni_blad = blad
                self._log.warning(
                    "Warstwa %s nie pobrała napisów filmu %s: %s",
                    warstwa.nazwa,
                    identyfikator_filmu,
                    blad.komunikat,
                )
        if ostatni_blad is not None:
            raise ostatni_blad
        return None


class WarstwaTranscriptApi:
    """Warstwa pierwsza: napisy przez bibliotekę ``youtube-transcript-api``."""

    nazwa = METODA_TRANSCRIPT_API

    def pobierz_napisy(
        self, identyfikator_filmu: str, preferencje: PreferencjeNapisow
    ) -> Napisy | None:
        """Wybiera ścieżkę napisów zgodnie z kolejnością preferencji i pobiera jej treść."""
        from youtube_transcript_api import YouTubeTranscriptApi

        try:
            lista = YouTubeTranscriptApi().list(identyfikator_filmu)
        except Exception as blad:  # noqa: BLE001 — biblioteka ma własną rodzinę wyjątków
            wynik = _rozpoznaj_wyjatek_transcript_api(blad, identyfikator_filmu)
            if wynik is None:
                return None
            raise wynik from blad

        sciezka = _wybierz_sciezke_transcript_api(lista, preferencje)
        if sciezka is None:
            return None

        transkrypcja, typ = sciezka
        try:
            pobrane = transkrypcja.fetch()
        except Exception as blad:  # noqa: BLE001 — biblioteka ma własną rodzinę wyjątków
            wynik = _rozpoznaj_wyjatek_transcript_api(blad, identyfikator_filmu)
            if wynik is None:
                return None
            raise wynik from blad

        segmenty = tuple(
            SegmentNapisow(poczatek_sekundy=float(fragment.start), tekst=str(fragment.text))
            for fragment in pobrane.snippets
        )
        return Napisy(
            jezyk=str(pobrane.language_code),
            typ=typ,
            segmenty=segmenty,
            metoda=self.nazwa,
        )


class WarstwaYtDlp:
    """Warstwa zapasowa dla napisów oraz jedyne źródło metadanych filmu."""

    nazwa = METODA_YT_DLP

    def __init__(self, opcje: dict[str, Any] | None = None) -> None:
        self._opcje: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
            **(opcje or {}),
        }

    def pobierz_metadane(self, identyfikator_filmu: str) -> MetadaneFilmu:
        """Odczytuje tytuł, kanał, długość i datę publikacji filmu."""
        informacje = self._informacje(identyfikator_filmu)
        return MetadaneFilmu(
            identyfikator=identyfikator_filmu,
            tytul=_napis_albo_nic(informacje.get("title")),
            kanal=_napis_albo_nic(informacje.get("uploader") or informacje.get("channel")),
            dlugosc_sekundy=_liczba_albo_nic(informacje.get("duration")),
            data_publikacji=_data_albo_nic(informacje.get("upload_date")),
        )

    def pobierz_napisy(
        self, identyfikator_filmu: str, preferencje: PreferencjeNapisow
    ) -> Napisy | None:
        """Wybiera ścieżkę napisów z informacji o filmie i pobiera jej treść."""
        informacje = self._informacje(identyfikator_filmu)
        wybor = _wybierz_sciezke_yt_dlp(informacje, preferencje)
        if wybor is None:
            return None

        jezyk, typ, sciezka = wybor
        tresc = self._pobierz_tresc(str(sciezka.get("url", "")), identyfikator_filmu)
        segmenty = _segmenty_z_formatu(str(sciezka.get("ext", "")), tresc)
        if not segmenty:
            return None
        return Napisy(jezyk=jezyk, typ=typ, segmenty=segmenty, metoda=self.nazwa)

    def _informacje(self, identyfikator_filmu: str) -> dict[str, Any]:
        """Zwraca słownik informacji o filmie zwrócony przez bibliotekę."""
        from yt_dlp import YoutubeDL
        from yt_dlp.utils import DownloadError

        try:
            with YoutubeDL(self._opcje) as klient:
                informacje = klient.extract_info(
                    adres_kanoniczny_filmu(identyfikator_filmu), download=False
                )
        except DownloadError as blad:
            raise _wyjatek_z_komunikatu_yt_dlp(str(blad), identyfikator_filmu) from blad
        except Exception as blad:  # noqa: BLE001 — biblioteka zgłasza własne typy wyjątków
            raise BladPrzejsciowy(
                f"Nie udało się odczytać danych filmu {identyfikator_filmu}: {blad}",
                identyfikator_filmu,
            ) from blad

        if not isinstance(informacje, dict):
            raise BladPrzejsciowy(
                f"Serwis nie zwrócił danych filmu {identyfikator_filmu}.", identyfikator_filmu
            )
        return informacje

    def _pobierz_tresc(self, adres: str, identyfikator_filmu: str) -> str:
        """Pobiera treść wybranej ścieżki napisów."""
        from yt_dlp import YoutubeDL

        if not adres:
            raise BladPrzejsciowy(
                f"Ścieżka napisów filmu {identyfikator_filmu} nie ma adresu.", identyfikator_filmu
            )
        try:
            with YoutubeDL(self._opcje) as klient:
                return str(klient.urlopen(adres).read().decode("utf-8", "replace"))
        except Exception as blad:  # noqa: BLE001 — biblioteka zgłasza własne typy wyjątków
            raise BladPrzejsciowy(
                f"Nie udało się pobrać napisów filmu {identyfikator_filmu}: {blad}",
                identyfikator_filmu,
            ) from blad


@dataclass(slots=True)
class _KandydatNapisow:
    """Pomocniczy opis rozważanej ścieżki napisów."""

    jezyk: str
    typ: str
    dane: dict[str, Any] = field(default_factory=dict)


def _wybierz_sciezke_transcript_api(
    lista: Any, preferencje: PreferencjeNapisow
) -> tuple[Any, str] | None:
    """Wybiera ścieżkę napisów w kolejności: ręczne, automatyczne, tłumaczone."""
    dostepne = list(lista)

    for jezyk in preferencje.jezyki:
        for transkrypcja in dostepne:
            if transkrypcja.language_code == jezyk and not transkrypcja.is_generated:
                return transkrypcja, TYP_NAPISOW_RECZNE

    if preferencje.dopuszczaj_automatyczne:
        for jezyk in preferencje.jezyki:
            for transkrypcja in dostepne:
                if transkrypcja.language_code == jezyk and transkrypcja.is_generated:
                    return transkrypcja, TYP_NAPISOW_AUTOMATYCZNE

    if preferencje.dopuszczaj_tlumaczone and preferencje.jezyki:
        for transkrypcja in dostepne:
            if transkrypcja.is_translatable:
                return transkrypcja.translate(preferencje.jezyki[0]), TYP_NAPISOW_TLUMACZONE

    return None


def _wybierz_sciezke_yt_dlp(
    informacje: dict[str, Any], preferencje: PreferencjeNapisow
) -> tuple[str, str, dict[str, Any]] | None:
    """Wybiera ścieżkę napisów z informacji zwróconych przez ``yt-dlp``."""
    reczne = informacje.get("subtitles") or {}
    automatyczne = informacje.get("automatic_captions") or {}

    for jezyk in preferencje.jezyki:
        sciezka = _najlepszy_format(reczne.get(jezyk))
        if sciezka is not None:
            return jezyk, TYP_NAPISOW_RECZNE, sciezka

    if preferencje.dopuszczaj_automatyczne:
        for jezyk in preferencje.jezyki:
            sciezka = _najlepszy_format(automatyczne.get(jezyk))
            if sciezka is not None:
                return jezyk, TYP_NAPISOW_AUTOMATYCZNE, sciezka

    return None


def _najlepszy_format(sciezki: Any) -> dict[str, Any] | None:
    """Wybiera format napisów najwygodniejszy do przetworzenia."""
    if not isinstance(sciezki, list) or not sciezki:
        return None
    for rozszerzenie in _FORMATY_NAPISOW_WEDLUG_PIERWSZENSTWA:
        for sciezka in sciezki:
            if isinstance(sciezka, dict) and sciezka.get("ext") == rozszerzenie:
                return sciezka
    pierwsza = sciezki[0]
    return pierwsza if isinstance(pierwsza, dict) else None


def _segmenty_z_formatu(rozszerzenie: str, tresc: str) -> tuple[SegmentNapisow, ...]:
    """Zamienia treść ścieżki napisów na segmenty, zależnie od jej formatu."""
    if rozszerzenie == "json3":
        return _segmenty_z_json3(tresc)
    return _segmenty_z_vtt(tresc)


def _segmenty_z_json3(tresc: str) -> tuple[SegmentNapisow, ...]:
    """Odczytuje segmenty z formatu ``json3`` używanego przez serwis."""
    try:
        dane = json.loads(tresc)
    except json.JSONDecodeError:
        return ()
    if not isinstance(dane, dict):
        return ()

    segmenty: list[SegmentNapisow] = []
    for zdarzenie in dane.get("events") or []:
        if not isinstance(zdarzenie, dict):
            continue
        fragmenty = zdarzenie.get("segs") or []
        tekst = "".join(
            str(fragment.get("utf8", "")) for fragment in fragmenty if isinstance(fragment, dict)
        )
        if not tekst.strip():
            continue
        poczatek = float(zdarzenie.get("tStartMs", 0)) / 1000
        segmenty.append(SegmentNapisow(poczatek_sekundy=poczatek, tekst=tekst))
    return tuple(segmenty)


def _segmenty_z_vtt(tresc: str) -> tuple[SegmentNapisow, ...]:
    """Odczytuje segmenty z formatu WebVTT albo SubRip.

    Interesują nas wyłącznie moment rozpoczęcia i tekst. Znaczniki pozycjonowania
    oraz numery bloków są pomijane, ponieważ nie niosą treści.
    """
    segmenty: list[SegmentNapisow] = []
    poczatek: float | None = None
    wiersze_tekstu: list[str] = []

    def domknij() -> None:
        if poczatek is None:
            return
        tekst = " ".join(wiersze_tekstu).strip()
        if tekst:
            segmenty.append(SegmentNapisow(poczatek_sekundy=poczatek, tekst=tekst))

    for wiersz in tresc.splitlines():
        oczyszczony = wiersz.strip()
        dopasowanie = _WZORZEC_CZASU_VTT.search(oczyszczony)
        if dopasowanie is not None:
            domknij()
            poczatek = (
                int(dopasowanie.group("godziny")) * 3600
                + int(dopasowanie.group("minuty")) * 60
                + int(dopasowanie.group("sekundy"))
                + int(dopasowanie.group("tysieczne")) / 1000
            )
            wiersze_tekstu = []
            continue
        if not oczyszczony or oczyszczony.startswith(_ZNACZNIKI_VTT) or oczyszczony.isdigit():
            continue
        if poczatek is not None:
            wiersze_tekstu.append(oczyszczony)

    domknij()
    return tuple(segmenty)


def _rozpoznaj_wyjatek_transcript_api(
    blad: Exception, identyfikator_filmu: str
) -> Exception | None:
    """Zamienia wyjątek biblioteki na wyjątek projektu albo na brak napisów.

    Wartość pusta oznacza, że film po prostu nie ma napisów, co nie jest błędem.
    """
    from youtube_transcript_api import (
        AgeRestricted,
        CouldNotRetrieveTranscript,
        InvalidVideoId,
        IpBlocked,
        NoTranscriptFound,
        RequestBlocked,
        TranscriptsDisabled,
        VideoUnavailable,
        VideoUnplayable,
    )

    if isinstance(blad, TranscriptsDisabled | NoTranscriptFound):
        return None
    if isinstance(blad, AgeRestricted):
        return BladTrwaly(
            f"Film {identyfikator_filmu} ma ograniczenie wiekowe i jego napisy nie są "
            "dostępne bez zalogowania. Źródło zostało pominięte.",
            identyfikator_filmu,
        )
    if isinstance(blad, InvalidVideoId):
        return BladTrwaly(
            f"Identyfikator filmu {identyfikator_filmu} jest niepoprawny.", identyfikator_filmu
        )
    if isinstance(blad, VideoUnplayable):
        return BladTrwaly(
            f"Film {identyfikator_filmu} jest niedostępny do odtworzenia. Bywa tak przy "
            "filmach prywatnych oraz przy ograniczeniu regionalnym.",
            identyfikator_filmu,
        )
    if isinstance(blad, VideoUnavailable):
        return BladTrwaly(
            f"Film {identyfikator_filmu} jest niedostępny. Bywa tak przy filmach usuniętych.",
            identyfikator_filmu,
        )
    if isinstance(blad, IpBlocked | RequestBlocked):
        return BladPrzejsciowy(
            f"Serwis zablokował żądanie o napisy filmu {identyfikator_filmu}. "
            "Spróbuj ponownie później.",
            identyfikator_filmu,
        )
    if isinstance(blad, CouldNotRetrieveTranscript):
        return BladPrzejsciowy(
            f"Nie udało się pobrać napisów filmu {identyfikator_filmu}: {blad}",
            identyfikator_filmu,
        )
    return BladPrzejsciowy(
        f"Nieoczekiwany błąd przy pobieraniu napisów filmu {identyfikator_filmu}: {blad}",
        identyfikator_filmu,
    )


def _wyjatek_z_komunikatu_yt_dlp(komunikat: str, identyfikator_filmu: str) -> Exception:
    """Rozpoznaje przypadek na podstawie komunikatu biblioteki ``yt-dlp``.

    Biblioteka zgłasza jeden typ wyjątku dla bardzo różnych sytuacji, więc jedyną
    dostępną wskazówką jest treść komunikatu. Nierozpoznany przypadek traktujemy
    jako błąd przejściowy, ponieważ przedwczesne porzucenie sprawnego źródła jest
    gorsze niż jedno zbędne ponowienie.
    """
    tekst = komunikat.lower()
    if "private video" in tekst:
        return BladTrwaly(f"Film {identyfikator_filmu} jest prywatny.", identyfikator_filmu)
    if "video unavailable" in tekst or "has been removed" in tekst:
        return BladTrwaly(
            f"Film {identyfikator_filmu} jest niedostępny albo został usunięty.",
            identyfikator_filmu,
        )
    if "age" in tekst and "confirm" in tekst or "sign in to confirm your age" in tekst:
        return BladTrwaly(
            f"Film {identyfikator_filmu} ma ograniczenie wiekowe.", identyfikator_filmu
        )
    if "not available in your country" in tekst or "blocked it in your country" in tekst:
        return BladTrwaly(
            f"Film {identyfikator_filmu} nie jest dostępny w tym regionie.", identyfikator_filmu
        )
    return BladPrzejsciowy(
        f"Nie udało się odczytać danych filmu {identyfikator_filmu}: {komunikat}",
        identyfikator_filmu,
    )


def _napis_albo_nic(wartosc: Any) -> str | None:
    """Zwraca oczyszczony napis albo wartość pustą."""
    if not isinstance(wartosc, str):
        return None
    oczyszczony = wartosc.strip()
    return oczyszczony or None


def _liczba_albo_nic(wartosc: Any) -> int | None:
    """Zwraca liczbę całkowitą albo wartość pustą."""
    if isinstance(wartosc, bool) or not isinstance(wartosc, (int, float)):
        return None
    return int(wartosc)


def _data_albo_nic(wartosc: Any) -> str | None:
    """Zamienia datę w postaci ``RRRRMMDD`` na postać ``RRRR-MM-DD``."""
    napis = _napis_albo_nic(wartosc)
    if napis is None or len(napis) != 8 or not napis.isdigit():
        return napis
    return f"{napis[:4]}-{napis[4:6]}-{napis[6:]}"
