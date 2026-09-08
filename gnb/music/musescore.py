"""Wykrywanie zainstalowanego programu MuseScore na potrzeby diagnostyki.

Ten moduł wyłącznie odnajduje plik wykonywalny MuseScore. Nie uruchamia go
i nie konwertuje nim żadnych plików. Renderowanie podglądu partytury przez
MuseScore jest decyzją świadomie odrzuconą, opisaną w sekcji 18d CLAUDE.md;
wykrywanie zostaje po to, żeby raport diagnostyki mówił prawdę o środowisku
i żeby przyszłe przywrócenie tej ścieżki miało gotowy punkt zaczepienia.

Na Windows plik wykonywalny nie nazywa się `mscore`, tylko `MuseScore4.exe`
albo `MuseScore3.exe`, i leży w podkatalogu `bin` katalogu instalacyjnego.
Nazwa `mscore` występuje wyłącznie na Linuksie i macOS. Wersja z Microsoft
Store nie daje się uruchomić z wiersza poleceń i nie jest brana pod uwagę.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from gnb.core.wyjatki import BrakNarzedzia

NAZWY_PLIKU_WYKONYWALNEGO = ("mscore", "MuseScore4.exe", "MuseScore3.exe")

# Znane miejsca instalacji MuseScore na Windows. Instalator nie dopisuje programu
# do zmiennej PATH, więc `shutil.which` sam go nie znajdzie, mimo że narzędzie
# jest zainstalowane. Podkatalog zapisujemy z ukośnikiem zwykłym, a nie
# wstecznym: `pathlib.Path` rozumie ukośnik zwykły jako separator na każdym
# systemie, a ukośnik wsteczny tylko na Windows — na Linuksie cały napis stałby
# się jedną nazwą i katalog `bin` nie zostałby odwiedzony. Ta sama konwencja co
# w `gnb/images/tesseract.py`.
_ZNANE_PODKATALOGI_WINDOWS = (
    ("PROGRAMFILES", "MuseScore 4/bin/MuseScore4.exe"),
    ("PROGRAMFILES(X86)", "MuseScore 4/bin/MuseScore4.exe"),
    ("PROGRAMFILES", "MuseScore 3/bin/MuseScore3.exe"),
    ("PROGRAMFILES(X86)", "MuseScore 3/bin/MuseScore3.exe"),
)
_DOMYSLNE_SCIEZKI_WINDOWS = (
    Path(r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe"),
    Path(r"C:\Program Files (x86)\MuseScore 4\bin\MuseScore4.exe"),
    Path(r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe"),
    Path(r"C:\Program Files (x86)\MuseScore 3\bin\MuseScore3.exe"),
)

KOMUNIKAT_BRAK_MUSESCORE = (
    "Nie znaleziono programu MuseScore. Zainstaluj go i dopisz do zmiennej PATH "
    "albo wskaż ścieżkę pliku wykonywalnego w ustawieniu „sciezka_musescore”. "
    "W tej wersji aplikacji MuseScore nie jest uruchamiany — służy tylko "
    "diagnostyce środowiska."
)


def znajdz_musescore(sciezka_wskazana: str = "") -> Path:
    """Zwraca ścieżkę pliku wykonywalnego MuseScore albo zgłasza `BrakNarzedzia`.

    Kolejność szukania: ścieżka wskazana wprost w konfiguracji, następnie zmienna
    PATH, na końcu znane miejsca instalacji na Windows. Ta sama kolejność co
    w `gnb.images.tesseract.znajdz_tesseract`.
    """
    if sciezka_wskazana:
        kandydat = Path(sciezka_wskazana)
        if kandydat.is_file():
            return kandydat
        raise BrakNarzedzia(
            f"Ustawienie „sciezka_musescore” wskazuje plik, którego nie ma: {sciezka_wskazana}."
        )

    for nazwa in NAZWY_PLIKU_WYKONYWALNEGO:
        znaleziony = shutil.which(nazwa)
        if znaleziony is not None:
            return Path(znaleziony)

    for zmienna, podkatalog in _ZNANE_PODKATALOGI_WINDOWS:
        baza = os.environ.get(zmienna)
        if not baza:
            continue
        kandydat = Path(baza) / podkatalog
        if kandydat.is_file():
            return kandydat
    for kandydat in _DOMYSLNE_SCIEZKI_WINDOWS:
        if kandydat.is_file():
            return kandydat

    raise BrakNarzedzia(KOMUNIKAT_BRAK_MUSESCORE)


def czy_dostepny(sciezka_wskazana: str = "") -> bool:
    """Zwraca prawdę, gdy MuseScore da się odnaleźć, i nie zgłasza wyjątku."""
    try:
        znajdz_musescore(sciezka_wskazana)
    except BrakNarzedzia:
        return False
    return True
