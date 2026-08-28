"""Testy deterministycznej reguły wyboru między TXT a MD z sekcji ósmej CLAUDE.md."""

from __future__ import annotations

from pathlib import Path

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku
from gnb.extractors.markdown import EkstraktorMarkdown
from gnb.extractors.tekst import EkstraktorTekstu
from gnb.output import regula_md
from gnb.output.regula_md import OPIS_WARUNKU_TABELA

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_dokument_strukturalny_md_spelnia_co_najmniej_dwa_warunki_i_dostaje_md() -> None:
    tekst = (KATALOG_DANYCH / "dokument_strukturalny.md").read_text(encoding="utf-8")
    dokument = EkstraktorMarkdown().wyekstrahuj("plik_tekstowy-md", tekst)

    decyzja = regula_md.ocen(dokument)

    assert decyzja.generuj_md is True
    assert len(decyzja.spelnione_warunki) >= regula_md.MINIMALNA_LICZBA_SPELNIONYCH_WARUNKOW
    assert regula_md.OPIS_WARUNKU_TABELA in decyzja.spelnione_warunki
    assert decyzja.poziom_pewnosci_wystarczajacy is True


def test_tekst_plaski_nie_dostaje_md() -> None:
    tekst = (KATALOG_DANYCH / "tekst_plaski.txt").read_text(encoding="utf-8")
    dokument = EkstraktorTekstu().wyekstrahuj("plik_tekstowy-txt", tekst)

    decyzja = regula_md.ocen(dokument)

    assert decyzja.generuj_md is False
    assert decyzja.spelnione_warunki == ()
    assert decyzja.poziom_pewnosci_wystarczajacy is False


def test_bogata_struktura_ale_niski_poziom_pewnosci_nie_dostaje_md() -> None:
    tekst = (KATALOG_DANYCH / "dokument_strukturalny.md").read_text(encoding="utf-8")
    dokument = EkstraktorMarkdown().wyekstrahuj("plik_tekstowy-md", tekst)
    dokument.poziom_pewnosci_struktury = PoziomPewnosciStruktury.NISKI

    decyzja = regula_md.ocen(dokument)

    assert len(decyzja.spelnione_warunki) >= 2
    assert decyzja.poziom_pewnosci_wystarczajacy is False
    assert decyzja.generuj_md is False


def test_jeden_spelniony_warunek_to_za_malo() -> None:
    tekst = "# Tytuł\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n"
    dokument = EkstraktorMarkdown().wyekstrahuj("tekst_wklejony-md", tekst)

    decyzja = regula_md.ocen(dokument)

    assert decyzja.spelnione_warunki == (regula_md.OPIS_WARUNKU_TABELA,)
    assert decyzja.generuj_md is False


def test_tabela_o_wierszach_roznej_dlugosci_nie_zalicza_warunku() -> None:
    """Tabela, której nie da się zapisać wiernie, nie spełnia warunku trzeciego.

    Tabela Markdown ma stałą liczbę kolumn wyznaczoną przez nagłówek, więc wiersz
    o innej liczbie komórek albo straci nadmiarowe komórki, albo dostanie puste.
    Sekcja ósma CLAUDE.md wymaga tabeli dającej się zapisać bez utraty znaczenia.
    """
    dokument = DokumentWyekstrahowany(
        identyfikator_zrodla="zrodlo-1",
        tekst="",
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
        metoda_ekstrakcji="test",
        bloki=[
            BlokTresci(rodzaj=RodzajBloku.TABELA, poziom=0, tresc="A\tB\nc\td\te"),
        ],
    )

    decyzja = regula_md.ocen(dokument)

    assert OPIS_WARUNKU_TABELA not in decyzja.spelnione_warunki


def test_tabela_o_rownych_wierszach_zalicza_warunek() -> None:
    dokument = DokumentWyekstrahowany(
        identyfikator_zrodla="zrodlo-2",
        tekst="",
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
        metoda_ekstrakcji="test",
        bloki=[
            BlokTresci(rodzaj=RodzajBloku.TABELA, poziom=0, tresc="A\tB\nc\td"),
        ],
    )

    decyzja = regula_md.ocen(dokument)

    assert OPIS_WARUNKU_TABELA in decyzja.spelnione_warunki
