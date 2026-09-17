"""Testy odczytu paska adresu przez UI Automation, wymagające otwartej przeglądarki.

Ten test wymaga konkretnego stanu pulpitu — okna Chrome albo Firefoksa na
pierwszym planie — więc nosi marker `pulpit` i jest domyślnie pominięty, zgodnie
z sekcją piątą CLAUDE.md. Uruchom go ręcznie poleceniem
``python -m pytest -m pulpit tests/hotkeys/test_automatyzacja.py`` z otwartą
przeglądarką. Logikę rozpoznania niezależną od tego, jakie okno jest aktywne,
sprawdzają `test_win32.py` i `test_obsluga.py`.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = [
    pytest.mark.pulpit,
    pytest.mark.skipif(
        sys.platform != "win32",
        reason="UI Automation dla przeglądarek działa wyłącznie na Windows.",
    ),
]

if sys.platform == "win32":
    from gnb.hotkeys import _automatyzacja, _win32

_PRZEGLADARKI = {"chrome", "firefox"}


def test_odczyt_paska_adresu_z_aktywnej_przegladarki() -> None:
    okno = _win32.informacje_o_aktywnym_oknie()
    if okno is None or okno.nazwa_procesu not in _PRZEGLADARKI:
        pytest.skip(
            "Aktywne okno nie jest Chrome ani Firefoksem. Otwórz jedną z tych "
            "przeglądarek na dowolnej stronie i uruchom ten test jeszcze raz."
        )

    adres = _automatyzacja.odczytaj_pasek_adresu(okno.uchwyt)

    assert adres is not None, (
        "Pasek adresu nie został odnaleziony w oknie — sprawdź, czy klasa "
        "kontrolki nie zmieniła się w nowszej wersji przeglądarki."
    )
    assert adres.strip() != ""
