"""Testy odczytu zaznaczenia w Eksploratorze, wymagające otwartego okna z zaznaczeniem.

Nosi marker `pulpit` i jest domyślnie pominięty, zgodnie z sekcją piątą
CLAUDE.md. Uruchom go ręcznie poleceniem
``python -m pytest -m pulpit tests/hotkeys/test_eksplorator.py`` z otwartym
oknem Eksploratora i zaznaczonym przynajmniej jednym plikiem.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = [
    pytest.mark.pulpit,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="Odczyt zaznaczenia w Eksploratorze działa wyłącznie na Windows.",
    ),
]

if sys.platform == "win32":
    from gnb.hotkeys import _eksplorator, _win32

_KLASA_OKNA_EKSPLORATORA = "CabinetWClass"


def test_odczyt_zaznaczenia_z_aktywnego_eksploratora() -> None:
    okno = _win32.informacje_o_aktywnym_oknie()
    if okno is None or okno.nazwa_klasy != _KLASA_OKNA_EKSPLORATORA:
        pytest.skip(
            "Aktywne okno nie jest Eksploratorem plików. Otwórz Eksplorator, "
            "zaznacz przynajmniej jeden plik i uruchom ten test jeszcze raz."
        )

    zaznaczenie = _eksplorator.odczytaj_zaznaczenie(okno.uchwyt)

    assert len(zaznaczenie) > 0, (
        "Okno Eksploratora jest aktywne, ale zaznaczenie jest puste — zaznacz "
        "plik przed uruchomieniem tego testu."
    )
    assert all(sciezka.exists() for sciezka in zaznaczenie)
