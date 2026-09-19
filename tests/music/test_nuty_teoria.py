"""Testy nazywania dźwięków i wartości rytmicznych."""

from __future__ import annotations

from gnb.music.nuty_teoria import (
    litera_dzwieku_z_midi,
    nazwa_dzwieku_z_midi,
    nazwa_wartosci_rytmicznej,
)


def test_nazwa_dzwieku_z_midi_srodkowe_c() -> None:
    assert nazwa_dzwieku_z_midi(60) == "C4"


def test_nazwa_dzwieku_z_midi_struny_basu_standardowego() -> None:
    assert nazwa_dzwieku_z_midi(28) == "E1"
    assert nazwa_dzwieku_z_midi(33) == "A1"
    assert nazwa_dzwieku_z_midi(38) == "D2"
    assert nazwa_dzwieku_z_midi(43) == "G2"


def test_nazwa_dzwieku_z_midi_uzywa_krzyzykow_i_polskiego_h() -> None:
    assert nazwa_dzwieku_z_midi(61) == "Cis4"
    assert nazwa_dzwieku_z_midi(59) == "H3"


def test_litera_dzwieku_bez_oktawy() -> None:
    assert litera_dzwieku_z_midi(28) == "E"
    assert litera_dzwieku_z_midi(40) == "E"


def test_nazwa_wartosci_rytmicznej_znane_wartosci() -> None:
    assert nazwa_wartosci_rytmicznej(1) == "cała nuta"
    assert nazwa_wartosci_rytmicznej(4) == "ćwierćnuta"
    assert nazwa_wartosci_rytmicznej(16) == "szesnastka"


def test_nazwa_wartosci_rytmicznej_z_kropka() -> None:
    assert nazwa_wartosci_rytmicznej(4, kropka=True) == "ćwierćnuta z kropką"


def test_nazwa_wartosci_rytmicznej_nierozpoznana_nie_rzuca_wyjatku() -> None:
    assert nazwa_wartosci_rytmicznej(3) == "jedna 3-a"
