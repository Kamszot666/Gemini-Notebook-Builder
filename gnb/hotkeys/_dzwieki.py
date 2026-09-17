"""Dźwięki potwierdzenia naciśnięcia globalnego skrótu: sukces i porażka.

Moduł jest importowalny na każdym systemie; cała jego zawartość leży za
sprawdzeniem ``sys.platform == "win32"``, bo moduł standardowy ``winsound``
istnieje wyłącznie na Windows.

Wybrano ``winsound.Beep`` zamiast ``winsound.MessageBeep``, bo ten drugi gra
dźwięk z motywu systemowego, który użytkownik mógł wyciszyć niezależnie od
głośności aplikacji. Dźwięki różnią się rytmem, nie tylko wysokością: sukces
to dwa krótkie, rosnące tony, porażka to jeden niski, dłuższy ton — parametry
obu są w ``stale.py``, w jednym miejscu.

``winsound.Beep`` blokuje wątek wywołujący na czas trwania dźwięku, dlatego
funkcje z tego modułu nie mogą być wołane z wątku pętli komunikatów skrótu.
Wołający — ``obsluga.py`` — gra dźwięk w tym samym wątku roboczym, w którym
i tak wykonuje resztę obsługi naciśnięcia, nie w wątku pętli.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import winsound

    from gnb.hotkeys.stale import (
        DZWIEK_PORAZKA_CZAS_MS,
        DZWIEK_PORAZKA_TON_HZ,
        DZWIEK_SUKCES_CZAS_MS,
        DZWIEK_SUKCES_TONY_HZ,
    )

    def zagraj_sukces() -> None:
        """Gra dwa krótkie, rosnące tony potwierdzające udane dodanie źródła."""
        for ton in DZWIEK_SUKCES_TONY_HZ:
            winsound.Beep(ton, DZWIEK_SUKCES_CZAS_MS)

    def zagraj_porazke() -> None:
        """Gra jeden niski, dłuższy ton sygnalizujący, że nic nie dodano."""
        winsound.Beep(DZWIEK_PORAZKA_TON_HZ, DZWIEK_PORAZKA_CZAS_MS)
