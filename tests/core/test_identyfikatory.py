"""Testy deterministycznych identyfikatorów źródeł i sum kontrolnych."""

from __future__ import annotations

from pathlib import Path

from gnb.core.identyfikatory import (
    DLUGOSC_SKROTU_W_IDENTYFIKATORZE,
    identyfikator_zrodla,
    suma_kontrolna_pliku,
    suma_kontrolna_tekstu_wklejonego,
)
from gnb.core.stale import TypZrodla


def test_suma_kontrolna_tekstu_jest_powtarzalna() -> None:
    tekst = "Powtarzalny tekst źródła."
    assert suma_kontrolna_tekstu_wklejonego(tekst) == suma_kontrolna_tekstu_wklejonego(tekst)


def test_suma_kontrolna_tekstu_ignoruje_wiodacy_znak_bom() -> None:
    bez_bom = "Treść wklejona."
    z_bom = "\ufeffTreść wklejona."
    assert suma_kontrolna_tekstu_wklejonego(bez_bom) == suma_kontrolna_tekstu_wklejonego(z_bom)


def test_rozny_tekst_daje_rozne_sumy_kontrolne() -> None:
    assert suma_kontrolna_tekstu_wklejonego("A") != suma_kontrolna_tekstu_wklejonego("B")


def test_suma_kontrolna_pliku_zalezy_od_zawartosci(tmp_path: Path) -> None:
    plik_a = tmp_path / "a.txt"
    plik_b = tmp_path / "b.txt"
    plik_a.write_text("taka sama treść", encoding="utf-8")
    plik_b.write_text("taka sama treść", encoding="utf-8")
    assert suma_kontrolna_pliku(plik_a) == suma_kontrolna_pliku(plik_b)

    plik_b.write_text("inna treść", encoding="utf-8")
    assert suma_kontrolna_pliku(plik_a) != suma_kontrolna_pliku(plik_b)


def test_identyfikator_zrodla_ma_prefiks_typu_i_skrocona_sume() -> None:
    suma = "0123456789abcdef" * 4
    identyfikator = identyfikator_zrodla(TypZrodla.TEKST_WKLEJONY, suma)
    prefiks, skrot = identyfikator.split("-", 1)
    assert prefiks == TypZrodla.TEKST_WKLEJONY.value
    assert skrot == suma[:DLUGOSC_SKROTU_W_IDENTYFIKATORZE]


def test_identyfikator_zalezy_od_typu_zrodla() -> None:
    suma = suma_kontrolna_tekstu_wklejonego("wspólna treść")
    identyfikator_tekstu = identyfikator_zrodla(TypZrodla.TEKST_WKLEJONY, suma)
    identyfikator_pliku = identyfikator_zrodla(TypZrodla.PLIK_TEKSTOWY, suma)
    assert identyfikator_tekstu != identyfikator_pliku


def test_ten_sam_tekst_wklejony_dwa_razy_daje_ten_sam_identyfikator() -> None:
    suma = suma_kontrolna_tekstu_wklejonego("dwa razy to samo")
    pierwszy = identyfikator_zrodla(TypZrodla.TEKST_WKLEJONY, suma)
    drugi = identyfikator_zrodla(TypZrodla.TEKST_WKLEJONY, suma)
    assert pierwszy == drugi
