"""Składanie plików wynikowych w Markdown: nagłówki źródeł, hierarchia i liczenie słów.

Plik MD jest domyślnym formatem wynikowym, bo użytkownik nawiguje po nim klawiszem
nagłówka w czytniku ekranu. Ten moduł odpowiada za trzy rzeczy, które do tego
potrzebne: złożenie pliku grupy tak, żeby każde źródło zaczynało się nagłówkiem
drugiego poziomu, przesunięcie nagłówków samego źródła pod ten nagłówek oraz
policzenie słów pliku MD bez znaczników składni.

Moduł nie escapuje tekstu (robi to ``gnb.extractors.escapowanie_markdown``) i nie
dzieli treści na części (robi to ``gnb.packing``). Nie zgaduje struktury: nagłówki
dodaje tylko tam, gdzie sam plik grupy wymaga nagłówka źródła.

Hierarchia pliku grupy: nagłówek pierwszego poziomu z nazwą grupy (i numerem
części), pod nim nagłówek drugiego poziomu z tytułem każdego źródła, pod nim
nagłówek metadanych źródła jako lista, a dalej treść źródła z nagłówkami
przesuniętymi tak, że najpłytszy z nich ma poziom trzeci. Nagłówek poziomu
szóstego jest sufitem: głębsze zostają szóstymi.

Liczenie słów: słowa pliku MD liczy się po zamianie na tekst bez znaczników,
dokładnie tą samą funkcją co dla pliku TXT z tą samą treścią, więc limit
notatnika nie zależy od formatu (sekcja dziewiąta CLAUDE.md).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from markdown_it.token import Token

from gnb.core.liczenie_slow import policz_slowa
from gnb.extractors.escapowanie_markdown import (
    escapuj_komorke_lub_fragment,
    escapuj_naglowek,
)
from gnb.extractors.markdown import utworz_parser
from gnb.extractors.strona_www import NAGLOWEK_SEKCJI_ODNOSNIKOW
from gnb.output.naglowek_metadanych import (
    ETYKIETA_ADRES,
    ETYKIETA_IDENTYFIKATOR,
    ETYKIETA_PLIK,
    ETYKIETA_TYTUL,
    polacz_z_trescia,
)
from gnb.output.tekst_bez_znacznikow import zamien_markdown_na_tekst

NAJPLYTSZY_POZIOM_TRESCI_ZRODLA_W_GRUPIE = 3
NAJGLEBSZY_POZIOM_NAGLOWKA = 6
POZIOM_WYKAZU_ODNOSNIKOW_W_GRUPIE = 3

_PARSER = utworz_parser()
_POZYCJA_WYKAZU = re.compile(r"^\d+\. ")


@dataclass(frozen=True, slots=True)
class FragmentGrupyMarkdown:
    """Jedno źródło w pliku grupy: jego nagłówek metadanych i treść już w Markdown."""

    naglowek_metadanych: str
    tresc_markdown: str


def policz_slowa_markdown(tekst_markdown: str) -> int:
    """Liczy słowa pliku MD po usunięciu znaczników składni.

    Wynik jest taki sam jak dla tej samej treści zapisanej jako TXT, bo plik TXT
    powstaje z tej samej zamiany Markdown na tekst.
    """
    return policz_slowa(zamien_markdown_na_tekst(tekst_markdown))


def przesun_naglowki(tekst_markdown: str, najplytszy_poziom_docelowy: int) -> str:
    """Przesuwa nagłówki najwyższego poziomu tak, żeby najpłytszy miał poziom docelowy.

    Przesunięcie zachowuje względną hierarchię nagłówków źródła. Gdy najpłytszy
    nagłówek jest już na poziomie docelowym albo głębiej, tekst zostaje bez
    zmian. Przesuwane są nagłówki leżące bezpośrednio w dokumencie, także
    nagłówki z podkreśleniem (znaki równości albo myślniki pod tekstem), które
    stają się nagłówkami z krzyżykami. Nagłówki wewnątrz cytatów i list oraz
    wiersze w blokach kodu zostają bez zmian, bo parser nie uznaje ich za
    nagłówki dokumentu albo zapis wiersza byłby inny.
    """
    tokeny = _PARSER.parse(tekst_markdown)
    naglowki = _naglowki_dokumentu(tokeny)
    if not naglowki:
        return tekst_markdown
    poziomy = [int(tokeny[indeks].tag[1:]) for indeks in naglowki]
    przesuniecie = najplytszy_poziom_docelowy - min(poziomy)
    if przesuniecie <= 0:
        return tekst_markdown
    return _przepisz_poziomy_naglowkow(
        tekst_markdown,
        tokeny,
        naglowki,
        [min(NAJGLEBSZY_POZIOM_NAGLOWKA, poziom + przesuniecie) for poziom in poziomy],
    )


def usun_przeskoki_naglowkow(tekst_markdown: str) -> str:
    """Zamienia przeskok poziomu nagłówka o więcej niż jeden na kolejny poziom.

    Nawigacja klawiszem poziomu nagłówka w czytniku ekranu gubi miejsce, gdy po
    nagłówku trzeciego poziomu następuje od razu piąty. Każdy nagłówek dostaje
    poziom o jeden głębszy niż najbliższy płytszy nagłówek, który go poprzedza,
    więc względne położenie zostaje: dwa nagłówki równorzędne w źródle pozostają
    równorzędne. Nagłówek bez płytszego poprzednika, na przykład pierwszy w tekście,
    zachowuje swój poziom. Nagłówki płytsze niż poprzedni nigdy nie są zmieniane.
    """
    tokeny = _PARSER.parse(tekst_markdown)
    naglowki = _naglowki_dokumentu(tokeny)
    if not naglowki:
        return tekst_markdown

    stos: list[tuple[int, int]] = []
    pierwotne = [int(tokeny[indeks].tag[1:]) for indeks in naglowki]
    nowe: list[int] = []
    for poziom in pierwotne:
        while stos and stos[-1][0] >= poziom:
            stos.pop()
        nowy = stos[-1][1] + 1 if stos else poziom
        stos.append((poziom, nowy))
        nowe.append(min(NAJGLEBSZY_POZIOM_NAGLOWKA, nowy))

    if nowe == pierwotne:
        return tekst_markdown
    return _przepisz_poziomy_naglowkow(tekst_markdown, tokeny, naglowki, nowe)


def oddziel_wykaz_odnosnikow(tekst_markdown: str) -> tuple[str, str]:
    """Oddziela końcowy wykaz odnośników od reszty treści źródła.

    Wykaz dopisuje ekstraktor stron na końcu tekstu pod nagłówkiem drugiego
    poziomu. Zwraca parę (treść bez wykazu, wykaz); gdy wykazu nie ma albo po jego
    nagłówku jest cokolwiek poza pozycjami numerowanymi, wykaz jest pusty, a treść
    zostaje cała.
    """
    naglowek_wykazu = f"## {NAGLOWEK_SEKCJI_ODNOSNIKOW}"
    if tekst_markdown.startswith(f"{naglowek_wykazu}\n"):
        poczatek = 0
    else:
        pozycja = tekst_markdown.rfind(f"\n{naglowek_wykazu}\n")
        if pozycja == -1:
            return tekst_markdown, ""
        poczatek = pozycja + 1
    wykaz = tekst_markdown[poczatek:]
    pozycje = wykaz.split("\n")[1:]
    if any(wiersz.strip() and not _POZYCJA_WYKAZU.match(wiersz) for wiersz in pozycje):
        return tekst_markdown, ""
    return tekst_markdown[:poczatek].rstrip("\n"), wykaz


def _naglowki_dokumentu(tokeny: list[Token]) -> list[int]:
    """Zwraca indeksy tokenów nagłówków leżących bezpośrednio w dokumencie."""
    return [
        indeks
        for indeks, token in enumerate(tokeny)
        if token.type == "heading_open" and token.level == 0 and token.map
    ]


def _przepisz_poziomy_naglowkow(
    tekst_markdown: str, tokeny: list[Token], naglowki: list[int], nowe_poziomy: list[int]
) -> str:
    """Zapisuje nagłówki z nowymi poziomami, także te z podkreśleniem, jako krzyżyki."""
    wiersze = tekst_markdown.split("\n")
    for indeks, nowy_poziom in reversed(list(zip(naglowki, nowe_poziomy, strict=True))):
        token = tokeny[indeks]
        poczatek, koniec = token.map or (0, 0)
        krzyzyki = "#" * nowy_poziom
        if token.markup in ("=", "-"):
            tresc = " ".join(tokeny[indeks + 1].content.split())
            wiersze[poczatek:koniec] = [f"{krzyzyki} {tresc}"]
        else:
            reszta = wiersze[poczatek].lstrip()[len(token.markup) :]
            wiersze[poczatek] = f"{krzyzyki}{reszta}"
    return "\n".join(wiersze)


def naglowek_metadanych_jako_liste(naglowek_metadanych: str) -> str:
    """Zamienia wiersze nagłówka metadanych na listę wypunktowaną.

    Lista jest czytelna liniowo i nie jest nagłówkiem sekcji, więc metadane nie
    wchodzą do spisu treści. Wartości są escapowane, żeby nie stały się składnią.
    """
    wiersze = [wiersz for wiersz in naglowek_metadanych.split("\n") if wiersz.strip()]
    return "\n".join(f"- {escapuj_komorke_lub_fragment(wiersz)}" for wiersz in wiersze)


def tytul_zrodla(naglowek_metadanych: str) -> str:
    """Wybiera tytuł źródła do nagłówka drugiego poziomu.

    Kolejność: pole „Tytuł”, potem „Plik”, „Adres” i identyfikator źródła, bo
    nagłówek sekcji nie może być pusty, a nazwa pliku albo adres przynajmniej
    mówi, czego dotyczy sekcja.
    """
    wartosci: dict[str, str] = {}
    for wiersz in naglowek_metadanych.split("\n"):
        etykieta, separator, wartosc = wiersz.partition(": ")
        if separator and wartosc.strip():
            wartosci.setdefault(etykieta, wartosc.strip())
    for etykieta in (ETYKIETA_TYTUL, ETYKIETA_PLIK, ETYKIETA_ADRES, ETYKIETA_IDENTYFIKATOR):
        if etykieta in wartosci:
            return wartosci[etykieta]
    return "Źródło bez tytułu"


def zloz_plik_grupy_markdown(
    fragmenty: Sequence[FragmentGrupyMarkdown], *, tytul_pliku: str
) -> str:
    """Składa plik grupy: nagłówek pierwszego poziomu i sekcje źródeł drugiego poziomu.

    Każda sekcja to nagłówek drugiego poziomu z tytułem źródła, pod nim lista
    metadanych źródła, a dalej jego treść z nagłówkami przesuniętymi pod ten
    nagłówek. Dzięki temu klawisz nagłówka w czytniku ekranu przeskakuje między
    źródłami, a hierarchia pliku jest poprawna.
    """
    czesci = [f"# {escapuj_naglowek(tytul_pliku)}"]
    for fragment in fragmenty:
        sekcja = [f"## {escapuj_naglowek(tytul_zrodla(fragment.naglowek_metadanych))}"]
        lista = naglowek_metadanych_jako_liste(fragment.naglowek_metadanych)
        # Wykaz odnośników leży zawsze o jeden poziom pod tytułem źródła, bez
        # względu na to, jak głęboko sięga hierarchia samego artykułu.
        tresc_glowna, wykaz = oddziel_wykaz_odnosnikow(fragment.tresc_markdown)
        tresc = przesun_naglowki(tresc_glowna, NAJPLYTSZY_POZIOM_TRESCI_ZRODLA_W_GRUPIE)
        if wykaz:
            wykaz = f"{'#' * POZIOM_WYKAZU_ODNOSNIKOW_W_GRUPIE}{wykaz[2:]}"
            tresc = polacz_z_trescia(tresc, wykaz) if tresc else wykaz
        sekcja.append(polacz_z_trescia(lista, tresc))
        czesci.append("\n\n".join(czesc for czesc in sekcja if czesc))
    return "\n\n".join(czesci)
