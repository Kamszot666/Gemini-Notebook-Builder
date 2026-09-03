"""Udostępnia katalog testów obrazów na ścieżce importu.

Tryb importu „importlib” nie dokłada katalogów testów do ścieżki modułów, więc
wspólny moduł pomocniczy `pomoce` nie byłby widoczny dla sąsiednich plików
testowych bez tego dopisania.
"""

from __future__ import annotations

import sys
from pathlib import Path

_KATALOG = str(Path(__file__).resolve().parent)
if _KATALOG not in sys.path:
    sys.path.insert(0, _KATALOG)
