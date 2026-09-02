"""Trzy niezależne limity notatnika w jednym miejscu.

Sekcja dziewiąta CLAUDE.md wymienia trzy ograniczenia traktowane jako niezależne:
liczbę źródeł w notatniku, liczbę słów w pojedynczym źródle oraz rozmiar pliku
w bajtach. Ten moduł opisuje dwa ograniczenia treści, czyli liczbę słów i rozmiar,
i udostępnia wspólne funkcje sprawdzające. Trzecie ograniczenie, liczba źródeł,
dotyczy całego notatnika, a nie pojedynczej treści, więc jest pilnowane w potoku.

Liczba słów jest liczona wspólną definicją z modułu `gnb.core.liczenie_slow`, żeby
wynik był spójny z manifestem, raportem i regułą wyboru formatu. Rozmiar liczy się
w bajtach kodowania UTF-8, ponieważ w takim kodowaniu zapisywane są pliki wynikowe.

Nagłówek metadanych nie jest wliczany do limitów. Zgodnie z modułem
`gnb.output.naglowek_metadanych` limity dotyczą samej treści dokumentu, bo
nagłówek jest informacją o źródle, a nie jego treścią. Wywołujący podaje więc tu
treść bez nagłówka.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnb.core.liczenie_slow import policz_slowa

_BAJTOW_W_MEGABAJCIE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class LimityPakowania:
    """Bezpieczne limity robocze pojedynczej treści: liczba słów i rozmiar w bajtach.

    Wartości pochodzą z konfiguracji projektu. Domyślne bezpieczne limity robocze
    z sekcji dziewiątej CLAUDE.md to 480 000 słów oraz 190 megabajtów, przy czym
    margines wobec twardych limitów notatnika istnieje dlatego, że sposób liczenia
    słów po stronie Google może różnić się od naszego.
    """

    limit_slow: int
    limit_bajtow: int

    @classmethod
    def z_konfiguracji(
        cls, bezpieczny_limit_slow: int, bezpieczny_limit_mb: int
    ) -> LimityPakowania:
        """Buduje limity z pól konfiguracji, przeliczając megabajty na bajty."""
        return cls(
            limit_slow=bezpieczny_limit_slow,
            limit_bajtow=bezpieczny_limit_mb * _BAJTOW_W_MEGABAJCIE,
        )


def liczba_bajtow(tekst: str) -> int:
    """Zwraca rozmiar tekstu w bajtach kodowania UTF-8, czyli tak, jak trafi na dysk."""
    return len(tekst.encode("utf-8"))


def miesci_sie(tekst: str, limity: LimityPakowania) -> bool:
    """Prawda, gdy treść mieści się jednocześnie w limicie słów i w limicie rozmiaru.

    Oba ograniczenia są sprawdzane niezależnie i muszą być spełnione naraz.
    Pusty tekst mieści się zawsze.
    """
    return policz_slowa(tekst) <= limity.limit_slow and liczba_bajtow(tekst) <= limity.limit_bajtow


def przekracza_limit(tekst: str, limity: LimityPakowania) -> bool:
    """Prawda, gdy treść przekracza którykolwiek z dwóch limitów treści."""
    return not miesci_sie(tekst, limity)
