"""Testy odczytu plików Guitar Pro gp3, gp4 i gp5 do opisu partytury."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia
from gnb.music.guitarpro import czy_dostepna_biblioteka, przeczytaj_guitarpro

pytestmark = pytest.mark.usefixtures("wymaga_pyguitarpro")

_PLIKI_AKORDOWE = [
    ("tabulatura_akordy.gp3", "gp3"),
    ("tabulatura_akordy.gp4", "gp4"),
    ("tabulatura_akordy.gp5", "gp5"),
]


@pytest.mark.parametrize(("nazwa_pliku", "kod_formatu"), _PLIKI_AKORDOWE)
def test_pliki_akordowe_maja_osiem_taktow_i_wlasciwy_format(
    nazwa_pliku: str, kod_formatu: str
) -> None:
    opis = przeczytaj_guitarpro(Path("tests/dane", nazwa_pliku).read_bytes())
    assert opis.liczba_taktow == 8
    assert opis.liczba_taktow_przyblizona is False
    assert opis.tempo_bpm == 120
    assert opis.format_zrodlowy == kod_formatu
    assert opis.struktura_czesci


def test_plik_z_efektami_ma_czternascie_taktow_i_czyta_sie_bez_wyjatku() -> None:
    opis = przeczytaj_guitarpro(Path("tests/dane/tabulatura_efekty.gp5").read_bytes())
    assert opis.liczba_taktow == 14


def test_zmiana_metrum_w_pliku_z_efektami_daje_ostrzezenie() -> None:
    opis = przeczytaj_guitarpro(Path("tests/dane/tabulatura_efekty.gp5").read_bytes())
    assert any("zmienia się metrum" in ostrzezenie for ostrzezenie in opis.ostrzezenia_zmian)


def test_puste_pole_tytulu_daje_tytul_none() -> None:
    for nazwa_pliku, _ in _PLIKI_AKORDOWE:
        opis = przeczytaj_guitarpro(Path("tests/dane", nazwa_pliku).read_bytes())
        assert opis.tytul is None


def test_numer_instrumentu_general_midi_nie_jest_przesuniety() -> None:
    # Plik z efektami ma tracks[0].channel.instrument równe 24, pliki akordowe 25.
    # Przy przesunięciu indeksu o jeden obie nazwy byłyby błędne.
    efekty = przeczytaj_guitarpro(Path("tests/dane/tabulatura_efekty.gp5").read_bytes())
    akordy = przeczytaj_guitarpro(Path("tests/dane/tabulatura_akordy.gp5").read_bytes())
    assert any("nylon" in nazwa for nazwa in efekty.instrumenty)
    assert any("stalow" in nazwa for nazwa in akordy.instrumenty)


def test_wersja_zapisu_trafia_do_uwag_bez_parsowania_na_liczbe() -> None:
    opis = przeczytaj_guitarpro(Path("tests/dane/tabulatura_akordy.gp3").read_bytes())
    assert any("FICHIER GUITAR PRO" in uwaga for uwaga in opis.uwagi_odczytu)


def test_tonacja_z_wyliczenia_a_nie_przez_str() -> None:
    opis = przeczytaj_guitarpro(Path("tests/dane/tabulatura_akordy.gp5").read_bytes())
    assert opis.tonacja == "C-dur"


def test_uszkodzony_plik_konczy_sie_bledem_trwalym() -> None:
    with pytest.raises(BladTrwaly):
        przeczytaj_guitarpro(b"FICHIER GUITAR PRO v5.00" + b"\x00" * 20)


def test_brak_biblioteki_zglasza_brak_narzedzia(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    prawdziwy_import = builtins.__import__

    def blokuj(nazwa: str, *reszta: object, **nazwane: object) -> object:
        if nazwa == "guitarpro" or nazwa.startswith("guitarpro."):
            raise ImportError("test: guitarpro zablokowane")
        return prawdziwy_import(nazwa, *reszta, **nazwane)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", blokuj)
    assert czy_dostepna_biblioteka() is False
    with pytest.raises(BrakNarzedzia):
        przeczytaj_guitarpro(Path("tests/dane/tabulatura_akordy.gp5").read_bytes())
