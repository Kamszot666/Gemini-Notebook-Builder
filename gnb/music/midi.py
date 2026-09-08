"""Odczyt pliku MIDI i zbudowanie z niego opisu partytury.

Silnikiem odczytu jest biblioteka mido w czystym Pythonie. Z pliku MIDI da się
odczytać nazwę utworu, metrum, tempo, tonację i użyte barwy General MIDI. Nie da
się natomiast odczytać podziału na takty, bo format MIDI go nie zapisuje —
liczba taktów jest zawsze przeliczana z długości nagrania w czasie i oznaczana
jako przybliżona.

Więcej niż jedna różna wartość metrum, tempa albo tonacji w pliku kończy się
ostrzeżeniem: opis podaje wartość początkową, a informacja o zmianie trafia do
pola ostrzeżeń, skąd potok kieruje ją do manifestu i raportu.
"""

from __future__ import annotations

import io
import math

from gnb.core.stale import PoziomPewnosciStruktury
from gnb.core.wyjatki import BladTrwaly
from gnb.music.instrumenty_gm import nazwa_instrumentu
from gnb.music.model import OpisPartytury
from gnb.music.tonacje import nazwa_tonacji_z_klucza_midi

METODA_ODCZYTU = "mido"
FORMAT_ZRODLOWY = "midi"

# Kanał perkusyjny w numeracji od zera. W numeracji od jedynki jest to kanał
# dziesiąty, na którym numer programu nie wybiera barwy, tylko zestaw perkusyjny.
_KANAL_PERKUSYJNY = 9

KOMUNIKAT_BRAK_BIBLIOTEKI = (
    "Nie znaleziono biblioteki mido, która czyta pliki MIDI. Zainstaluj ją "
    "poleceniem „pip install gnb[nuty]”. Bez niej pliki MIDI nie zostaną "
    "odczytane, a pozostałe formaty źródeł działają normalnie."
)
KOMUNIKAT_USZKODZONY = (
    "Pliku MIDI nie dało się odczytać: jest uszkodzony albo nie jest plikiem "
    "MIDI (brak poprawnego nagłówka „MThd”)."
)


def czy_dostepna_biblioteka() -> bool:
    """Zwraca prawdę, gdy bibliotekę mido da się zaimportować."""
    try:
        import mido  # noqa: F401
    except ImportError:
        return False
    return True


