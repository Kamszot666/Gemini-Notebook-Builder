"""Stałe globalnego skrótu klawiszowego: identyfikatory rejestracji i parametry dźwięków.

Moduł nie zależy od Windows — same liczby można odczytać i przetestować na
każdym systemie.
"""

from __future__ import annotations

# Identyfikatory skrótu przekazywane do RegisterHotKey. Kombinacja nie jest tu
# wpisana na stałe: pochodzi z konfiguracji (``gnb.core.skrot``). Są dwa
# identyfikatory, bo przy zmianie kombinacji nowa jest rejestrowana, zanim
# zostanie wyrejestrowana stara, żeby w żadnej chwili nie zostać bez skrótu,
# a dwie rejestracje w tym samym wątku muszą mieć różne identyfikatory.
IDENTYFIKATORY_SKROTU = (1, 2)

# Parametry dwóch różnych dźwięków potwierdzenia z ``_dzwieki.py``. Zgodnie
# z decyzją użytkownika dźwięki różnią się rytmem, nie tylko wysokością: sukces
# to dwa krótkie, rosnące tony, porażka to jeden niski, dłuższy ton. Wartości są
# stałymi w jednym miejscu, żeby dało się je zmienić bez szukania w kodzie.
DZWIEK_SUKCES_TONY_HZ: tuple[int, ...] = (880, 1318)
DZWIEK_SUKCES_CZAS_MS = 90
DZWIEK_PORAZKA_TON_HZ = 220
DZWIEK_PORAZKA_CZAS_MS = 260
