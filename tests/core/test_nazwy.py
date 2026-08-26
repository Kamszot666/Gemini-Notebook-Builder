"""Testy sanityzacji nazw projektów i plików do postaci bezpiecznej dla Windows."""

from __future__ import annotations

import pytest

from gnb.core.nazwy import (
    bezpieczna_nazwa_pliku,
    sanityzuj_nazwe_projektu,
    wygeneruj_nazwe_projektu,
)
from gnb.core.wyjatki import BladTrwaly


@pytest.mark.parametrize("nazwa_zarezerwowana", ["CON", "con", "PRN", "COM1", "LPT9", "nul"])
def test_nazwa_zarezerwowana_jest_odrzucana(nazwa_zarezerwowana: str) -> None:
    with pytest.raises(BladTrwaly):
        sanityzuj_nazwe_projektu(nazwa_zarezerwowana)


def test_znaki_niedozwolone_sa_zamieniane_na_podkreslenie() -> None:
    assert sanityzuj_nazwe_projektu("raport: 2026/08 <wersja>") == "raport_ 2026_08 _wersja_"


def test_koncowe_kropki_i_spacje_sa_usuwane() -> None:
    assert sanityzuj_nazwe_projektu("Projekt testowy...  ") == "Projekt testowy"


def test_pusta_nazwa_po_oczyszczeniu_jest_bledem() -> None:
    with pytest.raises(BladTrwaly):
        sanityzuj_nazwe_projektu("   ...   ")


def test_wygeneruj_nazwe_bierze_poczatkowe_slowa() -> None:
    nazwa = wygeneruj_nazwe_projektu("Jak przygotować bazę wiedzy dla asystenta AI krok po kroku")
    assert nazwa == "jak_przygotować_bazę_wiedzy_dla_asystenta_ai_krok"


def test_wygeneruj_nazwe_zwraca_awaryjna_dla_pustej_podstawy() -> None:
    assert wygeneruj_nazwe_projektu("   ") == "projekt"


def test_bezpieczna_nazwa_pliku_uzywa_awaryjnej_dla_nazwy_zarezerwowanej() -> None:
    assert (
        bezpieczna_nazwa_pliku("CON", nazwa_awaryjna="tekst_wklejony-abc") == "tekst_wklejony-abc"
    )


def test_bezpieczna_nazwa_pliku_zachowuje_poprawny_tytul() -> None:
    assert (
        bezpieczna_nazwa_pliku("Notatka o kodowaniu", nazwa_awaryjna="x") == "Notatka o kodowaniu"
    )
