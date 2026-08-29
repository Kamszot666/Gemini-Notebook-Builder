"""Klucze porównawcze dwóch pierwszych etapów deduplikacji z sekcji szesnastej.

Etap pierwszy wykrywa teksty dokładnie identyczne po normalizacji: kluczem jest
suma kontrolna znormalizowanego tekstu. Etap drugi wykrywa teksty różniące się
wyłącznie kosmetyką, czyli interpunkcją, białymi znakami i wielkością liter:
kluczem jest suma kontrolna tekstu sprowadzonego do samych liter i cyfr
rozdzielonych pojedynczą spacją.

Moduł nie decyduje o niczym. Zwraca same klucze, a porównanie i decyzję
podejmuje orkiestrator deduplikacji.
"""

from __future__ import annotations

import hashlib
import unicodedata

# Kategorie Unicode uznawane za znaki treści. Litery i cyfry zostają, wszystko
# inne — interpunkcja, symbole, znaki przestankowe — jest usuwane, bo etap drugi
# ma pomijać właśnie takie różnice. Pierwsza litera nazwy kategorii Unicode: „L”
# to litera, „N” to liczba.
_KATEGORIE_TRESCI = ("L", "N")


def hash_tresci(tekst: str) -> str:
    """Zwraca sumę kontrolną znormalizowanego tekstu dla pierwszego etapu.

    Tekst jest oczekiwany już po normalizacji z modułu `gnb.normalization`.
    Kodowanie do UTF-8 jest tu jedynie sposobem podania znaków funkcji skrótu,
    a nie ponowną normalizacją.
    """
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()


def klucz_kosmetyczny(tekst: str) -> str:
    """Zwraca sumę kontrolną tekstu pozbawionego różnic kosmetycznych.

    Tekst jest sprowadzany do małych liter, rozkładany zgodnie z postacią
    Unicode NFKD, a następnie zostają z niego wyłącznie litery i cyfry. Sąsiednie
    grupy znaków treści są rozdzielane pojedynczą spacją, żeby sklejenie dwóch
    słów po usunięciu łącznika nie tworzyło słowa, którego w tekście nie było.
    Dwa teksty różniące się tylko interpunkcją, odstępami albo wielkością liter
    dają po tym ten sam klucz.
    """
    rozlozony = unicodedata.normalize("NFKD", tekst.casefold())
    grupy: list[str] = []
    biezaca: list[str] = []
    for znak in rozlozony:
        if unicodedata.category(znak)[0] in _KATEGORIE_TRESCI:
            biezaca.append(znak)
        elif biezaca:
            grupy.append("".join(biezaca))
            biezaca = []
    if biezaca:
        grupy.append("".join(biezaca))
    uproszczony = " ".join(grupy)
    return hashlib.sha256(uproszczony.encode("utf-8")).hexdigest()
