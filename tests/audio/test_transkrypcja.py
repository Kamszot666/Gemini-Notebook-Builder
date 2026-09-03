"""Testy warstwy transkrypcji: ustawienia, strażnik urządzenia i atrapa PyAV.

Rzeczywista transkrypcja wymaga pobranego modelu, więc jej test pomija się bez
niego przez fiksturę ``wymaga_model_whisper`` i nosi marker ``wolne``. Reszta,
w tym strażnik atrapy modułu ``av`` i dobór liczby wątków, działa bez modelu.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from gnb.audio import transkrypcja
from gnb.audio.transkrypcja import (
    _RDZENIE_ZOSTAWIONE_WOLNE,
    SegmentTranskrypcji,
    UstawieniaTranskrypcji,
    powod_atrapy_av,
)
from gnb.core.konfiguracja import Konfiguracja
from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_ustawienia_z_konfiguracji_biora_pola_transkrypcji() -> None:
    ustawienia = UstawieniaTranskrypcji.z_konfiguracji(
        Konfiguracja(transkrypcja_model="small", transkrypcja_prog_vad=0.4)
    )

    assert ustawienia.model == "small"
    assert ustawienia.jezyk == "pl"
    assert ustawienia.urzadzenie == "procesor"
    assert ustawienia.typ_obliczen == "int8"
    assert ustawienia.prog_vad == pytest.approx(0.4)


def test_ustawienia_z_konfiguracji_odrzucaja_karte_graficzna() -> None:
    """Decyzja trzecia etapu dziewiątego: karta graficzna to jawny błąd, nie cicha podmiana.

    Test czerwieni się, gdyby wybór urządzenia zaczął po cichu wracać do procesora
    zamiast zgłaszać, że ta ścieżka nie jest obsługiwana.
    """
    with pytest.raises(BladTrwaly, match="procesor"):
        UstawieniaTranskrypcji.z_konfiguracji(
            Konfiguracja(transkrypcja_urzadzenie="karta_graficzna")
        )


def test_efektywna_liczba_watkow_zostawia_jeden_rdzen_wolny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Domyślny dobór wątków transkrypcji nie zajmuje wszystkich rdzeni.

    Powód jest dostępnościowy: przy pełnym obciążeniu wszystkich rdzeni synteza
    mowy czytnika ekranu się zacina, a użytkownik właśnie wtedy słucha komunikatów
    o postępie. Test czerwieni się, gdyby ktoś „zoptymalizował” dobór z powrotem
    do pełnej liczby rdzeni. To samo sprawdzenie istnieje dla procesów OCR.
    """
    monkeypatch.setattr(transkrypcja.os, "cpu_count", lambda: 6)
    assert (
        UstawieniaTranskrypcji(liczba_watkow=0).efektywna_liczba_watkow
        == 6 - _RDZENIE_ZOSTAWIONE_WOLNE
    )

    monkeypatch.setattr(transkrypcja.os, "cpu_count", lambda: 1)
    assert UstawieniaTranskrypcji(liczba_watkow=0).efektywna_liczba_watkow == 1

    monkeypatch.setattr(transkrypcja.os, "cpu_count", lambda: None)
    assert UstawieniaTranskrypcji(liczba_watkow=0).efektywna_liczba_watkow == 1

    monkeypatch.setattr(transkrypcja.os, "cpu_count", lambda: 12)
    assert UstawieniaTranskrypcji(liczba_watkow=5).efektywna_liczba_watkow == 5


def test_segment_niepewny_gdy_niskie_prawdopodobienstwo_albo_brak_mowy() -> None:
    pewny = SegmentTranskrypcji(0.0, 3.0, "wyraźny fragment", -0.3, 0.02)
    slaby = SegmentTranskrypcji(0.0, 3.0, "fragment", -2.4, 0.02)
    bez_mowy = SegmentTranskrypcji(0.0, 3.0, "fragment", -0.3, 0.85)

    assert pewny.czy_niepewny is False
    assert slaby.czy_niepewny is True
    assert bez_mowy.czy_niepewny is True


