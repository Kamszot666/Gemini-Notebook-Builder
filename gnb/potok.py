"""Orkiestracja potoku przetwarzania w zakresie etapów pierwszego i drugiego.

Potok uruchamia etapy w stałej kolejności z sekcji ósmej CLAUDE.md, w części
obsługiwanej przez etapy pierwszy i drugi: wejście, walidacja i utworzenie
źródła, pobranie lub import treści, ekstrakcja, normalizacja, klasyfikacja TXT
kontra MD, zapis wyników, manifest, checkpoint, raport. Etapy deduplikacji,
kondensacji i grupowania są pominięte, ale ich miejsce w kolejności jest
zachowane.

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

import httpx

from gnb.core.identyfikatory import suma_kontrolna_bajtow
from gnb.core.konfiguracja import Konfiguracja
from gnb.core.model import DokumentWyekstrahowany, Zrodlo
from gnb.core.nazwy import nazwa_pliku_wynikowego, wygeneruj_nazwe_projektu
from gnb.core.stale import StatusZrodla, TypWejscia, TypZrodla
from gnb.core.wyjatki import BladGnb, BladTrwaly, PrzekroczonoLimit
from gnb.core.youtube import rozpoznaj
from gnb.extractors.bazowy import Ekstraktor, RejestrEkstraktorow, domyslny_rejestr
from gnb.extractors.strona_www import KOMUNIKAT_WYMAGA_SKRYPTOW, czy_wymaga_skryptow
from gnb.extractors.youtube import KOMUNIKAT_NAPISY_BEZ_TRESCI
from gnb.extractors.youtube import zbuduj_dokument as zbuduj_dokument_z_napisow
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
    identyfikator_adresu,
    identyfikator_awaryjny,
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
    ZDARZENIE_MANIFEST_ZAPISANY,
    ZDARZENIE_NAPISY_INNY_JEZYK,
    ZDARZENIE_NAPISY_WYBRANE,
    ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY,
    ZDARZENIE_PROJEKT_UTWORZONY,
    ZDARZENIE_PROJEKT_WZNOWIONY,
    ZDARZENIE_PROJEKT_ZAKONCZONY,
    ZDARZENIE_ZRODLO_BLAD,
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
    WpisPobrania,
    WpisWyniku,
    WpisZrodla,
    zapisz_manifest,
)
from gnb.output.raport import (
    PodsumowanieProjektu,
    ZrodloNieprzetworzone,
    zapisz_raport,
    zbuduj_raport,
)
from gnb.output.tekst_bez_znacznikow import zamien_markdown_na_tekst
from gnb.output.zapis import zapisz_wyniki
from gnb.persistence.cache import PamiecPodreczna, WpisCache, otworz, teraz_utc
from gnb.persistence.checkpoint import WERSJA_SCHEMATU as WERSJA_SCHEMATU_CHECKPOINTU
from gnb.persistence.checkpoint import (
    Checkpoint,
    StanPobrania,
    StanWyniku,
    StanZrodla,
    wczytaj,
    zapisz,
)
from gnb.persistence.projekt import UkladProjektu, ustal_uklad, utworz_katalogi

_STATUSY_KONCOWE = frozenset(
    {StatusZrodla.SPAKOWANE.value, StatusZrodla.POMINIETE.value, StatusZrodla.BLAD.value}
)
_ROZSZERZENIE_ORYGINALU_TEKSTU = "txt"
_ROZSZERZENIE_ORYGINALU_NAPISOW = "json"

# Wynik fazy pobrania dla jednego adresu: treść, świadome pominięcie albo błąd.
WynikFazyPobrania = OdpowiedzPobrania | PominietePobranie | BladGnb

# Wynik fazy pobrania dla jednego filmu: napisy, świadome pominięcie albo błąd.
WynikFazyFilmu = WynikYouTube | PominietyFilm | BladGnb

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


def przetworz_projekt(
    pozycje: Sequence[PozycjaWejsciowa],
    konfiguracja: Konfiguracja,
    *,
    nazwa_projektu: str | None = None,
    wlasny_katalog_projektu: Path | None = None,
    zegar: Callable[[], datetime] = _teraz_utc,
    zegar_lokalny: Callable[[], datetime] = teraz_lokalny,
    rejestr: RejestrEkstraktorow | None = None,
    transport_http: httpx.AsyncBaseTransport | None = None,
    pobieracz_youtube: PobieraczYouTube | None = None,
) -> WynikPrzetwarzania:
    """Przetwarza listę wejść w ramach jednego projektu i zwraca podsumowanie.

    Argument `zegar` podaje czas UTC używany w checkpoincie, manifeście i logu
    szczegółowym. Argument `zegar_lokalny` podaje czas lokalny systemu, którym
    prowadzony jest przeznaczony dla użytkownika plik ``log_wazne.txt``. Oba
    zegary można podmienić w testach.

    Argumenty `transport_http` oraz `pobieracz_youtube` służą wyłącznie testom.
    Pozwalają podstawić sztuczny transport oraz przygotowane napisy i sprawdzić
    cały potok bez korzystania z sieci.
    """
    rejestr = rejestr or domyslny_rejestr(konfiguracja.zachowuj_odnosniki)
    czas_startu = zegar()

    nazwa = nazwa_projektu or _wygeneruj_nazwe_projektu(pozycje)
    uklad = ustal_uklad(
        konfiguracja.katalog_wynikow, nazwa, wlasny_katalog_projektu=wlasny_katalog_projektu
    )
    utworz_katalogi(uklad, z_materialami_zrodlowymi=konfiguracja.zachowuj_oryginaly)

    istniejacy_checkpoint = wczytaj(uklad.checkpoint)
    wznowiono = istniejacy_checkpoint is not None
    checkpoint = istniejacy_checkpoint or _nowy_checkpoint(uklad, konfiguracja, zegar())

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

        pobrane = _pobierz_strony(pozycje, konfiguracja, checkpoint, log, transport_http)
        filmy = _pobierz_filmy(
            pozycje, konfiguracja, checkpoint, log, transport_http, pobieracz_youtube
        )
        wykonanie = _Wykonanie(
            uklad, konfiguracja, checkpoint, dziennik_wazny, log, rejestr, zegar, pobrane, filmy
        )
        for pozycja in pozycje:
            wykonanie.przetworz(pozycja)

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
        zegar: Callable[[], datetime],
        pobrane: dict[str, WynikFazyPobrania] | None = None,
        filmy: dict[str, WynikFazyFilmu] | None = None,
    ) -> None:
        self._uklad = uklad
        self._konfiguracja = konfiguracja
        self._checkpoint = checkpoint
        self._dziennik_wazny = dziennik_wazny
        self._log = log
        self._rejestr = rejestr
        self._zegar = zegar
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

        if istniejacy is None and self._liczba_aktywnych() >= self._konfiguracja.limit_zrodel:
            self._pomin(
                zrodlo, pozycja, "Przekroczono limit liczby źródeł w notatniku. Źródło pominięte."
            )
            return

        try:
            self._przetworz_zrodlo(pozycja, zrodlo)
        except PrzekroczonoLimit as blad:
            # Przekroczenie limitu nie jest awarią, tylko przypadkiem jeszcze
            # nieobsłużonym: podział zbyt dużego źródła to zadanie etapu
            # szóstego. Taki sam status dostaje przekroczenie limitu liczby
            # źródeł, więc obie sytuacje są opisane w ten sam sposób.
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
        self._zapisz_dokument(pozycja, zrodlo, przygotowane)

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

    def _przygotuj_tresc(
        self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo
    ) -> _PrzygotowanyDokument | None:
        """Buduje dokument ze źródła tekstowego, plikowego albo strony internetowej."""
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

        return _PrzygotowanyDokument(
            dokument=dokument,
            suma_kontrolna=suma_kontrolna,
            tekst_txt=self._tekst_dla_wersji_txt(ekstraktor, dokument.tekst),
            stan_pobrania=stan_pobrania,
            metadane={},
        )

    def _zapisz_dokument(
        self,
        pozycja: PozycjaWejsciowa,
        zrodlo: Zrodlo,
        przygotowane: _PrzygotowanyDokument,
    ) -> None:
        """Normalizuje dokument, zapisuje pliki wynikowe i odnotowuje stan źródła."""
        identyfikator = zrodlo.identyfikator_zrodla
        dokument = przygotowane.dokument
        stan_pobrania = przygotowane.stan_pobrania
        suma_kontrolna = przygotowane.suma_kontrolna

        znormalizowany = zbuduj_dokument_znormalizowany(identyfikator, dokument.tekst)

        if znormalizowany.liczba_slow > self._konfiguracja.bezpieczny_limit_slow:
            raise PrzekroczonoLimit(
                f"Źródło ma {znormalizowany.liczba_slow} słów, ponad bezpieczny limit "
                f"{self._konfiguracja.bezpieczny_limit_slow}. Podział źródła to zadanie "
                "etapu szóstego.",
                identyfikator,
            )

        decyzja = regula_md.ocen(dokument)
        nazwa_bazowa = nazwa_pliku_wynikowego(dokument.tytul, identyfikator)
        pliki = zapisz_wyniki(
            self._uklad.pliki_wynikowe,
            nazwa_bazowa,
            identyfikator,
            znormalizowany,
            decyzja,
            formaty_wlaczone=self._konfiguracja.formaty_wynikowe,
            tekst_txt=przygotowane.tekst_txt,
        )

        wyniki_stanu = [
            StanWyniku(
                sciezka_wzgledna=plik.sciezka.relative_to(self._uklad.katalog_projektu).as_posix(),
                format=plik.format.value,
                liczba_slow=plik.liczba_slow,
                liczba_znakow=plik.liczba_znakow,
                rozmiar_bajtow=plik.rozmiar_bajtow,
                checksum=plik.checksum,
            )
            for plik in pliki
        ]
        self._checkpoint.zrodla[identyfikator] = StanZrodla(
            identyfikator=identyfikator,
            typ=zrodlo.typ_zrodla.value,
            pochodzenie=zrodlo.pochodzenie,
            checksum=suma_kontrolna,
            format_zrodla=pozycja.format_zrodla,
            status=StatusZrodla.SPAKOWANE.value,
            nazwa_bazowa_wyniku=nazwa_bazowa,
            wyniki=wyniki_stanu,
            liczba_slow=znormalizowany.liczba_slow,
            liczba_znakow=znormalizowany.liczba_znakow,
            decyzja_md=decyzja.generuj_md,
            uzasadnienie_md=list(decyzja.spelnione_warunki),
            pobranie=stan_pobrania,
            metadane=dict(przygotowane.metadane),
        )
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_PRZYJETE)
        for _ in pliki:
            self._dziennik_wazny.zapisz(ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY)
        self._loguj(
            logging.INFO,
            identyfikator,
            f"Zapisano {len(pliki)} plików wynikowych, wersja MD: "
            f"{'tak' if decyzja.generuj_md else 'nie'}.",
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

    def _tekst_dla_wersji_txt(self, ekstraktor: Ekstraktor, tekst: str) -> str | None:
        """Zwraca treść wersji TXT, gdy ma się różnić od treści wersji MD.

        Dla ekstraktora zwracającego tekst ze znacznikami wersja TXT powstaje
        przez przepisanie dokumentu bez znaczników, a jej treść jest ponownie
        normalizowana, żeby oba pliki wynikowe przechodziły te same reguły.
        Dla tekstu już czystego zwracana jest wartość pusta, co oznacza „użyj
        tekstu znormalizowanego bez zmian”.
        """
        if not ekstraktor.tekst_zawiera_znaczniki:
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

    def _loguj(self, poziom: int, identyfikator: str, komunikat: str) -> None:
        self._log.log(poziom, komunikat, extra={"identyfikator_zrodla": identyfikator})


def _pobierz_strony(
    pozycje: Sequence[PozycjaWejsciowa],
    konfiguracja: Konfiguracja,
    checkpoint: Checkpoint,
    log: logging.Logger,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, WynikFazyPobrania]:
    """Pobiera wszystkie adresy z listy wejść i zwraca wyniki po identyfikatorze źródła.

    Adresy, które w checkpoincie mają już status końcowy, nie są pobierane
    ponownie. Powtórzony adres jest pobierany raz, bo jego identyfikator wynika
    z kanonicznej postaci adresu.
    """
    zadania = _zadania_do_pobrania(pozycje, checkpoint)
    if not zadania:
        return {}

    log.info("Faza pobrania: %d adresów do pobrania.", len(zadania))
    wyniki = asyncio.run(
        _pobierz_asynchronicznie([zadanie for _, zadanie in zadania], konfiguracja, log, transport)
    )
    return {identyfikator: wynik for (identyfikator, _), wynik in zip(zadania, wyniki, strict=True)}


def _pobierz_filmy(
    pozycje: Sequence[PozycjaWejsciowa],
    konfiguracja: Konfiguracja,
    checkpoint: Checkpoint,
    log: logging.Logger,
    transport: httpx.AsyncBaseTransport | None = None,
    pobieracz_youtube: PobieraczYouTube | None = None,
) -> dict[str, WynikFazyFilmu]:
    """Pobiera napisy wszystkich filmów z listy wejść i zwraca wyniki po identyfikatorze.

    Playlisty, kanały i adresy YouTube bez identyfikatora filmu są odrzucane bez
    sięgania do sieci, ze statusem pominięcia i powodem gotowym do pokazania
    użytkownikowi. Filmy przetworzone w poprzednim uruchomieniu nie są pobierane
    ponownie.
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
        wyniki.update(
            asyncio.run(
                _pobierz_filmy_asynchronicznie(
                    do_pobrania, konfiguracja, log, transport, pobieracz_youtube
                )
            )
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
    if not pozycje:
        return wygeneruj_nazwe_projektu("")
    pierwsza = pozycje[0]
    if pierwsza.wejscie.typ_wejscia is TypWejscia.PLIK:
        return wygeneruj_nazwe_projektu(Path(pierwsza.wejscie.wartosc).stem)
    return wygeneruj_nazwe_projektu(pierwsza.wejscie.wartosc[:_MAKSYMALNA_PODSTAWA_NAZWY])


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


def _zbuduj_manifest(uklad: UkladProjektu, checkpoint: Checkpoint) -> Manifest:
    wpisy_zrodel: list[WpisZrodla] = []
    wpisy_wynikow: list[WpisWyniku] = []
    for stan in checkpoint.zrodla.values():
        wpisy_zrodel.append(
            WpisZrodla(
                identyfikator=stan.identyfikator,
                typ=stan.typ,
                pochodzenie=stan.pochodzenie,
                checksum=stan.checksum,
                status=stan.status,
                duplikat=None,
                decyzja_md=stan.decyzja_md,
                uzasadnienie_md=tuple(stan.uzasadnienie_md),
                pliki_wynikowe=tuple(wynik.sciezka_wzgledna for wynik in stan.wyniki),
                komunikat_bledu=stan.komunikat_bledu,
                pobranie=_wpis_pobrania(stan.pobranie),
                metadane=dict(stan.metadane),
            )
        )
        for wynik in stan.wyniki:
            wpisy_wynikow.append(
                WpisWyniku(
                    sciezka=wynik.sciezka_wzgledna,
                    format=wynik.format,
                    liczba_zrodel=1,
                    liczba_slow=wynik.liczba_slow,
                    liczba_znakow=wynik.liczba_znakow,
                    rozmiar_bajtow=wynik.rozmiar_bajtow,
                    checksum=wynik.checksum,
                    status=StatusZrodla.SPAKOWANE.value,
                )
            )
    return Manifest(
        wersja_schematu=WERSJA_SCHEMATU_MANIFESTU,
        identyfikator_projektu=uklad.identyfikator_projektu,
        nazwa_projektu=uklad.nazwa_projektu,
        zrodla=tuple(wpisy_zrodel),
        wyniki=tuple(wpisy_wynikow),
    )


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

    wyniki = [wynik for stan in checkpoint.zrodla.values() for wynik in stan.wyniki]
    liczba_txt = sum(1 for wynik in wyniki if wynik.format == "txt")
    liczba_md = sum(1 for wynik in wyniki if wynik.format == "md")
    laczna_liczba_slow = sum(wynik.liczba_slow for wynik in wyniki if wynik.format == "txt")
    najwiekszy = max(wyniki, key=lambda wynik: wynik.rozmiar_bajtow, default=None)

    return PodsumowanieProjektu(
        liczba_wejsc=len(checkpoint.zrodla),
        liczba_zrodel_poprawnych=poprawne,
        liczba_zrodel_pominietych=pominiete,
        liczba_zrodel_blednych=bledne,
        liczba_duplikatow=0,
        liczba_zrodel_po_deduplikacji=poprawne,
        liczba_plikow_txt=liczba_txt,
        liczba_plikow_md=liczba_md,
        liczba_plikow_pdf=0,
        limit_zrodel=limit_zrodel,
        najwiekszy_plik_nazwa=(najwiekszy.sciezka_wzgledna if najwiekszy is not None else None),
        najwiekszy_plik_bajtow=najwiekszy.rozmiar_bajtow if najwiekszy is not None else 0,
        laczna_liczba_slow=laczna_liczba_slow,
        czas_pracy_sekundy=czas_pracy_sekundy,
        zrodla_nieprzetworzone=_zrodla_nieprzetworzone(checkpoint),
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


def _policz_status(checkpoint: Checkpoint, status: StatusZrodla) -> int:
    return sum(1 for stan in checkpoint.zrodla.values() if stan.status == status.value)
