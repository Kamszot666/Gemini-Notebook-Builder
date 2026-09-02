"""Escapowanie treści przed wstawieniem jej do odpowiedzi HTML interfejsu.

Sekcja jedenasta punkt drugi CLAUDE.md: treść pobrana ze źródeł nigdy nie trafia
do przeglądarki jako HTML, zawsze jako tekst z pełnym escapowaniem. Ten moduł
jest jedynym miejscem, przez które przechodzi każdy napis pochodzący ze źródła,
z nazwy pliku, z komunikatu błędu i z pola użytkownika, zanim znajdzie się
w odpowiedzi serwera. Widoki nie wolno budować przez wstawianie surowych napisów.
"""

from __future__ import annotations

import html


def escapuj(wartosc: object) -> str:
    """Zwraca wartość zescapowaną do bezpiecznego wstawienia w HTML.

    Escapowane są znaki „&”, „<”, „>” oraz oba rodzaje cudzysłowu. Dzięki
    escapowaniu cudzysłowów ten sam wynik jest bezpieczny zarówno w treści
    elementu, jak i w wartości atrybutu ujętej w cudzysłów.
    """
    return html.escape(str(wartosc), quote=True)


def atrybut(nazwa: str, wartosc: object) -> str:
    """Buduje jeden atrybut HTML w postaci ``nazwa="zescapowana wartość"``.

    Nazwa atrybutu nie jest escapowana, bo pochodzi wyłącznie z kodu widoku,
    nigdy z danych. Wartość jest zawsze escapowana.
    """
    return f'{nazwa}="{escapuj(wartosc)}"'
