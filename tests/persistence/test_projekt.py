"""Testy układu katalogów projektu wynikowego."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.persistence.projekt import ustal_uklad, utworz_katalogi


def test_uklad_katalogow_powstaje_w_poprawnym_miejscu(tmp_path: Path) -> None:
    uklad = ustal_uklad(tmp_path, "Mój projekt")
    utworz_katalogi(uklad)

    assert uklad.katalog_projektu == tmp_path / "Mój projekt"
    for katalog in (
        uklad.materialy_zrodlowe,
        uklad.wyniki_posrednie,
        uklad.pliki_wynikowe,
        uklad.logi,
    ):
        assert katalog.is_dir()
    assert uklad.manifest_json.name == "manifest.json"
    assert uklad.checkpoint.name == "checkpoint.json"


def test_wlasny_katalog_projektu_jest_respektowany(tmp_path: Path) -> None:
    wlasny = tmp_path / "gdzie indziej" / "projekt"
    uklad = ustal_uklad(tmp_path, "Nazwa", wlasny_katalog_projektu=wlasny)
    assert uklad.katalog_projektu == wlasny


def test_nazwa_zarezerwowana_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly):
        ustal_uklad(tmp_path, "PRN")


def test_identyfikator_projektu_jest_stabilny(tmp_path: Path) -> None:
    pierwszy = ustal_uklad(tmp_path, "Powtarzalny")
    drugi = ustal_uklad(tmp_path, "Powtarzalny")
    assert pierwszy.identyfikator_projektu == drugi.identyfikator_projektu
