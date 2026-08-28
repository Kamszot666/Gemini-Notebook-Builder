"""Sanityzacja nazw projektów i plików do postaci bezpiecznej dla Windows.

Reguły pochodzą z sekcji piętnastej CLAUDE.md: odrzucenie znaków niedozwolonych
i znaków sterujących, nazw zarezerwowanych systemu Windows oraz kropek i spacji
na końcu nazwy, a także ograniczenie długości wobec granicy dwustu sześćdziesięciu
znaków całej ścieżki.

Polskie znaki diakrytyczne są zachowywane, a nie zamieniane na odpowiedniki bez
ogonków. Nazwy plików wynikowych stają się nazwami źródeł w notatniku i są
odsłuchiwane czytnikiem ekranu, więc transliteracja pogorszyłaby ich odczyt.

Funkcje w tym module nie tworzą katalogów ani nie dotykają dysku. Wyłącznie
przetwarzają napisy.
"""

from __future__ import annotations

import re

from gnb.core.wyjatki import BladTrwaly

_ZNAKI_NIEDOZWOLONE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WIELE_PODKRESLEN = re.compile(r"_{2,}")
_SLOWA = re.compile(r"\w+")

_NAZWY_ZAREZERWOWANE = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{numer}" for numer in range(1, 10)}
    | {f"LPT{numer}" for numer in range(1, 10)}
)

MAKSYMALNA_DLUGOSC_NAZWY = 100
MAKSYMALNA_LICZBA_SLOW_W_NAZWIE = 8
MAKSYMALNA_DLUGOSC_TRZONU_NAZWY_PLIKU = 60
DLUGOSC_SKROTU_W_NAZWIE_PLIKU = 8
ROZDZIELACZ_SKROTU_W_NAZWIE_PLIKU = "_"
_NAZWA_AWARYJNA_PROJEKTU = "projekt"
_NAZWA_AWARYJNA_ZRODLA = "zrodlo"


def _oczysc(nazwa: str) -> str:
    """Zamienia znaki niedozwolone na podkreślenie i przycina nazwę.

    Kolejno: znaki niedozwolone i sterujące zamieniane są na podkreślenie,
    ciągi podkreśleń skracane do jednego, usuwane są białe znaki oraz końcowe
    kropki i spacje, a długość jest ograniczana. Przycięcie długości jest
    powtórzone po obcięciu, bo obcięcie mogło odsłonić kropkę lub spację.
    """
    oczyszczona = _ZNAKI_NIEDOZWOLONE.sub("_", nazwa)
    oczyszczona = _WIELE_PODKRESLEN.sub("_", oczyszczona).strip().rstrip(". ")
    oczyszczona = oczyszczona[:MAKSYMALNA_DLUGOSC_NAZWY].strip().rstrip(". ")
    return oczyszczona


def sanityzuj_nazwe_projektu(nazwa: str) -> str:
    """Zwraca nazwę projektu w postaci bezpiecznej dla systemu plików Windows.

    Nazwa pusta po oczyszczeniu oraz nazwa zarezerwowana w systemie Windows
    kończą się błędem trwałym z czytelnym komunikatem, ponieważ takiej nazwy nie
    da się bezpiecznie naprawić automatycznie i decyzję musi podjąć użytkownik.
    """
    oczyszczona = _oczysc(nazwa)
    if not oczyszczona:
        raise BladTrwaly("Nazwa projektu jest pusta po oczyszczeniu. Podaj inną nazwę.")
    if oczyszczona.upper() in _NAZWY_ZAREZERWOWANE:
        raise BladTrwaly(
            f"Nazwa projektu „{oczyszczona}” jest zarezerwowana w systemie Windows. "
            "Podaj inną nazwę."
        )
    return oczyszczona


def wygeneruj_nazwe_projektu(podstawa: str) -> str:
    """Tworzy krótką, bezpieczną nazwę projektu na podstawie dowolnego napisu.

    Używane, gdy użytkownik nie poda nazwy projektu. Funkcja bierze początkowe
    słowa podanego napisu, łączy je podkreśleniami i przepuszcza przez
    sanityzację. Gdy nie da się wydobyć nic sensownego, zwraca nazwę awaryjną.
    """
    slowa = _SLOWA.findall(podstawa.lower())
    trzon = "_".join(slowa[:MAKSYMALNA_LICZBA_SLOW_W_NAZWIE])
    if not trzon:
        return _NAZWA_AWARYJNA_PROJEKTU
    try:
        return sanityzuj_nazwe_projektu(trzon)
    except BladTrwaly:
        return _NAZWA_AWARYJNA_PROJEKTU


