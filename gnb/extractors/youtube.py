"""Zamiana napisów filmu na tekst nadający się do notatnika.

Napisy przychodzą jako setki krótkich segmentów, często urwanych w połowie
zdania. Taki zapis jest bezużyteczny jako materiał źródłowy i wyjątkowo męczący
przy odsłuchu czytnikiem ekranu, dlatego segmenty są sklejane w zdania,
a zdania w akapity.

Napisy automatyczne mają dodatkową właściwość: kolejne segmenty powtarzają
końcówkę poprzedniego, ponieważ tekst przewija się na ekranie. Powtórzenia są
wykrywane i usuwane, żeby to samo zdanie nie pojawiło się w wyniku dwa razy.

Znaczniki czasu są opcjonalne i domyślnie wyłączone. Znacznik przy każdym
segmencie rozbijałby tekst na strzępy, więc gdy są włączone, pojawiają się
wyłącznie na początku akapitu. Podział na akapity jest identyczny w obu trybach:
włączenie znaczników niczego nie przesuwa, dodaje jedynie znacznik na początku.

Moduł nie interpretuje treści napisów. Tekst z serwisu jest danymi, nigdy
instrukcją.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury
from gnb.ingestion.youtube import SegmentNapisow, WynikYouTube

METODA_EKSTRAKCJI = "napisy_youtube"

# Progi podziału na akapity. Akapit jest zamykany na końcu zdania, gdy ma już
# sensowną długość, a najpóźniej po przekroczeniu długości maksymalnej, żeby
# materiał bez interpunkcji nie zamienił się w jeden nieskończony blok.
MINIMALNA_DLUGOSC_AKAPITU = 350
MAKSYMALNA_DLUGOSC_AKAPITU = 1200
SEKUND_W_GODZINIE = 3600

KOMUNIKAT_NAPISY_BEZ_TRESCI = (
    "Napisy tego filmu nie zawierają mowy, a jedynie oznaczenia dźwięków albo puste "
    "wiersze, więc nie ma z czego zbudować tekstu. Źródło zostało pominięte."
)

_ZNAKI_KONCA_ZDANIA = (".", "!", "?", "…", ":")

# Oznaczenia dźwięków, na przykład „[muzyka]” albo „(śmiech)”, oraz znaczniki
# pozycjonowania i wyróżnień, które serwis wplata w treść napisów.
_OZNACZENIA_DZWIEKOW = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_ZNACZNIKI_WEWNETRZNE = re.compile(r"<[^>]*>")
_NUTY = re.compile(r"[♪♫]")
_BIALE_ZNAKI = re.compile(r"\s+")


def zbuduj_dokument(
    wynik: WynikYouTube, *, znaczniki_czasu: bool = False
) -> DokumentWyekstrahowany:
    """Buduje dokument wyekstrahowany z napisów jednego filmu.

    Poziom pewności struktury jest niski, ponieważ transkrypcja mowy nie ma
    struktury dokumentu: nie ma w niej nagłówków, list ani tabel. Dzięki temu
    reguła z sekcji ósmej CLAUDE.md nigdy nie wygeneruje dla filmu wersji MD.
    """
    akapity = zbuduj_akapity(wynik.napisy.segmenty)
    tekst = zapisz_akapity(
        akapity,
        znaczniki_czasu=znaczniki_czasu,
        dlugosc_filmu_sekundy=wynik.metadane.dlugosc_sekundy,
    )
    return DokumentWyekstrahowany(
        identyfikator_zrodla=wynik.identyfikator,
        tekst=tekst,
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
        metoda_ekstrakcji=METODA_EKSTRAKCJI,
        tytul=wynik.metadane.tytul,
        metadane=_metadane_tekstowe(wynik),
    )


class Akapit:
    """Jeden akapit transkrypcji wraz z momentem jego rozpoczęcia."""

    __slots__ = ("poczatek_sekundy", "tekst")

    def __init__(self, poczatek_sekundy: float, tekst: str) -> None:
        self.poczatek_sekundy = poczatek_sekundy
        self.tekst = tekst

    def __eq__(self, inny: object) -> bool:
        if not isinstance(inny, Akapit):
            return NotImplemented
        return (self.poczatek_sekundy, self.tekst) == (inny.poczatek_sekundy, inny.tekst)

    def __repr__(self) -> str:
        return f"Akapit({self.poczatek_sekundy!r}, {self.tekst!r})"


def zbuduj_akapity(segmenty: Sequence[SegmentNapisow]) -> list[Akapit]:
    """Skleja segmenty napisów w akapity, usuwając powtórzenia i puste fragmenty.

    Podział jest deterministyczny i nie zależy od tego, czy znaczniki czasu są
    włączone. Akapit kończy się na granicy zdania, gdy osiągnął już minimalną
    długość, albo po przekroczeniu długości maksymalnej.
    """
    akapity: list[Akapit] = []
    biezacy: list[str] = []
    poczatek: float = 0.0

    for segment in segmenty:
        tekst = _oczysc_segment(segment.tekst)
        if not tekst:
            continue

        dolaczany = _bez_powtorzenia(" ".join(biezacy), tekst)
        if not dolaczany:
            continue

        if not biezacy:
            poczatek = segment.poczatek_sekundy
        biezacy.append(dolaczany)

        polaczony = " ".join(biezacy)
        if _czy_zamknac_akapit(polaczony):
            akapity.append(Akapit(poczatek, polaczony))
            biezacy = []

    if biezacy:
        akapity.append(Akapit(poczatek, " ".join(biezacy)))
    return akapity


def zapisz_akapity(
    akapity: Sequence[Akapit],
    *,
    znaczniki_czasu: bool = False,
    dlugosc_filmu_sekundy: int | None = None,
) -> str:
    """Zapisuje akapity jako tekst, opcjonalnie ze znacznikiem czasu na początku.

    Format znacznika jest jednolity w obrębie całego pliku i zależy od długości
    filmu, a nie od momentu danego akapitu. Dzięki temu w jednym materiale nie
    mieszają się zapisy dwu- i trzyczłonowe.
    """
    if not akapity:
        return ""
    if not znaczniki_czasu:
        return "\n\n".join(akapit.tekst for akapit in akapity)

    z_godzinami = _czy_zapis_z_godzinami(akapity, dlugosc_filmu_sekundy)
    return "\n\n".join(
        f"{_znacznik_czasu(akapit.poczatek_sekundy, z_godzinami)} {akapit.tekst}"
        for akapit in akapity
    )


def _czy_zapis_z_godzinami(akapity: Sequence[Akapit], dlugosc_filmu_sekundy: int | None) -> bool:
    """Rozstrzyga, czy znacznik ma zawierać godziny.

    Podstawą jest długość filmu. Gdy nie jest znana, decyduje moment ostatniego
    akapitu, bo to najlepsze dostępne przybliżenie długości materiału.
    """
    if dlugosc_filmu_sekundy is not None:
        return dlugosc_filmu_sekundy >= SEKUND_W_GODZINIE
    return bool(akapity) and akapity[-1].poczatek_sekundy >= SEKUND_W_GODZINIE


def _znacznik_czasu(sekundy: float, z_godzinami: bool) -> str:
    """Buduje znacznik czasu w postaci ``[mm:ss]`` albo ``[h:mm:ss]``."""
    calkowite = int(sekundy)
    godziny, reszta = divmod(calkowite, SEKUND_W_GODZINIE)
    minuty, sekundy_reszty = divmod(reszta, 60)
    if z_godzinami:
        return f"[{godziny}:{minuty:02d}:{sekundy_reszty:02d}]"
    return f"[{minuty + godziny * 60:02d}:{sekundy_reszty:02d}]"


def _oczysc_segment(tekst: str) -> str:
    """Usuwa z segmentu oznaczenia dźwięków, znaczniki i nadmiarowe białe znaki."""
    bez_znacznikow = _ZNACZNIKI_WEWNETRZNE.sub(" ", tekst)
    bez_dzwiekow = _OZNACZENIA_DZWIEKOW.sub(" ", bez_znacznikow)
    bez_nut = _NUTY.sub(" ", bez_dzwiekow)
    return _BIALE_ZNAKI.sub(" ", bez_nut).strip()


def _bez_powtorzenia(dotychczasowy: str, nowy: str) -> str:
    """Zwraca tę część nowego segmentu, której nie ma jeszcze w akapicie.

    Napisy automatyczne powtarzają końcówkę poprzedniego segmentu, bo tekst
    przewija się na ekranie. Bez tego kroku to samo zdanie trafiłoby do wyniku
    kilka razy.
    """
    if not dotychczasowy:
        return nowy
    if nowy in dotychczasowy:
        return ""
    slowa_nowe = nowy.split()
    for dlugosc in range(len(slowa_nowe), 0, -1):
        poczatek = " ".join(slowa_nowe[:dlugosc])
        if dotychczasowy.endswith(poczatek):
            return " ".join(slowa_nowe[dlugosc:])
    return nowy


def _czy_zamknac_akapit(tekst: str) -> bool:
    """Rozstrzyga, czy akapit jest już gotowy do zamknięcia."""
    if len(tekst) >= MAKSYMALNA_DLUGOSC_AKAPITU:
        return True
    return len(tekst) >= MINIMALNA_DLUGOSC_AKAPITU and tekst.endswith(_ZNAKI_KONCA_ZDANIA)


def _metadane_tekstowe(wynik: WynikYouTube) -> dict[str, str]:
    """Zbiera metadane filmu w postaci nadającej się do zapisu w manifeście."""
    metadane: dict[str, str] = {
        "identyfikator_filmu": wynik.identyfikator,
        "adres_kanoniczny": wynik.adres_kanoniczny,
        "jezyk_napisow": wynik.napisy.jezyk,
        "typ_napisow": wynik.napisy.typ,
    }
    if wynik.napisy.metoda:
        metadane["metoda_pobrania_napisow"] = wynik.napisy.metoda
    if wynik.metadane.tytul:
        metadane["tytul"] = wynik.metadane.tytul
    if wynik.metadane.kanal:
        metadane["kanal"] = wynik.metadane.kanal
    if wynik.metadane.dlugosc_sekundy is not None:
        metadane["dlugosc_sekundy"] = str(wynik.metadane.dlugosc_sekundy)
    if wynik.metadane.data_publikacji:
        metadane["data_publikacji"] = wynik.metadane.data_publikacji
    return metadane
