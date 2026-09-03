"""Testy przyjmowania plików obrazów jako wejścia i kierowania ich ścieżką binarną."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import PrzekroczonoLimit
from gnb.ingestion.wejscie import (
    czy_format_binarny,
    przyjmij_plik,
    typ_zrodla_dla_pliku,
    waliduj_i_utworz_zrodlo,
)

_MOMENT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "rozszerzenie",
    ["png", "jpg", "jpeg", "webp", "tiff", "bmp", "gif", "heic"],
)
def test_format_obrazu_daje_typ_zrodla_obraz(rozszerzenie: str) -> None:
    assert typ_zrodla_dla_pliku(rozszerzenie) is TypZrodla.PLIK_OBRAZ
    assert czy_format_binarny(rozszerzenie) is True


def test_plik_tekstowy_nie_jest_binarny() -> None:
    assert czy_format_binarny("txt") is False
    assert typ_zrodla_dla_pliku("txt") is TypZrodla.PLIK_TEKSTOWY


def test_walidacja_pliku_png_tworzy_zrodlo_typu_obraz(
    tmp_path: Path, obraz_z_tekstem: Callable[..., bytes]
) -> None:
    plik = tmp_path / "diagram.png"
    plik.write_bytes(obraz_z_tekstem(["diagram"]))

    zrodlo = waliduj_i_utworz_zrodlo(
        przyjmij_plik(plik, _MOMENT), Konfiguracja(katalog_wynikow=tmp_path), _MOMENT
    )

    assert zrodlo.typ_zrodla is TypZrodla.PLIK_OBRAZ
    assert zrodlo.checksum


def test_zbyt_duzy_obraz_jest_pomijany_przekroczeniem_limitu(tmp_path: Path) -> None:
    plik = tmp_path / "wielki.png"
    plik.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * (3 * 1024 * 1024))

    with pytest.raises(PrzekroczonoLimit):
        waliduj_i_utworz_zrodlo(
            przyjmij_plik(plik, _MOMENT),
            Konfiguracja(katalog_wynikow=tmp_path, bezpieczny_limit_mb=2),
            _MOMENT,
        )
