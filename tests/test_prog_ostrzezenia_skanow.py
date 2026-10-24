"""Testy progu ostrzeżenia o niskiej pewności odczytu skanów: konfiguracja i raport."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.konfiguracja import wczytaj_konfiguracje
from gnb.core.wyjatki import BladTrwaly
from gnb.core.zapis_konfiguracji import zapisz_ustawienia
from gnb.output.raport import zbuduj_raport
from gnb.persistence.checkpoint import WERSJA_SCHEMATU, Checkpoint, StanZrodla
from gnb.potok import _zbuduj_podsumowanie


def test_prog_ostrzezenia_ma_domyslnie_75_i_czyta_sie_z_pliku_i_srodowiska(tmp_path: Path) -> None:
    assert (
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={}).ocr_prog_ostrzezenia == 75.0
    )

    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("ocr_prog_ostrzezenia = 66.5\n", encoding="utf-8")
    assert wczytaj_konfiguracje(plik, srodowisko={}).ocr_prog_ostrzezenia == 66.5

    z_srodowiska = wczytaj_konfiguracje(plik, srodowisko={"GNB_OCR_PROG_OSTRZEZENIA": "90"})
    assert z_srodowiska.ocr_prog_ostrzezenia == 90.0


@pytest.mark.parametrize("wartosc", ["-1", "101", "abc"])
def test_niepoprawny_prog_ostrzezenia_konczy_sie_bledem(tmp_path: Path, wartosc: str) -> None:
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml", srodowisko={"GNB_OCR_PROG_OSTRZEZENIA": wartosc}
        )


def test_prog_ostrzezenia_nizszy_niz_prog_nieczytelnosci_to_blad_z_nazwami_obu_ustawien(
    tmp_path: Path,
) -> None:
    srodowisko = {"GNB_OCR_PROG_PEWNOSCI": "60", "GNB_OCR_PROG_OSTRZEZENIA": "40"}
    with pytest.raises(BladTrwaly) as blad:
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko=srodowisko)
    assert "ocr_prog_ostrzezenia" in blad.value.komunikat
    assert "ocr_prog_pewnosci" in blad.value.komunikat

    # Równe progi są dozwolone.
    srodowisko["GNB_OCR_PROG_OSTRZEZENIA"] = "60"
    assert wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko=srodowisko)


def test_zapis_z_formularza_odrzuca_prog_ostrzezenia_nizszy_niz_prog_nieczytelnosci(
    tmp_path: Path,
) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("ocr_prog_pewnosci = 50\n", encoding="utf-8")
    przed = plik.read_text(encoding="utf-8")

    with pytest.raises(BladTrwaly, match="ocr_prog_ostrzezenia"):
        zapisz_ustawienia(plik, {"ocr_prog_ostrzezenia": 30})

    assert plik.read_text(encoding="utf-8") == przed
    zapisz_ustawienia(plik, {"ocr_prog_ostrzezenia": 80})
    assert wczytaj_konfiguracje(plik, srodowisko={}).ocr_prog_ostrzezenia == 80.0


def _checkpoint_ze_skanem(pewnosc: str) -> Checkpoint:
    stan = StanZrodla(
        identyfikator="obraz-1",
        typ="plik_obraz",
        pochodzenie="017.jpg",
        checksum="abc",
        format_zrodla="jpg",
        status="spakowane",
        metadane={
            "srednia_pewnosc_ocr": pewnosc,
            "nieczytelne_dla_ocr": "nie",
            "ocena_ocr": "poprawna",
        },
        naglowek_metadanych="Plik: 017.jpg",
    )
    return Checkpoint(
        wersja_schematu=WERSJA_SCHEMATU,
        identyfikator_projektu="p",
        nazwa_projektu="p",
        katalog_projektu="k",
        konfiguracja={},
        czas_ostatniej_zmiany="2026-10-24T12:00:00+00:00",
        zrodla={"obraz-1": stan},
    )


def _raport(pewnosc: str, prog: float) -> str:
    podsumowanie = _zbuduj_podsumowanie(
        checkpoint=_checkpoint_ze_skanem(pewnosc),
        limit_zrodel=100,
        czas_pracy_sekundy=None,
        prog_ostrzezenia_skanow=prog,
    )
    return zbuduj_raport("p", podsumowanie)


def test_prog_ostrzezenia_decyduje_o_sekcji_raportu_ze_skanami_o_niskiej_pewnosci() -> None:
    przy_75 = _raport("70.0", 75.0)
    assert "Skany z niską pewnością odczytu, liczba: 1" in przy_75
    assert "Plik: 017.jpg" in przy_75

    przy_65 = _raport("70.0", 65.0)
    assert "Skany z niską pewnością odczytu" not in przy_65

    # Wartość równa progowi nie jest poniżej progu.
    assert "Skany z niską pewnością odczytu" not in _raport("75.0", 75.0)
