"""Wykrywanie projektów w katalogu wyników i wyróżnianie niedokończonych.

Interfejs pokazuje po starcie listę wszystkich projektów z katalogu wyników,
żeby użytkownik mógł wejść do dowolnego z nich albo wznowić niedokończony zamiast
zaczynać od nowa, zgodnie z sekcją osiemnastą punkt dziewiąty CLAUDE.md. Projekt
jest niedokończony, gdy ma checkpoint z flagą ``zakonczony`` równą fałsz. Lista
powstaje z odczytu katalogu przy każdym wywołaniu, bez pamięci podręcznej, więc
projekt usunięty z dysku znika z niej od razu.

Uszkodzony checkpoint jednego projektu nie może wywrócić całej listy. Taki
projekt trafia na listę z komunikatem błędu przy nim, a nie znika po cichu.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gnb.core.wyjatki import BladGnb
from gnb.persistence.checkpoint import wczytaj

_NAZWA_CHECKPOINT = "checkpoint.json"


@dataclass(frozen=True, slots=True)
class ProjektNaLiscie:
    """Jeden projekt w katalogu wyników, opisany na potrzeby listy w interfejsie."""

    nazwa: str
    katalog: Path
    zakonczony: bool
    liczba_zrodel: int
    czas_ostatniej_zmiany: str
    komunikat_bledu: str | None = None

    @property
    def stan(self) -> str:
        """Krótki stan projektu do odczytu przez czytnik ekranu: jedno słowo."""
        if self.komunikat_bledu is not None:
            return "uszkodzony"
        return "zakończony" if self.zakonczony else "niedokończony"


def znajdz_projekty(katalog_wynikow: Path) -> list[ProjektNaLiscie]:
    """Zwraca projekty z katalogu wyników, ostatnio zmienione na początku listy.

    Projektem jest podkatalog zawierający plik ``checkpoint.json``. Katalog
    wyników, którego jeszcze nie ma, daje pustą listę, a nie błąd.
    """
    if not katalog_wynikow.is_dir():
        return []
    projekty: list[ProjektNaLiscie] = []
    for wpis in sorted(katalog_wynikow.iterdir()):
        plik = wpis / _NAZWA_CHECKPOINT
        if wpis.is_dir() and plik.is_file():
            projekty.append(_wczytaj_pozycje(wpis, plik))
    projekty.sort(key=lambda projekt: projekt.czas_ostatniej_zmiany, reverse=True)
    return projekty


def opisz_projekt(katalog: Path) -> ProjektNaLiscie | None:
    """Opisuje jeden projekt, albo zwraca None, gdy katalog nie ma pliku checkpointu."""
    plik = katalog / _NAZWA_CHECKPOINT
    if not katalog.is_dir() or not plik.is_file():
        return None
    return _wczytaj_pozycje(katalog, plik)


def niedokonczone(katalog_wynikow: Path) -> list[ProjektNaLiscie]:
    """Zwraca projekty, które nie doszły do końca albo mają uszkodzony checkpoint."""
    return [
        projekt
        for projekt in znajdz_projekty(katalog_wynikow)
        if not projekt.zakonczony or projekt.komunikat_bledu is not None
    ]


def _wczytaj_pozycje(katalog: Path, plik_checkpointu: Path) -> ProjektNaLiscie:
    try:
        checkpoint = wczytaj(plik_checkpointu)
    except BladGnb as blad:
        return ProjektNaLiscie(
            nazwa=katalog.name,
            katalog=katalog,
            zakonczony=False,
            liczba_zrodel=0,
            czas_ostatniej_zmiany="",
            komunikat_bledu=blad.komunikat,
        )
    if checkpoint is None:
        return ProjektNaLiscie(
            nazwa=katalog.name,
            katalog=katalog,
            zakonczony=False,
            liczba_zrodel=0,
            czas_ostatniej_zmiany="",
            komunikat_bledu="Plik checkpointu zniknął między sprawdzeniem a odczytem.",
        )
    return ProjektNaLiscie(
        nazwa=checkpoint.nazwa_projektu or katalog.name,
        katalog=katalog,
        zakonczony=checkpoint.zakonczony,
        liczba_zrodel=len(checkpoint.zrodla),
        czas_ostatniej_zmiany=checkpoint.czas_ostatniej_zmiany,
    )
