"""Orkiestracja potoku przetwarzania od wejścia po raport końcowy.

Potok uruchamia etapy w stałej kolejności z sekcji ósmej CLAUDE.md: wejście,
walidacja i utworzenie źródła, pobranie lub import treści, ekstrakcja,
normalizacja, klasyfikacja TXT kontra MD, deduplikacja, zapis wyników, manifest,
checkpoint, raport. Etapy kondensacji i grupowania tematycznego są pominięte, ale
ich miejsce w kolejności jest zachowane.

Deduplikacja porównuje wszystkie źródła naraz, więc potok jest podzielony na
fazy. Faza normalizacji doprowadza każde źródło do znormalizowanego tekstu,
zapisuje ten tekst w podkatalogu wyników pośrednich i nadaje źródłu status
„znormalizowane”. Faza deduplikacji zestawia znormalizowane teksty, oznacza
pewne duplikaty statusem „duplikat” i zapisuje audytowalne decyzje. Faza zapisu
tworzy pliki wynikowe wyłącznie dla źródeł, które przeżyły deduplikację. Podział
na fazy jest też podziałem wznowienia: przerwanie w trakcie deduplikacji albo
zapisu nie wymaga ponownej ekstrakcji, bo znormalizowany tekst jest już na dysku.

Pobranie adresów jest osobną fazą, wykonywaną przed pętlą po źródłach. Dzięki
temu strony pobierają się równolegle, z zachowaniem limitu połączeń na domenę
i odstępu między żądaniami, a reszta potoku pozostaje synchroniczna i prosta.
Adresy już przetworzone w poprzednim uruchomieniu nie są pobierane ponownie,
bo ich identyfikator wynika z kanonicznej postaci adresu.

Jedno uszkodzone wejście nie zatrzymuje reszty. Kończy się kontrolowanym błędem
zapisanym w logu szczegółowym, w manifeście i w raporcie końcowym. Potok jest
odporny na wznowienie: źródła zapisane w checkpoincie ze statusem końcowym nie
są przetwarzane ponownie, a manifest oraz raport są odbudowywane z pełnego stanu
checkpointu.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from gnb.core.identyfikatory import suma_kontrolna_bajtow
from gnb.core.konfiguracja import Konfiguracja
from gnb.core.model import (
    DokumentWyekstrahowany,
    DokumentZnormalizowany,
    PlikWynikowy,
    Zrodlo,
)
from gnb.core.nazwy import (
    nazwa_pliku_czesci,
    nazwa_pliku_grupy,
    nazwa_pliku_wynikowego,
    skrot_z_identyfikatora,
    wygeneruj_nazwe_projektu,
)
from gnb.core.postep import FazaPotoku, WywolanieZwrotnePostepu, ZdarzeniePostepu
from gnb.core.stale import StatusZrodla, TypWejscia, TypZrodla, WynikDeduplikacji
from gnb.core.wyjatki import BladGnb, BladTrwaly, PrzekroczonoLimit
from gnb.core.youtube import rozpoznaj
from gnb.deduplication import UstawieniaDeduplikacji, ZrodloDoDeduplikacji, deduplikuj
from gnb.deduplication.orkiestrator import WynikDeduplikacjiZbioru
from gnb.extractors.bazowy import (
    PostepEkstrakcji,
    RejestrEkstraktorow,
    RejestrEkstraktorowBinarnych,
    domyslny_rejestr,
    domyslny_rejestr_binarny,
)
from gnb.extractors.dane_strukturalne import (
    KLUCZ_ROZBIEZNOSCI,
    odczytaj_json_ld,
    scal_metadane,
)
from gnb.extractors.strona_www import KOMUNIKAT_WYMAGA_SKRYPTOW, czy_wymaga_skryptow
from gnb.extractors.youtube import KOMUNIKAT_NAPISY_BEZ_TRESCI
from gnb.extractors.youtube import zbuduj_dokument as zbuduj_dokument_z_napisow
from gnb.images.tesseract import UstawieniaOcr
from gnb.ingestion.pobieranie import (
    OdpowiedzPobrania,
    Pobieracz,
    PominietePobranie,
    UstawieniaPobierania,
    Zadanie,
)
from gnb.ingestion.wejscie import (
    FORMAT_YOUTUBE,
    PozycjaWejsciowa,
    czy_format_binarny,
    identyfikator_adresu,
    identyfikator_awaryjny,
    przyjmij_plik,
    przyjmij_tekst,
    przyjmij_url,
    typ_zrodla_dla_formatu,
    waliduj_i_utworz_zrodlo,
    wczytaj_tresc_zrodla,
)
from gnb.ingestion.youtube import (
    PobieraczYouTube,
    PominietyFilm,
    PreferencjeNapisow,
    WynikYouTube,
    do_json,
    klucz_pamieci_podrecznej,
    opis_typu_napisow,
    z_json,
)
from gnb.logging_pl.dziennik import (
    NAZWA_LOGU_SZCZEGOLOWEGO,
    NAZWA_LOGU_WAZNEGO,
    ZDARZENIE_CHECKPOINT_ZAPISANY,
    ZDARZENIE_DEDUPLIKACJA_ZAKONCZONA,
    ZDARZENIE_GRUPA_SPAKOWANA,
    ZDARZENIE_JAKOSC_PODEJRZANA,
    ZDARZENIE_MANIFEST_ZAPISANY,
    ZDARZENIE_MOZLIWY_DUPLIKAT,
    ZDARZENIE_NAPISY_INNY_JEZYK,
    ZDARZENIE_NAPISY_WYBRANE,
    ZDARZENIE_OSTRZEZENIE_EKSTRAKCJI,
    ZDARZENIE_OSTRZEZENIE_PODZIALU,
    ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY,
    ZDARZENIE_PROJEKT_UTWORZONY,
    ZDARZENIE_PROJEKT_WZNOWIONY,
    ZDARZENIE_PROJEKT_ZAKONCZONY,
    ZDARZENIE_ZRODLO_BLAD,
    ZDARZENIE_ZRODLO_DUPLIKAT,
    ZDARZENIE_ZRODLO_PODZIELONE,
    ZDARZENIE_ZRODLO_POMINIETE,
    ZDARZENIE_ZRODLO_PRZYJETE,
    DziennikSzczegolowy,
    DziennikWazny,
    teraz_lokalny,
)
from gnb.normalization.kodowanie import zdekoduj
from gnb.normalization.normalizacja import zbuduj_dokument_znormalizowany, znormalizuj
from gnb.output import regula_md
from gnb.output.manifest import WERSJA_SCHEMATU as WERSJA_SCHEMATU_MANIFESTU
from gnb.output.manifest import (
    Manifest,
    WpisDeduplikacji,
    WpisPobrania,
    WpisWyniku,
    WpisZrodla,
    zapisz_manifest,
)
from gnb.output.naglowek_metadanych import (
    ETYKIETA_ADRES,
    ETYKIETA_AUTOR,
    ETYKIETA_DATA_IMPORTU,
    ETYKIETA_DATA_PUBLIKACJI,
    ETYKIETA_DLUGOSC,
    ETYKIETA_IDENTYFIKATOR,
    ETYKIETA_JEZYK_NAPISOW,
    ETYKIETA_KANAL,
    ETYKIETA_PLIK,
    ETYKIETA_RODZAJ_NAPISOW,
    ETYKIETA_TYP,
    ETYKIETA_TYTUL,
    opis_dlugosci,
    opis_typu_zrodla,
    z_oznaczeniem_czesci,
    zbuduj_naglowek,
)
from gnb.output.ocena_jakosci import OCENA_PODEJRZANA, OcenaJakosci, ocen_jakosc
from gnb.output.raport import (
    MaterialDoSprawdzenia,
    PodsumowanieProjektu,
    ZrodloNieprzetworzone,
    zapisz_raport,
    zbuduj_raport,
)
from gnb.output.skladanie import oznaczenie_pliku_grupy, zloz_plik
from gnb.output.tekst_bez_znacznikow import zamien_markdown_na_tekst
from gnb.output.zapis import zapisz_plik_pakietu, zapisz_wyniki
from gnb.packing import (
    LimityPakowania,
    PlanPliku,
    ZrodloDoPakowania,
    podziel_na_czesci,
    rozplanuj_grupe,
)
from gnb.persistence.cache import PamiecPodreczna, WpisCache, otworz, teraz_utc
from gnb.persistence.checkpoint import WERSJA_SCHEMATU as WERSJA_SCHEMATU_CHECKPOINTU
from gnb.persistence.checkpoint import (
    Checkpoint,
    DecyzjaDeduplikacjiZapis,
    StanPobrania,
    StanWyniku,
    StanZrodla,
    WejscieZapis,
    wczytaj,
    zapisz,
)
from gnb.persistence.projekt import UkladProjektu, ustal_uklad, utworz_katalogi

_STATUSY_KONCOWE = frozenset(
    {StatusZrodla.SPAKOWANE.value, StatusZrodla.POMINIETE.value, StatusZrodla.BLAD.value}
)
_ROZSZERZENIE_ORYGINALU_TEKSTU = "txt"
_ROZSZERZENIE_ORYGINALU_NAPISOW = "json"

# Nazwy plików wyników pośrednich zapisywanych po normalizacji. Pierwszy trzyma
# znormalizowany tekst dokumentu, drugi powstaje tylko dla źródeł, których
# wersja TXT różni się od wersji MD, na przykład plików Markdown.
_SUFIKS_TEKST_ZNORMALIZOWANY = "znormalizowany.txt"
_SUFIKS_TEKST_WERSJI_TXT = "wersja-txt.txt"

KOMUNIKAT_DUPLIKAT = (
    "Źródło zostało uznane za duplikat źródła {glowne} (metoda: {metoda}, "
    "podobieństwo {podobienstwo:.2f}). Nie powstaje dla niego plik wynikowy, żeby "
    "nie zajmować miejsca w limicie źródeł notatnika. Decyzja jest w manifeście."
)
KOMUNIKAT_BRAK_TEKSTU_POSREDNIEGO = (
    "Brak pliku wyniku pośredniego dla znormalizowanego źródła, więc nie da się "
    "zapisać pliku wynikowego. Plik mógł zostać usunięty. Przetwórz projekt od "
    "nowa albo przywróć zawartość podkatalogu wyników pośrednich."
)

# Formaty plików dokumentowych, dla których tytuł i podział na akapity są
# naturalną cechą prozy, więc ich brak jest sygnałem utraty treści, a nie
# właściwością formatu. CSV, SRT i VTT celowo nie są tutaj wymienione.
_FORMATY_DOKUMENTOW_OCENIANE = frozenset({"pdf", "docx", "epub", "html", "htm", "xhtml"})


def _czy_ocenic_jakosc(typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
    """Rozstrzyga, czy źródło podlega ocenie jakości ekstrakcji.

    Strona i film mają treść powstającą przez rozpoznanie niezależnie od
    formatu, więc są oceniane zawsze. Plik dokumentowy jest oceniany tylko dla
    formatów prozy — PDF, DOCX, EPUB i HTML lokalny — bo CSV oraz napisy SRT
    i VTT z natury formatu nie mają tytułu ani akapitów.
    """
    if typ_zrodla in (TypZrodla.STRONA_WWW, TypZrodla.YOUTUBE):
        return True
    return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in _FORMATY_DOKUMENTOW_OCENIANE


# Wynik fazy pobrania dla jednego adresu: treść, świadome pominięcie albo błąd.
WynikFazyPobrania = OdpowiedzPobrania | PominietePobranie | BladGnb

# Wynik fazy pobrania dla jednego filmu: napisy, świadome pominięcie albo błąd.
WynikFazyFilmu = WynikYouTube | PominietyFilm | BladGnb

KOMUNIKAT_PLIK_BEZ_TRESCI = (
    "Ekstrakcja niczego nie odczytała, więc wynik zawierałby wyłącznie nagłówek "
    "metadanych, bez treści źródła. Źródło zostało pominięte, żeby pusty plik nie "
    "zajmował miejsca w limicie źródeł notatnika."
)

_TYP_ZAWARTOSCI_NAPISOW = "application/json"
_MAKSYMALNA_PODSTAWA_NAZWY = 120


@dataclass(frozen=True, slots=True)
class _PrzygotowanyDokument:
    """Dokument gotowy do normalizacji i zapisu, wraz z danymi towarzyszącymi.

    Struktura pozwala obsłużyć jedną ścieżką zapisu wszystkie rodzaje źródeł,
    mimo że każdy z nich dochodzi do dokumentu inaczej: plik przez odczyt, strona
    przez pobranie i ekstrakcję, a film przez napisy.
    """

    dokument: DokumentWyekstrahowany
    suma_kontrolna: str
    tekst_txt: str | None
    stan_pobrania: StanPobrania | None
    metadane: dict[str, str]
    tekst_zrodla: str | None = None
    tresc_porownawcza: str | None = None


@dataclass(frozen=True, slots=True)
class WynikPrzetwarzania:
    """Podsumowanie jednego uruchomienia potoku dla projektu."""

    katalog_projektu: Path
    identyfikator_projektu: str
    nazwa_projektu: str
    liczba_przetworzonych: int
    liczba_pominietych: int
    liczba_bledow: int
    sciezka_manifestu: Path
    sciezka_raportu: Path
    wznowiono: bool


def _teraz_utc() -> datetime:
    return datetime.now(UTC)


def _zglos_postep(
    postep: WywolanieZwrotnePostepu | None,
    faza: FazaPotoku,
    wykonano: int,
    wszystkich: int,
    opis: str,
) -> None:
    """Przekazuje jedno zdarzenie postępu do wywołania zwrotnego, jeżeli je podano.

    Dławienie komunikatów jest po stronie odbiorcy, nie tutaj: potok zgłasza
    każde zdarzenie, a interfejs decyduje, które i jak często ogłosić.
    """
    if postep is None:
        return
    postep(ZdarzeniePostepu(faza=faza, wykonano=wykonano, wszystkich=wszystkich, opis=opis))


def przetworz_projekt(
    pozycje: Sequence[PozycjaWejsciowa],
    konfiguracja: Konfiguracja,
    *,
    nazwa_projektu: str | None = None,
    wlasny_katalog_projektu: Path | None = None,
    zegar: Callable[[], datetime] = _teraz_utc,
    zegar_lokalny: Callable[[], datetime] = teraz_lokalny,
    rejestr: RejestrEkstraktorow | None = None,
    rejestr_binarny: RejestrEkstraktorowBinarnych | None = None,
    transport_http: httpx.AsyncBaseTransport | None = None,
    pobieracz_youtube: PobieraczYouTube | None = None,
    postep: WywolanieZwrotnePostepu | None = None,
) -> WynikPrzetwarzania:
    """Przetwarza listę wejść w ramach jednego projektu i zwraca podsumowanie.

    Argument `zegar` podaje czas UTC używany w checkpoincie, manifeście i logu
    szczegółowym. Argument `zegar_lokalny` podaje czas lokalny systemu, którym
    prowadzony jest przeznaczony dla użytkownika plik ``log_wazne.txt``. Oba
    zegary można podmienić w testach.

    Argument `postep` to opcjonalne wywołanie zwrotne przyjmujące kolejne
    `ZdarzeniePostepu` na granicach faz oraz po każdym przetworzonym źródle. Brak
    tego argumentu oznacza pracę bez raportowania postępu, tak jak w wierszu
    poleceń. Interfejs WWW podaje tu funkcję, która zamienia zdarzenia na dławione
    komunikaty regionu ``role="status"``.

    Argumenty `transport_http` oraz `pobieracz_youtube` służą wyłącznie testom.
    Pozwalają podstawić sztuczny transport oraz przygotowane napisy i sprawdzić
    cały potok bez korzystania z sieci.
    """
    rejestr = rejestr or domyslny_rejestr(konfiguracja.zachowuj_odnosniki)
    rejestr_binarny = rejestr_binarny or domyslny_rejestr_binarny(
        UstawieniaOcr.z_konfiguracji(konfiguracja), ocr_wlaczony=konfiguracja.ocr_wlaczony
    )
    czas_startu = zegar()

    nazwa = nazwa_projektu or _wygeneruj_nazwe_projektu(pozycje)
    uklad = ustal_uklad(
        konfiguracja.katalog_wynikow, nazwa, wlasny_katalog_projektu=wlasny_katalog_projektu
    )
    utworz_katalogi(uklad, z_materialami_zrodlowymi=konfiguracja.zachowuj_oryginaly)

    istniejacy_checkpoint = wczytaj(uklad.checkpoint)
    wznowiono = istniejacy_checkpoint is not None
    checkpoint = istniejacy_checkpoint or _nowy_checkpoint(uklad, konfiguracja, zegar())
    _zapamietaj_wejscia(checkpoint, pozycje)

    dziennik_wazny = DziennikWazny(uklad.logi / NAZWA_LOGU_WAZNEGO, zegar_lokalny)
    with DziennikSzczegolowy(
        uklad.logi / NAZWA_LOGU_SZCZEGOLOWEGO, uklad.identyfikator_projektu
    ) as log:
        dziennik_wazny.zapisz(
            ZDARZENIE_PROJEKT_WZNOWIONY if wznowiono else ZDARZENIE_PROJEKT_UTWORZONY
        )
        log.info(
            "Projekt „%s”, katalog %s, wznowienie: %s",
            uklad.nazwa_projektu,
            uklad.katalog_projektu,
            "tak" if wznowiono else "nie",
        )

        pobrane = _pobierz_strony(pozycje, konfiguracja, checkpoint, log, transport_http, postep)
        filmy = _pobierz_filmy(
            pozycje, konfiguracja, checkpoint, log, transport_http, pobieracz_youtube, postep
        )
        wykonanie = _Wykonanie(
            uklad,
            konfiguracja,
            checkpoint,
            dziennik_wazny,
            log,
            rejestr,
            rejestr_binarny,
            zegar,
            zegar_lokalny,
            pobrane,
            filmy,
            postep,
        )
        liczba_pozycji = len(pozycje)
        for numer, pozycja in enumerate(pozycje, start=1):
            wykonanie.przetworz(pozycja)
            _zglos_postep(
                postep,
                FazaPotoku.EKSTRAKCJA,
                numer,
                liczba_pozycji,
                f"Przetworzono {numer} z {liczba_pozycji} źródeł",
            )

        _zglos_postep(postep, FazaPotoku.DEDUPLIKACJA, 0, 1, "Deduplikacja źródeł")
        wykonanie.deduplikuj()
        _zglos_postep(postep, FazaPotoku.DEDUPLIKACJA, 1, 1, "Deduplikacja zakończona")

        _zglos_postep(postep, FazaPotoku.PAKOWANIE, 0, 1, "Pakowanie i zapis plików wynikowych")
        wykonanie.zapisz_pliki_wynikowe()
        _zglos_postep(postep, FazaPotoku.PAKOWANIE, 1, 1, "Pliki wynikowe zapisane")

        checkpoint.zakonczony = True
        checkpoint.czas_ostatniej_zmiany = zegar().isoformat()
        zapisz(uklad.checkpoint, checkpoint)
        dziennik_wazny.zapisz(ZDARZENIE_CHECKPOINT_ZAPISANY)

        manifest = _zbuduj_manifest(uklad, checkpoint)
        zapisz_manifest(uklad.manifest_json, uklad.manifest_txt, manifest)
        dziennik_wazny.zapisz(ZDARZENIE_MANIFEST_ZAPISANY)

        podsumowanie = _zbuduj_podsumowanie(
            checkpoint=checkpoint,
            limit_zrodel=konfiguracja.limit_zrodel,
            czas_pracy_sekundy=(zegar() - czas_startu).total_seconds(),
        )
        zapisz_raport(uklad.raport, zbuduj_raport(uklad.nazwa_projektu, podsumowanie))
        dziennik_wazny.zapisz(ZDARZENIE_PROJEKT_ZAKONCZONY)
        log.info("Projekt zakończony.")
        _zglos_postep(postep, FazaPotoku.ZAKONCZENIE, 1, 1, "Projekt zakończony")

    return WynikPrzetwarzania(
        katalog_projektu=uklad.katalog_projektu,
        identyfikator_projektu=uklad.identyfikator_projektu,
        nazwa_projektu=uklad.nazwa_projektu,
        liczba_przetworzonych=_policz_status(checkpoint, StatusZrodla.SPAKOWANE),
        liczba_pominietych=_policz_status(checkpoint, StatusZrodla.POMINIETE),
        liczba_bledow=_policz_status(checkpoint, StatusZrodla.BLAD),
        sciezka_manifestu=uklad.manifest_json,
        sciezka_raportu=uklad.raport,
        wznowiono=wznowiono,
    )


class _Wykonanie:
    """Stan współdzielony przy przetwarzaniu kolejnych wejść jednego uruchomienia."""

    def __init__(
        self,
        uklad: UkladProjektu,
        konfiguracja: Konfiguracja,
        checkpoint: Checkpoint,
        dziennik_wazny: DziennikWazny,
        log: logging.Logger,
        rejestr: RejestrEkstraktorow,
        rejestr_binarny: RejestrEkstraktorowBinarnych,
        zegar: Callable[[], datetime],
        zegar_lokalny: Callable[[], datetime],
        pobrane: dict[str, WynikFazyPobrania] | None = None,
        filmy: dict[str, WynikFazyFilmu] | None = None,
        postep: WywolanieZwrotnePostepu | None = None,
    ) -> None:
        self._uklad = uklad
        self._konfiguracja = konfiguracja
        self._checkpoint = checkpoint
        self._dziennik_wazny = dziennik_wazny
        self._log = log
        self._rejestr = rejestr
        self._rejestr_binarny = rejestr_binarny
        self._zegar = zegar
        self._zegar_lokalny = zegar_lokalny
        self._postep = postep
        self._pobrane: dict[str, WynikFazyPobrania] = pobrane if pobrane is not None else {}
        self._filmy: dict[str, WynikFazyFilmu] = filmy if filmy is not None else {}

    def przetworz(self, pozycja: PozycjaWejsciowa) -> None:
        """Przetwarza jedno wejście, aktualizując checkpoint i logi."""
        try:
            zrodlo = waliduj_i_utworz_zrodlo(pozycja, self._konfiguracja, self._zegar())
        except BladGnb as blad:
            self._zapisz_blad_wejscia(pozycja, blad)
            return

        identyfikator = zrodlo.identyfikator_zrodla
        istniejacy = self._checkpoint.zrodla.get(identyfikator)
        if istniejacy is not None and istniejacy.status in _STATUSY_KONCOWE:
            self._loguj(
                logging.INFO, identyfikator, f"Pomijam już przetworzone źródło {identyfikator}."
            )
            return
        if istniejacy is not None and istniejacy.status == StatusZrodla.DUPLIKAT.value:
            self._loguj(
                logging.INFO,
                identyfikator,
                f"Źródło {identyfikator} jest już oznaczone jako duplikat, pomijam.",
            )
            return
        if (
            istniejacy is not None
            and istniejacy.status == StatusZrodla.ZNORMALIZOWANE.value
            and self._ma_tekst_posredni(identyfikator)
        ):
            self._loguj(
                logging.INFO,
                identyfikator,
                f"Źródło {identyfikator} jest już znormalizowane, czeka na deduplikację i zapis.",
            )
            return

        if istniejacy is None and self._liczba_aktywnych() >= self._konfiguracja.limit_zrodel:
            self._pomin(
                zrodlo, pozycja, "Przekroczono limit liczby źródeł w notatniku. Źródło pominięte."
            )
            return

        try:
            self._przetworz_zrodlo(pozycja, zrodlo)
        except PrzekroczonoLimit as blad:
            # Limit słów źródła jest teraz obsługiwany podziałem w fazie pakowania,
            # więc tu trafia już tylko przekroczenie limitu zgłoszone wprost przez
            # ekstraktor. Dostaje status pominięcia, tak samo jak przekroczenie
            # limitu liczby źródeł notatnika.
            self._pomin(zrodlo, pozycja, blad.komunikat)
        except BladGnb as blad:
            self._zapisz_blad_zrodla(zrodlo, pozycja, blad)

    def _przetworz_zrodlo(self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo) -> None:
        """Doprowadza jedno źródło od treści do zapisanych plików wynikowych."""
        przygotowane = (
            self._przygotuj_film(pozycja, zrodlo)
            if zrodlo.typ_zrodla is TypZrodla.YOUTUBE
            else self._przygotuj_tresc(pozycja, zrodlo)
        )
        if przygotowane is None:
            return
        self._znormalizuj_i_odloz(pozycja, zrodlo, przygotowane)

    def _przygotuj_film(
        self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo
    ) -> _PrzygotowanyDokument | None:
        """Buduje dokument z napisów filmu pobranych we wcześniejszej fazie."""
        identyfikator = zrodlo.identyfikator_zrodla
        wynik = self._filmy.get(identyfikator)

        if isinstance(wynik, PominietyFilm):
            self._pomin(zrodlo, pozycja, wynik.powod)
            return None
        if isinstance(wynik, BladGnb):
            raise wynik
        if wynik is None:
            raise BladTrwaly(
                f"Brak wyniku pobrania napisów dla adresu {zrodlo.pochodzenie}.", identyfikator
            )

        dokument = zbuduj_dokument_z_napisow(
            wynik, znaczniki_czasu=self._konfiguracja.znaczniki_czasu
        )
        if not dokument.tekst.strip():
            self._pomin(zrodlo, pozycja, KOMUNIKAT_NAPISY_BEZ_TRESCI)
            return None

        surowe = do_json(wynik)
        self._zachowaj_oryginal(pozycja, zrodlo, dokument.tekst, surowe)
        self._odnotuj_napisy(wynik)
        self._loguj(
            logging.INFO,
            identyfikator,
            f"Film {wynik.identyfikator}, napisy {wynik.napisy.typ} w języku "
            f"{wynik.napisy.jezyk}, metoda {wynik.napisy.metoda or 'nieznana'}.",
        )
        return _PrzygotowanyDokument(
            dokument=dokument,
            suma_kontrolna=suma_kontrolna_bajtow(surowe),
            tekst_txt=None,
            stan_pobrania=None,
            metadane=dict(dokument.metadane),
        )

    def _odnotuj_napisy(self, wynik: WynikYouTube) -> None:
        """Zapisuje w logu ważnym, jakie napisy wybrano dla filmu.

        Wpis powstaje zawsze, bo język i rodzaj napisów są informacją o jakości
        materiału, a użytkownik nie powinien musieć zaglądać do manifestu, żeby
        się ich dowiedzieć. Sięgnięcie po język spoza listy preferencji dostaje
        dodatkowy wiersz ostrzeżenia, żeby podmiana języka nie była cicha.
        """
        opis_typu = opis_typu_napisow(wynik.napisy.typ)
        self._dziennik_wazny.zapisz(
            f"{ZDARZENIE_NAPISY_WYBRANE}: język {wynik.napisy.jezyk}, {opis_typu}"
        )
        if not wynik.napisy.awaryjny_jezyk:
            return

        oczekiwane = ", ".join(self._konfiguracja.jezyki_napisow) or "brak"
        opis_filmu = wynik.metadane.tytul or wynik.adres_kanoniczny
        self._dziennik_wazny.zapisz(
            f"{ZDARZENIE_NAPISY_INNY_JEZYK}: {opis_filmu}, oczekiwano "
            f"{oczekiwane}, pobrano {wynik.napisy.jezyk}"
        )

    def _naglowek(
        self,
        pozycja: PozycjaWejsciowa,
        zrodlo: Zrodlo,
        dokument: DokumentWyekstrahowany,
        metadane: dict[str, str],
    ) -> str:
        """Buduje nagłówek metadanych dopisywany na początku plików wynikowych.

        Pola nieobecne dla danego źródła są pomijane. Adres dotyczy źródeł
        sieciowych i jest adresem pobierania, a nie postacią kanoniczną, żeby
        dało się go wkleić do przeglądarki wprost. Plik dotyczy źródeł lokalnych.
        Data importu jest zapisywana w czasie lokalnym, bo nagłówek czyta
        człowiek.
        """
        pola: dict[str, str] = {
            ETYKIETA_TYTUL: dokument.tytul or "",
            ETYKIETA_TYP: opis_typu_zrodla(zrodlo.typ_zrodla),
            ETYKIETA_AUTOR: metadane.get("autor", ""),
            ETYKIETA_DATA_PUBLIKACJI: metadane.get("data_publikacji", ""),
            ETYKIETA_KANAL: metadane.get("kanal", ""),
            ETYKIETA_DLUGOSC: _opis_dlugosci_z_metadanych(metadane),
            ETYKIETA_JEZYK_NAPISOW: metadane.get("jezyk_napisow", ""),
            ETYKIETA_RODZAJ_NAPISOW: _opis_rodzaju_napisow(metadane),
            ETYKIETA_DATA_IMPORTU: self._zegar_lokalny().strftime("%Y-%m-%d"),
            ETYKIETA_IDENTYFIKATOR: zrodlo.identyfikator_zrodla,
        }

        if pozycja.wejscie.typ_wejscia is TypWejscia.URL:
            pola[ETYKIETA_ADRES] = pozycja.wejscie.wartosc
        elif pozycja.wejscie.typ_wejscia is TypWejscia.PLIK:
            pola[ETYKIETA_PLIK] = Path(pozycja.wejscie.wartosc).name

        return zbuduj_naglowek(pola)

    def _przygotuj_tresc(
        self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo
    ) -> _PrzygotowanyDokument | None:
        """Buduje dokument ze źródła tekstowego, plikowego albo strony internetowej."""
        if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK and czy_format_binarny(
            pozycja.format_zrodla
        ):
            return self._przygotuj_tresc_binarna(pozycja, zrodlo)

        identyfikator = zrodlo.identyfikator_zrodla
        tresc = self._tresc_zrodla(pozycja, zrodlo)
        if tresc is None:
            return None
        tekst, kodowanie, surowe_bajty, stan_pobrania, suma_kontrolna = tresc

        self._zachowaj_oryginal(pozycja, zrodlo, tekst, surowe_bajty)
        self._loguj(logging.INFO, identyfikator, f"Źródło {identyfikator}, kodowanie {kodowanie}.")

        ekstraktor = self._rejestr.dobierz(zrodlo.typ_zrodla, pozycja.format_zrodla)
        dokument = ekstraktor.wyekstrahuj(identyfikator, tekst)

        if zrodlo.typ_zrodla is TypZrodla.STRONA_WWW and czy_wymaga_skryptow(tekst, dokument.tekst):
            self._pomin(zrodlo, pozycja, KOMUNIKAT_WYMAGA_SKRYPTOW)
            return None

        czy_strona = zrodlo.typ_zrodla is TypZrodla.STRONA_WWW
        strukturalne = odczytaj_json_ld(tekst) if czy_strona else None
        metadane = (
            scal_metadane(dict(dokument.metadane), strukturalne)
            if strukturalne is not None
            else dict(dokument.metadane)
        )
        self._odnotuj_rozbieznosc(identyfikator, metadane)

        return _PrzygotowanyDokument(
            dokument=dokument,
            suma_kontrolna=suma_kontrolna,
            tekst_txt=self._tekst_dla_wersji_txt(
                ekstraktor.tekst_zawiera_znaczniki, dokument.tekst
            ),
            stan_pobrania=stan_pobrania,
            metadane=metadane,
            tekst_zrodla=tekst if czy_strona else None,
            tresc_porownawcza=strukturalne.tresc_porownawcza if strukturalne else None,
        )

    def _przygotuj_tresc_binarna(
        self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo
    ) -> _PrzygotowanyDokument:
        """Buduje dokument z pliku binarnego: PDF, DOCX albo EPUB.

        Format binarny nie przechodzi przez rozkodowanie tekstu, bo próba
        wykrycia kodowania znakowego na jego bajtach dałaby bezużyteczny wynik.
        Nie przechodzi też przez odczyt danych strukturalnych JSON-LD, bo ten
        dotyczy wyłącznie stron internetowych.
        """
        identyfikator = zrodlo.identyfikator_zrodla
        bajty = _odczytaj_bajty_pliku(Path(pozycja.wejscie.wartosc), identyfikator)

        self._zachowaj_oryginal(pozycja, zrodlo, "", bajty)
        self._loguj(logging.INFO, identyfikator, f"Źródło {identyfikator}, plik binarny.")

        ekstraktor = self._rejestr_binarny.dobierz(zrodlo.typ_zrodla, pozycja.format_zrodla)
        dokument = ekstraktor.wyekstrahuj(
            identyfikator, bajty, postep=self._postep_ocr(zrodlo.pochodzenie)
        )

        return _PrzygotowanyDokument(
            dokument=dokument,
            suma_kontrolna=zrodlo.checksum or "",
            tekst_txt=self._tekst_dla_wersji_txt(
                ekstraktor.tekst_zawiera_znaczniki, dokument.tekst
            ),
            stan_pobrania=None,
            metadane=dict(dokument.metadane),
            tekst_zrodla=None,
            tresc_porownawcza=None,
        )

    def _odnotuj_rozbieznosc(self, identyfikator: str, metadane: dict[str, str]) -> None:
        """Zapisuje w logu szczegółowym rozbieżność metadanych, o ile wystąpiła.

        Obie sprzeczne wartości są już w manifeście. Log dopisuje samą informację
        o tym, których pól dotyczy różnica, żeby nie trzeba było jej wyszukiwać.
        """
        rozbiezne = metadane.get(KLUCZ_ROZBIEZNOSCI)
        if not rozbiezne:
            return
        self._loguj(
            logging.WARNING,
            identyfikator,
            f"Metadane z danych strukturalnych różnią się od wyniku ekstraktora "
            f"w polach: {rozbiezne}. Obie wartości są w manifeście.",
        )

    def _znormalizuj_i_odloz(
        self,
        pozycja: PozycjaWejsciowa,
        zrodlo: Zrodlo,
        przygotowane: _PrzygotowanyDokument,
    ) -> None:
        """Normalizuje dokument i odkłada go do deduplikacji, bez zapisu pliku wynikowego.

        To jest pierwsza z trzech faz potoku. Znormalizowany tekst trafia do
        podkatalogu wyników pośrednich, a źródło dostaje status „znormalizowane”.
        Plik wynikowy powstaje dopiero w fazie zapisu, po deduplikacji, żeby nie
        tworzyć pliku dla źródła, które za chwilę okaże się duplikatem.
        """
        identyfikator = zrodlo.identyfikator_zrodla
        dokument = przygotowane.dokument
        stan_pobrania = przygotowane.stan_pobrania
        suma_kontrolna = przygotowane.suma_kontrolna

        znormalizowany = zbuduj_dokument_znormalizowany(identyfikator, dokument.tekst)

        # Źródło przekraczające bezpieczny limit słów nie jest już pomijane:
        # w fazie zapisu, po deduplikacji, faza pakowania dzieli je na części na
        # granicy jednostki strukturalnej. Podział zbyt dużego źródła to zadanie
        # etapu szóstego i jest tutaj rozstrzygnięte.

        ocena = self._ocen_jakosc(zrodlo, pozycja, dokument, znormalizowany.tekst, przygotowane)

        if ocena is None and not znormalizowany.tekst.strip():
            # Format celowo pominięty przez ocenę jakości, na przykład CSV albo
            # napisy SRT i VTT, nie ma żadnej treści: wynik zawierałby wyłącznie
            # nagłówek metadanych i nie wniesie nic do notatnika. Źródło jest
            # pomijane, zamiast zajmować slot notatnika pustą treścią. Format
            # oceniany, na przykład skan PDF bez warstwy tekstowej, zamiast tego
            # trafia niżej do oceny jakości jako podejrzany i zostaje zapisany do
            # ręcznego sprawdzenia.
            self._pomin(zrodlo, pozycja, KOMUNIKAT_PLIK_BEZ_TRESCI)
            return

        ostrzezenia = self._zbierz_ostrzezenia(zrodlo, dokument)
        decyzja = regula_md.ocen(dokument)
        nazwa_bazowa = nazwa_pliku_wynikowego(dokument.tytul, identyfikator)
        naglowek = self._naglowek(pozycja, zrodlo, dokument, przygotowane.metadane)

        self._zapisz_tekst_posredni(
            identyfikator, _SUFIKS_TEKST_ZNORMALIZOWANY, znormalizowany.tekst
        )
        if przygotowane.tekst_txt is not None:
            self._zapisz_tekst_posredni(
                identyfikator, _SUFIKS_TEKST_WERSJI_TXT, przygotowane.tekst_txt
            )

        self._checkpoint.zrodla[identyfikator] = StanZrodla(
            identyfikator=identyfikator,
            typ=zrodlo.typ_zrodla.value,
            pochodzenie=zrodlo.pochodzenie,
            checksum=suma_kontrolna,
            format_zrodla=pozycja.format_zrodla,
            status=StatusZrodla.ZNORMALIZOWANE.value,
            nazwa_bazowa_wyniku=nazwa_bazowa,
            wyniki=[],
            liczba_slow=znormalizowany.liczba_slow,
            liczba_znakow=znormalizowany.liczba_znakow,
            decyzja_md=decyzja.generuj_md,
            uzasadnienie_md=list(decyzja.spelnione_warunki),
            pobranie=stan_pobrania,
            metadane=dict(przygotowane.metadane),
            ocena_jakosci=ocena.ocena if ocena is not None else None,
            powody_oceny=list(ocena.powody) if ocena is not None else [],
            ostrzezenia=ostrzezenia,
            naglowek_metadanych=naglowek,
            grupa_pakowania=pozycja.grupa,
        )
        self._zapisz_checkpoint()
        self._loguj(
            logging.INFO,
            identyfikator,
            f"Znormalizowano źródło {identyfikator}: {znormalizowany.liczba_slow} słów, "
            f"wersja MD: {'tak' if decyzja.generuj_md else 'nie'}.",
        )

    def deduplikuj(self) -> None:
        """Druga faza potoku: porównuje znormalizowane źródła i oznacza duplikaty.

        Faza jest wykonywana raz. Po wznowieniu pracy, gdy przerwanie nastąpiło
        już po deduplikacji, znacznik w checkpoincie pozwala ją pominąć, żeby
        istniejące decyzje się nie powtórzyły ani nie zmieniły.
        """
        if self._checkpoint.deduplikacja.wykonana:
            self._loguj(
                logging.INFO, "-", "Deduplikacja była już wykonana w tym projekcie, pomijam."
            )
            return

        kandydaci = [
            ZrodloDoDeduplikacji(
                identyfikator=stan.identyfikator,
                tekst=self._wczytaj_tekst_posredni(stan.identyfikator, _SUFIKS_TEKST_ZNORMALIZOWANY)
                or "",
                liczba_slow=stan.liczba_slow or 0,
            )
            for stan in self._checkpoint.zrodla.values()
            if stan.status == StatusZrodla.ZNORMALIZOWANE.value
        ]

        wynik = deduplikuj(kandydaci, self._ustawienia_deduplikacji())
        self._zastosuj_wynik_deduplikacji(wynik)

        self._checkpoint.deduplikacja.wykonana = True
        self._checkpoint.deduplikacja.decyzje = [
            DecyzjaDeduplikacjiZapis(
                identyfikator_zrodla_glownego=decyzja.identyfikator_zrodla_glownego,
                identyfikator_duplikatu=decyzja.identyfikator_duplikatu,
                metoda=decyzja.metoda,
                wynik_podobienstwa=decyzja.wynik_podobienstwa,
                decyzja=decyzja.decyzja.value,
                uzasadnienie=decyzja.uzasadnienie,
                zachowane_fragmenty_unikalne=list(decyzja.zachowane_fragmenty_unikalne),
            )
            for decyzja in wynik.decyzje
        ]
        self._zapisz_checkpoint()

        liczba_pewnych = len(wynik.identyfikatory_duplikatow)
        liczba_do_przegladu = len(wynik.identyfikatory_do_przegladu)
        self._dziennik_wazny.zapisz(
            f"{ZDARZENIE_DEDUPLIKACJA_ZAKONCZONA}: {liczba_pewnych} pewnych duplikatów, "
            f"{liczba_do_przegladu} do rozstrzygnięcia"
        )
        self._loguj(
            logging.INFO,
            "-",
            f"Deduplikacja zakończona: {len(kandydaci)} źródeł porównanych, "
            f"{liczba_pewnych} pewnych duplikatów, {liczba_do_przegladu} do rozstrzygnięcia.",
        )

    def _zastosuj_wynik_deduplikacji(self, wynik: WynikDeduplikacjiZbioru) -> None:
        """Nadaje status „duplikat” pewnym duplikatom i odnotowuje pary do przeglądu."""
        po_identyfikatorze = {decyzja.identyfikator_duplikatu: decyzja for decyzja in wynik.decyzje}
        for identyfikator in sorted(wynik.identyfikatory_duplikatow):
            stan = self._checkpoint.zrodla[identyfikator]
            decyzja = po_identyfikatorze[identyfikator]
            stan.status = StatusZrodla.DUPLIKAT.value
            stan.duplikat_glowny = decyzja.identyfikator_zrodla_glownego
            stan.komunikat_bledu = KOMUNIKAT_DUPLIKAT.format(
                glowne=decyzja.identyfikator_zrodla_glownego,
                metoda=decyzja.metoda,
                podobienstwo=decyzja.wynik_podobienstwa,
            )
            self._dziennik_wazny.zapisz(f"{ZDARZENIE_ZRODLO_DUPLIKAT}: {stan.pochodzenie}")
            self._loguj(
                logging.INFO,
                identyfikator,
                f"Źródło {identyfikator} to duplikat {decyzja.identyfikator_zrodla_glownego}, "
                f"metoda {decyzja.metoda}, podobieństwo {decyzja.wynik_podobienstwa:.2f}.",
            )
        for identyfikator in sorted(wynik.identyfikatory_do_przegladu):
            decyzja = po_identyfikatorze[identyfikator]
            stan = self._checkpoint.zrodla[identyfikator]
            self._dziennik_wazny.zapisz(f"{ZDARZENIE_MOZLIWY_DUPLIKAT}: {stan.pochodzenie}")
            self._loguj(
                logging.WARNING,
                identyfikator,
                f"Źródło {identyfikator} może być duplikatem "
                f"{decyzja.identyfikator_zrodla_glownego} (podobieństwo "
                f"{decyzja.wynik_podobienstwa:.2f}, metoda {decyzja.metoda}). Oba zostają.",
            )

    def _ustawienia_deduplikacji(self) -> UstawieniaDeduplikacji:
        """Buduje ustawienia deduplikacji z konfiguracji projektu.

        Etap embeddingów lokalnych nie jest realizowany w tym zakresie. Gdy jest
        włączony w konfiguracji, potok dopisuje o tym czytelną informację i
        pracuje dalej bez tego etapu, tak jak przy braku narzędzia zewnętrznego.
        """
        if self._konfiguracja.deduplikacja_embeddingi_wlaczone:
            self._loguj(
                logging.WARNING,
                "-",
                "Etap embeddingów lokalnych w deduplikacji jest włączony w konfiguracji, "
                "ale nie został jeszcze zaimplementowany. Ten etap został pominięty.",
            )
        return UstawieniaDeduplikacji(
            etap_hash=self._konfiguracja.deduplikacja_hash_wlaczona,
            etap_kosmetyczny=self._konfiguracja.deduplikacja_kosmetyczna_wlaczona,
            etap_podobienstwa=self._konfiguracja.deduplikacja_podobienstwo_wlaczone,
            prog_duplikatu=self._konfiguracja.deduplikacja_prog_duplikatu,
            prog_do_przegladu=self._konfiguracja.deduplikacja_prog_do_przegladu,
        )

    def zapisz_pliki_wynikowe(self) -> None:
        """Trzecia faza potoku: pakowanie źródeł, które przeżyły deduplikację.

        Źródło przekraczające bezpieczny limit słów albo limit rozmiaru jest
        dzielone na części na granicy jednostki strukturalnej. Małe źródła jednej
        grupy tematycznej nadanej przez użytkownika są łączone w jeden plik.
        Źródło bez grupy, które mieści się w limicie, dostaje jeden plik razem
        z warunkową wersją Markdown, dokładnie jak przed etapem szóstym.
        """
        limity = LimityPakowania.z_konfiguracji(
            self._konfiguracja.bezpieczny_limit_slow, self._konfiguracja.bezpieczny_limit_mb
        )
        do_pakowania = [
            stan
            for stan in self._checkpoint.zrodla.values()
            if stan.status == StatusZrodla.ZNORMALIZOWANE.value
        ]
        grupy: dict[str, list[StanZrodla]] = {}
        for stan in do_pakowania:
            if stan.grupa_pakowania:
                grupy.setdefault(stan.grupa_pakowania, []).append(stan)
            else:
                self._spakuj_zrodlo_samodzielne(stan, limity)
        for nazwa_grupy, stany in grupy.items():
            self._spakuj_grupe(nazwa_grupy, stany, limity)

    def _spakuj_zrodlo_samodzielne(self, stan: StanZrodla, limity: LimityPakowania) -> None:
        """Pakuje jedno źródło spoza grupy: jeden plik albo kilka ponumerowanych części."""
        tekst = self._wczytaj_tekst_posredni(stan.identyfikator, _SUFIKS_TEKST_ZNORMALIZOWANY)
        if tekst is None:
            self._oznacz_brak_tekstu_posredniego(stan)
            return
        podzial = podziel_na_czesci(tekst, limity)
        if len(podzial.czesci) == 1:
            self._zapisz_zrodlo_niepodzielone(stan, tekst)
            return
        self._zapisz_czesci_zrodla(stan, podzial.czesci, list(podzial.ostrzezenia))

    def _oznacz_brak_tekstu_posredniego(self, stan: StanZrodla) -> None:
        """Zamienia brak pliku wyniku pośredniego na kontrolowany błąd źródła."""
        stan.status = StatusZrodla.BLAD.value
        stan.komunikat_bledu = KOMUNIKAT_BRAK_TEKSTU_POSREDNIEGO
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_BLAD)
        self._loguj(logging.ERROR, stan.identyfikator, KOMUNIKAT_BRAK_TEKSTU_POSREDNIEGO)

    def _zapisz_zrodlo_niepodzielone(self, stan: StanZrodla, tekst: str) -> None:
        """Zapisuje jedno źródło mieszczące się w limicie: TXT zawsze, MD warunkowo."""
        identyfikator = stan.identyfikator
        znormalizowany = DokumentZnormalizowany(
            identyfikator_zrodla=identyfikator,
            tekst=tekst,
            liczba_slow=stan.liczba_slow or 0,
            liczba_znakow=stan.liczba_znakow or 0,
        )
        # Pole poziomu pewności służy tu tylko odtworzeniu decyzji dla zapisu. Sam
        # zapis czyta wyłącznie `generuj_md`, a ten jest już rozstrzygnięty.
        decyzja = regula_md.DecyzjaFormatu(
            generuj_md=bool(stan.decyzja_md),
            spelnione_warunki=tuple(stan.uzasadnienie_md),
            poziom_pewnosci_wystarczajacy=bool(stan.decyzja_md),
        )
        tekst_txt = self._wczytaj_tekst_posredni(identyfikator, _SUFIKS_TEKST_WERSJI_TXT)

        pliki = zapisz_wyniki(
            self._uklad.pliki_wynikowe,
            stan.nazwa_bazowa_wyniku or nazwa_pliku_wynikowego(None, identyfikator),
            identyfikator,
            znormalizowany,
            decyzja,
            formaty_wlaczone=self._konfiguracja.formaty_wynikowe,
            tekst_txt=tekst_txt,
            naglowek=stan.naglowek_metadanych or "",
        )

        stan.wyniki = [self._stan_wyniku(plik, [identyfikator], None, None) for plik in pliki]
        stan.status = StatusZrodla.SPAKOWANE.value
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_PRZYJETE)
        for _ in pliki:
            self._dziennik_wazny.zapisz(ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY)
        self._loguj(
            logging.INFO,
            identyfikator,
            f"Zapisano {len(pliki)} plików wynikowych, wersja MD: "
            f"{'tak' if stan.decyzja_md else 'nie'}.",
        )

    def _zapisz_czesci_zrodla(
        self, stan: StanZrodla, czesci: list[str], ostrzezenia: list[str]
    ) -> None:
        """Zapisuje kolejne części źródła podzielonego, każdą z własnym oznaczeniem części."""
        identyfikator = stan.identyfikator
        liczba = len(czesci)
        nazwa_bazowa = stan.nazwa_bazowa_wyniku or nazwa_pliku_wynikowego(None, identyfikator)
        wyniki: list[StanWyniku] = []
        for numer, czesc in enumerate(czesci, start=1):
            naglowek = z_oznaczeniem_czesci(stan.naglowek_metadanych or "", numer, liczba)
            tresc = zloz_plik([(naglowek, czesc)])
            nazwa = nazwa_pliku_czesci(nazwa_bazowa, numer, liczba)
            plik = zapisz_plik_pakietu(self._uklad.pliki_wynikowe, nazwa, tresc, [identyfikator])
            wyniki.append(self._stan_wyniku(plik, [identyfikator], numer, liczba))

        stan.wyniki = wyniki
        stan.ostrzezenia_pakowania = list(ostrzezenia)
        stan.status = StatusZrodla.SPAKOWANE.value
        self._zapisz_checkpoint()

        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_PRZYJETE)
        self._dziennik_wazny.zapisz(
            f"{ZDARZENIE_ZRODLO_PODZIELONE}: {stan.pochodzenie}, {liczba} części"
        )
        for _ in wyniki:
            self._dziennik_wazny.zapisz(ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY)
        self._odnotuj_ostrzezenia_pakowania(stan, ostrzezenia)
        self._loguj(
            logging.INFO,
            identyfikator,
            f"Źródło {identyfikator} podzielone na {liczba} części po przekroczeniu limitu.",
        )

    def _spakuj_grupe(
        self, nazwa_grupy: str, stany: list[StanZrodla], limity: LimityPakowania
    ) -> None:
        """Pakuje jedną grupę tematyczną: dzieli źródła duże i łączy małe w jak najmniej plików.

        Wszystkie źródła grupy dostają status „spakowane” w jednym zapisie
        checkpointu. Przerwanie pracy przed tym zapisem zostawia je jako
        „znormalizowane”, więc wznowienie planuje grupę od nowa, nadpisując pliki.
        """
        zrodla_do_pakowania: list[ZrodloDoPakowania] = []
        po_identyfikatorze: dict[str, StanZrodla] = {}
        for stan in stany:
            tekst = self._wczytaj_tekst_posredni(stan.identyfikator, _SUFIKS_TEKST_ZNORMALIZOWANY)
            if tekst is None:
                self._oznacz_brak_tekstu_posredniego(stan)
                continue
            po_identyfikatorze[stan.identyfikator] = stan
            zrodla_do_pakowania.append(
                ZrodloDoPakowania(stan.identyfikator, tekst, grupa=nazwa_grupy)
            )
        if not zrodla_do_pakowania:
            return

        for stan in po_identyfikatorze.values():
            stan.wyniki = []
            stan.ostrzezenia_pakowania = []

        for plan in rozplanuj_grupe(nazwa_grupy, zrodla_do_pakowania, limity):
            self._zapisz_plan_grupy(nazwa_grupy, plan, po_identyfikatorze)

        for stan in po_identyfikatorze.values():
            if stan.wyniki:
                stan.status = StatusZrodla.SPAKOWANE.value
        self._zapisz_checkpoint()

        sciezki = {
            wynik.sciezka_wzgledna for stan in po_identyfikatorze.values() for wynik in stan.wyniki
        }
        self._dziennik_wazny.zapisz(
            f"{ZDARZENIE_GRUPA_SPAKOWANA}: {nazwa_grupy}, "
            f"{len(po_identyfikatorze)} źródeł, {len(sciezki)} plików"
        )
        for stan in po_identyfikatorze.values():
            self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_PRZYJETE)
            self._odnotuj_ostrzezenia_pakowania(stan, stan.ostrzezenia_pakowania)
        for _ in sciezki:
            self._dziennik_wazny.zapisz(ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY)
        self._loguj(
            logging.INFO,
            "-",
            f"Grupa „{nazwa_grupy}”: {len(po_identyfikatorze)} źródeł w {len(sciezki)} plikach.",
        )

    def _zapisz_plan_grupy(
        self, nazwa_grupy: str, plan: PlanPliku, po_identyfikatorze: dict[str, StanZrodla]
    ) -> None:
        """Zapisuje jeden plik zaplanowany dla grupy i dopisuje go do stanu jego źródeł."""
        identyfikatory = [fragment.identyfikator for fragment in plan.fragmenty]

        if plan.czy_grupa:
            nazwa_bazowa = nazwa_pliku_grupy(nazwa_grupy, identyfikatory)
            oznaczenie = (
                oznaczenie_pliku_grupy(nazwa_grupy, plan.numer_czesci, plan.liczba_czesci)
                if plan.czy_wieloczesciowy
                else ""
            )
            fragmenty_tekstu = [
                (
                    po_identyfikatorze[fragment.identyfikator].naglowek_metadanych or "",
                    fragment.tekst,
                )
                for fragment in plan.fragmenty
            ]
            tresc = zloz_plik(fragmenty_tekstu, oznaczenie_pliku=oznaczenie)
        else:
            (fragment,) = plan.fragmenty
            stan = po_identyfikatorze[fragment.identyfikator]
            nazwa_bazowa = stan.nazwa_bazowa_wyniku or nazwa_pliku_wynikowego(
                None, stan.identyfikator
            )
            naglowek = z_oznaczeniem_czesci(
                stan.naglowek_metadanych or "", plan.numer_czesci, plan.liczba_czesci
            )
            tresc = zloz_plik([(naglowek, fragment.tekst)])

        nazwa = (
            nazwa_pliku_czesci(nazwa_bazowa, plan.numer_czesci, plan.liczba_czesci)
            if plan.czy_wieloczesciowy
            else nazwa_bazowa
        )
        plik = zapisz_plik_pakietu(self._uklad.pliki_wynikowe, nazwa, tresc, identyfikatory)
        numer, liczba = _numery_czesci(plan)
        wynik = self._stan_wyniku(plik, identyfikatory, numer, liczba)
        for identyfikator in identyfikatory:
            po_identyfikatorze[identyfikator].wyniki.append(wynik)
        for ostrzezenie in plan.ostrzezenia:
            for identyfikator in identyfikatory:
                po_identyfikatorze[identyfikator].ostrzezenia_pakowania.append(ostrzezenie)

    def _stan_wyniku(
        self,
        plik: PlikWynikowy,
        identyfikatory_zrodel: list[str],
        numer_czesci: int | None,
        liczba_czesci: int | None,
    ) -> StanWyniku:
        """Buduje wpis stanu jednego pliku wynikowego z jego rzeczywistej zawartości."""
        return StanWyniku(
            sciezka_wzgledna=plik.sciezka.relative_to(self._uklad.katalog_projektu).as_posix(),
            format=plik.format.value,
            liczba_slow=plik.liczba_slow,
            liczba_znakow_pliku=plik.liczba_znakow,
            rozmiar_bajtow=plik.rozmiar_bajtow,
            checksum=plik.checksum,
            identyfikatory_zrodel=list(identyfikatory_zrodel),
            numer_czesci=numer_czesci,
            liczba_czesci=liczba_czesci,
        )

    def _odnotuj_ostrzezenia_pakowania(self, stan: StanZrodla, ostrzezenia: list[str]) -> None:
        """Zapisuje ostrzeżenia podziału w obu logach, tą samą drogą co pominięcie."""
        if not ostrzezenia:
            return
        self._dziennik_wazny.zapisz(f"{ZDARZENIE_OSTRZEZENIE_PODZIALU}: {stan.pochodzenie}")
        for ostrzezenie in ostrzezenia:
            self._loguj(logging.WARNING, stan.identyfikator, f"Ostrzeżenie podziału: {ostrzezenie}")

    def _zapisz_tekst_posredni(self, identyfikator: str, sufiks: str, tekst: str) -> None:
        """Zapisuje jeden plik wyniku pośredniego w UTF-8 z końcami wierszy LF."""
        self._uklad.wyniki_posrednie.mkdir(parents=True, exist_ok=True)
        cel = self._uklad.wyniki_posrednie / f"{identyfikator}.{sufiks}"
        with cel.open("w", encoding="utf-8", newline="\n") as plik:
            plik.write(tekst)

    def _wczytaj_tekst_posredni(self, identyfikator: str, sufiks: str) -> str | None:
        """Odczytuje plik wyniku pośredniego albo zwraca nic, gdy go nie ma."""
        cel = self._uklad.wyniki_posrednie / f"{identyfikator}.{sufiks}"
        if not cel.is_file():
            return None
        return cel.read_text(encoding="utf-8")

    def _ma_tekst_posredni(self, identyfikator: str) -> bool:
        cel = self._uklad.wyniki_posrednie / f"{identyfikator}.{_SUFIKS_TEKST_ZNORMALIZOWANY}"
        return cel.is_file()

    def _zbierz_ostrzezenia(self, zrodlo: Zrodlo, dokument: DokumentWyekstrahowany) -> list[str]:
        """Zbiera ostrzeżenia zgłoszone przez ekstraktor i odnotowuje je w obu logach.

        Źródło bez żadnej znormalizowanej treści, dla formatu celowo wyłączonego
        z oceny jakości, jest pomijane wcześniej, w `_znormalizuj_i_odloz`, i tutaj
        w ogóle nie dociera. Format oceniany, na przykład skan PDF bez warstwy
        tekstowej, dociera tutaj nawet z pustą treścią, bo jego pusty wynik
        obsługuje ocena jakości, a nie to miejsce.

        Ostrzeżenie nie zmienia statusu źródła. Źródło jest zapisywane normalnie,
        a ostrzeżenie trafia do checkpointu, a stąd do manifestu i do raportu.
        """
        ostrzezenia = list(dokument.ostrzezenia)
        if not ostrzezenia:
            return []

        self._dziennik_wazny.zapisz(f"{ZDARZENIE_OSTRZEZENIE_EKSTRAKCJI}: {zrodlo.pochodzenie}")
        for ostrzezenie in ostrzezenia:
            self._loguj(logging.WARNING, zrodlo.identyfikator_zrodla, f"Ostrzeżenie: {ostrzezenie}")
        return ostrzezenia

    def _ocen_jakosc(
        self,
        zrodlo: Zrodlo,
        pozycja: PozycjaWejsciowa,
        dokument: DokumentWyekstrahowany,
        tekst: str,
        przygotowane: _PrzygotowanyDokument,
    ) -> OcenaJakosci | None:
        """Ocenia jakość wyniku dla źródeł, w których treść powstaje przez ekstrakcję.

        Strona, film, PDF, DOCX, EPUB i plik HTML lokalny przechodzą przez
        rozpoznawanie treści, więc mogą stracić jej część po cichu i dlatego są
        oceniane. Tekst wklejony oraz pliki TXT i MD nie są oceniane, bo ich
        treść jest dokładnie tym, co podał użytkownik. Plik CSV oraz napisy SRT
        i VTT też są wyłączone: z natury formatu nie mają tytułu ani podziału na
        akapity, więc dostałyby nienaprawialne ostrzeżenie przy każdym pliku.
        Ocena „podejrzana” dla materiału, którego nie da się poprawić, byłaby
        ostrzeżeniem bez znaczenia, a takie uczy pomijać wszystkie ostrzeżenia.
        """
        if not _czy_ocenic_jakosc(zrodlo.typ_zrodla, pozycja.format_zrodla):
            return None
        ocena = ocen_jakosc(
            tekst,
            tytul=dokument.tytul,
            tekst_zrodla=przygotowane.tekst_zrodla,
            tresc_porownawcza=przygotowane.tresc_porownawcza,
        )
        if ocena.czy_podejrzana:
            self._odnotuj_podejrzana_jakosc(zrodlo, ocena.powody)
        return ocena

    def _odnotuj_podejrzana_jakosc(self, zrodlo: Zrodlo, powody: tuple[str, ...]) -> None:
        """Zapisuje podejrzany wynik ekstrakcji w obu logach.

        Źródło jest zapisywane normalnie i nie jest kasowane. Wpis w logu ważnym
        istnieje po to, żeby użytkownik dowiedział się o sprawie w trakcie pracy,
        a nie dopiero z raportu końcowego.
        """
        self._dziennik_wazny.zapisz(f"{ZDARZENIE_JAKOSC_PODEJRZANA}: {zrodlo.pochodzenie}")
        self._loguj(
            logging.WARNING,
            zrodlo.identyfikator_zrodla,
            "Wynik ekstrakcji wygląda podejrzanie. Powody: " + "; ".join(powody),
        )

    def _tresc_zrodla(
        self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo
    ) -> tuple[str, str, bytes | None, StanPobrania | None, str] | None:
        """Zwraca treść źródła wraz z danymi towarzyszącymi albo nic, gdy je pominięto.

        Dla pliku i tekstu wklejonego treść pochodzi z odczytu wejścia. Dla
        adresu strony pochodzi z wcześniejszej fazy pobrania. Wartość pusta
        oznacza, że źródło zostało już zapisane jako pominięte i dalsze etapy
        nie mają się nim zajmować.
        """
        if pozycja.wejscie.typ_wejscia is not TypWejscia.URL:
            tekst, kodowanie = wczytaj_tresc_zrodla(pozycja)
            return tekst, kodowanie, None, None, zrodlo.checksum or ""

        wynik = self._pobrane.get(zrodlo.identyfikator_zrodla)
        if isinstance(wynik, PominietePobranie):
            self._pomin(zrodlo, pozycja, wynik.powod)
            return None
        if isinstance(wynik, BladGnb):
            raise wynik
        if wynik is None:
            raise BladTrwaly(
                f"Brak wyniku pobrania dla adresu {zrodlo.pochodzenie}.",
                zrodlo.identyfikator_zrodla,
            )

        tekst, kodowanie = _zdekoduj_odpowiedz(wynik)
        stan_pobrania = StanPobrania(
            adres_koncowy=wynik.adres_koncowy,
            kod_odpowiedzi=wynik.kod_odpowiedzi,
            deklarowane_kodowanie=wynik.deklarowane_kodowanie,
            etag=wynik.etag,
            last_modified=wynik.last_modified,
            z_pamieci_podrecznej=wynik.z_pamieci_podrecznej,
        )
        return tekst, kodowanie, wynik.tresc, stan_pobrania, suma_kontrolna_bajtow(wynik.tresc)

    def _tekst_dla_wersji_txt(self, zawiera_znaczniki: bool, tekst: str) -> str | None:
        """Zwraca treść wersji TXT, gdy ma się różnić od treści wersji MD.

        Dla ekstraktora zwracającego tekst ze znacznikami wersja TXT powstaje
        przez przepisanie dokumentu bez znaczników, a jej treść jest ponownie
        normalizowana, żeby oba pliki wynikowe przechodziły te same reguły.
        Dla tekstu już czystego zwracana jest wartość pusta, co oznacza „użyj
        tekstu znormalizowanego bez zmian”. Argument `zawiera_znaczniki` to
        `tekst_zawiera_znaczniki` użytego ekstraktora, tekstowego albo binarnego.
        """
        if not zawiera_znaczniki:
            return None
        return znormalizuj(zamien_markdown_na_tekst(tekst))

    def _zachowaj_oryginal(
        self,
        pozycja: PozycjaWejsciowa,
        zrodlo: Zrodlo,
        tekst: str,
        surowe_bajty: bytes | None = None,
    ) -> None:
        """Zachowuje oryginał źródła w podkatalogu materiałów źródłowych.

        Strona internetowa jest zapisywana jako surowe bajty odpowiedzi, bez
        przekodowywania. Deklarowane kodowanie trafia do manifestu, więc ponowna
        ekstrakcja z zachowanego pliku odczyta go poprawnie także wtedy, gdy
        strona nie była w UTF-8.

        Przy wyłączonym ustawieniu `zachowuj_oryginaly` nie powstaje ani plik,
        ani sam podkatalog materiałów źródłowych.
        """
        if not self._konfiguracja.zachowuj_oryginaly:
            return
        self._uklad.materialy_zrodlowe.mkdir(parents=True, exist_ok=True)
        rozszerzenie = _rozszerzenie_oryginalu(pozycja.format_zrodla)
        cel = self._uklad.materialy_zrodlowe / f"{zrodlo.identyfikator_zrodla}.{rozszerzenie}"
        if cel.exists():
            return
        if surowe_bajty is not None:
            cel.write_bytes(surowe_bajty)
            return
        if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK:
            zrodlo_pliku = Path(pozycja.wejscie.wartosc)
            if zrodlo_pliku.is_file():
                cel.write_bytes(zrodlo_pliku.read_bytes())
                return
        with cel.open("w", encoding="utf-8", newline="\n") as plik:
            plik.write(tekst)

    def _liczba_aktywnych(self) -> int:
        return sum(
            1 for stan in self._checkpoint.zrodla.values() if stan.status != StatusZrodla.BLAD.value
        )

    def _pomin(self, zrodlo: Zrodlo, pozycja: PozycjaWejsciowa, komunikat: str) -> None:
        self._checkpoint.zrodla[zrodlo.identyfikator_zrodla] = StanZrodla(
            identyfikator=zrodlo.identyfikator_zrodla,
            typ=zrodlo.typ_zrodla.value,
            pochodzenie=zrodlo.pochodzenie,
            checksum=zrodlo.checksum or "",
            format_zrodla=pozycja.format_zrodla,
            status=StatusZrodla.POMINIETE.value,
            komunikat_bledu=komunikat,
        )
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_POMINIETE)
        self._loguj(
            logging.WARNING,
            zrodlo.identyfikator_zrodla,
            f"Pominięto źródło {zrodlo.identyfikator_zrodla}: {komunikat}",
        )

    def _zapisz_blad_zrodla(self, zrodlo: Zrodlo, pozycja: PozycjaWejsciowa, blad: BladGnb) -> None:
        self._checkpoint.zrodla[zrodlo.identyfikator_zrodla] = StanZrodla(
            identyfikator=zrodlo.identyfikator_zrodla,
            typ=zrodlo.typ_zrodla.value,
            pochodzenie=zrodlo.pochodzenie,
            checksum=zrodlo.checksum or "",
            format_zrodla=pozycja.format_zrodla,
            status=StatusZrodla.BLAD.value,
            komunikat_bledu=blad.komunikat,
        )
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_BLAD)
        self._loguj(
            logging.ERROR,
            zrodlo.identyfikator_zrodla,
            f"Błąd źródła {zrodlo.identyfikator_zrodla}: {blad.komunikat}",
        )

    def _zapisz_blad_wejscia(self, pozycja: PozycjaWejsciowa, blad: BladGnb) -> None:
        """Zapisuje wejście, którego nie dało się zwalidować, jako błąd albo pominięcie.

        Wejście przekraczające limit dostaje status „pominiete”, tak samo jak
        źródło przekraczające limit słów. Pozostałe błędy walidacji, na przykład
        brak pliku albo nieobsługiwany format, pozostają statusem „blad”.
        """
        identyfikator = identyfikator_awaryjny(pozycja)
        pochodzenie = (
            Path(pozycja.wejscie.wartosc).name
            if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK
            else "tekst wklejony"
        )
        pominiecie = isinstance(blad, PrzekroczonoLimit)
        self._checkpoint.zrodla[identyfikator] = StanZrodla(
            identyfikator=identyfikator,
            typ=pozycja.wejscie.typ_wejscia.value,
            pochodzenie=pochodzenie,
            checksum="",
            format_zrodla=pozycja.format_zrodla,
            status=(StatusZrodla.POMINIETE if pominiecie else StatusZrodla.BLAD).value,
            komunikat_bledu=blad.komunikat,
        )
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(
            ZDARZENIE_ZRODLO_POMINIETE if pominiecie else ZDARZENIE_ZRODLO_BLAD
        )
        if pominiecie:
            self._loguj(logging.WARNING, identyfikator, f"Pominięto wejście: {blad.komunikat}")
            return
        self._loguj(logging.ERROR, identyfikator, f"Błąd wejścia: {blad.komunikat}")

    def _zapisz_checkpoint(self) -> None:
        # Checkpoint jest zapisywany po każdym źródle, żeby po przerwaniu pracy
        # dało się wznowić bez powtórzeń. Do log_wazne.txt trafia dopiero zapis
        # końcowy, żeby ten log nie tonął we wpisach technicznych.
        self._checkpoint.czas_ostatniej_zmiany = self._zegar().isoformat()
        zapisz(self._uklad.checkpoint, self._checkpoint)

    def _postep_ocr(self, pochodzenie: str) -> PostepEkstrakcji | None:
        """Buduje wywołanie zwrotne postępu OCR skanu dla jednego źródła.

        Bez odbiorcy postępu zwraca nic, więc ekstraktor nie płaci za budowanie
        komunikatów, których i tak nikt nie usłyszy. Z odbiorcą zgłasza po każdej
        rozpoznanej stronie zdanie gotowe do ogłoszenia w regionie postępu.
        """
        if self._postep is None:
            return None

        def zglos(wykonano: int, wszystkich: int) -> None:
            _zglos_postep(
                self._postep,
                FazaPotoku.OCR,
                wykonano,
                wszystkich,
                f"Rozpoznawanie tekstu ze skanu „{pochodzenie}”, strona {wykonano} z {wszystkich}",
            )

        return zglos

    def _loguj(self, poziom: int, identyfikator: str, komunikat: str) -> None:
        self._log.log(poziom, komunikat, extra={"identyfikator_zrodla": identyfikator})


def _odczytaj_bajty_pliku(sciezka: Path, identyfikator: str) -> bytes:
    """Odczytuje zawartość pliku, zamieniając awarię odczytu na błąd trwały.

    Plik usunięty, przeniesiony albo zablokowany przez inny program między
    walidacją wejścia a odczytem podnosi ``OSError``, który nie jest wyjątkiem
    projektu. Bez tego opakowania wywracał cały przebieg razem ze wszystkimi
    poprawnymi źródłami z tej samej partii.
    """
    try:
        return sciezka.read_bytes()
    except OSError as blad:
        raise BladTrwaly(
            f"Nie udało się odczytać pliku {sciezka.name}. Plik mógł zostać usunięty, "
            f"przeniesiony albo zablokowany przez inny program. Szczegóły: {blad.strerror}.",
            identyfikator,
        ) from blad


def _opis_dlugosci_z_metadanych(metadane: dict[str, str]) -> str:
    """Zamienia zapisaną w metadanych długość w sekundach na czytelny opis."""
    surowa = metadane.get("dlugosc_sekundy", "")
    if not surowa.isdigit():
        return ""
    return opis_dlugosci(int(surowa))


def _opis_rodzaju_napisow(metadane: dict[str, str]) -> str:
    """Zwraca rodzaj napisów w postaci przeznaczonej dla człowieka."""
    typ = metadane.get("typ_napisow", "")
    return opis_typu_napisow(typ) if typ else ""


def _pobierz_strony(
    pozycje: Sequence[PozycjaWejsciowa],
    konfiguracja: Konfiguracja,
    checkpoint: Checkpoint,
    log: logging.Logger,
    transport: httpx.AsyncBaseTransport | None = None,
    postep: WywolanieZwrotnePostepu | None = None,
) -> dict[str, WynikFazyPobrania]:
    """Pobiera wszystkie adresy z listy wejść i zwraca wyniki po identyfikatorze źródła.

    Adresy, które w checkpoincie mają już status końcowy, nie są pobierane
    ponownie. Powtórzony adres jest pobierany raz, bo jego identyfikator wynika
    z kanonicznej postaci adresu.

    Postęp jest zgłaszany zgrubnie: jedno zdarzenie przed pobieraniem i jedno po
    nim. Samo pobieranie jest tu najdłuższym odcinkiem pracy, więc zdarzenie
    otwierające mówi użytkownikowi, że praca trwa, mimo braku zapisu do
    checkpointu w tym czasie.
    """
    zadania = _zadania_do_pobrania(pozycje, checkpoint)
    if not zadania:
        return {}

    log.info("Faza pobrania: %d adresów do pobrania.", len(zadania))
    _zglos_postep(
        postep,
        FazaPotoku.POBIERANIE_STRON,
        0,
        len(zadania),
        f"Pobieranie {len(zadania)} adresów stron",
    )
    wyniki = asyncio.run(
        _pobierz_asynchronicznie([zadanie for _, zadanie in zadania], konfiguracja, log, transport)
    )
    _zglos_postep(
        postep,
        FazaPotoku.POBIERANIE_STRON,
        len(zadania),
        len(zadania),
        f"Pobrano {len(zadania)} adresów stron",
    )
    return {identyfikator: wynik for (identyfikator, _), wynik in zip(zadania, wyniki, strict=True)}


def _pobierz_filmy(
    pozycje: Sequence[PozycjaWejsciowa],
    konfiguracja: Konfiguracja,
    checkpoint: Checkpoint,
    log: logging.Logger,
    transport: httpx.AsyncBaseTransport | None = None,
    pobieracz_youtube: PobieraczYouTube | None = None,
    postep: WywolanieZwrotnePostepu | None = None,
) -> dict[str, WynikFazyFilmu]:
    """Pobiera napisy wszystkich filmów z listy wejść i zwraca wyniki po identyfikatorze.

    Playlisty, kanały i adresy YouTube bez identyfikatora filmu są odrzucane bez
    sięgania do sieci, ze statusem pominięcia i powodem gotowym do pokazania
    użytkownikowi. Filmy przetworzone w poprzednim uruchomieniu nie są pobierane
    ponownie.

    Postęp jest zgłaszany zgrubnie, jednym zdarzeniem przed pobieraniem napisów
    i jednym po nim, tak samo jak dla pobierania stron.
    """
    wyniki: dict[str, WynikFazyFilmu] = {}
    do_pobrania: list[tuple[str, str, Zadanie]] = []
    widziane: set[str] = set()

    for pozycja in pozycje:
        if pozycja.format_zrodla != FORMAT_YOUTUBE:
            continue
        kanoniczny = pozycja.adres_kanoniczny or pozycja.wejscie.wartosc
        identyfikator = identyfikator_adresu(TypZrodla.YOUTUBE, kanoniczny)
        if identyfikator in widziane:
            continue
        stan = checkpoint.zrodla.get(identyfikator)
        if stan is not None and stan.status in _STATUSY_KONCOWE:
            continue
        widziane.add(identyfikator)

        rozpoznanie = rozpoznaj(pozycja.wejscie.wartosc)
        if not rozpoznanie.czy_film or rozpoznanie.identyfikator_filmu is None:
            wyniki[identyfikator] = PominietyFilm(
                identyfikator="",
                adres_kanoniczny=kanoniczny,
                powod=rozpoznanie.powod_odrzucenia or "Adres nie wskazuje pojedynczego filmu.",
            )
            continue

        do_pobrania.append(
            (
                identyfikator,
                rozpoznanie.identyfikator_filmu,
                Zadanie(
                    adres_pobierania=kanoniczny,
                    klucz_kanoniczny=kanoniczny,
                    wskazany_jawnie=pozycja.wskazane_jawnie,
                ),
            )
        )

    if do_pobrania:
        log.info("Faza pobrania napisów: %d filmów do pobrania.", len(do_pobrania))
        _zglos_postep(
            postep,
            FazaPotoku.POBIERANIE_NAPISOW,
            0,
            len(do_pobrania),
            f"Pobieranie napisów {len(do_pobrania)} filmów",
        )
        wyniki.update(
            asyncio.run(
                _pobierz_filmy_asynchronicznie(
                    do_pobrania, konfiguracja, log, transport, pobieracz_youtube
                )
            )
        )
        _zglos_postep(
            postep,
            FazaPotoku.POBIERANIE_NAPISOW,
            len(do_pobrania),
            len(do_pobrania),
            f"Pobrano napisy {len(do_pobrania)} filmów",
        )
    return wyniki


async def _pobierz_filmy_asynchronicznie(
    zadania: Sequence[tuple[str, str, Zadanie]],
    konfiguracja: Konfiguracja,
    log: logging.Logger,
    transport: httpx.AsyncBaseTransport | None,
    pobieracz_youtube: PobieraczYouTube | None,
) -> dict[str, WynikFazyFilmu]:
    """Sprawdza reguły witryny i pobiera napisy kolejnych filmów.

    Filmy są pobierane po kolei, ponieważ obie biblioteki napisów pracują
    synchronicznie i same wykonują swoje żądania. Praca każdej z nich odbywa się
    w osobnym wątku, żeby nie blokować pętli zdarzeń.
    """
    preferencje = _preferencje_napisow(konfiguracja)
    pobieracz = pobieracz_youtube or PobieraczYouTube(preferencje, log=log)
    pamiec = _otworz_pamiec_podreczna(konfiguracja, log)
    wyniki: dict[str, WynikFazyFilmu] = {}

    try:
        async with Pobieracz(
            UstawieniaPobierania.z_konfiguracji(konfiguracja),
            transport=transport,
            log=log,
        ) as klient:
            for identyfikator, identyfikator_filmu, zadanie in zadania:
                pominiecie = await klient.sprawdz_reguly_witryny(zadanie)
                if pominiecie is not None:
                    wyniki[identyfikator] = PominietyFilm(
                        identyfikator=identyfikator_filmu,
                        adres_kanoniczny=zadanie.klucz_kanoniczny,
                        powod=pominiecie.powod,
                    )
                    continue
                wyniki[identyfikator] = await _film_z_pamieci_albo_serwisu(
                    identyfikator_filmu, pobieracz, preferencje, pamiec, konfiguracja, log
                )
    finally:
        if pamiec is not None:
            pamiec.zamknij()
    return wyniki


async def _film_z_pamieci_albo_serwisu(
    identyfikator_filmu: str,
    pobieracz: PobieraczYouTube,
    preferencje: PreferencjeNapisow,
    pamiec: PamiecPodreczna | None,
    konfiguracja: Konfiguracja,
    log: logging.Logger,
) -> WynikFazyFilmu:
    """Zwraca napisy filmu z pamięci podręcznej albo pobiera je z serwisu."""
    klucz = klucz_pamieci_podrecznej(identyfikator_filmu, preferencje)
    if pamiec is not None:
        wpis = pamiec.odczytaj(klucz)
        if wpis is not None and wpis.czy_swiezy(
            konfiguracja.maksymalny_wiek_cache_dni, teraz_utc()
        ):
            zapamietany = z_json(wpis.tresc)
            if zapamietany is not None:
                log.info("Napisy filmu %s wzięte z pamięci podręcznej.", identyfikator_filmu)
                return zapamietany

    try:
        wynik = await asyncio.to_thread(pobieracz.pobierz, identyfikator_filmu)
    except BladGnb as blad:
        return blad

    if isinstance(wynik, WynikYouTube) and pamiec is not None:
        pamiec.zapisz(
            WpisCache(
                klucz=klucz,
                adres_koncowy=wynik.adres_kanoniczny,
                kod_odpowiedzi=200,
                typ_zawartosci=_TYP_ZAWARTOSCI_NAPISOW,
                deklarowane_kodowanie="utf-8",
                etag=None,
                last_modified=None,
                tresc=do_json(wynik),
                pobrano=teraz_utc(),
            )
        )
    return wynik


def _rozszerzenie_oryginalu(format_zrodla: str) -> str:
    """Zwraca rozszerzenie pliku, pod którym zachowywany jest oryginał źródła.

    Napisy filmu są zachowywane jako plik JSON, ponieważ w takiej postaci są
    pobierane i w takiej dają się ponownie odczytać.
    """
    if format_zrodla == FORMAT_YOUTUBE:
        return _ROZSZERZENIE_ORYGINALU_NAPISOW
    return format_zrodla or _ROZSZERZENIE_ORYGINALU_TEKSTU


def _preferencje_napisow(konfiguracja: Konfiguracja) -> PreferencjeNapisow:
    """Buduje preferencje wyboru napisów z konfiguracji aplikacji."""
    return PreferencjeNapisow(
        jezyki=konfiguracja.jezyki_napisow,
        dopuszczaj_automatyczne=konfiguracja.napisy_automatyczne,
        dopuszczaj_tlumaczone=konfiguracja.napisy_tlumaczone,
        awaryjny_dowolny_jezyk=konfiguracja.awaryjny_dowolny_jezyk,
    )


def _zadania_do_pobrania(
    pozycje: Sequence[PozycjaWejsciowa], checkpoint: Checkpoint
) -> list[tuple[str, Zadanie]]:
    """Buduje listę adresów do pobrania wraz z identyfikatorami ich źródeł."""
    zadania: list[tuple[str, Zadanie]] = []
    widziane: set[str] = set()
    for pozycja in pozycje:
        if pozycja.wejscie.typ_wejscia is not TypWejscia.URL:
            continue
        if pozycja.format_zrodla == FORMAT_YOUTUBE:
            continue
        kanoniczny = pozycja.adres_kanoniczny or pozycja.wejscie.wartosc
        identyfikator = identyfikator_adresu(
            typ_zrodla_dla_formatu(pozycja.format_zrodla), kanoniczny
        )
        if identyfikator in widziane:
            continue
        stan = checkpoint.zrodla.get(identyfikator)
        if stan is not None and stan.status in _STATUSY_KONCOWE:
            continue
        widziane.add(identyfikator)
        zadania.append(
            (
                identyfikator,
                Zadanie(adres_pobierania=pozycja.wejscie.wartosc, klucz_kanoniczny=kanoniczny),
            )
        )
    return zadania


async def _pobierz_asynchronicznie(
    zadania: Sequence[Zadanie],
    konfiguracja: Konfiguracja,
    log: logging.Logger,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[WynikFazyPobrania]:
    """Uruchamia pobieranie wszystkich adresów z zachowaniem limitów na domenę."""
    pamiec = _otworz_pamiec_podreczna(konfiguracja, log)
    try:
        async with Pobieracz(
            UstawieniaPobierania.z_konfiguracji(konfiguracja),
            pamiec=pamiec,
            transport=transport,
            log=log,
        ) as pobieracz:
            return list(await pobieracz.pobierz_wiele(zadania))
    finally:
        if pamiec is not None:
            pamiec.zamknij()


def _otworz_pamiec_podreczna(
    konfiguracja: Konfiguracja, log: logging.Logger
) -> PamiecPodreczna | None:
    """Otwiera wspólną pamięć podręczną i usuwa z niej przeterminowane wpisy.

    Niedostępna albo uszkodzona pamięć podręczna nie zatrzymuje pracy. Zostaje
    wtedy wyłączona na to uruchomienie, a powód trafia do logu szczegółowego,
    ponieważ pamięć podręczna jest wygodą, a nie warunkiem przetwarzania.
    """
    if not konfiguracja.uzywaj_cache:
        return None
    try:
        pamiec = otworz(konfiguracja.sciezka_cache)
        usuniete = pamiec.usun_przeterminowane(konfiguracja.maksymalny_wiek_cache_dni, teraz_utc())
    except BladGnb as blad:
        log.warning("Pamięć podręczna wyłączona na to uruchomienie: %s", blad.komunikat)
        return None
    if usuniete:
        log.info("Usunięto %d przeterminowanych wpisów pamięci podręcznej.", usuniete)
    return pamiec


def _zdekoduj_odpowiedz(odpowiedz: OdpowiedzPobrania) -> tuple[str, str]:
    """Zamienia bajty odpowiedzi na tekst, korzystając z kodowania podanego przez serwer.

    Kodowanie zadeklarowane przez serwer ma pierwszeństwo, bo jest informacją
    wprost od źródła. Gdy go nie ma albo gdy zawiedzie, kodowanie jest wykrywane
    tak samo jak dla plików lokalnych.
    """
    if odpowiedz.deklarowane_kodowanie:
        try:
            return (
                odpowiedz.tresc.decode(odpowiedz.deklarowane_kodowanie),
                odpowiedz.deklarowane_kodowanie,
            )
        except (LookupError, UnicodeDecodeError):
            pass
    return zdekoduj(odpowiedz.tresc)


def _wygeneruj_nazwe_projektu(pozycje: Sequence[PozycjaWejsciowa]) -> str:
    """Buduje nazwę projektu z pierwszego wejścia, gdy użytkownik jej nie podał.

    Nazwa podana opcją `--projekt` ma zawsze pierwszeństwo i ta funkcja w ogóle
    wtedy nie jest wywoływana.
    """
    if not pozycje:
        return wygeneruj_nazwe_projektu("")
    pierwsza = pozycje[0]
    if pierwsza.wejscie.typ_wejscia is TypWejscia.PLIK:
        return wygeneruj_nazwe_projektu(Path(pierwsza.wejscie.wartosc).stem)
    if pierwsza.wejscie.typ_wejscia is TypWejscia.URL:
        return wygeneruj_nazwe_projektu(_podstawa_nazwy_z_adresu(pierwsza))
    return wygeneruj_nazwe_projektu(pierwsza.wejscie.wartosc[:_MAKSYMALNA_PODSTAWA_NAZWY])


def _podstawa_nazwy_z_adresu(pozycja: PozycjaWejsciowa) -> str:
    """Buduje krótką podstawę nazwy projektu z adresu źródła.

    Cały adres w nazwie katalogu jest nieczytelny przy odsłuchu: czytnik ekranu
    odczytuje go w całości, razem z każdym podkreśleniem, przy każdym przejściu
    przez katalog Dokumenty. Dlatego film daje nazwę złożoną z członu „youtube”
    i identyfikatora filmu, a strona nazwę hosta bez przedrostka „www” wraz
    z początkiem sumy kontrolnej źródła, który rozróżnia dwa artykuły z tego
    samego serwisu.

    Właściwa nazwa, budowana z tytułu źródła, wymagałaby znajomości tytułu przed
    utworzeniem katalogu. Powody, dla których na razie tego nie robimy, opisuje
    sekcja osiemnasta e CLAUDE.md.
    """
    kanoniczny = pozycja.adres_kanoniczny or pozycja.wejscie.wartosc

    if pozycja.format_zrodla == FORMAT_YOUTUBE:
        rozpoznanie = rozpoznaj(pozycja.wejscie.wartosc)
        if rozpoznanie.identyfikator_filmu is not None:
            return f"youtube {rozpoznanie.identyfikator_filmu}"

    host = (urlsplit(kanoniczny).hostname or "").removeprefix("www.")
    identyfikator = identyfikator_adresu(typ_zrodla_dla_formatu(pozycja.format_zrodla), kanoniczny)
    return f"{host} {skrot_z_identyfikatora(identyfikator)}"


def _nowy_checkpoint(
    uklad: UkladProjektu, konfiguracja: Konfiguracja, moment: datetime
) -> Checkpoint:
    return Checkpoint(
        wersja_schematu=WERSJA_SCHEMATU_CHECKPOINTU,
        identyfikator_projektu=uklad.identyfikator_projektu,
        nazwa_projektu=uklad.nazwa_projektu,
        katalog_projektu=str(uklad.katalog_projektu),
        konfiguracja={
            "katalog_wynikow": str(konfiguracja.katalog_wynikow),
            "limit_zrodel": str(konfiguracja.limit_zrodel),
            "bezpieczny_limit_slow": str(konfiguracja.bezpieczny_limit_slow),
            "bezpieczny_limit_mb": str(konfiguracja.bezpieczny_limit_mb),
            "formaty_wynikowe": ",".join(konfiguracja.formaty_wynikowe),
            "zachowuj_oryginaly": "tak" if konfiguracja.zachowuj_oryginaly else "nie",
            "zachowuj_odnosniki": "tak" if konfiguracja.zachowuj_odnosniki else "nie",
        },
        czas_ostatniej_zmiany=moment.isoformat(),
    )


def _zapamietaj_wejscia(checkpoint: Checkpoint, pozycje: Sequence[PozycjaWejsciowa]) -> None:
    """Dopisuje wejścia bieżącego uruchomienia do listy wejść w checkpoincie.

    Wejścia są rozróżniane po parze rodzaju i wartości, więc ponowne podanie tego
    samego źródła w kolejnym uruchomieniu nie mnoży wpisów. Lista wejść pozwala
    wznowić projekt bez ponownego podawania źródeł, czego wymaga sekcja
    czternasta punkt trzeci CLAUDE.md, a z czego korzysta wznowienie z interfejsu
    WWW.
    """
    widziane = {(wejscie.typ_wejscia, wejscie.wartosc) for wejscie in checkpoint.wejscia}
    for pozycja in pozycje:
        klucz = (pozycja.wejscie.typ_wejscia.value, pozycja.wejscie.wartosc)
        if klucz in widziane:
            continue
        widziane.add(klucz)
        checkpoint.wejscia.append(
            WejscieZapis(
                typ_wejscia=pozycja.wejscie.typ_wejscia.value,
                wartosc=pozycja.wejscie.wartosc,
                format_zrodla=pozycja.format_zrodla,
                moment_dodania=pozycja.wejscie.moment_dodania.isoformat(),
                grupa=pozycja.grupa,
            )
        )


def odtworz_wejscia(checkpoint: Checkpoint, konfiguracja: Konfiguracja) -> list[PozycjaWejsciowa]:
    """Odbudowuje pozycje wejściowe z listy wejść zapisanej w checkpoincie.

    Używane przy wznowieniu projektu z interfejsu WWW: użytkownik nie podaje
    źródeł ponownie, bo potok odtwarza je z checkpointu. Każde wejście wraca
    przez tę samą funkcję przyjmującą, której użyto pierwotnie, więc identyfikator
    źródła jest ten sam i etapy już ukończone nie są powtarzane. Moment dodania
    jest ustawiany na chwilę wznowienia, ponieważ nie wpływa on na identyfikator
    ani wejścia, ani źródła.
    """
    moment = datetime.now(UTC)
    pozycje: list[PozycjaWejsciowa] = []
    for wejscie in checkpoint.wejscia:
        if wejscie.typ_wejscia == TypWejscia.URL.value:
            pozycje.append(
                przyjmij_url(
                    wejscie.wartosc,
                    moment,
                    konfiguracja.dodatkowe_parametry_sledzace,
                    grupa=wejscie.grupa,
                )
            )
        elif wejscie.typ_wejscia == TypWejscia.PLIK.value:
            pozycje.append(przyjmij_plik(Path(wejscie.wartosc), moment, grupa=wejscie.grupa))
        elif wejscie.typ_wejscia == TypWejscia.TEKST.value:
            pozycje.append(
                przyjmij_tekst(
                    wejscie.wartosc,
                    moment,
                    format_tekstu=wejscie.format_zrodla or "txt",
                    grupa=wejscie.grupa,
                )
            )
    return pozycje


def _zbuduj_manifest(uklad: UkladProjektu, checkpoint: Checkpoint) -> Manifest:
    wpisy_zrodel: list[WpisZrodla] = []
    for stan in checkpoint.zrodla.values():
        wpisy_zrodel.append(
            WpisZrodla(
                identyfikator=stan.identyfikator,
                typ=stan.typ,
                pochodzenie=stan.pochodzenie,
                checksum=stan.checksum,
                status=stan.status,
                duplikat=(
                    f"duplikat źródła {stan.duplikat_glowny}"
                    if stan.status == StatusZrodla.DUPLIKAT.value and stan.duplikat_glowny
                    else None
                ),
                decyzja_md=stan.decyzja_md,
                uzasadnienie_md=tuple(stan.uzasadnienie_md),
                pliki_wynikowe=tuple(wynik.sciezka_wzgledna for wynik in stan.wyniki),
                komunikat_bledu=stan.komunikat_bledu,
                pobranie=_wpis_pobrania(stan.pobranie),
                metadane=dict(stan.metadane),
                ocena_jakosci=stan.ocena_jakosci,
                powody_oceny=tuple(stan.powody_oceny),
                ostrzezenia=tuple(stan.ostrzezenia),
                grupa_pakowania=stan.grupa_pakowania,
                ostrzezenia_pakowania=tuple(stan.ostrzezenia_pakowania),
            )
        )
    return Manifest(
        wersja_schematu=WERSJA_SCHEMATU_MANIFESTU,
        identyfikator_projektu=uklad.identyfikator_projektu,
        nazwa_projektu=uklad.nazwa_projektu,
        zrodla=tuple(wpisy_zrodel),
        wyniki=_wpisy_wynikow(checkpoint),
        deduplikacja=tuple(
            WpisDeduplikacji(
                identyfikator_zrodla_glownego=decyzja.identyfikator_zrodla_glownego,
                identyfikator_duplikatu=decyzja.identyfikator_duplikatu,
                metoda=decyzja.metoda,
                wynik_podobienstwa=decyzja.wynik_podobienstwa,
                decyzja=decyzja.decyzja,
                uzasadnienie=decyzja.uzasadnienie,
                zachowane_fragmenty_unikalne=tuple(decyzja.zachowane_fragmenty_unikalne),
            )
            for decyzja in checkpoint.deduplikacja.decyzje
        ),
    )


def _wpisy_wynikow(checkpoint: Checkpoint) -> tuple[WpisWyniku, ...]:
    """Buduje wpisy plików wynikowych, licząc każdy plik raz, nawet plik grupy.

    Ten sam plik grupy jest zapisany w stanie każdego ze swoich źródeł, więc bez
    złączenia po ścieżce trafiłby do manifestu wielokrotnie. Liczba źródeł w pliku
    pochodzi z listy identyfikatorów zapisanej przy wyniku, a dla wpisów sprzed
    etapu szóstego, w których tej listy nie ma, przyjmowane jest źródło macierzyste.
    """
    po_sciezce: dict[str, WpisWyniku] = {}
    for stan in checkpoint.zrodla.values():
        for wynik in stan.wyniki:
            if wynik.sciezka_wzgledna in po_sciezce:
                continue
            identyfikatory = tuple(wynik.identyfikatory_zrodel) or (stan.identyfikator,)
            po_sciezce[wynik.sciezka_wzgledna] = WpisWyniku(
                sciezka=wynik.sciezka_wzgledna,
                format=wynik.format,
                liczba_zrodel=len(identyfikatory),
                liczba_slow=wynik.liczba_slow,
                liczba_znakow_pliku=wynik.liczba_znakow_pliku,
                rozmiar_bajtow=wynik.rozmiar_bajtow,
                checksum=wynik.checksum,
                status=StatusZrodla.SPAKOWANE.value,
                identyfikatory_zrodel=identyfikatory,
                numer_czesci=wynik.numer_czesci,
                liczba_czesci=wynik.liczba_czesci,
            )
    return tuple(po_sciezce.values())


def _wpis_pobrania(pobranie: StanPobrania | None) -> WpisPobrania | None:
    """Przenosi dane pobrania z checkpointu do manifestu."""
    if pobranie is None:
        return None
    return WpisPobrania(
        adres_koncowy=pobranie.adres_koncowy,
        kod_odpowiedzi=pobranie.kod_odpowiedzi,
        deklarowane_kodowanie=pobranie.deklarowane_kodowanie,
        etag=pobranie.etag,
        last_modified=pobranie.last_modified,
        z_pamieci_podrecznej=pobranie.z_pamieci_podrecznej,
    )


def _zbuduj_podsumowanie(
    *,
    checkpoint: Checkpoint,
    limit_zrodel: int,
    czas_pracy_sekundy: float,
) -> PodsumowanieProjektu:
    poprawne = _policz_status(checkpoint, StatusZrodla.SPAKOWANE)
    pominiete = _policz_status(checkpoint, StatusZrodla.POMINIETE)
    bledne = _policz_status(checkpoint, StatusZrodla.BLAD)
    duplikaty = _policz_status(checkpoint, StatusZrodla.DUPLIKAT)

    # Plik grupy jest zapisany w stanie każdego ze swoich źródeł, więc liczenie
    # po ścieżce liczy go raz. Bez tego plik grupy pięciu źródeł liczyłby się
    # pięciokrotnie i zawyżałby wykorzystanie limitu.
    wyniki = list(
        {
            wynik.sciezka_wzgledna: wynik
            for stan in checkpoint.zrodla.values()
            for wynik in stan.wyniki
        }.values()
    )
    liczba_txt = sum(1 for wynik in wyniki if wynik.format == "txt")
    liczba_md = sum(1 for wynik in wyniki if wynik.format == "md")
    liczba_pdf = sum(1 for wynik in wyniki if wynik.format == "pdf")
    laczna_liczba_slow = sum(
        wynik.liczba_slow for wynik in wyniki if wynik.format in ("txt", "pdf")
    )
    najwiekszy = max(wyniki, key=lambda wynik: wynik.rozmiar_bajtow, default=None)

    return PodsumowanieProjektu(
        liczba_wejsc=len(checkpoint.zrodla),
        liczba_zrodel_poprawnych=poprawne,
        liczba_zrodel_pominietych=pominiete,
        liczba_zrodel_blednych=bledne,
        liczba_duplikatow=duplikaty,
        liczba_zrodel_po_deduplikacji=poprawne,
        liczba_plikow_txt=liczba_txt,
        liczba_plikow_md=liczba_md,
        liczba_plikow_pdf=liczba_pdf,
        limit_zrodel=limit_zrodel,
        najwiekszy_plik_nazwa=(najwiekszy.sciezka_wzgledna if najwiekszy is not None else None),
        najwiekszy_plik_bajtow=najwiekszy.rozmiar_bajtow if najwiekszy is not None else 0,
        laczna_liczba_slow=laczna_liczba_slow,
        czas_pracy_sekundy=czas_pracy_sekundy,
        zrodla_nieprzetworzone=_zrodla_nieprzetworzone(checkpoint),
        materialy_do_sprawdzenia=_materialy_do_sprawdzenia(checkpoint),
    )


def _zrodla_nieprzetworzone(checkpoint: Checkpoint) -> tuple[ZrodloNieprzetworzone, ...]:
    """Zbiera źródła pominięte i błędne wraz z powodem, do wykazu w raporcie."""
    statusy_nieprzetworzone = (StatusZrodla.POMINIETE.value, StatusZrodla.BLAD.value)
    return tuple(
        ZrodloNieprzetworzone(
            identyfikator=stan.identyfikator,
            pochodzenie=stan.pochodzenie,
            status=stan.status,
            powod=stan.komunikat_bledu or "Powód nie został zapisany.",
        )
        for stan in checkpoint.zrodla.values()
        if stan.status in statusy_nieprzetworzone
    )


def _materialy_do_sprawdzenia(checkpoint: Checkpoint) -> tuple[MaterialDoSprawdzenia, ...]:
    """Zbiera źródła zapisane poprawnie, przy których coś wymaga obejrzenia.

    Kwalifikuje źródło podejrzane w ocenie jakości, źródło z ostrzeżeniem
    ekstraktora, źródło z ostrzeżeniem podziału oraz źródło, które deduplikacja
    uznała za możliwy duplikat i zostawiła obie kopie do rozstrzygnięcia. Każdy
    z powodów musi tu trafiać niezależnie od pozostałych, bo mówią o różnych
    rzeczach.
    """
    mozliwe_duplikaty = _mozliwe_duplikaty_wedlug_zrodla(checkpoint)
    return tuple(
        MaterialDoSprawdzenia(
            identyfikator=stan.identyfikator,
            pochodzenie=stan.pochodzenie,
            powody=tuple(stan.powody_oceny),
            ostrzezenia=tuple(stan.ostrzezenia),
            mozliwe_duplikaty=mozliwe_duplikaty.get(stan.identyfikator, ()),
            ostrzezenia_pakowania=tuple(stan.ostrzezenia_pakowania),
        )
        for stan in checkpoint.zrodla.values()
        if stan.ocena_jakosci == OCENA_PODEJRZANA
        or stan.ostrzezenia
        or stan.ostrzezenia_pakowania
        or stan.identyfikator in mozliwe_duplikaty
    )


def _mozliwe_duplikaty_wedlug_zrodla(checkpoint: Checkpoint) -> dict[str, tuple[str, ...]]:
    """Buduje opisy możliwych duplikatów dla każdego źródła oznaczonego do przeglądu.

    Decyzja o możliwym duplikacie dotyczy pary źródeł. Opis jest przypisywany
    źródłu wskazanemu w decyzji jako duplikat, ponieważ to ono zostało zachowane
    obok źródła głównego i to przy nim użytkownik ma podjąć decyzję.
    """
    wynik: dict[str, list[str]] = {}
    for decyzja in checkpoint.deduplikacja.decyzje:
        if decyzja.decyzja != WynikDeduplikacji.WYMAGA_DECYZJI_UZYTKOWNIKA.value:
            continue
        opis = (
            f"Możliwy duplikat źródła {decyzja.identyfikator_zrodla_glownego}: "
            f"podobieństwo {decyzja.wynik_podobienstwa:.2f}, metoda {decyzja.metoda}."
        )
        wynik.setdefault(decyzja.identyfikator_duplikatu, []).append(opis)
    return {identyfikator: tuple(opisy) for identyfikator, opisy in wynik.items()}


def _numery_czesci(plan: PlanPliku) -> tuple[int | None, int | None]:
    """Zwraca numer i liczbę części do zapisu, albo parę pustą dla pliku jedynego.

    Plik jedyny dla swojej podstawy nazwy nie dostaje oznaczenia części, więc jego
    wpis w checkpoincie i manifeście ma tu wartości puste, a nie „1 z 1”.
    """
    if not plan.czy_wieloczesciowy:
        return None, None
    return plan.numer_czesci, plan.liczba_czesci


def _policz_status(checkpoint: Checkpoint, status: StatusZrodla) -> int:
    return sum(1 for stan in checkpoint.zrodla.values() if stan.status == status.value)
