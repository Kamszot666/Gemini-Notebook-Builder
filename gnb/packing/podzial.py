"""Podział pojedynczej treści przekraczającej limit na części.

Sekcja dziesiąta CLAUDE.md: gdy pojedyncze źródło przekracza limit, dzieli się je
na części na granicy nagłówka lub akapitu, nigdy w środku zdania. Ten moduł
realizuje podział na znormalizowanym tekście, w którym nagłówek ani akapit nie są
osobno oznaczone, więc granicą akapitu jest pusty wiersz.

Hierarchia granic podziału, każda niższa używana tylko wtedy, gdy wyższa jednostka
sama nie mieści się w limicie:

1. Bloki rozdzielone pustym wierszem, czyli akapity, nagłówki i listy.
2. Pojedyncze wiersze wewnątrz bloku, obecne tam, gdzie źródło miało twarde
   złamania wiersza.
3. Zdania, wydzielane po kropce, wykrzykniku, znaku zapytania albo wielokropku,
   z zachowaniem znaku kończącego przy zdaniu.
4. Granica słowa, czyli biały znak, używana w ostateczności.

Podział na poziomie słowa oznacza cięcie wewnątrz zdania, więc dokłada ostrzeżenie.
Ostrzeżenie przechodzi tę samą drogę co pominięcie: trafia do manifestu i do
raportu, żeby kompromis był widoczny dla użytkownika, a nie cichy. Pojedyncze
słowo bez białych znaków dłuższe niż limit rozmiaru jest zapisywane w całości
z osobnym ostrzeżeniem, ponieważ druga zasada priorytetów zabrania utraty treści,
a nie ma sposobu podzielenia takiego ciągu bez cięcia w środku znaku.

Moduł pracuje wyłącznie na tekście. Nie dokłada nagłówka metadanych ani oznaczenia
części, bo to zadanie warstwy składającej pliki wynikowe.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from gnb.packing.limity import LimityPakowania, miesci_sie

# Podział na zdania: po znaku kończącym zdanie i następującym po nim białym znaku.
# Wzorzec zachowuje znak kończący przy zdaniu poprzedzającym, bo bez kropki zdanie
# przestaje być zdaniem.
_GRANICA_ZDANIA = re.compile(r"(?<=[.!?…])\s+")

OSTRZEZENIE_PODZIAL_W_ZDANIU = (
    "Podział źródła został wykonany wewnątrz zdania, na granicy słowa, ponieważ "
    "pojedyncze zdanie przekraczało bezpieczny limit. Sprawdź styk części."
)
OSTRZEZENIE_SLOWO_PONAD_LIMIT = (
    "Fragment bez białych znaków przekracza bezpieczny limit rozmiaru i został "
    "zapisany w całości, żeby nie stracić treści. Sprawdź, czy to nie jest zrzut "
    "danych zamiast tekstu."
)


@dataclass(frozen=True, slots=True)
class WynikPodzialu:
    """Wynik podziału jednej treści: lista części oraz ostrzeżenia o kompromisach.

    Gdy treść mieści się w limicie, lista części ma jeden element równy tekstowi
    wejściowemu, a lista ostrzeżeń jest pusta. Każda część z osobna mieści się
    w limicie słów i w limicie rozmiaru, z jedynym wyjątkiem opisanym przez
    ostrzeżenie o fragmencie bez białych znaków.
    """

    czesci: list[str]
    ostrzezenia: list[str] = field(default_factory=list)


def podziel_na_czesci(tekst: str, limity: LimityPakowania) -> WynikPodzialu:
    """Dzieli tekst na możliwie najmniejszą liczbę części mieszczących się w limitach.

    Treść mieszcząca się w limicie jest zwracana bez zmian jako jedna część.
    W przeciwnym razie tekst jest sklejany z jednostek coraz drobniejszego
    poziomu, tak aby granica podziału wypadała jak najwyżej w hierarchii.
    """
    if miesci_sie(tekst, limity):
        return WynikPodzialu(czesci=[tekst])

    ostrzezenia: list[str] = []
    czesci = _podziel_rekurencyjnie(tekst, limity, poziom=0, ostrzezenia=ostrzezenia)
    # Kolejność ostrzeżeń nie niesie znaczenia, a powtórzenia tylko zaśmiecają
    # raport, więc zostają wyłącznie unikalne, w kolejności pierwszego wystąpienia.
    unikalne = list(dict.fromkeys(ostrzezenia))
    return WynikPodzialu(czesci=czesci, ostrzezenia=unikalne)


def _na_bloki(tekst: str) -> list[str]:
    return [blok for blok in tekst.split("\n\n") if blok]


def _na_wiersze(tekst: str) -> list[str]:
    return [wiersz for wiersz in tekst.split("\n") if wiersz]


def _na_zdania(tekst: str) -> list[str]:
    return [zdanie for zdanie in _GRANICA_ZDANIA.split(tekst) if zdanie]


def _na_slowa(tekst: str) -> list[str]:
    return tekst.split()


# Kolejne poziomy podziału. Każdy zwraca listę jednostek oraz łącznik, którym
# jednostki są z powrotem sklejane w część. Poziom słowa jest ostatni, bo cięcie
# na granicy słowa jest cięciem wewnątrz zdania.
_POZIOMY: tuple[tuple[Callable[[str], list[str]], str], ...] = (
    (_na_bloki, "\n\n"),
    (_na_wiersze, "\n"),
    (_na_zdania, " "),
    (_na_slowa, " "),
)
_POZIOM_SLOWA = len(_POZIOMY) - 1


def _podziel_rekurencyjnie(
    tekst: str,
    limity: LimityPakowania,
    *,
    poziom: int,
    ostrzezenia: list[str],
) -> list[str]:
    """Dzieli tekst, sklejając jednostki danego poziomu, a zbyt duże schodząc niżej."""
    if poziom >= len(_POZIOMY):
        # Poniżej poziomu słowa nie da się już zejść bez cięcia w środku znaku.
        # Fragment jest zwracany w całości, z ostrzeżeniem dla użytkownika.
        ostrzezenia.append(OSTRZEZENIE_SLOWO_PONAD_LIMIT)
        return [tekst]

    rozbij, laczik = _POZIOMY[poziom]
    jednostki = rozbij(tekst)
    if len(jednostki) <= 1:
        # Ten poziom niczego nie rozdzielił, więc próbujemy niższego.
        return _podziel_rekurencyjnie(tekst, limity, poziom=poziom + 1, ostrzezenia=ostrzezenia)

    if poziom == _POZIOM_SLOWA:
        # Doszło do realnego cięcia na granicy słowa, czyli wewnątrz zdania.
        ostrzezenia.append(OSTRZEZENIE_PODZIAL_W_ZDANIU)

    return _sklej_jednostki(jednostki, laczik, limity, poziom=poziom, ostrzezenia=ostrzezenia)


def _sklej_jednostki(
    jednostki: Sequence[str],
    laczik: str,
    limity: LimityPakowania,
    *,
    poziom: int,
    ostrzezenia: list[str],
) -> list[str]:
    """Skleja jednostki w części, otwierając nową część przed przekroczeniem limitu."""
    czesci: list[str] = []
    biezaca = ""

    for jednostka in jednostki:
        kandydat = f"{biezaca}{laczik}{jednostka}" if biezaca else jednostka
        if miesci_sie(kandydat, limity):
            biezaca = kandydat
            continue

        if biezaca:
            czesci.append(biezaca)
            biezaca = ""

        if miesci_sie(jednostka, limity):
            biezaca = jednostka
            continue

        drobniejsze = _podziel_rekurencyjnie(
            jednostka, limity, poziom=poziom + 1, ostrzezenia=ostrzezenia
        )
        czesci.extend(drobniejsze[:-1])
        biezaca = drobniejsze[-1] if drobniejsze else ""

    if biezaca:
        czesci.append(biezaca)
    return czesci
