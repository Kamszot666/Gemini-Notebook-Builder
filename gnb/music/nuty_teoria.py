"""Nazwy pojedynczych dźwięków i wartości rytmicznych, wspólne dla modułu nut.

Nazwy dźwięków są zawsze w zapisie krzyżykowym (Cis, Dis, Fis, Gis, Ais),
niezależnie od tonacji utworu. Właściwa pisownia enharmoniczna (na przykład
Dis kontra Es) zależy od kontekstu tonalnego, a sekcja piętnasta CLAUDE.md
zabrania zgadywania — więc zamiast próbować odgadnąć, przyjęto jeden, stały
sposób nazywania, udokumentowany wprost jako konwencja, a nie jako twierdzenie
o „poprawnej” pisowni.

Numer oktawy liczony jest w notacji naukowej, w której środkowe C fortepianu
(numer MIDI 60) to C4 — ta sama konwencja, w której numer MIDI 0 to C-1.
"""

from __future__ import annotations

_NAZWY_DZWIEKOW = (
    "C",
    "Cis",
    "D",
    "Dis",
    "E",
    "F",
    "Fis",
    "G",
    "Gis",
    "A",
    "Ais",
    "H",
)

# Nazwa wartości rytmicznej dla wartości `beat.duration.value` z PyGuitarPro:
# 1 oznacza całą nutę, każda kolejna liczba dwukrotność podziału poprzedniej.
_NAZWY_WARTOSCI_RYTMICZNYCH: dict[int, str] = {
    1: "cała nuta",
    2: "półnuta",
    4: "ćwierćnuta",
    8: "ósemka",
    16: "szesnastka",
    32: "trzydziestodwójka",
    64: "sześćdziesięcioczwórka",
    128: "sto dwudziestoósemka",
}


def nazwa_dzwieku_z_midi(numer_midi: int) -> str:
    """Zwraca nazwę dźwięku w zapisie polskim z numerem oktawy, na przykład „E1”.

    Numer oktawy w notacji naukowej: numer MIDI 60 to C4. Nazwa jest zawsze
    krzyżykowa — patrz uwaga w docstringu modułu o tym, dlaczego nie próbujemy
    dobrać pisowni enharmonicznej do tonacji.
    """
    litera = _NAZWY_DZWIEKOW[numer_midi % 12]
    oktawa = numer_midi // 12 - 1
    return f"{litera}{oktawa}"


def litera_dzwieku_z_midi(numer_midi: int) -> str:
    """Zwraca samą literę nazwy dźwięku, bez numeru oktawy."""
    return _NAZWY_DZWIEKOW[numer_midi % 12]


def nazwa_wartosci_rytmicznej(wartosc: int, *, kropka: bool = False) -> str:
    """Zwraca polską nazwę wartości rytmicznej, opcjonalnie z kropką.

    Wartość nierozpoznana (spoza tabeli) dostaje awaryjną nazwę opisową zamiast
    wyjątku, bo pojedyncza egzotyczna wartość rytmiczna nie może zatrzymać
    całego odczytu pliku.
    """
    nazwa = _NAZWY_WARTOSCI_RYTMICZNYCH.get(wartosc, f"jedna {wartosc}-a")
    if kropka:
        nazwa = f"{nazwa} z kropką"
    return nazwa
