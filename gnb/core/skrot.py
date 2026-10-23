"""Kombinacja globalnego skrótu klawiszowego: postać tekstowa, reguły i kody Win32.

Moduł odpowiada za jedno: zamienić napis w rodzaju ``Control+Shift+F12`` na
sprawdzoną kombinację i z powrotem oraz podać liczby, których oczekuje Win32
``RegisterHotKey``. Te same reguły obowiązują przy zapisie z formularza
ustawień, przy wczytywaniu pliku konfiguracji i przy zmiennej środowiskowej.

Moduł nie zależy od Windows i niczego nie rejestruje. Leży w ``gnb.core``, a nie
w ``gnb.hotkeys``, bo konfiguracja musi sprawdzać kombinację także na systemie,
na którym pakiet ``gnb.hotkeys`` nic nie eksportuje.
"""

from __future__ import annotations

import string
from dataclasses import dataclass

from gnb.core.wyjatki import BladTrwaly

# Flagi modyfikatorów Win32 z dokumentacji RegisterHotKey. MOD_NOREPEAT jest
# konieczny: bez niego automatyczne powtarzanie klawiatury przy przytrzymaniu
# kombinacji generuje wiele komunikatów WM_HOTKEY z jednego naciśnięcia, więc
# jedno dłuższe przytrzymanie dodawałoby to samo źródło wielokrotnie.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Kody klawiszy wirtualnych Win32. F1 to 0x70, dalej kolejno do F24 (0x87).
# Litery mają kody ASCII wielkich liter, cyfry kody ASCII cyfr.
_VK_F1 = 0x70
_LICZBA_KLAWISZY_FUNKCYJNYCH = 24

NAZWA_CONTROL = "Control"
NAZWA_ALT = "Alt"
NAZWA_SHIFT = "Shift"
NAZWA_WINDOWS = "Windows"

DOMYSLNA_KOMBINACJA_SKROTU = "Control+Shift+F12"

# Klawisze do wyboru na liście „Klawisz”. Bez Caps Lock, Insert i Num Lock:
# to modyfikatory NVDA i klawisze stanu. Kombinacja z Caps Lock wymagałaby
# haka niskopoziomowego odłożonego w sekcji dwunastej CLAUDE.md.
KLAWISZE_FUNKCYJNE: tuple[str, ...] = tuple(
    f"F{numer}" for numer in range(1, _LICZBA_KLAWISZY_FUNKCYJNYCH + 1)
)
KLAWISZE_LITEROWE: tuple[str, ...] = tuple(string.ascii_uppercase)
KLAWISZE_CYFROWE: tuple[str, ...] = tuple(string.digits)
KLAWISZE_SKROTU: tuple[str, ...] = KLAWISZE_FUNKCYJNE + KLAWISZE_LITEROWE + KLAWISZE_CYFROWE

# Zapisy modyfikatorów przyjmowane przy wczytywaniu, bez względu na wielkość liter.
_NAZWY_MODYFIKATOROW = {
    "control": NAZWA_CONTROL,
    "ctrl": NAZWA_CONTROL,
    "alt": NAZWA_ALT,
    "shift": NAZWA_SHIFT,
    "windows": NAZWA_WINDOWS,
    "win": NAZWA_WINDOWS,
}


@dataclass(frozen=True, slots=True)
class KombinacjaSkrotu:
    """Sprawdzona kombinacja: cztery modyfikatory i jeden klawisz.

    Obiekt powstaje wyłącznie przez ``zbuduj_kombinacje`` albo
    ``rozbierz_kombinacje``, które sprawdzają reguły, więc każda istniejąca
    instancja jest poprawna.
    """

    control: bool
    alt: bool
    shift: bool
    windows: bool
    klawisz: str

    @property
    def liczba_modyfikatorow(self) -> int:
        return sum((self.control, self.alt, self.shift, self.windows))

    def jako_napis(self) -> str:
        """Postać zapisywana w pliku, na przykład ``Control+Shift+F12``."""
        return "+".join([*self.nazwy_modyfikatorow(), self.klawisz])

    def jako_slowa(self) -> str:
        """Postać do przeczytania na głos, na przykład „Control plus Shift plus F12”."""
        return " plus ".join([*self.nazwy_modyfikatorow(), self.klawisz])

    def nazwy_modyfikatorow(self) -> tuple[str, ...]:
        nazwy: list[str] = []
        if self.control:
            nazwy.append(NAZWA_CONTROL)
        if self.alt:
            nazwy.append(NAZWA_ALT)
        if self.shift:
            nazwy.append(NAZWA_SHIFT)
        if self.windows:
            nazwy.append(NAZWA_WINDOWS)
        return tuple(nazwy)

    def modyfikatory_win32(self) -> int:
        """Suma flag dla ``RegisterHotKey``, zawsze z ``MOD_NOREPEAT``."""
        suma = MOD_NOREPEAT
        if self.control:
            suma |= MOD_CONTROL
        if self.alt:
            suma |= MOD_ALT
        if self.shift:
            suma |= MOD_SHIFT
        if self.windows:
            suma |= MOD_WIN
        return suma

    def kod_klawisza_win32(self) -> int:
        """Kod klawisza wirtualnego Win32 dla ``RegisterHotKey``."""
        if self.klawisz.startswith("F") and len(self.klawisz) > 1:
            return _VK_F1 + int(self.klawisz[1:]) - 1
        return ord(self.klawisz)


