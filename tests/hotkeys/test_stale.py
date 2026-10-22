"""Testy flag rejestracji skrótu: każda kombinacja musi dostać MOD_NOREPEAT.

Bez tej flagi Win32 `RegisterHotKey` generuje wiele komunikatów `WM_HOTKEY`
z jednego dłuższego przytrzymania kombinacji, przez automatyczne powtarzanie
klawiatury. Ten test chroni przed regresją do samej sumy modyfikatorów. Sama
kombinacja nie jest już stałą, tylko ustawieniem, więc test sprawdza kilka
różnych kombinacji, a nie jedną domyślną.
"""

from __future__ import annotations

import pytest

from gnb.core.skrot import DOMYSLNA_KOMBINACJA, rozbierz_kombinacje
from gnb.hotkeys.stale import IDENTYFIKATORY_SKROTU

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


def test_domyslna_kombinacja_zawiera_control_i_shift() -> None:
    modyfikatory = DOMYSLNA_KOMBINACJA.modyfikatory_win32()

    assert modyfikatory & MOD_CONTROL
    assert modyfikatory & MOD_SHIFT
    assert not modyfikatory & MOD_ALT
    assert not modyfikatory & MOD_WIN


@pytest.mark.parametrize(
    "napis", ["Control+Shift+F12", "Control+Alt+F11", "Windows+F5", "Alt+Shift+Q", "Shift+F1"]
)
def test_kazda_kombinacja_ma_mod_norepeat(napis: str) -> None:
    """Bez tej flagi przytrzymanie skrótu dodałoby to samo źródło wiele razy."""
    assert rozbierz_kombinacje(napis).modyfikatory_win32() & MOD_NOREPEAT, (
        "Modyfikatory muszą zawierać MOD_NOREPEAT (0x4000), inaczej przytrzymanie "
        "klawiszy generuje wielokrotne WM_HOTKEY."
    )


def test_identyfikatory_rejestracji_sa_dwa_i_rozne() -> None:
    """Zmiana kombinacji rejestruje nową przed wyrejestrowaniem starej, więc potrzeba dwóch."""
    assert len(set(IDENTYFIKATORY_SKROTU)) == 2
