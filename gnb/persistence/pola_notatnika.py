"""Trwałe przechowywanie dwóch pól tekstowych notatnika.

Pola to instrukcja systemowa notatnika oraz prompt dla zewnętrznego mechanizmu
wyszukującego źródła, opisane w sekcji jedenastej a CLAUDE.md. Są zapisywane
w pliku ``pola_notatnika.json`` w katalogu projektu, zapisem atomowym przez plik
tymczasowy i ``os.replace``, tym samym wzorcem co checkpoint.

To osobny plik, a nie pole checkpointu, ponieważ treść pól nie jest stanem
potoku i nie ma wpływu na wznowienie. Trzymanie jej w checkpoincie oznaczałoby
zapis całego stanu potoku przy każdym naciśnięciu przycisku zapisu pola.

Aplikacja nigdy nie wykonuje promptu wyszukiwania samoczynnie. Ten moduł go
wyłącznie przechowuje i udostępnia interfejsowi.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from gnb.core.wyjatki import BladTrwaly

NAZWA_PLIKU = "pola_notatnika.json"
_SUFIKS_TYMCZASOWY = ".tmp"


@dataclass(frozen=True, slots=True)
class PolaNotatnika:
    """Dwa niezależne pola tekstowe zapisywane razem z projektem.

    Pole `instrukcja_systemowa` to instrukcja systemowa dla notatnika, z limitem
    znaków pochodzącym z konfiguracji. Pole `prompt_wyszukiwania` to prompt dla
    zewnętrznego mechanizmu wyszukującego źródła, którego aplikacja nigdy nie
    uruchamia sama. Pola nie wpływają na siebie ani na przetwarzanie materiałów.
    """

    instrukcja_systemowa: str = ""
    prompt_wyszukiwania: str = ""


class PrzekroczonoLimitZnakow(BladTrwaly):
    """Instrukcja systemowa jest dłuższa niż limit znaków z konfiguracji.

    Osobny typ wyjątku pozwala interfejsowi odróżnić przekroczenie limitu, które
    powiąże z polem przez ``aria-describedby``, od innych błędów zapisu.
    """


def wczytaj(sciezka: Path) -> PolaNotatnika:
    """Wczytuje pola notatnika. Brak pliku jest poprawny i daje puste pola.

    Uszkodzony plik kończy się błędem trwałym z komunikatem po polsku, a nie
    surowym śladem stosu, tak samo jak przy checkpoincie.
    """
    if not sciezka.is_file():
        return PolaNotatnika()
    try:
        dane = json.loads(sciezka.read_text(encoding="utf-8"))
    except (OSError, ValueError) as blad:
        raise BladTrwaly(
            f"Nie udało się odczytać pliku pól notatnika {sciezka}. Przyczyna: {blad}"
        ) from blad
    if not isinstance(dane, dict):
        raise BladTrwaly(f"Zawartość pliku pól notatnika {sciezka} nie jest obiektem JSON.")
    return PolaNotatnika(
        instrukcja_systemowa=str(dane.get("instrukcja_systemowa", "")),
        prompt_wyszukiwania=str(dane.get("prompt_wyszukiwania", "")),
    )


def zapisz(sciezka: Path, pola: PolaNotatnika, *, limit_znakow_instrukcji: int) -> None:
    """Zapisuje pola notatnika atomowo, po sprawdzeniu limitu znaków instrukcji.

    Przekroczenie limitu znaków instrukcji systemowej kończy się wyjątkiem
    `PrzekroczonoLimitZnakow`, żeby interfejs pokazał czytelny błąd przy polu,
    zamiast po cichu przyciąć treść. Prompt wyszukiwania nie ma limitu.
    """
    liczba_znakow = len(pola.instrukcja_systemowa)
    if liczba_znakow > limit_znakow_instrukcji:
        raise PrzekroczonoLimitZnakow(
            f"Instrukcja systemowa ma {liczba_znakow} znaków, ponad limit "
            f"{limit_znakow_instrukcji}. Skróć treść przed zapisaniem."
        )
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = sciezka.with_name(sciezka.name + _SUFIKS_TYMCZASOWY)
    tresc = json.dumps(
        {
            "instrukcja_systemowa": pola.instrukcja_systemowa,
            "prompt_wyszukiwania": pola.prompt_wyszukiwania,
        },
        ensure_ascii=False,
        indent=2,
    )
    with tymczasowy.open("w", encoding="utf-8", newline="\n") as plik:
        plik.write(tresc)
        plik.flush()
        os.fsync(plik.fileno())
    os.replace(tymczasowy, sciezka)
