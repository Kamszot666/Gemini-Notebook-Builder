"""Ekstrakcja treści pliku CSV jako pojedynczej tabeli.

Plik CSV nie ma tytułu ani podziału na akapity, ponieważ z natury formatu jest
tabelą danych, a nie prozą. Ekstraktor nie zgaduje tytułu z niczego, a ocena
jakości ekstrakcji celowo nie obejmuje tego formatu — dokumentuje to
`gnb.potok`, bo dla tabeli brak tytułu nie jest oznaką utraty treści, tylko
naturalnym stanem, a ostrzeżenie bez możliwości naprawy uczyłoby pomijać
wszystkie ostrzeżenia.

Pierwszy wiersz pliku jest zawsze traktowany jako nagłówek kolumn. To jest
założenie, a nie wykryte automatycznie, bo pliku CSV nie da się jednoznacznie
rozstrzygnąć, czy pierwszy wiersz jest nagłówkiem, czy pierwszym rekordem.

Ogranicznik kolumn jest rozpoznawany automatycznie spośród przecinka, średnika,
tabulatora i pionowej kreski. Gdy rozpoznanie się nie powiedzie, na przykład
przy pliku z jednym wierszem, przyjmowany jest przecinek, bo to najczęstszy
ogranicznik plików CSV eksportowanych z arkuszy kalkulacyjnych.

Treść trafia do jednego bloku tabeli, a stąd do tekstu w zapisie Markdown.
Wersja TXT rozpisuje z niego każdy rekord jako kolejne wiersze „nazwa kolumny:
wartość”, co czytnik ekranu odsłuchuje wyraźnie lepiej niż wiersz z komórkami
rozdzielonymi przecinkami.
"""

from __future__ import annotations

import csv
import io

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.extractors.bloki_markdown import zapisz_bloki_jako_markdown

METODA_EKSTRAKCJI = "csv"
FORMATY_CSV = frozenset({"csv"})

KOMUNIKAT_BRAK_DANYCH = "Plik CSV nie zawiera żadnego wiersza z danymi."

_ROZMIAR_PROBKI_DO_ROZPOZNANIA_OGRANICZNIKA = 8192
_MOZLIWE_OGRANICZNIKI = ",;\t|"


class EkstraktorCsv:
    """Ekstraktor plików CSV, zamieniający je na jedną tabelę."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_CSV

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Wczytuje wiersze CSV i zamienia je na jeden blok tabeli."""
        wiersze = _wczytaj_wiersze(tekst)
        if not wiersze:
            return DokumentWyekstrahowany(
                identyfikator_zrodla=identyfikator_zrodla,
                tekst="",
                poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
                metoda_ekstrakcji=METODA_EKSTRAKCJI,
                ostrzezenia=[KOMUNIKAT_BRAK_DANYCH],
            )

        blok = BlokTresci(
            rodzaj=RodzajBloku.TABELA,
            poziom=0,
            tresc="\n".join("\t".join(wiersz) for wiersz in wiersze),
        )
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=zapisz_bloki_jako_markdown([blok]),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            bloki=[blok],
            metadane={
                "liczba_kolumn": str(len(wiersze[0])),
                "liczba_wierszy_danych": str(len(wiersze) - 1),
            },
        )


def _wczytaj_wiersze(tekst: str) -> list[list[str]]:
    """Parsuje tekst CSV na wiersze komórek, pomijając wiersze całkiem puste.

    Tabulator i znak nowej linii wewnątrz komórki są zamieniane na spację,
    ponieważ wewnętrzny format bloku tabeli używa ich jako rozdzielaczy wierszy
    i kolumn, więc pozostawienie ich zniekształciłoby strukturę tabeli.
    """
    if not tekst.strip():
        return []
    dialekt = _rozpoznaj_dialekt(tekst)
    czytnik = csv.reader(io.StringIO(tekst), dialekt)
    wiersze: list[list[str]] = []
    for surowy_wiersz in czytnik:
        wiersz = [_oczysc_komorke(komorka) for komorka in surowy_wiersz]
        if any(komorka for komorka in wiersz):
            wiersze.append(wiersz)
    return wiersze


def _oczysc_komorke(komorka: str) -> str:
    """Sprowadza treść komórki do jednego wiersza, bez tabulatorów w środku."""
    return komorka.replace("\t", " ").replace("\r\n", " ").replace("\n", " ").strip()


def _rozpoznaj_dialekt(tekst: str) -> csv.Dialect | type[csv.Dialect]:
    """Rozpoznaje ogranicznik kolumn, a przy niepowodzeniu zakłada przecinek."""
    probka = tekst[:_ROZMIAR_PROBKI_DO_ROZPOZNANIA_OGRANICZNIKA]
    try:
        return csv.Sniffer().sniff(probka, delimiters=_MOZLIWE_OGRANICZNIKI)
    except csv.Error:
        return csv.excel
