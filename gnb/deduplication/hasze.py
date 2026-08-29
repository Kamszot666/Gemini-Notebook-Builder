"""Klucze porównawcze dwóch pierwszych etapów deduplikacji z sekcji szesnastej.

Etap pierwszy wykrywa teksty dokładnie identyczne po normalizacji: kluczem jest
suma kontrolna znormalizowanego tekstu. Etap drugi wykrywa teksty różniące się
wyłącznie kosmetyką, czyli interpunkcją, białymi znakami i wielkością liter:
kluczem jest suma kontrolna tekstu, z którego usunięto interpunkcję i symbole,
sprowadzono litery do małych i ujednolicono odstępy.

Etap drugi celowo nie rusza znaków diakrytycznych. „pas” i „pąs” to różne słowa
i muszą dawać różne klucze, bo klucz etapu drugiego trafia w orkiestratorze
wprost w decyzję „duplikat”, bez progu i bez ścieżki do ręcznego rozstrzygnięcia.
Dlatego nie ma tu rozkładu zgodności Unicode (NFKD) ani usuwania znaków łączących
(kategoria Mn) — obie te operacje razem zdejmują ogonek z „ą” i skleiłyby oba
słowa w jeden klucz.

Moduł nie decyduje o niczym. Zwraca same klucze, a porównanie i decyzję
podejmuje orkiestrator deduplikacji.
"""

from __future__ import annotations

import hashlib
import unicodedata

# Pierwsze litery nazw kategorii Unicode znaków traktowanych jako kosmetyka:
# „P” to interpunkcja, „S” to symbole. Litery, cyfry i znaki diakrytyczne
# zostają nietknięte.
_KATEGORIE_KOSMETYCZNE = ("P", "S")


def hash_tresci(tekst: str) -> str:
    """Zwraca sumę kontrolną znormalizowanego tekstu dla pierwszego etapu.

    Tekst jest oczekiwany już po normalizacji z modułu `gnb.normalization`.
    Kodowanie do UTF-8 jest tu jedynie sposobem podania znaków funkcji skrótu,
    a nie ponowną normalizacją.
    """
    return hashlib.sha256(tekst.encode("utf-8")).hexdigest()


def klucz_kosmetyczny(tekst: str) -> str:
    """Zwraca sumę kontrolną tekstu pozbawionego różnic kosmetycznych.

    Tekst jest sprowadzany do małych liter i postaci Unicode NFC, po czym
    interpunkcja i symbole są zamieniane na spację, a ciągi białych znaków na
    pojedynczą spację. Zamiana na spację, a nie usunięcie, sprawia, że po
    skasowaniu łącznika „biało-czerwony” daje ten sam klucz co „biało czerwony”,
    ale inny niż „białoczerwony”. Litery, cyfry i znaki diakrytyczne pozostają
    bez zmian, więc dwa teksty różniące się wyłącznie interpunkcją, odstępami
    albo wielkością liter dają ten sam klucz, a różniące się choćby jednym
    diakrytykiem — różny.
    """
    znormalizowany = unicodedata.normalize("NFC", tekst.casefold())
    znaki = [" " if (znak.isspace() or _czy_kosmetyczny(znak)) else znak for znak in znormalizowany]
    uproszczony = " ".join("".join(znaki).split())
    return hashlib.sha256(uproszczony.encode("utf-8")).hexdigest()


def _czy_kosmetyczny(znak: str) -> bool:
    """Prawda dla znaku interpunkcji albo symbolu, czyli różnicy kosmetycznej."""
    return unicodedata.category(znak)[0] in _KATEGORIE_KOSMETYCZNE
