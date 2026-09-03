"""Rozpoznawanie tekstu z obrazów przez program Tesseract.

Silnikiem OCR jest wyłącznie Tesseract, wołany przez podproces z pełną ścieżką
pliku wykonywalnego, a nie przez bibliotekę pośredniczącą. Powód jest ten sam co
w module diagnostyki: zero nowych zależności i pełna kontrola nad przełącznikami
``-l``, ``--psm`` oraz ``--tessdata-dir``. Decyzja pierwsza i druga etapu ósmego.

Obraz jest przekazywany do Tesseracta przez standardowe wejście w formacie PNG,
a rozpoznany tekst wraca standardowym wyjściem w kodowaniu UTF-8. Dzięki temu
nie powstają pliki tymczasowe, których trzeba by pilnować przy przerwaniu pracy.

Brak Tesseracta nie wywraca aplikacji: kończy się wyjątkiem `BrakNarzedzia`
z czytelnym komunikatem, a potok zamienia go na kontrolowane pominięcie źródła.

Operacja OCR jest kosztowna obliczeniowo, więc `rozpoznaj_wiele` uruchamia
kolejne wywołania Tesseracta równolegle. Każde wywołanie to osobny proces
systemowy Tesseracta, zgodnie z wymaganiem sekcji piętnastej CLAUDE.md, żeby
operacje kosztowne wykonywać w osobnych procesach. Pula jest wątkowa jedynie po
to, żeby te procesy wystartować i zebrać ich wyniki, a nie żeby liczyć w wątkach.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly, BrakNarzedzia

NAZWA_PLIKU_WYKONYWALNEGO = "tesseract"

# Znane miejsca instalacji Tesseracta na Windows. Instalator z projektu UB Mannheim
# nie zawsze dopisuje program do zmiennej PATH, a wtedy `shutil.which` go nie
# znajdzie, mimo że narzędzie jest zainstalowane i sprawne.
_ZNANE_PODKATALOGI_WINDOWS = (
    ("PROGRAMFILES", "Tesseract-OCR"),
    ("PROGRAMFILES(X86)", "Tesseract-OCR"),
    ("LOCALAPPDATA", "Programs/Tesseract-OCR"),
)
_DOMYSLNE_SCIEZKI_WINDOWS = (
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
)

# Górny limit czasu jednego wywołania Tesseracta. Rozpoznanie jednej strony
# skanu w rozsądnej rozdzielczości mieści się w kilkunastu sekundach; wartość
# jest wielokrotnie wyższa, żeby nie ucinać pracy na wolniejszym sprzęcie, ale
# skończona, żeby zawieszony proces nie zatrzymał całego potoku.
LIMIT_CZASU_WYWOLANIA_SEKUNDY = 180

# Domyślna liczba równoległych procesów OCR, gdy konfiguracja podaje zero, czyli
# „dobierz sam”. Trzymana nisko, bo każdy proces Tesseracta sam wykorzystuje
# kilka rdzeni, a nadmiar procesów tylko odbiera pamięć.
_DOMYSLNA_LICZBA_PROCESOW = 4

KOMUNIKAT_BRAK_TESSERACTA = (
    "Nie znaleziono programu Tesseract, który rozpoznaje tekst na obrazach i "
    "skanach. Zainstaluj Tesseract i dopisz go do zmiennej PATH albo wskaż "
    "ścieżkę pliku wykonywalnego w ustawieniu „sciezka_tesseract”. Bez niego "
    "obrazy i skanowane pliki PDF nie zostaną rozpoznane."
)


@dataclass(frozen=True, slots=True)
class UstawieniaOcr:
    """Zestaw ustawień jednego przebiegu OCR, wyprowadzony z konfiguracji projektu."""

    jezyk: str = "pol"
    tryb_segmentacji: int = 3
    rozdzielczosc_pdf_dpi: int = 300
    sciezka_tesseract: str = ""
    sciezka_tessdata: str = ""
    liczba_procesow: int = 0

    @classmethod
    def z_konfiguracji(cls, konfiguracja: Konfiguracja) -> UstawieniaOcr:
        """Buduje ustawienia OCR z pól konfiguracji aplikacji."""
        return cls(
            jezyk=konfiguracja.ocr_jezyk,
            tryb_segmentacji=konfiguracja.ocr_psm,
            rozdzielczosc_pdf_dpi=konfiguracja.ocr_rozdzielczosc_pdf_dpi,
            sciezka_tesseract=konfiguracja.sciezka_tesseract,
            sciezka_tessdata=konfiguracja.sciezka_tessdata,
            liczba_procesow=konfiguracja.ocr_liczba_procesow,
        )

    @property
    def efektywna_liczba_procesow(self) -> int:
        """Zwraca liczbę równoległych procesów OCR, zamieniając zero na wartość dobraną."""
        if self.liczba_procesow > 0:
            return self.liczba_procesow
        rdzenie = os.cpu_count() or 1
        return max(1, min(_DOMYSLNA_LICZBA_PROCESOW, rdzenie))


def znajdz_tesseract(sciezka_wskazana: str = "") -> Path:
    """Zwraca ścieżkę pliku wykonywalnego Tesseracta albo zgłasza `BrakNarzedzia`.

    Kolejność szukania: ścieżka wskazana wprost w konfiguracji, następnie zmienna
    PATH, na końcu znane miejsca instalacji na Windows. Ta sama kolejność co
    w module diagnostyki, uzupełniona o znane katalogi, bo instalator Tesseracta
    często nie dopisuje się do zmiennej PATH.
    """
    if sciezka_wskazana:
        kandydat = Path(sciezka_wskazana)
        if kandydat.is_file():
            return kandydat
        raise BrakNarzedzia(
            f"Ustawienie „sciezka_tesseract” wskazuje plik, którego nie ma: {sciezka_wskazana}."
        )

    znaleziony = shutil.which(NAZWA_PLIKU_WYKONYWALNEGO)
    if znaleziony is not None:
        return Path(znaleziony)

    for zmienna, podkatalog in _ZNANE_PODKATALOGI_WINDOWS:
        baza = os.environ.get(zmienna)
        if not baza:
            continue
        kandydat = Path(baza) / podkatalog / "tesseract.exe"
        if kandydat.is_file():
            return kandydat
    for kandydat in _DOMYSLNE_SCIEZKI_WINDOWS:
        if kandydat.is_file():
            return kandydat

    raise BrakNarzedzia(KOMUNIKAT_BRAK_TESSERACTA)


def czy_dostepny(sciezka_wskazana: str = "") -> bool:
    """Zwraca prawdę, gdy Tesseract da się odnaleźć, i nie zgłasza wyjątku."""
    try:
        znajdz_tesseract(sciezka_wskazana)
    except BrakNarzedzia:
        return False
    return True


def dostepne_jezyki(sciezka_wskazana: str = "") -> tuple[str, ...]:
    """Zwraca posortowaną listę zainstalowanych danych językowych Tesseracta.

    Pusta lista oznacza, że Tesseract nie zwrócił żadnego języka albo że nie dało
    się go uruchomić. Instalator Tesseracta domyślnie dokłada tylko angielski,
    więc bez pliku ``pol.traineddata`` OCR polskiego tekstu daje wynik
    systematycznie błędny — ta funkcja pozwala to sprawdzić w diagnostyce.
    """
    try:
        program = znajdz_tesseract(sciezka_wskazana)
    except BrakNarzedzia:
        return ()
    try:
        wynik = subprocess.run(
            [str(program), "--list-langs"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    wiersze = (wynik.stdout or wynik.stderr).splitlines()
    jezyki = [wiersz.strip() for wiersz in wiersze[1:] if wiersz.strip()]
    return tuple(sorted(jezyki))


def rozpoznaj_tekst(
    obraz_png: bytes,
    ustawienia: UstawieniaOcr,
    *,
    identyfikator_zrodla: str | None = None,
) -> str:
    """Rozpoznaje tekst z jednego obrazu PNG i zwraca go jako czysty tekst.

    Obraz jest przekazywany przez standardowe wejście, a wynik odbierany ze
    standardowego wyjścia. Ostrzeżenia Tesseracta na standardowym wyjściu błędu
    przy udanym rozpoznaniu, na przykład o braku informacji o rozdzielczości, są
    pomijane. Niezerowy kod wyjścia kończy się błędem trwałym z komunikatem
    Tesseracta, a przekroczenie limitu czasu błędem przejściowym.
    """
    program = znajdz_tesseract(ustawienia.sciezka_tesseract)
    polecenie = [
        str(program),
        "stdin",
        "stdout",
        "-l",
        ustawienia.jezyk,
        "--psm",
        str(ustawienia.tryb_segmentacji),
    ]
    if ustawienia.sciezka_tessdata:
        polecenie.extend(["--tessdata-dir", ustawienia.sciezka_tessdata])

    try:
        wynik = subprocess.run(
            polecenie,
            input=obraz_png,
            capture_output=True,
            timeout=LIMIT_CZASU_WYWOLANIA_SEKUNDY,
            check=False,
        )
    except FileNotFoundError as blad:
        raise BrakNarzedzia(KOMUNIKAT_BRAK_TESSERACTA, identyfikator_zrodla) from blad
    except subprocess.TimeoutExpired as blad:
        raise BladPrzejsciowy(
            "Rozpoznawanie tekstu przez Tesseract przekroczyło limit czasu "
            f"{LIMIT_CZASU_WYWOLANIA_SEKUNDY} sekund.",
            identyfikator_zrodla,
        ) from blad

    if wynik.returncode != 0:
        powod = wynik.stderr.decode("utf-8", errors="replace").strip() or "brak szczegółów"
        raise BladTrwaly(
            f"Tesseract zakończył pracę błędem (kod {wynik.returncode}): {powod}.",
            identyfikator_zrodla,
        )
    tekst = wynik.stdout.decode("utf-8", errors="replace")
    return tekst.replace("\r\n", "\n").replace("\r", "\n")


def rozpoznaj_wiele(
    obrazy_png: Sequence[bytes],
    ustawienia: UstawieniaOcr,
    *,
    przy_postepie: Callable[[int, int], None] | None = None,
    identyfikator_zrodla: str | None = None,
) -> list[str]:
    """Rozpoznaje tekst z wielu obrazów, uruchamiając procesy Tesseracta równolegle.

    Wynik zachowuje kolejność wejścia, więc strona pierwsza skanu pozostaje
    pierwsza także wtedy, gdy jej OCR skończył się po OCR strony trzeciej.
    Argument `przy_postepie` jest wołany po każdym gotowym obrazie z parą liczb:
    ile obrazów już gotowych i ile wszystkich. Służy raportowaniu postępu długiej
    operacji, żeby użytkownik nie został przy niemym oknie.
    """
    wszystkich = len(obrazy_png)
    if wszystkich == 0:
        return []

    # Odnalezienie narzędzia raz, przed pulą, żeby jego brak zgłosił się jako
    # jeden czytelny wyjątek, a nie jako wiązka błędów z wątków roboczych.
    znajdz_tesseract(ustawienia.sciezka_tesseract)

    wyniki: list[str] = [""] * wszystkich
    gotowych = 0
    liczba_procesow = min(ustawienia.efektywna_liczba_procesow, wszystkich)
    with ThreadPoolExecutor(max_workers=liczba_procesow) as pula:
        przypisane: dict[Future[str], int] = {
            pula.submit(
                rozpoznaj_tekst,
                obraz,
                ustawienia,
                identyfikator_zrodla=identyfikator_zrodla,
            ): numer
            for numer, obraz in enumerate(obrazy_png)
        }
        for zadanie in as_completed(przypisane):
            numer = przypisane[zadanie]
            wyniki[numer] = zadanie.result()
            gotowych += 1
            if przy_postepie is not None:
                przy_postepie(gotowych, wszystkich)
    return wyniki
