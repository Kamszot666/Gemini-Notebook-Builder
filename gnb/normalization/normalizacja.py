"""Normalizacja tekstu źródła przed policzeniem słów i zapisaniem wyników.

Zakres normalizacji: końce wierszy sprowadzane są do pojedynczego znaku nowej
linii, znaki Unicode do postaci NFC, białe znaki inne niż spacja i znak nowej
linii zamieniane są na pojedynczą spację, ciągi spacji skracane do jednej, znaki
niewidoczne i sterujące usuwane, z końców wierszy usuwane są białe znaki, ciągi
trzech i więcej pustych wierszy skracane są do jednego pustego wiersza, a puste
wiersze z początku i końca tekstu są usuwane.

Zamiana tabulatorów i twardych spacji na zwykłą spację nie jest kosmetyką.
Czytnik ekranu odczytuje tabulator jako osobny element, a w materiale dla
notatnika jest to szum. Znaki o zerowej szerokości, miękki łącznik i znaki
sterujące są niewidoczne dla czytelnika, więc w treści nie niosą nic poza
zaśmieceniem sumy kontrolnej i licznika znaków.

Łącznik nierozdzielający i spoiwo, czyli znaki ZWNJ oraz ZWJ, są zachowywane,
ponieważ w części pism i w sekwencjach emoji zmieniają znaczenie zapisu.

Moduł nie wykrywa kodowania i nie interpretuje struktury dokumentu. Zakłada, że
dostaje tekst już rozkodowany do postaci znakowej.
"""

from __future__ import annotations

import re
import unicodedata

from gnb.core.liczenie_slow import policz_slowa, policz_znaki
from gnb.core.model import DokumentZnormalizowany

_NADMIAROWE_PUSTE_WIERSZE = re.compile(r"\n{3,}")

# Ciągi białych znaków innych niż znak nowej linii: tabulatory, twarde spacje,
# wąskie spacje niepodzielne oraz zwykłe spacje wielokrotne.
_BIALE_ZNAKI_POZA_NOWA_LINIA = re.compile(r"[^\S\n]+")

# Pojedynczy biały znak, używany przy zamianie znaków wcięcia na spacje.
_BIALY_ZNAK = re.compile(r"\s")

# Znaki niewidoczne dla czytelnika: spacja o zerowej szerokości, spoiwo słów,
# znacznik kolejności bajtów wewnątrz tekstu oraz miękki łącznik. Zapisane jako
# kody, a nie wprost, bo w kodzie źródłowym byłyby niewidoczne i nie do odczytania
# czytnikiem ekranu.
_ZNAKI_NIEWIDOCZNE = re.compile("[\u200b\u2060\ufeff\u00ad]")

# Znaki sterujące poza znakiem nowej linii, który jest tu treścią.
_ZNAKI_STERUJACE = re.compile("[\x00-\x08\x0e-\x1f\x7f]")


def znormalizuj(tekst: str) -> str:
    """Sprowadza tekst do jednolitej postaci przed liczeniem słów i zapisem.

    Funkcja jest idempotentna: ponowne wywołanie na własnym wyniku niczego już
    nie zmienia. Kolejność kroków jest ustalona. Zamiana końców wierszy musi
    poprzedzać usuwanie białych znaków z końców wierszy, a zamiana tabulatorów
    i twardych spacji na spację musi poprzedzać usuwanie znaków sterujących,
    ponieważ część znaków sterujących jest jednocześnie białymi znakami i ma
    zostać spacją, a nie zniknąć bez śladu.
    """
    tekst = tekst.replace("\r\n", "\n").replace("\r", "\n")
    tekst = unicodedata.normalize("NFC", tekst)
    tekst = _ZNAKI_NIEWIDOCZNE.sub("", tekst)
    tekst = _ZNAKI_STERUJACE.sub("", tekst)
    tekst = "\n".join(_znormalizuj_wiersz(wiersz) for wiersz in tekst.split("\n"))
    tekst = _NADMIAROWE_PUSTE_WIERSZE.sub("\n\n", tekst)
    return tekst.strip()


def _znormalizuj_wiersz(wiersz: str) -> str:
    """Porządkuje białe znaki wewnątrz jednego wiersza, zachowując jego wcięcie.

    Wewnątrz wiersza tabulatory, twarde spacje i ciągi spacji stają się jedną
    spacją, ponieważ w zdaniu nie niosą treści, a czytnik ekranu odczytuje je
    osobno. Wcięcie na początku wiersza jest natomiast zachowywane co do liczby
    znaków, bo niesie znaczenie: tak zapisujemy zagnieżdżenie list i wcięcia
    wewnątrz bloków kodu. Każdy biały znak wcięcia staje się pojedynczą spacją,
    więc wcięcie tabulatorami nie zmienia głębokości zapisu.
    """
    bez_wciecia = wiersz.lstrip()
    wciecie = wiersz[: len(wiersz) - len(bez_wciecia)]
    return (
        _BIALY_ZNAK.sub(" ", wciecie) + _BIALE_ZNAKI_POZA_NOWA_LINIA.sub(" ", bez_wciecia)
    ).rstrip()


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
