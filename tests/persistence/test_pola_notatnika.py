"""Testy trwałego przechowywania dwóch pól tekstowych notatnika."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.persistence.pola_notatnika import (
    PolaNotatnika,
    PrzekroczonoLimitZnakow,
    wczytaj,
    zapisz,
)


def test_brak_pliku_daje_puste_pola(tmp_path: Path) -> None:
    pola = wczytaj(tmp_path / "pola_notatnika.json")
    assert pola == PolaNotatnika(instrukcja_systemowa="", prompt_wyszukiwania="")


def test_zapis_i_odczyt_zwraca_te_same_pola(tmp_path: Path) -> None:
    sciezka = tmp_path / "pola_notatnika.json"
    oryginal = PolaNotatnika(
        instrukcja_systemowa="Odpowiadaj zwięźle i po polsku.",
        prompt_wyszukiwania="Znajdź artykuły o dostępności aplikacji desktopowych.",
    )
    zapisz(sciezka, oryginal, limit_znakow_instrukcji=10_000)

    assert wczytaj(sciezka) == oryginal


def test_przekroczenie_limitu_instrukcji_konczy_sie_wyjatkiem(tmp_path: Path) -> None:
    sciezka = tmp_path / "pola_notatnika.json"
    pola = PolaNotatnika(instrukcja_systemowa="a" * 11)

    with pytest.raises(PrzekroczonoLimitZnakow, match="ponad limit"):
        zapisz(sciezka, pola, limit_znakow_instrukcji=10)

    assert not sciezka.exists(), "plik nie może powstać, gdy zapis odrzucono"


def test_prompt_wyszukiwania_nie_ma_limitu(tmp_path: Path) -> None:
    sciezka = tmp_path / "pola_notatnika.json"
    pola = PolaNotatnika(instrukcja_systemowa="krótka", prompt_wyszukiwania="x" * 50_000)

    zapisz(sciezka, pola, limit_znakow_instrukcji=100)

    assert len(wczytaj(sciezka).prompt_wyszukiwania) == 50_000


def test_uszkodzony_plik_daje_blad_trwaly(tmp_path: Path) -> None:
    sciezka = tmp_path / "pola_notatnika.json"
    sciezka.write_text("to nie jest json", encoding="utf-8")

    with pytest.raises(BladTrwaly):
        wczytaj(sciezka)


def test_polskie_znaki_przezywaja_zapis_i_odczyt(tmp_path: Path) -> None:
    sciezka = tmp_path / "pola_notatnika.json"
    pola = PolaNotatnika(instrukcja_systemowa="Zażółć gęślą jaźń.")
    zapisz(sciezka, pola, limit_znakow_instrukcji=10_000)

    assert wczytaj(sciezka).instrukcja_systemowa == "Zażółć gęślą jaźń."
    assert "\\u" not in sciezka.read_text(encoding="utf-8")
