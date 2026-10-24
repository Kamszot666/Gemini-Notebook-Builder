"""Testy konwencji plików z dopiskami odręcznymi obok zdjęć skanów."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gnb.ingestion.dopiski import (
    czy_plik_dopiskow,
    dopiski_bez_skanu,
    odfiltruj_pliki_dopiskow,
    wczytaj_dopiski,
    znajdz_plik_dopiskow,
)
from gnb.ingestion.wejscie import przyjmij_plik

_MOMENT = datetime(2026, 10, 24, tzinfo=UTC)


@pytest.mark.parametrize(
    ("nazwa", "oczekiwane"),
    [
        ("017_dopiski.txt", True),
        ("017_DOPISKI.MD", True),
        ("017_dopiski.docx", False),
        ("_dopiski.txt", False),
        ("017.txt", False),
        ("dopiski_017.txt", False),
    ],
)
def test_rozpoznaje_nazwy_plikow_dopiskow(nazwa: str, oczekiwane: bool) -> None:
    assert czy_plik_dopiskow(Path(nazwa)) is oczekiwane


def test_znajduje_plik_dopiskow_obok_zdjecia_bez_wzgledu_na_wielkosc_liter(tmp_path: Path) -> None:
    zdjecie = tmp_path / "017.jpg"
    zdjecie.write_bytes(b"x")
    assert znajdz_plik_dopiskow(zdjecie) is None
    (tmp_path / "017_Dopiski.MD").write_text("md", encoding="utf-8")
    assert znajdz_plik_dopiskow(zdjecie) == tmp_path / "017_Dopiski.MD"
    (tmp_path / "017_dopiski.txt").write_text("txt", encoding="utf-8")
    # Plik .txt ma pierwszeństwo przed .md.
    assert znajdz_plik_dopiskow(zdjecie) == tmp_path / "017_dopiski.txt"
    # Dopiski innego zdjęcia nie pasują.
    assert znajdz_plik_dopiskow(tmp_path / "018.jpg") is None


def test_odczytuje_utf8_z_bom_z_notatnika_i_normalizuje_konce_wierszy(tmp_path: Path) -> None:
    plik = tmp_path / "1_dopiski.txt"
    plik.write_bytes("﻿Pierwszy wiersz\r\nDrugi ąę\r\n\r\n".encode())
    assert wczytaj_dopiski(plik) == "Pierwszy wiersz\nDrugi ąę"


def test_odczytuje_dopiski_zapisane_w_windows_1250(tmp_path: Path) -> None:
    plik = tmp_path / "1_dopiski.txt"
    plik.write_bytes("Zażółć gęślą jaźń. Dopisek ołówkiem przy marginesie.".encode("cp1250"))
    assert "Zażółć gęślą jaźń" in wczytaj_dopiski(plik)


def test_odfiltrowuje_pliki_dopiskow_z_wejsc_i_wykrywa_osierocone(tmp_path: Path) -> None:
    for nazwa in ("1.png", "1_dopiski.txt", "2_dopiski.md", "notatka.txt"):
        (tmp_path / nazwa).write_bytes(b"x")
    pozycje = [
        przyjmij_plik(tmp_path / nazwa, _MOMENT)
        for nazwa in ("1.png", "1_dopiski.txt", "2_dopiski.md", "notatka.txt")
    ]
    pozostale, dopiski = odfiltruj_pliki_dopiskow(pozycje)
    assert [Path(pozycja.wejscie.wartosc).name for pozycja in pozostale] == [
        "1.png",
        "notatka.txt",
    ]
    assert sorted(plik.name for plik in dopiski) == ["1_dopiski.txt", "2_dopiski.md"]
    # Zdjęcie 2 nie istnieje, więc tylko jego dopiski są osierocone.
    assert [plik.name for plik in dopiski_bez_skanu(dopiski)] == ["2_dopiski.md"]
