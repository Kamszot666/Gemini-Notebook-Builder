"""Orkiestracja potoku przetwarzania w zakresie etapu pierwszego.

Potok uruchamia etapy w stałej kolejności z sekcji ósmej CLAUDE.md, w części
obsługiwanej przez etap pierwszy: wejście, walidacja i utworzenie źródła, import
treści, ekstrakcja, normalizacja, klasyfikacja TXT kontra MD, zapis wyników,
manifest, checkpoint, raport. Etapy deduplikacji, kondensacji i grupowania są
pominięte, ale ich miejsce w kolejności jest zachowane.

Jedno uszkodzone wejście nie zatrzymuje reszty. Kończy się kontrolowanym błędem
zapisanym w logu szczegółowym, w manifeście i w raporcie końcowym. Potok jest
odporny na wznowienie: źródła zapisane w checkpoincie ze statusem końcowym nie
są przetwarzane ponownie, a manifest oraz raport są odbudowywane z pełnego stanu
checkpointu.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.model import Zrodlo
from gnb.core.nazwy import bezpieczna_nazwa_pliku, wygeneruj_nazwe_projektu
from gnb.core.stale import StatusZrodla, TypWejscia
from gnb.core.wyjatki import BladGnb, PrzekroczonoLimit
from gnb.extractors.bazowy import RejestrEkstraktorow, domyslny_rejestr
from gnb.ingestion.wejscie import (
    PozycjaWejsciowa,
    identyfikator_awaryjny,
    waliduj_i_utworz_zrodlo,
    wczytaj_tresc_zrodla,
)
from gnb.logging_pl.dziennik import (
    NAZWA_LOGU_SZCZEGOLOWEGO,
    NAZWA_LOGU_WAZNEGO,
    ZDARZENIE_CHECKPOINT_ZAPISANY,
    ZDARZENIE_MANIFEST_ZAPISANY,
    ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY,
    ZDARZENIE_PROJEKT_UTWORZONY,
    ZDARZENIE_PROJEKT_WZNOWIONY,
    ZDARZENIE_PROJEKT_ZAKONCZONY,
    ZDARZENIE_ZRODLO_BLAD,
    ZDARZENIE_ZRODLO_POMINIETE,
    ZDARZENIE_ZRODLO_PRZYJETE,
    DziennikSzczegolowy,
    DziennikWazny,
)
from gnb.normalization.normalizacja import zbuduj_dokument_znormalizowany
from gnb.output import regula_md
from gnb.output.manifest import WERSJA_SCHEMATU as WERSJA_SCHEMATU_MANIFESTU
from gnb.output.manifest import Manifest, WpisWyniku, WpisZrodla, zapisz_manifest
from gnb.output.raport import PodsumowanieProjektu, zapisz_raport, zbuduj_raport
from gnb.output.zapis import zapisz_wyniki
from gnb.persistence.checkpoint import WERSJA_SCHEMATU as WERSJA_SCHEMATU_CHECKPOINTU
from gnb.persistence.checkpoint import Checkpoint, StanWyniku, StanZrodla, wczytaj, zapisz
from gnb.persistence.projekt import UkladProjektu, ustal_uklad, utworz_katalogi

_STATUSY_KONCOWE = frozenset(
    {StatusZrodla.SPAKOWANE.value, StatusZrodla.POMINIETE.value, StatusZrodla.BLAD.value}
)
_ROZSZERZENIE_ORYGINALU_TEKSTU = "txt"
_MAKSYMALNA_PODSTAWA_NAZWY = 120


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
    rejestr: RejestrEkstraktorow | None = None,
) -> WynikPrzetwarzania:
    """Przetwarza listę wejść w ramach jednego projektu i zwraca podsumowanie."""
    rejestr = rejestr if rejestr is not None else domyslny_rejestr()
    czas_startu = zegar()

    nazwa = nazwa_projektu or _wygeneruj_nazwe_projektu(pozycje)
    uklad = ustal_uklad(
        konfiguracja.katalog_wynikow, nazwa, wlasny_katalog_projektu=wlasny_katalog_projektu
    )
    utworz_katalogi(uklad)

    istniejacy_checkpoint = wczytaj(uklad.checkpoint)
    wznowiono = istniejacy_checkpoint is not None
    checkpoint = istniejacy_checkpoint or _nowy_checkpoint(uklad, konfiguracja, zegar())

    dziennik_wazny = DziennikWazny(uklad.logi / NAZWA_LOGU_WAZNEGO, zegar)
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

        wykonanie = _Wykonanie(uklad, konfiguracja, checkpoint, dziennik_wazny, log, rejestr, zegar)
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
    ) -> None:
        self._uklad = uklad
        self._konfiguracja = konfiguracja
        self._checkpoint = checkpoint
        self._dziennik_wazny = dziennik_wazny
        self._log = log
        self._rejestr = rejestr
        self._zegar = zegar
        self._uzyte_nazwy: set[str] = {
            stan.nazwa_bazowa_wyniku
            for stan in checkpoint.zrodla.values()
            if stan.nazwa_bazowa_wyniku is not None
        }

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
        except BladGnb as blad:
            self._zapisz_blad_zrodla(zrodlo, pozycja, blad)

    def _przetworz_zrodlo(self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo) -> None:
        identyfikator = zrodlo.identyfikator_zrodla

        tekst, kodowanie = wczytaj_tresc_zrodla(pozycja)
        self._zachowaj_oryginal(pozycja, zrodlo, tekst)
        self._loguj(logging.INFO, identyfikator, f"Źródło {identyfikator}, kodowanie {kodowanie}.")

        ekstraktor = self._rejestr.dobierz(zrodlo.typ_zrodla, pozycja.format_zrodla)
        dokument = ekstraktor.wyekstrahuj(identyfikator, tekst)
        znormalizowany = zbuduj_dokument_znormalizowany(identyfikator, dokument.tekst)

        if znormalizowany.liczba_slow > self._konfiguracja.bezpieczny_limit_slow:
            raise PrzekroczonoLimit(
                f"Źródło ma {znormalizowany.liczba_slow} słów, ponad bezpieczny limit "
                f"{self._konfiguracja.bezpieczny_limit_slow}. Podział źródła to zadanie "
                "etapu szóstego.",
                identyfikator,
            )

        decyzja = regula_md.ocen(dokument)
        nazwa_bazowa = self._nazwa_bazowa(dokument.tytul, identyfikator)
        pliki = zapisz_wyniki(
            self._uklad.pliki_wynikowe,
            nazwa_bazowa,
            identyfikator,
            znormalizowany,
            decyzja,
            formaty_wlaczone=self._konfiguracja.formaty_wynikowe,
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
            checksum=zrodlo.checksum or "",
            format_zrodla=pozycja.format_zrodla,
            status=StatusZrodla.SPAKOWANE.value,
            nazwa_bazowa_wyniku=nazwa_bazowa,
            wyniki=wyniki_stanu,
            liczba_slow=znormalizowany.liczba_slow,
            liczba_znakow=znormalizowany.liczba_znakow,
            decyzja_md=decyzja.generuj_md,
            uzasadnienie_md=list(decyzja.spelnione_warunki),
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

    def _zachowaj_oryginal(self, pozycja: PozycjaWejsciowa, zrodlo: Zrodlo, tekst: str) -> None:
        """Zachowuje oryginał źródła w podkatalogu materiałów źródłowych."""
        self._uklad.materialy_zrodlowe.mkdir(parents=True, exist_ok=True)
        rozszerzenie = pozycja.format_zrodla or _ROZSZERZENIE_ORYGINALU_TEKSTU
        cel = self._uklad.materialy_zrodlowe / f"{zrodlo.identyfikator_zrodla}.{rozszerzenie}"
        if cel.exists():
            return
        if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK:
            zrodlo_pliku = Path(pozycja.wejscie.wartosc)
            if zrodlo_pliku.is_file():
                cel.write_bytes(zrodlo_pliku.read_bytes())
                return
        with cel.open("w", encoding="utf-8", newline="\n") as plik:
            plik.write(tekst)

    def _nazwa_bazowa(self, tytul: str | None, identyfikator: str) -> str:
        propozycja = bezpieczna_nazwa_pliku(
            tytul if tytul else identyfikator, nazwa_awaryjna=identyfikator
        )
        nazwa = propozycja
        licznik = 2
        while nazwa in self._uzyte_nazwy:
            nazwa = f"{propozycja}-{licznik}"
            licznik += 1
        self._uzyte_nazwy.add(nazwa)
        return nazwa

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
        identyfikator = identyfikator_awaryjny(pozycja)
        pochodzenie = (
            Path(pozycja.wejscie.wartosc).name
            if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK
            else "tekst wklejony"
        )
        self._checkpoint.zrodla[identyfikator] = StanZrodla(
            identyfikator=identyfikator,
            typ=pozycja.wejscie.typ_wejscia.value,
            pochodzenie=pochodzenie,
            checksum="",
            format_zrodla=pozycja.format_zrodla,
            status=StatusZrodla.BLAD.value,
            komunikat_bledu=blad.komunikat,
        )
        self._zapisz_checkpoint()
        self._dziennik_wazny.zapisz(ZDARZENIE_ZRODLO_BLAD)
        self._loguj(logging.ERROR, identyfikator, f"Błąd wejścia: {blad.komunikat}")

    def _zapisz_checkpoint(self) -> None:
        # Checkpoint jest zapisywany po każdym źródle, żeby po przerwaniu pracy
        # dało się wznowić bez powtórzeń. Do log_wazne.txt trafia dopiero zapis
        # końcowy, żeby ten log nie tonął we wpisach technicznych.
        self._checkpoint.czas_ostatniej_zmiany = self._zegar().isoformat()
        zapisz(self._uklad.checkpoint, self._checkpoint)

    def _loguj(self, poziom: int, identyfikator: str, komunikat: str) -> None:
        self._log.log(poziom, komunikat, extra={"identyfikator_zrodla": identyfikator})


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
    )


def _policz_status(checkpoint: Checkpoint, status: StatusZrodla) -> int:
    return sum(1 for stan in checkpoint.zrodla.values() if stan.status == status.value)
