"""Ekstraktor tekstu płaskiego: tekst wklejony oraz pliki TXT.

Tekst płaski nie niesie wiarygodnej struktury, nawet jeżeli zawiera wiersze
wyglądające na nagłówki albo wypunktowania. Dlatego ekstraktor zawsze zgłasza
niski poziom pewności struktury i nie tworzy bloków strukturalnych. Dzięki temu
warunek konieczny reguły wyboru formatu z sekcji ósmej CLAUDE.md jest pilnowany
w kodzie, a nie tylko opisany w dokumentacji: z pliku TXT nigdy nie powstanie
wersja Markdown.
"""

from __future__ import annotations

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla

_FORMATY_TEKSTU_WKLEJONEGO = frozenset({"", "txt"})
_MAKSYMALNA_DLUGOSC_TYTULU = 80


class EkstraktorTekstu:
    """Ekstraktor tekstu płaskiego dla tekstu wklejonego i plików TXT."""

    metoda = "tekst_plaski"
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        if typ_zrodla is TypZrodla.PLIK_TEKSTOWY:
            return format_zrodla == "txt"
        if typ_zrodla is TypZrodla.TEKST_WKLEJONY:
            return format_zrodla in _FORMATY_TEKSTU_WKLEJONEGO
        return False

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Zwraca dokument bez bloków strukturalnych, z niskim poziomem pewności."""
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=self.metoda,
            tytul=_pierwszy_niepusty_wiersz(tekst),
        )


def _pierwszy_niepusty_wiersz(tekst: str) -> str | None:
    """Zwraca pierwszy niepusty wiersz tekstu jako propozycję tytułu."""
    for wiersz in tekst.splitlines():
        oczyszczony = wiersz.strip()
        if oczyszczony:
            return oczyszczony[:_MAKSYMALNA_DLUGOSC_TYTULU]
    return None
