"""Odczyt pliku MusicXML i zbudowanie z niego opisu partytury.

Silnikiem odczytu jest biblioteka standardowa `xml.etree.ElementTree`, bez
zależności zewnętrznej. Obsługiwane są oba warianty schematu, `score-partwise`
i `score-timewise`, oraz skompresowany kontener MXL, czyli archiwum ZIP
z dokumentem partytury w środku.

W przeciwieństwie do MIDI, MusicXML zapisuje podział na takty wprost, więc
liczba taktów jest dokładna. Wiele różnych oznaczeń tonacji albo metrum w obrębie
pierwszej partii kończy się ostrzeżeniem: opis podaje wartość początkową.
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree as ET

from gnb.core.wyjatki import BladTrwaly
from gnb.music.model import OpisPartytury
from gnb.music.tonacje import nazwa_tonacji_z_kwint

METODA_ODCZYTU = "xml.etree"

KOMUNIKAT_USZKODZONY = (
    "Pliku MusicXML nie dało się odczytać: jest uszkodzony albo nie jest dokumentem MusicXML."
)
KOMUNIKAT_MXL_BEZ_ZAWARTOSCI = (
    "Skompresowany plik MusicXML (MXL) nie zawiera żadnego dokumentu partytury."
)

_UWAGA_BRAK_TRYBU = (
    "W pliku nie ma oznaczenia trybu przy tonacji; zgodnie ze specyfikacją "
    "MusicXML przyjęto tryb durowy."
)

# Przelicznik jednostki metronomu na ćwierćnutę. Klucz to nazwa jednostki
# z elementu „beat-unit”, wartość to liczba, przez którą mnożymy liczbę uderzeń
# na minutę, żeby uzyskać tempo w ćwierćnutach.
_PRZELICZNIK_JEDNOSTKI = {
    "whole": 4.0,
    "half": 2.0,
    "quarter": 1.0,
    "eighth": 0.5,
    "16th": 0.25,
}


def przeczytaj_musicxml(bajty: bytes) -> OpisPartytury:
    """Buduje `OpisPartytury` z bajtów pliku MusicXML albo kontenera MXL.

    Zgłasza `BladTrwaly` dla pliku uszkodzonego albo nie będącego dokumentem
    MusicXML. Nie dokłada identyfikatora źródła — robi to adapter.
    """
    tresc_xml, format_zrodlowy = _rozpakuj(bajty)
    try:
        korzen = ET.fromstring(tresc_xml)
    except ET.ParseError as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY) from blad

    rodzaj_korzenia = _lokalny(korzen.tag)
    if rodzaj_korzenia not in ("score-partwise", "score-timewise"):
        raise BladTrwaly(KOMUNIKAT_USZKODZONY)

    # W schemacie „partwise” takty są dziećmi pierwszej partii, a w „timewise”
    # dziećmi korzenia. Zakres liczenia taktów i wykrywania zmian klucza czy
    # metrum musi to uwzględnić, inaczej liczba taktów wychodzi zerowa.
    if rodzaj_korzenia == "score-partwise":
        partia = _pierwszy(korzen, "part")
        zakres_taktow = partia if partia is not None else korzen
    else:
        zakres_taktow = korzen

    tytul = (
        _tekst(korzen, "work-title")
        or _tekst(korzen, "movement-title")
        or _tekst(korzen, "credit-words")
    )
    tonacja, uwagi_odczytu = _odczytaj_tonacje(zakres_taktow)
    metrum = _odczytaj_metrum(zakres_taktow)
    tempo_bpm = _odczytaj_tempo(korzen)
    instrumenty, struktura_czesci = _odczytaj_partie(korzen)
    liczba_taktow = len(_wszystkie(zakres_taktow, "measure")) or None

    ostrzezenia_zmian = _ostrzezenia_zmian(zakres_taktow, tonacja, metrum)

    return OpisPartytury(
        format_zrodlowy=format_zrodlowy,
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


def _rozpakuj(bajty: bytes) -> tuple[bytes, str]:
    """Zwraca właściwą treść XML oraz kod formatu źródłowego (``musicxml`` albo ``mxl``)."""
    if not zipfile.is_zipfile(io.BytesIO(bajty)):
        return bajty, "musicxml"

    try:
        with zipfile.ZipFile(io.BytesIO(bajty)) as archiwum:
            nazwa_wewnetrzna = _sciezka_partytury_w_mxl(archiwum)
            if nazwa_wewnetrzna is None:
                raise BladTrwaly(KOMUNIKAT_MXL_BEZ_ZAWARTOSCI)
            return archiwum.read(nazwa_wewnetrzna), "mxl"
    except zipfile.BadZipFile as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY) from blad


def _sciezka_partytury_w_mxl(archiwum: zipfile.ZipFile) -> str | None:
    """Ustala nazwę pliku z partyturą wewnątrz kontenera MXL.

    Najpierw czyta wskazanie z pliku ``META-INF/container.xml``, a gdy go nie ma,
    bierze pierwszy plik o rozszerzeniu ``.musicxml`` albo ``.xml`` spoza
    katalogu ``META-INF``.
    """
    try:
        container = archiwum.read("META-INF/container.xml")
    except KeyError:
        container = b""

    if container:
        try:
            korzen = ET.fromstring(container)
        except ET.ParseError:
            korzen = None
        if korzen is not None:
            rootfile = _pierwszy(korzen, "rootfile")
            if rootfile is not None:
                pelna_sciezka = rootfile.get("full-path")
                if pelna_sciezka and pelna_sciezka in archiwum.namelist():
                    return pelna_sciezka

    for nazwa in archiwum.namelist():
        if nazwa.startswith("META-INF/"):
            continue
        if nazwa.lower().endswith((".musicxml", ".xml")):
            return nazwa
    return None


def _lokalny(tag: str) -> str:
    """Zwraca lokalną nazwę znacznika, odcinając prefiks przestrzeni nazw."""
    return tag.rsplit("}", 1)[-1]


def _pierwszy(korzen: ET.Element, nazwa: str) -> ET.Element | None:
    """Zwraca pierwszy element o podanej nazwie lokalnej albo ``None``."""
    for element in korzen.iter():
        if _lokalny(element.tag) == nazwa:
            return element
    return None


def _wszystkie(korzen: ET.Element, nazwa: str) -> list[ET.Element]:
    """Zwraca wszystkie elementy o podanej nazwie lokalnej."""
    return [element for element in korzen.iter() if _lokalny(element.tag) == nazwa]


def _tekst(korzen: ET.Element, nazwa: str) -> str | None:
    """Zwraca przycięty tekst pierwszego elementu o podanej nazwie albo ``None``."""
    element = _pierwszy(korzen, nazwa)
    if element is None or element.text is None:
        return None
    przyciety = element.text.strip()
    return przyciety or None


def _odczytaj_tonacje(zakres: ET.Element) -> tuple[str | None, list[str]]:
    """Zwraca nazwę tonacji oraz listę uwag odczytu dla pierwszego oznaczenia klucza."""
    klucz = _pierwszy(zakres, "key")
    if klucz is None:
        return None, []
    element_kwint = _pierwszy(klucz, "fifths")
    if element_kwint is None or element_kwint.text is None:
        return None, []
    try:
        liczba_kwint = int(element_kwint.text.strip())
    except ValueError:
        return None, []

    element_trybu = _pierwszy(klucz, "mode")
    uwagi: list[str] = []
    if element_trybu is None or not (element_trybu.text and element_trybu.text.strip()):
        moll = False
        uwagi.append(_UWAGA_BRAK_TRYBU)
    else:
        moll = element_trybu.text.strip().lower() == "minor"

    return nazwa_tonacji_z_kwint(liczba_kwint, moll=moll), uwagi


def _odczytaj_metrum(zakres: ET.Element) -> str | None:
    """Zwraca pierwsze metrum jako napis „licznik/mianownik” albo ``None``."""
    element_czasu = _pierwszy(zakres, "time")
    if element_czasu is None:
        return None
    licznik = _tekst(element_czasu, "beats")
    mianownik = _tekst(element_czasu, "beat-type")
    if licznik is None or mianownik is None:
        return None
    return f"{licznik}/{mianownik}"


def _odczytaj_tempo(korzen: ET.Element) -> int | None:
    """Zwraca tempo w uderzeniach ćwierćnutowych na minutę albo ``None``."""
    for element in _wszystkie(korzen, "sound"):
        tempo = element.get("tempo")
        if tempo:
            try:
                return round(float(tempo))
            except ValueError:
                continue

    metronom = _pierwszy(korzen, "metronome")
    if metronom is not None:
        jednostka = _tekst(metronom, "beat-unit")
        na_minute = _tekst(metronom, "per-minute")
        if jednostka is not None and na_minute is not None:
            try:
                wartosc = float(na_minute)
            except ValueError:
                return None
            przelicznik = _PRZELICZNIK_JEDNOSTKI.get(jednostka.lower(), 1.0)
            return round(wartosc * przelicznik)
    return None


def _odczytaj_partie(korzen: ET.Element) -> tuple[list[str], list[str]]:
    """Zwraca listę instrumentów oraz opis struktury części z listy partii."""
    instrumenty: list[str] = []
    struktura: list[str] = []
    for numer, score_part in enumerate(_wszystkie(korzen, "score-part"), start=1):
        nazwa = _tekst(score_part, "part-name") or _tekst(score_part, "instrument-name")
        if nazwa is None:
            continue
        struktura.append(f"Partia {numer}: {nazwa}")
        if nazwa not in instrumenty:
            instrumenty.append(nazwa)
    return instrumenty, struktura


def _ostrzezenia_zmian(zakres: ET.Element, tonacja: str | None, metrum: str | None) -> list[str]:
    """Buduje ostrzeżenia, gdy w obrębie pierwszej partii zmienia się klucz albo metrum."""
    ostrzezenia: list[str] = []

    wartosci_kwint: set[str] = set()
    for klucz in _wszystkie(zakres, "key"):
        element_kwint = _pierwszy(klucz, "fifths")
        if element_kwint is not None and element_kwint.text:
            wartosci_kwint.add(element_kwint.text.strip())
    if len(wartosci_kwint) > 1:
        ostrzezenia.append(
            f"W partyturze zmienia się tonacja ({len(wartosci_kwint)} różne oznaczenia); "
            f"opis podaje tonację początkową ({tonacja})."
        )

    wartosci_metrum: set[str] = set()
    for czas in _wszystkie(zakres, "time"):
        licznik = _tekst(czas, "beats")
        mianownik = _tekst(czas, "beat-type")
        if licznik is not None and mianownik is not None:
            wartosci_metrum.add(f"{licznik}/{mianownik}")
    if len(wartosci_metrum) > 1:
        ostrzezenia.append(
            f"W partyturze zmienia się metrum ({len(wartosci_metrum)} różne wartości); "
            f"opis podaje metrum początkowe ({metrum})."
        )

    return ostrzezenia
