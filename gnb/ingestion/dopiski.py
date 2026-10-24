"""Dopiski odręczne przepisane przez osobę widzącą, leżące obok zdjęć skanów.

Tesseract nie czyta pisma odręcznego, więc dopiski na kartce przepisuje osoba
widząca. Konwencja jest prosta: obok zdjęcia ``NAZWA.jpg`` w tym samym folderze
leży plik tekstowy ``NAZWA_dopiski.txt`` albo ``NAZWA_dopiski.md``. Osoba
przepisująca nie musi znać Markdownu, więc treść pliku jest zawsze traktowana
jako zwykły tekst.

Plik dopisków nie jest osobnym źródłem. Ten moduł wyłącza go z listy wejść,
znajduje go dla danego zdjęcia i odczytuje jego treść. Nie decyduje, gdzie ta
treść trafi w pliku wynikowym (to robi pakowanie) i nie miesza jej z wynikiem
OCR: dopiski są zawsze oddzielną, opisaną sekcją.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from pathlib import Path

from gnb.core.nazwy import klucz_porzadku_naturalnego
from gnb.core.stale import TypWejscia
from gnb.extractors.plik_obraz import FORMATY_OBRAZOW
from gnb.ingestion.wejscie import FORMATY_PLIKOW, PozycjaWejsciowa
from gnb.normalization.kodowanie import zdekoduj

SUFIKS_NAZWY_DOPISKOW = "_dopiski"
ROZSZERZENIA_DOPISKOW = (".txt", ".md")


def czy_plik_dopiskow(sciezka: Path) -> bool:
    """Prawda, gdy nazwa pliku ma postać ``NAZWA_dopiski.txt`` albo ``NAZWA_dopiski.md``."""
    trzon = sciezka.stem.lower()
    return (
        sciezka.suffix.lower() in ROZSZERZENIA_DOPISKOW
        and trzon.endswith(SUFIKS_NAZWY_DOPISKOW)
        and len(trzon) > len(SUFIKS_NAZWY_DOPISKOW)
    )


def znajdz_plik_dopiskow(sciezka_obrazu: Path) -> Path | None:
    """Zwraca plik dopisków leżący obok zdjęcia albo nic, gdy go nie ma.

    Wielkość liter w nazwie nie ma znaczenia, bo Notatnik i Eksplorator potrafią
    ją zmienić. Gdy istnieją oba pliki, ``.txt`` ma pierwszeństwo przed ``.md``.
    """
    katalog = sciezka_obrazu.parent
    szukany_trzon = f"{sciezka_obrazu.stem}{SUFIKS_NAZWY_DOPISKOW}".lower()
    try:
        pliki = sorted(katalog.iterdir(), key=lambda plik: plik.name.lower())
    except OSError:
        return None
    for rozszerzenie in ROZSZERZENIA_DOPISKOW:
        for plik in pliki:
            if (
                plik.is_file()
                and plik.stem.lower() == szukany_trzon
                and plik.suffix.lower() == rozszerzenie
            ):
                return plik
    return None


def wczytaj_dopiski(sciezka: Path) -> str:
    """Odczytuje treść pliku dopisków, wykrywając kodowanie jak w plikach tekstowych.

    Notatnik zapisuje UTF-8 ze znacznikiem kolejności bajtów, a starsze wersje
    w ANSI; oba przypadki obsługuje wspólne wykrywanie kodowania. Zwracany jest
    tekst w postaci NFC, z końcami wierszy zamienionymi na znak nowej linii
    i bez pustych brzegów.
    """
    tekst, _ = zdekoduj(sciezka.read_bytes())
    tekst = unicodedata.normalize("NFC", tekst).replace("\r\n", "\n").replace("\r", "\n")
    return tekst.strip()


def odfiltruj_pliki_dopiskow(
    pozycje: Sequence[PozycjaWejsciowa],
) -> tuple[list[PozycjaWejsciowa], list[Path]]:
    """Oddziela pliki dopisków od pozostałych wejść.

    Zwraca parę: wejścia, które mają zostać źródłami, oraz ścieżki plików
    dopisków usuniętych z tej listy.
    """
    pozostale: list[PozycjaWejsciowa] = []
    dopiski: list[Path] = []
    for pozycja in pozycje:
        if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK and czy_plik_dopiskow(
            Path(pozycja.wejscie.wartosc)
        ):
            dopiski.append(Path(pozycja.wejscie.wartosc))
        else:
            pozostale.append(pozycja)
    return pozostale, dopiski


def pliki_z_folderu(folder: Path) -> tuple[list[Path], list[str]]:
    """Zwraca pliki folderu do przetworzenia i nazwy plików pominiętych z powodu formatu.

    Folder jest czytany bez podfolderów. Pliki ukryte (nazwa od kropki) są
    pomijane bez komunikatu, bo to ślady systemu, a nie materiały użytkownika.
    Pliki w formacie, którego aplikacja nie obsługuje, nie są przetwarzane,
    ale ich nazwy wracają do wołającego, żeby mógł je wypisać zamiast pominąć
    po cichu. Kolejność jest naturalna według nazw, więc skan 2 stoi przed 10.
    Pliki dopisków są zwracane razem ze zdjęciami: potok sam je wyłącza z listy
    źródeł i dołącza do skanów.

    Zgłasza `NotADirectoryError`, gdy ścieżka nie jest folderem.
    """
    if not folder.is_dir():
        raise NotADirectoryError(str(folder))
    obslugiwane: list[Path] = []
    nieobslugiwane: list[str] = []
    for plik in sorted(folder.iterdir(), key=lambda p: klucz_porzadku_naturalnego(p.name)):
        if not plik.is_file() or plik.name.startswith("."):
            continue
        if plik.suffix.lower().lstrip(".") in FORMATY_PLIKOW:
            obslugiwane.append(plik)
        else:
            nieobslugiwane.append(plik.name)
    return obslugiwane, nieobslugiwane


def dopiski_bez_skanu(pliki_dopiskow: Sequence[Path]) -> list[Path]:
    """Zwraca pliki dopisków, obok których nie ma zdjęcia o pasującej nazwie."""
    osierocone: list[Path] = []
    for plik in pliki_dopiskow:
        trzon = plik.stem[: -len(SUFIKS_NAZWY_DOPISKOW)].lower()
        try:
            sasiedzi = list(plik.parent.iterdir())
        except OSError:
            sasiedzi = []
        ma_skan = any(
            sasiad.stem.lower() == trzon and sasiad.suffix.lower().lstrip(".") in FORMATY_OBRAZOW
            for sasiad in sasiedzi
        )
        if not ma_skan:
            osierocone.append(plik)
    return osierocone