def bezpieczna_nazwa_pliku(propozycja: str, *, nazwa_awaryjna: str) -> str:
    """Zwraca bezpieczną nazwę pliku wynikowego bez rozszerzenia.

    Reguły oczyszczania są takie same jak dla nazwy projektu, ale nazwa pusta
    lub zarezerwowana nie jest tu błędem. W takim wypadku zwracana jest nazwa
    awaryjna, którą zwykle jest identyfikator źródła.
    """
    oczyszczona = _oczysc(propozycja)
    if not oczyszczona or oczyszczona.upper() in _NAZWY_ZAREZERWOWANE:
        return nazwa_awaryjna
    return oczyszczona


def nazwa_pliku_wynikowego(tytul: str | None, identyfikator_zrodla: str) -> str:
    """Buduje nazwę pliku wynikowego bez rozszerzenia: trzon tytułu i skrót źródła.

    Nazwa ma postać trzonu tytułu, podkreślenia i pierwszych ośmiu znaków skrótu
    z identyfikatora źródła, na przykład ``baza_wiedzy_dla_asystenta_ai_3f2a9c1d``.
    Skrót zapewnia unikalność nazwy bez licznika kolizji i pozwala powiązać plik
    z wpisem w manifeście bez otwierania go. Nazwa jest stabilna między
    uruchomieniami, bo identyfikator źródła jest wyprowadzany deterministycznie
    z jego treści, a nie z kolejności podania źródeł.

    Gotowa nazwa nie zawiera ciągów podkreśleń ani podkreśleń na brzegach.
    Czytnik ekranu odczytuje każdy taki znak osobno, więc ich powielenie jest
    realną uciążliwością przy przeglądaniu katalogu, a nie drobiazgiem
    kosmetycznym.
    """
    trzon = bezpieczna_nazwa_pliku(
        _trzon_z_tytulu(tytul or ""),
        nazwa_awaryjna=_czlon_typu_z_identyfikatora(identyfikator_zrodla),
    )
    skrot = skrot_z_identyfikatora(identyfikator_zrodla)
    nazwa = f"{trzon}{ROZDZIELACZ_SKROTU_W_NAZWIE_PLIKU}{skrot}"
    return _WIELE_PODKRESLEN.sub("_", nazwa).strip("_")


def _trzon_z_tytulu(tytul: str) -> str:
    """Zamienia tytuł na trzon nazwy pliku: małe litery, słowa łączone podkreśleniem.

    Trzon jest przycinany do sześćdziesięciu znaków zawsze na granicy słowa, więc
    ostatnie słowo, które się nie mieści, jest pomijane w całości. Jedynym
    wyjątkiem jest tytuł, którego już pierwsze słowo przekracza tę długość —
    wtedy to słowo jest obcinane, bo inaczej trzon byłby pusty.
    """
    slowa = _SLOWA.findall(tytul.lower())
    trzon = ""
    for slowo in slowa:
        kandydat = f"{trzon}_{slowo}" if trzon else slowo
        if len(kandydat) > MAKSYMALNA_DLUGOSC_TRZONU_NAZWY_PLIKU:
            break
        trzon = kandydat
    if not trzon and slowa:
        trzon = slowa[0][:MAKSYMALNA_DLUGOSC_TRZONU_NAZWY_PLIKU]
    return _WIELE_PODKRESLEN.sub("_", trzon).strip("_")


def _czlon_typu_z_identyfikatora(identyfikator_zrodla: str) -> str:
    """Zwraca człon typu źródła z identyfikatora, używany gdy tytuł jest pusty."""
    czlon = identyfikator_zrodla.rsplit("-", 1)[0].strip()
    return czlon if czlon else _NAZWA_AWARYJNA_ZRODLA


def skrot_z_identyfikatora(identyfikator_zrodla: str) -> str:
    """Zwraca początek skrótu z identyfikatora źródła, czyli człon po ostatnim myślniku.

    Funkcja jest publiczna, ponieważ tego samego skrótu używa nazwa katalogu
    projektu budowana z adresu źródła.
    """
    czlon = identyfikator_zrodla.rsplit("-", 1)[-1].strip()
    skrot = (czlon if czlon else identyfikator_zrodla.strip())[:DLUGOSC_SKROTU_W_NAZWIE_PLIKU]
    return skrot if skrot else _NAZWA_AWARYJNA_ZRODLA
