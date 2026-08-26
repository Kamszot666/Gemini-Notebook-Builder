"""Układ katalogów pojedynczego projektu wynikowego.

Katalog projektu leży poza repozytorium, domyślnie w podkatalogu katalogu
wyników pochodzącego z konfiguracji. Wewnątrz katalogu projektu trzymane są
osobno: materiały źródłowe, wyniki pośrednie, pliki wynikowe przeznaczone do
notatnika, manifest, logi i checkpoint. Pliki wynikowe mają własny podkatalog,
żeby dało się je znaleźć bez przeglądania reszty.

Moduł wyznacza ścieżki i tworzy katalogi. Nie zapisuje żadnej treści.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from gnb.core.nazwy import sanityzuj_nazwe_projektu

_NAZWA_MATERIALY_ZRODLOWE = "materialy_zrodlowe"
_NAZWA_WYNIKI_POSREDNIE = "wyniki_posrednie"
_NAZWA_PLIKI_WYNIKOWE = "pliki_wynikowe"
_NAZWA_LOGI = "logi"
_NAZWA_MANIFEST_JSON = "manifest.json"
_NAZWA_MANIFEST_TXT = "manifest.txt"
_NAZWA_CHECKPOINT = "checkpoint.json"
_NAZWA_RAPORT = "raport.txt"


@dataclass(frozen=True, slots=True)
class UkladProjektu:
    """Zestaw ścieżek wewnątrz katalogu jednego projektu wynikowego."""

    katalog_projektu: Path
    identyfikator_projektu: str
    nazwa_projektu: str

    @property
    def materialy_zrodlowe(self) -> Path:
        return self.katalog_projektu / _NAZWA_MATERIALY_ZRODLOWE

    @property
    def wyniki_posrednie(self) -> Path:
        return self.katalog_projektu / _NAZWA_WYNIKI_POSREDNIE

    @property
    def pliki_wynikowe(self) -> Path:
        return self.katalog_projektu / _NAZWA_PLIKI_WYNIKOWE

    @property
    def logi(self) -> Path:
        return self.katalog_projektu / _NAZWA_LOGI

    @property
    def manifest_json(self) -> Path:
        return self.katalog_projektu / _NAZWA_MANIFEST_JSON

    @property
    def manifest_txt(self) -> Path:
        return self.katalog_projektu / _NAZWA_MANIFEST_TXT

    @property
    def checkpoint(self) -> Path:
        return self.katalog_projektu / _NAZWA_CHECKPOINT

    @property
    def raport(self) -> Path:
        return self.katalog_projektu / _NAZWA_RAPORT


def identyfikator_projektu(nazwa_bezpieczna: str) -> str:
    """Wyprowadza stabilny identyfikator projektu ze skrótu jego bezpiecznej nazwy."""
    skrot = hashlib.sha256(nazwa_bezpieczna.encode("utf-8")).hexdigest()[:12]
    return f"proj-{skrot}"


def ustal_uklad(
    katalog_nadrzedny: Path,
    nazwa: str,
    *,
    wlasny_katalog_projektu: Path | None = None,
) -> UkladProjektu:
    """Wyznacza ścieżki projektu bez tworzenia katalogów na dysku.

    Nazwa projektu jest sanityzowana do postaci bezpiecznej dla Windows. Gdy
    użytkownik wskaże własny katalog projektu, jest on używany wprost, a nazwa
    służy tylko do wyznaczenia identyfikatora projektu.
    """
    nazwa_bezpieczna = sanityzuj_nazwe_projektu(nazwa)
    katalog = (
        wlasny_katalog_projektu
        if wlasny_katalog_projektu is not None
        else katalog_nadrzedny / nazwa_bezpieczna
    )
    return UkladProjektu(
        katalog_projektu=katalog,
        identyfikator_projektu=identyfikator_projektu(nazwa_bezpieczna),
        nazwa_projektu=nazwa_bezpieczna,
    )


def utworz_katalogi(uklad: UkladProjektu) -> None:
    """Tworzy katalog projektu i jego podkatalogi, jeżeli jeszcze nie istnieją."""
    for katalog in (
        uklad.katalog_projektu,
        uklad.materialy_zrodlowe,
        uklad.wyniki_posrednie,
        uklad.pliki_wynikowe,
        uklad.logi,
    ):
        katalog.mkdir(parents=True, exist_ok=True)
