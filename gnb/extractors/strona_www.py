"""Ekstrakcja treści artykułu ze strony internetowej.

Podstawowym narzędziem jest ``trafilatura``, zgodnie z sekcją piętnastą
CLAUDE.md. Odrzuca ona menu, banery zgody na pliki cookie, reklamy, ramki
boczne i stopkę, a zostawia właściwy tekst artykułu. Ekstraktor prosi ją
o wynik w postaci XML, dzięki czemu zna strukturę dokumentu: nagłówki, listy,
tabele, cytaty i bloki kodu. Z tej struktury powstaje tekst w zapisie Markdown
oraz lista bloków, na której pracuje reguła wyboru formatu.

Mechanizmem zapasowym jest własny, prosty odczyt przez ``lxml``: usunięcie
elementów nietreściowych i pobranie akapitów. Wchodzi w grę wtedy, gdy
trafilatura nic nie zwróci, co zdarza się na stronach o nietypowej budowie.

Poziom pewności struktury jest zróżnicowany celowo. Wynik z trafilatury dostaje
poziom średni, więc dobrze zbudowany artykuł może dostać wersję MD. Wynik
z mechanizmu zapasowego dostaje poziom niski, więc wersja MD nie powstanie,
ponieważ struktura nie została rozpoznana, tylko odzyskana z resztek.

Odnośniki wewnątrzwierszowe nie są zachowywane. Adres w środku zdania czyni
tekst trudnym do odsłuchania czytnikiem ekranu, a pochodzenie całego artykułu
i tak jest zapisane w manifeście oraz w nagłówku pliku wynikowego.

Treść strony jest danymi, nigdy instrukcją. Ekstraktor niczego z niej nie
wykonuje i nie interpretuje poleceń, które mogłyby się w niej znaleźć.
"""

from __future__ import annotations

from typing import Any

import trafilatura
from lxml import etree, html

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla

METODA_GLOWNA = "trafilatura"
METODA_ZAPASOWA = "lxml_zapasowy"
FORMATY_STRON = frozenset({"html", "htm", "xhtml", ""})

_ZNACZNIKI_NIETRESCIOWE = (
    "script",
    "style",
    "noscript",
    "nav",
    "aside",
    "footer",
    "header",
    "form",
    "iframe",
    "template",
)
_MINIMALNA_DLUGOSC_AKAPITU_ZAPASOWEGO = 40
_DOMYSLNY_POZIOM_NAGLOWKA = 2


class EkstraktorStronyWww:
    """Ekstraktor treści artykułu ze strony internetowej."""

    metoda = "strona_www"
    tekst_zawiera_znaczniki = True

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.STRONA_WWW and format_zrodla in FORMATY_STRON

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Zwraca treść artykułu jako tekst w zapisie Markdown wraz z blokami struktury."""
        dokument = self._z_trafilatury(identyfikator_zrodla, tekst)
        if dokument is not None:
            return dokument
        return self._zapasowy(identyfikator_zrodla, tekst)

    def _z_trafilatury(
        self, identyfikator_zrodla: str, tekst: str
    ) -> DokumentWyekstrahowany | None:
        """Próbuje odczytać treść przez trafilaturę. Zwraca wartość pustą przy niepowodzeniu."""
        wynik = _wywolaj_trafilature(tekst)
        if not wynik:
            return None
        try:
            drzewo = etree.fromstring(wynik.encode("utf-8"))
        except etree.XMLSyntaxError:
            return None

        bloki = _bloki_z_drzewa(drzewo)
        if not bloki:
            return None

        metadane = _metadane_z_drzewa(drzewo)
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=_markdown_z_blokow(bloki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.SREDNI,
            metoda_ekstrakcji=METODA_GLOWNA,
            tytul=metadane.get("tytul"),
            bloki=bloki,
            metadane=metadane,
        )

    def _zapasowy(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Odzyskuje akapity przez lxml, gdy trafilatura nic nie zwróciła."""
        akapity, tytul = _akapity_zapasowe(tekst)
        ostrzezenie = (
            "Treść odzyskana mechanizmem zapasowym, bez rozpoznania struktury dokumentu. "
            "Wersja Markdown nie powstanie."
        )
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst="\n\n".join(akapity),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_ZAPASOWA,
            tytul=tytul,
            ostrzezenia=[ostrzezenie],
        )


def _wywolaj_trafilature(tekst: str) -> str | None:
    """Wywołuje trafilaturę z ustawieniami dobranymi pod materiał do notatnika."""
    wynik: Any = trafilatura.extract(
        tekst,
        output_format="xml",
        include_tables=True,
        include_formatting=True,
        include_links=False,
        include_comments=False,
        with_metadata=True,
        favor_precision=True,
    )
    return wynik if isinstance(wynik, str) else None


