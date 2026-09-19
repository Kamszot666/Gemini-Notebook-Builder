"""Test end-to-end: kontrola limitu źródeł a grupowanie tematyczne.

Zgłoszona usterka, znaleziona na prawdziwym przebiegu projektu
``bas-nauczyciel`` 2026-09-19: `_liczba_aktywnych` w `gnb/potok.py` liczyła do
limitu każde źródło osobno, ignorując grupowanie opcją `--grupa`. Przy grupie
łączącej wiele źródeł w jeden plik wynikowy prowadziło to do cichego
odrzucania kolejnych, prawidłowych źródeł tej samej grupy, mimo że w notatniku
zostawało mnóstwo wolnych slotów — bo slot zajmuje plik, a nie źródło. Ten
test sprawdza skutek widoczny z zewnątrz, nie liczbę pośrednią: żadne źródło
grupy nie dostaje statusu „pominiete” z powodu limitu, a wszystkie trafiają
do jednego wspólnego pliku wynikowego.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_tekst
from gnb.potok import przetworz_projekt

_MOMENT = datetime(2026, 9, 19, 9, 0, tzinfo=UTC)
_GRUPA = "Materiały do limitu grupowania"
_LICZBA_ZRODEL = 6
_LIMIT_ZRODEL = 3


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": _MOMENT}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _pozycje() -> list[PozycjaWejsciowa]:
    return [
        przyjmij_tekst(
            f"Notatka numer {numer} tej samej grupy tematycznej, z własną treścią.",
            _MOMENT,
            grupa=_GRUPA,
        )
        for numer in range(1, _LICZBA_ZRODEL + 1)
    ]


def _konfiguracja(tmp_path: Path) -> Konfiguracja:
    return Konfiguracja(
        katalog_wynikow=tmp_path,
        deduplikacja_hash_wlaczona=False,
        deduplikacja_kosmetyczna_wlaczona=False,
        deduplikacja_podobienstwo_wlaczone=False,
        # Limit mniejszy niż liczba źródeł, ale większy niż liczba plików,
        # jakie grupa naprawdę wyprodukuje (jeden). Przed poprawką kontrola
        # w trakcie przyjmowania wejścia liczyła źródła, nie pliki, więc
        # źródła powyżej trzeciego dostawałyby status „pominiete” mimo
        # wolnych slotów.
        limit_zrodel=_LIMIT_ZRODEL,
    )


def test_grupa_wiekszej_liczby_zrodel_niz_limit_nie_traci_zadnego_zrodla(
    tmp_path: Path,
) -> None:
    """Sześć źródeł jednej grupy przy limicie trzech nie może stracić żadnego z nich.

    Grupa daje jeden plik wynikowy, więc zajmuje jeden slot niezależnie od
    liczby członków — sekcja 18e punkt czwarty CLAUDE.md, akapit o kierunku
    odwrotnym do podziału źródła zbyt dużego.
    """
    wynik = przetworz_projekt(
        _pozycje(),
        _konfiguracja(tmp_path),
        nazwa_projektu="Limit a grupowanie",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_bledow == 0
    assert wynik.liczba_pominietych == 0
    assert wynik.liczba_przetworzonych == _LICZBA_ZRODEL

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    statusy = [zrodlo["status"] for zrodlo in manifest["zrodla"]]
    assert statusy.count("spakowane") == _LICZBA_ZRODEL
    assert statusy.count("pominiete") == 0

    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 1, "sześć małych źródeł jednej grupy ma dać jeden plik, nie sześć"

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba źródeł pominiętych: 0" in raport
    assert "Liczba plików TXT: 1" in raport
