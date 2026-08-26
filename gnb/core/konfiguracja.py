"""Konfiguracja aplikacji w zakresie obsługiwanym przez etap pierwszy.

Moduł buduje konfigurację z trzech źródeł, w kolejności rosnącego pierwszeństwa:
wartości domyślne zapisane w kodzie, plik TOML oraz zmienne środowiskowe
z prefiksem ``GNB_``. Brak pliku konfiguracji nie jest błędem — obowiązują
wtedy wartości domyślne.

Obsługiwane są wyłącznie pola potrzebne w etapie pierwszym: katalog nadrzędny
wyników, limit liczby źródeł, bezpieczny limit słów, bezpieczny limit megabajtów
oraz lista formatów wynikowych. Pozostałe pola wymienione w sekcji jedenastej a
pliku CLAUDE.md dojdą w kolejnych etapach.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from gnb.core.wyjatki import BladTrwaly

DOMYSLNY_LIMIT_ZRODEL = 100
DOMYSLNY_BEZPIECZNY_LIMIT_SLOW = 480_000
DOMYSLNY_BEZPIECZNY_LIMIT_MB = 190
DOMYSLNE_FORMATY_WYNIKOWE: tuple[str, ...] = ("txt", "md")

NAZWA_KATALOGU_APLIKACJI_WINDOWS = "Gemini Notebook Builder"
NAZWA_KATALOGU_APLIKACJI_XDG = "gemini-notebook-builder"
NAZWA_PLIKU_KONFIGURACJI = "konfiguracja.toml"
NAZWA_PODKATALOGU_WYNIKOW = "Gemini Notebook Builder"
PREFIKS_ZMIENNYCH = "GNB_"

_DOZWOLONE_FORMATY = ("txt", "md")

# Mapowanie nazwy zmiennej środowiskowej na nazwę pola konfiguracji.
_ZMIENNE_SRODOWISKOWE: Mapping[str, str] = {
    PREFIKS_ZMIENNYCH + "KATALOG_WYNIKOW": "katalog_wynikow",
    PREFIKS_ZMIENNYCH + "LIMIT_ZRODEL": "limit_zrodel",
    PREFIKS_ZMIENNYCH + "BEZPIECZNY_LIMIT_SLOW": "bezpieczny_limit_slow",
    PREFIKS_ZMIENNYCH + "BEZPIECZNY_LIMIT_MB": "bezpieczny_limit_mb",
    PREFIKS_ZMIENNYCH + "FORMATY_WYNIKOWE": "formaty_wynikowe",
}
_ZNANE_POLA = frozenset(_ZMIENNE_SRODOWISKOWE.values())


def _domyslny_katalog_wynikow() -> Path:
    """Domyślny katalog nadrzędny wyników: podkatalog w katalogu Dokumenty.

    Ścieżka jest wyznaczana dynamicznie z katalogu domowego użytkownika, a nie
    wpisana na sztywno. Nazwa katalogu Dokumenty zależy od języka systemu i sam
    katalog bywa przeniesiony na inny dysk, dlatego użytkownik może wskazać
    własny katalog przez plik konfiguracji albo zmienną środowiskową
    ``GNB_KATALOG_WYNIKOW``.
    """
    return Path.home() / "Documents" / NAZWA_PODKATALOGU_WYNIKOW


@dataclass(frozen=True, slots=True)
class Konfiguracja:
    """Zestaw ustawień aplikacji w zakresie obsługiwanym przez etap pierwszy."""

    katalog_wynikow: Path = field(default_factory=_domyslny_katalog_wynikow)
    limit_zrodel: int = DOMYSLNY_LIMIT_ZRODEL
    bezpieczny_limit_slow: int = DOMYSLNY_BEZPIECZNY_LIMIT_SLOW
    bezpieczny_limit_mb: int = DOMYSLNY_BEZPIECZNY_LIMIT_MB
    formaty_wynikowe: tuple[str, ...] = DOMYSLNE_FORMATY_WYNIKOWE


def sciezka_pliku_konfiguracji(srodowisko: Mapping[str, str] | None = None) -> Path:
    """Zwraca oczekiwaną ścieżkę pliku konfiguracji dla bieżącego systemu.

    Na Windows jest to podkatalog aplikacji w katalogu wskazywanym przez zmienną
    ``APPDATA``. Na pozostałych systemach jest to katalog zgodny ze standardem
    XDG, czyli ``XDG_CONFIG_HOME`` albo katalog ``.config`` w katalogu domowym.
    """
    srodowisko = os.environ if srodowisko is None else srodowisko
    appdata = srodowisko.get("APPDATA")
    if appdata:
        return Path(appdata) / NAZWA_KATALOGU_APLIKACJI_WINDOWS / NAZWA_PLIKU_KONFIGURACJI
    xdg = srodowisko.get("XDG_CONFIG_HOME")
    katalog_bazowy = Path(xdg) if xdg else Path.home() / ".config"
    return katalog_bazowy / NAZWA_KATALOGU_APLIKACJI_XDG / NAZWA_PLIKU_KONFIGURACJI


def wczytaj_konfiguracje(
    sciezka_pliku: Path | None = None,
    srodowisko: Mapping[str, str] | None = None,
) -> Konfiguracja:
    """Buduje konfigurację z wartości domyślnych, pliku TOML i zmiennych środowiskowych.

    Zmienna środowiskowa ma pierwszeństwo przed wartością z pliku, a wartość
    z pliku przed wartością domyślną z kodu. Brak pliku konfiguracji nie jest
    błędem. Uszkodzony plik albo niepoprawna wartość kończą się błędem trwałym
    z czytelnym komunikatem po polsku.
    """
    srodowisko = os.environ if srodowisko is None else srodowisko
    sciezka = sciezka_pliku if sciezka_pliku is not None else sciezka_pliku_konfiguracji(srodowisko)

    z_pliku = _wartosci_z_pliku(sciezka)
    ze_srodowiska = _wartosci_ze_srodowiska(srodowisko)
    scalone: dict[str, object] = {**z_pliku, **ze_srodowiska}

    domyslna = Konfiguracja()
    return Konfiguracja(
        katalog_wynikow=(
            Path(str(scalone["katalog_wynikow"]))
            if "katalog_wynikow" in scalone
            else domyslna.katalog_wynikow
        ),
        limit_zrodel=_jako_liczba(scalone, "limit_zrodel", domyslna.limit_zrodel),
        bezpieczny_limit_slow=_jako_liczba(
            scalone, "bezpieczny_limit_slow", domyslna.bezpieczny_limit_slow
        ),
        bezpieczny_limit_mb=_jako_liczba(
            scalone, "bezpieczny_limit_mb", domyslna.bezpieczny_limit_mb
        ),
        formaty_wynikowe=_jako_formaty(scalone, domyslna.formaty_wynikowe),
    )


def _wartosci_z_pliku(sciezka: Path) -> dict[str, object]:
    """Wczytuje znane pola z pliku TOML. Brak pliku daje pusty słownik."""
    if not sciezka.exists():
        return {}
    try:
        with sciezka.open("rb") as plik:
            dane = tomllib.load(plik)
    except (OSError, tomllib.TOMLDecodeError) as blad:
        raise BladTrwaly(f"Nie udało się wczytać pliku konfiguracji {sciezka}: {blad}") from blad
    return {klucz: wartosc for klucz, wartosc in dane.items() if klucz in _ZNANE_POLA}


def _wartosci_ze_srodowiska(srodowisko: Mapping[str, str]) -> dict[str, object]:
    """Zbiera nadpisania ze zmiennych środowiskowych z prefiksem ``GNB_``."""
    wynik: dict[str, object] = {}
    for zmienna, pole in _ZMIENNE_SRODOWISKOWE.items():
        wartosc = srodowisko.get(zmienna, "").strip()
        if wartosc:
            wynik[pole] = wartosc
    return wynik


def _jako_liczba(scalone: Mapping[str, object], pole: str, domyslna: int) -> int:
    """Zamienia wartość pola na liczbę całkowitą dodatnią albo zgłasza błąd."""
    if pole not in scalone:
        return domyslna
    surowa = scalone[pole]
    if isinstance(surowa, bool) or not isinstance(surowa, (int, str)):
        raise BladTrwaly(f"Ustawienie „{pole}” musi być liczbą całkowitą.")
    try:
        liczba = int(str(surowa).strip())
    except ValueError as blad:
        raise BladTrwaly(
            f"Ustawienie „{pole}” musi być liczbą całkowitą, a jest „{surowa}”."
        ) from blad
    if liczba <= 0:
        raise BladTrwaly(f"Ustawienie „{pole}” musi być liczbą dodatnią, a jest {liczba}.")
    return liczba


def _jako_formaty(scalone: Mapping[str, object], domyslne: tuple[str, ...]) -> tuple[str, ...]:
    """Zamienia wartość pola formatów na uporządkowaną krotkę z gwarantowanym TXT."""
    if "formaty_wynikowe" not in scalone:
        return domyslne
    surowa = scalone["formaty_wynikowe"]
    if isinstance(surowa, (list, tuple)):
        elementy = [str(element).strip().lower() for element in surowa]
    else:
        elementy = [czesc.strip().lower() for czesc in str(surowa).split(",")]
    elementy = [element for element in elementy if element]

    nieznane = sorted(set(elementy) - set(_DOZWOLONE_FORMATY))
    if nieznane:
        raise BladTrwaly(
            f"Nieobsługiwane formaty wynikowe: {', '.join(nieznane)}. Dozwolone: txt, md."
        )
    if "txt" not in elementy:
        elementy.insert(0, "txt")
    return tuple(dict.fromkeys(elementy))
