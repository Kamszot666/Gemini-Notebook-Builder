"""Testy odwzorowania numerów General MIDI na polskie nazwy instrumentów."""

from __future__ import annotations

from gnb.music.instrumenty_gm import (
    INSTRUMENTY_GM,
    NAZWA_ZESTAWU_PERKUSYJNEGO,
    nazwa_instrumentu,
    nazwa_klawisza_perkusji,
)


def test_tablica_ma_dokladnie_sto_dwadziescia_osiem_wpisow_bez_luk() -> None:
    assert set(INSTRUMENTY_GM) == set(range(128))
    assert all(nazwa.strip() for nazwa in INSTRUMENTY_GM.values())


def test_numery_gitary_akustycznej_nie_sa_przesuniete_o_jeden() -> None:
    # Pułapka priorytetu pierwszego: numer programu w pliku jest liczony od zera,
    # a publikowana specyfikacja General MIDI od jedynki. Przy przesunięciu o jeden
    # numer 24 dałby gitarę stalową zamiast nylonowej, bez żadnego widocznego objawu.
    assert "nylon" in nazwa_instrumentu(24)
    assert "stalow" in nazwa_instrumentu(25)


def test_numer_spoza_zakresu_daje_opis_zastepczy_a_nie_wyjatek() -> None:
    assert nazwa_instrumentu(200) == "instrument nr 200"
    assert nazwa_instrumentu(-1) == "instrument nr -1"


def test_kanal_perkusyjny_zawsze_daje_zestaw_perkusyjny() -> None:
    assert nazwa_instrumentu(0, perkusja=True) == NAZWA_ZESTAWU_PERKUSYJNEGO
    assert nazwa_instrumentu(48, perkusja=True) == NAZWA_ZESTAWU_PERKUSYJNEGO


def test_nazwa_klawisza_perkusji_z_mapy_i_spoza_mapy() -> None:
    assert nazwa_klawisza_perkusji(38) == "werbel akustyczny"
    assert nazwa_klawisza_perkusji(200) == "element perkusji nr 200"
