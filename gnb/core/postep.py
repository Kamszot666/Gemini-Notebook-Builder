"""Zdarzenia postępu potoku przetwarzania.

Moduł definiuje wyłącznie typ zdarzenia postępu oraz wyliczenie faz potoku. Potok
wywołuje opcjonalne wywołanie zwrotne z kolejnymi zdarzeniami na granicach faz
oraz po każdym przetworzonym źródle. Interfejs WWW zamienia te zdarzenia na
dławione komunikaty w regionie ``role="status"``.

Moduł jest osobny po to, żeby pakiet interfejsu i rejestr zadań w tle nie musiały
importować całego potoku dla samego typu zdarzenia. Nie zawiera żadnej logiki
przetwarzania.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class FazaPotoku(StrEnum):
    """Faza potoku, w której powstało zdarzenie postępu.

    Kolejność wartości odpowiada kolejności etapów z sekcji ósmej CLAUDE.md
    w części obsługiwanej przez dotychczasowe etapy. Faza pobierania napisów jest
    osobna od fazy pobierania stron, bo filmy pobierają się po kolei, a strony
    równolegle. Faza OCR jest zgłaszana wewnątrz ekstrakcji, dla skanu PDF strona
    po stronie, żeby użytkownik nie został przy niemym oknie przez kilkanaście
    minut rozpoznawania grubego skanu.
    """

    POBIERANIE_STRON = "pobieranie_stron"
    POBIERANIE_NAPISOW = "pobieranie_napisow"
    EKSTRAKCJA = "ekstrakcja"
    OCR = "ocr"
    DEDUPLIKACJA = "deduplikacja"
    PAKOWANIE = "pakowanie"
    ZAKONCZENIE = "zakonczenie"


@dataclass(frozen=True, slots=True)
class ZdarzeniePostepu:
    """Pojedyncze zdarzenie postępu przekazywane do wywołania zwrotnego.

    Pole `wykonano` i `wszystkich` opisują postęp w obrębie fazy. Dla faz bez
    naturalnego licznika, na przykład deduplikacji, `wszystkich` wynosi jeden,
    a `wykonano` zero na początku i jeden na końcu. Pole `opis` to gotowe zdanie
    po polsku, którego interfejs może użyć wprost, po dławieniu.
    """

    faza: FazaPotoku
    wykonano: int
    wszystkich: int
    opis: str


# Podpis opcjonalnego wywołania zwrotnego przyjmowanego przez potok. Brak
# wywołania zwrotnego oznacza pracę bez raportowania postępu, jak w wierszu
# poleceń.
WywolanieZwrotnePostepu = Callable[[ZdarzeniePostepu], None]