class _BlokadaImportu:
    """Znajdywacz w sys.meta_path, który blokuje wskazane moduły błędem importu.

    W Pythonie 3.12 stary interfejs ``find_module`` i ``load_module`` jest
    ignorowany, więc symulacja braku modułu musi implementować ``find_spec``.
    """

    def __init__(self, blokowane: tuple[str, ...]) -> None:
        self._blokowane = blokowane

    def find_spec(self, nazwa: str, sciezka: object = None, cel: object = None) -> None:
        if nazwa in self._blokowane or any(
            nazwa.startswith(f"{prefiks}.") for prefiks in self._blokowane
        ):
            raise ImportError(f"Moduł {nazwa} zablokowany w teście (symulacja Smart App Control).")
        return None


@pytest.fixture
def bez_pyav(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Symuluje maszynę, na której PyAV jest zablokowany przez kontrolę aplikacji."""
    transkrypcja._faster_whisper.cache_clear()
    for nazwa in list(sys.modules):
        if (
            nazwa == "av"
            or nazwa.startswith("av.")
            or nazwa == "faster_whisper"
            or nazwa.startswith("faster_whisper.")
        ):
            monkeypatch.delitem(sys.modules, nazwa, raising=False)
    monkeypatch.setattr(transkrypcja, "_powod_atrapy_av", None)
    monkeypatch.setattr(sys, "meta_path", [_BlokadaImportu(("av",)), *sys.meta_path])
    yield
    transkrypcja._faster_whisper.cache_clear()


def test_blokada_pyav_nie_zatrzymuje_importu_warstwy_transkrypcji(
    bez_pyav: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Zablokowany PyAV nie może wywalić importu faster-whisper: wstawiamy atrapę.

    Test czerwieni się, gdyby strażnik przestał wstawiać atrapę albo przestał
    zapisywać powód: wtedy na komputerze użytkownika cała ścieżka audio padałaby
    przy imporcie.
    """
    try:
        with caplog.at_level(logging.WARNING, logger="gnb.audio.transkrypcja"):
            modul = transkrypcja._faster_whisper()
    except BrakNarzedzia:
        pytest.skip("faster-whisper nie jest zainstalowany, nie ma czego chronić.")

    assert isinstance(modul, ModuleType)
    assert modul.__name__ == "faster_whisper"
    assert "av" in sys.modules
    assert powod_atrapy_av() is not None
    assert any("atrap" in rekord.message.lower() for rekord in caplog.records)


def test_blokada_calego_faster_whisper_daje_brak_narzedzia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gdy nie ma nawet samej biblioteki, warstwa zgłasza `BrakNarzedzia`, nie wyjątek importu."""
    transkrypcja._faster_whisper.cache_clear()
    for nazwa in list(sys.modules):
        if nazwa == "faster_whisper" or nazwa.startswith("faster_whisper."):
            monkeypatch.delitem(sys.modules, nazwa, raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BlokadaImportu(("faster_whisper",)), *sys.meta_path])
    try:
        with pytest.raises(BrakNarzedzia):
            transkrypcja._faster_whisper()
    finally:
        transkrypcja._faster_whisper.cache_clear()

    assert transkrypcja.czy_dostepna_biblioteka() in (True, False)


def test_model_dostepny_lokalnie_falsz_dla_nieistniejacego_modelu(
    wymaga_faster_whisper: None,
) -> None:
    assert transkrypcja.model_dostepny_lokalnie("model-ktorego-nie-ma", "int8") is False


@pytest.mark.wolne
def test_transkrybuj_przepisuje_polska_mowe(
    wymaga_model_whisper: None, wymaga_ffmpeg: None
) -> None:
    from gnb.audio.dekodowanie import dekoduj_do_fali

    fala = dekoduj_do_fali((KATALOG_DANYCH / "audio_mowa.wav").read_bytes())
    postep: list[tuple[int, int]] = []

    wynik = transkrypcja.transkrybuj(
        fala,
        UstawieniaTranskrypcji(model="tiny"),
        przy_postepie=lambda a, b: postep.append((a, b)),
    )

    assert wynik.segmenty
    laczny_tekst = " ".join(segment.tekst for segment in wynik.segmenty).lower()
    assert any(slowo in laczny_tekst for slowo in ("nagranie", "testowe", "mowy", "polsku"))
    assert wynik.dlugosc_nagrania_sekundy > 5.0
    assert postep and postep[-1][0] <= postep[-1][1]
