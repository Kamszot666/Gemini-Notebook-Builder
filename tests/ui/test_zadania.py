"""Testy rejestru jednego zadania przetwarzania w tle."""

from __future__ import annotations

import threading
import time

import pytest

from gnb.core.postep import FazaPotoku, ZdarzeniePostepu
from gnb.ui.zadania import RejestrZadan, StanZadania, ZadanieJuzTrwa


def _poczekaj_na_stan(rejestr: RejestrZadan, oczekiwany: StanZadania) -> None:
    for _ in range(200):
        informacja = rejestr.informacja()
        if informacja is not None and informacja.stan is oczekiwany:
            return
        time.sleep(0.01)
    raise AssertionError(f"Zadanie nie osiągnęło stanu {oczekiwany} w wyznaczonym czasie.")


def test_zakonczone_zadanie_ma_stan_zakonczone_i_wynik() -> None:
    rejestr = RejestrZadan()
    wartownik = object()

    def praca(postep):  # type: ignore[no-untyped-def]
        postep(ZdarzeniePostepu(FazaPotoku.EKSTRAKCJA, 1, 1, "Przetworzono 1 z 1 źródeł"))
        return wartownik

    rejestr.uruchom("Projekt", praca)
    _poczekaj_na_stan(rejestr, StanZadania.ZAKONCZONE)

    informacja = rejestr.informacja()
    assert informacja is not None
    assert informacja.wynik is wartownik
    assert informacja.komunikat_bledu is None


def test_wyjatek_w_watku_daje_stan_bledu_a_nie_slad_stosu() -> None:
    rejestr = RejestrZadan()

    def praca(_postep):  # type: ignore[no-untyped-def]
        raise RuntimeError("coś poszło nie tak")

    rejestr.uruchom("Projekt z błędem", praca)
    _poczekaj_na_stan(rejestr, StanZadania.BLAD)

    informacja = rejestr.informacja()
    assert informacja is not None
    assert informacja.komunikat_bledu == "coś poszło nie tak"


def test_drugie_uruchomienie_w_trakcie_pierwszego_jest_odrzucane() -> None:
    rejestr = RejestrZadan()
    zwolnij = threading.Event()

    def praca_dluga(_postep):  # type: ignore[no-untyped-def]
        zwolnij.wait(timeout=5)
        return None

    rejestr.uruchom("Pierwszy", praca_dluga)
    try:
        with pytest.raises(ZadanieJuzTrwa, match="Trwa już przetwarzanie"):
            rejestr.uruchom("Drugi", praca_dluga)
    finally:
        zwolnij.set()


def test_brak_zadania_daje_none() -> None:
    assert RejestrZadan().informacja() is None
