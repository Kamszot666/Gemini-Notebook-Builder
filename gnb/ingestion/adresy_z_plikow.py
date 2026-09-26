"""Przyjmowanie plików TXT, MD i DOCX, które mogą zawierać adresy stron.

Interfejs WWW i polecenie `przetworz` przyjmują plik tą samą drogą. Plik złożony
wyłącznie z adresów jest jawną listą źródeł: każdy adres staje się źródłem
wskazanym wprost, a sam plik nie trafia do notatnika. Zwykły plik z adresami
w treści zostaje źródłem tekstowym, a adresy jawne z jego treści są dodawane
osobno, jako źródła niewskazane wprost, do limitu adresów z jednego pliku.

Moduł nie pobiera niczego i nie zna interfejsu ani wiersza poleceń. Nie czyta też
celów odnośników ukrytych pod innym tekstem: automatycznie pobierane są
wyłącznie adresy zapisane w widocznej treści.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.lista_url import (
    KOMUNIKAT_LIMIT_ADRESOW_Z_PLIKU,
    AdresWejsciowy,
    adresy_z_pliku_z_limitem,
    rozpoznaj_liste_adresow_w_pliku,
)
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik, przyjmij_url


@dataclass(frozen=True, slots=True)
class PrzyjeciePliku:
    """Wynik przyjęcia jednego pliku: pozycje do przetworzenia i adresy z treści.

    Dla pliku będącego listą adresów `pozycje` zawiera adresy jako źródła jawne,
    a `jest_lista_adresow` jest prawdą. Dla zwykłego pliku `pozycje` zawiera sam
    plik, a `adresy_znalezione` adresy jawne z jego treści, które wywołujący
    dołącza funkcją `dolacz_adresy_znalezione`. Pole `ostrzezenie` jest
    ustawione po przekroczeniu limitu adresów z jednego pliku.
    """

    pozycje: tuple[PozycjaWejsciowa, ...]
    adresy_znalezione: tuple[AdresWejsciowy, ...] = ()
    jest_lista_adresow: bool = False
    liczba_znalezionych: int = 0
    ostrzezenie: str | None = None


def przyjmij_plik_z_adresami(
    sciezka: Path,
    moment: datetime,
    konfiguracja: Konfiguracja,
    *,
    grupa: str | None = None,
    nuty: bool = False,
) -> PrzyjeciePliku:
    """Przyjmuje plik jako listę adresów albo jako źródło z adresami w treści."""
    lista = rozpoznaj_liste_adresow_w_pliku(sciezka, konfiguracja.dodatkowe_parametry_sledzace)
    if lista is not None:
        pozycje = tuple(
            przyjmij_url(
                wpis.podany, moment, konfiguracja.dodatkowe_parametry_sledzace, grupa=grupa
            )
            for wpis in lista.adresy
        )
        return PrzyjeciePliku(
            pozycje=pozycje, jest_lista_adresow=True, liczba_znalezionych=len(pozycje)
        )

    z_pliku = adresy_z_pliku_z_limitem(
        sciezka, konfiguracja.limit_adresow_z_pliku, konfiguracja.dodatkowe_parametry_sledzace
    )
    pozycja_pliku = przyjmij_plik(sciezka, moment, grupa=grupa, nuty=nuty)
    ostrzezenie: str | None = None
    if z_pliku.przekroczono_limit:
        ostrzezenie = KOMUNIKAT_LIMIT_ADRESOW_Z_PLIKU.format(
            znaleziono=z_pliku.liczba_znalezionych, limit=z_pliku.limit
        )
        pozycja_pliku = replace(pozycja_pliku, ostrzezenia_wejscia=(ostrzezenie,))
    return PrzyjeciePliku(
        pozycje=(pozycja_pliku,),
        adresy_znalezione=z_pliku.adresy,
        liczba_znalezionych=z_pliku.liczba_znalezionych,
        ostrzezenie=ostrzezenie,
    )


def dolacz_adresy_znalezione(
    pozycje: list[PozycjaWejsciowa],
    znalezione: list[AdresWejsciowy],
    moment: datetime,
    konfiguracja: Konfiguracja,
    *,
    grupa: str | None = None,
) -> None:
    """Dopisuje na końcu listy adresy znalezione w treści plików, bez wyjątku od robots.txt.

    Adres, który już jest na liście pozycji, nie jest dodawany drugi raz.
    """
    znane = {pozycja.adres_kanoniczny for pozycja in pozycje if pozycja.adres_kanoniczny}
    for wpis in znalezione:
        if wpis.kanoniczny in znane:
            continue
        znane.add(wpis.kanoniczny)
        pozycje.append(
            przyjmij_url(
                wpis.podany,
                moment,
                konfiguracja.dodatkowe_parametry_sledzace,
                grupa=grupa,
                wskazane_jawnie=False,
            )
        )
