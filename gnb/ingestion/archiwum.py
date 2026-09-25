"""Rozwijanie archiwów ZIP na osobne pliki wejściowe, z limitami i ochroną ścieżek.

Archiwum ZIP nie jest źródłem, tylko pojemnikiem na źródła. Ten moduł rozpakowuje
je do katalogu projektu i zwraca listę zwykłych wejść plikowych, które potok
przetwarza tymi samymi adapterami co pliki podane wprost. Każdy wpis archiwum jest
albo przyjęty jako wejście, albo pominięty z powodem, a całość jest opisana
w wyniku rozwinięcia, żeby trafiła do checkpointu, manifestu i raportu: element
pominięty po cichu jest gorszy niż błąd.

Archiwum bywa bombą kompresji albo nośnikiem ścieżek wychodzących poza katalog
docelowy, więc odczyt ma pięć zabezpieczeń.

1. Nic nie jest zapisywane pod nazwą z archiwum. Plik trafia do katalogu projektu
   pod nazwą własną: numer wpisu i oczyszczona nazwa końcowa, bez katalogów.
   Nazwa z archiwum służy wyłącznie do opisu pochodzenia w manifeście.
2. Wpis ze ścieżką bezwzględną, literą dysku, składnikiem `..`, dowiązaniem
   symbolicznym albo znakiem zerowym jest pomijany z komunikatem.
3. Limity liczby plików, łącznego rozmiaru po rozpakowaniu i stosunku kompresji
   dotyczą całego archiwum. Ich przekroczenie pomija całe archiwum, nigdy jego
   część: niekompletny zbiór dokumentów w notatniku, bez informacji, że czegoś
   brakuje, byłby cichą utratą treści. Rozmiar jest liczony zarówno według
   deklaracji w archiwum, jak i według faktycznie odczytanych bajtów.
4. Archiwum w archiwum jest rozwijane do ograniczonej głębokości. Głębsze wpisy są
   pomijane z komunikatem.
5. Wpisy zaszyfrowane są pomijane. Aplikacja nie próbuje haseł.

Moduł nie łączy plików z archiwum w grupy: grupa jest nadawana wyłącznie wtedy,
gdy użytkownik podał jej nazwę dla archiwum, i wtedy dziedziczą ją wszystkie pliki.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import stat
import zipfile
import zlib
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

from gnb.core.identyfikatory import suma_kontrolna_pliku
from gnb.ingestion.wejscie import (
    FORMATY_NUTY_GUITAR_PRO_NIEOBSLUGIWANE,
    FORMATY_PLIKOW,
    PozycjaWejsciowa,
    przyjmij_plik,
)

FORMAT_ARCHIWUM = "zip"
ROZDZIELACZ_POCHODZENIA = " » "

STATUS_ROZWINIETE = "rozwiniete"
STATUS_POMINIETE = "pominiete"
STATUS_WPISU_PRZYJETY = "przyjety"
STATUS_WPISU_POMINIETY = "pominiety"

_BAJTOW_W_MEGABAJCIE = 1024 * 1024
_ROZMIAR_PORCJI = 1024 * 1024
_MAKSYMALNA_DLUGOSC_NAZWY = 80
_FLAGA_SZYFROWANIA = 0x1
_FLAGA_UTF8 = 0x800
_WZORZEC_LITERY_DYSKU = re.compile(r"^[A-Za-z]:")
_WZORZEC_ZNAKOW_NIEDOZWOLONYCH = re.compile(r"[^\w.\- ()\[\]]", re.UNICODE)

# Nazwy plików metadanych, które programy dopisują do archiwów, a które nie są
# treścią autora. Nie są odczytywane, ale są wymienione jako pominięte.
_NAZWY_METADANYCH = frozenset({".ds_store", "thumbs.db", "desktop.ini"})
_KATALOGI_METADANYCH = ("__macosx/",)


@dataclass(frozen=True, slots=True)
class LimityArchiwum:
    """Limity rozwijania archiwum, pochodzące z konfiguracji."""

    maksymalna_liczba_plikow: int = 200
    maksymalny_rozmiar_bajtow: int = 500 * _BAJTOW_W_MEGABAJCIE
    maksymalny_stosunek_kompresji: int = 200
    maksymalne_zaglebienie: int = 2

    @classmethod
    def z_konfiguracji(
        cls, liczba_plikow: int, rozmiar_mb: int, stosunek_kompresji: int, zaglebienie: int
    ) -> LimityArchiwum:
        return cls(
            maksymalna_liczba_plikow=liczba_plikow,
            maksymalny_rozmiar_bajtow=rozmiar_mb * _BAJTOW_W_MEGABAJCIE,
            maksymalny_stosunek_kompresji=stosunek_kompresji,
            maksymalne_zaglebienie=zaglebienie,
        )


@dataclass(slots=True)
class WpisArchiwum:
    """Jeden plik z archiwum: przyjęty jako wejście albo pominięty z powodem."""

    sciezka: str
    status: str
    format: str = ""
    rozmiar_bajtow: int = 0
    komunikat: str | None = None
    suma_kontrolna: str | None = None


@dataclass(slots=True)
class WynikRozwiniecia:
    """Wynik rozwinięcia jednego archiwum: opis wpisów oraz wejścia do przetworzenia."""

    nazwa: str
    suma_kontrolna: str
    status: str
    komunikat: str | None = None
    wpisy: list[WpisArchiwum] = field(default_factory=list)
    pozycje: list[PozycjaWejsciowa] = field(default_factory=list)
    ostrzezenia: list[str] = field(default_factory=list)


class _PrzekroczonoLimitArchiwum(Exception):
    """Sygnał wewnętrzny: limit dotyczący całego archiwum został przekroczony."""


@dataclass(slots=True)
class _Stan:
    """Liczniki i wyniki jednego rozwijania, wspólne dla archiwum i archiwów zagnieżdżonych."""

    nazwa_glownego: str
    katalog: Path
    limity: LimityArchiwum
    moment: datetime
    grupa: str | None
    liczba_plikow: int = 0
    rozmiar_deklarowany: int = 0
    rozmiar_odczytany: int = 0
    numer_pliku: int = 0
    wpisy: list[WpisArchiwum] = field(default_factory=list)
    pozycje: list[PozycjaWejsciowa] = field(default_factory=list)


def czy_archiwum(format_zrodla: str) -> bool:
    """Zwraca prawdę, gdy format oznacza archiwum ZIP."""
    return format_zrodla == FORMAT_ARCHIWUM


def rozwin_archiwum(
    sciezka: Path,
    katalog_bazowy: Path,
    limity: LimityArchiwum,
    moment: datetime,
    *,
    grupa: str | None = None,
) -> WynikRozwiniecia:
    """Rozwija archiwum do katalogu docelowego i zwraca opis oraz wejścia do przetworzenia.

    Katalog docelowy jest tworzony pod katalogiem bazowym, pod nazwą z początku
    sumy kontrolnej archiwum, więc ponowne dodanie tego samego archiwum trafia
    w to samo miejsce, a dwa różne archiwa o tej samej nazwie się nie mieszają.
    Przy przekroczeniu
    limitu całego archiwum albo błędzie zapisu jest usuwany razem z wszystkim, co
    do tej pory rozpakowano, a wynik ma status pominięcia i pustą listę wejść.
    """
    try:
        suma = suma_kontrolna_pliku(sciezka)
    except OSError as blad:
        return WynikRozwiniecia(
            nazwa=sciezka.name,
            suma_kontrolna="",
            status=STATUS_POMINIETE,
            komunikat=f"Nie udało się odczytać pliku archiwum: {blad.strerror or blad}.",
        )
    wynik = WynikRozwiniecia(nazwa=sciezka.name, suma_kontrolna=suma, status=STATUS_ROZWINIETE)
    katalog_docelowy = katalog_bazowy / suma[:16]
    stan = _Stan(
        nazwa_glownego=sciezka.name,
        katalog=katalog_docelowy,
        limity=limity,
        moment=moment,
        grupa=grupa,
    )
    try:
        katalog_docelowy.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(sciezka) as archiwum:
            _przejdz_archiwum(archiwum, sciezka.name, 1, stan)
    except _PrzekroczonoLimitArchiwum as sygnal:
        shutil.rmtree(katalog_docelowy, ignore_errors=True)
        wynik.status = STATUS_POMINIETE
        wynik.komunikat = str(sygnal)
        return wynik
    except zipfile.BadZipFile:
        shutil.rmtree(katalog_docelowy, ignore_errors=True)
        wynik.status = STATUS_POMINIETE
        wynik.komunikat = (
            "Plik nie jest poprawnym archiwum ZIP: jest uszkodzony albo ma inny format niż "
            "wskazuje rozszerzenie."
        )
        return wynik
    except OSError as blad:
        shutil.rmtree(katalog_docelowy, ignore_errors=True)
        wynik.status = STATUS_POMINIETE
        wynik.komunikat = f"Nie udało się rozpakować archiwum: {blad.strerror or blad}."
        return wynik

    wynik.wpisy = stan.wpisy
    wynik.pozycje = stan.pozycje
    if not stan.pozycje:
        wynik.ostrzezenia.append(
            "Z archiwum nie przyjęto żadnego pliku, bo żaden nie miał obsługiwanego formatu."
        )
    return wynik


def _przejdz_archiwum(archiwum: zipfile.ZipFile, prefiks: str, poziom: int, stan: _Stan) -> None:
    """Przegląda wpisy jednego archiwum, dopisując wyniki do wspólnego stanu."""
    for informacja in archiwum.infolist():
        if informacja.is_dir():
            continue
        nazwa = _nazwa_wpisu(informacja)
        opis = f"{prefiks}{ROZDZIELACZ_POCHODZENIA}{nazwa}" if poziom > 1 else nazwa
        _przyjmij_wpis(archiwum, informacja, nazwa, opis, poziom, stan)


def _przyjmij_wpis(
    archiwum: zipfile.ZipFile,
    informacja: zipfile.ZipInfo,
    nazwa: str,
    opis: str,
    poziom: int,
    stan: _Stan,
) -> None:
    stan.liczba_plikow += 1
    if stan.liczba_plikow > stan.limity.maksymalna_liczba_plikow:
        raise _PrzekroczonoLimitArchiwum(
            f"Archiwum ma więcej niż {stan.limity.maksymalna_liczba_plikow} plików. Całe "
            "archiwum zostało pominięte, żeby do notatnika nie trafiła niekompletna część "
            "zbioru. Podziel archiwum na mniejsze albo podnieś limit w konfiguracji."
        )
    stan.rozmiar_deklarowany += informacja.file_size
    if stan.rozmiar_deklarowany > stan.limity.maksymalny_rozmiar_bajtow:
        raise _PrzekroczonoLimitArchiwum(
            f"Rozmiar zawartości archiwum po rozpakowaniu przekracza limit "
            f"{stan.limity.maksymalny_rozmiar_bajtow // _BAJTOW_W_MEGABAJCIE} megabajtów. "
            "Całe archiwum zostało pominięte. Podziel je na mniejsze albo podnieś limit "
            "w konfiguracji."
        )
    if informacja.file_size > 0 and (
        informacja.compress_size == 0
        or informacja.file_size / informacja.compress_size
        > stan.limity.maksymalny_stosunek_kompresji
    ):
        raise _PrzekroczonoLimitArchiwum(
            f"Wpis „{opis}” ma stosunek kompresji ponad "
            f"{stan.limity.maksymalny_stosunek_kompresji} do 1, co jest cechą bomby kompresji. "
            "Całe archiwum zostało pominięte."
        )

    powod = _powod_pominiecia(informacja, nazwa)
    format_wpisu = nazwa.rsplit(".", 1)[-1].lower() if "." in nazwa.rsplit("/", 1)[-1] else ""
    if powod is None and informacja.file_size == 0:
        powod = "Plik jest pusty."
    if (
        powod is None
        and format_wpisu == FORMAT_ARCHIWUM
        and poziom >= stan.limity.maksymalne_zaglebienie
    ):
        powod = (
            f"Archiwum zagnieżdżone głębiej niż {stan.limity.maksymalne_zaglebienie} poziomy "
            "nie jest rozwijane."
        )
    if powod is None and format_wpisu not in FORMATY_PLIKOW | {FORMAT_ARCHIWUM}:
        powod = _powod_nieobslugiwanego_formatu(format_wpisu)
    if powod is not None:
        stan.wpisy.append(
            WpisArchiwum(
                sciezka=opis,
                status=STATUS_WPISU_POMINIETY,
                format=format_wpisu,
                rozmiar_bajtow=informacja.file_size,
                komunikat=powod,
            )
        )
        return

    stan.numer_pliku += 1
    cel = stan.katalog / f"{stan.numer_pliku:04d}_{_bezpieczna_nazwa(nazwa)}"
    try:
        zapisano, suma = _zapisz_wpis(archiwum, informacja, cel, stan)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error) as blad:
        cel.unlink(missing_ok=True)
        stan.wpisy.append(
            WpisArchiwum(
                sciezka=opis,
                status=STATUS_WPISU_POMINIETY,
                format=format_wpisu,
                rozmiar_bajtow=informacja.file_size,
                komunikat=f"Wpisu nie dało się rozpakować: {blad}.",
            )
        )
        return

    if format_wpisu == FORMAT_ARCHIWUM:
        try:
            with zipfile.ZipFile(cel) as zagniezdzone:
                _przejdz_archiwum(zagniezdzone, opis, poziom + 1, stan)
        except zipfile.BadZipFile:
            stan.wpisy.append(
                WpisArchiwum(
                    sciezka=opis,
                    status=STATUS_WPISU_POMINIETY,
                    format=format_wpisu,
                    rozmiar_bajtow=zapisano,
                    komunikat="Archiwum zagnieżdżone jest uszkodzone.",
                )
            )
        finally:
            cel.unlink(missing_ok=True)
        return

    pozycja = przyjmij_plik(cel, stan.moment, grupa=stan.grupa)
    stan.pozycje.append(replace(pozycja, archiwum=stan.nazwa_glownego, sciezka_w_archiwum=opis))
    stan.wpisy.append(
        WpisArchiwum(
            sciezka=opis,
            status=STATUS_WPISU_PRZYJETY,
            format=format_wpisu,
            rozmiar_bajtow=zapisano,
            suma_kontrolna=suma,
        )
    )


def _zapisz_wpis(
    archiwum: zipfile.ZipFile, informacja: zipfile.ZipInfo, cel: Path, stan: _Stan
) -> tuple[int, str]:
    """Zapisuje wpis do pliku strumieniowo, pilnując łącznego rozmiaru faktycznie odczytanego."""
    skrot = hashlib.sha256()
    zapisano = 0
    with archiwum.open(informacja) as zrodlo, cel.open("wb") as wynik:
        while True:
            porcja = zrodlo.read(_ROZMIAR_PORCJI)
            if not porcja:
                break
            zapisano += len(porcja)
            stan.rozmiar_odczytany += len(porcja)
            if stan.rozmiar_odczytany > stan.limity.maksymalny_rozmiar_bajtow:
                raise _PrzekroczonoLimitArchiwum(
                    "Faktyczny rozmiar zawartości archiwum po rozpakowaniu przekracza limit "
                    f"{stan.limity.maksymalny_rozmiar_bajtow // _BAJTOW_W_MEGABAJCIE} megabajtów, "
                    "mimo że deklaracja w archiwum go nie przekraczała. Całe archiwum zostało "
                    "pominięte."
                )
            skrot.update(porcja)
            wynik.write(porcja)
    return zapisano, skrot.hexdigest()


def _powod_pominiecia(informacja: zipfile.ZipInfo, nazwa: str) -> str | None:
    """Zwraca powód pominięcia wpisu z przyczyn bezpieczeństwa albo zwykłych, gdy jest."""
    if "\x00" in nazwa:
        return "Nazwa wpisu zawiera znak zerowy, więc wpis został pominięty jako niebezpieczny."
    znormalizowana = nazwa.replace("\\", "/")
    if znormalizowana.startswith("/") or _WZORZEC_LITERY_DYSKU.match(znormalizowana):
        return (
            "Wpis ma ścieżkę bezwzględną albo literę dysku, więc został pominięty jako "
            "niebezpieczny."
        )
    if ".." in znormalizowana.split("/"):
        return "Wpis ma składnik „..” w ścieżce, więc został pominięty jako niebezpieczny."
    tryb = informacja.external_attr >> 16
    if tryb and stat.S_ISLNK(tryb):
        return "Wpis jest dowiązaniem symbolicznym, więc został pominięty jako niebezpieczny."
    if informacja.flag_bits & _FLAGA_SZYFROWANIA:
        return "Wpis jest zaszyfrowany hasłem. Aplikacja nie próbuje haseł."
    koncowa = znormalizowana.rsplit("/", 1)[-1].lower()
    if koncowa in _NAZWY_METADANYCH or znormalizowana.lower().startswith(_KATALOGI_METADANYCH):
        return "Plik metadanych systemu, bez treści autora."
    if not koncowa:
        return "Wpis nie ma nazwy pliku."
    return None


def _powod_nieobslugiwanego_formatu(format_wpisu: str) -> str:
    if format_wpisu in FORMATY_NUTY_GUITAR_PRO_NIEOBSLUGIWANE:
        return (
            f"Format Guitar Pro „{format_wpisu}” nie jest obsługiwany. Obsługiwane są "
            "wersje gp3, gp4 i gp5."
        )
    return f"Nieobsługiwany format pliku: „{format_wpisu or 'brak rozszerzenia'}”."


def _nazwa_wpisu(informacja: zipfile.ZipInfo) -> str:
    """Zwraca nazwę wpisu, poprawiając kodowanie starszych archiwów.

    Archiwum bez znacznika UTF-8 ma nazwy w stronie kodowej DOS, a biblioteka
    odczytuje je jako cp437, więc polskie znaki w nazwie wyglądają jak
    przypadkowe symbole. Gdy nazwa ma znaki spoza ASCII, próbowana jest strona
    kodowa cp852, używana dla polskiego systemu. To dotyczy wyłącznie opisu
    pochodzenia w manifeście, nigdy treści pliku.
    """
    nazwa = informacja.filename
    if informacja.flag_bits & _FLAGA_UTF8 or nazwa.isascii():
        return nazwa
    try:
        return nazwa.encode("cp437").decode("cp852")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return nazwa


def _bezpieczna_nazwa(nazwa: str) -> str:
    """Zamienia nazwę wpisu na bezpieczną nazwę pliku: bez katalogów i znaków specjalnych."""
    koncowa = nazwa.replace("\\", "/").rsplit("/", 1)[-1]
    oczyszczona = _WZORZEC_ZNAKOW_NIEDOZWOLONYCH.sub("_", koncowa).strip(" .")
    if not oczyszczona:
        return "plik"
    if len(oczyszczona) > _MAKSYMALNA_DLUGOSC_NAZWY:
        baza, kropka, rozszerzenie = oczyszczona.rpartition(".")
        if kropka and len(rozszerzenie) <= 10:
            return baza[: _MAKSYMALNA_DLUGOSC_NAZWY - len(rozszerzenie) - 1] + "." + rozszerzenie
        return oczyszczona[:_MAKSYMALNA_DLUGOSC_NAZWY]
    return oczyszczona
