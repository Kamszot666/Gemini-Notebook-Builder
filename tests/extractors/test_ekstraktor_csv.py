"""Testy ekstraktora plików CSV."""

from __future__ import annotations

from pathlib import Path

from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.extractors.plik_csv import EkstraktorCsv
from gnb.normalization.kodowanie import zdekoduj

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_wiersze_przecinkowe_daja_jeden_blok_tabeli() -> None:
    tekst = "imię,wiek,miasto\nAnna,30,Kraków\nJan,25,Poznań\n"
    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-1", tekst)

    assert len(dokument.bloki) == 1
    blok = dokument.bloki[0]
    assert blok.rodzaj is RodzajBloku.TABELA
    assert blok.tresc.split("\n") == [
        "imię\twiek\tmiasto",
        "Anna\t30\tKraków",
        "Jan\t25\tPoznań",
    ]
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.WYSOKI
    assert dokument.tytul is None


def test_ogranicznik_srednikowy_jest_rozpoznawany() -> None:
    tekst = "imię;wiek\nAnna;30\nJan;25\n"
    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-2", tekst)

    assert dokument.bloki[0].tresc.split("\n") == ["imię\twiek", "Anna\t30", "Jan\t25"]


def test_tekst_wynikowy_jest_tabela_markdown() -> None:
    tekst = "a,b\n1,2\n"
    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-3", tekst)

    assert dokument.tekst == "| a | b |\n| --- | --- |\n| 1 | 2 |"


def test_pusty_plik_daje_ostrzezenie_i_brak_blokow() -> None:
    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-4", "   \n  \n")

    assert dokument.bloki == []
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.ostrzezenia


def test_tabulator_wewnatrz_komorki_nie_rozbija_kolumn() -> None:
    tekst = 'a,b\n"jeden\tdwa",trzy\n'
    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-5", tekst)

    assert dokument.bloki[0].tresc.split("\n")[1] == "jeden dwa\ttrzy"


def test_obsluguje_wylacznie_format_csv_dla_pliku_dokumentu() -> None:
    ekstraktor = EkstraktorCsv()
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "csv") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "pdf") is False
    assert ekstraktor.obsluguje(TypZrodla.PLIK_TEKSTOWY, "csv") is False


def test_plik_testowy_ze_srednikiem_daje_jeden_blok_tabeli() -> None:
    dane = (KATALOG_DANYCH / "tabela_metod.csv").read_bytes()
    tekst, _ = zdekoduj(dane)
    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-6", tekst)

    assert len(dokument.bloki) == 1
    wiersze = dokument.bloki[0].tresc.split("\n")
    assert wiersze[0] == "metoda\tkoszt_obliczeniowy\twykrywa\tdomyslnie_wlaczona"
    assert len(wiersze) == 5


def test_pionowa_kreska_w_komorce_nie_rozbija_tabeli() -> None:
    """Kreska w treści komórki jest escapowana, więc nie tworzy dodatkowej kolumny.

    Pionowa kreska rozdziela komórki w zapisie tabeli Markdown. Komórka o treści
    zawierającej ten znak rozbijała dotąd strukturę całego wiersza.
    """
    tekst = "Nazwa;Opis\nMetoda A;wariant pierwszy | wariant drugi\n"

    dokument = EkstraktorCsv().wyekstrahuj("plik_dokument-40", tekst)

    wiersze = [wiersz for wiersz in dokument.tekst.split("\n") if wiersz.startswith("|")]
    wiersz_danych = wiersze[-1]
    assert r"wariant pierwszy \| wariant drugi" in wiersz_danych
    # Wiersz ma mieć dokładnie dwie komórki, tak jak nagłówek, a nie trzy.
    assert wiersz_danych.count(" | ") == 1
