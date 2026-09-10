"""Wykrywanie zainstalowanego programu Audiveris na potrzeby diagnostyki i adaptera.

W przeciwieństwie do MuseScore, Audiveris jest w tej wersji aplikacji naprawdę
uruchamiany — przez `gnb.extractors.plik_nuty_skanowane` — więc ten moduł
odnajduje jego plik wykonywalny, a wywołanie należy do adaptera.

Na Windows instalator jpackage kładzie plik wykonywalny wprost w katalogu
instalacyjnym jako `Audiveris.exe`, z własnym, samodzielnym środowiskiem Java
w podkatalogu `runtime`. Ten plik wykonywalny NIE korzysta z systemowej Javy —
sprawdzone uruchomieniem: katalog `runtime\\bin` zawiera własne `java.exe`.
Systemowa Java bywa potrzebna innym sposobom instalacji Audiverisa, na przykład
samemu plikowi `audiveris.jar` uruchamianemu poleceniem `java -jar`, dlatego
diagnostyka w `gnb/cli.py` sprawdza obecność Javy osobno i opisuje to zastrzeżenie
wprost. Na Linuksie i macOS plik wykonywalny nazywa się `audiveris`, bez rozszerzenia.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from gnb.core.wyjatki import BrakNarzedzia

NAZWY_PLIKU_WYKONYWALNEGO = ("audiveris", "Audiveris.exe")

# Znane miejsca instalacji Audiverisa na Windows. Instalator jpackage nie
# dopisuje programu do zmiennej PATH, więc `shutil.which` sam go nie znajdzie,
# mimo że narzędzie jest zainstalowane. Ukośnik zwykły, nie wsteczny — z tego
# samego powodu co w `gnb/music/musescore.py`: `pathlib.Path` rozumie ukośnik
# zwykły jako separator na każdym systemie, a wsteczny tylko na Windows.
_ZNANE_PODKATALOGI_WINDOWS = (
    ("PROGRAMFILES", "Audiveris/Audiveris.exe"),
    ("PROGRAMFILES(X86)", "Audiveris/Audiveris.exe"),
)
_DOMYSLNE_SCIEZKI_WINDOWS = (
    Path(r"C:\Program Files\Audiveris\Audiveris.exe"),
    Path(r"C:\Program Files (x86)\Audiveris\Audiveris.exe"),
)

KOMUNIKAT_BRAK_AUDIVERISA = (
    "Nie znaleziono programu Audiveris, który rozpoznaje zapis nutowy z obrazu "
    "i z pliku PDF. Zainstaluj go i dopisz do zmiennej PATH albo wskaż ścieżkę "
    "pliku wykonywalnego w ustawieniu „sciezka_audiveris”. Bez niego materiały "
    "nutowe zapisane jako obraz albo skan zostaną pominięte."
)


def znajdz_audiveris(sciezka_wskazana: str = "") -> Path:
    """Zwraca ścieżkę pliku wykonywalnego Audiverisa albo zgłasza `BrakNarzedzia`.

    Kolejność szukania: ścieżka wskazana wprost w konfiguracji, następnie zmienna
    PATH, na końcu znane miejsca instalacji na Windows. Ta sama kolejność co
    w `gnb.music.musescore.znajdz_musescore` i `gnb.images.tesseract.znajdz_tesseract`.
    """
    if sciezka_wskazana:
        kandydat = Path(sciezka_wskazana)
        if kandydat.is_file():
            return kandydat
        raise BrakNarzedzia(
            f"Ustawienie „sciezka_audiveris” wskazuje plik, którego nie ma: {sciezka_wskazana}."
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

    raise BrakNarzedzia(KOMUNIKAT_BRAK_AUDIVERISA)


def czy_dostepny(sciezka_wskazana: str = "") -> bool:
    """Zwraca prawdę, gdy Audiveris da się odnaleźć, i nie zgłasza wyjątku."""
    try:
        znajdz_audiveris(sciezka_wskazana)
    except BrakNarzedzia:
        return False
    return True
