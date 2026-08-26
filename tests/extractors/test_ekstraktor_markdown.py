"""Testy ekstraktora Markdown, w tym rozpoznawania tabel GFM."""

from __future__ import annotations

from pathlib import Path

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.extractors.bazowy import domyslny_rejestr
from gnb.extractors.markdown import EkstraktorMarkdown

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def _wyekstrahuj_dokument_strukturalny() -> DokumentWyekstrahowany:
    tekst = (KATALOG_DANYCH / "dokument_strukturalny.md").read_text(encoding="utf-8")
    return EkstraktorMarkdown().wyekstrahuj("plik_tekstowy-md", tekst)


def test_dokument_md_ma_wysoki_poziom_pewnosci() -> None:
    dokument = _wyekstrahuj_dokument_strukturalny()
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.WYSOKI


def test_naglowki_maja_rozpoznana_hierarchie() -> None:
    dokument = _wyekstrahuj_dokument_strukturalny()
    naglowki = [blok for blok in dokument.bloki if blok.rodzaj is RodzajBloku.NAGLOWEK]
    poziomy = sorted({blok.poziom for blok in naglowki})
    assert len(naglowki) >= 3
    assert poziomy == [1, 2, 3]


def test_listy_maja_policzone_elementy() -> None:
    dokument = _wyekstrahuj_dokument_strukturalny()
    listy = [blok for blok in dokument.bloki if blok.rodzaj is RodzajBloku.LISTA]
    assert len(listy) == 2
    assert all(len(lista.tresc.split("\n")) == 3 for lista in listy)


def test_tabela_jest_rozpoznana_jako_blok_tabela() -> None:
    dokument = _wyekstrahuj_dokument_strukturalny()
    tabele = [blok for blok in dokument.bloki if blok.rodzaj is RodzajBloku.TABELA]
    assert len(tabele) == 1
    assert "Metoda" in tabele[0].tresc
    assert "MinHash" in tabele[0].tresc


def test_blok_kodu_i_cytat_sa_rozpoznawane() -> None:
    tekst = "# Tytuł\n\n> To jest cytat blokowy.\n\n```python\nprint('kod')\n```\n"
    dokument = EkstraktorMarkdown().wyekstrahuj("tekst_wklejony-md", tekst)
    rodzaje = {blok.rodzaj for blok in dokument.bloki}
    assert RodzajBloku.CYTAT in rodzaje
    assert RodzajBloku.KOD in rodzaje


def test_rejestr_dobiera_ekstraktor_markdown_dla_md() -> None:
    rejestr = domyslny_rejestr()
    assert isinstance(rejestr.dobierz(TypZrodla.PLIK_TEKSTOWY, "md"), EkstraktorMarkdown)
    assert isinstance(rejestr.dobierz(TypZrodla.TEKST_WKLEJONY, "md"), EkstraktorMarkdown)
