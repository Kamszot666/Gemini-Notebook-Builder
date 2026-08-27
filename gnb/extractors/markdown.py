"""Ekstraktor Markdown: pliki MD oraz tekst wklejony zadeklarowany jako Markdown.

Struktura dokumentu Markdown jest jawna, dlatego ekstraktor zgłasza wysoki
poziom pewności struktury. Parserem jest ``markdown-it-py`` w presecie
``commonmark`` z jawnie włączoną regułą tabel. Tabele nie należą do specyfikacji
CommonMark, a trzeci warunek reguły wyboru formatu z sekcji ósmej CLAUDE.md
wymaga rozpoznania tabeli, więc reguła ``table`` jest włączana wprost. Wtyczki
``mdit-py-plugins`` nie są do tego potrzebne.

Ekstraktor nie renderuje Markdown z powrotem do tekstu — zapis wersji MD to
zadanie modułu `gnb.output.zapis`.
"""

from __future__ import annotations

from markdown_it import MarkdownIt
from markdown_it.token import Token

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla

_FORMATY_MARKDOWN = frozenset({"md", "markdown"})
_MAKSYMALNA_DLUGOSC_TYTULU = 80
_TYPY_ZRODLA_MARKDOWN = (TypZrodla.PLIK_TEKSTOWY, TypZrodla.TEKST_WKLEJONY)


def utworz_parser() -> MarkdownIt:
    """Buduje parser CommonMark z włączoną regułą tabel GFM.

    Funkcja jest publiczna, ponieważ tej samej konfiguracji parsera używa moduł
    `gnb.output.tekst_bez_znacznikow`. Obie ścieżki muszą widzieć identyczną
    strukturę dokumentu, w tym tabele, których CommonMark sam nie obejmuje.
    """
    return MarkdownIt("commonmark").enable("table")


