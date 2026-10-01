"""Punkt wejścia polecenia ``python -m gnb.ui.server``.

Nazwa pliku jest angielska, ponieważ jest częścią kontraktu komend z sekcji
piątej CLAUDE.md. Cała logika i wszystkie komunikaty pozostają po polsku;
właściwy serwer jest w module ``gnb.ui.serwer``.
"""

from __future__ import annotations

import io
import sys
import webbrowser
from collections.abc import Callable
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja, sciezka_pliku_konfiguracji, wczytaj_konfiguracje
from gnb.core.wyjatki import BladGnb
from gnb.ui.blokada import BlokadaInstancji, odczytaj_adres_dzialajacej_kopii
from gnb.ui.serwer import uruchom_serwer

KOD_BLAD = 1
KOD_JUZ_DZIALA = 3


def _wymus_kodowanie_utf8() -> None:
    """Przełącza wyjście na UTF-8, żeby polskie znaki w komunikatach były czytelne.

    Konsola Windows bywa stroną kodową taką jak cp1250, w której polskie znaki
    diakrytyczne wypisują się nieczytelnie. Ten sam zabieg stosuje wiersz poleceń.
    """
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if isinstance(sys.stderr, io.TextIOWrapper):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _obsluz_druga_kopie(
    konfiguracja: Konfiguracja,
    katalog_danych: Path,
    otworz_przegladarke: Callable[[str], object],
) -> int:
    """Informuje, że interfejs już działa, i otwiera go w przeglądarce.

    Nie dotyka działającej kopii: tylko czyta zapisany przez nią adres. Gdy
    adresu nie ma, na przykład bo pierwsza kopia dopiero startuje, podaje adres
    z konfiguracji.
    """
    adres = odczytaj_adres_dzialajacej_kopii(katalog_danych) or (
        f"http://{konfiguracja.adres_nasluchu}:{konfiguracja.port_nasluchu}/"
    )
    print(
        f"Interfejs Gemini Notebook Builder już działa pod adresem {adres}. "
        "Nie uruchamiam drugiej kopii. Otwieram ten adres w przeglądarce."
    )
    try:
        otworz_przegladarke(adres)
    except Exception:  # noqa: BLE001 - brak przeglądarki nie może zmienić wyniku.
        print("Nie udało się otworzyć przeglądarki. Otwórz ten adres ręcznie.")
    return KOD_JUZ_DZIALA


def main(otworz_przegladarke: Callable[[str], object] = webbrowser.open) -> int:
    """Wczytuje konfigurację, zakłada blokadę pojedynczej kopii i uruchamia serwer.

    Blokada jest zakładana przed otwarciem portu i przed rejestracją skrótu.
    """
    _wymus_kodowanie_utf8()
    try:
        konfiguracja = wczytaj_konfiguracje()
    except BladGnb as blad:
        print(f"Nie udało się wczytać konfiguracji: {blad.komunikat}")
        return KOD_BLAD

    katalog_danych = sciezka_pliku_konfiguracji().parent
    blokada = BlokadaInstancji(katalog_danych)
    try:
        zajeta = not blokada.zajmij()
    except OSError as blad:
        print(
            f"Nie udało się założyć blokady pojedynczej kopii w katalogu {katalog_danych}: "
            f"{blad}. Sprawdź uprawnienia do tego katalogu."
        )
        return KOD_BLAD
    if zajeta:
        return _obsluz_druga_kopie(konfiguracja, katalog_danych, otworz_przegladarke)

    try:
        uruchom_serwer(konfiguracja, blokada=blokada)
    except OSError as blad:
        print(
            f"Nie udało się uruchomić serwera na {konfiguracja.adres_nasluchu}:"
            f"{konfiguracja.port_nasluchu}. Port może być zajęty. Szczegóły: {blad}."
        )
        return KOD_BLAD
    finally:
        blokada.zwolnij()
    return 0


if __name__ == "__main__":
    sys.exit(main())