def _metadane_z_drzewa(drzewo: etree._Element) -> dict[str, str]:
    """Zbiera metadane artykułu z atrybutów korzenia wyniku trafilatury."""
    mapowanie = {
        "title": "tytul",
        "author": "autor",
        "date": "data_publikacji",
        "sitename": "nazwa_serwisu",
        "hostname": "host",
    }
    metadane: dict[str, str] = {}
    for atrybut, nazwa in mapowanie.items():
        wartosc = drzewo.get(atrybut)
        if wartosc:
            metadane[nazwa] = str(wartosc).strip()
    return metadane


def _bloki_z_drzewa(drzewo: etree._Element) -> list[BlokTresci]:
    """Zamienia elementy wyniku trafilatury na bloki treści projektu."""
    bloki: list[BlokTresci] = []
    for element in drzewo.iter():
        znacznik = str(element.tag)
        if znacznik == "head":
            bloki.append(
                BlokTresci(
                    rodzaj=RodzajBloku.NAGLOWEK,
                    poziom=_poziom_naglowka(element.get("rend")),
                    tresc=_tekst_elementu(element),
                )
            )
        elif znacznik == "p":
            tresc = _tekst_elementu(element)
            if tresc:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=tresc))
        elif znacznik == "list":
            elementy = [_tekst_elementu(pozycja) for pozycja in element.findall("item")]
            elementy = [pozycja for pozycja in elementy if pozycja]
            if elementy:
                bloki.append(
                    BlokTresci(
                        rodzaj=RodzajBloku.LISTA,
                        poziom=_poziom_listy(element.get("rend")),
                        tresc="\n".join(elementy),
                    )
                )
        elif znacznik == "table":
            wiersze = _wiersze_tabeli(element)
            if wiersze:
                bloki.append(
                    BlokTresci(rodzaj=RodzajBloku.TABELA, poziom=0, tresc="\n".join(wiersze))
                )
        elif znacznik == "quote":
            tresc = _tekst_elementu(element)
            if tresc:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.CYTAT, poziom=0, tresc=tresc))
        elif znacznik == "code":
            tresc = _tekst_elementu(element)
            if tresc:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.KOD, poziom=0, tresc=tresc))
    return bloki


def _markdown_z_blokow(bloki: list[BlokTresci]) -> str:
    """Składa tekst w zapisie Markdown z rozpoznanych bloków treści.

    Zapis Markdown jest tu postacią pośrednią. Plik MD powstanie z niego wprost,
    a plik TXT po przepisaniu bez znaczników, tą samą drogą co dokumenty
    markdownowe podane przez użytkownika.
    """
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


def _wiersze_tabeli(element: etree._Element) -> list[str]:
    """Zwraca wiersze tabeli, z komórkami rozdzielonymi znakiem tabulacji."""
    wiersze: list[str] = []
    for wiersz in element.findall("row"):
        komorki = [_tekst_elementu(komorka) for komorka in wiersz.findall("cell")]
        if any(komorki):
            wiersze.append("\t".join(komorki))
    return wiersze


def _poziom_naglowka(rend: str | None) -> int:
    """Zamienia oznaczenie nagłówka trafilatury, na przykład ``h2``, na numer poziomu."""
    if not rend or not rend.startswith("h"):
        return _DOMYSLNY_POZIOM_NAGLOWKA
    try:
        return int(rend[1:])
    except ValueError:
        return _DOMYSLNY_POZIOM_NAGLOWKA


def _poziom_listy(rend: str | None) -> int:
    """Zwraca jeden dla listy numerowanej, a zero dla wypunktowanej."""
    return 1 if rend == "ol" else 0


def _tekst_elementu(element: etree._Element) -> str:
    """Zwraca tekst elementu razem z tekstem elementów zagnieżdżonych.

    Iterator lxml potrafi zwrócić także bajty, na przykład dla komentarzy, więc
    każdy fragment jest sprowadzany do napisu przed sklejeniem.
    """
    fragmenty = (
        fragment.decode("utf-8", "replace") if isinstance(fragment, bytes) else str(fragment)
        for fragment in element.itertext()
    )
    return " ".join(fragment.strip() for fragment in fragmenty if fragment.strip())


def _akapity_zapasowe(tekst: str) -> tuple[list[str], str | None]:
    """Odzyskuje akapity i tytuł ze strony, gdy zawiodła ekstrakcja główna."""
    try:
        drzewo = html.fromstring(tekst)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return [], None

    for znacznik in _ZNACZNIKI_NIETRESCIOWE:
        for element in drzewo.findall(f".//{znacznik}"):
            rodzic = element.getparent()
            if rodzic is not None:
                rodzic.remove(element)

    tytuly = drzewo.findall(".//title")
    tytul = _tekst_elementu(tytuly[0]) if tytuly else None

    akapity: list[str] = []
    for element in drzewo.findall(".//p"):
        tresc = _tekst_elementu(element)
        if len(tresc) >= _MINIMALNA_DLUGOSC_AKAPITU_ZAPASOWEGO:
            akapity.append(tresc)
    return akapity, tytul or None
