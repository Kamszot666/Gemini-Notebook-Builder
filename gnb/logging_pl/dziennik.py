"""Konfiguracja dwóch plików logów projektu.

Plik ``log_wazne.txt`` zawiera wpisy w formacie ``ZDARZENIE|Godzina:Minuta``, po
jednym na wiersz. Na początku każdego dnia oraz przy pierwszym wpisie po
uruchomieniu aplikacji dopisywany jest wiersz z datą w postaci
``--- RRRR-MM-DD (czas lokalny) ---``. Format wpisów jest zatwierdzony w sekcji
czternastej CLAUDE.md i nie wolno go zmieniać.

Ten log jest prowadzony w czasie lokalnym systemu, ponieważ czyta go użytkownik.
Wiersz daty niesie o tym jawną informację, żeby przy zestawianiu obu logów nie
było wątpliwości, w jakiej strefie zapisano godzinę. Log szczegółowy, manifest
i checkpoint pozostają w czasie UTC jako dane techniczne.

Plik ``log_szczegolowy.txt`` zawiera czas, poziom, moduł, identyfikator źródła,
komunikat oraz informację o wyjątku. Jest konfigurowany na standardowym module
``logging``, a jego znaczniki czasu są zapisywane w czasie UTC, żeby dane
techniczne były niezależne od strefy czasowej maszyny.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import TracebackType

NAZWA_LOGU_WAZNEGO = "log_wazne.txt"
NAZWA_LOGU_SZCZEGOLOWEGO = "log_szczegolowy.txt"

# Teksty zdarzeń dopisywanych do log_wazne.txt. Nie mogą zawierać znaku pionowej
# kreski, bo ten znak rozdziela zdarzenie od godziny.
ZDARZENIE_PROJEKT_UTWORZONY = "Projekt utworzony"
ZDARZENIE_PROJEKT_WZNOWIONY = "Projekt wznowiony"
ZDARZENIE_ZRODLO_PRZYJETE = "Źródło przyjęte"
ZDARZENIE_ZRODLO_POMINIETE = "Źródło pominięte"
ZDARZENIE_ZRODLO_BLAD = "Błąd źródła"
ZDARZENIE_PLIK_WYNIKOWY_ZAPISANY = "Plik wynikowy zapisany"
ZDARZENIE_MANIFEST_ZAPISANY = "Manifest zapisany"
ZDARZENIE_CHECKPOINT_ZAPISANY = "Checkpoint zapisany"
ZDARZENIE_PROJEKT_ZAKONCZONY = "Projekt zakończony"
ZDARZENIE_NAPISY_WYBRANE = "Napisy wybrane"
ZDARZENIE_NAPISY_INNY_JEZYK = "Uwaga, napisy w innym języku niż preferowane"
ZDARZENIE_JAKOSC_PODEJRZANA = "Uwaga, podejrzany wynik ekstrakcji"
ZDARZENIE_OSTRZEZENIE_EKSTRAKCJI = "Uwaga, ostrzeżenie ekstraktora"

_FORMAT_LOGU_SZCZEGOLOWEGO = (
    "%(asctime)s|%(levelname)s|%(name)s|%(identyfikator_zrodla)s|%(message)s"
)

# Oznaczenie dopisywane do wiersza daty w log_wazne.txt. Mówi wprost, że godziny
# w tym pliku są czasem lokalnym systemu, a nie czasem UTC.
OZNACZENIE_CZASU_LOKALNEGO = "czas lokalny"


def teraz_lokalny() -> datetime:
    """Zwraca bieżący moment w czasie lokalnym systemu, ze świadomością strefy."""
    return datetime.now().astimezone()


class DziennikWazny:
    """Dopisywacz wpisów do pliku ``log_wazne.txt`` w zatwierdzonym formacie.

    Wiersz z datą jest dopisywany przy pierwszym wpisie w danym cyklu życia
    obiektu oraz za każdym razem, gdy zmieni się dzień. Odpowiada to wymaganiu,
    że data pojawia się także przy pierwszym wpisie po uruchomieniu aplikacji.

    Domyślnym zegarem jest czas lokalny systemu. Podanie własnego zegara służy
    testom i nie zmienia znaczenia wiersza daty.
    """

    def __init__(self, sciezka: Path, zegar: Callable[[], datetime] = teraz_lokalny) -> None:
        self._sciezka = sciezka
        self._zegar = zegar
        self._data_ostatniego_wpisu: str | None = None
        self._przed_pierwszym_wpisem = True

    def zapisz(self, zdarzenie: str) -> None:
        """Dopisuje jeden wiersz zdarzenia, poprzedzając go w razie potrzeby wierszem daty."""
        if "|" in zdarzenie:
            raise ValueError("Tekst zdarzenia nie może zawierać znaku pionowej kreski.")
        teraz = self._zegar()
        data = teraz.strftime("%Y-%m-%d")
        godzina_minuta = teraz.strftime("%H:%M")

        self._sciezka.parent.mkdir(parents=True, exist_ok=True)
        with self._sciezka.open("a", encoding="utf-8", newline="\n") as plik:
            if self._przed_pierwszym_wpisem or data != self._data_ostatniego_wpisu:
                plik.write(f"--- {data} ({OZNACZENIE_CZASU_LOKALNEGO}) ---\n")
            plik.write(f"{zdarzenie}|{godzina_minuta}\n")

        self._przed_pierwszym_wpisem = False
        self._data_ostatniego_wpisu = data


class _FormatterUtc(logging.Formatter):
    """Formatter zapisujący znaczniki czasu w czasie UTC, a nie w czasie lokalnym.

    Domyślny formatter modułu ``logging`` używa czasu lokalnego. Log szczegółowy
    jest danymi technicznymi zestawianymi z manifestem i checkpointem, które są
    prowadzone w czasie UTC, więc musi używać tej samej podstawy czasu. Czas
    lokalny jest zarezerwowany dla pliku ``log_wazne.txt``.
    """

    converter = time.gmtime


class _FiltrIdentyfikatoraZrodla(logging.Filter):
    """Uzupełnia rekordy logów o domyślny identyfikator źródła, gdy go nie podano."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "identyfikator_zrodla"):
            record.__dict__["identyfikator_zrodla"] = "-"
        return True


