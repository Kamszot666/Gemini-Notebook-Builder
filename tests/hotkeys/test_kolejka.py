"""Testy kolejki źródeł dodanych globalnym skrótem, gdy rejestr zadań jest zajęty.

`KolejkaSkrotu` jest czystą strukturą danych bez zależności od Windows.
"""

from __future__ import annotations

from datetime import UTC, datetime

from gnb.hotkeys.kolejka import KolejkaSkrotu
from gnb.ingestion.wejscie import przyjmij_tekst


def _pozycja(tresc: str = "treść") -> object:
    return przyjmij_tekst(tresc, datetime.now(UTC))


def test_kolejka_pusta_na_starcie() -> None:
    kolejka = KolejkaSkrotu()

    assert kolejka.czy_pusta() is True
    assert kolejka.liczba_oczekujacych() == 0
    assert kolejka.odbierz_jeden_projekt() is None


def test_dodanie_i_odebranie_jednego_projektu() -> None:
    kolejka = KolejkaSkrotu()
    pozycja = _pozycja("pierwsza")

    kolejka.dodaj("Projekt A", pozycja)

    assert kolejka.czy_pusta() is False
    assert kolejka.liczba_oczekujacych() == 1

    wynik = kolejka.odbierz_jeden_projekt()
    assert wynik is not None
    nazwa, pozycje = wynik
    assert nazwa == "Projekt A"
    assert pozycje == [pozycja]
    assert kolejka.czy_pusta() is True


def test_wiele_pozycji_tego_samego_projektu_wraca_razem() -> None:
    kolejka = KolejkaSkrotu()
    kolejka.dodaj("Projekt A", _pozycja("pierwsza"))
    kolejka.dodaj("Projekt A", _pozycja("druga"))

    assert kolejka.liczba_oczekujacych() == 2
    nazwa, pozycje = kolejka.odbierz_jeden_projekt()  # type: ignore[misc]
    assert nazwa == "Projekt A"
    assert len(pozycje) == 2
    assert kolejka.odbierz_jeden_projekt() is None


def test_odebranie_jednego_projektu_nie_rusza_innych() -> None:
    kolejka = KolejkaSkrotu()
    kolejka.dodaj("Pierwszy", _pozycja("a"))
    kolejka.dodaj("Drugi", _pozycja("b"))

    nazwa, _ = kolejka.odbierz_jeden_projekt()  # type: ignore[misc]

    assert nazwa == "Pierwszy"
    assert kolejka.liczba_oczekujacych() == 1
    assert kolejka.czy_pusta() is False

    nazwa2, _ = kolejka.odbierz_jeden_projekt()  # type: ignore[misc]
    assert nazwa2 == "Drugi"
    assert kolejka.czy_pusta() is True


def test_liczba_oczekujacych_sumuje_wszystkie_projekty() -> None:
    kolejka = KolejkaSkrotu()
    kolejka.dodaj("Pierwszy", _pozycja("a"))
    kolejka.dodaj("Pierwszy", _pozycja("b"))
    kolejka.dodaj("Drugi", _pozycja("c"))

    assert kolejka.liczba_oczekujacych() == 3