def zbuduj_kombinacje(
    *, control: bool, alt: bool, shift: bool, windows: bool, klawisz: str
) -> KombinacjaSkrotu:
    """Sprawdza reguły i zwraca kombinację albo zgłasza ``BladTrwaly`` po polsku.

    Reguły (decyzje użytkownika z 23 października 2026): klawisz z listy
    dozwolonych; co najmniej jeden modyfikator; każdy klawisz, także F1 do F24,
    wymaga co najmniej dwóch modyfikatorów albo klawisza Windows, bo pojedynczy
    modyfikator z klawiszem to skróty programów i systemu (Alt plus F4 zamyka
    okna, Shift plus F10 otwiera menu kontekstowe, Control plus F4 zamyka
    kartę); Control plus Alt z literą albo cyfrą, z Shiftem albo bez, jest
    niedozwolone, bo na polskiej klawiaturze prawy Alt (AltGr) to dla Windows
    Control plus Alt i taki skrót zabrałby polskie litery.
    """
    nazwa = klawisz.strip().upper()
    if nazwa not in KLAWISZE_SKROTU:
        raise BladTrwaly(
            f"Klawisz „{klawisz}” nie jest dozwolony w skrócie. Wybierz klawisz od F1 do F24, "
            "literę od A do Z albo cyfrę od 0 do 9."
        )
    kombinacja = KombinacjaSkrotu(control, alt, shift, windows, nazwa)
    if kombinacja.liczba_modyfikatorow == 0:
        raise BladTrwaly(
            "Skrót musi zawierać co najmniej jeden klawisz modyfikujący: Control, Alt, Shift "
            "albo Windows."
        )
    jest_znakiem = nazwa not in KLAWISZE_FUNKCYJNE
    if jest_znakiem and control and alt:
        raise BladTrwaly(
            "Control plus Alt z literą albo cyfrą jest niedozwolone, bo na polskiej klawiaturze "
            "prawy Alt (AltGr) to dla Windows Control plus Alt, więc taki skrót zabrałby "
            "polskie litery: ą, ę, ł, ń, ó, ś, ź, ż i ć. Wybierz klawisz funkcyjny od F1 do F24 "
            "albo inne modyfikatory."
        )
    if kombinacja.liczba_modyfikatorow < 2 and not windows:
        raise BladTrwaly(
            "Skrót wymaga co najmniej dwóch modyfikatorów albo klawisza Windows, bo pojedynczy "
            "modyfikator z klawiszem to zwykłe skróty programów i systemu, na przykład "
            "Alt plus F4 zamyka okna, Shift plus F10 otwiera menu kontekstowe, a Control plus C "
            "kopiuje. Dodaj drugi modyfikator."
        )
    return kombinacja


def rozbierz_kombinacje(napis: str) -> KombinacjaSkrotu:
    """Zamienia napis w rodzaju ``Control+Shift+F12`` na sprawdzoną kombinację.

    Wielkość liter i odstępy wokół plusa nie mają znaczenia, a ``Ctrl`` i ``Win``
    są przyjmowane jako skróty nazw. Błąd zgłasza ``BladTrwaly`` z komunikatem
    po polsku.
    """
    czesci = [czesc.strip() for czesc in str(napis).split("+")]
    if not czesci or not czesci[-1] or any(not czesc for czesc in czesci):
        raise BladTrwaly(
            f"Skrót „{napis}” ma niepoprawną postać. Podaj modyfikatory i klawisz oddzielone "
            "plusem, na przykład Control+Shift+F12."
        )
    *modyfikatory, klawisz = czesci
    wybrane: set[str] = set()
    for czesc in modyfikatory:
        nazwa = _NAZWY_MODYFIKATOROW.get(czesc.lower())
        if nazwa is None:
            raise BladTrwaly(
                f"Skrót „{napis}” zawiera nieznany modyfikator „{czesc}”. Dozwolone są Control, "
                "Alt, Shift i Windows."
            )
        wybrane.add(nazwa)
    return zbuduj_kombinacje(
        control=NAZWA_CONTROL in wybrane,
        alt=NAZWA_ALT in wybrane,
        shift=NAZWA_SHIFT in wybrane,
        windows=NAZWA_WINDOWS in wybrane,
        klawisz=klawisz,
    )


DOMYSLNA_KOMBINACJA = rozbierz_kombinacje(DOMYSLNA_KOMBINACJA_SKROTU)


@dataclass(frozen=True, slots=True)
class WynikZmianySkrotu:
    """Wynik próby zmiany kombinacji w działającym serwerze.

    ``komunikat`` jest gotowym zdaniem po polsku. ``dziala_teraz`` to napis
    kombinacji, która działa po próbie, albo ``None``, gdy żadna nie jest
    zarejestrowana.
    """

    udalo_sie: bool
    komunikat: str
    dziala_teraz: str | None
