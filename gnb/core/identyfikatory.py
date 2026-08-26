"""Deterministyczne identyfikatory źródeł oraz sumy kontrolne treści.

Identyfikator źródła musi być stabilny między uruchomieniami aplikacji, bo na
nim opiera się wznowienie pracy i pamięć podręczna. Jest wyprowadzany z typu
źródła i z sumy kontrolnej jego pochodzenia: bajtów pliku albo bajtów tekstu
wklejonego zakodowanego w UTF-8.

Pełna suma kontrolna to skrót SHA-256 zapisany szesnastkowo. Identyfikator
źródła to wartość typu źródła połączona myślnikiem z pierwszymi szesnastoma
znakami tej sumy. Skrócona postać jest czytelna przy odsłuchu syntezatorem mowy,
a pełną sumę przechowuje osobne pole `checksum` obiektu `Zrodlo`.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from gnb.core.stale import TypZrodla

DLUGOSC_SKROTU_W_IDENTYFIKATORZE = 16
_ROZMIAR_BLOKU_ODCZYTU = 65536
_ZNAK_BOM = "\ufeff"


def suma_kontrolna_bajtow(dane: bytes) -> str:
    """Zwraca pełną, szesnastkową sumę kontrolną SHA-256 podanych bajtów."""
    return hashlib.sha256(dane).hexdigest()


def suma_kontrolna_pliku(sciezka: Path) -> str:
    """Zwraca pełną sumę kontrolną SHA-256 zawartości pliku, czytając go blokami.

    Odczyt blokami pozwala policzyć sumę także dla dużych plików bez wczytywania
    całej zawartości do pamięci naraz.
    """
    skrot = hashlib.sha256()
    with sciezka.open("rb") as plik:
        while blok := plik.read(_ROZMIAR_BLOKU_ODCZYTU):
            skrot.update(blok)
    return skrot.hexdigest()


def suma_kontrolna_tekstu_wklejonego(tekst: str) -> str:
    """Zwraca pełną sumę kontrolną SHA-256 surowego tekstu wklejonego.

    Tekst jest kodowany do UTF-8. Jeżeli zaczyna się znakiem kolejności bajtów,
    ten znak jest wcześniej odcinany, żeby ten sam tekst wklejony z tym znakiem
    i bez niego dawał ten sam identyfikator.
    """
    if tekst.startswith(_ZNAK_BOM):
        tekst = tekst[len(_ZNAK_BOM) :]
    return suma_kontrolna_bajtow(tekst.encode("utf-8"))


def identyfikator_zrodla(typ: TypZrodla, suma_kontrolna_pochodzenia: str) -> str:
    """Buduje stabilny identyfikator źródła z typu i skróconej sumy kontrolnej.

    Identyfikator ma postać wartości typu źródła, myślnika oraz pierwszych
    szesnastu znaków szesnastkowych sumy kontrolnej pochodzenia. Ten sam plik
    albo ten sam tekst wklejony zawsze daje ten sam identyfikator, co jest
    zachowaniem oczekiwanym i wykorzystywanym przez wznowienie pracy.
    """
    skrot = suma_kontrolna_pochodzenia[:DLUGOSC_SKROTU_W_IDENTYFIKATORZE]
    return f"{typ.value}-{skrot}"
