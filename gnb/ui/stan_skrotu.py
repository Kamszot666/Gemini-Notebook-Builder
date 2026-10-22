"""Stan globalnego skrótu widoczny w interfejsie: aktywny projekt, komunikat i szkic tekstu.

Aktywny projekt jest zapamiętywany trwale w małym pliku stanu w katalogu danych
aplikacji, obok pliku konfiguracji. Ostatni komunikat i szkic tekstu ze skrótu
żyją wyłącznie w pamięci bieżącego uruchomienia serwera, chronione tym samym
rodzajem zamka co rejestr zadań w ``gnb.ui.zadania``. Ten moduł nie zależy od
Windows — interfejs używa go niezależnie od tego, czy moduł ``gnb.hotkeys`` jest
w ogóle aktywny na danym systemie, żeby strony dało się wyrenderować
i przetestować także na Linuksie.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gnb.core.wyjatki import BladGnb
from gnb.persistence.projekt import ustal_uklad

_LOG = logging.getLogger("gnb.ui")

NAZWA_PLIKU_STANU_SKROTU = "stan_skrotu.json"
WERSJA_SCHEMATU_STANU_SKROTU = 1
_SUFIKS_TYMCZASOWY = ".tmp"

# Górna granica szkicu jednego projektu. Zaznaczenie całej długiej strony
# skrótem nie może po cichu zająć pamięci serwera bez ograniczenia.
LIMIT_ZNAKOW_SZKICU = 500_000


class AktywnyProjektSkrotu:
    """Nazwa co najwyżej jednego projektu, do którego skrót dodaje nowe źródła.

    Wybór jest jawny: użytkownik ustawia go przyciskiem na stronie projektu albo
    wyborem projektu na liście strony głównej, a nie „ostatnio otwartym
    projektem”. Powód jest opisany w sekcji dwunastej CLAUDE.md: samo zajrzenie
    na stronę innego projektu w przeglądarce nie może po cichu przenieść miejsca,
    do którego trafia materiał dodany skrótem, bo źródło w złym projekcie jest
    błędem poprawności danych, która w hierarchii priorytetów z sekcji czwartej
    stoi nad wygodą.

    Gdy podano ``plik_stanu``, wybór jest zapisywany atomowo (plik tymczasowy
    i ``os.replace``) i przywracany przy starcie serwera metodą ``przywroc``.
    Bez pliku wybór żyje tylko w pamięci, co wystarcza testom.
    """

    def __init__(self, plik_stanu: Path | None = None) -> None:
        self._zamek = threading.Lock()
        self._nazwa: str | None = None
        self._plik_stanu = plik_stanu

    def ustaw(self, nazwa: str) -> None:
        with self._zamek:
            self._nazwa = nazwa
            self._zapisz_lub_zaloguj(nazwa)

    def aktualny(self) -> str | None:
        with self._zamek:
            return self._nazwa

    def przywroc(self, katalog_wynikow: Path) -> str | None:
        """Przywraca zapamiętany projekt, o ile jego katalog nadal ma checkpoint.

        Zwraca ``None``, gdy nie ma nic do zakomunikowania: nie było zapisu albo
        projekt został przywrócony. W przeciwnym razie zwraca zdanie dla
        użytkownika i nie ustawia aktywnego projektu. Uszkodzony albo nowszy
        plik stanu nigdy nie kończy się wyjątkiem. Katalogu projektu nie
        tworzy się od nowa tylko dlatego, że był zapamiętany.
        """
        if self._plik_stanu is None or not self._plik_stanu.is_file():
            return None
        try:
            surowe = json.loads(self._plik_stanu.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return (
                "Nie udało się odczytać pliku z zapamiętanym projektem skrótu, więc nie ma "
                "aktywnego projektu. Ustaw aktywny projekt skrótu na stronie projektu."
            )
        if not isinstance(surowe, dict):
            return (
                "Plik z zapamiętanym projektem skrótu ma niepoprawną zawartość, więc nie ma "
                "aktywnego projektu. Ustaw aktywny projekt skrótu na stronie projektu."
            )
        wersja = surowe.get("wersja_schematu")
        if not isinstance(wersja, int) or wersja > WERSJA_SCHEMATU_STANU_SKROTU:
            return (
                "Plik z zapamiętanym projektem skrótu pochodzi z nowszej wersji aplikacji, "
                "więc nie ma aktywnego projektu. Ustaw aktywny projekt skrótu na stronie projektu."
            )
        nazwa = surowe.get("aktywny_projekt")
        if not isinstance(nazwa, str) or not nazwa:
            return None
        if self._projekt_istnieje(katalog_wynikow, nazwa):
            with self._zamek:
                self._nazwa = nazwa
            return None
        self._usun_plik_stanu()
        return (
            f"Zapamiętanego projektu skrótu „{nazwa}” już nie ma na dysku, więc nie ma "
            "aktywnego projektu. Ustaw nowy aktywny projekt skrótu na stronie projektu."
        )

    @staticmethod
    def _projekt_istnieje(katalog_wynikow: Path, nazwa: str) -> bool:
        try:
            katalog = ustal_uklad(katalog_wynikow, nazwa).katalog_projektu
        except BladGnb:
            return False
        return (katalog / "checkpoint.json").is_file()

    def _zapisz_lub_zaloguj(self, nazwa: str) -> None:
        """Zapisuje wybór atomowo; błąd zapisu nie cofa wyboru w pamięci."""
        if self._plik_stanu is None:
            return
        try:
            self._plik_stanu.parent.mkdir(parents=True, exist_ok=True)
            tymczasowy = self._plik_stanu.with_name(self._plik_stanu.name + _SUFIKS_TYMCZASOWY)
            tresc = json.dumps(
                {"wersja_schematu": WERSJA_SCHEMATU_STANU_SKROTU, "aktywny_projekt": nazwa},
                ensure_ascii=False,
                indent=2,
            )
            with tymczasowy.open("w", encoding="utf-8", newline="\n") as plik:
                plik.write(tresc)
                plik.flush()
                os.fsync(plik.fileno())
            os.replace(tymczasowy, self._plik_stanu)
        except OSError:
            _LOG.exception(
                "Nie udało się zapisać aktywnego projektu skrótu. Wybór działa do zamknięcia "
                "serwera, ale po restarcie trzeba ustawić go ponownie."
            )

    def _usun_plik_stanu(self) -> None:
        if self._plik_stanu is None:
            return
        try:
            self._plik_stanu.unlink(missing_ok=True)
        except OSError:
            _LOG.exception("Nie udało się usunąć pliku z zapamiętanym projektem skrótu.")


@dataclass(frozen=True, slots=True)
class KomunikatSkrotu:
    """Jeden zapisany wynik naciśnięcia globalnego skrótu, do pokazania w interfejsie."""

    tekst: str
    sukces: bool
    czas: datetime


class OstatniKomunikatSkrotu:
    """Trzyma jeden, najnowszy wynik naciśnięcia globalnego skrótu.

    Dźwięk z ``gnb.hotkeys`` jest natychmiastowym potwierdzeniem w chwili
    naciśnięcia skrótu; ten komunikat jest jego trwałym, tekstowym
    odpowiednikiem, do sprawdzenia później na stronie interfejsu — zgodnie
    z decyzją czwartą sekcji dwunastej CLAUDE.md o potwierdzeniu bez
    przenoszenia fokusu.
    """

    def __init__(self) -> None:
        self._zamek = threading.Lock()
        self._ostatni: KomunikatSkrotu | None = None

    def ustaw(self, tekst: str, *, sukces: bool) -> None:
        with self._zamek:
            self._ostatni = KomunikatSkrotu(tekst=tekst, sukces=sukces, czas=datetime.now(UTC))

    def aktualny(self) -> KomunikatSkrotu | None:
        with self._zamek:
            return self._ostatni


def dolacz_do_szkicu(obecny: str, nowy: str) -> str:
    """Dopisuje tekst na końcu szkicu tak, żeby kursor stał w nowym, pustym wierszu.

    Gdy szkic nie jest pusty i nie kończy się znakiem nowego wiersza, najpierw
    dopisuje taki znak. Po tekście zawsze dopisuje znak nowego wiersza.
    """
    if obecny and not obecny.endswith("\n"):
        obecny += "\n"
    return obecny + nowy + "\n"


@dataclass(frozen=True, slots=True)
class StanSzkicu:
    """Treść szkicu jednego projektu i numer jego wersji do wykrywania zmian."""

    tekst: str
    wersja: int


class SzkicTekstuSkrotu:
    """Szkic tekstu zaznaczonego w przeglądarce, osobny dla każdego projektu.

    Żyje wyłącznie w pamięci serwera, tak jak kolejka skrótu. Każdy kolejny
    tekst jest dopisywany na końcu, nie zastępuje poprzedniego. Numer wersji
    rośnie przy każdej zmianie, także przy wyczyszczeniu, więc strona otwarta
    w przeglądarce odpytuje serwer i dopisuje tylko to, co nowe.
    """

    def __init__(self, limit_znakow: int = LIMIT_ZNAKOW_SZKICU) -> None:
        self._zamek = threading.Lock()
        self._limit = limit_znakow
        self._teksty: dict[str, str] = {}
        self._wersje: dict[str, int] = {}

    def dopisz(self, projekt: str, tekst: str) -> bool:
        """Dopisuje tekst do szkicu projektu. Zwraca fałsz, gdy szkic przekroczyłby limit."""
        with self._zamek:
            nowa_tresc = dolacz_do_szkicu(self._teksty.get(projekt, ""), tekst)
            if len(nowa_tresc) > self._limit:
                return False
            self._teksty[projekt] = nowa_tresc
            self._wersje[projekt] = self._wersje.get(projekt, 0) + 1
            return True

    def pobierz(self, projekt: str) -> StanSzkicu:
        with self._zamek:
            return StanSzkicu(self._teksty.get(projekt, ""), self._wersje.get(projekt, 0))

    def wyczysc(self, projekt: str) -> None:
        with self._zamek:
            if self._teksty.pop(projekt, None) is not None:
                self._wersje[projekt] = self._wersje.get(projekt, 0) + 1
