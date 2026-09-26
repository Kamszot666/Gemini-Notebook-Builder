"""Stałe globalnego skrótu klawiszowego: kombinacja klawiszy i parametry dźwięków.

Moduł nie zależy od Windows — same liczby można odczytać i przetestować na
każdym systemie. Wartości modyfikatorów i kodu klawisza odpowiadają stałym
Win32 ``MOD_CONTROL``, ``MOD_SHIFT`` i ``VK_F12``, używanym w ``_win32.py``.
"""

from __future__ import annotations

# Domyślna kombinacja skrótu: Control plus Shift plus F12, zgodnie z sekcją
# dwunastą CLAUDE.md. Modyfikatory są sumą bitową stałych Win32 MOD_CONTROL
# (0x0002), MOD_SHIFT (0x0004) i MOD_NOREPEAT (0x4000); kod klawisza to
# VK_F12 (0x7B). MOD_NOREPEAT jest konieczny: bez niej automatyczne
# powtarzanie klawiatury przy przytrzymaniu kombinacji generuje wiele
# komunikatów WM_HOTKEY z jednego naciśnięcia, więc jedno dłuższe
# przytrzymanie dodawałoby to samo źródło wielokrotnie. Dokumentacja
# RegisterHotKey opisuje tę flagę wprost; dostępna od Windows 7, czyli na
# każdym wspieranym Windows 11.
MODYFIKATORY_SKROTU = 0x0002 | 0x0004 | 0x4000
KOD_KLAWISZA_SKROTU = 0x7B

# Identyfikator skrótu przekazywany do RegisterHotKey. Wartość dowolna, unikalna
# w obrębie procesu — ten proces rejestruje tylko jeden skrót, więc wystarczy
# jedna stała.
IDENTYFIKATOR_SKROTU = 1

# Parametry dwóch różnych dźwięków potwierdzenia z ``_dzwieki.py``. Zgodnie
# z decyzją użytkownika dźwięki różnią się rytmem, nie tylko wysokością: sukces
# to dwa krótkie, rosnące tony, porażka to jeden niski, dłuższy ton. Wartości są
# stałymi w jednym miejscu, żeby dało się je zmienić bez szukania w kodzie.
DZWIEK_SUKCES_TONY_HZ: tuple[int, ...] = (880, 1318)
DZWIEK_SUKCES_CZAS_MS = 90
DZWIEK_PORAZKA_TON_HZ = 220
DZWIEK_PORAZKA_CZAS_MS = 260

# Nazwa projektu, do którego skrót dodaje źródła, gdy użytkownik nie wybrał
# jawnie żadnego projektu. Dzięki niej kolejne strony można dodawać jedna po
# drugiej bez zaglądania do interfejsu, a po restarcie serwera skrót nie milknie.
NAZWA_DOMYSLNEGO_PROJEKTU_SKROTU = "Adresy ze skrótu"
