"""Testy nagłówka metadanych dopisywanego na początku plików wynikowych."""

from __future__ import annotations

import pytest

from gnb.core.stale import TypZrodla
from gnb.output.naglowek_metadanych import (
    ETYKIETA_ADRES,
    ETYKIETA_AUTOR,
    ETYKIETA_DATA_IMPORTU,
    ETYKIETA_IDENTYFIKATOR,
    ETYKIETA_PLIK,
    ETYKIETA_TYP,
    ETYKIETA_TYTUL,
    KOLEJNOSC_POL,
    opis_dlugosci,
    opis_typu_zrodla,
    polacz_z_trescia,
    zbuduj_naglowek,
)


def test_pola_sa_wypisane_w_stalej_kolejnosci() -> None:
    """Kolejność jest stała, żeby układ nagłówka był przewidywalny przy odsłuchu."""
    pola = {
        ETYKIETA_IDENTYFIKATOR: "plik_tekstowy-1",
        ETYKIETA_TYTUL: "Notatka",
        ETYKIETA_DATA_IMPORTU: "2026-08-28",
        ETYKIETA_TYP: "plik tekstowy",
    }

    wiersze = zbuduj_naglowek(pola).splitlines()

    assert wiersze == [
        "Tytuł: Notatka",
        "Typ źródła: plik tekstowy",
        "Data importu: 2026-08-28",
        "Identyfikator źródła: plik_tekstowy-1",
    ]


def test_kazdy_wiersz_ma_postac_etykieta_dwukropek_spacja_wartosc() -> None:
    naglowek = zbuduj_naglowek({ETYKIETA_TYTUL: "Notatka", ETYKIETA_AUTOR: "Anna Nowak"})

    for wiersz in naglowek.splitlines():
        etykieta, separator, wartosc = wiersz.partition(": ")
        assert separator == ": "
        assert etykieta and wartosc
        assert etykieta in KOLEJNOSC_POL


def test_pole_nieobecne_jest_pomijane_w_calosci() -> None:
    naglowek = zbuduj_naglowek({ETYKIETA_TYTUL: "Notatka"})

    assert naglowek == "Tytuł: Notatka"
    assert "Autor" not in naglowek


def test_pole_puste_jest_pomijane_tak_samo_jak_nieobecne() -> None:
    naglowek = zbuduj_naglowek({ETYKIETA_TYTUL: "Notatka", ETYKIETA_AUTOR: "   "})

    assert naglowek == "Tytuł: Notatka"


def test_pusty_zestaw_pol_daje_pusty_naglowek() -> None:
    assert zbuduj_naglowek({}) == ""


def test_naglowek_jest_oddzielony_od_tresci_jednym_pustym_wierszem() -> None:
    wynik = polacz_z_trescia("Tytuł: Notatka", "Treść dokumentu.")

    assert wynik == "Tytuł: Notatka\n\nTreść dokumentu."
    assert "---" not in wynik
    assert "===" not in wynik


def test_brak_naglowka_zostawia_sama_tresc() -> None:
    assert polacz_z_trescia("", "Treść dokumentu.") == "Treść dokumentu."


def test_naglowek_nie_zawiera_skladni_markdown() -> None:
    """Metadane nie mogą stać się nagłówkiem sekcji ani trafić do spisu treści."""
    naglowek = zbuduj_naglowek({ETYKIETA_TYTUL: "Notatka", ETYKIETA_ADRES: "https://przyklad.pl/a"})

    assert not naglowek.startswith("#")
    assert "**" not in naglowek
    assert not any(wiersz.startswith(("#", "-", "*", ">")) for wiersz in naglowek.splitlines())


def test_adres_i_plik_moga_wystapic_osobno() -> None:
    z_adresem = zbuduj_naglowek({ETYKIETA_ADRES: "https://przyklad.pl/a"})
    z_plikiem = zbuduj_naglowek({ETYKIETA_PLIK: "notatka.txt"})

    assert z_adresem == "Adres: https://przyklad.pl/a"
    assert z_plikiem == "Plik: notatka.txt"


@pytest.mark.parametrize(
    ("sekundy", "oczekiwane"),
    [
        (0, "0 sekund"),
        (1, "1 sekunda"),
        (3, "3 sekundy"),
        (5, "5 sekund"),
        (13, "13 sekund"),
        (62, "1 minuta 2 sekundy"),
        (1203, "20 minut 3 sekundy"),
        (3600, "1 godzina"),
        (3725, "1 godzina 2 minuty 5 sekund"),
        (7322, "2 godziny 2 minuty 2 sekundy"),
    ],
)
def test_dlugosc_jest_zapisana_slownie_z_poprawna_odmiana(sekundy: int, oczekiwane: str) -> None:
    assert opis_dlugosci(sekundy) == oczekiwane


@pytest.mark.parametrize(
    ("typ", "oczekiwane"),
    [
        (TypZrodla.STRONA_WWW, "strona internetowa"),
        (TypZrodla.YOUTUBE, "film z serwisu YouTube"),
        (TypZrodla.TEKST_WKLEJONY, "tekst wklejony"),
        (TypZrodla.PLIK_TEKSTOWY, "plik tekstowy"),
    ],
)
def test_typ_zrodla_ma_nazwe_zrozumiala_bez_znajomosci_kodu(
    typ: TypZrodla, oczekiwane: str
) -> None:
    assert opis_typu_zrodla(typ) == oczekiwane
