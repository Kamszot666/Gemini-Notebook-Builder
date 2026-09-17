"""Stan globalnego skrótu widoczny w interfejsie: aktywny projekt i ostatni komunikat.

Oba elementy żyją wyłącznie w pamięci bieżącego uruchomienia serwera, chronione
tym samym rodzajem zamka co rejestr zadań w ``gnb.ui.zadania``. Ten moduł nie
zależy od Windows — interfejs używa go niezależnie od tego, czy moduł
``gnb.hotkeys`` jest w ogóle aktywny na danym systemie, żeby strony dało się
wyrenderować i przetestować także na Linuksie.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime


class AktywnyProjektSkrotu:
    """Nazwa co najwyżej jednego projektu, do którego skrót dodaje nowe źródła.

    Wybór jest jawny — użytkownik ustawia go przyciskiem na stronie projektu —
    a nie „ostatnio otwartym projektem”. Powód jest opisany w sekcji dwunastej
    CLAUDE.md: samo zajrzenie na stronę innego projektu w przeglądarce nie
    może po cichu przenieść miejsca, do którego trafia materiał dodany
    skrótem, bo źródło w złym projekcie jest błędem poprawności danych, która
    w hierarchii priorytetów z sekcji czwartej stoi nad wygodą.

    Po restarcie serwera nie ma aktywnego projektu, dopóki użytkownik nie
    wybierze go ponownie — wybór nie jest nigdzie trwale zapisywany.
    """

    def __init__(self) -> None:
        self._zamek = threading.Lock()
        self._nazwa: str | None = None

    def ustaw(self, nazwa: str) -> None:
        with self._zamek:
            self._nazwa = nazwa

    def aktualny(self) -> str | None:
        with self._zamek:
            return self._nazwa


@dataclass(frozen=True, slots=True)
class KomunikatSkrotu:
    """Jeden zapisany wynik naciśnięcia globalnego skrótu, do pokazania w interfejsie."""

    tekst: str
    sukces: bool
    czas: datetime


class OstatniKomunikatSkrotu:
    """Trzyma jeden, najnowszy wynik naciśnięcia globalnego skrótu.

    Dźwięk z ``gnb.hotkeys`` jest natychmiastowym potwierdzeniem w chwili
    naciśnięcia skrótu; ten komunikat jest jego trwałym, tekstowym
    odpowiednikiem, do sprawdzenia później na stronie interfejsu — zgodnie
    z decyzją czwartą sekcji dwunastej CLAUDE.md o potwierdzeniu bez
    przenoszenia fokusu.
    """

    def __init__(self) -> None:
        self._zamek = threading.Lock()
        self._ostatni: KomunikatSkrotu | None = None

    def ustaw(self, tekst: str, *, sukces: bool) -> None:
        with self._zamek:
            self._ostatni = KomunikatSkrotu(tekst=tekst, sukces=sukces, czas=datetime.now(UTC))

    def aktualny(self) -> KomunikatSkrotu | None:
        with self._zamek:
            return self._ostatni
