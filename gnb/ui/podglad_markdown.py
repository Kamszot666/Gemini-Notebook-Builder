"""Zamiana pliku Markdown na bezpieczny HTML do podglądu jako strona.

Podgląd jako strona istnieje po to, żeby czytnik ekranu mógł przechodzić po
nagłówkach pliku MD klawiszem nagłówka, tak jak po stronie internetowej. Edytor
tekstu tego nie umożliwia.

To jest świadomy, wąski wyjątek od zasady z sekcji jedenastej CLAUDE.md, że
treść pobrana ze źródeł nigdy nie trafia do przeglądarki jako HTML. Wyjątek
zatwierdził użytkownik 23 października 2026 i działa tylko przy spełnieniu
wszystkich warunków poniżej:

1. Znaczniki HTML buduje wyłącznie ten moduł, z zestawu elementów, który
   wytwarza renderer biblioteki ``markdown-it-py``: nagłówki od ``h1`` do ``h6``,
   listy, tabele, cytaty, bloki kodu, akapity, wyróżnienia i odnośniki. Cały tekst
   ze źródła jest escapowany przez renderer, także treść nagłówków, komórek
   i bloków kodu.
2. Surowy HTML zawarty w pliku jest wyłączony opcją ``html=False``, więc znaczniki
   z pliku są pokazywane jako tekst.
3. Odnośniki są dozwolone wyłącznie dla adresów ``http`` i ``https`` z nazwą
   serwera. Każdy inny schemat, na przykład ``javascript:`` albo ``data:``,
   oraz adres względny staje się zwykłym tekstem. Odnośniki dostają
   ``rel="noopener noreferrer"``.
4. Obrazy są wyłączone. Zapis obrazu zostaje tekstem.
5. Dodatkową warstwą jest nagłówek ``Content-Security-Policy`` strony podglądu,
   który blokuje skrypty i zasoby zewnętrzne (``NAGLOWEK_POLITYKI_PODGLADU``).

Moduł nie czyta plików i nie wie nic o projektach: dostaje tekst, zwraca HTML.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

DOZWOLONE_SCHEMATY_ODNOSNIKOW = frozenset({"http", "https"})

# Polityka dla strony podglądu: żadnych skryptów, ramek, obrazów ani zasobów
# z zewnątrz. Wbudowany styl wyglądu i krój pisma z adresu serwera są dozwolone.
NAGLOWEK_POLITYKI_PODGLADU = (
    "default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)


def _czy_adres_dozwolony(adres: str) -> bool:
    """Przepuszcza tylko pełne adresy http i https, z nazwą serwera."""
    try:
        czesci = urlsplit(adres.strip())
    except ValueError:
        return False
    return czesci.scheme.lower() in DOZWOLONE_SCHEMATY_ODNOSNIKOW and bool(czesci.netloc)


class _ParserBezpieczny(MarkdownIt):
    """Parser, który uznaje za odnośnik wyłącznie adresy http i https z nazwą serwera."""

    def validateLink(self, url: str) -> bool:
        return _czy_adres_dozwolony(url)


def _utworz_parser() -> MarkdownIt:
    """Buduje parser CommonMark z tabelami, bez surowego HTML i bez obrazów."""
    parser = _ParserBezpieczny("commonmark", {"html": False, "breaks": True}).enable("table")
    parser.disable("image")
    return parser


_PARSER = _utworz_parser()


def zamien_markdown_na_html(tekst_markdown: str) -> str:
    """Zamienia tekst Markdown na fragment HTML bezpieczny do wstawienia w stronę.

    Zwraca same elementy treści, bez ``html``, ``head`` i ``body``. Znaki końca
    wiersza w akapicie stają się ``br``, bo plik MD zaczyna się od metadanych
    źródła, zapisanych w kolejnych wierszach jednego akapitu.
    """
    tokeny = _PARSER.parse(tekst_markdown)
    _dopisz_atrybuty_odnosnikow(tokeny)
    return str(_PARSER.renderer.render(tokeny, _PARSER.options, {}))


def _dopisz_atrybuty_odnosnikow(tokeny: list[Token]) -> None:
    """Dopisuje ``rel`` do każdego odnośnika, także tego w komórce tabeli i w liście."""
    for token in tokeny:
        if token.type == "link_open":
            token.attrSet("rel", "noopener noreferrer")
        if token.children:
            _dopisz_atrybuty_odnosnikow(token.children)
