"""Podstawowe kontrakty danych aplikacji, opisane w sekcji siódmej CLAUDE.md.

Ten moduł definiuje struktury danych wspólne dla całego potoku przetwarzania:
od wejścia podanego przez użytkownika, przez ekstrakcję i normalizację,
deduplikację, aż po pliki wynikowe. Moduł nie zawiera logiki przetwarzania,
wyłącznie definicje typów. Kolejność pól w każdej klasie odpowiada opisowi
z pliku CLAUDE.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from gnb.core.stale import (
    FormatWynikowy,
    PoziomPewnosciStruktury,
    RodzajBloku,
    StatusZrodla,
    TypWejscia,
    TypZrodla,
    WynikDeduplikacji,
)


@dataclass(slots=True)
class WejscieSurowe:
    """To, co użytkownik podał aplikacji, zanim zostało zwalidowane."""

    identyfikator_wejscia: str
    typ_wejscia: TypWejscia
    wartosc: str
    moment_dodania: datetime


@dataclass(slots=True)
class Zrodlo:
    """Pojedyncze źródło po walidacji wejścia.

    Identyfikator jest wyprowadzany deterministycznie z typu i znormalizowanego
    pochodzenia źródła, dzięki czemu jest stabilny między uruchomieniami
    i pozwala poprawnie działać wznowieniu oraz pamięci podręcznej.
    """

    identyfikator_zrodla: str
    typ_zrodla: TypZrodla
    pochodzenie: str
    checksum: str | None
    status: StatusZrodla
    utworzono: datetime
    zaktualizowano: datetime


@dataclass(slots=True)
class BlokTresci:
    """Pojedynczy element strukturalny wyekstrahowanego dokumentu."""

    rodzaj: RodzajBloku
    poziom: int
    tresc: str


@dataclass(slots=True)
class DokumentWyekstrahowany:
    """Wynik etapu ekstrakcji dla jednego źródła."""

    identyfikator_zrodla: str
    tekst: str
    poziom_pewnosci_struktury: PoziomPewnosciStruktury
    metoda_ekstrakcji: str
    tytul: str | None = None
    bloki: list[BlokTresci] = field(default_factory=list)
    metadane: dict[str, str] = field(default_factory=dict)
    ostrzezenia: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DokumentZnormalizowany:
    """Tekst źródła po normalizacji, wraz z policzoną liczbą słów i znaków."""

    identyfikator_zrodla: str
    tekst: str
    liczba_slow: int
    liczba_znakow: int


@dataclass(slots=True)
class DecyzjaDeduplikacji:
    """Audytowalna decyzja podjęta przy porównaniu dwóch źródeł."""

    identyfikator_zrodla_glownego: str
    identyfikator_duplikatu: str
    metoda: str
    wynik_podobienstwa: float
    decyzja: WynikDeduplikacji
    uzasadnienie: str
    zachowane_fragmenty_unikalne: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PlikWynikowy:
    """Jeden plik wynikowy zapisany jako źródło gotowe do wgrania do notatnika."""

    sciezka: Path
    format: FormatWynikowy
    identyfikatory_zrodel: list[str]
    liczba_slow: int
    liczba_znakow: int
    rozmiar_bajtow: int
    checksum: str
