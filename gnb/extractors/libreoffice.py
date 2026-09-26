"""Wykrywanie LibreOffice i konwersja starych formatów Office na nowe.

LibreOffice jest potrzebny wyłącznie do plików DOC i PPT: dla tych dwóch
formatów binarnych nie ma dobrej biblioteki w czystym Pythonie, więc program
zamienia je na DOCX i PPTX, a dalej ekstrakcja idzie zwykłymi adapterami.
Wszystkie pozostałe formaty biurowe aplikacja czyta sama.

Na Windows instalator kładzie w katalogu programu dwa pliki: `soffice.exe`, który
otwiera okno i blokuje proces, oraz `soffice.com`, wariant konsolowy, który zwraca
sterowanie natychmiast. Aplikacja używa zawsze `soffice.com`, tak jak diagnostyka
w `gnb/cli.py`. Konwersja odbywa się w osobnym, tymczasowym profilu użytkownika,
żeby nie kolidowała z LibreOffice, który użytkownik ma akurat otwarty, i żeby
nie zapisywała niczego w jego profilu. Profil jest usuwany po zakończeniu pracy
programu. Plik do konwersji jest zapisywany w katalogu tymczasowym systemu,
nigdy w katalogu repozytorium ani projektu.

Dokument otwierany w trybie bez okna nie uruchamia makr. Mimo to plik jest
traktowany jako dane od nieznanego nadawcy: czas konwersji jest ograniczony, a jej
wynik jest sprawdzany, zanim trafi do dalszych etapów.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia

NAZWY_PLIKU_WYKONYWALNEGO = ("soffice.com", "soffice")

_ZNANE_PODKATALOGI_WINDOWS = (
    ("PROGRAMFILES", "LibreOffice/program/soffice.com"),
    ("PROGRAMFILES(X86)", "LibreOffice/program/soffice.com"),
)

LIMIT_CZASU_KONWERSJI_SEKUND = 180

KOMUNIKAT_BRAK_LIBREOFFICE = (
    "Nie znaleziono programu LibreOffice, który jest potrzebny do odczytu plików DOC i PPT. "
    "Zainstaluj go i dopisz do zmiennej PATH albo wskaż ścieżkę pliku soffice.com "
    "w ustawieniu „sciezka_libreoffice”. Bez niego pliki DOC i PPT zostaną pominięte, "
    "a pozostałe formaty działają normalnie. Możesz też zapisać taki plik w nowszym "
    "formacie, DOCX albo PPTX, i dodać go ponownie."
)

_profil_tymczasowy: Path | None = None


def znajdz_libreoffice(sciezka_wskazana: str = "") -> Path:
    """Zwraca ścieżkę pliku `soffice.com` albo zgłasza `BrakNarzedzia`.

    Kolejność szukania: ścieżka wskazana wprost w konfiguracji, następnie zmienna
    PATH, na końcu znane miejsca instalacji na Windows. Ta sama kolejność co
    dla pozostałych narzędzi zewnętrznych.
    """
    if sciezka_wskazana:
        kandydat = Path(sciezka_wskazana)
        if kandydat.is_file():
            return kandydat
        raise BrakNarzedzia(
            f"Ustawienie „sciezka_libreoffice” wskazuje plik, którego nie ma: {sciezka_wskazana}."
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
    raise BrakNarzedzia(KOMUNIKAT_BRAK_LIBREOFFICE)


def czy_dostepny(sciezka_wskazana: str = "") -> bool:
    """Zwraca prawdę, gdy LibreOffice da się odnaleźć, i nie zgłasza wyjątku."""
    try:
        znajdz_libreoffice(sciezka_wskazana)
    except BrakNarzedzia:
        return False
    return True


def konwertuj(
    program: Path,
    bajty: bytes,
    rozszerzenie_zrodla: str,
    format_docelowy: str,
    identyfikator: str,
) -> bytes:
    """Zamienia dokument na inny format i zwraca bajty wyniku.

    Zgłasza `BladTrwaly`, gdy konwersja przekroczy limit czasu, program zakończy
    się błędem albo nie utworzy pliku wynikowego.
    """
    with tempfile.TemporaryDirectory(prefix="gnb_lo_") as katalog_tymczasowy:
        katalog = Path(katalog_tymczasowy)
        wejscie = katalog / f"dokument.{rozszerzenie_zrodla}"
        wyjscie = katalog / "wynik"
        wyjscie.mkdir()
        wejscie.write_bytes(bajty)
        polecenie = [
            str(program),
            "--headless",
            "--norestore",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            f"-env:UserInstallation={_profil().as_uri()}",
            "--convert-to",
            format_docelowy,
            "--outdir",
            str(wyjscie),
            str(wejscie),
        ]
        try:
            wynik = subprocess.run(
                polecenie,
                capture_output=True,
                timeout=LIMIT_CZASU_KONWERSJI_SEKUND,
                check=False,
            )
        except subprocess.TimeoutExpired as blad:
            raise BladTrwaly(
                f"Konwersja pliku programem LibreOffice trwała ponad "
                f"{LIMIT_CZASU_KONWERSJI_SEKUND} sekund i została przerwana. Plik może być "
                "uszkodzony albo bardzo duży.",
                identyfikator,
            ) from blad
        except OSError as blad:
            raise BladTrwaly(
                f"Nie udało się uruchomić programu LibreOffice: {blad.strerror or blad}.",
                identyfikator,
            ) from blad
        pliki = list(wyjscie.glob(f"*.{format_docelowy}"))
        if wynik.returncode != 0 or not pliki:
            raise BladTrwaly(
                "Program LibreOffice nie zdołał odczytać pliku: jest uszkodzony, zaszyfrowany "
                "hasłem albo ma inny format niż wskazuje rozszerzenie.",
                identyfikator,
            )
        return pliki[0].read_bytes()


def _profil() -> Path:
    """Zwraca katalog tymczasowego profilu LibreOffice, wspólny dla całego procesu.

    Pierwsze uruchomienie z nowym profilem trwa dłużej, bo program tworzy jego
    zawartość, więc profil jest tworzony raz i usuwany dopiero przy wyjściu.
    """
    global _profil_tymczasowy
    if _profil_tymczasowy is None or not _profil_tymczasowy.exists():
        _profil_tymczasowy = Path(tempfile.mkdtemp(prefix="gnb_lo_profil_"))
        atexit.register(shutil.rmtree, _profil_tymczasowy, ignore_errors=True)
    return _profil_tymczasowy
