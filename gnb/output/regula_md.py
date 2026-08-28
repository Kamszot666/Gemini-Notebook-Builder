"""Deterministyczna reguła wyboru między TXT a MD z sekcji ósmej CLAUDE.md.

TXT powstaje zawsze. MD powstaje dodatkowo tylko wtedy, gdy dokument spełnia co
najmniej dwa z czterech warunków strukturalnych oraz spełnia warunek konieczny:
poziom pewności struktury zgłoszony przez ekstraktor jest co najmniej średni.

Reguła nie zgaduje struktury z płaskiego tekstu. Pracuje wyłącznie na blokach
rozpoznanych przez ekstraktor, a poziom pewności rozstrzyga warunek konieczny.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku
from gnb.extractors.bloki_markdown import czy_tabela_zapisywalna_bez_utraty

MINIMALNA_LICZBA_SPELNIONYCH_WARUNKOW = 2
MINIMALNA_LICZBA_NAGLOWKOW = 3
MINIMALNA_LICZBA_LIST = 2
MINIMALNA_LICZBA_ELEMENTOW_W_LISCIE = 3

OPIS_WARUNKU_NAGLOWKI = "co najmniej trzy nagłówki tworzące hierarchię co najmniej dwupoziomową"
OPIS_WARUNKU_LISTY = (
    "co najmniej dwie listy, w tym przynajmniej jedna z co najmniej trzema elementami"
)
OPIS_WARUNKU_TABELA = "co najmniej jedna tabela dająca się zapisać bez utraty znaczenia"
OPIS_WARUNKU_KOD = "blok kodu lub zapis techniczny, w którym formatowanie niesie znaczenie"

_WYSTARCZAJACE_POZIOMY_PEWNOSCI = frozenset(
    {PoziomPewnosciStruktury.SREDNI, PoziomPewnosciStruktury.WYSOKI}
)


@dataclass(frozen=True, slots=True)
class DecyzjaFormatu:
    """Wynik oceny reguły wyboru formatu dla jednego dokumentu."""

    generuj_md: bool
    spelnione_warunki: tuple[str, ...]
    poziom_pewnosci_wystarczajacy: bool


def ocen(dokument: DokumentWyekstrahowany) -> DecyzjaFormatu:
    """Ocenia, czy obok pliku TXT powstaje też plik MD.

    MD powstaje wtedy i tylko wtedy, gdy spełnione są co najmniej dwa z czterech
    warunków strukturalnych z sekcji ósmej CLAUDE.md oraz gdy poziom pewności
    struktury jest co najmniej średni.
    """
    bloki = dokument.bloki
    spelnione: list[str] = []

    if _warunek_naglowki(bloki):
        spelnione.append(OPIS_WARUNKU_NAGLOWKI)
    if _warunek_listy(bloki):
        spelnione.append(OPIS_WARUNKU_LISTY)
    if _warunek_tabela(bloki):
        spelnione.append(OPIS_WARUNKU_TABELA)
    if _warunek_kod(bloki):
        spelnione.append(OPIS_WARUNKU_KOD)

    poziom_wystarczajacy = dokument.poziom_pewnosci_struktury in _WYSTARCZAJACE_POZIOMY_PEWNOSCI
    generuj_md = len(spelnione) >= MINIMALNA_LICZBA_SPELNIONYCH_WARUNKOW and poziom_wystarczajacy

    return DecyzjaFormatu(
        generuj_md=generuj_md,
        spelnione_warunki=tuple(spelnione),
        poziom_pewnosci_wystarczajacy=poziom_wystarczajacy,
    )


def _warunek_naglowki(bloki: Sequence[BlokTresci]) -> bool:
    """Prawda, gdy są co najmniej trzy nagłówki i istnieje realne zagnieżdżenie."""
    naglowki = [blok for blok in bloki if blok.rodzaj is RodzajBloku.NAGLOWEK]
    if len(naglowki) < MINIMALNA_LICZBA_NAGLOWKOW:
        return False
    poziomy = {blok.poziom for blok in naglowki}
    if len(poziomy) < 2:
        return False
    najplytszy = min(poziomy)
    return any(blok.poziom > najplytszy for blok in naglowki)


def _warunek_listy(bloki: Sequence[BlokTresci]) -> bool:
    """Prawda, gdy są co najmniej dwie listy i co najmniej jedna ma trzy elementy."""
    listy = [blok for blok in bloki if blok.rodzaj is RodzajBloku.LISTA]
    if len(listy) < MINIMALNA_LICZBA_LIST:
        return False
    return any(_liczba_elementow(blok) >= MINIMALNA_LICZBA_ELEMENTOW_W_LISCIE for blok in listy)


def _liczba_elementow(blok: BlokTresci) -> int:
    """Liczba elementów listy zakodowanych jako osobne wiersze treści bloku."""
    if not blok.tresc:
        return 0
    return len(blok.tresc.split("\n"))


def _warunek_tabela(bloki: Sequence[BlokTresci]) -> bool:
    """Prawda, gdy jest tabela, którą da się zapisać w Markdown bez utraty znaczenia.

    Sama obecność bloku tabeli nie wystarcza. Tabela o wierszach różnej długości
    straci przy zapisie komórki albo dostanie puste, więc nie spełnia warunku
    trzeciego z sekcji ósmej CLAUDE.md, który mówi o tabeli dającej się zapisać
    bez utraty znaczenia.
    """
    return any(
        blok.rodzaj is RodzajBloku.TABELA and czy_tabela_zapisywalna_bez_utraty(blok)
        for blok in bloki
    )


def _warunek_kod(bloki: Sequence[BlokTresci]) -> bool:
    return any(blok.rodzaj is RodzajBloku.KOD for blok in bloki)
