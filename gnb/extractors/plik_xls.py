"""Ekstrakcja treści ze starych arkuszy XLS biblioteką xlrd.

Format XLS to binarny format programu Excel sprzed 2007 roku. Biblioteka xlrd
w wersji drugiej czyta wyłącznie ten format, a nie XLSX, co wystarcza, bo XLSX ma
własny ekstraktor. Zasady zapisu arkusza są te same co dla XLSX i leżą w
`gnb.extractors.arkusze`: każdy arkusz jest nagłówkiem i tabelą, data jest
zapisana jako RRRR-MM-DD, komórka procentowa jako procent.

Wartość komórki z zapisanym wynikiem formuły jest odczytywana jako ten wynik.
Skoroszyt zaszyfrowany hasłem kończy się błędem trwałym z czytelnym komunikatem.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import xlrd

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.arkusze import bloki_arkusza, czy_format_walutowy, wartosc_na_tekst
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.bloki_markdown import zapisz_bloki_jako_markdown

METODA_EKSTRAKCJI = "xls"
FORMATY_XLS = frozenset({"xls"})

KOMUNIKAT_USZKODZONY = (
    "Plik XLS jest uszkodzony, zaszyfrowany hasłem albo nie jest skoroszytem programu "
    "Excel: nie dało się go odczytać. Skoroszytu zaszyfrowanego hasłem aplikacja nie "
    "otwiera. Zapisz go bez szyfrowania i dodaj ponownie."
)

_BLEDY_ODCZYTU = (xlrd.XLRDError, OSError, ValueError, KeyError, IndexError, AssertionError)
_WIDOCZNY = 0


class EkstraktorXls:
    """Ekstraktor skoroszytów XLS: każdy arkusz jako nagłówek i tabela."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_XLS

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Odczytuje wszystkie arkusze skoroszytu. Argument `postep` nie jest używany."""
        try:
            skoroszyt = xlrd.open_workbook(file_contents=bajty, formatting_info=True)
        except _BLEDY_ODCZYTU as blad:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY, identyfikator_zrodla) from blad

        try:
            bloki: list[BlokTresci] = []
            komorki_walutowe = 0
            for arkusz in skoroszyt.sheets():
                wiersze, waluty = _wiersze_arkusza(skoroszyt, arkusz)
                komorki_walutowe += waluty
                bloki.extend(
                    bloki_arkusza(arkusz.name, wiersze, ukryty=arkusz.visibility != _WIDOCZNY)
                )
        except _BLEDY_ODCZYTU as blad:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY, identyfikator_zrodla) from blad
        finally:
            skoroszyt.release_resources()

        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=zapisz_bloki_jako_markdown(bloki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            bloki=bloki,
            ostrzezenia=(
                [
                    f"W skoroszycie jest {komorki_walutowe} komórek z formatem walutowym. "
                    "Zapisano same liczby, bez symbolu waluty, więc przy tych komórkach "
                    "nie ma jednostki."
                ]
                if komorki_walutowe
                else []
            ),
        )


def _wiersze_arkusza(skoroszyt: Any, arkusz: Any) -> tuple[list[list[str]], int]:
    """Zwraca wiersze arkusza jako tekst oraz liczbę komórek z formatem walutowym."""
    wiersze: list[list[str]] = []
    komorki_walutowe = 0
    for numer_wiersza in range(arkusz.nrows):
        wiersz: list[str] = []
        for numer_kolumny in range(arkusz.ncols):
            komorka = arkusz.cell(numer_wiersza, numer_kolumny)
            wiersz.append(_tekst_komorki(skoroszyt, komorka))
            if komorka.ctype == xlrd.XL_CELL_NUMBER and czy_format_walutowy(
                _format_liczby(skoroszyt, komorka)
            ):
                komorki_walutowe += 1
        wiersze.append(wiersz)
    return wiersze, komorki_walutowe


def _tekst_komorki(skoroszyt: Any, komorka: Any) -> str:
    """Zamienia komórkę xlrd na tekst, uwzględniając typ komórki i jej format liczby."""
    typ = komorka.ctype
    wartosc = komorka.value
    if typ in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
        return ""
    if typ == xlrd.XL_CELL_DATE:
        return wartosc_na_tekst(_data(skoroszyt, wartosc))
    if typ == xlrd.XL_CELL_BOOLEAN:
        return wartosc_na_tekst(bool(wartosc))
    if typ == xlrd.XL_CELL_ERROR:
        return str(xlrd.error_text_from_code.get(wartosc, "#BŁĄD!"))
    if typ == xlrd.XL_CELL_NUMBER:
        return wartosc_na_tekst(float(wartosc), _format_liczby(skoroszyt, komorka))
    return str(wartosc)


def _data(skoroszyt: Any, wartosc: float) -> dt.datetime | float:
    """Zamienia liczbę daty programu Excel na datę, a przy niepoprawnej wartości zostawia liczbę."""
    try:
        data: dt.datetime = xlrd.xldate.xldate_as_datetime(wartosc, skoroszyt.datemode)
        return data
    except (xlrd.xldate.XLDateError, OverflowError, ValueError):
        return wartosc


def _format_liczby(skoroszyt: Any, komorka: Any) -> str | None:
    """Zwraca zapis formatu liczby komórki albo ``None``, gdy go nie ma."""
    try:
        xf = skoroszyt.xf_list[komorka.xf_index]
        return str(skoroszyt.format_map[xf.format_key].format_str)
    except (IndexError, KeyError, AttributeError):
        return None
