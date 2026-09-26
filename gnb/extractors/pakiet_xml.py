"""Bezpieczny odczyt archiwów ZIP z plikami XML: wspólna podstawa ODF i OOXML.

Pliki ODT, ODS, ODP oraz PPTX są archiwami ZIP, w których treść leży w plikach
XML. Ten moduł odpowiada za to, co wspólne: otwarcie archiwum, odczyt jednego
wpisu jako drzewa XML oraz kilka pomocników do zapisu nazw i tekstu. Nie zna
struktury żadnego z formatów.

Plik z internetu jest treścią, nigdy poleceniem, a archiwum ZIP bywa bombą
kompresji, więc odczyt ma trzy zabezpieczenia. Po pierwsze, rozmiar rozpakowanego
wpisu jest ograniczony, przy czym sprawdzany jest zarówno rozmiar zadeklarowany
w archiwum, jak i faktycznie odczytana liczba bajtów, bo deklaracja może
kłamać. Po drugie, wpis zawierający deklarację typu dokumentu albo definicję
encji jest odrzucany, bo dokumenty ODF i OOXML ich nie używają, a to one
umożliwiają ataki przez rozszerzanie encji. Po trzecie, żaden wpis nie jest
zapisywany na dysku: wszystko jest czytane do pamięci, więc nazwy wpisów
z archiwum nie mają jak wyprowadzić zapisu poza katalog projektu.

Niepoprawne archiwum, zaszyfrowany dokument i niepoprawny XML kończą się
błędem trwałym z komunikatem po polsku, a nie surowym wyjątkiem biblioteki.
"""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

from gnb.core.wyjatki import BladTrwaly

# Największy dopuszczalny rozmiar jednego rozpakowanego pliku XML. Treść dużego
# dokumentu bywa rzędu dziesiątek megabajtów, ale nie setek, więc granica
# odcina bombę kompresji, nie zwykły duży plik.
LIMIT_ROZMIARU_WPISU_BAJTOW = 200 * 1024 * 1024
LIMIT_LICZBY_WPISOW = 100_000

_ZAKAZANE_ZNACZNIKI = (b"<!DOCTYPE", b"<!ENTITY")


def otworz_archiwum(bajty: bytes, identyfikator: str, opis_formatu: str) -> zipfile.ZipFile:
    """Otwiera archiwum ZIP z pamięci albo zgłasza błąd trwały z czytelnym komunikatem.

    Argument `opis_formatu` wchodzi do komunikatu, na przykład „dokument ODT”.
    """
    try:
        archiwum = zipfile.ZipFile(io.BytesIO(bajty))
    except (zipfile.BadZipFile, OSError, ValueError) as blad:
        raise BladTrwaly(
            f"Plik nie jest poprawnym {opis_formatu}: nie dało się odczytać jego archiwum. "
            "Plik jest uszkodzony, zaszyfrowany albo ma inny format niż wskazuje rozszerzenie.",
            identyfikator,
        ) from blad
    if len(archiwum.infolist()) > LIMIT_LICZBY_WPISOW:
        raise BladTrwaly(
            f"Archiwum {opis_formatu} ma ponad {LIMIT_LICZBY_WPISOW} wpisów, co nie jest "
            "typowe dla dokumentu, więc nie zostało odczytane.",
            identyfikator,
        )
    return archiwum


def czy_ma_wpis(archiwum: zipfile.ZipFile, nazwa_wpisu: str) -> bool:
    """Zwraca prawdę, gdy archiwum ma wpis o podanej nazwie."""
    return nazwa_wpisu in archiwum.namelist()


