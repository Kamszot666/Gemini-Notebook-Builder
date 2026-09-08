"""Testy wykrywania zainstalowanego programu MuseScore."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gnb.core.wyjatki import BrakNarzedzia
from gnb.music import musescore


def test_sciezka_wskazana_do_istniejacego_pliku_jest_zwracana(tmp_path: Path) -> None:
    plik = tmp_path / "MuseScore4.exe"
    plik.write_bytes(b"")
    assert musescore.znajdz_musescore(str(plik)) == plik


def test_sciezka_wskazana_do_nieistniejacego_pliku_zglasza_brak_narzedzia(
    tmp_path: Path,
) -> None:
    with pytest.raises(BrakNarzedzia):
        musescore.znajdz_musescore(str(tmp_path / "nie_ma.exe"))


def test_znajduje_musescore_w_znanym_podkatalogu_gdy_nie_ma_w_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _nazwa: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setattr(musescore, "_DOMYSLNE_SCIEZKI_WINDOWS", ())
    plik = tmp_path / "MuseScore 4" / "bin" / "MuseScore4.exe"
    plik.parent.mkdir(parents=True)
    plik.write_bytes(b"")

    assert musescore.znajdz_musescore("") == plik


def test_brak_wszedzie_zglasza_brak_narzedzia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _nazwa: None)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.setattr(musescore, "_DOMYSLNE_SCIEZKI_WINDOWS", ())
    with pytest.raises(BrakNarzedzia):
        musescore.znajdz_musescore("")


def test_czy_dostepny_dla_nieistniejacej_sciezki_zwraca_falsz(tmp_path: Path) -> None:
    assert musescore.czy_dostepny(str(tmp_path / "nie_ma.exe")) is False
