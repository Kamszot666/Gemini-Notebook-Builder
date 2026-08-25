"""Wiersz poleceń aplikacji Gemini Notebook Builder.

Obecnie udostępnia wyłącznie polecenie `diagnostyka`, sprawdzające
dostępność narzędzi zewnętrznych wymienionych w sekcji piątej CLAUDE.md.
Ten moduł nie zawiera logiki przetwarzania materiałów źródłowych.
"""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
from dataclasses import dataclass


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

    ustalone = parser.parse_args(argumenty)

    if ustalone.polecenie == "diagnostyka":
        return uruchom_diagnostyke()

    parser.error(f"Nieznane polecenie: {ustalone.polecenie}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
