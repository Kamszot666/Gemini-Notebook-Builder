"""Rejestr jednego zadania przetwarzania w tle.

Interfejs uruchamia potok w osobnym wątku, żeby żądanie HTTP wróciło od razu,
a strona projektu mogła pokazywać postęp. Jednocześnie działa najwyżej jedno
zadanie: dwa równoległe przebiegi pisałyby do tego samego checkpointu. Drugie
żądanie uruchomienia jest odrzucane czytelnym komunikatem, a nie kolejkowane.

Wyjątek w wątku roboczym jest przechwytywany i zapisywany jako stan błędu,
nigdy nie ucieka jako surowy ślad stosu.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from gnb.core.postep import WywolanieZwrotnePostepu
from gnb.potok import WynikPrzetwarzania
from gnb.ui.postep import DlawikPostepu

# Praca zlecana rejestrowi: funkcja przyjmująca wywołanie zwrotne postępu
# i zwracająca podsumowanie przetwarzania. Rejestr podaje jej dławik postępu.
PracaWTle = Callable[[WywolanieZwrotnePostepu], WynikPrzetwarzania]


class StanZadania(StrEnum):
    """Stan zadania przetwarzania w tle."""

    TRWA = "trwa"
    ZAKONCZONE = "zakonczone"
    BLAD = "blad"


class ZadanieJuzTrwa(Exception):
    """Próba uruchomienia drugiego zadania, gdy jedno już trwa."""


@dataclass(frozen=True, slots=True)
class InformacjaOZadaniu:
    """Migawka stanu zadania przekazywana do widoku."""

    nazwa_projektu: str
    stan: StanZadania
    komunikat_postepu: str
    komunikat_bledu: str | None
    wynik: WynikPrzetwarzania | None


@dataclass
class _Zadanie:
    nazwa_projektu: str
    dlawik: DlawikPostepu
    stan: StanZadania = StanZadania.TRWA
    wynik: WynikPrzetwarzania | None = None
    komunikat_bledu: str | None = None


class RejestrZadan:
    """Trzyma stan najwyżej jednego zadania przetwarzania w tle."""

    def __init__(self) -> None:
        self._zamek = threading.Lock()
        self._zadanie: _Zadanie | None = None

    def uruchom(self, nazwa_projektu: str, praca: PracaWTle) -> None:
        """Uruchamia pracę w nowym wątku. Odrzuca żądanie, gdy zadanie już trwa."""
        with self._zamek:
            if self._zadanie is not None and self._zadanie.stan is StanZadania.TRWA:
                raise ZadanieJuzTrwa(
                    f"Trwa już przetwarzanie projektu „{self._zadanie.nazwa_projektu}”. "
                    "Poczekaj na jego zakończenie, zanim uruchomisz kolejne."
                )
            zadanie = _Zadanie(nazwa_projektu=nazwa_projektu, dlawik=DlawikPostepu())
            self._zadanie = zadanie

        watek = threading.Thread(
            target=self._wykonaj,
            args=(zadanie, praca),
            name="gnb-przetwarzanie",
            daemon=True,
        )
        watek.start()

    def informacja(self) -> InformacjaOZadaniu | None:
        """Zwraca migawkę stanu bieżącego zadania albo nic, gdy żadnego nie było."""
        with self._zamek:
            zadanie = self._zadanie
            if zadanie is None:
                return None
            return InformacjaOZadaniu(
                nazwa_projektu=zadanie.nazwa_projektu,
                stan=zadanie.stan,
                komunikat_postepu=zadanie.dlawik.komunikat(),
                komunikat_bledu=zadanie.komunikat_bledu,
                wynik=zadanie.wynik,
            )

    def czy_trwa(self) -> bool:
        with self._zamek:
            return self._zadanie is not None and self._zadanie.stan is StanZadania.TRWA

    def _wykonaj(self, zadanie: _Zadanie, praca: PracaWTle) -> None:
        # Wątek roboczy przechwytuje każdy wyjątek: nie ma go komu przekazać
        # wyżej, a jego wyciek zabiłby wątek bez śladu w interfejsie.
        try:
            wynik = praca(zadanie.dlawik.przyjmij)
        except Exception as blad:
            with self._zamek:
                zadanie.stan = StanZadania.BLAD
                zadanie.komunikat_bledu = str(blad) or blad.__class__.__name__
            return
        with self._zamek:
            zadanie.wynik = wynik
            zadanie.stan = StanZadania.ZAKONCZONE
