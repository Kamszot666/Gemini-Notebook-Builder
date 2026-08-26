"""Testy podpolecenia wiersza poleceń ``gnb przetworz``."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.cli import main

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"


def test_przetworz_konczy_sie_kodem_zero_dla_poprawnego_wejscia(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(
        [
            "przetworz",
            "--projekt",
            "Test CLI",
            "--plik",
            str(KATALOG_DANYCH / "dokument_strukturalny.md"),
            "--tekst",
            "Krótki tekst wklejony.",
        ]
    )

    assert kod == 0
    wyjscie = capsys.readouterr().out
    assert "Przetworzono 2 źródeł, pominięto 0." in wyjscie
    assert "Wyniki są w katalogu:" in wyjscie
    assert (tmp_path / "Test CLI" / "manifest.json").exists()


def test_przetworz_bez_zrodel_konczy_sie_kodem_niezerowym(
    capsys: pytest.CaptureFixture[str],
) -> None:
    kod = main(["przetworz", "--projekt", "Bez źródeł"])
    assert kod == 2
    assert "Nie podano żadnego źródła" in capsys.readouterr().out


def test_przetworz_z_bledna_sciezka_pliku_konczy_sie_kodem_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(["przetworz", "--projekt", "Test błędu", "--plik", str(tmp_path / "nie_ma.txt")])

    assert kod == 0
    assert "Źródła z błędem: 1" in capsys.readouterr().out
