"""Testy rozkodowania nagrań audio przez podproces FFmpeg.

Testy rzeczywistego dekodowania pomijają się z czytelnym komunikatem, gdy w
środowisku nie ma FFmpega — służy do tego fikstura ``wymaga_ffmpeg``. Reszta,
w tym odnajdywanie narzędzia i obsługa jego braku, działa niezależnie od FFmpega.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from gnb.audio import dekodowanie
from gnb.audio.dekodowanie import (
    CZESTOTLIWOSC_PROBKOWANIA,
    czy_dostepny,
    dekoduj_do_fali,
    dlugosc_fali_sekundy,
    znajdz_ffmpeg,
)
from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_znajdz_ffmpeg_zglasza_brak_gdy_nie_ma_go_w_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak FFmpega w PATH kończy się `BrakNarzedzia`, a nie cichym zwróceniem czegokolwiek."""
    monkeypatch.setattr(dekodowanie.shutil, "which", lambda _nazwa: None)

    with pytest.raises(BrakNarzedzia, match="FFmpeg"):
        znajdz_ffmpeg()


def test_czy_dostepny_jest_falszem_bez_ffmpega(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dekodowanie.shutil, "which", lambda _nazwa: None)
    assert czy_dostepny() is False


def test_dekoduj_bez_ffmpega_zglasza_brak_narzedzia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dekodowanie.shutil, "which", lambda _nazwa: None)

    with pytest.raises(BrakNarzedzia):
        dekoduj_do_fali(b"cokolwiek")


def test_dekoduj_wav_zwraca_fale_16khz_mono_float32(wymaga_ffmpeg: None) -> None:
    bajty = (KATALOG_DANYCH / "audio_mowa.wav").read_bytes()

    fala = dekoduj_do_fali(bajty, identyfikator_zrodla="audio-1")

    assert fala.dtype == np.float32
    assert fala.ndim == 1
    # Plik audio_mowa.wav trwa około ośmiu sekund.
    dlugosc = dlugosc_fali_sekundy(fala)
    assert 6.0 < dlugosc < 12.0
    assert len(fala) == pytest.approx(dlugosc * CZESTOTLIWOSC_PROBKOWANIA, abs=1)


def test_dekoduj_m4a_dziala_mimo_naglowka_na_koncu_pliku(wymaga_ffmpeg: None) -> None:
    """Kontener M4A trzyma nagłówek na końcu, więc dekodowanie idzie z pliku, nie strumienia."""
    bajty = (KATALOG_DANYCH / "transkrypcja.m4a").read_bytes()

    fala = dekoduj_do_fali(bajty, identyfikator_zrodla="audio-2")

    assert dlugosc_fali_sekundy(fala) > 60.0


def test_dekoduj_uszkodzony_material_konczy_sie_bladem_trwalym(wymaga_ffmpeg: None) -> None:
    with pytest.raises(BladTrwaly):
        dekoduj_do_fali(b"to nie jest nagranie audio" * 100, identyfikator_zrodla="audio-3")
