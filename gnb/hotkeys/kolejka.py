"""Kolejka źródeł dodanych skrótem, gdy rejestr zadań interfejsu jest zajęty.

Naciśnięcie skrótu w trakcie trwającego przetwarzania nie może zgubić źródła
ani zgłosić błędu. Źródło jest zapisywane w tej kolejce natychmiast, a
przetworzone w kolejnym przebiegu — albo od razu, gdy rejestr zadań jest wolny,
albo automatycznie po zakończeniu bieżącego zadania, zgodnie z decyzją
pierwszą etapu jedenastego.

Kolejka jest czystą strukturą danych w pamięci, bez zależności od Windows i bez
własnego zapisu do checkpointu: każda pozycja trafia do checkpointu dopiero
w chwili, gdy ``przetworz_projekt`` faktycznie ją przetworzy, tak samo jak przy
zwykłym wywołaniu z wiersza poleceń albo z interfejsu.
"""

from __future__ import annotations

import threading

from gnb.ingestion.wejscie import PozycjaWejsciowa


class KolejkaSkrotu:
    """Trzyma oczekujące pozycje wejściowe, pogrupowane po nazwie projektu.

    Jeden projekt naraz: metoda ``odbierz_jeden_projekt`` zwraca i usuwa wszystkie
    oczekujące pozycje jednego projektu, co odpowiada temu, jak działa dodawanie
    kolejnej grupy źródeł osobnym wywołaniem, opisane w sekcji piątej CLAUDE.md.
    """

    def __init__(self) -> None:
        self._zamek = threading.Lock()
        self._oczekujace: dict[str, list[PozycjaWejsciowa]] = {}

    def dodaj(self, nazwa_projektu: str, pozycja: PozycjaWejsciowa) -> None:
        """Zapisuje pozycję jako oczekującą na przetworzenie w projekcie o podanej nazwie."""
        with self._zamek:
            self._oczekujace.setdefault(nazwa_projektu, []).append(pozycja)

    def odbierz_jeden_projekt(self) -> tuple[str, list[PozycjaWejsciowa]] | None:
        """Zwraca i usuwa z kolejki wszystkie oczekujące pozycje jednego projektu.

        Zwraca ``None``, gdy kolejka jest pusta. Kolejność projektów odpowiada
        kolejności pierwszego dodania do kolejki.
        """
        with self._zamek:
            if not self._oczekujace:
                return None
            nazwa = next(iter(self._oczekujace))
            pozycje = self._oczekujace.pop(nazwa)
            return nazwa, pozycje

    def czy_pusta(self) -> bool:
        with self._zamek:
            return not self._oczekujace

    def liczba_oczekujacych(self) -> int:
        """Łączna liczba oczekujących pozycji, sumowana po wszystkich projektach."""
        with self._zamek:
            return sum(len(pozycje) for pozycje in self._oczekujace.values())

    def stan(self) -> dict[str, int]:
        """Zwraca liczbę oczekujących pozycji dla każdego projektu, bez ich usuwania.

        Służy raportowaniu przy zamknięciu serwera: ``ObslugaSkrotu.zatrzymaj``
        woła tę metodę, żeby opisać ewentualną utratę zawartości kolejki, bez
        zmiany jej stanu — samo raportowanie nie powinno konsumować pozycji.
        """
        with self._zamek:
            return {nazwa: len(pozycje) for nazwa, pozycje in self._oczekujace.items() if pozycje}
