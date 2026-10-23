"""Testy kombinacji globalnego skrótu: rozbiór, reguły i kody Win32.

Reguły są sprawdzane na konkretnych przypadkach z decyzji użytkownika z 22
października 2026, a nie na wartościach wyliczonych tym samym kodem.
"""

from __future__ import annotations

import pytest

from gnb.core.skrot import (
    DOMYSLNA_KOMBINACJA,
    DOMYSLNA_KOMBINACJA_SKROTU,
    KLAWISZE_SKROTU,
    rozbierz_kombinacje,
    zbuduj_kombinacje,
)
from gnb.core.wyjatki import BladTrwaly


def test_domyslna_kombinacja_to_control_shift_f12() -> None:
    assert DOMYSLNA_KOMBINACJA_SKROTU == "Control+Shift+F12"
    assert DOMYSLNA_KOMBINACJA.jako_slowa() == "Control plus Shift plus F12"
    assert DOMYSLNA_KOMBINACJA.kod_klawisza_win32() == 0x7B


def test_lista_klawiszy_ma_f1_do_f24_litery_i_cyfry_bez_klawiszy_stanu() -> None:
    assert KLAWISZE_SKROTU[0] == "F1"
    assert "F24" in KLAWISZE_SKROTU
    assert "F25" not in KLAWISZE_SKROTU
    assert "A" in KLAWISZE_SKROTU and "Z" in KLAWISZE_SKROTU and "0" in KLAWISZE_SKROTU
    assert len(KLAWISZE_SKROTU) == 24 + 26 + 10
    for zabroniony in ("Caps Lock", "CapsLock", "Insert", "Num Lock", "NumLock"):
        assert zabroniony not in KLAWISZE_SKROTU


@pytest.mark.parametrize(
    ("napis", "kod"),
    [("Control+Shift+F1", 0x70), ("Control+Shift+F12", 0x7B), ("Control+Shift+F24", 0x87)],
)
def test_kody_klawiszy_funkcyjnych(napis: str, kod: int) -> None:
    assert rozbierz_kombinacje(napis).kod_klawisza_win32() == kod


def test_kody_liter_i_cyfr_to_kody_ascii() -> None:
    assert rozbierz_kombinacje("Control+Shift+Q").kod_klawisza_win32() == ord("Q")
    assert rozbierz_kombinacje("Control+Shift+7").kod_klawisza_win32() == ord("7")


def test_rozbior_ignoruje_wielkosc_liter_odstepy_i_kolejnosc_i_normalizuje() -> None:
    kombinacja = rozbierz_kombinacje(" shift + CTRL + f11 ")

    assert kombinacja.jako_napis() == "Control+Shift+F11"
    assert rozbierz_kombinacje("win+f5").jako_napis() == "Windows+F5"


def test_napis_i_slowa_podaja_modyfikatory_w_stalej_kolejnosci() -> None:
    kombinacja = zbuduj_kombinacje(control=True, alt=True, shift=True, windows=True, klawisz="f9")

    assert kombinacja.jako_napis() == "Control+Alt+Shift+Windows+F9"
    assert kombinacja.jako_slowa() == "Control plus Alt plus Shift plus Windows plus F9"
    assert rozbierz_kombinacje(kombinacja.jako_napis()) == kombinacja


@pytest.mark.parametrize(
    "napis",
    [
        "Control+Shift+F12",
        "Control+Alt+F11",
        "Control+Shift+Q",
        "Alt+Shift+Q",
        "Windows+F1",
        "Windows+Q",
        "Shift+Windows+F5",
        "Control+Alt+Shift+F9",
    ],
)
def test_dozwolone_kombinacje_przechodza(napis: str) -> None:
    assert rozbierz_kombinacje(napis).jako_napis() == napis


@pytest.mark.parametrize(
    ("napis", "fragment_komunikatu"),
    [
        ("F12", "co najmniej jeden klawisz modyfikujący"),
        ("Q", "co najmniej jeden klawisz modyfikujący"),
        # Reguła pierwsza: pojedynczy modyfikator nie wystarcza nawet dla F1 do F24.
        ("Alt+F4", "co najmniej dwóch modyfikatorów"),
        ("Shift+F10", "co najmniej dwóch modyfikatorów"),
        ("Control+F4", "co najmniej dwóch modyfikatorów"),
        ("Shift+Q", "co najmniej dwóch modyfikatorów"),
        ("Control+C", "co najmniej dwóch modyfikatorów"),
        ("Alt+X", "co najmniej dwóch modyfikatorów"),
        ("Control+7", "co najmniej dwóch modyfikatorów"),
        # Reguła druga: Control plus Alt z literą albo cyfrą to AltGr.
        ("Control+Alt+Q", "prawy Alt"),
        ("Control+Alt+9", "prawy Alt"),
        ("Control+Alt+Shift+A", "prawy Alt"),
    ],
)
def test_niedozwolone_kombinacje_dostaja_polski_komunikat(
    napis: str, fragment_komunikatu: str
) -> None:
    with pytest.raises(BladTrwaly) as blad:
        rozbierz_kombinacje(napis)

    assert fragment_komunikatu in blad.value.komunikat


def test_kombinacja_zapisana_wczesniej_przez_uzytkownika_jest_nadal_dozwolona() -> None:
    """Control plus Alt plus F11 ma dwa modyfikatory i klawisz funkcyjny, więc przechodzi."""
    assert rozbierz_kombinacje("Control+Alt+F11").jako_napis() == "Control+Alt+F11"


@pytest.mark.parametrize(
    "napis", ["Control+Caps Lock", "Control+Insert", "Control+F25", "Control+Num Lock", "Control+"]
)
def test_klawisze_stanu_i_nieistniejace_sa_odrzucane(napis: str) -> None:
    with pytest.raises(BladTrwaly):
        rozbierz_kombinacje(napis)


def test_nieznany_modyfikator_i_pusty_napis_sa_odrzucane() -> None:
    with pytest.raises(BladTrwaly) as blad:
        rozbierz_kombinacje("Super+F12")
    assert "nieznany modyfikator" in blad.value.komunikat
    with pytest.raises(BladTrwaly):
        rozbierz_kombinacje("")
    with pytest.raises(BladTrwaly):
        rozbierz_kombinacje("Control++F12")
