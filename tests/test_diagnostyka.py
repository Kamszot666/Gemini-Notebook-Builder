"""Testy komendy `python -m gnb.cli diagnostyka`."""

from __future__ import annotations

import subprocess
import sys


def _uruchom_diagnostyke() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "gnb.cli", "diagnostyka"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_diagnostyka_zwraca_kod_zero_niezaleznie_od_dostepnosci_narzedzi() -> None:
    """Brak narzędzia opcjonalnego nie może wywalić komendy diagnostyki."""

    wynik = _uruchom_diagnostyke()

    assert wynik.returncode == 0
    assert "Raport diagnostyczny" in wynik.stdout
    assert "Koniec raportu" in wynik.stdout


def test_diagnostyka_wymienia_wszystkie_sprawdzane_narzedzia() -> None:
    """Raport musi wymieniać nazwę każdego z pięciu narzędzi z sekcji piątej CLAUDE.md."""

    wynik = _uruchom_diagnostyke()

    for nazwa in ("FFmpeg", "Tesseract", "LibreOffice", "MuseScore", "Java"):
        assert nazwa in wynik.stdout