class DziennikSzczegolowy:
    """Kontekstowy konfigurator pliku ``log_szczegolowy.txt``.

    Po wejściu w blok ``with`` dodaje uchwyt pliku do dedykowanego rejestratora,
    a po wyjściu go usuwa i zamyka. Dzięki temu wielokrotne uruchomienia w jednym
    procesie nie mnożą uchwytów ani nie zostawiają otwartych plików.
    """

    def __init__(self, sciezka: Path, identyfikator_projektu: str) -> None:
        self._sciezka = sciezka
        self._logger = logging.getLogger(f"gnb.projekt.{identyfikator_projektu}")
        self._uchwyt: logging.FileHandler | None = None

    def __enter__(self) -> logging.Logger:
        self._sciezka.parent.mkdir(parents=True, exist_ok=True)
        uchwyt = logging.FileHandler(self._sciezka, encoding="utf-8")
        uchwyt.setFormatter(_FormatterUtc(_FORMAT_LOGU_SZCZEGOLOWEGO))
        uchwyt.addFilter(_FiltrIdentyfikatoraZrodla())
        self._logger.addHandler(uchwyt)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._uchwyt = uchwyt
        return self._logger

    def __exit__(
        self,
        typ_wyjatku: type[BaseException] | None,
        wartosc_wyjatku: BaseException | None,
        slad: TracebackType | None,
    ) -> None:
        if self._uchwyt is not None:
            self._logger.removeHandler(self._uchwyt)
            self._uchwyt.close()
            self._uchwyt = None
