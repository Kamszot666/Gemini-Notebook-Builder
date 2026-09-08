"""Testy przyjmowania materiałów nutowych jako wejścia."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import FormatNieobslugiwany, PrzekroczonoLimit
from gnb.ingestion.wejscie import (
    FORMATY_PLIKOW,
    FORMATY_PLIKOW_BINARNYCH,
    czy_format_binarny,
    przyjmij_plik,
    typ_zrodla_dla_pliku,
    waliduj_i_utworz_zrodlo,
)

_MOMENT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("rozszerzenie", ["mid", "midi", "musicxml", "mxl", "gp3", "gp4", "gp5"])
def test_format_nutowy_daje_typ_zrodla_nuty_i_jest_binarny(rozszerzenie: str) -> None:
    assert typ_zrodla_dla_pliku(rozszerzenie) is TypZrodla.PLIK_NUTY
    assert rozszerzenie in FORMATY_PLIKOW
    assert rozszerzenie in FORMATY_PLIKOW_BINARNYCH
    assert czy_format_binarny(rozszerzenie) is True


def test_pdf_z_flaga_nuty_daje_typ_nuty_a_bez_flagi_dokument() -> None:
    assert typ_zrodla_dla_pliku("pdf") is TypZrodla.PLIK_DOKUMENT
    assert typ_zrodla_dla_pliku("pdf", wymus_nuty=True) is TypZrodla.PLIK_NUTY


def test_obraz_z_flaga_nuty_daje_typ_nuty_a_tekst_nie() -> None:
    assert typ_zrodla_dla_pliku("png", wymus_nuty=True) is TypZrodla.PLIK_NUTY
    assert typ_zrodla_dla_pliku("txt", wymus_nuty=True) is TypZrodla.PLIK_TEKSTOWY


def test_przyjmij_plik_przenosi_flage_nuty_do_pozycji() -> None:
    pozycja = przyjmij_plik(Path("skan.pdf"), _MOMENT, nuty=True)
    assert pozycja.wymus_nuty is True
    assert przyjmij_plik(Path("skan.pdf"), _MOMENT).wymus_nuty is False


def test_walidacja_pliku_midi_tworzy_zrodlo_typu_nuty(tmp_path: Path) -> None:
    plik = tmp_path / "melodia.mid"
    plik.write_bytes(Path("tests/dane/melodia.mid").read_bytes())

    zrodlo = waliduj_i_utworz_zrodlo(
        przyjmij_plik(plik, _MOMENT), Konfiguracja(katalog_wynikow=tmp_path), _MOMENT
    )
    assert zrodlo.typ_zrodla is TypZrodla.PLIK_NUTY
    assert zrodlo.checksum


def test_walidacja_pdf_z_flaga_nuty_daje_zrodlo_typu_nuty(tmp_path: Path) -> None:
    plik = tmp_path / "skan.pdf"
    plik.write_bytes(b"%PDF-1.4\n%%EOF\n")

    zrodlo = waliduj_i_utworz_zrodlo(
        przyjmij_plik(plik, _MOMENT, nuty=True),
        Konfiguracja(katalog_wynikow=tmp_path),
        _MOMENT,
    )
    assert zrodlo.typ_zrodla is TypZrodla.PLIK_NUTY


@pytest.mark.parametrize("rozszerzenie", ["gp", "gpx"])
def test_nowsze_formaty_guitar_pro_konczą_sie_czytelnym_komunikatem(
    rozszerzenie: str, tmp_path: Path
) -> None:
    plik = tmp_path / f"tabulatura.{rozszerzenie}"
    plik.write_bytes(b"BCFZ\x00\x00")

    with pytest.raises(FormatNieobslugiwany) as informacja:
        waliduj_i_utworz_zrodlo(
            przyjmij_plik(plik, _MOMENT), Konfiguracja(katalog_wynikow=tmp_path), _MOMENT
        )
    assert "gp3" in informacja.value.komunikat
    assert "gp5" in informacja.value.komunikat


def test_zbyt_duzy_plik_nutowy_jest_pomijany_przekroczeniem_limitu(tmp_path: Path) -> None:
    plik = tmp_path / "wielka.gp5"
    plik.write_bytes(b"0" * (3 * 1024 * 1024))

    with pytest.raises(PrzekroczonoLimit):
        waliduj_i_utworz_zrodlo(
            przyjmij_plik(plik, _MOMENT),
            Konfiguracja(katalog_wynikow=tmp_path, bezpieczny_limit_mb=2),
            _MOMENT,
        )
