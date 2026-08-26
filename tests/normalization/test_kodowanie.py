"""Testy wykrywania kodowania i dekodowania bajtów źródła do tekstu."""

from __future__ import annotations

from pathlib import Path

from gnb.normalization.kodowanie import zdekoduj

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"
_ZNAK_BOM = "\ufeff"


def test_plik_windows1250_odczytany_bez_utraty_polskich_znakow() -> None:
    dane = (KATALOG_DANYCH / "tekst_windows1250.txt").read_bytes()
    tekst, kodowanie = zdekoduj(dane)

    assert "Zażółć gęślą jaźń." in tekst
    assert "zakończenia wierszy CRLF" in tekst
    assert "?" not in tekst
    assert "cp1250" in kodowanie.lower() or "windows-1250" in kodowanie.lower()


def test_bom_utf8_jest_usuwany() -> None:
    dane = "Tekst po BOM.".encode("utf-8-sig")
    tekst, _ = zdekoduj(dane)
    assert tekst == "Tekst po BOM."
    assert not tekst.startswith(_ZNAK_BOM)


def test_czysty_utf8_dziala() -> None:
    tekst, kodowanie = zdekoduj("Zwykły tekst UTF-8 z ą, ć, ż.".encode())
    assert tekst == "Zwykły tekst UTF-8 z ą, ć, ż."
    assert "utf" in kodowanie.lower()


def test_puste_wejscie_daje_pusty_tekst() -> None:
    tekst, kodowanie = zdekoduj(b"")
    assert tekst == ""
    assert kodowanie == "utf-8"


def test_bom_utf16_jest_usuwany() -> None:
    dane = "Tekst UTF-16.".encode("utf-16")
    tekst, _ = zdekoduj(dane)
    assert tekst == "Tekst UTF-16."
    assert not tekst.startswith(_ZNAK_BOM)
