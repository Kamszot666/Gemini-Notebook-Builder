"""Zapis listy bloków treści jako tekstu w zapisie Markdown.

Kilka ekstraktorów rozpoznaje tę samą strukturę dokumentu — nagłówki, akapity,
listy, tabele, cytaty i bloki kodu — i musi zamienić ją na jeden ciąg tekstu
w zapisie Markdown, który potem staje się treścią pliku wynikowego MD, a po
przepisaniu bez znaczników treścią pliku TXT. Ekstraktor strony internetowej,
pliku CSV, DOCX oraz EPUB potrzebują dokładnie tego samego przekształcenia,
więc mieszka ono w jednym miejscu, zamiast być powtórzone w każdym z nich.

Format wewnętrzny bloku tabeli jest ustalony: wiersze rozdzielone znakiem nowej
linii, komórki wewnątrz wiersza rozdzielone tabulatorem, pierwszy wiersz jest
nagłówkiem. Format bloku listy: elementy rozdzielone znakiem nowej linii,
`poziom` równy jeden oznacza listę numerowaną, a zero listę wypunktowaną.
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
    wiersze = [wiersz for wiersz in blok.tresc.split("\n") if wiersz]
    if not wiersze:
        return ""
    naglowek = wiersze[0].split("\t")
    zapis = [
        "| " + " | ".join(naglowek) + " |",
        "| " + " | ".join("---" for _ in naglowek) + " |",
    ]
    for wiersz in wiersze[1:]:
        komorki = wiersz.split("\t")
        zapis.append("| " + " | ".join(komorki) + " |")
    return "\n".join(zapis)
