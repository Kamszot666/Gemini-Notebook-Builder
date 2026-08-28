"""Ekstrakcja treści z plików DOCX z zachowaniem struktury dokumentu.

Format DOCX niesie prawdziwą strukturę semantyczną: styl akapitu mówi wprost,
czy jest nagłówkiem i którego poziomu, czy elementem listy wypunktowanej albo
numerowanej, a tabela jest osobnym elementem dokumentu, a nie zgadywanym
układem tekstu. Dzięki temu ekstraktor zgłasza wysoki poziom pewności struktury
— wyższy niż dla strony internetowej, gdzie strukturę trzeba dopiero rozpoznać
z kodu HTML.

Akapity i tabele są czytane w kolejności występowania w dokumencie, a nie
osobno jedne po drugich, ponieważ `python-docx` domyślnie udostępnia je jako
dwie osobne listy i traci przez to układ dokumentu. Kolejne akapity o tym samym
stylu listy są sklejane w jeden blok listy, zgodnie z wewnętrznym formatem
bloku ustalonym dla całego projektu.

Plik uszkodzony albo niebędący dokumentem Worda kończy się błędem trwałym
z czytelnym komunikatem, a nie surowym wyjątkiem biblioteki. Jedno uszkodzone
źródło nie może zatrzymać całego projektu.

Ekstraktor nie rozpoznaje bloków kodu, ponieważ DOCX nie ma dla nich
standardowego stylu — zgadywanie po nazwie czcionki byłoby heurystyką bez
pewności, a projekt nie zgaduje struktury tam, gdzie nie da się jej stwierdzić
wprost z formatu.
"""

from __future__ import annotations

import io
import re
import zipfile

from docx import Document
from docx.document import Document as DokumentDocx
from docx.opc.exceptions import OpcError
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.bloki_markdown import zapisz_bloki_jako_markdown

METODA_EKSTRAKCJI = "docx"
FORMATY_DOCX = frozenset({"docx"})

KOMUNIKAT_USZKODZONY = (
    "Plik DOCX jest uszkodzony albo nie jest dokumentem programu Word: nie dało "
    "się odczytać jego archiwum ani zawartości."
)

# Wyjątki, którymi biblioteka zgłasza plik nienadający się do odczytu. Błąd
# klucza pojawia się dla poprawnego archiwum zip pozbawionego pliku
# „[Content_Types].xml”, czyli dla archiwum, które nie jest dokumentem DOCX.
_BLEDY_ODCZYTU_DOCX = (OpcError, zipfile.BadZipFile, KeyError, ValueError, OSError)

_WZORZEC_NAGLOWKA = re.compile(r"^Heading (\d+)$")
_FORMAT_DATY = "%Y-%m-%d"


class EkstraktorDocx:
    """Ekstraktor plików DOCX zachowujący nagłówki, listy i tabele."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_DOCX

    def wyekstrahuj(self, identyfikator_zrodla: str, bajty: bytes) -> DokumentWyekstrahowany:
        """Odczytuje dokument DOCX zachowując nagłówki, listy i tabele w kolejności."""
        try:
            dokument_docx = Document(io.BytesIO(bajty))
        except _BLEDY_ODCZYTU_DOCX as blad:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY, identyfikator_zrodla) from blad

        bloki = _bloki_z_dokumentu(dokument_docx)
        tytul = _tytul(dokument_docx, bloki)
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=zapisz_bloki_jako_markdown(bloki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=tytul,
            bloki=bloki,
            metadane=_metadane(dokument_docx),
        )


def _bloki_z_dokumentu(dokument_docx: DokumentDocx) -> list[BlokTresci]:
    """Zwraca bloki treści w kolejności występowania akapitów i tabel w pliku."""
    bloki: list[BlokTresci] = []
    elementy_listy: list[str] = []
    rodzaj_listy = 0

    def zamknij_liste() -> None:
        if elementy_listy:
            bloki.append(
                BlokTresci(
                    rodzaj=RodzajBloku.LISTA, poziom=rodzaj_listy, tresc="\n".join(elementy_listy)
                )
            )
            elementy_listy.clear()

    for element in dokument_docx.element.body.iterchildren():
        if element.tag == qn("w:p"):
            akapit = Paragraph(element, dokument_docx)
            tekst = akapit.text.strip()
            if not tekst:
                continue
            styl = akapit.style.name if akapit.style is not None else ""
            dopasowanie = _WZORZEC_NAGLOWKA.match(styl)
            if dopasowanie or styl == "Title":
                zamknij_liste()
                poziom = int(dopasowanie.group(1)) if dopasowanie else 1
                bloki.append(BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=poziom, tresc=tekst))
            elif styl.startswith("List Number"):
                if elementy_listy and rodzaj_listy != 1:
                    zamknij_liste()
                rodzaj_listy = 1
                elementy_listy.append(tekst)
            elif styl.startswith("List Bullet"):
                if elementy_listy and rodzaj_listy != 0:
                    zamknij_liste()
                rodzaj_listy = 0
                elementy_listy.append(tekst)
            elif styl in ("Quote", "Intense Quote"):
                zamknij_liste()
                bloki.append(BlokTresci(rodzaj=RodzajBloku.CYTAT, poziom=0, tresc=tekst))
            else:
                zamknij_liste()
                bloki.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=tekst))
        elif element.tag == qn("w:tbl"):
            zamknij_liste()
            wiersze = _wiersze_tabeli(Table(element, dokument_docx))
            if wiersze:
                bloki.append(
                    BlokTresci(rodzaj=RodzajBloku.TABELA, poziom=0, tresc="\n".join(wiersze))
                )
    zamknij_liste()
    return bloki


def _wiersze_tabeli(tabela: Table) -> list[str]:
    """Zwraca wiersze tabeli, z komórkami rozdzielonymi tabulatorem."""
    wiersze: list[str] = []
    for wiersz in tabela.rows:
        komorki = [_jeden_wiersz_tekstu(komorka.text) for komorka in wiersz.cells]
        if any(komorki):
            wiersze.append("\t".join(komorki))
    return wiersze


def _jeden_wiersz_tekstu(tekst: str) -> str:
    """Sprowadza treść komórki do jednego wiersza, bez tabulatorów w środku."""
    return tekst.replace("\t", " ").replace("\r\n", " ").replace("\n", " ").strip()


def _tytul(dokument_docx: DokumentDocx, bloki: list[BlokTresci]) -> str | None:
    """Zwraca tytuł z metadanych dokumentu albo pierwszy nagłówek jako zastępstwo."""
    tytul_z_metadanych: str | None = dokument_docx.core_properties.title
    if tytul_z_metadanych and tytul_z_metadanych.strip():
        return tytul_z_metadanych.strip()
    for blok in bloki:
        if blok.rodzaj is RodzajBloku.NAGLOWEK:
            return blok.tresc
    return None


def _metadane(dokument_docx: DokumentDocx) -> dict[str, str]:
    """Zbiera autora oraz daty utworzenia i modyfikacji z właściwości dokumentu."""
    wlasciwosci = dokument_docx.core_properties
    metadane: dict[str, str] = {}
    if wlasciwosci.author and wlasciwosci.author.strip():
        metadane["autor"] = wlasciwosci.author.strip()
    if wlasciwosci.created is not None:
        metadane["data_publikacji"] = wlasciwosci.created.strftime(_FORMAT_DATY)
    if wlasciwosci.modified is not None:
        metadane["data_aktualizacji"] = wlasciwosci.modified.strftime(_FORMAT_DATY)
    return metadane
