"""Testy normalizacji tekstu źródła."""

from __future__ import annotations

import unicodedata

from gnb.normalization.normalizacja import zbuduj_dokument_znormalizowany, znormalizuj


def test_konce_wierszy_sa_sprowadzane_do_lf() -> None:
    assert znormalizuj("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_biale_znaki_z_koncow_wierszy_sa_usuwane() -> None:
    assert (
        znormalizuj("wiersz z ogonem   \n  wcięty wiersz  ") == "wiersz z ogonem\n  wcięty wiersz"
    )


def test_nadmiarowe_puste_wiersze_sa_skracane() -> None:
    assert znormalizuj("a\n\n\n\n\nb") == "a\n\nb"


def test_puste_wiersze_z_poczatku_i_konca_sa_usuwane() -> None:
    assert znormalizuj("\n\n  treść  \n\n") == "treść"


def test_znaki_unicode_sa_sprowadzane_do_nfc() -> None:
    tekst_nfd = unicodedata.normalize("NFD", "ąćź")
    wynik = znormalizuj(tekst_nfd)
    assert wynik == "ąćź"
    assert unicodedata.is_normalized("NFC", wynik)


def test_normalizacja_jest_idempotentna() -> None:
    surowy = "\r\n Tytuł  \r\n\r\n\r\n Treść z ogonem \t\n"
    raz = znormalizuj(surowy)
    assert znormalizuj(raz) == raz


def test_dokument_znormalizowany_ma_liczniki_z_tekstu_po_normalizacji() -> None:
    dokument = zbuduj_dokument_znormalizowany("zrodlo-1", "  dwa\r\n\r\n\r\nsłowa  ")
    assert dokument.tekst == "dwa\n\nsłowa"
    assert dokument.liczba_slow == 2
    assert dokument.liczba_znakow == len("dwa\n\nsłowa")
