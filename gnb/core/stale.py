"""Wyliczenia i stałe wspólne dla modelu danych aplikacji.

Wartości tekstowe wyliczeń są ustalone celowo, bo trafiają do zapisu
w checkpoincie i w manifeście. Zmiana wartości istniejącego wyliczenia
jest zmianą formatu danych i wymaga podniesienia wersji schematu.
"""

from __future__ import annotations

from enum import StrEnum


class TypWejscia(StrEnum):
    """Rodzaj wejścia podanego przez użytkownika, zanim zostanie zwalidowane."""

    URL = "url"
    LISTA_URL = "lista_url"
    PLIK = "plik"
    TEKST = "tekst"


class TypZrodla(StrEnum):
    """Rodzaj źródła po walidacji wejścia, decydujący o użytym ekstraktorze."""

    STRONA_WWW = "strona_www"
    YOUTUBE = "youtube"
    TEKST_WKLEJONY = "tekst_wklejony"
    PLIK_TEKSTOWY = "plik_tekstowy"
    PLIK_DOKUMENT = "plik_dokument"
    PLIK_AUDIO = "plik_audio"
    PLIK_OBRAZ = "plik_obraz"
    PLIK_NUTY = "plik_nuty"


class StatusZrodla(StrEnum):
    """Status źródła w potoku przetwarzania, zgodny z sekcją siódmą CLAUDE.md."""

    OCZEKUJE = "oczekuje"
    POBRANE = "pobrane"
    WYEKSTRAHOWANE = "wyekstrahowane"
    ZNORMALIZOWANE = "znormalizowane"
    DUPLIKAT = "duplikat"
    SPAKOWANE = "spakowane"
    POMINIETE = "pominiete"
    BLAD = "blad"


class RodzajBloku(StrEnum):
    """Rodzaj elementu strukturalnego wewnątrz wyekstrahowanego dokumentu."""

    NAGLOWEK = "naglowek"
    AKAPIT = "akapit"
    LISTA = "lista"
    TABELA = "tabela"
    CYTAT = "cytat"
    KOD = "kod"


class PoziomPewnosciStruktury(StrEnum):
    """Poziom pewności, z jakim ekstraktor rozpoznał strukturę dokumentu."""

    NISKI = "niski"
    SREDNI = "sredni"
    WYSOKI = "wysoki"


class WynikDeduplikacji(StrEnum):
    """Decyzja podjęta przez etap deduplikacji dla pary porównywanych źródeł."""

    DUPLIKAT = "duplikat"
    CZESCIOWY_DUPLIKAT = "czesciowy_duplikat"
    ROZNE = "rozne"
    WYMAGA_DECYZJI_UZYTKOWNIKA = "wymaga_decyzji_uzytkownika"


class FormatWynikowy(StrEnum):
    """Format pliku wynikowego zapisywanego jako źródło notatnika."""

    TXT = "txt"
    MD = "md"
    PDF = "pdf"
