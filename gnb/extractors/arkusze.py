"""Wspólne przekształcenia arkuszy kalkulacyjnych: wartości komórek na tekst i bloki arkusza.

Ekstraktory XLSX i XLS czytają skoroszyt innymi bibliotekami, ale zapisują go
tak samo: każdy arkusz jest nagłówkiem „Arkusz: nazwa” i jedną tabelą, a wartość
komórki jest tekstem w postaci, którą użytkownik rozpozna. Ten moduł trzyma
tę wspólną część, żeby oba formaty nie zapisywały tej samej liczby inaczej.

Zasady zapisu wartości:

1. Data jest zapisywana jako RRRR-MM-DD, a data z godziną jako RRRR-MM-DD GG:MM:SS.
   Data w arkuszu jest liczbą zależną od stylu komórki, więc odczytana bez
   uwzględnienia stylu wyglądałaby jak przypadkowa liczba, a poprawność danych
   jest w tym projekcie priorytetem pierwszym.
2. Liczba jest zapisywana z piętnastoma cyframi znaczącymi, jak w arkuszu, żeby
   0,1 dodane do 0,2 nie dało zapisu 0,30000000000000004. Liczba całkowita nie
   ma części dziesiętnej.
3. Komórka o formacie procentowym jest zapisywana jako procent, bo surowa wartość
   0,25 nie mówi czytelnikowi, że autor widział 25%.
4. Wartość logiczna to „prawda” albo „fałsz”. Błąd komórki jest zapisywany jego
   nazwą, na przykład „#DZIEL/0!”, bo to informacja, którą widział autor.

Formaty walutowe i niestandardowe formaty liczb nie są odtwarzane: komórka jest
zapisana jako liczba bez symbolu waluty. To świadome ograniczenie, opisane
w dokumentacji formatów.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Sequence

from gnb.core.model import BlokTresci
from gnb.core.stale import RodzajBloku
from gnb.extractors.blok_tabeli import blok_tabeli

_POLA_CZASU_ZERO = dt.time(0, 0)
_WZORZEC_WALUTY = re.compile(r"[$€£¥]|zł|PLN|USD|EUR|GBP|\[\$", re.IGNORECASE)


def czy_format_walutowy(format_liczby: str | None) -> bool:
    """Rozstrzyga, czy format liczby komórki zawiera symbol albo nazwę waluty.

    Formaty walutowe nie są odtwarzane: taka komórka jest zapisana jako sama
    liczba. Ta funkcja pozwala policzyć takie komórki i zgłosić je w ostrzeżeniu,
    żeby liczba bez waluty nie była odbierana jako liczba bez jednostki.
    """
    return bool(format_liczby) and _WZORZEC_WALUTY.search(format_liczby or "") is not None


def wartosc_na_tekst(wartosc: object, format_liczby: str | None = None) -> str:
    """Zamienia wartość komórki arkusza na tekst według zasad z opisu modułu."""
    if wartosc is None:
        return ""
    if isinstance(wartosc, bool):
        return "prawda" if wartosc else "fałsz"
    if isinstance(wartosc, dt.datetime):
        if wartosc.time() == _POLA_CZASU_ZERO:
            return wartosc.date().isoformat()
        return wartosc.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(wartosc, dt.date):
        return wartosc.isoformat()
    if isinstance(wartosc, dt.time):
        return wartosc.strftime("%H:%M:%S")
    if isinstance(wartosc, dt.timedelta):
        return str(wartosc)
    if isinstance(wartosc, int):
        return str(wartosc)
    if isinstance(wartosc, float):
        if format_liczby and "%" in format_liczby:
            return _liczba(wartosc * 100) + "%"
        return _liczba(wartosc)
    return str(wartosc)


def _liczba(wartosc: float) -> str:
    if wartosc != wartosc or wartosc in (float("inf"), float("-inf")):
        return str(wartosc)
    if wartosc == int(wartosc) and abs(wartosc) < 1e15:
        return str(int(wartosc))
    return f"{wartosc:.15g}"


def bloki_arkusza(
    nazwa: str, wiersze: Sequence[Sequence[str]], *, ukryty: bool = False
) -> list[BlokTresci]:
    """Zwraca nagłówek arkusza i jego tabelę albo pustą listę dla arkusza bez treści."""
    tabela = blok_tabeli(wiersze)
    if tabela is None:
        return []
    opis = f"Arkusz: {nazwa}" + (" (arkusz ukryty)" if ukryty else "")
    return [BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=2, tresc=opis), tabela]
