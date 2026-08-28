"""Ekstrakcja treści z plików EPUB z zachowaniem struktury rozdziałów.

EPUB jest archiwum zip z rozdziałami zapisanymi jako pliki XHTML. Ten
ekstraktor czyta rozdziały w kolejności lektury zapisanej w spisie `spine`
pliku, a nie w kolejności ich zapisania wewnątrz archiwum, bo tylko `spine`
gwarantuje właściwą kolejność czytania. Dokument nawigacyjny EPUB 3, czyli plik
`nav.xhtml` ze spisem treści, jest pomijany, ponieważ jest spisem odnośników,
a nie treścią książki.

Każdy rozdział jest rozbierany na nagłówki, akapity, listy, tabele i cytaty
wprost ze znaczników XHTML: `h1` do `h6`, `p`, `ul` i `ol`, `table`, `blockquote`.
To jest bezpośrednie odwzorowanie znaczników semantycznych, a nie zgadywanie
granic treści jak w ekstraktorze strony internetowej, dlatego poziom pewności
struktury jest wysoki. Zagnieżdżenie elementów w kontenerach `div`, `section`
i `article` jest przechodzone rekurencyjnie, żeby treść owinięta w takie
elementy, co jest typowe dla plików EPUB generowanych automatycznie, nie
zginęła.

Plik uszkodzony albo niebędący książką EPUB kończy się błędem trwałym
z czytelnym komunikatem, a nie surowym wyjątkiem biblioteki. Jedno uszkodzone
źródło nie może zatrzymać całego projektu. Rozdział, którego nie da się
sparsować, jest pomijany, ale zgłasza ostrzeżenie, więc nie znika po cichu.

Blok kodu nie jest tu rozpoznawany osobno od bloku cytatu ponad to, co
odwzorowuje znacznik `pre`, ponieważ nuty i notacja techniczna w e-bookach są
rzadkością, a rozbudowana obsługa niosłaby ryzyko błędów bez realnej potrzeby.
"""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime

from ebooklib import ITEM_DOCUMENT, epub
from lxml import etree, html

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.bloki_markdown import zapisz_bloki_jako_markdown

METODA_EKSTRAKCJI = "epub"
FORMATY_EPUB = frozenset({"epub"})

KOMUNIKAT_USZKODZONY = (
    "Plik EPUB jest uszkodzony albo nie jest książką EPUB: nie dało się odczytać "
    "jego archiwum ani spisu zawartości."
)
KOMUNIKAT_ROZDZIAL_NIEODCZYTANY = (
    "Rozdziału {nazwa} nie dało się sparsować, więc jego treść nie znalazła się "
    "w wyniku. Pozostałe rozdziały zostały odczytane normalnie."
)

# Wyjątki, którymi biblioteki zgłaszają plik nienadający się do odczytu. Błąd
# klucza pojawia się dla poprawnego archiwum zip pozbawionego pliku
# „META-INF/container.xml”, czyli dla archiwum, które nie jest książką EPUB.
_BLEDY_ODCZYTU_EPUB = (epub.EpubException, zipfile.BadZipFile, KeyError, OSError)

_ZNACZNIKI_NAGLOWKOW = frozenset({"h1", "h2", "h3", "h4", "h5", "h6"})
_ZNACZNIKI_KONTENEROW = frozenset({"div", "section", "article", "main", "body"})
_ZNACZNIKI_KOMOREK = frozenset({"td", "th"})
_BIALE_ZNAKI = re.compile(r"\s+")


