"""Odwzorowanie oznaczeń tonacji z plików nutowych na polskie nazwy.

Trzy formaty zapisują tonację inaczej. MusicXML podaje liczbę kwint (pole
``fifths`` od minus siedem do siedem) oraz tryb. Guitar Pro podaje wyliczenie,
którego wartość to para liczb w tej samej konwencji co MusicXML. MIDI podaje
napis w rodzaju ``"C"`` albo ``"F#m"``. Ten moduł sprowadza wszystkie trzy do
polskiej nazwy w rodzaju „C-dur” albo „fis-moll”.

Polskie nazewnictwo dźwięków różni się od angielskiego: angielskie ``B`` to
polskie ``H``, a angielskie ``B flat`` to polskie ``B``. Tablice poniżej są już
w zapisie polskim.
"""

from __future__ import annotations

# Liczba kwint w oznaczeniu tonacji odwzorowana na polską nazwę dźwięku
# podstawowego, osobno dla trybu durowego i molowego. Tryb molowy zapisujemy
# małą literą, zgodnie z tradycją polskiego nazewnictwa.
_KWINTY_DUR: dict[int, str] = {
    -7: "Ces",
    -6: "Ges",
    -5: "Des",
    -4: "As",
    -3: "Es",
    -2: "B",
    -1: "F",
    0: "C",
    1: "G",
    2: "D",
    3: "A",
    4: "E",
    5: "H",
    6: "Fis",
    7: "Cis",
}
_KWINTY_MOLL: dict[int, str] = {
    -7: "as",
    -6: "es",
    -5: "b",
    -4: "f",
    -3: "c",
    -2: "g",
    -1: "d",
    0: "a",
    1: "e",
    2: "h",
    3: "fis",
    4: "cis",
    5: "gis",
    6: "dis",
    7: "ais",
}

# Rdzeń napisu klucza w konwencji biblioteki mido (bez końcowego „m”)
# odwzorowany na liczbę kwint. Konwencja mido jest angielska, więc „B” oznacza
# tu ton o pięciu krzyżykach, czyli polskie H.
_KWINTY_MIDI_DUR: dict[str, int] = {
    "Cb": -7,
    "Gb": -6,
    "Db": -5,
    "Ab": -4,
    "Eb": -3,
    "Bb": -2,
    "F": -1,
    "C": 0,
    "G": 1,
    "D": 2,
    "A": 3,
    "E": 4,
    "B": 5,
    "F#": 6,
    "C#": 7,
}
_KWINTY_MIDI_MOLL: dict[str, int] = {
    "Ab": -7,
    "Eb": -6,
    "Bb": -5,
    "F": -4,
    "C": -3,
    "G": -2,
    "D": -1,
    "A": 0,
    "E": 1,
    "B": 2,
    "F#": 3,
    "C#": 4,
    "G#": 5,
    "D#": 6,
    "A#": 7,
}


def nazwa_tonacji_z_kwint(liczba_kwint: int, *, moll: bool) -> str | None:
    """Zwraca polską nazwę tonacji dla liczby kwint i trybu albo ``None``.

    Liczba kwint spoza zakresu od minus siedem do siedem nie ma standardowej
    nazwy tonacji, więc funkcja zwraca ``None`` zamiast zgadywać.
    """
    tablica = _KWINTY_MOLL if moll else _KWINTY_DUR
    podstawa = tablica.get(liczba_kwint)
    if podstawa is None:
        return None
    return f"{podstawa}-{'moll' if moll else 'dur'}"


def nazwa_tonacji_z_klucza_midi(klucz: str) -> str | None:
    """Zwraca polską nazwę tonacji dla napisu klucza w konwencji biblioteki mido.

    Przykłady wejścia: ``"C"``, ``"F#"``, ``"Cb"``, ``"Am"``, ``"F#m"``. Napis
    nierozpoznany daje ``None``, żeby nie wstawiać do opisu wartości zmyślonej.
    """
    oczyszczony = klucz.strip()
    if not oczyszczony:
        return None
    moll = oczyszczony.endswith("m")
    rdzen = oczyszczony[:-1] if moll else oczyszczony
    tablica = _KWINTY_MIDI_MOLL if moll else _KWINTY_MIDI_DUR
    liczba_kwint = tablica.get(rdzen)
    if liczba_kwint is None:
        return None
    return nazwa_tonacji_z_kwint(liczba_kwint, moll=moll)
