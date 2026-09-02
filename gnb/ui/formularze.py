"""Parsowanie ciała żądań formularzy interfejsu WWW.

Obsługiwane są dwa typy zawartości: ``application/x-www-form-urlencoded`` dla
formularzy bez plików oraz ``multipart/form-data`` dla formularzy z wysyłką
pliku.

Multipart jest parsowany ręcznie, przez podział ciała po ciągu granicznym
``boundary``, a nie modułem ``email``. Moduł ``email`` traktuje ładunek jako
tekst i potrafi normalizować końce wierszy, co uszkodziłoby wysłany plik
binarny, na przykład PDF, DOCX albo EPUB. Ręczny podział zwraca zawartość każdej
części bajt w bajt, bez żadnej zmiany. Priorytet pierwszy z sekcji czwartej
CLAUDE.md, poprawność danych, przeważa tu nad zwięzłością kodu.

Nadawca formularza multipart ma obowiązek dobrać ciąg graniczny tak, żeby nie
wystąpił w treści żadnej części; przeglądarki losują go właśnie w tym celu.
Dzięki temu podział po ciągu granicznym jest jednoznaczny.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs

from gnb.core.nazwy import bezpieczna_nazwa_pliku

_ROZDZIELACZ_NAGLOWKOW = b"\r\n\r\n"
_KONIEC_WIERSZA = b"\r\n"
_NAZWA_AWARYJNA_PLIKU = "plik"
_WZORZEC_NAZWY_POLA = re.compile(r'name="([^"]*)"')
_WZORZEC_NAZWY_PLIKU = re.compile(r'filename="([^"]*)"')


class BladFormularza(Exception):
    """Ciało żądania formularza jest niepoprawne albo przekracza dozwolony rozmiar.

    Serwer zamienia ten wyjątek na odpowiedź 400 z komunikatem po polsku, a nie
    na surowy ślad stosu.
    """


@dataclass(frozen=True, slots=True)
class PlikFormularza:
    """Jeden plik wysłany w formularzu multipart, z zawartością bajt w bajt."""

    nazwa_pola: str
    nazwa_pliku: str
    zawartosc: bytes


@dataclass(frozen=True, slots=True)
class WynikFormularza:
    """Rozłożone pola tekstowe i pliki jednego formularza."""

    pola: dict[str, list[str]] = field(default_factory=dict)
    pliki: list[PlikFormularza] = field(default_factory=list)

    def pole(self, nazwa: str, domyslne: str = "") -> str:
        """Zwraca pierwszą wartość pola o danej nazwie albo wartość domyślną."""
        wartosci = self.pola.get(nazwa)
        return wartosci[0] if wartosci else domyslne


def parsuj(
    cialo: bytes,
    typ_zawartosci: str,
    *,
    maksymalny_rozmiar_bajtow: int,
    maksymalna_liczba_plikow: int,
) -> WynikFormularza:
    """Rozkłada ciało żądania na pola i pliki, zależnie od typu zawartości.

    Rozmiar ciała jest sprawdzany przed parsowaniem. Liczba plików jest
    sprawdzana po parsowaniu. Przekroczenie któregokolwiek limitu kończy się
    `BladFormularza`.
    """
    if len(cialo) > maksymalny_rozmiar_bajtow:
        raise BladFormularza(
            f"Ciało żądania ma {len(cialo)} bajtów, ponad limit {maksymalny_rozmiar_bajtow}. "
            "Wyślij mniejszy plik albo zwiększ limit w konfiguracji."
        )

    glowny_typ = typ_zawartosci.split(";", 1)[0].strip().lower()
    if glowny_typ == "multipart/form-data":
        wynik = _parsuj_multipart(cialo, typ_zawartosci)
    else:
        wynik = _parsuj_urlencoded(cialo)

    if len(wynik.pliki) > maksymalna_liczba_plikow:
        raise BladFormularza(
            f"Formularz zawiera {len(wynik.pliki)} plików, ponad limit {maksymalna_liczba_plikow}."
        )
    return wynik


def bezpieczna_nazwa_wysylki(surowa_nazwa: str) -> str:
    """Zwraca bezpieczną dla Windows nazwę pliku wysłanego przez formularz.

    Najpierw odcinany jest ewentualny fragment ścieżki, żeby nazwa w rodzaju
    ``..\\..\\plik`` nie mogła wyjść poza katalog wejściowy projektu. Dalej nazwa
    przechodzi przez tę samą sanityzację co nazwa pliku wynikowego, z zachowaniem
    rozszerzenia potrzebnego do rozpoznania formatu.
    """
    sama_nazwa = Path(surowa_nazwa.replace("\\", "/")).name
    return bezpieczna_nazwa_pliku(sama_nazwa, nazwa_awaryjna=_NAZWA_AWARYJNA_PLIKU)


def _parsuj_urlencoded(cialo: bytes) -> WynikFormularza:
    pola = parse_qs(cialo.decode("utf-8", errors="replace"), keep_blank_values=True)
    return WynikFormularza(pola=pola, pliki=[])


def _parsuj_multipart(cialo: bytes, typ_zawartosci: str) -> WynikFormularza:
    granica = _wydziel_granice(typ_zawartosci)
    separator = b"--" + granica
    pola: dict[str, list[str]] = {}
    pliki: list[PlikFormularza] = []

    for segment in _segmenty_multipart(cialo, separator):
        surowe_naglowki, rozdzielony, zawartosc = segment.partition(_ROZDZIELACZ_NAGLOWKOW)
        if not rozdzielony:
            # Część bez pustego wiersza rozdzielającego nagłówki od treści jest
            # uszkodzona. Pomijamy ją, zamiast wywracać cały formularz.
            continue
        dyspozycja = _naglowek_dyspozycji(surowe_naglowki)
        nazwa_pola = _dopasuj(_WZORZEC_NAZWY_POLA, dyspozycja)
        if nazwa_pola is None:
            continue
        nazwa_pliku = _dopasuj(_WZORZEC_NAZWY_PLIKU, dyspozycja)
        if nazwa_pliku is None:
            pola.setdefault(nazwa_pola, []).append(zawartosc.decode("utf-8", errors="replace"))
        elif nazwa_pliku:
            pliki.append(
                PlikFormularza(
                    nazwa_pola=nazwa_pola,
                    nazwa_pliku=nazwa_pliku,
                    zawartosc=zawartosc,
                )
            )
    return WynikFormularza(pola=pola, pliki=pliki)


def _wydziel_granice(typ_zawartosci: str) -> bytes:
    for czesc in typ_zawartosci.split(";"):
        czesc = czesc.strip()
        if czesc.lower().startswith("boundary="):
            wartosc = czesc[len("boundary=") :].strip().strip('"')
            if wartosc:
                return wartosc.encode("latin-1", errors="replace")
    raise BladFormularza("Nagłówek multipart nie zawiera ciągu granicznego (boundary).")


def _segmenty_multipart(cialo: bytes, separator: bytes) -> Iterable[bytes]:
    """Wydziela treść kolejnych części między ciągami granicznymi.

    Pierwszy fragment przed pierwszym ciągiem granicznym oraz zamykający fragment
    po ostatnim ciągu granicznym są pomijane. Każda zwrócona część ma odcięty
    wiodący oraz zamykający znak końca wiersza.
    """
    fragmenty = cialo.split(separator)
    for fragment in fragmenty[1:-1]:
        if fragment.startswith(_KONIEC_WIERSZA):
            fragment = fragment[len(_KONIEC_WIERSZA) :]
        if fragment.endswith(_KONIEC_WIERSZA):
            fragment = fragment[: -len(_KONIEC_WIERSZA)]
        yield fragment


def _naglowek_dyspozycji(surowe_naglowki: bytes) -> str:
    tekst = surowe_naglowki.decode("utf-8", errors="replace")
    for wiersz in tekst.split("\r\n"):
        if wiersz.lower().startswith("content-disposition:"):
            return wiersz
    return ""


def _dopasuj(wzorzec: re.Pattern[str], tekst: str) -> str | None:
    dopasowanie = wzorzec.search(tekst)
    return dopasowanie.group(1) if dopasowanie is not None else None
