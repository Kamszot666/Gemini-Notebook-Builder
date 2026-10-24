"""Test end-to-end: strona obrócona pod statywem jest odczytana, a obrót widać w pliku grupy."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import przyjmij_plik
from gnb.potok import przetworz_projekt
from tests.images.test_odczyt_pewnosci import _strona_druku

_MOMENT = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def _zegar():
    stan = {"teraz": _MOMENT}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def test_obrocona_strona_jest_czytelna_a_obrot_zapisany_w_metadanych_i_pliku_md(
    wymaga_ocr_pol: None, tmp_path: Path
) -> None:
    from gnb.images.tesseract import dostepne_jezyki

    if "osd" not in dostepne_jezyki():
        pytest.skip("Tesseract nie ma danych orientacji osd.traineddata.")
    folder = tmp_path / "zdjecia"
    folder.mkdir()
    prosta = _strona_druku().convert("RGB")
    inna = _strona_druku(ziarno=8).convert("RGB")
    prosta.save(folder / "k_1.png")
    # Strona do góry nogami, jak kartka położona pod statywem odwrotnie.
    inna.rotate(180, expand=True, fillcolor=(255, 255, 255)).save(folder / "k_2.png")

    wynik = przetworz_projekt(
        [
            przyjmij_plik(folder / "k_1.png", _MOMENT, grupa="akta"),
            przyjmij_plik(folder / "k_2.png", _MOMENT, grupa="akta"),
        ],
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki", grupy_obrazow_jako_skany=True),
        nazwa_projektu="Akta obrot",
        zegar=_zegar(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    obroty = {zrodlo["metadane"]["obrot_strony_stopnie"] for zrodlo in manifest["zrodla"]}
    assert obroty == {"0", "180"}
    assert all(zrodlo["metadane"]["nieczytelne_dla_ocr"] == "nie" for zrodlo in manifest["zrodla"])

    tresc = next((wynik.katalog_projektu / "pliki_wynikowe").glob("*.md")).read_text(
        encoding="utf-8"
    )
    sekcja_1, sekcja_2 = tresc.split("## k_2.png")
    assert "- Obrót strony przed odczytem: 0 stopni" in sekcja_1
    assert "- Obrót strony przed odczytem: 180 stopni" in sekcja_2
    assert "wyrok" in sekcja_2.lower()
