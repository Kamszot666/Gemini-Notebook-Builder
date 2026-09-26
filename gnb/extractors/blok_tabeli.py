"""Budowa bloku tabeli z wierszy komórek: wspólne dla arkuszy i prezentacji.

Wewnętrzny format bloku tabeli jest ustalony w `gnb.extractors.bloki_markdown`:
wiersze rozdzielone znakiem nowej linii, komórki rozdzielone tabulatorem,
pierwszy wiersz jest nagłówkiem. Ten moduł zamienia listę wierszy na taki blok
i wyrównuje szerokość wierszy, bo wiersz z inną liczbą komórek niż nagłówek
uniemożliwiałby zapis tabeli w Markdown bez utraty znaczenia.

Moduł nie zgaduje, który wiersz jest nagłówkiem: pierwszy wiersz jest nim
z założenia, tak samo jak w plikach CSV.
"""

from __future__ import annotations

from collections.abc import Sequence

from gnb.core.model import BlokTresci
from gnb.core.stale import RodzajBloku


def oczysc_komorke(tekst: str) -> str:
    """Sprowadza treść komórki do jednego wiersza, bez tabulatorów i znaków nowej linii."""
    return " ".join(tekst.replace("\t", " ").split())


def blok_tabeli(wiersze: Sequence[Sequence[str]]) -> BlokTresci | None:
    """Buduje blok tabeli albo zwraca ``None``, gdy nie ma żadnej niepustej komórki.

    Wiersze całkiem puste są pomijane. Puste komórki na końcu każdego wiersza są
    odcinane, a następnie wszystkie wiersze są uzupełniane pustymi komórkami do
    szerokości najdłuższego z nich, żeby tabela miała stałą liczbę kolumn.
    """
    oczyszczone = [[oczysc_komorke(komorka) for komorka in wiersz] for wiersz in wiersze]
    niepuste = [wiersz for wiersz in oczyszczone if any(wiersz)]
    if not niepuste:
        return None
    przyciete = [_bez_pustych_na_koncu(wiersz) for wiersz in niepuste]
    szerokosc = max(len(wiersz) for wiersz in przyciete)
    wyrownane = [wiersz + [""] * (szerokosc - len(wiersz)) for wiersz in przyciete]
    return BlokTresci(
        rodzaj=RodzajBloku.TABELA,
        poziom=0,
        tresc="\n".join("\t".join(wiersz) for wiersz in wyrownane),
    )


def _bez_pustych_na_koncu(wiersz: list[str]) -> list[str]:
    koniec = len(wiersz)
    while koniec > 0 and not wiersz[koniec - 1]:
        koniec -= 1
    return wiersz[:koniec]
