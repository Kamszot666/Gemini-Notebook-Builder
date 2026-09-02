"""Grupowanie tematyczne i pakowanie źródeł do plików wynikowych.

Ten pakiet działa zawsze po deduplikacji, nigdy przed nią. Dzieli i łączy
źródła z poszanowaniem trzech niezależnych limitów notatnika: liczby źródeł,
liczby słów w źródle i rozmiaru pliku, opisanych w sekcji dziewiątej
CLAUDE.md. Nie zapisuje plików na dysk — tym zajmuje się `gnb.output`.

Kryterium grupowania w tym etapie to jawne przypisanie przez użytkownika: źródła
z tą samą nazwą grupy trafiają do wspólnego pliku, a źródło bez nazwy grupy
dostaje własny plik. Bez embeddingów i bez interfejsu żadne automatyczne
kryterium tematyczne nie jest dostępne, a łączenie po samym typie źródła byłoby
łączeniem przypadkowym, zakazanym w sekcji dziesiątej CLAUDE.md. Przypisanie
per źródło z interfejsu jest zadaniem etapu siódmego.
"""

from __future__ import annotations

from gnb.packing.limity import (
    LimityPakowania,
    liczba_bajtow,
    miesci_sie,
    przekracza_limit,
)
from gnb.packing.pakowanie import (
    FragmentPliku,
    PlanPliku,
    ZrodloDoPakowania,
    rozplanuj_grupe,
    rozplanuj_pojedyncze_zrodlo,
)
from gnb.packing.podzial import WynikPodzialu, podziel_na_czesci

__all__ = [
    "FragmentPliku",
    "LimityPakowania",
    "PlanPliku",
    "WynikPodzialu",
    "ZrodloDoPakowania",
    "liczba_bajtow",
    "miesci_sie",
    "podziel_na_czesci",
    "przekracza_limit",
    "rozplanuj_grupe",
    "rozplanuj_pojedyncze_zrodlo",
]
