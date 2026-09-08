"""Odczyt pliku Guitar Pro i zbudowanie z niego opisu partytury.

Silnikiem odczytu jest biblioteka PyGuitarPro. Obsługiwane są wersje formatu
gp3, gp4 i gp5. Nowsze formaty gpx i gp, czyli wersje szósta i siódma programu
Guitar Pro, nie są obsługiwane; ich odrzucenie z czytelnym komunikatem
następuje wcześniej, w warstwie przyjmowania wejścia, zgodnie z sekcją
piętnastą CLAUDE.md.

PyGuitarPro sam wykrywa wersję pliku z jego nagłówka, więc ten moduł nie musi
rozpoznawać wersji po rozszerzeniu. Liczba taktów jest dokładna, bo pochodzi
z nagłówków taktów. Zmiana metrum między nagłówkami taktów kończy się
ostrzeżeniem.
"""

from __future__ import annotations

import io

from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia
from gnb.music.instrumenty_gm import nazwa_instrumentu
from gnb.music.model import OpisPartytury
from gnb.music.tonacje import nazwa_tonacji_z_kwint

METODA_ODCZYTU = "pyguitarpro"

KOMUNIKAT_BRAK_BIBLIOTEKI = (
    "Nie znaleziono biblioteki PyGuitarPro, która czyta pliki Guitar Pro. "
    "Zainstaluj ją poleceniem „pip install gnb[nuty]”. Bez niej pliki gp3, gp4 "
    "i gp5 nie zostaną odczytane, a pozostałe formaty źródeł działają normalnie."
)
KOMUNIKAT_USZKODZONY = (
    "Pliku Guitar Pro nie dało się odczytać: jest uszkodzony albo zapisany "
    "w nieobsługiwanej odmianie formatu."
)


def czy_dostepna_biblioteka() -> bool:
    """Zwraca prawdę, gdy bibliotekę PyGuitarPro da się zaimportować."""
    try:
        import guitarpro  # noqa: F401
    except ImportError:
        return False
    return True


def przeczytaj_guitarpro(bajty: bytes) -> OpisPartytury:
    """Buduje `OpisPartytury` z bajtów pliku Guitar Pro w wersji gp3, gp4 albo gp5.

    Zgłasza `BrakNarzedzia`, gdy biblioteki PyGuitarPro nie ma, oraz `BladTrwaly`
    dla pliku uszkodzonego albo w nieobsługiwanej odmianie. Nie dokłada
    identyfikatora źródła — robi to adapter.
    """
    try:
        import guitarpro
    except ImportError as blad:
        raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI) from blad

    try:
        utwor = guitarpro.parse(io.BytesIO(bajty))
    except (guitarpro.GPException, OSError, EOFError, ValueError, IndexError) as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY) from blad

    tytul = (utwor.title or "").strip() or None
    tempo_bpm = int(utwor.tempo) if utwor.tempo else None
    tonacja = _nazwa_tonacji(utwor.key)

    naglowki = list(utwor.measureHeaders)
    liczba_taktow = len(naglowki) or None
    metrum = _metrum_naglowka(naglowki[0]) if naglowki else None

    instrumenty: list[str] = []
    struktura_czesci: list[str] = []
    for numer, sciezka in enumerate(utwor.tracks, start=1):
        nazwa_sciezki = (sciezka.name or "").strip() or f"ścieżka {numer}"
        struktura_czesci.append(f"Ścieżka {numer}: {nazwa_sciezki}")
        nazwa_instrumentu_sciezki = nazwa_instrumentu(
            sciezka.channel.instrument, perkusja=sciezka.isPercussionTrack
        )
        if nazwa_instrumentu_sciezki not in instrumenty:
            instrumenty.append(nazwa_instrumentu_sciezki)

    ostrzezenia_zmian = _ostrzezenia_zmian(naglowki, metrum)

    uwagi_odczytu: list[str] = []
    if getattr(utwor, "version", None):
        uwagi_odczytu.append(f"Wersja zapisu podana w pliku: {utwor.version}.")

    return OpisPartytury(
        format_zrodlowy=_kod_formatu(utwor),
        metoda_odczytu=METODA_ODCZYTU,
        tytul=tytul,
        tonacja=tonacja,
        metrum=metrum,
        tempo_bpm=tempo_bpm,
        liczba_taktow=liczba_taktow,
        liczba_taktow_przyblizona=False,
        instrumenty=instrumenty,
        struktura_czesci=struktura_czesci,
        ostrzezenia_zmian=ostrzezenia_zmian,
        uwagi_odczytu=uwagi_odczytu,
    )


def _kod_formatu(utwor: object) -> str:
    """Zwraca kod formatu źródłowego w postaci „gp3”, „gp4” albo „gp5”."""
    krotka_wersji = getattr(utwor, "versionTuple", None)
    if krotka_wersji:
        return f"gp{krotka_wersji[0]}"
    return "gp5"


def _nazwa_tonacji(klucz: object) -> str | None:
    """Zamienia wyliczenie tonacji z PyGuitarPro na polską nazwę.

    Wartość wyliczenia to para liczb: liczba kwint oraz tryb, gdzie zero oznacza
    dur, a jeden moll. Ta sama konwencja co w polu `fifths` MusicXML.
    """
    wartosc = getattr(klucz, "value", None)
    if not isinstance(wartosc, tuple) or len(wartosc) != 2:
        return None
    liczba_kwint, tryb = wartosc
    return nazwa_tonacji_z_kwint(int(liczba_kwint), moll=int(tryb) == 1)


def _metrum_naglowka(naglowek: object) -> str | None:
    """Zwraca metrum nagłówka taktu jako napis „licznik/mianownik” albo ``None``."""
    metrum = getattr(naglowek, "timeSignature", None)
    if metrum is None:
        return None
    licznik = getattr(metrum, "numerator", None)
    mianownik = getattr(getattr(metrum, "denominator", None), "value", None)
    if licznik is None or mianownik is None:
        return None
    return f"{licznik}/{mianownik}"


def _ostrzezenia_zmian(naglowki: list[object], pierwsze_metrum: str | None) -> list[str]:
    """Buduje ostrzeżenie, gdy metrum zmienia się między nagłówkami taktów."""
    metra = {metrum for naglowek in naglowki if (metrum := _metrum_naglowka(naglowek)) is not None}
    if len(metra) > 1:
        return [
            f"W tabulaturze zmienia się metrum ({len(metra)} różne wartości); "
            f"opis podaje metrum początkowe ({pierwsze_metrum})."
        ]
    return []
