"""Punkt wejścia polecenia ``python -m gnb.ui.server``.

Nazwa pliku jest angielska, ponieważ jest częścią kontraktu komend z sekcji
piątej CLAUDE.md. Cała logika i wszystkie komunikaty pozostają po polsku;
właściwy serwer jest w module ``gnb.ui.serwer``.
"""

from __future__ import annotations

import io
import sys

from gnb.core.konfiguracja import wczytaj_konfiguracje
from gnb.core.wyjatki import BladGnb
from gnb.ui.serwer import uruchom_serwer

KOD_BLAD = 1


def _wymus_kodowanie_utf8() -> None:
    """Przełącza wyjście na UTF-8, żeby polskie znaki w komunikatach były czytelne.

    Konsola Windows bywa stroną kodową taką jak cp1250, w której polskie znaki
    diakrytyczne wypisują się nieczytelnie. Ten sam zabieg stosuje wiersz poleceń.
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    """Wczytuje konfigurację i uruchamia serwer interfejsu."""
    _wymus_kodowanie_utf8()
    try:
        konfiguracja = wczytaj_konfiguracje()
    except BladGnb as blad:
        print(f"Nie udało się wczytać konfiguracji: {blad.komunikat}")
        return KOD_BLAD

    try:
        uruchom_serwer(konfiguracja)
    except OSError as blad:
        print(
            f"Nie udało się uruchomić serwera na {konfiguracja.adres_nasluchu}:"
            f"{konfiguracja.port_nasluchu}. Port może być zajęty. Szczegóły: {blad}."
        )
        return KOD_BLAD
    return 0


if __name__ == "__main__":
    sys.exit(main())
