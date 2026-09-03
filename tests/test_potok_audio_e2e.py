"""Testy end-to-end potoku dla źródeł będących nagraniami audio.

Test pełnej transkrypcji wymaga pobranego modelu i nosi marker ``wolne``.
Odrzucenie materiału muzycznego oraz pominięcie przy wyłączonej transkrypcji
działają bez modelu — pierwszy używa prawdziwego filtra mowy, drugi nie dotyka
nawet FFmpega.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import przyjmij_plik
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"
_MOMENT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 3, 12, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def test_wylaczona_transkrypcja_pomija_nagranie_w_potoku(tmp_path: Path) -> None:
    """Bez modelu i bez FFmpega: wyłączona transkrypcja daje status „pominiete”, nie „blad”."""
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "audio_mowa.wav", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path, transkrypcja_wlaczona=False),
        nazwa_projektu="Audio wyłączone",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert manifest["zrodla"][0]["status"] == "pominiete"
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "wyłączona" in raport


def test_material_muzyczny_jest_pomijany_w_potoku(
    wymaga_faster_whisper: None, wymaga_ffmpeg: None, tmp_path: Path
) -> None:
    """Nagranie muzyczne bez mowy: status „pominiete” i powód w raporcie, nigdy transkrypcja."""
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "audio_muzyka.mp3", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path),
        nazwa_projektu="Audio muzyka",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_przetworzonych == 0
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "niemowny" in raport


@pytest.mark.wolne
def test_nagranie_mowy_przechodzi_caly_potok_i_ma_naglowek_z_jezykiem(
    wymaga_model_whisper: None, wymaga_ffmpeg: None, tmp_path: Path
) -> None:
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "audio_mowa.wav", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path, transkrypcja_model="tiny"),
        nazwa_projektu="Audio mowa",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodlo = manifest["zrodla"][0]
    assert zrodlo["status"] == "spakowane"
    assert zrodlo["metadane"]["jezyk"]

    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 1
    tresc = pliki_txt[0].read_text(encoding="utf-8")
    assert "Typ źródła: nagranie" in tresc
    assert "Język:" in tresc
    assert "Długość:" in tresc


@pytest.mark.wolne
def test_dluzsze_nagranie_m4a_przechodzi_potok(
    wymaga_model_whisper: None, wymaga_ffmpeg: None, tmp_path: Path
) -> None:
    """Prawdziwe, dłuższe nagranie polskiej mowy w kontenerze M4A."""
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "transkrypcja.m4a", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path, transkrypcja_model="tiny"),
        nazwa_projektu="Audio m4a",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert pliki_txt and len(pliki_txt[0].read_text(encoding="utf-8")) > 200
