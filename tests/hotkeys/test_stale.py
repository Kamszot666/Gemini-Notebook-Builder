"""Testy stałych globalnego skrótu: kombinacja klawiszy musi zawierać MOD_NOREPEAT.

Bez tej flagi Win32 `RegisterHotKey` generuje wiele komunikatów `WM_HOTKEY`
z jednego dłuższego przytrzymania kombinacji, przez automatyczne powtarzanie
klawiatury. Ten test chroni przed regresją do samej sumy MOD_CONTROL i
MOD_SHIFT.
"""

from __future__ import annotations

from gnb.hotkeys.stale import MODYFIKATORY_SKROTU

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000


def test_modyfikatory_zawieraja_control_i_shift() -> None:
    assert MODYFIKATORY_SKROTU & MOD_CONTROL
    assert MODYFIKATORY_SKROTU & MOD_SHIFT


def test_modyfikatory_zawieraja_mod_norepeat() -> None:
    """Bez tej flagi przytrzymanie skrótu dodałoby to samo źródło wiele razy."""
    assert MODYFIKATORY_SKROTU & MOD_NOREPEAT, (
        "MODYFIKATORY_SKROTU musi zawierać MOD_NOREPEAT (0x4000), inaczej "
        "przytrzymanie klawiszy generuje wielokrotne WM_HOTKEY."
    )
