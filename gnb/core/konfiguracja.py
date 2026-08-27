"""Konfiguracja aplikacji w zakresie obsługiwanym przez etapy pierwszy i drugi.

Moduł buduje konfigurację z trzech źródeł, w kolejności rosnącego pierwszeństwa:
wartości domyślne zapisane w kodzie, plik TOML oraz zmienne środowiskowe
z prefiksem ``GNB_``. Brak pliku konfiguracji nie jest błędem — obowiązują
wtedy wartości domyślne.

Obsługiwane są pola potrzebne w etapach pierwszym i drugim: katalog nadrzędny
wyników, limit liczby źródeł, bezpieczny limit słów, bezpieczny limit megabajtów,
lista formatów wynikowych, zachowywanie oryginałów źródeł oraz ustawienia
pobierania stron: nazwa klienta, limit czasu, ponowienia, odstępy, liczba
połączeń na domenę, respektowanie pliku robots, pamięć podręczna i dodatkowe
parametry śledzące. Pozostałe pola wymienione w sekcji jedenastej a pliku
CLAUDE.md dojdą w kolejnych etapach.
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
DOMYSLNE_ZACHOWYWANIE_ORYGINALOW = True

# Ustawienia pobierania stron internetowych. Nazwa klienta jest rozpoznawalna
# i wskazuje projekt, zgodnie z wymaganiem sekcji piętnastej CLAUDE.md.
DOMYSLNA_NAZWA_KLIENTA = (
    "GeminiNotebookBuilder/0.1 (+https://github.com/Kamszot666/Gemini-Notebook-Builder)"
)
DOMYSLNY_LIMIT_CZASU_SEKUNDY = 20.0
DOMYSLNA_LICZBA_PONOWIEN = 3
DOMYSLNA_PODSTAWA_ODSTEPU_SEKUNDY = 1.0
DOMYSLNY_MAKSYMALNY_ODSTEP_SEKUNDY = 30.0
DOMYSLNY_ODSTEP_MIEDZY_ZADANIAMI_SEKUNDY = 1.0
DOMYSLNE_POLACZENIA_NA_DOMENE = 3
DOMYSLNE_RESPEKTOWANIE_ROBOTS = True
DOMYSLNY_MAKSYMALNY_ROZMIAR_POBRANIA_MB = 20

# Ustawienia pamięci podręcznej. Jest wspólna dla wszystkich projektów, żeby to
# samo źródło użyte w dwóch notatnikach pobierało się tylko raz.
DOMYSLNE_UZYWANIE_CACHE = True
DOMYSLNY_MAKSYMALNY_WIEK_CACHE_DNI = 30
NAZWA_PLIKU_CACHE = "cache.sqlite3"

NAZWA_KATALOGU_APLIKACJI_WINDOWS = "Gemini Notebook Builder"
NAZWA_KATALOGU_APLIKACJI_XDG = "gemini-notebook-builder"
NAZWA_PLIKU_KONFIGURACJI = "konfiguracja.toml"
NAZWA_PODKATALOGU_WYNIKOW = "Gemini Notebook Builder"
PREFIKS_ZMIENNYCH = "GNB_"

_DOZWOLONE_FORMATY = ("txt", "md")

# Napisy uznawane za prawdę i za fałsz w pliku konfiguracji oraz w zmiennych
# środowiskowych. W pliku TOML można też podać wprost wartość logiczną.
_WARTOSCI_PRAWDY = frozenset({"1", "tak", "true", "prawda", "on"})
_WARTOSCI_FALSZU = frozenset({"0", "nie", "false", "falsz", "fałsz", "off"})

# Mapowanie nazwy zmiennej środowiskowej na nazwę pola konfiguracji.
_ZMIENNE_SRODOWISKOWE: Mapping[str, str] = {
    PREFIKS_ZMIENNYCH + "KATALOG_WYNIKOW": "katalog_wynikow",
    PREFIKS_ZMIENNYCH + "LIMIT_ZRODEL": "limit_zrodel",
    PREFIKS_ZMIENNYCH + "BEZPIECZNY_LIMIT_SLOW": "bezpieczny_limit_slow",
    PREFIKS_ZMIENNYCH + "BEZPIECZNY_LIMIT_MB": "bezpieczny_limit_mb",
    PREFIKS_ZMIENNYCH + "FORMATY_WYNIKOWE": "formaty_wynikowe",
    PREFIKS_ZMIENNYCH + "ZACHOWUJ_ORYGINALY": "zachowuj_oryginaly",
    PREFIKS_ZMIENNYCH + "NAZWA_KLIENTA": "nazwa_klienta",
    PREFIKS_ZMIENNYCH + "LIMIT_CZASU_SEKUNDY": "limit_czasu_sekundy",
    PREFIKS_ZMIENNYCH + "LICZBA_PONOWIEN": "liczba_ponowien",
    PREFIKS_ZMIENNYCH + "PODSTAWA_ODSTEPU_SEKUNDY": "podstawa_odstepu_sekundy",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_ODSTEP_SEKUNDY": "maksymalny_odstep_sekundy",
    PREFIKS_ZMIENNYCH + "ODSTEP_MIEDZY_ZADANIAMI_SEKUNDY": "odstep_miedzy_zadaniami_sekundy",
    PREFIKS_ZMIENNYCH + "POLACZENIA_NA_DOMENE": "polaczenia_na_domene",
    PREFIKS_ZMIENNYCH + "RESPEKTUJ_ROBOTS": "respektuj_robots",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_ROZMIAR_POBRANIA_MB": "maksymalny_rozmiar_pobrania_mb",
    PREFIKS_ZMIENNYCH + "UZYWAJ_CACHE": "uzywaj_cache",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_WIEK_CACHE_DNI": "maksymalny_wiek_cache_dni",
    PREFIKS_ZMIENNYCH + "SCIEZKA_CACHE": "sciezka_cache",
    PREFIKS_ZMIENNYCH + "DODATKOWE_PARAMETRY_SLEDZACE": "dodatkowe_parametry_sledzace",
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


def _domyslna_sciezka_cache() -> Path:
    """Domyślna ścieżka wspólnej pamięci podręcznej: katalog danych aplikacji.

    Pamięć podręczna leży obok pliku konfiguracji, a nie wewnątrz katalogu
    projektu, ponieważ jest wspólna dla wszystkich projektów. To samo źródło
    użyte w dwóch notatnikach pobiera się dzięki temu tylko raz.
    """
    return sciezka_pliku_konfiguracji().parent / NAZWA_PLIKU_CACHE


@dataclass(frozen=True, slots=True)
class Konfiguracja:
    """Zestaw ustawień aplikacji w zakresie obsługiwanym przez etapy pierwszy i drugi."""

    katalog_wynikow: Path = field(default_factory=_domyslny_katalog_wynikow)
    limit_zrodel: int = DOMYSLNY_LIMIT_ZRODEL
    bezpieczny_limit_slow: int = DOMYSLNY_BEZPIECZNY_LIMIT_SLOW
    bezpieczny_limit_mb: int = DOMYSLNY_BEZPIECZNY_LIMIT_MB
    formaty_wynikowe: tuple[str, ...] = DOMYSLNE_FORMATY_WYNIKOWE
    zachowuj_oryginaly: bool = DOMYSLNE_ZACHOWYWANIE_ORYGINALOW
    nazwa_klienta: str = DOMYSLNA_NAZWA_KLIENTA
    limit_czasu_sekundy: float = DOMYSLNY_LIMIT_CZASU_SEKUNDY
    liczba_ponowien: int = DOMYSLNA_LICZBA_PONOWIEN
    podstawa_odstepu_sekundy: float = DOMYSLNA_PODSTAWA_ODSTEPU_SEKUNDY
    maksymalny_odstep_sekundy: float = DOMYSLNY_MAKSYMALNY_ODSTEP_SEKUNDY
    odstep_miedzy_zadaniami_sekundy: float = DOMYSLNY_ODSTEP_MIEDZY_ZADANIAMI_SEKUNDY
    polaczenia_na_domene: int = DOMYSLNE_POLACZENIA_NA_DOMENE
    respektuj_robots: bool = DOMYSLNE_RESPEKTOWANIE_ROBOTS
    maksymalny_rozmiar_pobrania_mb: int = DOMYSLNY_MAKSYMALNY_ROZMIAR_POBRANIA_MB
    uzywaj_cache: bool = DOMYSLNE_UZYWANIE_CACHE
    maksymalny_wiek_cache_dni: int = DOMYSLNY_MAKSYMALNY_WIEK_CACHE_DNI
    sciezka_cache: Path = field(default_factory=_domyslna_sciezka_cache)
    dodatkowe_parametry_sledzace: tuple[str, ...] = ()


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
        zachowuj_oryginaly=_jako_prawda_falsz(
            scalone, "zachowuj_oryginaly", domyslna.zachowuj_oryginaly
        ),
        nazwa_klienta=_jako_napis(scalone, "nazwa_klienta", domyslna.nazwa_klienta),
        limit_czasu_sekundy=_jako_liczba_rzeczywista(
            scalone, "limit_czasu_sekundy", domyslna.limit_czasu_sekundy
        ),
        liczba_ponowien=_jako_liczba_nieujemna(
            scalone, "liczba_ponowien", domyslna.liczba_ponowien
        ),
        podstawa_odstepu_sekundy=_jako_liczba_rzeczywista(
            scalone, "podstawa_odstepu_sekundy", domyslna.podstawa_odstepu_sekundy
        ),
        maksymalny_odstep_sekundy=_jako_liczba_rzeczywista(
            scalone, "maksymalny_odstep_sekundy", domyslna.maksymalny_odstep_sekundy
        ),
        odstep_miedzy_zadaniami_sekundy=_jako_liczba_rzeczywista(
            scalone,
            "odstep_miedzy_zadaniami_sekundy",
            domyslna.odstep_miedzy_zadaniami_sekundy,
            dopusc_zero=True,
        ),
        polaczenia_na_domene=_jako_liczba(
            scalone, "polaczenia_na_domene", domyslna.polaczenia_na_domene
        ),
        respektuj_robots=_jako_prawda_falsz(scalone, "respektuj_robots", domyslna.respektuj_robots),
        maksymalny_rozmiar_pobrania_mb=_jako_liczba(
            scalone, "maksymalny_rozmiar_pobrania_mb", domyslna.maksymalny_rozmiar_pobrania_mb
        ),
        uzywaj_cache=_jako_prawda_falsz(scalone, "uzywaj_cache", domyslna.uzywaj_cache),
        maksymalny_wiek_cache_dni=_jako_liczba(
            scalone, "maksymalny_wiek_cache_dni", domyslna.maksymalny_wiek_cache_dni
        ),
        sciezka_cache=(
            Path(str(scalone["sciezka_cache"]))
            if "sciezka_cache" in scalone
            else domyslna.sciezka_cache
        ),
        dodatkowe_parametry_sledzace=_jako_lista_napisow(
            scalone, "dodatkowe_parametry_sledzace", domyslna.dodatkowe_parametry_sledzace
        ),
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


def _jako_napis(scalone: Mapping[str, object], pole: str, domyslna: str) -> str:
    """Zwraca wartość pola jako napis, odrzucając wartość pustą."""
    if pole not in scalone:
        return domyslna
    napis = str(scalone[pole]).strip()
    if not napis:
        raise BladTrwaly(f"Ustawienie „{pole}” nie może być puste.")
    return napis


def _jako_liczba_nieujemna(scalone: Mapping[str, object], pole: str, domyslna: int) -> int:
    """Zwraca wartość pola jako liczbę całkowitą nieujemną.

    Zero jest tu poprawne, bo zero ponowień oznacza pracę bez ponawiania,
    a nie błąd konfiguracji.
    """
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
    if liczba < 0:
        raise BladTrwaly(f"Ustawienie „{pole}” nie może być ujemne, a jest {liczba}.")
    return liczba


def _jako_liczba_rzeczywista(
    scalone: Mapping[str, object], pole: str, domyslna: float, *, dopusc_zero: bool = False
) -> float:
    """Zwraca wartość pola jako liczbę zmiennoprzecinkową, w sekundach.

    Zero jest dopuszczalne tylko tam, gdzie ma sens, na przykład przy odstępie
    między żądaniami. Limit czasu równy zeru oznaczałby natychmiastowy timeout,
    więc jest odrzucany.
    """
    if pole not in scalone:
        return domyslna
    surowa = scalone[pole]
    if isinstance(surowa, bool) or not isinstance(surowa, (int, float, str)):
        raise BladTrwaly(f"Ustawienie „{pole}” musi być liczbą.")
    try:
        liczba = float(str(surowa).strip().replace(",", "."))
    except ValueError as blad:
        raise BladTrwaly(f"Ustawienie „{pole}” musi być liczbą, a jest „{surowa}”.") from blad
    if liczba < 0 or (liczba == 0 and not dopusc_zero):
        raise BladTrwaly(f"Ustawienie „{pole}” musi być liczbą dodatnią, a jest {liczba}.")
    return liczba


def _jako_lista_napisow(
    scalone: Mapping[str, object], pole: str, domyslna: tuple[str, ...]
) -> tuple[str, ...]:
    """Zwraca wartość pola jako krotkę napisów bez powtórzeń.

    W pliku TOML wartość podaje się jako listę, a w zmiennej środowiskowej jako
    wartości rozdzielone przecinkiem.
    """
    if pole not in scalone:
        return domyslna
    surowa = scalone[pole]
    if isinstance(surowa, (list, tuple)):
        elementy = [str(element).strip() for element in surowa]
    else:
        elementy = [czesc.strip() for czesc in str(surowa).split(",")]
    return tuple(dict.fromkeys(element for element in elementy if element))


def _jako_prawda_falsz(scalone: Mapping[str, object], pole: str, domyslna: bool) -> bool:
    """Zamienia wartość pola na wartość logiczną albo zgłasza błąd trwały.

    W pliku TOML przyjmowana jest wprost wartość logiczna. W zmiennej
    środowiskowej oraz w polu tekstowym przyjmowane są napisy „tak” i „nie”,
    „true” i „false”, „1” i „0” oraz kilka ich odpowiedników, niezależnie od
    wielkości liter.
    """
    if pole not in scalone:
        return domyslna
    surowa = scalone[pole]
    if isinstance(surowa, bool):
        return surowa
    napis = str(surowa).strip().lower()
    if napis in _WARTOSCI_PRAWDY:
        return True
    if napis in _WARTOSCI_FALSZU:
        return False
    raise BladTrwaly(
        f"Ustawienie „{pole}” musi być wartością logiczną, na przykład „tak” albo „nie”, "
        f"a jest „{surowa}”."
    )


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
