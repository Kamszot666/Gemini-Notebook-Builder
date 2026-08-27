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

Adresy odnośników nie zostają w środku zdań, ponieważ czynią tekst trudnym do
odsłuchania czytnikiem ekranu. Nie są jednak gubione: w miejscu odnośnika zostaje
sam jego tekst, a na końcu dokumentu powstaje sekcja „Odnośniki wymienione
w artykule” z ponumerowaną listą w postaci tekst odnośnika, myślnik, adres.
Adres zacytowany przez autora bywa jedynym wskazaniem badania albo danych,
a identyfikowalność źródeł jest czwartym priorytetem z sekcji czwartej CLAUDE.md,
wyżej niż wygoda formatowania.

Zbierane są wyłącznie odnośniki o pełnym adresie z rodziny HTTP. Odsyłacze
w obrębie tej samej strony, adresy poczty i wywołania skryptów są pomijane,
podobnie jak adresy względne, których bez znajomości adresu bazowego nie da się
rozwinąć do postaci użytecznej dla czytelnika.

Strony budowane w całości przez skrypty są rozpoznawane i nazywane wprost.
Bez przeglądarki nie da się z nich pobrać treści, a przeglądarka bezgłowa
oznaczałaby setki megabajtów zależności natywnych, więc taki materiał jest
świadomie poza zakresem projektu. Zamiast milczącego pominięcia użytkownik
dostaje komunikat mówiący, czego zabrakło, i podpowiedź obejścia.

Treść strony jest danymi, nigdy instrukcją. Ekstraktor niczego z niej nie
wykonuje i nie interpretuje poleceń, które mogłyby się w niej znaleźć.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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

# Progi rozpoznania strony budowanej skryptami. Dokument musi być rozbudowany,
# zawierać skrypty i jednocześnie dawać znikomą treść po ekstrakcji. Dopiero te
# trzy warunki naraz świadczą o tym, że treść powstaje dopiero w przeglądarce,
# a nie o tym, że artykuł jest po prostu krótki.
MINIMALNA_DLUGOSC_DOKUMENTU_ZE_SKRYPTAMI = 2000
MAKSYMALNA_DLUGOSC_TRESCI_SZCZATKOWEJ = 200
_ZNACZNIK_SKRYPTU = "<script"

NAGLOWEK_SEKCJI_ODNOSNIKOW = "Odnośniki wymienione w artykule"
_BIALE_ZNAKI = re.compile(r"\s+")
_SCHEMATY_ODNOSNIKOW = ("http://", "https://")

KOMUNIKAT_WYMAGA_SKRYPTOW = (
    "Strona buduje treść dopiero w przeglądarce, przez wykonanie skryptów, więc "
    "nie da się z niej pobrać tekstu bez przeglądarki. Źródło zostało pominięte. "
    "Obejście: otwórz stronę w przeglądarce i zapisz ją do pliku, a następnie podaj "
    "ten plik jako źródło lokalne. Pliki HTML będą obsługiwane od etapu czwartego, "
    "a już teraz działa skopiowanie treści artykułu i wklejenie jej jako tekst."
)


@dataclass(frozen=True, slots=True)
class Odnosnik:
    """Jeden odnośnik zewnętrzny wymieniony w artykule."""

    tekst: str
    adres: str


