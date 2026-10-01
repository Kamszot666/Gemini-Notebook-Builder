"""Blokada pojedynczej kopii serwera interfejsu.

Moduł odpowiada za to, żeby w danym momencie działała tylko jedna kopia
procesu ``python -m gnb.ui.server``. Blokada jest niezależna od portu: to plik
w katalogu danych aplikacji, na którym proces zakłada blokadę systemu
operacyjnego. System zwalnia ją sam, gdy proces się kończy, także po awarii
albo zabiciu procesu, więc pozostawiony plik nie blokuje kolejnego uruchomienia.

Moduł nie zatrzymuje ani nie zakłóca działającej kopii i nie obejmuje poleceń
wiersza poleceń ``gnb.cli``. Kod zależny od systemu leży wyłącznie za
sprawdzeniem ``sys.platform``, zgodnie z sekcją szóstą CLAUDE.md.

Plik niesie też adres działającej kopii, żeby druga kopia mogła go podać
użytkownikowi. Na Windows blokowany jest jeden bajt daleko za treścią pliku,
bo blokada zakresu bajtów uniemożliwia innym procesom odczyt zablokowanego
zakresu, a adres musi dać się odczytać.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

NAZWA_PLIKU_BLOKADY = "serwer.lock"

# Przesunięcie blokowanego bajtu na Windows. Leży za wszelką możliwą treścią
# pliku, który niesie tylko jeden krótki adres.
_PRZESUNIECIE_BLOKADY = 1_048_576
_MAKSYMALNA_DLUGOSC_ADRESU = 512


class BlokadaInstancji:
    """Wyłączna blokada systemowa na pliku w katalogu danych aplikacji."""

    def __init__(self, katalog_danych: Path) -> None:
        self._sciezka = katalog_danych / NAZWA_PLIKU_BLOKADY
        self._plik: BinaryIO | None = None

    @property
    def sciezka(self) -> Path:
        return self._sciezka

    def zajmij(self) -> bool:
        """Zakłada blokadę. Zwraca fałsz, gdy trzyma ją już inny proces.

        Błąd wejścia-wyjścia przy otwieraniu pliku, na przykład brak
        uprawnień do katalogu, jest przekazywany wyżej jako ``OSError``.
        """
        if self._plik is not None:
            return True
        self._sciezka.parent.mkdir(parents=True, exist_ok=True)
        plik = open(self._sciezka, "a+b")  # noqa: SIM115 - plik żyje do zwolnienia blokady.
        if not _zaloz_blokade(plik):
            plik.close()
            return False
        self._plik = plik
        return True

    def zapisz_adres(self, adres: str) -> None:
        """Zapisuje adres działającej kopii, żeby druga kopia mogła go podać."""
        if self._plik is None:
            return
        dane = adres.encode("utf-8")[:_MAKSYMALNA_DLUGOSC_ADRESU]
        self._plik.seek(0)
        self._plik.truncate(0)
        self._plik.write(dane)
        self._plik.flush()

    def zwolnij(self) -> None:
        """Zwalnia blokadę i zamyka plik. Plik zostaje na dysku, bo nie szkodzi."""
        if self._plik is None:
            return
        try:
            _zdejmij_blokade(self._plik)
        finally:
            self._plik.close()
            self._plik = None

    def __enter__(self) -> BlokadaInstancji:
        return self

    def __exit__(
        self,
        typ: type[BaseException] | None,
        wartosc: BaseException | None,
        slad: TracebackType | None,
    ) -> None:
        self.zwolnij()


def odczytaj_adres_dzialajacej_kopii(katalog_danych: Path) -> str | None:
    """Zwraca adres zapisany przez działającą kopię albo ``None``, gdy go nie ma."""
    try:
        tresc = (katalog_danych / NAZWA_PLIKU_BLOKADY).read_bytes()
    except OSError:
        return None
    adres = tresc[:_MAKSYMALNA_DLUGOSC_ADRESU].decode("utf-8", errors="replace").strip()
    return adres or None


if sys.platform == "win32":
    import msvcrt

    def _zaloz_blokade(plik: BinaryIO) -> bool:
        plik.seek(_PRZESUNIECIE_BLOKADY)
        try:
            msvcrt.locking(plik.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        finally:
            plik.seek(0)
        return True

    def _zdejmij_blokade(plik: BinaryIO) -> None:
        plik.seek(_PRZESUNIECIE_BLOKADY)
        try:
            msvcrt.locking(plik.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            plik.seek(0)

else:
    import fcntl

    def _zaloz_blokade(plik: BinaryIO) -> bool:
        try:
            fcntl.flock(plik.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        return True

    def _zdejmij_blokade(plik: BinaryIO) -> None:
        try:
            fcntl.flock(plik.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
