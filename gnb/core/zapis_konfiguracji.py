"""Zapis zmian w pliku konfiguracji TOML z poziomu strony ustawień.

Moduł odpowiada za jedno: zmienić wskazane klucze w pliku konfiguracji
użytkownika, nie niszcząc reszty. Plik jest edytowany biblioteką ``tomlkit``,
która zachowuje komentarze, kolejność i klucze nieznane aplikacji. Nowa treść
jest najpierw zapisywana do pliku tymczasowego i sprawdzana tymi samymi
regułami co przy wczytywaniu konfiguracji; dopiero poprawny plik zastępuje
dotychczasowy przez ``os.replace``, a poprzednia wersja zostaje jako jedna
kopia zapasowa.

Moduł nie decyduje, które pola wolno zmieniać, i nie zna interfejsu WWW.
Zmienne środowiskowe nie biorą udziału w sprawdzaniu: pierwszeństwo zmiennej
nie może sprawić, że błędna wartość w pliku przejdzie niezauważona.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path

import tomlkit
from tomlkit.exceptions import TOMLKitError

from gnb.core.konfiguracja import Konfiguracja, wczytaj_konfiguracje
from gnb.core.wyjatki import BladTrwaly

SUFIKS_KOPII_ZAPASOWEJ = ".bak"
_SUFIKS_TYMCZASOWY = ".nowy"


def zapisz_ustawienia(
    sciezka: Path,
    zmiany: Mapping[str, object],
    usun: Iterable[str] = (),
) -> None:
    """Zmienia i usuwa klucze w pliku konfiguracji, atomowo i po sprawdzeniu poprawności.

    Klucze z ``zmiany`` dostają nową wartość (z wyjątkiem wartości równej
    domyślnej dla klucza, którego w pliku jeszcze nie ma), klucze z ``usun`` znikają z pliku,
    więc obowiązuje dla nich wartość domyślna. Reszta pliku, w tym komentarze
    i klucze nieznane aplikacji, zostaje bez zmian. Niepoprawny wynik kończy się
    ``BladTrwaly`` z komunikatem po polsku, a plik na dysku pozostaje taki, jaki był.
    """
    dokument = _wczytaj_dokument(sciezka)
    domyslna = Konfiguracja()
    for klucz, wartosc in zmiany.items():
        # Wartość równa domyślnej nie trafia do pliku, jeśli nie było tam tego
        # klucza: dzięki temu zmiana wartości domyślnej w nowej wersji aplikacji
        # dosięga użytkownika, który niczego świadomie nie ustawiał.
        if klucz not in dokument and _jako_porownywalne(wartosc) == _jako_porownywalne(
            getattr(domyslna, klucz, object())
        ):
            continue
        dokument[klucz] = _do_wartosci_toml(wartosc)
    for klucz in usun:
        if klucz in dokument:
            del dokument[klucz]
    nowa_tresc = tomlkit.dumps(dokument)

    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = sciezka.with_name(sciezka.name + _SUFIKS_TYMCZASOWY)
    try:
        with tymczasowy.open("w", encoding="utf-8", newline="\n") as plik:
            plik.write(nowa_tresc)
            plik.flush()
            os.fsync(plik.fileno())
        # Sprawdzenie tymi samymi regułami co przy starcie, ale bez zmiennych
        # środowiskowych: błąd w pliku ma wyjść teraz, a nie przy następnym starcie.
        wczytaj_konfiguracje(tymczasowy, srodowisko={})
        if sciezka.exists():
            shutil.copy2(sciezka, sciezka.with_name(sciezka.name + SUFIKS_KOPII_ZAPASOWEJ))
        os.replace(tymczasowy, sciezka)
    except OSError as blad:
        raise BladTrwaly(f"Nie udało się zapisać pliku konfiguracji {sciezka}: {blad}") from blad
    finally:
        tymczasowy.unlink(missing_ok=True)


def _wczytaj_dokument(sciezka: Path) -> tomlkit.TOMLDocument:
    if not sciezka.exists():
        return tomlkit.document()
    try:
        return tomlkit.parse(sciezka.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, TOMLKitError) as blad:
        raise BladTrwaly(f"Nie udało się wczytać pliku konfiguracji {sciezka}: {blad}") from blad


def _jako_porownywalne(wartosc: object) -> object:
    if isinstance(wartosc, (list, tuple)):
        return tuple(str(element) for element in wartosc)
    if isinstance(wartosc, (bool, int, float, str)):
        return wartosc
    return str(wartosc)


def _do_wartosci_toml(wartosc: object) -> object:
    """Zamienia wartość pola na typ zapisywalny w TOML."""
    if isinstance(wartosc, (bool, int, float, str)):
        return wartosc
    if isinstance(wartosc, (list, tuple)):
        return [str(element) for element in wartosc]
    return str(wartosc)
