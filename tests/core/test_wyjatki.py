"""Testy taksonomii wyjątków z gnb.core.wyjatki."""

from __future__ import annotations

import pytest

from gnb.core.wyjatki import (
    BladPrzejsciowy,
    BladTrwaly,
    BrakNarzedzia,
    FormatNieobslugiwany,
    PrzekroczonoLimit,
)


@pytest.mark.parametrize(
    "klasa_wyjatku",
    [BladPrzejsciowy, BladTrwaly, FormatNieobslugiwany, BrakNarzedzia, PrzekroczonoLimit],
)
def test_wyjatek_niesie_komunikat_i_identyfikator_zrodla(klasa_wyjatku: type[Exception]) -> None:
    wyjatek = klasa_wyjatku("Czytelny komunikat po polsku.", identyfikator_zrodla="abc123")

    assert wyjatek.komunikat == "Czytelny komunikat po polsku."  # type: ignore[attr-defined]
    assert wyjatek.identyfikator_zrodla == "abc123"  # type: ignore[attr-defined]
    assert str(wyjatek) == "Czytelny komunikat po polsku."


@pytest.mark.parametrize(
    "klasa_wyjatku",
    [BladPrzejsciowy, BladTrwaly, FormatNieobslugiwany, BrakNarzedzia, PrzekroczonoLimit],
)
def test_identyfikator_zrodla_jest_opcjonalny(klasa_wyjatku: type[Exception]) -> None:
    wyjatek = klasa_wyjatku("Komunikat bez znanego źródła.")

    assert wyjatek.identyfikator_zrodla is None  # type: ignore[attr-defined]
