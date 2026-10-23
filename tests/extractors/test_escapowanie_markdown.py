"""Testy escapowania składni Markdown w tekście spoza bloków strukturalnych.

Test nie porównuje wyniku z napisem wyliczonym tym samym kodem. Sprawdza dwie
rzeczy niezależnie od implementacji: parser CommonMark widzi po escapowaniu
wyłącznie akapity, a tekst odczytany z powrotem ma te same słowa co wejście.
"""

from __future__ import annotations

import pytest

from gnb.extractors.escapowanie_markdown import (
    dlugosc_ogrodzenia_kodu,
    escapuj_naglowek,
    escapuj_tekst_plaski,
)
from gnb.extractors.markdown import utworz_parser
from gnb.output.tekst_bez_znacznikow import zamien_markdown_na_tekst

_TOKENY_AKAPITU = {"paragraph_open", "inline", "paragraph_close"}

_PODEJRZANE_WIERSZE = [
    "# Nie nagłówek",
    "## Też nie nagłówek",
    "###### Szósty poziom",
    "#",
    "- punkt",
    "-",
    "+ plus",
    "* gwiazdka",
    "1. pierwszy",
    "12) nawias",
    "> cytat",
    ">cytat bez spacji",
    "```",
    "~~~ ogrodzenie",
    "---",
    "***",
    "___",
    "- - -",
    "===",
    "--",
    "| a | b |",
    "[1]: https://przyklad.pl",
    "   - wcięty punkt",
    "2*3*4 to 24",
    "a_b_c i _kursywa_",
    "**pogrubienie**",
    "`kod`",
    "<div>html</div>",
    "<!-- komentarz -->",
    "&amp; encja",
    "[tekst](https://przyklad.pl)",
    "~~skreślone~~",
    "kończy się ukośnikiem\\",
    "C:\\Users\\jan\\plik.txt",
    "\\# już escapowany",
]


@pytest.mark.parametrize("wiersz", _PODEJRZANE_WIERSZE)
def test_po_escapowaniu_parser_widzi_wylacznie_akapit(wiersz: str) -> None:
    tekst = f"Zdanie otwierające.\n{wiersz}\nZdanie zamykające."

    tokeny = utworz_parser().parse(escapuj_tekst_plaski(tekst))

    typy = {token.type for token in tokeny}
    assert typy <= _TOKENY_AKAPITU, f"fałszywa struktura z wiersza {wiersz!r}: {typy}"


@pytest.mark.parametrize("wiersz", _PODEJRZANE_WIERSZE)
def test_po_escapowaniu_wiersz_na_poczatku_tekstu_tez_jest_akapitem(wiersz: str) -> None:
    tokeny = utworz_parser().parse(escapuj_tekst_plaski(wiersz))

    assert {token.type for token in tokeny} <= _TOKENY_AKAPITU


@pytest.mark.parametrize("wiersz", _PODEJRZANE_WIERSZE)
def test_escapowanie_nie_gubi_slow_tekstu(wiersz: str) -> None:
    tekst = f"Zdanie otwierające.\n{wiersz}\nZdanie zamykające."

    odczytany = zamien_markdown_na_tekst(escapuj_tekst_plaski(tekst))

    assert odczytany.split() == tekst.split()


def test_zwykly_tekst_bez_skladni_zostaje_bez_zmian() -> None:
    tekst = "Zwykłe zdanie z ą, ć, ż.\n\nDrugi akapit: 3 - 2 = 1, a snake_case zostaje.\nhttps://a.pl/x_y"

    assert escapuj_tekst_plaski(tekst) == tekst


def test_sciezka_windows_nie_dostaje_zbednych_ukosnikow() -> None:
    assert escapuj_tekst_plaski("C:\\Users\\jan\\plik.txt") == "C:\\Users\\jan\\plik.txt"


def test_podkreslenie_wewnatrz_slowa_nie_jest_escapowane_a_na_brzegu_jest() -> None:
    assert escapuj_tekst_plaski("snake_case") == "snake_case"
    assert escapuj_tekst_plaski("_kursywa_") == "\\_kursywa\\_"


def test_naglowek_escapuje_zamykajacy_ciag_krzyzykow() -> None:
    """Zamykający ciąg krzyżyków po spacji parser odcina z nagłówka."""
    zapis = f"## {escapuj_naglowek('Język C #')}"

    tokeny = utworz_parser().parse(zapis)

    assert tokeny[1].content == "Język C \\#"
    assert zamien_markdown_na_tekst(zapis).split() == ["Język", "C", "#"]


def test_ogrodzenie_kodu_jest_dluzsze_niz_najdluzszy_ciag_grawisow_w_tresci() -> None:
    assert dlugosc_ogrodzenia_kodu("zwykły kod") == 3
    assert dlugosc_ogrodzenia_kodu("a ``` b") == 4
    assert dlugosc_ogrodzenia_kodu("a ````` b") == 6
