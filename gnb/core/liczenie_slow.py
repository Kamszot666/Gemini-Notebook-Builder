"""Jedna wspólna definicja liczenia słów i znaków dla całego projektu.

Liczba słów to liczba niepustych fragmentów tekstu po podziale znormalizowanego
tekstu na dowolnych ciągach białych znaków. Ta sama funkcja jest używana wszędzie,
gdzie projekt odwołuje się do limitu słów notatnika, żeby wynik był spójny między
manifestem, raportem i sprawdzaniem limitów.

Moduł nie normalizuje tekstu i nie usuwa metadanych technicznych. Zakłada, że
dostaje tekst już znormalizowany i pozbawiony metadanych, które nie są treścią.
"""

from __future__ import annotations


def policz_slowa(tekst: str) -> int:
    """Zwraca liczbę słów w tekście.

    Słowem jest każdy niepusty fragment powstały po podziale tekstu na dowolnych
    ciągach białych znaków. Wielokrotne spacje, tabulatory i znaki nowej linii
    są traktowane tak samo jak pojedyncza spacja, a tekst pusty ma zero słów.
    """
    return len(tekst.split())


def policz_znaki(tekst: str) -> int:
    """Zwraca liczbę znaków tekstu, licząc też białe znaki wewnątrz treści."""
    return len(tekst)
