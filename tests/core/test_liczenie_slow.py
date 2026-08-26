"""Testy jednej wspólnej definicji liczenia słów i znaków."""

from __future__ import annotations

import pytest

from gnb.core.liczenie_slow import policz_slowa, policz_znaki


@pytest.mark.parametrize(
    ("tekst", "oczekiwana_liczba_slow"),
    [
        ("", 0),
        ("   \n\t  ", 0),
        ("jedno", 1),
        ("dwa słowa", 2),
        ("wiele   spacji    między   słowami", 4),
        ("słowa\nw\nkolejnych\nwierszach", 4),
        ("  wiodące i końcowe spacje  ", 4),
        ("tabulator\tteż\trozdziela", 3),
        ("zażółć gęślą jaźń", 3),
    ],
)
def test_policz_slowa_dzieli_po_bialych_znakach(tekst: str, oczekiwana_liczba_slow: int) -> None:
    assert policz_slowa(tekst) == oczekiwana_liczba_slow


def test_policz_znaki_liczy_wszystkie_znaki_wraz_z_bialymi() -> None:
    assert policz_znaki("abc def") == 7
    assert policz_znaki("") == 0
    assert policz_znaki("ą") == 1