def przeczytaj_midi(bajty: bytes) -> OpisPartytury:
    """Buduje `OpisPartytury` z bajtów pliku MIDI.

    Zgłasza `BladTrwaly` dla pliku uszkodzonego albo nie będącego plikiem MIDI.
    Nie dokłada identyfikatora źródła — robi to adapter, który zna identyfikator.
    """
    import mido
    from mido.midifiles.meta import KeySignatureError

    try:
        plik = mido.MidiFile(file=io.BytesIO(bajty))
    except (OSError, EOFError, ValueError, IndexError, KeyError, KeySignatureError) as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY) from blad

    tytul: str | None = None
    metra: list[str] = []
    tempa: list[int] = []
    tonacje: list[str] = []
    nazwy_sciezek_z_nutami: list[str] = []
    instrumenty: list[str] = []
    kanaly_z_nutami: set[int] = set()

    for sciezka in plik.tracks:
        nazwa_sciezki: str | None = None
        sciezka_ma_nuty = False
        for komunikat in sciezka:
            typ = komunikat.type
            if typ == "track_name" and nazwa_sciezki is None:
                nazwa_sciezki = komunikat.name.strip() or None
                if tytul is None and nazwa_sciezki is not None:
                    tytul = nazwa_sciezki
            elif typ == "time_signature":
                metra.append(f"{komunikat.numerator}/{komunikat.denominator}")
            elif typ == "set_tempo":
                tempa.append(round(mido.tempo2bpm(komunikat.tempo)))
            elif typ == "key_signature":
                nazwa = nazwa_tonacji_z_klucza_midi(komunikat.key)
                if nazwa is not None:
                    tonacje.append(nazwa)
            elif typ == "program_change":
                perkusja = komunikat.channel == _KANAL_PERKUSYJNY
                nazwa = nazwa_instrumentu(komunikat.program, perkusja=perkusja)
                if nazwa not in instrumenty:
                    instrumenty.append(nazwa)
            elif typ == "note_on" and komunikat.velocity > 0:
                sciezka_ma_nuty = True
                kanaly_z_nutami.add(komunikat.channel)
        if sciezka_ma_nuty and nazwa_sciezki is not None:
            nazwy_sciezek_z_nutami.append(nazwa_sciezki)

    if _KANAL_PERKUSYJNY in kanaly_z_nutami:
        nazwa_perkusji = nazwa_instrumentu(0, perkusja=True)
        if nazwa_perkusji not in instrumenty:
            instrumenty.append(nazwa_perkusji)

    metrum = metra[0] if metra else None
    tempo_bpm = tempa[0] if tempa else None
    tonacja = tonacje[0] if tonacje else None

    ostrzezenia_zmian: list[str] = []
    if len(set(metra)) > 1:
        ostrzezenia_zmian.append(
            f"Utwór zmienia metrum ({len(set(metra))} różne wartości); "
            f"opis podaje metrum początkowe ({metrum})."
        )
    if len(set(tempa)) > 1:
        ostrzezenia_zmian.append(
            f"Utwór zmienia tempo ({len(set(tempa))} różne wartości); "
            f"opis podaje tempo początkowe ({tempo_bpm} uderzeń na minutę)."
        )
    if len(set(tonacje)) > 1:
        ostrzezenia_zmian.append(
            f"Utwór zmienia tonację ({len(set(tonacje))} różne wartości); "
            f"opis podaje tonację początkową ({tonacja})."
        )

    tiki_konca = max(
        (sum(komunikat.time for komunikat in sciezka) for sciezka in plik.tracks),
        default=0,
    )
    liczba_taktow = _przyblizona_liczba_taktow(
        tiki_konca, plik.ticks_per_beat, metra[0] if metra else "4/4"
    )

    struktura_czesci = [
        f"Ścieżka {numer}: {nazwa}" for numer, nazwa in enumerate(nazwy_sciezek_z_nutami, start=1)
    ]

    poziom_pewnosci = (
        PoziomPewnosciStruktury.SREDNI
        if metrum is not None and tempo_bpm is not None
        else PoziomPewnosciStruktury.NISKI
    )

    return OpisPartytury(
        format_zrodlowy=FORMAT_ZRODLOWY,
        metoda_odczytu=METODA_ODCZYTU,
        tytul=tytul,
        tonacja=tonacja,
        metrum=metrum,
        tempo_bpm=tempo_bpm,
        liczba_taktow=liczba_taktow,
        liczba_taktow_przyblizona=True,
        instrumenty=instrumenty,
        struktura_czesci=struktura_czesci,
        poziom_pewnosci=poziom_pewnosci,
        ostrzezenia_zmian=ostrzezenia_zmian,
    )


def _przyblizona_liczba_taktow(
    tiki_konca: int, tiki_na_uderzenie: int, pierwsze_metrum: str
) -> int | None:
    """Wylicza przybliżoną liczbę taktów z długości nagrania i pierwszego metrum.

    Wartość jest z założenia niepewna: tiki obejmują wybrzmienie i ciszę na końcu
    dopisaną przez program, takt niepełny na początku nie jest odróżniany,
    a zmiany metrum i tempa przesuwają granice taktów. Dlatego wynik jest zawsze
    oznaczany jako przybliżony.
    """
    if tiki_na_uderzenie <= 0 or tiki_konca <= 0:
        return None

    licznik_tekst, mianownik_tekst = pierwsze_metrum.split("/")
    licznik = int(licznik_tekst)
    mianownik = int(mianownik_tekst)
    uderzen_w_takcie = licznik * 4 / mianownik
    if uderzen_w_takcie <= 0:
        return None

    uderzen = tiki_konca / tiki_na_uderzenie
    return max(1, math.ceil(uderzen / uderzen_w_takcie))
