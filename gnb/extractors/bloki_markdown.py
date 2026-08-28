"""Zapis listy bloków treści jako tekstu w zapisie Markdown.

Kilka ekstraktorów rozpoznaje tę samą strukturę dokumentu — nagłówki, akapity,
listy, tabele, cytaty i bloki kodu — i musi zamienić ją na jeden ciąg tekstu
w zapisie Markdown, który potem staje się treścią pliku wynikowego MD, a po
przepisaniu bez znaczników treścią pliku TXT. Ekstraktor strony internetowej,
pliku CSV, DOCX oraz EPUB potrzebują dokładnie tego samego przekształcenia,
więc mieszka ono w jednym miejscu, zamiast być powtórzone w każdym z nich.

Format wewnętrzny bloku tabeli jest ustalony: wiersze rozdzielone znakiem nowej
linii, komórki wewnątrz wiersza rozdzielone tabulatorem, pierwszy wiersz jest
nagłówkiem. Ten moduł jest jedynym miejscem, które ten format rozumie, więc tu
mieszka też sprawdzenie, czy daną tabelę da się zapisać bez utraty znaczenia.

Format bloku listy: elementy rozdzielone znakiem nowej linii, `poziom` równy
jeden oznacza listę numerowaną, a zero listę wypunktowaną.
"""

from __future__ import annotations

from collections.abc import Sequence

from gnb.core.model import BlokTresci
from gnb.core.stale import RodzajBloku


def zapisz_bloki_jako_markdown(bloki: Sequence[BlokTresci]) -> str:
    """Składa tekst w zapisie Markdown z rozpoznanych bloków treści."""
    fragmenty: list[str] = []
    for blok in bloki:
        if blok.rodzaj is RodzajBloku.NAGLOWEK:
            fragmenty.append(f"{'#' * max(1, min(blok.poziom, 6))} {blok.tresc}")
        elif blok.rodzaj is RodzajBloku.AKAPIT:
            fragmenty.append(blok.tresc)
        elif blok.rodzaj is RodzajBloku.LISTA:
            fragmenty.append(_markdown_listy(blok))
        elif blok.rodzaj is RodzajBloku.TABELA:
            fragmenty.append(_markdown_tabeli(blok))
        elif blok.rodzaj is RodzajBloku.CYTAT:
            fragmenty.append(
                "\n".join(f"> {wiersz}" for wiersz in blok.tresc.split("\n") if wiersz)
            )
        elif blok.rodzaj is RodzajBloku.KOD:
            fragmenty.append(f"```\n{blok.tresc}\n```")
    return "\n\n".join(fragment for fragment in fragmenty if fragment)


def _markdown_listy(blok: BlokTresci) -> str:
    """Zapisuje listę jako Markdown, zachowując rozróżnienie na wypunktowaną i numerowaną."""
    elementy = [element for element in blok.tresc.split("\n") if element]
    if blok.poziom == 1:
        return "\n".join(f"{numer}. {element}" for numer, element in enumerate(elementy, start=1))
    return "\n".join(f"- {element}" for element in elementy)


def _markdown_tabeli(blok: BlokTresci) -> str:
    """Zapisuje tabelę jako tabelę Markdown z wierszem rozdzielającym."""
    wiersze = wiersze_tabeli(blok)
    if not wiersze:
        return ""
    naglowek = wiersze[0]
    zapis = [
        "| " + " | ".join(_komorka_markdown(komorka) for komorka in naglowek) + " |",
        "| " + " | ".join("---" for _ in naglowek) + " |",
    ]
    for komorki in wiersze[1:]:
        zapis.append("| " + " | ".join(_komorka_markdown(komorka) for komorka in komorki) + " |")
    return "\n".join(zapis)


def _komorka_markdown(komorka: str) -> str:
    """Przygotowuje treść komórki do zapisu w tabeli Markdown.

    Pionowa kreska rozdziela komórki w zapisie tabeli, więc kreska występująca
    w treści komórki musi zostać poprzedzona odwrotnym ukośnikiem. Bez tego
    komórka o treści „a | b” rozbijała tabelę na dodatkową kolumnę i psuła
    strukturę całego wiersza.
    """
    return komorka.replace("\\", "\\\\").replace("|", r"\|")


def wiersze_tabeli(blok: BlokTresci) -> list[list[str]]:
    """Rozkłada wewnętrzny format bloku tabeli na wiersze i komórki."""
    return [wiersz.split("\t") for wiersz in blok.tresc.split("\n") if wiersz]


def czy_tabela_zapisywalna_bez_utraty(blok: BlokTresci) -> bool:
    """Rozstrzyga, czy tabelę da się zapisać jako tabelę Markdown bez utraty znaczenia.

    Tabela Markdown ma stałą liczbę kolumn, wyznaczoną przez wiersz nagłówka.
    Wiersz o innej liczbie komórek albo straci nadmiarowe komórki, albo dostanie
    puste, więc taka tabela nie da się zapisać wiernie. Sekcja ósma CLAUDE.md
    wymaga przy warunku trzecim reguły MD tabeli, którą da się zapisać bez utraty
    znaczenia, a nie tabeli jakiejkolwiek.

    Sama pionowa kreska w treści komórki nie przeszkadza, ponieważ zapis ją
    escapuje.
    """
    wiersze = wiersze_tabeli(blok)
    if not wiersze:
        return False
    liczba_kolumn = len(wiersze[0])
    return all(len(wiersz) == liczba_kolumn for wiersz in wiersze)