def wczytaj_bajty_wpisu(archiwum: zipfile.ZipFile, nazwa_wpisu: str, identyfikator: str) -> bytes:
    """Czyta wpis do pamięci z ograniczeniem rozmiaru rozpakowanej treści."""
    try:
        informacja = archiwum.getinfo(nazwa_wpisu)
    except KeyError as blad:
        raise BladTrwaly(
            f"W archiwum brakuje wymaganego wpisu „{nazwa_wpisu}”, więc plik nie jest "
            "kompletnym dokumentem.",
            identyfikator,
        ) from blad
    if informacja.file_size > LIMIT_ROZMIARU_WPISU_BAJTOW:
        raise BladTrwaly(
            f"Wpis „{nazwa_wpisu}” ma po rozpakowaniu {informacja.file_size} bajtów, ponad "
            f"limit {LIMIT_ROZMIARU_WPISU_BAJTOW}. Plik nie został odczytany.",
            identyfikator,
        )
    try:
        with archiwum.open(informacja) as plik:
            dane = plik.read(LIMIT_ROZMIARU_WPISU_BAJTOW + 1)
    except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError) as blad:
        raise BladTrwaly(
            f"Nie udało się rozpakować wpisu „{nazwa_wpisu}”: plik jest uszkodzony "
            "albo zaszyfrowany.",
            identyfikator,
        ) from blad
    if len(dane) > LIMIT_ROZMIARU_WPISU_BAJTOW:
        raise BladTrwaly(
            f"Wpis „{nazwa_wpisu}” po rozpakowaniu przekracza limit "
            f"{LIMIT_ROZMIARU_WPISU_BAJTOW} bajtów. Plik nie został odczytany.",
            identyfikator,
        )
    return dane


def wczytaj_xml(archiwum: zipfile.ZipFile, nazwa_wpisu: str, identyfikator: str) -> ET.Element:
    """Czyta wpis archiwum jako drzewo XML, odrzucając deklaracje typu dokumentu i encje."""
    dane = wczytaj_bajty_wpisu(archiwum, nazwa_wpisu, identyfikator)
    return zbuduj_drzewo(dane, nazwa_wpisu, identyfikator)


def wczytaj_xml_opcjonalny(
    archiwum: zipfile.ZipFile, nazwa_wpisu: str, identyfikator: str
) -> ET.Element | None:
    """Jak `wczytaj_xml`, ale brak wpisu daje ``None``, a nie błąd."""
    if not czy_ma_wpis(archiwum, nazwa_wpisu):
        return None
    return wczytaj_xml(archiwum, nazwa_wpisu, identyfikator)


def zbuduj_drzewo(dane: bytes, opis: str, identyfikator: str) -> ET.Element:
    """Buduje drzewo XML z bajtów, odrzucając niebezpieczne konstrukcje."""
    if any(znacznik in dane for znacznik in _ZAKAZANE_ZNACZNIKI):
        raise BladTrwaly(
            f"Wpis „{opis}” zawiera deklarację typu dokumentu albo definicję encji, której "
            "dokumenty tego formatu nie używają. Plik został odrzucony jako potencjalnie "
            "niebezpieczny.",
            identyfikator,
        )
    try:
        return ET.fromstring(dane)
    except ET.ParseError as blad:
        raise BladTrwaly(
            f"Wpis „{opis}” nie jest poprawnym XML: plik jest uszkodzony.", identyfikator
        ) from blad


def nazwa_lokalna(znacznik: str) -> str:
    """Zwraca nazwę elementu bez przestrzeni nazw, na przykład ``h`` z ``{...}h``."""
    return znacznik.rsplit("}", 1)[-1]


def atrybut(element: ET.Element, nazwa_lokalna_atrybutu: str) -> str | None:
    """Zwraca wartość atrybutu o podanej nazwie lokalnej, bez względu na przestrzeń nazw."""
    for klucz, wartosc in element.attrib.items():
        if nazwa_lokalna(klucz) == nazwa_lokalna_atrybutu:
            return wartosc
    return None


def jeden_wiersz(tekst: str) -> str:
    """Sprowadza tekst do jednego wiersza, bez tabulatorów i podwójnych spacji."""
    return " ".join(tekst.replace("\t", " ").split())
