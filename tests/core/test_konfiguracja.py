"""Testy wczytywania konfiguracji z wartości domyślnych, pliku TOML i środowiska."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.konfiguracja import (
    DOMYSLNY_BEZPIECZNY_LIMIT_SLOW,
    DOMYSLNY_LIMIT_ZRODEL,
    wczytaj_konfiguracje,
)
from gnb.core.wyjatki import BladTrwaly


def test_brak_pliku_daje_wartosci_domyslne(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})
    assert konfiguracja.limit_zrodel == DOMYSLNY_LIMIT_ZRODEL
    assert konfiguracja.bezpieczny_limit_slow == DOMYSLNY_BEZPIECZNY_LIMIT_SLOW
    assert konfiguracja.formaty_wynikowe == ("txt", "md")


def test_wartosci_z_pliku_toml_sa_wczytywane(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text(
        'katalog_wynikow = "D:/Wyniki"\n'
        "limit_zrodel = 300\n"
        "bezpieczny_limit_slow = 200000\n"
        'formaty_wynikowe = ["txt"]\n',
        encoding="utf-8",
    )
    konfiguracja = wczytaj_konfiguracje(plik, srodowisko={})
    assert konfiguracja.katalog_wynikow == Path("D:/Wyniki")
    assert konfiguracja.limit_zrodel == 300
    assert konfiguracja.bezpieczny_limit_slow == 200000
    assert konfiguracja.formaty_wynikowe == ("txt",)


def test_zmienna_srodowiskowa_ma_pierwszenstwo_przed_plikiem(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("limit_zrodel = 300\n", encoding="utf-8")
    konfiguracja = wczytaj_konfiguracje(plik, srodowisko={"GNB_LIMIT_ZRODEL": "50"})
    assert konfiguracja.limit_zrodel == 50


def test_zmienna_srodowiskowa_katalogu_wynikow(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml", srodowisko={"GNB_KATALOG_WYNIKOW": "/dane/wyniki"}
    )
    assert konfiguracja.katalog_wynikow == Path("/dane/wyniki")


def test_uszkodzony_plik_toml_daje_blad_trwaly(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("to nie jest = poprawny [ toml", encoding="utf-8")
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(plik, srodowisko={})


def test_niepoprawna_liczba_daje_blad_trwaly(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={"GNB_LIMIT_ZRODEL": "sto"})


def test_nieznany_format_wynikowy_daje_blad_trwaly(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml", srodowisko={"GNB_FORMATY_WYNIKOWE": "txt,pdf"}
        )


def test_zachowuj_oryginaly_jest_domyslnie_wlaczone_i_da_sie_wylaczyc(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("limit_zrodel = 50\n", encoding="utf-8")

    assert wczytaj_konfiguracje(plik, {}).zachowuj_oryginaly is True

    plik.write_text("zachowuj_oryginaly = false\n", encoding="utf-8")
    assert wczytaj_konfiguracje(plik, {}).zachowuj_oryginaly is False

    assert wczytaj_konfiguracje(plik, {"GNB_ZACHOWUJ_ORYGINALY": "tak"}).zachowuj_oryginaly is True


def test_niepoprawna_wartosc_logiczna_konczy_sie_bledem(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text('zachowuj_oryginaly = "moze"\n', encoding="utf-8")
    with pytest.raises(BladTrwaly, match="wartością logiczną"):
        wczytaj_konfiguracje(plik, {})


def test_deduplikacja_ma_domyslne_wlaczenie_i_progi(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})

    assert konfiguracja.deduplikacja_hash_wlaczona is True
    assert konfiguracja.deduplikacja_kosmetyczna_wlaczona is True
    assert konfiguracja.deduplikacja_podobienstwo_wlaczone is True
    assert konfiguracja.deduplikacja_embeddingi_wlaczone is False
    assert konfiguracja.deduplikacja_prog_duplikatu == 0.9
    assert konfiguracja.deduplikacja_prog_do_przegladu == 0.75


def test_progi_deduplikacji_da_sie_ustawic_z_pliku_i_srodowiska(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("deduplikacja_prog_duplikatu = 0.95\n", encoding="utf-8")
    assert wczytaj_konfiguracje(plik, {}).deduplikacja_prog_duplikatu == 0.95

    z_srodowiska = wczytaj_konfiguracje(plik, {"GNB_DEDUPLIKACJA_PROG_DUPLIKATU": "0,8"})
    assert z_srodowiska.deduplikacja_prog_duplikatu == 0.8


def test_prog_deduplikacji_spoza_przedzialu_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="od zera do jednego"):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml", srodowisko={"GNB_DEDUPLIKACJA_PROG_DUPLIKATU": "1.5"}
        )


def test_prog_do_przegladu_wyzszy_niz_prog_duplikatu_konczy_sie_bledem(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text(
        "deduplikacja_prog_duplikatu = 0.7\ndeduplikacja_prog_do_przegladu = 0.9\n",
        encoding="utf-8",
    )
    with pytest.raises(BladTrwaly, match="nie może być wyższe"):
        wczytaj_konfiguracje(plik, {})
