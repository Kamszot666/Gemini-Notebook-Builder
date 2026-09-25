"""Testy ekstraktora RTF, ekstraktora TSV oraz plików tekstu prostego."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.plik_csv import EkstraktorCsv, EkstraktorTsv
from gnb.extractors.plik_rtf import EkstraktorRtf
from gnb.extractors.tekst import EkstraktorTekstu
from gnb.ingestion.wejscie import FORMATY_PLIKOW, typ_zrodla_dla_pliku

DANE = Path(__file__).resolve().parents[1] / "dane" / "formaty"

_RTF_POLSKI = (
    rb"{\rtf1\ansi\ansicpg1250\deff0 Za\'bf\'f3\'b3\'e6 g\'ea\'9cl\'b9 ja\'9f\'f1."
    rb"\par Drugi akapit.\par}"
)


# --- RTF -----------------------------------------------------------------------


def test_rtf_z_libreoffice_daje_tekst_akapitami() -> None:
    dokument = EkstraktorRtf().wyekstrahuj("id", (DANE / "dokument.rtf").read_bytes())

    assert "Zażółć gęślą jaźń." in dokument.tekst
    assert "Ostatni akapit po tabeli." in dokument.tekst
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.bloki == []
    # Tabela jest spłaszczona przez bibliotekę, więc ekstraktor mówi o tym wprost.
    assert any("zawiera tabele" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)


def test_rtf_odczytuje_polskie_znaki_ze_strony_kodowej_zapisanej_w_pliku() -> None:
    dokument = EkstraktorRtf().wyekstrahuj("id", _RTF_POLSKI)

    assert dokument.tekst == "Zażółć gęślą jaźń.\n\nDrugi akapit."
    assert dokument.tytul == "Zażółć gęślą jaźń."
    assert dokument.ostrzezenia == []


def test_rtf_z_obrazem_i_obiektem_ostrzega() -> None:
    plik = rb"{\rtf1\ansi Tekst {\pict\pngblip 89504e47}{\object\objemb dane}\par}"

    ostrzezenia = EkstraktorRtf().wyekstrahuj("id", plik).ostrzezenia

    assert any("obrazy (1)" in ostrzezenie for ostrzezenie in ostrzezenia)
    assert any("obiekty osadzone (1)" in ostrzezenie for ostrzezenie in ostrzezenia)


def test_plik_niebedacy_rtf_zglasza_blad_trwaly() -> None:
    with pytest.raises(BladTrwaly, match="nie jest poprawnym dokumentem RTF"):
        EkstraktorRtf().wyekstrahuj("id", b"zwykly tekst")


def test_rtf_obsluguje_tylko_rtf() -> None:
    ekstraktor = EkstraktorRtf()

    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "rtf")
    assert not ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "doc")


# --- TSV -------------------------------------------------------------------------


def test_tsv_rozdziela_po_tabulatorze_mimo_przecinkow_w_komorkach() -> None:
    tekst = "Imię\tOpis\nAnna\ta, b, c\nJan\td, e, f\n"

    dokument = EkstraktorTsv().wyekstrahuj("id", tekst)

    assert "| Imię | Opis |" in dokument.tekst
    assert "| Anna | a, b, c |" in dokument.tekst
    assert dokument.metadane["liczba_kolumn"] == "2"


def test_tsv_i_csv_obsluguja_rozne_formaty() -> None:
    assert EkstraktorTsv().obsluguje(TypZrodla.PLIK_DOKUMENT, "tsv")
    assert not EkstraktorTsv().obsluguje(TypZrodla.PLIK_DOKUMENT, "csv")
    assert EkstraktorCsv().obsluguje(TypZrodla.PLIK_DOKUMENT, "csv")
    assert not EkstraktorCsv().obsluguje(TypZrodla.PLIK_DOKUMENT, "tsv")


def test_tsv_pusty_daje_ostrzezenie() -> None:
    dokument = EkstraktorTsv().wyekstrahuj("id", "   \n")

    assert dokument.tekst == ""
    assert dokument.ostrzezenia


# --- tekst prosty -------------------------------------------------------------------


@pytest.mark.parametrize(
    "format_zrodla", ["json", "xml", "yaml", "yml", "toml", "ini", "cfg", "log"]
)
def test_pliki_tekstu_prostego_maja_typ_pliku_tekstowego_i_ekstraktor_tekstu(
    format_zrodla: str,
) -> None:
    assert format_zrodla in FORMATY_PLIKOW
    assert typ_zrodla_dla_pliku(format_zrodla) is TypZrodla.PLIK_TEKSTOWY
    assert EkstraktorTekstu().obsluguje(TypZrodla.PLIK_TEKSTOWY, format_zrodla)


def test_json_zostaje_zwyklym_tekstem_bez_tytulu_z_pierwszego_wiersza() -> None:
    tresc = '{\n  "a": 1,\n  "b": [1, 2]\n}\n'

    dokument = EkstraktorTekstu().wyekstrahuj("id", tresc)

    assert dokument.tekst == tresc
    assert dokument.bloki == []
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI


def test_plik_env_nie_jest_obslugiwany_bo_niesie_sekrety() -> None:
    assert "env" not in FORMATY_PLIKOW


def test_tsv_nie_zgaduje_ogranicznika_tylko_uzywa_tabulatora() -> None:
    """Dla tego tekstu rozpoznawanie ogranicznika CSV wybrałoby przecinek, a TSV ma tabulator."""
    tekst = "a,b\tc\n1,2\t3\n4,5\t6\n7,8\t9\n"

    dokument = EkstraktorTsv().wyekstrahuj("id", tekst)

    assert "| a,b | c |" in dokument.tekst
    assert dokument.metadane["liczba_kolumn"] == "2"
