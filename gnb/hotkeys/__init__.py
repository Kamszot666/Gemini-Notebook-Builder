"""Globalny skrót klawiszowy Control plus Shift plus F12. Moduł wyłącznie dla Windows.

Skrót działa tylko wtedy, gdy działa serwer interfejsu, uruchomiony poleceniem
``python -m gnb.ui.server``: rejestracja zachodzi przy starcie serwera
i kończy się przy jego zamknięciu. Nie powstaje żaden osobny proces w tle ani
autostart, zgodnie z decyzją pierwszą sekcji dwunastej CLAUDE.md.

Naciśnięcie skrótu dodaje do aktywnego projektu to, co jest otwarte w aktywnym
oknie: adres bieżącej strony w Chrome albo Firefoksie, albo zaznaczone pliki
w Eksploratorze Windows. Wynik jest zgłaszany dźwiękiem i komunikatem
tekstowym w interfejsie, bez przenoszenia fokusu i bez użycia schowka
w jakiejkolwiek roli.

Reszta pakietu ``gnb`` nie importuje niczego z tego modułu ani nie zakłada
jego obecności. Brak działania tego modułu na systemie innym niż Windows jest
normalnym stanem pracy, a nie błędem, zgodnie z sekcją szóstą i sekcją
dwunastą CLAUDE.md — na takim systemie ten pakiet po prostu niczego nie
eksportuje.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from gnb.hotkeys.obsluga import ObslugaSkrotu

    __all__ = ["ObslugaSkrotu"]
else:
    __all__: list[str] = []
