"""Konfiguracja aplikacji w zakresie obsługiwanym przez etapy od pierwszego do piątego.

Moduł buduje konfigurację z trzech źródeł, w kolejności rosnącego pierwszeństwa:
wartości domyślne zapisane w kodzie, plik TOML oraz zmienne środowiskowe
z prefiksem ``GNB_``. Brak pliku konfiguracji nie jest błędem — obowiązują
wtedy wartości domyślne.

Obsługiwane są pola potrzebne w dotychczasowych etapach: katalog nadrzędny
wyników, limit liczby źródeł, bezpieczny limit słów, bezpieczny limit megabajtów,
lista formatów wynikowych, zachowywanie oryginałów źródeł, ustawienia pobierania
stron: nazwa klienta, limit czasu, ponowienia, odstępy, liczba połączeń na
domenę, respektowanie pliku robots, pamięć podręczna i dodatkowe parametry
śledzące, ustawienia napisów filmów: języki, zgoda na napisy automatyczne
i tłumaczone oraz znaczniki czasu, włączenie i progi kolejnych etapów
deduplikacji, a także ustawienia interfejsu WWW: adres i port nasłuchu, limit
znaków pola instrukcji systemowej notatnika oraz limit rozmiaru wysyłanego
pliku. Pozostałe pola wymienione w sekcji jedenastej a pliku CLAUDE.md dojdą
w kolejnych etapach.

Adres nasłuchu musi wskazywać pętlę zwrotną. Sekcja jedenasta CLAUDE.md zakazuje
nasłuchu na innym adresie, ponieważ interfejs nie ma uwierzytelniania, więc
wartość spoza pętli zwrotnej kończy się błędem trwałym, a nie cichym
zastąpieniem wartością domyślną.
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
DOMYSLNE_ZACHOWYWANIE_ODNOSNIKOW = True

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

# Wyjątek od kontroli robots.txt dla adresów wskazanych wprost przez użytkownika.
# Uzasadnienie i cztery warunki zakresu opisuje sekcja piętnasta CLAUDE.md,
# podsekcja o wyjątku dla źródeł wskazanych jawnie.
DOMYSLNY_WYJATEK_ROBOTS_DLA_ZRODEL_JAWNYCH = True
DOMYSLNY_MAKSYMALNY_ROZMIAR_POBRANIA_MB = 20

# Pusta wartość oznacza magazyn zaufanych certyfikatów wbudowany w bibliotekę
# HTTP. Własny plik PEM jest potrzebny tam, gdzie ruch przechodzi przez firmowy
# serwer pośredniczący albo program antywirusowy podstawiający własny
# certyfikat. Nie ma i nie będzie opcji wyłączającej weryfikację certyfikatu,
# ponieważ byłoby to obejście zabezpieczenia, zakazane w sekcji trzeciej
# CLAUDE.md.
DOMYSLNA_SCIEZKA_CERTYFIKATOW = ""

# Ustawienia pamięci podręcznej. Jest wspólna dla wszystkich projektów, żeby to
# samo źródło użyte w dwóch notatnikach pobierało się tylko raz.
DOMYSLNE_UZYWANIE_CACHE = True
DOMYSLNY_MAKSYMALNY_WIEK_CACHE_DNI = 30
NAZWA_PLIKU_CACHE = "cache.sqlite3"

# Ustawienia napisów filmów. Kolejność języków jest kolejnością preferencji.
DOMYSLNE_JEZYKI_NAPISOW: tuple[str, ...] = ("pl", "en")
DOMYSLNE_NAPISY_AUTOMATYCZNE = True
DOMYSLNE_NAPISY_TLUMACZONE = False
DOMYSLNY_AWARYJNY_DOWOLNY_JEZYK = True
DOMYSLNE_ZNACZNIKI_CZASU = False

# Ustawienia deduplikacji. Etapy pierwszy, drugi i trzeci z sekcji szesnastej
# CLAUDE.md są domyślnie włączone. Etap embeddingów lokalnych jest domyślnie
# wyłączony i pozostaje poza zakresem etapu piątego. Próg pewnego duplikatu i
# niższy próg do ręcznego rozstrzygnięcia dotyczą wyłącznie etapu trzeciego,
# bo etapy pierwszy i drugi porównują treść dokładnie.
DOMYSLNA_DEDUPLIKACJA_HASH_WLACZONA = True
DOMYSLNA_DEDUPLIKACJA_KOSMETYCZNA_WLACZONA = True
DOMYSLNA_DEDUPLIKACJA_PODOBIENSTWO_WLACZONE = True
DOMYSLNE_DEDUPLIKACJA_EMBEDDINGI_WLACZONE = False
DOMYSLNY_DEDUPLIKACJA_PROG_DUPLIKATU = 0.9
DOMYSLNY_DEDUPLIKACJA_PROG_DO_PRZEGLADU = 0.75

# Ustawienia interfejsu WWW. Adres nasłuchu jest domyślnie pętlą zwrotną i musi
# nią pozostać, dopóki interfejs nie ma uwierzytelniania, zgodnie z sekcją
# jedenastą CLAUDE.md. Limit znaków instrukcji systemowej wynika wprost z sekcji
# jedenastej a. Limit rozmiaru wysyłanego pliku chroni serwer przed wyczerpaniem
# pamięci przy wysyłce dużego pliku binarnego.
DOMYSLNY_ADRES_NASLUCHU = "127.0.0.1"
DOMYSLNY_PORT_NASLUCHU = 8765
DOMYSLNY_LIMIT_ZNAKOW_INSTRUKCJI_SYSTEMOWEJ = 10_000
DOMYSLNY_MAKSYMALNY_ROZMIAR_WYSYLKI_MB = 190

# Adresy uznawane za pętlę zwrotną. „localhost” jest dopuszczony, bo w praktyce
# rozwiązuje się na adres pętli zwrotnej, a użytkownicy tak właśnie wpisują adres
# w przeglądarce.
_ADRESY_PETLI_ZWROTNEJ = frozenset({"127.0.0.1", "localhost", "::1"})
_MAKSYMALNY_NUMER_PORTU = 65535

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
    PREFIKS_ZMIENNYCH + "ZACHOWUJ_ODNOSNIKI": "zachowuj_odnosniki",
    PREFIKS_ZMIENNYCH + "NAZWA_KLIENTA": "nazwa_klienta",
    PREFIKS_ZMIENNYCH + "LIMIT_CZASU_SEKUNDY": "limit_czasu_sekundy",
    PREFIKS_ZMIENNYCH + "LICZBA_PONOWIEN": "liczba_ponowien",
    PREFIKS_ZMIENNYCH + "PODSTAWA_ODSTEPU_SEKUNDY": "podstawa_odstepu_sekundy",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_ODSTEP_SEKUNDY": "maksymalny_odstep_sekundy",
    PREFIKS_ZMIENNYCH + "ODSTEP_MIEDZY_ZADANIAMI_SEKUNDY": "odstep_miedzy_zadaniami_sekundy",
    PREFIKS_ZMIENNYCH + "POLACZENIA_NA_DOMENE": "polaczenia_na_domene",
    PREFIKS_ZMIENNYCH + "RESPEKTUJ_ROBOTS": "respektuj_robots",
    PREFIKS_ZMIENNYCH + "WYJATEK_ROBOTS_DLA_ZRODEL_JAWNYCH": "wyjatek_robots_dla_zrodel_jawnych",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_ROZMIAR_POBRANIA_MB": "maksymalny_rozmiar_pobrania_mb",
    PREFIKS_ZMIENNYCH + "SCIEZKA_CERTYFIKATOW": "sciezka_certyfikatow",
    PREFIKS_ZMIENNYCH + "UZYWAJ_CACHE": "uzywaj_cache",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_WIEK_CACHE_DNI": "maksymalny_wiek_cache_dni",
    PREFIKS_ZMIENNYCH + "SCIEZKA_CACHE": "sciezka_cache",
    PREFIKS_ZMIENNYCH + "DODATKOWE_PARAMETRY_SLEDZACE": "dodatkowe_parametry_sledzace",
    PREFIKS_ZMIENNYCH + "JEZYKI_NAPISOW": "jezyki_napisow",
    PREFIKS_ZMIENNYCH + "NAPISY_AUTOMATYCZNE": "napisy_automatyczne",
    PREFIKS_ZMIENNYCH + "NAPISY_TLUMACZONE": "napisy_tlumaczone",
    PREFIKS_ZMIENNYCH + "AWARYJNY_DOWOLNY_JEZYK": "awaryjny_dowolny_jezyk",
    PREFIKS_ZMIENNYCH + "ZNACZNIKI_CZASU": "znaczniki_czasu",
    PREFIKS_ZMIENNYCH + "DEDUPLIKACJA_HASH_WLACZONA": "deduplikacja_hash_wlaczona",
    PREFIKS_ZMIENNYCH + "DEDUPLIKACJA_KOSMETYCZNA_WLACZONA": "deduplikacja_kosmetyczna_wlaczona",
    PREFIKS_ZMIENNYCH + "DEDUPLIKACJA_PODOBIENSTWO_WLACZONE": "deduplikacja_podobienstwo_wlaczone",
    PREFIKS_ZMIENNYCH + "DEDUPLIKACJA_EMBEDDINGI_WLACZONE": "deduplikacja_embeddingi_wlaczone",
    PREFIKS_ZMIENNYCH + "DEDUPLIKACJA_PROG_DUPLIKATU": "deduplikacja_prog_duplikatu",
    PREFIKS_ZMIENNYCH + "DEDUPLIKACJA_PROG_DO_PRZEGLADU": "deduplikacja_prog_do_przegladu",
    PREFIKS_ZMIENNYCH + "ADRES_NASLUCHU": "adres_nasluchu",
    PREFIKS_ZMIENNYCH + "PORT_NASLUCHU": "port_nasluchu",
    PREFIKS_ZMIENNYCH + "LIMIT_ZNAKOW_INSTRUKCJI_SYSTEMOWEJ": "limit_znakow_instrukcji_systemowej",
    PREFIKS_ZMIENNYCH + "MAKSYMALNY_ROZMIAR_WYSYLKI_MB": "maksymalny_rozmiar_wysylki_mb",
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
    zachowuj_odnosniki: bool = DOMYSLNE_ZACHOWYWANIE_ODNOSNIKOW
    nazwa_klienta: str = DOMYSLNA_NAZWA_KLIENTA
    limit_czasu_sekundy: float = DOMYSLNY_LIMIT_CZASU_SEKUNDY
    liczba_ponowien: int = DOMYSLNA_LICZBA_PONOWIEN
    podstawa_odstepu_sekundy: float = DOMYSLNA_PODSTAWA_ODSTEPU_SEKUNDY
    maksymalny_odstep_sekundy: float = DOMYSLNY_MAKSYMALNY_ODSTEP_SEKUNDY
    odstep_miedzy_zadaniami_sekundy: float = DOMYSLNY_ODSTEP_MIEDZY_ZADANIAMI_SEKUNDY
    polaczenia_na_domene: int = DOMYSLNE_POLACZENIA_NA_DOMENE
    respektuj_robots: bool = DOMYSLNE_RESPEKTOWANIE_ROBOTS
    wyjatek_robots_dla_zrodel_jawnych: bool = DOMYSLNY_WYJATEK_ROBOTS_DLA_ZRODEL_JAWNYCH
    maksymalny_rozmiar_pobrania_mb: int = DOMYSLNY_MAKSYMALNY_ROZMIAR_POBRANIA_MB
    sciezka_certyfikatow: str = DOMYSLNA_SCIEZKA_CERTYFIKATOW
    uzywaj_cache: bool = DOMYSLNE_UZYWANIE_CACHE
    maksymalny_wiek_cache_dni: int = DOMYSLNY_MAKSYMALNY_WIEK_CACHE_DNI
    sciezka_cache: Path = field(default_factory=_domyslna_sciezka_cache)
    dodatkowe_parametry_sledzace: tuple[str, ...] = ()
    jezyki_napisow: tuple[str, ...] = DOMYSLNE_JEZYKI_NAPISOW
    napisy_automatyczne: bool = DOMYSLNE_NAPISY_AUTOMATYCZNE
    napisy_tlumaczone: bool = DOMYSLNE_NAPISY_TLUMACZONE
    awaryjny_dowolny_jezyk: bool = DOMYSLNY_AWARYJNY_DOWOLNY_JEZYK
    znaczniki_czasu: bool = DOMYSLNE_ZNACZNIKI_CZASU
    deduplikacja_hash_wlaczona: bool = DOMYSLNA_DEDUPLIKACJA_HASH_WLACZONA
    deduplikacja_kosmetyczna_wlaczona: bool = DOMYSLNA_DEDUPLIKACJA_KOSMETYCZNA_WLACZONA
    deduplikacja_podobienstwo_wlaczone: bool = DOMYSLNA_DEDUPLIKACJA_PODOBIENSTWO_WLACZONE
    deduplikacja_embeddingi_wlaczone: bool = DOMYSLNE_DEDUPLIKACJA_EMBEDDINGI_WLACZONE
    deduplikacja_prog_duplikatu: float = DOMYSLNY_DEDUPLIKACJA_PROG_DUPLIKATU
    deduplikacja_prog_do_przegladu: float = DOMYSLNY_DEDUPLIKACJA_PROG_DO_PRZEGLADU
    adres_nasluchu: str = DOMYSLNY_ADRES_NASLUCHU
    port_nasluchu: int = DOMYSLNY_PORT_NASLUCHU
    limit_znakow_instrukcji_systemowej: int = DOMYSLNY_LIMIT_ZNAKOW_INSTRUKCJI_SYSTEMOWEJ
    maksymalny_rozmiar_wysylki_mb: int = DOMYSLNY_MAKSYMALNY_ROZMIAR_WYSYLKI_MB


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
    konfiguracja = Konfiguracja(
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
        zachowuj_odnosniki=_jako_prawda_falsz(
            scalone, "zachowuj_odnosniki", domyslna.zachowuj_odnosniki
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
        sciezka_certyfikatow=_jako_sciezka_pliku(
            scalone, "sciezka_certyfikatow", domyslna.sciezka_certyfikatow
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
        jezyki_napisow=_jako_lista_napisow(scalone, "jezyki_napisow", domyslna.jezyki_napisow),
        napisy_automatyczne=_jako_prawda_falsz(
            scalone, "napisy_automatyczne", domyslna.napisy_automatyczne
        ),
        napisy_tlumaczone=_jako_prawda_falsz(
            scalone, "napisy_tlumaczone", domyslna.napisy_tlumaczone
        ),
        awaryjny_dowolny_jezyk=_jako_prawda_falsz(
            scalone, "awaryjny_dowolny_jezyk", domyslna.awaryjny_dowolny_jezyk
        ),
        znaczniki_czasu=_jako_prawda_falsz(scalone, "znaczniki_czasu", domyslna.znaczniki_czasu),
        deduplikacja_hash_wlaczona=_jako_prawda_falsz(
            scalone, "deduplikacja_hash_wlaczona", domyslna.deduplikacja_hash_wlaczona
        ),
        deduplikacja_kosmetyczna_wlaczona=_jako_prawda_falsz(
            scalone, "deduplikacja_kosmetyczna_wlaczona", domyslna.deduplikacja_kosmetyczna_wlaczona
        ),
        deduplikacja_podobienstwo_wlaczone=_jako_prawda_falsz(
            scalone,
            "deduplikacja_podobienstwo_wlaczone",
            domyslna.deduplikacja_podobienstwo_wlaczone,
        ),
        deduplikacja_embeddingi_wlaczone=_jako_prawda_falsz(
            scalone, "deduplikacja_embeddingi_wlaczone", domyslna.deduplikacja_embeddingi_wlaczone
        ),
        deduplikacja_prog_duplikatu=_jako_ulamek(
            scalone, "deduplikacja_prog_duplikatu", domyslna.deduplikacja_prog_duplikatu
        ),
        deduplikacja_prog_do_przegladu=_jako_ulamek(
            scalone, "deduplikacja_prog_do_przegladu", domyslna.deduplikacja_prog_do_przegladu
        ),
        adres_nasluchu=_jako_adres_nasluchu(scalone, "adres_nasluchu", domyslna.adres_nasluchu),
        port_nasluchu=_jako_port(scalone, "port_nasluchu", domyslna.port_nasluchu),
        limit_znakow_instrukcji_systemowej=_jako_liczba(
            scalone,
            "limit_znakow_instrukcji_systemowej",
            domyslna.limit_znakow_instrukcji_systemowej,
        ),
        maksymalny_rozmiar_wysylki_mb=_jako_liczba(
            scalone, "maksymalny_rozmiar_wysylki_mb", domyslna.maksymalny_rozmiar_wysylki_mb
        ),
    )
    if konfiguracja.deduplikacja_prog_do_przegladu > konfiguracja.deduplikacja_prog_duplikatu:
        raise BladTrwaly(
            "Ustawienie „deduplikacja_prog_do_przegladu” "
            f"({konfiguracja.deduplikacja_prog_do_przegladu}) nie może być wyższe niż "
            f"„deduplikacja_prog_duplikatu” ({konfiguracja.deduplikacja_prog_duplikatu}). "
            "Niższy próg oznacza parę do ręcznego rozstrzygnięcia, wyższy — pewny duplikat."
        )
    return konfiguracja


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


def _jako_adres_nasluchu(scalone: Mapping[str, object], pole: str, domyslna: str) -> str:
    """Zwraca adres nasłuchu, odrzucając wszystko poza pętlą zwrotną.

    Sekcja jedenasta CLAUDE.md zakazuje nasłuchu na adresie innym niż pętla
    zwrotna, dopóki interfejs nie ma uwierzytelniania. Wartość spoza pętli
    zwrotnej kończy się więc błędem trwałym z czytelnym komunikatem, a nie cichym
    zastąpieniem wartością domyślną, żeby pomyłka w konfiguracji nie wystawiła
    interfejsu do sieci bez wiedzy użytkownika.
    """
    if pole not in scalone:
        return domyslna
    napis = str(scalone[pole]).strip()
    if not napis:
        return domyslna
    if napis not in _ADRESY_PETLI_ZWROTNEJ:
        dozwolone = ", ".join(sorted(_ADRESY_PETLI_ZWROTNEJ))
        raise BladTrwaly(
            f"Ustawienie „{pole}” musi wskazywać pętlę zwrotną ({dozwolone}), a jest „{napis}”. "
            "Sekcja jedenasta CLAUDE.md zakazuje nasłuchu na innym adresie, ponieważ interfejs "
            "nie ma uwierzytelniania."
        )
    return napis


def _jako_port(scalone: Mapping[str, object], pole: str, domyslna: int) -> int:
    """Zwraca numer portu nasłuchu z przedziału od jednego do sześćdziesięciu pięciu tysięcy."""
    liczba = _jako_liczba(scalone, pole, domyslna)
    if liczba > _MAKSYMALNY_NUMER_PORTU:
        raise BladTrwaly(
            f"Ustawienie „{pole}” musi być numerem portu od 1 do {_MAKSYMALNY_NUMER_PORTU}, "
            f"a jest {liczba}."
        )
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


def _jako_ulamek(scalone: Mapping[str, object], pole: str, domyslna: float) -> float:
    """Zwraca wartość pola jako liczbę z przedziału od zera wyłącznie do jednego włącznie.

    Progi deduplikacji są ułamkami podobieństwa, więc wartość spoza tego
    przedziału jest błędem konfiguracji, a nie ostrzeżeniem do zignorowania.
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
    if not 0 < liczba <= 1:
        raise BladTrwaly(
            f"Ustawienie „{pole}” musi mieścić się w przedziale od zera do jednego, "
            f"a jest {liczba}."
        )
    return liczba


def _jako_sciezka_pliku(scalone: Mapping[str, object], pole: str, domyslna: str) -> str:
    """Zwraca ścieżkę pliku podaną w konfiguracji, sprawdzając, czy plik istnieje.

    Wartość pusta jest poprawna i oznacza użycie ustawienia domyślnego.
    Wskazanie nieistniejącego pliku jest błędem trwałym, ponieważ cicha praca
    z pominięciem takiego ustawienia kończyłaby się niezrozumiałymi błędami
    połączenia przy każdym adresie.
    """
    if pole not in scalone:
        return domyslna
    napis = str(scalone[pole]).strip()
    if not napis:
        return ""
    if not Path(napis).is_file():
        raise BladTrwaly(
            f"Ustawienie „{pole}” wskazuje plik, którego nie ma: {napis}. "
            "Podaj poprawną ścieżkę albo usuń to ustawienie."
        )
    return napis


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
