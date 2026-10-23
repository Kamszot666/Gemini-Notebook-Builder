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

from collections.abc import Sequence
from dataclasses import dataclass

from gnb.core.liczenie_slow import policz_slowa
from gnb.extractors.escapowanie_markdown import (
    escapuj_komorke_lub_fragment,
    escapuj_naglowek,
)
from gnb.extractors.markdown import utworz_parser
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

_PARSER = utworz_parser()


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
    naglowki = [
        indeks
        for indeks, token in enumerate(tokeny)
        if token.type == "heading_open" and token.level == 0 and token.map
    ]
    if not naglowki:
        return tekst_markdown
    najplytszy = min(int(tokeny[indeks].tag[1:]) for indeks in naglowki)
    przesuniecie = najplytszy_poziom_docelowy - najplytszy
    if przesuniecie <= 0:
        return tekst_markdown

    wiersze = tekst_markdown.split("\n")
    for indeks in reversed(naglowki):
        token = tokeny[indeks]
        poczatek, koniec = token.map or (0, 0)
        nowy_poziom = min(NAJGLEBSZY_POZIOM_NAGLOWKA, int(token.tag[1:]) + przesuniecie)
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
        tresc = przesun_naglowki(fragment.tresc_markdown, NAJPLYTSZY_POZIOM_TRESCI_ZRODLA_W_GRUPIE)
        sekcja.append(polacz_z_trescia(lista, tresc))
        czesci.append("\n\n".join(czesc for czesc in sekcja if czesc))
    return "\n\n".join(czesci)
