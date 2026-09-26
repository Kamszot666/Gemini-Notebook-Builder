"""Escapowanie treści przed wstawieniem jej do odpowiedzi HTML interfejsu.

Sekcja jedenasta punkt drugi CLAUDE.md: treść pobrana ze źródeł nigdy nie trafia
do przeglądarki jako HTML, zawsze jako tekst z pełnym escapowaniem. Ten moduł
jest jedynym miejscem, przez które przechodzi każdy napis pochodzący ze źródła,
z nazwy pliku, z komunikatu błędu i z pola użytkownika, zanim znajdzie się
w odpowiedzi serwera. Widoki nie wolno budować przez wstawianie surowych napisów.
"""

from __future__ import annotations

import html
import re


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


_WZORZEC_ADRESU_HTTP = re.compile(r"https?://\S+")
_ZNAKI_KONCA_ZDANIA = ".,;:!?)]}»”\"'"


def tekst_z_odnosnikami(tekst: str) -> str:
    """Escapuje tekst i zamienia adresy http oraz https na odnośniki w nowej karcie.

    Adres innego schematu, na przykład ``javascript:``, nigdy nie staje się
    odnośnikiem, bo wzorzec dopasowuje wyłącznie ``http://`` i ``https://``.
    Znaki interpunkcji doklejone do adresu na końcu zdania zostają poza
    odnośnikiem. Bezpieczeństwo nie zależy od zawartości adresu: cały dopasowany
    fragment przechodzi przez ``escapuj`` w atrybucie ``href`` i w widocznym
    tekście, więc adres z doklejonym cudzysłowem albo nawiasem ostrym nie
    wyrywa się z atrybutu i nie wstawia własnego znacznika.
    """
    fragmenty: list[str] = []
    pozycja = 0
    for dopasowanie in _WZORZEC_ADRESU_HTTP.finditer(tekst):
        koniec = dopasowanie.end()
        while koniec > dopasowanie.start() and tekst[koniec - 1] in _ZNAKI_KONCA_ZDANIA:
            koniec -= 1
        adres_surowy = tekst[dopasowanie.start() : koniec]
        if len(adres_surowy) <= len("https://"):
            continue
        fragmenty.append(escapuj(tekst[pozycja : dopasowanie.start()]))
        adres = escapuj(adres_surowy)
        fragmenty.append(
            f'<a href="{adres}" target="_blank" rel="noopener noreferrer">'
            f"{adres} (otwiera się w nowej karcie)</a>"
        )
        pozycja = koniec
    fragmenty.append(escapuj(tekst[pozycja:]))
    return "".join(fragmenty)
