"""Wspólna pamięć podręczna pobranych zasobów, oparta na SQLite.

Pamięć podręczna jest jedna dla wszystkich projektów i leży w katalogu danych
aplikacji, obok pliku konfiguracji. Dzięki temu ten sam artykuł użyty w dwóch
notatnikach pobiera się tylko raz. Kluczem jest kanoniczna postać adresu, więc
dwa zapisy tego samego adresu różniące się parametrem śledzącym trafiają na ten
sam wpis.

Ponieważ plik jest wspólny, dwa uruchomienia aplikacji mogą go dotknąć naraz.
Z tego powodu włączony jest tryb WAL, ustawiony jest limit czasu oczekiwania na
blokadę, a zajętość bazy jest zgłaszana jako `BladPrzejsciowy`, czyli sytuacja
do ponowienia, nigdy jako awaria przetwarzania.

Zawartość pamięci podręcznej jest odtwarzalna, bo zawsze można pobrać zasób
ponownie. Dlatego niezgodna wersja schematu nie jest naprawiana migracją, tylko
świadomie odrzucana: tabele są tworzone od nowa, a stara zawartość znika.
Numer wersji jest zapisany w bazie, więc świadoma migracja będzie możliwa
później, gdy zawartość zacznie być kosztowna do odtworzenia.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly

WERSJA_SCHEMATU = 1
LIMIT_CZASU_BLOKADY_MS = 5000

_KOMUNIKAT_ZAJETEJ_BAZY = (
    "Pamięć podręczna jest w tej chwili zajęta przez inne uruchomienie aplikacji. "
    "Spróbuj ponownie za chwilę."
)


@dataclass(frozen=True, slots=True)
class WpisCache:
    """Jeden zapamiętany zasób wraz z danymi potrzebnymi do zapytania warunkowego."""

    klucz: str
    adres_koncowy: str
    kod_odpowiedzi: int
    typ_zawartosci: str
    deklarowane_kodowanie: str
    etag: str | None
    last_modified: str | None
    tresc: bytes
    pobrano: datetime

    def czy_swiezy(self, maksymalny_wiek_dni: int, teraz: datetime) -> bool:
        """Rozstrzyga, czy wpis mieści się w dopuszczalnym wieku."""
        return teraz - self.pobrano <= timedelta(days=maksymalny_wiek_dni)


class PamiecPodreczna:
    """Dostęp do pliku pamięci podręcznej. Otwiera połączenie i tworzy schemat."""

    def __init__(self, sciezka: Path) -> None:
        self._sciezka = sciezka
        sciezka.parent.mkdir(parents=True, exist_ok=True)
        with _zamien_bledy_sqlite():
            self._polaczenie = sqlite3.connect(sciezka, timeout=LIMIT_CZASU_BLOKADY_MS / 1000)
            self._polaczenie.execute("PRAGMA journal_mode = WAL")
            self._polaczenie.execute(f"PRAGMA busy_timeout = {LIMIT_CZASU_BLOKADY_MS}")
            self._przygotuj_schemat()

    @property
    def sciezka(self) -> Path:
        """Ścieżka pliku pamięci podręcznej, pokazywana użytkownikowi."""
        return self._sciezka

    def odczytaj(self, klucz: str) -> WpisCache | None:
        """Zwraca zapamiętany zasób albo wartość pustą, gdy go nie ma."""
        with _zamien_bledy_sqlite():
            wiersz = self._polaczenie.execute(
                "SELECT klucz, adres_koncowy, kod_odpowiedzi, typ_zawartosci, "
                "deklarowane_kodowanie, etag, last_modified, tresc, pobrano "
                "FROM zasoby WHERE klucz = ?",
                (klucz,),
            ).fetchone()
        if wiersz is None:
            return None
        return WpisCache(
            klucz=wiersz[0],
            adres_koncowy=wiersz[1],
            kod_odpowiedzi=wiersz[2],
            typ_zawartosci=wiersz[3],
            deklarowane_kodowanie=wiersz[4],
            etag=wiersz[5],
            last_modified=wiersz[6],
            tresc=wiersz[7],
            pobrano=datetime.fromisoformat(wiersz[8]),
        )

    def zapisz(self, wpis: WpisCache) -> None:
        """Zapisuje zasób, nadpisując wcześniejszy wpis o tym samym kluczu."""
        with _zamien_bledy_sqlite(), self._polaczenie:
            self._polaczenie.execute(
                "INSERT INTO zasoby (klucz, adres_koncowy, kod_odpowiedzi, typ_zawartosci, "
                "deklarowane_kodowanie, etag, last_modified, tresc, pobrano) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(klucz) DO UPDATE SET adres_koncowy = excluded.adres_koncowy, "
                "kod_odpowiedzi = excluded.kod_odpowiedzi, "
                "typ_zawartosci = excluded.typ_zawartosci, "
                "deklarowane_kodowanie = excluded.deklarowane_kodowanie, "
                "etag = excluded.etag, last_modified = excluded.last_modified, "
                "tresc = excluded.tresc, pobrano = excluded.pobrano",
                (
                    wpis.klucz,
                    wpis.adres_koncowy,
                    wpis.kod_odpowiedzi,
                    wpis.typ_zawartosci,
                    wpis.deklarowane_kodowanie,
                    wpis.etag,
                    wpis.last_modified,
                    wpis.tresc,
                    wpis.pobrano.isoformat(),
                ),
            )

    def odswiez_czas_pobrania(self, klucz: str, moment: datetime) -> None:
        """Przesuwa czas pobrania wpisu, gdy serwer potwierdził jego aktualność.

        Używane po odpowiedzi 304, która oznacza, że zapamiętana treść jest
        nadal aktualna i nie trzeba pobierać jej ponownie.
        """
        with _zamien_bledy_sqlite(), self._polaczenie:
            self._polaczenie.execute(
                "UPDATE zasoby SET pobrano = ? WHERE klucz = ?", (moment.isoformat(), klucz)
            )

    def usun_przeterminowane(self, maksymalny_wiek_dni: int, teraz: datetime) -> int:
        """Usuwa wpisy starsze niż podany wiek i zwraca liczbę usuniętych."""
        granica = (teraz - timedelta(days=maksymalny_wiek_dni)).isoformat()
        with _zamien_bledy_sqlite(), self._polaczenie:
            kursor = self._polaczenie.execute("DELETE FROM zasoby WHERE pobrano < ?", (granica,))
        return kursor.rowcount if kursor.rowcount and kursor.rowcount > 0 else 0

    def wyczysc(self) -> int:
        """Usuwa całą zawartość pamięci podręcznej i zwraca liczbę usuniętych wpisów."""
        with _zamien_bledy_sqlite(), self._polaczenie:
            liczba = self._polaczenie.execute("SELECT COUNT(*) FROM zasoby").fetchone()[0]
            self._polaczenie.execute("DELETE FROM zasoby")
        return int(liczba)

    def liczba_wpisow(self) -> int:
        """Zwraca liczbę zapamiętanych zasobów."""
        with _zamien_bledy_sqlite():
            return int(self._polaczenie.execute("SELECT COUNT(*) FROM zasoby").fetchone()[0])

    def zamknij(self) -> None:
        """Zamyka połączenie z bazą."""
        self._polaczenie.close()

    def __enter__(self) -> PamiecPodreczna:
        return self

    def __exit__(self, typ: object, wartosc: object, slad: object) -> None:
        self.zamknij()

    def _przygotuj_schemat(self) -> None:
        """Tworzy schemat albo odrzuca zawartość zapisaną w innej wersji schematu."""
        with self._polaczenie:
            self._polaczenie.execute(
                "CREATE TABLE IF NOT EXISTS wersja_schematu (numer INTEGER NOT NULL)"
            )
            wiersz = self._polaczenie.execute("SELECT numer FROM wersja_schematu").fetchone()
            if wiersz is not None and int(wiersz[0]) != WERSJA_SCHEMATU:
                self._polaczenie.execute("DROP TABLE IF EXISTS zasoby")
                self._polaczenie.execute("DELETE FROM wersja_schematu")
                wiersz = None
            if wiersz is None:
                self._polaczenie.execute(
                    "INSERT INTO wersja_schematu (numer) VALUES (?)", (WERSJA_SCHEMATU,)
                )
            self._polaczenie.execute(
                "CREATE TABLE IF NOT EXISTS zasoby ("
                "klucz TEXT PRIMARY KEY, "
                "adres_koncowy TEXT NOT NULL, "
                "kod_odpowiedzi INTEGER NOT NULL, "
                "typ_zawartosci TEXT NOT NULL, "
                "deklarowane_kodowanie TEXT NOT NULL, "
                "etag TEXT, "
                "last_modified TEXT, "
                "tresc BLOB NOT NULL, "
                "pobrano TEXT NOT NULL)"
            )


def otworz(sciezka: Path) -> PamiecPodreczna:
    """Otwiera pamięć podręczną pod wskazaną ścieżką, tworząc plik w razie potrzeby."""
    return PamiecPodreczna(sciezka)


def wyczysc_pamiec_podreczna(sciezka: Path) -> int:
    """Czyści pamięć podręczną i zwraca liczbę usuniętych wpisów.

    Funkcja istnieje po to, żeby użytkownik mógł opróżnić pamięć podręczną
    poleceniem aplikacji, bez szukania plików po dysku.
    """
    if not sciezka.exists():
        return 0
    with otworz(sciezka) as pamiec:
        return pamiec.wyczysc()


def teraz_utc() -> datetime:
    """Zwraca bieżący moment w czasie UTC, używany do znaczników pamięci podręcznej."""
    return datetime.now(UTC)


@contextmanager
def _zamien_bledy_sqlite() -> Iterator[None]:
    """Zamienia błędy SQLite na wyjątki projektu, z podziałem na przejściowe i trwałe."""
    try:
        yield
    except sqlite3.OperationalError as blad:
        if "locked" in str(blad).lower() or "busy" in str(blad).lower():
            raise BladPrzejsciowy(_KOMUNIKAT_ZAJETEJ_BAZY) from blad
        raise BladTrwaly(f"Błąd pamięci podręcznej: {blad}") from blad
    except sqlite3.DatabaseError as blad:
        raise BladTrwaly(f"Plik pamięci podręcznej jest uszkodzony: {blad}") from blad
