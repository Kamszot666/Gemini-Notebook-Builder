"""Składanie treści jednego pliku wynikowego z fragmentów wraz z nagłówkami.

Plik wynikowy może zawierać więcej niż jedno źródło, gdy użytkownik przypisał
kilka małych źródeł do wspólnej grupy tematycznej. Sekcja dziesiąta CLAUDE.md
wymaga wtedy nagłówka metadanych przed treścią każdego fragmentu, pozwalającego
ustalić jego pochodzenie.

Fragmenty są oddzielone jednym pustym wierszem i wierszem „Kolejny fragment tego
pliku:”, żeby granica między materiałami była jednoznaczna także przy odsłuchu
czytnikiem ekranu. Nie ma linii ozdobnych ani separatorów ze znaków.

Plik grupy, której skład nie zmieścił się w jednym pliku, dostaje na początku
wiersz z nazwą grupy i numerem części. Ten sam mechanizm nie dotyczy pojedynczego
źródła podzielonego na części — tam oznaczenie części jest polem nagłówka
metadanych, budowanym przez `gnb.output.naglowek_metadanych`.
"""

from __future__ import annotations

from collections.abc import Sequence

from gnb.output.naglowek_metadanych import polacz_z_trescia

WIERSZ_KOLEJNEGO_FRAGMENTU = "Kolejny fragment tego pliku:"


def oznaczenie_pliku_grupy(nazwa_grupy: str, numer_czesci: int, liczba_czesci: int) -> str:
    """Buduje wiersz nagłówkowy pliku grupy podzielonej na kilka plików."""
    return f"Plik grupy „{nazwa_grupy}”, część {numer_czesci} z {liczba_czesci}."


def zloz_plik(
    fragmenty: Sequence[tuple[str, str]],
    *,
    oznaczenie_pliku: str = "",
) -> str:
    """Skleja treść pliku z par (nagłówek, treść), oddzielając fragmenty czytelnie.

    Każdy fragment jest złączeniem nagłówka i treści oddzielonych jednym pustym
    wierszem. Drugi i kolejny fragment poprzedza wiersz „Kolejny fragment tego
    pliku:”. Argument `oznaczenie_pliku`, jeżeli podany, trafia na sam początek,
    przed pierwszym nagłówkiem.
    """
    czesci_tekstu: list[str] = []
    if oznaczenie_pliku:
        czesci_tekstu.append(oznaczenie_pliku)

    for indeks, (naglowek, tresc) in enumerate(fragmenty):
        if indeks > 0:
            czesci_tekstu.append(WIERSZ_KOLEJNEGO_FRAGMENTU)
        czesci_tekstu.append(polacz_z_trescia(naglowek, tresc))

    return "\n\n".join(czesci_tekstu)
