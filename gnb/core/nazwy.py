"""Sanityzacja nazw projektów i plików do postaci bezpiecznej dla Windows.

Reguły pochodzą z sekcji piętnastej CLAUDE.md: odrzucenie znaków niedozwolonych
i znaków sterujących, nazw zarezerwowanych systemu Windows oraz kropek i spacji
na końcu nazwy, a także ograniczenie długości wobec granicy dwustu sześćdziesięciu
znaków całej ścieżki.

Funkcje w tym module nie tworzą katalogów ani nie dotykają dysku. Wyłącznie
przetwarzają napisy.
"""

from __future__ import annotations

import re

from gnb.core.wyjatki import BladTrwaly

_ZNAKI_NIEDOZWOLONE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIELE_PODKRESLEN = re.compile(r"_{2,}")
_SLOWA = re.compile(r"\w+")

_NAZWY_ZAREZERWOWANE = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{numer}" for numer in range(1, 10)}
    | {f"LPT{numer}" for numer in range(1, 10)}
)

MAKSYMALNA_DLUGOSC_NAZWY = 100
MAKSYMALNA_LICZBA_SLOW_W_NAZWIE = 8
_NAZWA_AWARYJNA_PROJEKTU = "projekt"


def _oczysc(nazwa: str) -> str:
    """Zamienia znaki niedozwolone na podkreślenie i przycina nazwę.

    Kolejno: znaki niedozwolone i sterujące zamieniane są na podkreślenie,
    ciągi podkreśleń skracane do jednego, usuwane są białe znaki oraz końcowe
    kropki i spacje, a długość jest ograniczana. Przycięcie długości jest
    powtórzone po obcięciu, bo obcięcie mogło odsłonić kropkę lub spację.
    """
    oczyszczona = _ZNAKI_NIEDOZWOLONE.sub("_", nazwa)
    oczyszczona = _WIELE_PODKRESLEN.sub("_", oczyszczona).strip().rstrip(". ")
    oczyszczona = oczyszczona[:MAKSYMALNA_DLUGOSC_NAZWY].strip().rstrip(". ")
    return oczyszczona


def sanityzuj_nazwe_projektu(nazwa: str) -> str:
    """Zwraca nazwę projektu w postaci bezpiecznej dla systemu plików Windows.

    Nazwa pusta po oczyszczeniu oraz nazwa zarezerwowana w systemie Windows
    kończą się błędem trwałym z czytelnym komunikatem, ponieważ takiej nazwy nie
    da się bezpiecznie naprawić automatycznie i decyzję musi podjąć użytkownik.
    """
    oczyszczona = _oczysc(nazwa)
    if not oczyszczona:
        raise BladTrwaly("Nazwa projektu jest pusta po oczyszczeniu. Podaj inną nazwę.")
    if oczyszczona.upper() in _NAZWY_ZAREZERWOWANE:
        raise BladTrwaly(
            f"Nazwa projektu „{oczyszczona}” jest zarezerwowana w systemie Windows. "
            "Podaj inną nazwę."
        )
    return oczyszczona


def wygeneruj_nazwe_projektu(podstawa: str) -> str:
    """Tworzy krótką, bezpieczną nazwę projektu na podstawie dowolnego napisu.

    Używane, gdy użytkownik nie poda nazwy projektu. Funkcja bierze początkowe
    słowa podanego napisu, łączy je podkreśleniami i przepuszcza przez
    sanityzację. Gdy nie da się wydobyć nic sensownego, zwraca nazwę awaryjną.
    """
    slowa = _SLOWA.findall(podstawa.lower())
    trzon = "_".join(slowa[:MAKSYMALNA_LICZBA_SLOW_W_NAZWIE])
    if not trzon:
        return _NAZWA_AWARYJNA_PROJEKTU
    try:
        return sanityzuj_nazwe_projektu(trzon)
    except BladTrwaly:
        return _NAZWA_AWARYJNA_PROJEKTU


def bezpieczna_nazwa_pliku(propozycja: str, *, nazwa_awaryjna: str) -> str:
    """Zwraca bezpieczną nazwę pliku wynikowego bez rozszerzenia.

    Reguły oczyszczania są takie same jak dla nazwy projektu, ale nazwa pusta
    lub zarezerwowana nie jest tu błędem. W takim wypadku zwracana jest nazwa
    awaryjna, którą zwykle jest identyfikator źródła.
    """
    oczyszczona = _oczysc(propozycja)
    if not oczyszczona or oczyszczona.upper() in _NAZWY_ZAREZERWOWANE:
        return nazwa_awaryjna
    return oczyszczona
