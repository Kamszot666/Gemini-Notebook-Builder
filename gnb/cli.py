"""Wiersz poleceń aplikacji Gemini Notebook Builder.

Udostępnia dwa polecenia. Polecenie ``diagnostyka`` sprawdza dostępność narzędzi
zewnętrznych wymienionych w sekcji piątej CLAUDE.md. Polecenie ``przetworz``
uruchamia potok przetwarzania z etapu pierwszego dla tekstu wklejonego oraz
plików TXT i MD.

Wyjście jest czytelne liniowo dla czytnika ekranu, bez pasków postępu i bez
znaków sterujących przerysowujących wiersz.
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gnb.core.konfiguracja import wczytaj_konfiguracje
from gnb.core.wyjatki import BladGnb
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik, przyjmij_tekst
from gnb.potok import przetworz_projekt


@dataclass(frozen=True, slots=True)
class Narzedzie:
    """Opis jednego narzędzia zewnętrznego sprawdzanego przez diagnostykę.

    Pole `polecenia` przyjmuje więcej niż jedną nazwę pliku wykonywalnego,
    bo na przykład MuseScore na Windows nie nazywa się `mscore`, tylko
    `MuseScore4.exe` albo `MuseScore3.exe`, zgodnie z pułapką opisaną
    w sekcji piętnastej CLAUDE.md.
    """

    nazwa: str
    polecenia: tuple[str, ...]
    argument_wersji: str
    do_czego_sluzy: str
    co_przestanie_dzialac: str


NARZEDZIA: tuple[Narzedzie, ...] = (
    Narzedzie(
        nazwa="FFmpeg",
        polecenia=("ffmpeg",),
        argument_wersji="-version",
        do_czego_sluzy="konwersja i przygotowanie plików audio",
        co_przestanie_dzialac="przetwarzanie nagrań mowy",
    ),
    Narzedzie(
        nazwa="Tesseract",
        polecenia=("tesseract",),
        argument_wersji="--version",
        do_czego_sluzy="rozpoznawanie tekstu na skanach i obrazach",
        co_przestanie_dzialac="OCR obrazów i skanowanych plików PDF",
    ),
    Narzedzie(
        nazwa="LibreOffice",
        polecenia=("soffice",),
        argument_wersji="--version",
        do_czego_sluzy="konwersja plików ODT oraz część obsługi PPTX",
        co_przestanie_dzialac="import plików w formacie ODT",
    ),
    Narzedzie(
        nazwa="MuseScore",
        polecenia=("mscore", "MuseScore4.exe", "MuseScore3.exe"),
        argument_wersji="--version",
        do_czego_sluzy="konwersja plików MIDI i MusicXML na PDF oraz odczyt tonacji i metrum",
        co_przestanie_dzialac="konwersja materiałów nutowych przez wiersz poleceń",
    ),
    Narzedzie(
        nazwa="Java",
        polecenia=("java",),
        argument_wersji="-version",
        do_czego_sluzy="uruchamianie Audiveris, czyli rozpoznawania nut ze skanów i zdjęć",
        co_przestanie_dzialac="rozpoznawanie notacji muzycznej z obrazów i plików PDF",
    ),
)


def _znajdz_wersje(sciezka_programu: str, argument: str) -> str | None:
    """Zwraca pierwszy wiersz wyjścia polecenia sprawdzającego wersję, jeżeli się uda.

    Przyjmuje pełną ścieżkę znalezioną wcześniej przez `shutil.which`, a nie
    samą nazwę polecenia. Windows potrafi mieć w tym samym katalogu zarówno
    wariant konsolowy, jak i graficzny tego samego programu — tak jest
    w przypadku LibreOffice, gdzie `soffice.com` zwraca się natychmiast,
    a `soffice.exe` otwiera okno i blokuje proces aż do przekroczenia
    limitu czasu. Podanie gołej nazwy `soffice` bez rozszerzenia pozostawia
    Windows wybór, który z nich uruchomić, i bywa to wybór graficzny, dlatego
    używana jest tu dokładnie ta ścieżka, którą wcześniej znalazł
    `shutil.which`.

    Niektóre narzędzia, na przykład Java, wypisują wersję na standardowe
    wyjście błędu zamiast na standardowe wyjście, dlatego sprawdzane jest
    jedno i drugie.
    """

    try:
        wynik = subprocess.run(
            [sciezka_programu, argument],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    tekst = (wynik.stdout or wynik.stderr).strip()
    if not tekst:
        return None
    return tekst.splitlines()[0]


def _sprawdz_narzedzie(narzedzie: Narzedzie) -> str:
    """Buduje jeden czytelny wiersz raportu diagnostyki dla podanego narzędzia."""

    for polecenie in narzedzie.polecenia:
        sciezka = shutil.which(polecenie)
        if sciezka is not None:
            wersja = _znajdz_wersje(sciezka, narzedzie.argument_wersji)
            opis_wersji = wersja if wersja is not None else "nieznana"
            return (
                f"{narzedzie.nazwa}: JEST ({polecenie}). Wersja: {opis_wersji}. Ścieżka: {sciezka}."
            )

    return (
        f"{narzedzie.nazwa}: BRAK. Służy do: {narzedzie.do_czego_sluzy}. "
        f"Bez niego przestanie działać: {narzedzie.co_przestanie_dzialac}."
    )


def uruchom_diagnostyke() -> int:
    """Wypisuje czytelny tekstowo raport dostępności narzędzi zewnętrznych.

    Zwraca zawsze kod zero, ponieważ brak opcjonalnego narzędzia zewnętrznego
    nie jest błędem aplikacji, zgodnie z sekcją piątą CLAUDE.md.
    """

    print("Raport diagnostyczny narzędzi zewnętrznych Gemini Notebook Builder.")
    print("")
    for narzedzie in NARZEDZIA:
        print(_sprawdz_narzedzie(narzedzie))
    print("")
    print("Koniec raportu. Brak narzędzia opcjonalnego nie zatrzymuje działania aplikacji.")
    return 0


def uruchom_przetwarzanie(
    nazwa_projektu: str | None,
    pliki: list[str],
    teksty_plaskie: list[str],
    teksty_markdown: list[str],
    katalog_projektu: str | None,
) -> int:
    """Buduje pozycje wejściowe, uruchamia potok i wypisuje raport dla użytkownika.

    Zwraca kod zero, gdy potok się wykona, oraz kod dwa, gdy nie podano żadnego
    źródła. Pojedyncze błędne źródło nie zmienia kodu wyjścia — jest opisane
    w raporcie, w manifeście i w logu.
    """
    moment = datetime.now(UTC)
    pozycje: list[PozycjaWejsciowa] = []
    for sciezka in pliki:
        pozycje.append(przyjmij_plik(Path(sciezka), moment))
    for tresc in teksty_plaskie:
        pozycje.append(przyjmij_tekst(tresc, moment, format_tekstu="txt"))
    for tresc in teksty_markdown:
        pozycje.append(przyjmij_tekst(tresc, moment, format_tekstu="md"))

    if not pozycje:
        print("Nie podano żadnego źródła. Użyj opcji --plik, --tekst albo --tekst-md.")
        return 2

    try:
        konfiguracja = wczytaj_konfiguracje()
        wynik = przetworz_projekt(
            pozycje,
            konfiguracja,
            nazwa_projektu=nazwa_projektu,
            wlasny_katalog_projektu=Path(katalog_projektu) if katalog_projektu else None,
        )
    except BladGnb as blad:
        print(f"Przetwarzanie przerwane błędem: {blad.komunikat}")
        return 1

    print(f"Projekt: {wynik.nazwa_projektu}")
    print(f"Katalog projektu: {wynik.katalog_projektu}")
    print(f"Wznowiono istniejący projekt: {'tak' if wynik.wznowiono else 'nie'}")
    print(f"Źródła przetworzone: {wynik.liczba_przetworzonych}")
    print(f"Źródła pominięte: {wynik.liczba_pominietych}")
    print(f"Źródła z błędem: {wynik.liczba_bledow}")
    print(f"Manifest: {wynik.sciezka_manifestu}")
    print(f"Raport końcowy: {wynik.sciezka_raportu}")
    print("")
    print(
        f"Przetworzono {wynik.liczba_przetworzonych} źródeł, "
        f"pominięto {wynik.liczba_pominietych + wynik.liczba_bledow}. "
        f"Wyniki są w katalogu: {wynik.katalog_projektu}."
    )
    return 0


def _wymus_kodowanie_utf8() -> None:
    """Ustawia standardowe wyjście i wyjście błędów na UTF-8.

    Domyślne kodowanie konsoli Windows bywa stroną kodową taką jak cp1250,
    w której polskie znaki diakrytyczne wypisują się jako nieczytelne znaki
    zapytania albo inne krzaki. Ponieważ raport diagnostyki musi być
    czytelny dla czytnika ekranu, wyjście jest jawnie przełączane na UTF-8
    niezależnie od strony kodowej odziedziczonej z systemu.
    """

    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main(argumenty: list[str] | None = None) -> int:
    """Punkt wejścia wiersza poleceń aplikacji."""

    _wymus_kodowanie_utf8()

    parser = argparse.ArgumentParser(
        prog="gnb", description="Gemini Notebook Builder — wiersz poleceń."
    )
    podpolecenia = parser.add_subparsers(dest="polecenie", required=True)
    podpolecenia.add_parser("diagnostyka", help="Sprawdź dostępność narzędzi zewnętrznych.")

    parser_przetworz = podpolecenia.add_parser(
        "przetworz",
        help="Przetwórz tekst wklejony oraz pliki TXT i MD w ramach jednego projektu.",
    )
    parser_przetworz.add_argument(
        "--projekt", metavar="NAZWA", default=None, help="Nazwa projektu. Domyślnie generowana."
    )
    parser_przetworz.add_argument(
        "--plik",
        action="append",
        default=[],
        metavar="SCIEZKA",
        help="Ścieżka pliku TXT lub MD. Opcję można podać wielokrotnie.",
    )
    parser_przetworz.add_argument(
        "--tekst",
        action="append",
        default=[],
        metavar="TRESC",
        help="Tekst wklejony traktowany jako tekst płaski. Opcję można podać wielokrotnie.",
    )
    parser_przetworz.add_argument(
        "--tekst-md",
        action="append",
        default=[],
        metavar="TRESC",
        dest="tekst_md",
        help="Tekst wklejony traktowany jako Markdown. Opcję można podać wielokrotnie.",
    )
    parser_przetworz.add_argument(
        "--katalog",
        metavar="SCIEZKA",
        default=None,
        help="Własny katalog projektu. Domyślnie katalog wyników z konfiguracji.",
    )

    ustalone = parser.parse_args(argumenty)

    if ustalone.polecenie == "diagnostyka":
        return uruchom_diagnostyke()

    if ustalone.polecenie == "przetworz":
        return uruchom_przetwarzanie(
            ustalone.projekt,
            list(ustalone.plik),
            list(ustalone.tekst),
            list(ustalone.tekst_md),
            ustalone.katalog,
        )

    parser.error(f"Nieznane polecenie: {ustalone.polecenie}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
