"""Testy komendy `python -m gnb.cli diagnostyka`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gnb import cli


def _uruchom_diagnostyke(*dodatkowe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "gnb.cli", "diagnostyka", *dodatkowe],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


class _FalszywyStrumien:
    """Strumień udający standardowe wyjście, ale niebędący ``io.TextIOWrapper``.

    Służy sprawdzeniu, że przełączenie kodowania rozpoznaje strumień po metodzie
    ``reconfigure``, a nie po konkretnym typie. Wariant `rzuca` sprawdza, że
    nieudane przełączenie nie zatrzymuje aplikacji.
    """

    def __init__(self, *, rzuca: bool = False) -> None:
        self.wywolania: list[dict[str, Any]] = []
        self._rzuca = rzuca

    def reconfigure(self, **argumenty: Any) -> None:
        self.wywolania.append(argumenty)
        if self._rzuca:
            raise ValueError("Tego strumienia nie da się przełączyć.")


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


def test_diagnostyka_z_opcja_plik_zapisuje_raport_w_utf8(tmp_path: Path) -> None:
    """Opcja --plik zapisuje raport wprost do pliku UTF-8 ze znacznikiem kolejności bajtów.

    Zapis wprost pomija przekierowanie powłoki, które na Windows psuje polskie
    znaki. Test czerwieni się, gdy plik przestanie być czytelnym UTF-8 albo gdy
    zgubi znaki diakrytyczne.
    """

    cel = tmp_path / "podkatalog" / "raport.txt"

    kod = cli.uruchom_diagnostyke(str(cel))

    assert kod == 0
    surowe = cel.read_bytes()
    assert surowe.startswith(b"\xef\xbb\xbf")
    tekst = cel.read_text(encoding="utf-8-sig")
    assert "narzędzi zewnętrznych" in tekst
    assert "Koniec raportu" in tekst


def test_diagnostyka_przez_wiersz_polecen_z_opcja_plik(tmp_path: Path) -> None:
    """Uruchomiona jako podproces komenda zapisuje czytelny raport do wskazanego pliku."""

    cel = tmp_path / "raport.txt"

    wynik = _uruchom_diagnostyke("--plik", str(cel))

    assert wynik.returncode == 0
    assert cel.read_text(encoding="utf-8-sig").count("ż") >= 1


def test_wymus_kodowanie_utf8_przelacza_strumien_bez_typu_textiowrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Przełączenie kodowania rozpoznaje strumień po metodzie, a nie po typie.

    Test czerwieni się, gdy kod wróci do sprawdzania ``isinstance`` z konkretnym
    typem: sztuczny strumień nie jest ``io.TextIOWrapper``, więc nie zostałby
    wtedy przełączony.
    """

    falszywy_out = _FalszywyStrumien()
    falszywy_err = _FalszywyStrumien()
    monkeypatch.setattr(sys, "stdout", falszywy_out)
    monkeypatch.setattr(sys, "stderr", falszywy_err)

    cli._wymus_kodowanie_utf8()

    assert falszywy_out.wywolania == [{"encoding": "utf-8", "errors": "replace"}]
    assert falszywy_err.wywolania == [{"encoding": "utf-8", "errors": "replace"}]


def test_wymus_kodowanie_utf8_toleruje_nieudane_przelaczenie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nieudane przełączenie kodowania nie może zatrzymać aplikacji."""

    monkeypatch.setattr(sys, "stdout", _FalszywyStrumien(rzuca=True))
    monkeypatch.setattr(sys, "stderr", _FalszywyStrumien(rzuca=True))

    cli._wymus_kodowanie_utf8()
