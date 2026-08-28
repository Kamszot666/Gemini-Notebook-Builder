"""Wspólny kontrakt ekstraktorów oraz rejestr dobierający ekstraktor do źródła.

Ekstraktor zamienia rozkodowany, jeszcze nieznormalizowany tekst źródła na
`DokumentWyekstrahowany`: tekst, opcjonalny tytuł, listę bloków strukturalnych
oraz poziom pewności rozpoznania struktury. Deklaruje też, czy zwracany tekst
zawiera znaczniki formatowania. Nowy format dodaje się jako nową
implementację protokołu `Ekstraktor` i wpis w rejestrze, bez zmian w pozostałych
modułach potoku.

Po etapie drugim istnieją trzy ekstraktory: tekstu płaskiego, Markdown
oraz stron internetowych.
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

    # Prawda oznacza, że zwracany tekst zachowuje znaczniki formatowania, jak
    # w Markdown. Potok buduje wtedy dodatkowo wersję TXT bez znaczników, żeby
    # plik TXT nie był kopią pliku MD. Fałsz oznacza tekst już czysty.
    tekst_zawiera_znaczniki: bool

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


def domyslny_rejestr(zachowuj_odnosniki: bool = True) -> RejestrEkstraktorow:
    """Buduje rejestr z ekstraktorami dostępnymi po etapie drugim.

    Ekstraktor Markdown jest przed ekstraktorem tekstu płaskiego, żeby źródło
    z formatem ``md`` trafiło do właściwego adaptera także wtedy, gdy jest
    tekstem wklejonym. Ekstraktor stron internetowych rozpoznaje własny typ
    źródła, więc jego miejsce w kolejności nie ma znaczenia.

    Argument `zachowuj_odnosniki` pochodzi z konfiguracji i decyduje o tym, czy
    na końcu treści artykułu powstaje wykaz odnośników.
    """
    from gnb.extractors.markdown import EkstraktorMarkdown
    from gnb.extractors.napisy import EkstraktorNapisow
    from gnb.extractors.plik_csv import EkstraktorCsv
    from gnb.extractors.strona_www import EkstraktorStronyWww
    from gnb.extractors.tekst import EkstraktorTekstu

    return RejestrEkstraktorow(
        (
            EkstraktorStronyWww(zachowuj_odnosniki=zachowuj_odnosniki),
            EkstraktorMarkdown(),
            EkstraktorCsv(),
            EkstraktorNapisow(),
            EkstraktorTekstu(),
        )
    )