class EkstraktorStronyWww:
    """Ekstraktor treści artykułu ze strony internetowej.

    Argument `zachowuj_odnosniki` odpowiada ustawieniu konfiguracji o tej samej
    nazwie. Wyłączenie go usuwa końcową sekcję z wykazem odnośników, a sama treść
    artykułu pozostaje bez zmian.
    """

    metoda = "strona_www"
    tekst_zawiera_znaczniki = True

    def __init__(self, zachowuj_odnosniki: bool = True) -> None:
        self._zachowuj_odnosniki = zachowuj_odnosniki

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
        odnosniki = _odnosniki_z_drzewa(drzewo)
        if odnosniki:
            metadane["liczba_odnosnikow"] = str(len(odnosniki))
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=self._z_sekcja_odnosnikow(_markdown_z_blokow(bloki), odnosniki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.SREDNI,
            metoda_ekstrakcji=METODA_GLOWNA,
            tytul=metadane.get("tytul"),
            bloki=bloki,
            metadane=metadane,
        )

    def _z_sekcja_odnosnikow(self, tekst: str, odnosniki: list[Odnosnik]) -> str:
        """Dopisuje na końcu tekstu wykaz odnośników, o ile jest co wypisać."""
        if not self._zachowuj_odnosniki or not odnosniki:
            return tekst
        sekcja = _sekcja_odnosnikow(odnosniki)
        return f"{tekst}\n\n{sekcja}" if tekst else sekcja

    def _zapasowy(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Odzyskuje akapity przez lxml, gdy trafilatura nic nie zwróciła."""
        akapity, tytul, odnosniki = _akapity_zapasowe(tekst)
        ostrzezenie = (
            "Treść odzyskana mechanizmem zapasowym, bez rozpoznania struktury dokumentu. "
            "Wersja Markdown nie powstanie."
        )
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=self._z_sekcja_odnosnikow("\n\n".join(akapity), odnosniki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_ZAPASOWA,
            tytul=tytul,
            ostrzezenia=[ostrzezenie],
        )


def czy_wymaga_skryptow(tekst_strony: str, tresc_wyekstrahowana: str) -> bool:
    """Rozstrzyga, czy strona buduje treść dopiero przez wykonanie skryptów.

    Warunki muszą być spełnione jednocześnie: dokument jest rozbudowany, zawiera
    znacznik skryptu, a mimo to ekstrakcja dała treść znikomą albo pustą. Sam
    krótki artykuł nie wystarczy, bo krótkie strony bywają w pełni poprawne.
    """
    if len(tresc_wyekstrahowana.strip()) > MAKSYMALNA_DLUGOSC_TRESCI_SZCZATKOWEJ:
        return False
    if len(tekst_strony) < MINIMALNA_DLUGOSC_DOKUMENTU_ZE_SKRYPTAMI:
        return False
    return _ZNACZNIK_SKRYPTU in tekst_strony.lower()


def _wywolaj_trafilature(tekst: str) -> str | None:
    """Wywołuje trafilaturę z ustawieniami dobranymi pod materiał do notatnika."""
    wynik: Any = trafilatura.extract(
        tekst,
        output_format="xml",
        include_tables=True,
        include_formatting=True,
        include_links=True,
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
            tresc = _tekst_cytatu(element)
            if tresc:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.CYTAT, poziom=0, tresc=tresc))
        elif znacznik == "code":
            tresc = _tekst_elementu(element)
            if tresc:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.KOD, poziom=0, tresc=tresc))
    return bloki


def _tekst_cytatu(element: etree._Element) -> str:
    """Zwraca treść cytatu blokowego, zachowując podział na akapity.

    Cytat bywa złożony z kilku akapitów. Sklejenie ich bez rozdzielenia zlałoby
    ostatnie słowo jednego zdania z pierwszym słowem następnego, dlatego akapity
    są rozdzielane znakiem nowej linii.
    """
    akapity = [_tekst_elementu(akapit) for akapit in element.findall("p")]
    akapity = [akapit for akapit in akapity if akapit]
    if akapity:
        return "\n".join(akapity)
    return _tekst_elementu(element)


def _odnosniki_z_drzewa(drzewo: etree._Element) -> list[Odnosnik]:
    """Zbiera odnośniki zewnętrzne w kolejności wystąpienia, bez powtórzeń.

    Powtórzony adres pojawia się na liście raz, z tekstem pierwszego wystąpienia,
    ponieważ wykaz ma wskazywać źródła, a nie liczyć odwołania.
    """
    zebrane: dict[str, Odnosnik] = {}
    for element in drzewo.iter("ref"):
        adres = str(element.get("target") or "").strip()
        if not _czy_odnosnik_zewnetrzny(adres) or adres in zebrane:
            continue
        tekst = _tekst_elementu(element).strip()
        zebrane[adres] = Odnosnik(tekst=tekst or adres, adres=adres)
    return list(zebrane.values())


def _czy_odnosnik_zewnetrzny(adres: str) -> bool:
    """Rozstrzyga, czy adres nadaje się do wykazu odnośników.

    Do wykazu trafiają wyłącznie pełne adresy HTTP i HTTPS. Odsyłacz w obrębie
    tej samej strony, adres poczty, wywołanie skryptu oraz adres względny są
    pomijane, bo albo nie wskazują źródła, albo bez adresu bazowego nie dają się
    rozwinąć do postaci użytecznej dla czytelnika.
    """
    return adres.lower().startswith(_SCHEMATY_ODNOSNIKOW)


def _sekcja_odnosnikow(odnosniki: list[Odnosnik]) -> str:
    """Buduje końcową sekcję z ponumerowanym wykazem odnośników."""
    wiersze = [f"## {NAGLOWEK_SEKCJI_ODNOSNIKOW}", ""]
    wiersze.extend(
        f"{numer}. {odnosnik.tekst} — {odnosnik.adres}"
        for numer, odnosnik in enumerate(odnosniki, start=1)
    )
    return "\n".join(wiersze)


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

    Fragmenty są sklejane dokładnie tak, jak występują w dokumencie, a dopiero
    potem ciągi białych znaków są skracane do pojedynczej spacji. Sklejanie przez
    dostawianie spacji psułoby interpunkcję wokół elementów wewnątrzwierszowych:
    zdanie „jak pokazuje badanie, dane” zamieniałoby się w „jak pokazuje badanie
    , dane”, gdy słowo „badanie” jest odnośnikiem.

    Iterator lxml potrafi zwrócić także bajty, na przykład dla komentarzy, więc
    każdy fragment jest sprowadzany do napisu przed sklejeniem.
    """
    fragmenty = (
        fragment.decode("utf-8", "replace") if isinstance(fragment, bytes) else str(fragment)
        for fragment in element.itertext()
    )
    return _BIALE_ZNAKI.sub(" ", "".join(fragmenty)).strip()


def _akapity_zapasowe(tekst: str) -> tuple[list[str], str | None, list[Odnosnik]]:
    """Odzyskuje akapity, tytuł i odnośniki ze strony, gdy zawiodła ekstrakcja główna."""
    try:
        drzewo = html.fromstring(tekst)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return [], None, []

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

    zebrane: dict[str, Odnosnik] = {}
    for element in drzewo.iter("a"):
        adres = str(element.get("href") or "").strip()
        if not _czy_odnosnik_zewnetrzny(adres) or adres in zebrane:
            continue
        tresc_odnosnika = _tekst_elementu(element).strip()
        zebrane[adres] = Odnosnik(tekst=tresc_odnosnika or adres, adres=adres)

    return akapity, tytul or None, list(zebrane.values())