class EkstraktorMarkdown:
    """Ekstraktor Markdown dla plików MD i tekstu wklejonego zadeklarowanego jako Markdown."""

    metoda = "markdown"
    tekst_zawiera_znaczniki = True

    def __init__(self) -> None:
        self._parser = utworz_parser()

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla in _TYPY_ZRODLA_MARKDOWN and format_zrodla in _FORMATY_MARKDOWN

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Parsuje Markdown na listę bloków strukturalnych z wysokim poziomem pewności."""
        bloki = _tokeny_na_bloki(self._parser.parse(tekst))
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=self.metoda,
            tytul=_tytul_z_blokow(bloki),
            bloki=bloki,
        )


def _tokeny_na_bloki(tokeny: list[Token]) -> list[BlokTresci]:
    """Zamienia płaską listę tokenów markdown-it na listę bloków treści."""
    bloki: list[BlokTresci] = []
    indeks = 0
    liczba_tokenow = len(tokeny)

    while indeks < liczba_tokenow:
        token = tokeny[indeks]
        typ = token.type

        if typ == "heading_open":
            bloki.append(
                BlokTresci(
                    rodzaj=RodzajBloku.NAGLOWEK,
                    poziom=_poziom_naglowka(token.tag),
                    tresc=_tresc_nastepnego_inline(tokeny, indeks),
                )
            )
            indeks += 3
            continue

        if typ == "paragraph_open":
            if token.level == 0:
                tresc = _tresc_nastepnego_inline(tokeny, indeks)
                if tresc:
                    bloki.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=tresc))
            indeks += 3
            continue

        if typ in ("bullet_list_open", "ordered_list_open"):
            elementy, indeks = _elementy_listy(tokeny, indeks)
            bloki.append(
                BlokTresci(
                    rodzaj=RodzajBloku.LISTA,
                    poziom=token.level,
                    tresc="\n".join(elementy),
                )
            )
            continue

        if typ == "table_open":
            wiersze, indeks = _wiersze_tabeli(tokeny, indeks)
            bloki.append(BlokTresci(rodzaj=RodzajBloku.TABELA, poziom=0, tresc="\n".join(wiersze)))
            continue

        if typ in ("fence", "code_block"):
            bloki.append(
                BlokTresci(rodzaj=RodzajBloku.KOD, poziom=0, tresc=token.content.rstrip("\n"))
            )
            indeks += 1
            continue

        if typ == "blockquote_open":
            tresc, indeks = _tresc_cytatu(tokeny, indeks)
            bloki.append(BlokTresci(rodzaj=RodzajBloku.CYTAT, poziom=0, tresc=tresc))
            continue

        indeks += 1

    return bloki


def _poziom_naglowka(tag: str) -> int:
    """Zamienia znacznik nagłówka HTML na numer poziomu, na przykład ``h3`` na 3."""
    try:
        return int(tag[1:])
    except ValueError:
        return 1


def _tresc_nastepnego_inline(tokeny: list[Token], indeks: int) -> str:
    """Zwraca oczyszczoną treść tokenu ``inline`` następującego po podanym indeksie."""
    if indeks + 1 < len(tokeny) and tokeny[indeks + 1].type == "inline":
        return tokeny[indeks + 1].content.strip()
    return ""


def _elementy_listy(tokeny: list[Token], start: int) -> tuple[list[str], int]:
    """Zwraca teksty elementów listy najwyższego poziomu oraz indeks za jej końcem.

    Zliczane są wyłącznie elementy bezpośrednie tej listy. Elementy list
    zagnieżdżonych mają wyższy poziom tokenu i nie są tu doliczane.
    """
    otwarcie = tokeny[start]
    poziom_listy = otwarcie.level
    poziom_elementu = poziom_listy + 1
    typ_zamkniecia = otwarcie.type.replace("_open", "_close")

    elementy: list[str] = []
    indeks = start + 1
    while indeks < len(tokeny):
        token = tokeny[indeks]
        if token.type == typ_zamkniecia and token.level == poziom_listy:
            indeks += 1
            break
        if token.type == "list_item_open" and token.level == poziom_elementu:
            elementy.append("")
        elif token.type == "inline" and elementy and not elementy[-1]:
            pierwszy_wiersz = token.content.strip().splitlines()
            elementy[-1] = pierwszy_wiersz[0] if pierwszy_wiersz else ""
        indeks += 1
    return elementy, indeks


def _wiersze_tabeli(tokeny: list[Token], start: int) -> tuple[list[str], int]:
    """Zwraca wiersze tabeli jako teksty z komórkami rozdzielonymi pionową kreską."""
    wiersze: list[str] = []
    komorki: list[str] = []
    indeks = start + 1
    while indeks < len(tokeny):
        token = tokeny[indeks]
        if token.type == "table_close":
            indeks += 1
            break
        if token.type == "tr_open":
            komorki = []
        elif token.type == "inline":
            komorki.append(token.content.strip())
        elif token.type == "tr_close":
            wiersze.append(" | ".join(komorki))
        indeks += 1
    return wiersze, indeks


def _tresc_cytatu(tokeny: list[Token], start: int) -> tuple[str, int]:
    """Zwraca połączony tekst cytatu blokowego oraz indeks za jego końcem."""
    poziom = tokeny[start].level
    fragmenty: list[str] = []
    indeks = start + 1
    while indeks < len(tokeny):
        token = tokeny[indeks]
        if token.type == "blockquote_close" and token.level == poziom:
            indeks += 1
            break
        if token.type == "inline":
            fragmenty.append(token.content.strip())
        indeks += 1
    return "\n".join(fragmenty), indeks


def _tytul_z_blokow(bloki: list[BlokTresci]) -> str | None:
    """Wybiera tytuł dokumentu: pierwszy nagłówek, a w razie jego braku pierwszy akapit."""
    for rodzaj_docelowy in (RodzajBloku.NAGLOWEK, RodzajBloku.AKAPIT):
        for blok in bloki:
            if blok.rodzaj is rodzaj_docelowy and blok.tresc:
                return blok.tresc[:_MAKSYMALNA_DLUGOSC_TYTULU]
    return None
