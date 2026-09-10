"""Testy wykrywania zainstalowanego programu Audiveris."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gnb.core.wyjatki import BrakNarzedzia
from gnb.music import audiveris


def test_sciezka_wskazana_do_istniejacego_pliku_jest_zwracana(tmp_path: Path) -> None:
    plik = tmp_path / "Audiveris.exe"
    plik.write_bytes(b"")
    assert audiveris.znajdz_audiveris(str(plik)) == plik


def test_sciezka_wskazana_do_nieistniejacego_pliku_zglasza_brak_narzedzia(
    tmp_path: Path,
) -> None:
    with pytest.raises(BrakNarzedzia):
        audiveris.znajdz_audiveris(str(tmp_path / "nie_ma.exe"))


def test_znane_podkatalogi_uzywaja_separatora_zrozumialego_na_kazdym_systemie() -> None:
    # Ukośnik wsteczny jest separatorem tylko na Windows. Na Linuksie „a\\b” to
    # jedna nazwa pliku, więc katalog docelowy nigdy nie zostaje odwiedzony,
    # a wykrywanie milczy. Sekcja 6 punkt 2 CLAUDE.md zakazuje ukośników
    # wpisanych na sztywno; poprawny zapis to ukośnik zwykły. Ten sam błąd
    # naprawiał pull request 26 dla MuseScore.
    for _zmienna, podkatalog in audiveris._ZNANE_PODKATALOGI_WINDOWS:
        assert "\\" not in podkatalog


def test_znajduje_audiverisa_w_znanym_podkatalogu_gdy_nie_ma_w_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _nazwa: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setattr(audiveris, "_DOMYSLNE_SCIEZKI_WINDOWS", ())
    plik = tmp_path / "Audiveris" / "Audiveris.exe"
    plik.parent.mkdir(parents=True)
    plik.write_bytes(b"")

    znaleziona = audiveris.znajdz_audiveris("")
    assert znaleziona == plik


def test_brak_wszedzie_zglasza_brak_narzedzia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _nazwa: None)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.setattr(audiveris, "_DOMYSLNE_SCIEZKI_WINDOWS", ())
    with pytest.raises(BrakNarzedzia):
        audiveris.znajdz_audiveris("")


def test_czy_dostepny_dla_nieistniejacej_sciezki_zwraca_falsz(tmp_path: Path) -> None:
    assert audiveris.czy_dostepny(str(tmp_path / "nie_ma.exe")) is False
