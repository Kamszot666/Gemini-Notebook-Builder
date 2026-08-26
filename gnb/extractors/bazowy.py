"""Wspólny kontrakt ekstraktorów oraz rejestr dobierający ekstraktor do źródła.

Ekstraktor zamienia rozkodowany, jeszcze nieznormalizowany tekst źródła na
`DokumentWyekstrahowany`: tekst, opcjonalny tytuł, listę bloków strukturalnych
oraz poziom pewności rozpoznania struktury. Nowy format dodaje się jako nową
implementację protokołu `Ekstraktor` i wpis w rejestrze, bez zmian w pozostałych
modułach potoku.

W etapie pierwszym istnieją dwa ekstraktory: tekstu płaskiego i Markdown.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import FormatNieobslugiwany


class Ekstraktor(Protocol):
    """Kontrakt pojedynczego adaptera ekstrakcji."""

    metoda: str

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        """Zwraca prawdę, jeżeli ten ekstraktor potrafi przetworzyć dane źródło.

        Argument `format_zrodla` to małą literą zapisane rozszerzenie pliku bez
        kropki albo zadeklarowany format tekstu wklejonego, na przykład ``txt``
        lub ``md``. Pusty napis oznacza brak wskazówki formatu.
        """
        ...

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Buduje `DokumentWyekstrahowany` z rozkodowanego tekstu źródła."""
        ...


class RejestrEkstraktorow:
    """Uporządkowana lista ekstraktorów z wyborem pierwszego pasującego."""

    def __init__(self, ekstraktory: Sequence[Ekstraktor]) -> None:
        self._ekstraktory: tuple[Ekstraktor, ...] = tuple(ekstraktory)

    def dobierz(self, typ_zrodla: TypZrodla, format_zrodla: str) -> Ekstraktor:
        """Zwraca pierwszy ekstraktor obsługujący dane źródło.

        Gdy żaden ekstraktor nie pasuje, zgłasza `FormatNieobslugiwany`
        z komunikatem po polsku gotowym do pokazania użytkownikowi.
        """
        for ekstraktor in self._ekstraktory:
            if ekstraktor.obsluguje(typ_zrodla, format_zrodla):
                return ekstraktor
        raise FormatNieobslugiwany(
            f"Brak ekstraktora dla źródła typu „{typ_zrodla.value}” "
            f"w formacie „{format_zrodla or 'nieokreślony'}”."
        )


def domyslny_rejestr() -> RejestrEkstraktorow:
    """Buduje rejestr z ekstraktorami dostępnymi w etapie pierwszym.

    Ekstraktor Markdown jest przed ekstraktorem tekstu płaskiego, żeby źródło
    z formatem ``md`` trafiło do właściwego adaptera także wtedy, gdy jest
    tekstem wklejonym.
    """
    from gnb.extractors.markdown import EkstraktorMarkdown
    from gnb.extractors.tekst import EkstraktorTekstu

    return RejestrEkstraktorow((EkstraktorMarkdown(), EkstraktorTekstu()))