class EkstraktorEpub:
    """Ekstraktor plików EPUB zachowujący nagłówki, listy i tabele rozdziałów."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_EPUB

    def wyekstrahuj(self, identyfikator_zrodla: str, bajty: bytes) -> DokumentWyekstrahowany:
        """Czyta rozdziały EPUB w kolejności lektury i zamienia je na bloki treści."""
        try:
            ksiazka = epub.read_epub(io.BytesIO(bajty))
        except _BLEDY_ODCZYTU_EPUB as blad:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY, identyfikator_zrodla) from blad

        bloki: list[BlokTresci] = []
        ostrzezenia: list[str] = []
        for rozdzial in _rozdzialy_w_kolejnosci(ksiazka):
            korzen = _korzen_html(rozdzial.get_content())
            if korzen is None:
                # Rozdział, którego nie da się sparsować, znikał wcześniej
                # w całości i bez śladu. Cała książka nie może przez to przepaść,
                # ale użytkownik musi się dowiedzieć, czego w wyniku nie ma.
                ostrzezenia.append(
                    KOMUNIKAT_ROZDZIAL_NIEODCZYTANY.format(nazwa=rozdzial.get_name())
                )
                continue
            bloki.extend(_bloki_z_elementu(korzen))

        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=zapisz_bloki_jako_markdown(bloki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=_pierwsza_wartosc(ksiazka, "title"),
            bloki=bloki,
            metadane=_metadane(ksiazka),
            ostrzezenia=ostrzezenia,
        )


def _rozdzialy_w_kolejnosci(ksiazka: epub.EpubBook) -> list[epub.EpubHtml]:
    """Zwraca dokumenty XHTML rozdziałów w kolejności lektury, bez dokumentu nawigacji."""
    rozdzialy: list[epub.EpubHtml] = []
    for identyfikator, _liniowy in ksiazka.spine:
        pozycja = ksiazka.get_item_with_id(identyfikator)
        if pozycja is None or pozycja.get_type() != ITEM_DOCUMENT:
            continue
        if isinstance(pozycja, epub.EpubNav):
            continue
        rozdzialy.append(pozycja)
    return rozdzialy


def _korzen_html(zawartosc: bytes) -> html.HtmlElement | None:
    """Parsuje zawartość rozdziału XHTML, zwracając wartość pustą przy błędzie."""
    try:
        return html.fromstring(zawartosc)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return None


def _bloki_z_elementu(element: html.HtmlElement | None) -> list[BlokTresci]:
    """Zamienia bezpośrednie dzieci elementu na bloki treści, wchodząc w kontenery."""
    if element is None:
        return []
    bloki: list[BlokTresci] = []
    for dziecko in element:
        znacznik = dziecko.tag
        if not isinstance(znacznik, str):
            continue
        if znacznik in _ZNACZNIKI_NAGLOWKOW:
            tekst = _tekst_elementu(dziecko)
            if tekst:
                bloki.append(
                    BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=int(znacznik[1]), tresc=tekst)
                )
        elif znacznik == "p":
            tekst = _tekst_elementu(dziecko)
            if tekst:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=tekst))
        elif znacznik in ("ul", "ol"):
            blok = _blok_listy(dziecko, numerowana=znacznik == "ol")
            if blok is not None:
                bloki.append(blok)
        elif znacznik == "table":
            wiersze = _wiersze_tabeli(dziecko)
            if wiersze:
                bloki.append(
                    BlokTresci(rodzaj=RodzajBloku.TABELA, poziom=0, tresc="\n".join(wiersze))
                )
        elif znacznik == "blockquote":
            tekst = _tekst_elementu(dziecko)
            if tekst:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.CYTAT, poziom=0, tresc=tekst))
        elif znacznik == "pre":
            tekst = dziecko.text_content().strip("\n")
            if tekst.strip():
                bloki.append(BlokTresci(rodzaj=RodzajBloku.KOD, poziom=0, tresc=tekst))
        elif znacznik in _ZNACZNIKI_KONTENEROW:
            bloki.extend(_bloki_z_elementu(dziecko))
    return bloki


def _blok_listy(element: html.HtmlElement, *, numerowana: bool) -> BlokTresci | None:
    """Buduje blok listy z bezpośrednich elementów `li`, pomijając zagnieżdżenie."""
    elementy = [_tekst_elementu(pozycja) for pozycja in element.findall("li")]
    elementy = [pozycja for pozycja in elementy if pozycja]
    if not elementy:
        return None
    return BlokTresci(
        rodzaj=RodzajBloku.LISTA, poziom=1 if numerowana else 0, tresc="\n".join(elementy)
    )


def _wiersze_tabeli(element: html.HtmlElement) -> list[str]:
    """Zwraca wiersze tabeli, z komórkami rozdzielonymi tabulatorem.

    Komórki są zbierane w kolejności ich wystąpienia w dokumencie, niezależnie
    od tego, czy są komórką nagłówkową, czy zwykłą. Wcześniej były to wyniki
    dwóch osobnych wyszukiwań sklejone jedno po drugim, przez co wiersz
    zawierający oba rodzaje komórek dostawał odwróconą kolejność kolumn.
    """
    wiersze: list[str] = []
    for wiersz in element.findall(".//tr"):
        komorki = [_tekst_elementu(komorka) for komorka in _komorki_wiersza(wiersz)]
        if any(komorki):
            wiersze.append("\t".join(komorki))
    return wiersze


def _komorki_wiersza(wiersz: html.HtmlElement) -> list[html.HtmlElement]:
    """Zwraca komórki wiersza tabeli w kolejności ich wystąpienia w dokumencie."""
    return [
        dziecko
        for dziecko in wiersz
        if isinstance(dziecko.tag, str) and dziecko.tag in _ZNACZNIKI_KOMOREK
    ]


def _tekst_elementu(element: html.HtmlElement) -> str:
    """Zwraca tekst elementu razem z tekstem elementów zagnieżdżonych, jednym wierszem."""
    return _BIALE_ZNAKI.sub(" ", element.text_content()).strip()


def _pierwsza_wartosc(ksiazka: epub.EpubBook, nazwa_pola: str) -> str | None:
    """Zwraca pierwszą wartość pola Dublin Core, na przykład tytułu albo autora."""
    wpisy = ksiazka.get_metadata("DC", nazwa_pola)
    if not wpisy:
        return None
    wartosc = wpisy[0][0]
    return wartosc.strip() if wartosc and wartosc.strip() else None


def _metadane(ksiazka: epub.EpubBook) -> dict[str, str]:
    """Zbiera autora i datę publikacji z metadanych Dublin Core pliku EPUB."""
    metadane: dict[str, str] = {}
    autor = _pierwsza_wartosc(ksiazka, "creator")
    if autor:
        metadane["autor"] = autor
    data = _pierwsza_wartosc(ksiazka, "date")
    if data:
        metadane["data_publikacji"] = _znormalizowana_data(data)
    return metadane


def _znormalizowana_data(wartosc: str) -> str:
    """Sprowadza datę EPUB, zapisaną w formacie W3CDTF, do postaci ``RRRR-MM-DD``."""
    try:
        return datetime.fromisoformat(wartosc.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return wartosc[:10]
