"""Normalizacja tekstu źródła przed policzeniem słów i zapisaniem wyników.

Zakres normalizacji: końce wierszy sprowadzane są do pojedynczego znaku nowej
linii, znaki Unicode do postaci NFC, z końców wierszy usuwane są białe znaki,
ciągi trzech i więcej pustych wierszy skracane są do jednego pustego wiersza,
a puste wiersze z początku i końca tekstu są usuwane.

Moduł nie wykrywa kodowania i nie interpretuje struktury dokumentu. Zakłada, że
dostaje tekst już rozkodowany do postaci znakowej.
"""

from __future__ import annotations

import re
import unicodedata

from gnb.core.liczenie_slow import policz_slowa, policz_znaki
from gnb.core.model import DokumentZnormalizowany

_NADMIAROWE_PUSTE_WIERSZE = re.compile(r"\n{3,}")


def znormalizuj(tekst: str) -> str:
    """Sprowadza tekst do jednolitej postaci przed liczeniem słów i zapisem.

    Funkcja jest idempotentna: ponowne wywołanie na własnym wyniku niczego już
    nie zmienia. Kolejność kroków jest ustalona, bo zamiana końców wierszy musi
    poprzedzać usuwanie białych znaków z końców wierszy.
    """
    tekst = tekst.replace("\r\n", "\n").replace("\r", "\n")
    tekst = unicodedata.normalize("NFC", tekst)
    tekst = "\n".join(wiersz.rstrip() for wiersz in tekst.split("\n"))
    tekst = _NADMIAROWE_PUSTE_WIERSZE.sub("\n\n", tekst)
    return tekst.strip()


def zbuduj_dokument_znormalizowany(identyfikator_zrodla: str, tekst: str) -> DokumentZnormalizowany:
    """Normalizuje tekst i pakuje go w `DokumentZnormalizowany` z licznikami.

    Liczba słów i znaków jest liczona z tekstu już znormalizowanego, wspólną
    definicją z modułu `gnb.core.liczenie_slow`.
    """
    znormalizowany = znormalizuj(tekst)
    return DokumentZnormalizowany(
        identyfikator_zrodla=identyfikator_zrodla,
        tekst=znormalizowany,
        liczba_slow=policz_slowa(znormalizowany),
        liczba_znakow=policz_znaki(znormalizowany),
    )
