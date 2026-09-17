"""Rozpoznanie, co globalny skrót ma dodać do aktywnego projektu.

Czysta logika, niezależna od Windows: przyjmuje już zebrane informacje
o aktywnym oknie, ewentualną wartość paska adresu i ewentualną listę
zaznaczonych plików, a zwraca albo opis tego, co dodać, albo porażkę
z czytelnym powodem. Dzięki temu ta funkcja jest testowalna na każdym
systemie, bez ani jednego wywołania Win32 — testy budują ``InformacjeOOknie``
ręcznie.

Rozróżnienie dwóch sytuacji przy przeglądarce jest celowe i zgodne z decyzją
z sekcji dwunastej CLAUDE.md: pasek adresu odczytany i pusty daje jedną
porażkę, a pasek adresu, którego w ogóle nie dało się odczytać, daje inną —
ta druga nigdy nie dodaje niczego po cichu.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gnb.hotkeys.model import DodanieZeSkrotu, InformacjeOOknie, TypDodania

# Nazwy procesów przeglądarek obsługiwanych w części A etapu jedenastego,
# zgodnie z decyzją użytkownika: to dwie przeglądarki używane na co dzień.
_PRZEGLADARKI = frozenset({"chrome", "firefox"})

# Nazwa klasy okna prawdziwego Eksploratora plików. Sam proces „explorer”
# obsługuje też pulpit i pasek zadań, więc nazwa procesu nie wystarcza do
# rozpoznania, patrz ``_KLASY_PULPITU`` niżej.
_KLASA_OKNA_EKSPLORATORA = "CabinetWClass"

# Klasy okien pulpitu i paska zadań, należące do procesu „explorer”, ale
# niebędące oknem z zawartością. Dostają osobny, czytelniejszy komunikat
# porażki niż nierozpoznany program.
_KLASY_PULPITU = frozenset({"Progman", "WorkerW", "Shell_TrayWnd"})

_SCHEMATY_ROZPOZNAWANE = ("http://", "https://", "ftp://", "file://")


@dataclass(frozen=True, slots=True)
class PorazkaRozpoznania:
    """Skrót nie ma czego dodać do aktywnego projektu. Niesie czytelny powód."""

    powod: str


def rozpoznaj(
    okno: InformacjeOOknie,
    adres_paska: str | None,
    pliki_zaznaczone: Sequence[Path],
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    """Ustala, co dodać do aktywnego projektu na podstawie stanu aktywnego okna.

    Argument ``adres_paska`` ma trzy możliwe znaczenia: wartość ze spacjami
    obciętymi to odczytany adres, pusty napis to odczytany, ale pusty pasek
    adresu, a ``None`` oznacza, że paska adresu w ogóle nie dało się odczytać.
    Tylko pierwsza sytuacja kończy się dodaniem adresu.
    """
    if okno.nazwa_procesu in _PRZEGLADARKI:
        return _rozpoznaj_przegladarke(okno, adres_paska)
    if okno.nazwa_klasy == _KLASA_OKNA_EKSPLORATORA:
        return _rozpoznaj_eksplorator(pliki_zaznaczone)
    if okno.nazwa_klasy in _KLASY_PULPITU:
        return PorazkaRozpoznania("Aktywne okno to pulpit. Nic nie dodano.")
    nazwa = okno.nazwa_procesu or "nieznany"
    return PorazkaRozpoznania(f"Aktywny program to {nazwa}, nie wiem, jak z niego coś dodać.")


def _rozpoznaj_przegladarke(
    okno: InformacjeOOknie, adres_paska: str | None
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    if adres_paska is None:
        return PorazkaRozpoznania(
            f"Nie udało się odczytać paska adresu w oknie „{okno.tytul}”. Nic nie dodano."
        )
    adres = adres_paska.strip()
    if not adres:
        return PorazkaRozpoznania(
            f"Pasek adresu w oknie „{okno.tytul}” jest pusty. Nic nie dodano."
        )
    return DodanieZeSkrotu(
        typ=TypDodania.ADRES, opis=okno.tytul or adres, adres=_znormalizowany_adres(adres)
    )


def _rozpoznaj_eksplorator(
    pliki_zaznaczone: Sequence[Path],
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    if not pliki_zaznaczone:
        return PorazkaRozpoznania(
            "Aktywne okno to Eksplorator plików bez zaznaczenia. Nic nie dodano."
        )
    pierwszy = pliki_zaznaczone[0].name
    if len(pliki_zaznaczone) == 1:
        opis = pierwszy
    else:
        opis = f"{pierwszy} i {len(pliki_zaznaczone) - 1} więcej"
    return DodanieZeSkrotu(typ=TypDodania.PLIKI, opis=opis, pliki=tuple(pliki_zaznaczone))


def _znormalizowany_adres(adres: str) -> str:
    """Dokłada schemat ``https://``, gdy pasek adresu pokazuje go bez schematu.

    Współczesne przeglądarki chowają schemat ``https://`` w pasku adresu, co
    sprawdzono na komputerze użytkownika zarówno w Chrome, jak i w Firefoksie.
    Adres z rozpoznawalnym schematem, na przykład ``http://`` z połączenia bez
    szyfrowania, zostaje bez zmian.
    """
    if adres.lower().startswith(_SCHEMATY_ROZPOZNAWANE):
        return adres
    return f"https://{adres}"
