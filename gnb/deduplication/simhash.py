"""SimHash na shinglach słów oraz porównanie sekwencyjne krótkich tekstów.

Trzeci etap deduplikacji z sekcji szesnastej CLAUDE.md wykrywa teksty bliskie,
ale nie identyczne: przedruk z jednym przeredagowanym zdaniem, ten sam artykuł
w dwóch serwisach, tekst z dodaną notką redakcyjną. Dla tekstów dłuższych służy
do tego SimHash liczony z zachodzących na siebie trójek słów, a podobieństwo
wynika z odległości Hamminga między odciskami. Dla tekstów krótkich, w których
SimHash jest niestabilny, podobieństwo liczy dopasowanie sekwencyjne z modułu
`difflib` biblioteki standardowej.

Funkcja skrótu shingla jest celowo `blake2b`, a nie wbudowane `hash`, ponieważ
`hash` dla łańcuchów znaków jest losowany przy każdym uruchomieniu procesu, a
decyzja o duplikacie musi być powtarzalna między uruchomieniami.
"""

from __future__ import annotations

import hashlib
from difflib import SequenceMatcher

LICZBA_BITOW = 64
DOMYSLNY_ROZMIAR_SHINGLA = 3

_MASKA = (1 << LICZBA_BITOW) - 1


def simhash_tekstu(tekst: str, *, rozmiar_shingla: int = DOMYSLNY_ROZMIAR_SHINGLA) -> int:
    """Zwraca 64-bitowy odcisk SimHash tekstu, liczony z shingli słów.

    Shingiel to ciąg kolejnych słów o długości `rozmiar_shingla`. Gdy tekst ma
    mniej słów niż jeden shingiel, całą jego listę słów traktujemy jako
    pojedynczy shingiel, żeby krótki tekst też dostał odcisk zamiast zera.
    """
    slowa = tekst.split()
    if not slowa:
        return 0
    if len(slowa) < rozmiar_shingla:
        shingle = [" ".join(slowa)]
    else:
        shingle = [
            " ".join(slowa[i : i + rozmiar_shingla])
            for i in range(len(slowa) - rozmiar_shingla + 1)
        ]

    wagi = [0] * LICZBA_BITOW
    for shingiel in shingle:
        odcisk = _skrot_shingla(shingiel)
        for bit in range(LICZBA_BITOW):
            if odcisk & (1 << bit):
                wagi[bit] += 1
            else:
                wagi[bit] -= 1

    wynik = 0
    for bit in range(LICZBA_BITOW):
        if wagi[bit] > 0:
            wynik |= 1 << bit
    return wynik


def _skrot_shingla(shingiel: str) -> int:
    """Zwraca powtarzalny 64-bitowy skrót jednego shingla."""
    surowy = hashlib.blake2b(shingiel.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(surowy, "big")


def odleglosc_hamminga(pierwszy: int, drugi: int) -> int:
    """Zwraca liczbę różniących się bitów dwóch 64-bitowych odcisków."""
    return ((pierwszy ^ drugi) & _MASKA).bit_count()


def podobienstwo_simhash(pierwszy: int, drugi: int) -> float:
    """Zamienia odległość Hamminga na podobieństwo w zakresie od zera do jednego."""
    return 1.0 - odleglosc_hamminga(pierwszy, drugi) / LICZBA_BITOW


def podobienstwo_sekwencyjne(pierwszy: str, drugi: str) -> float:
    """Zwraca podobieństwo dwóch krótkich tekstów jako współczynnik dopasowania.

    Wynik jest współczynnikiem `SequenceMatcher.ratio`: jeden oznacza teksty
    identyczne, zero — brak wspólnych fragmentów. Metoda jest kosztowna
    obliczeniowo, dlatego stosuje się ją tylko do tekstów krótkich, wybieranych
    przez orkiestrator na podstawie liczby słów.
    """
    return SequenceMatcher(None, pierwszy, drugi, autojunk=False).ratio()
