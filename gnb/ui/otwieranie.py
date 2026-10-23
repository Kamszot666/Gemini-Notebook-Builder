"""Otwieranie pliku wynikowego w aplikacji domyślnej systemu na komputerze serwera.

Przeglądarka nie otworzy pliku lokalnego z odnośnika ``file://`` na stronie wczytanej
przez http, więc otwarcie pliku robi serwer, który działa na tym samym komputerze
co użytkownik. Moduł odpowiada wyłącznie za samo otwarcie podanej ścieżki. Nie
sprawdza, czy plik należy do projektu: to robi wywołujący, który przyjmuje od
przeglądarki wyłącznie nazwę pliku z wykazu plików wynikowych projektu, nigdy ścieżkę.

Kod zależny od systemu leży wewnątrz sprawdzenia ``sys.platform == "win32"``, tak
jak w ``gnb.hotkeys``, żeby ``mypy --platform linux`` go pomijał. Na innym systemie
(na przykład na serwerze z Linuksem, gdzie aplikacja domyślna nie ma na czyim
pulpicie się otworzyć) funkcja zwraca czytelny komunikat zamiast otwierać cokolwiek.
"""

from __future__ import annotations

import sys
from pathlib import Path

KOMUNIKAT_NIE_WINDOWS = (
    "Otwieranie pliku w aplikacji domyślnej działa tylko na Windows, na komputerze, "
    "na którym działa serwer. Użyj odnośnika do podglądu pliku jako tekstu."
)

if sys.platform == "win32":
    import os

    def otworz_plik(sciezka: Path) -> str | None:
        """Otwiera plik w aplikacji domyślnej. Zwraca komunikat błędu albo ``None``."""
        try:
            os.startfile(sciezka)
        except OSError as blad:
            return (
                f"Nie udało się otworzyć pliku {sciezka.name} w aplikacji domyślnej: "
                f"{blad.strerror or 'błąd systemu'}. Użyj odnośnika do podglądu pliku jako tekstu."
            )
        return None

else:

    def otworz_plik(sciezka: Path) -> str | None:
        """Na systemie innym niż Windows nie otwiera niczego i zwraca komunikat."""
        del sciezka
        return KOMUNIKAT_NIE_WINDOWS
