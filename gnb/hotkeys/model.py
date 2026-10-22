"""Typy danych współdzielone między odczytem stanu pulpitu a rozpoznaniem źródła.

Moduł nie zależy od Windows, dzięki czemu logika w ``rozpoznanie.py`` i
``kolejka.py`` jest testowalna na każdym systemie: testy budują te struktury
ręcznie, bez wywołania ani jednej funkcji Win32.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class InformacjeOOknie:
    """Migawka aktywnego okna zebrana przez ``_win32.py``.

    Pole ``nazwa_procesu`` jest nazwą pliku wykonywalnego bez rozszerzenia
    i bez wielkości liter, na przykład ``chrome`` albo ``explorer``. Pole
    ``nazwa_klasy`` jest nazwą klasy okna Win32, potrzebną do odróżnienia
    prawdziwego okna Eksploratora plików (``CabinetWClass``) od pulpitu
    i paska zadań, które też należą do procesu ``explorer.exe``.
    """

    uchwyt: int
    tytul: str
    nazwa_klasy: str
    nazwa_procesu: str


class TypDodania(StrEnum):
    """Rodzaj źródła, jakie skrót dodaje do aktywnego projektu."""

    ADRES = "adres"
    PLIKI = "pliki"
    ADRESY_Z_ZAZNACZENIA = "adresy_z_zaznaczenia"
    TEKST = "tekst"


@dataclass(frozen=True, slots=True)
class DodanieZeSkrotu:
    """Wynik rozpoznania: co konkretnie dodać do aktywnego projektu.

    Pole ``opis`` jest krótkim opisem do komunikatu potwierdzenia, na przykład
    tytułem strony albo nazwą pierwszego zaznaczonego pliku.
    """

    typ: TypDodania
    opis: str
    adres: str | None = None
    pliki: tuple[Path, ...] = ()
    adresy: tuple[str, ...] = ()
    tekst: str = ""
    liczba_pominietych_adresow_interfejsu: int = 0


class RodzajZaznaczenia(StrEnum):
    """Czym jest tekst zaznaczony w przeglądarce: samymi adresami czy zwykłym tekstem."""

    ADRESY = "adresy"
    TEKST = "tekst"


@dataclass(frozen=True, slots=True)
class ZaznaczonyTekst:
    """Sklasyfikowany tekst zaznaczony w przeglądarce.

    Dla rodzaju ``ADRESY`` pole ``adresy`` niesie adresy bez powtórzeń,
    w kolejności wystąpienia. Dla rodzaju ``TEKST`` pole ``tekst`` niesie
    zaznaczenie z usuniętymi białymi znakami na obu końcach.
    """

    rodzaj: RodzajZaznaczenia
    adresy: tuple[str, ...] = ()
    tekst: str = ""


class RodzajWynikuKopiowania(StrEnum):
    """Wynik próby odczytania zaznaczenia przez schowek."""

    ZAZNACZONO = "zaznaczono"
    NIC_NIE_ZAZNACZONO = "nic_nie_zaznaczono"
    SCHOWEK_NIE_DO_PRZYWROCENIA = "schowek_nie_do_przywrocenia"
    BLAD = "blad"


@dataclass(frozen=True, slots=True)
class WynikKopiowania:
    """Co zwróciła próba skopiowania zaznaczenia z przeglądarki.

    Pole ``tekst`` jest wypełnione tylko dla ``ZAZNACZONO``. Pole ``uwaga`` niesie
    zdanie dla użytkownika, gdy coś poszło nie tak mimo uzyskanego wyniku,
    na przykład nie udało się przywrócić poprzedniej zawartości schowka.
    """

    rodzaj: RodzajWynikuKopiowania
    tekst: str = ""
    uwaga: str = ""
