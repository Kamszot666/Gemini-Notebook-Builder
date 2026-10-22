"""Testy wczytywania ustawień wyglądu i odrzucania znaków sterujących w konfiguracji.

Pliki wejściowe są napisane ręcznie, żeby test nie sprawdzał tylko tego, co sam
zapisze bieżący kod.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja, wczytaj_konfiguracje
from gnb.core.wyjatki import BladTrwaly


def _plik(katalog: Path, tresc: str) -> Path:
    sciezka = katalog / "konfiguracja.toml"
    sciezka.write_text(tresc, encoding="utf-8")
    return sciezka


def test_domyslny_wyglad_to_ciemny_schemat_w_rozmiarze_domyslnym() -> None:
    konfiguracja = Konfiguracja()

    assert konfiguracja.wyglad_schemat == "ciemny"
    assert konfiguracja.wyglad_rozmiar_czcionki == 100
    assert konfiguracja.wyglad_kroj_pisma == "systemowy"


def test_wyglad_z_pliku_i_zmienna_srodowiskowa_ma_pierwszenstwo(tmp_path: Path) -> None:
    plik = _plik(
        tmp_path,
        'wyglad_schemat = "bialy_na_czarnym"\n'
        "wyglad_rozmiar_czcionki = 150\n"
        'wyglad_kolor_tla = "#ABCDEF"\n',
    )

    z_pliku = wczytaj_konfiguracje(plik, srodowisko={})
    ze_zmienna = wczytaj_konfiguracje(plik, srodowisko={"GNB_WYGLAD_SCHEMAT": "Zolty_Na_Czarnym"})

    assert z_pliku.wyglad_schemat == "bialy_na_czarnym"
    assert z_pliku.wyglad_rozmiar_czcionki == 150
    assert z_pliku.wyglad_kolor_tla == "#abcdef"
    assert ze_zmienna.wyglad_schemat == "zolty_na_czarnym"


@pytest.mark.parametrize(
    ("tresc", "nazwa_pola"),
    [
        ('wyglad_schemat = "tecza"\n', "wyglad_schemat"),
        ("wyglad_rozmiar_czcionki = 90\n", "wyglad_rozmiar_czcionki"),
        ('wyglad_rozmiar_czcionki = "duzy"\n', "wyglad_rozmiar_czcionki"),
        ('wyglad_kroj_pisma = "comic"\n', "wyglad_kroj_pisma"),
        ('wyglad_kolor_tla = "red"\n', "wyglad_kolor_tla"),
        ('wyglad_kolor_tekstu = "#fff"\n', "wyglad_kolor_tekstu"),
        ('wyglad_kolor_fokusu = "#12345g"\n', "wyglad_kolor_fokusu"),
        ('wyglad_kolor_bledu = "#ffffff; color: red"\n', "wyglad_kolor_bledu"),
        (
            'wyglad_kolor_obramowania = "#fff;}</style><script>x</script>"\n',
            "wyglad_kolor_obramowania",
        ),
        ('wyglad_kolor_odnosnikow = "url(x)"\n', "wyglad_kolor_odnosnikow"),
    ],
)
def test_niepoprawny_wyglad_w_pliku_daje_blad_trwaly_z_nazwa_pola(
    tmp_path: Path, tresc: str, nazwa_pola: str
) -> None:
    plik = _plik(tmp_path, tresc)

    with pytest.raises(BladTrwaly, match=nazwa_pola):
        wczytaj_konfiguracje(plik, srodowisko={})


def test_niepoprawny_kolor_ze_zmiennej_srodowiskowej_jest_odrzucany(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="wyglad_kolor_tla"):
        wczytaj_konfiguracje(
            tmp_path / "brak.toml", srodowisko={"GNB_WYGLAD_KOLOR_TLA": "javascript:alert(1)"}
        )


# --- znaki sterujące -----------------------------------------------------------


@pytest.mark.parametrize("znak", ["\r", "\n", "\t", "\x00", "\x1b", "\x7f", "\x85"])
def test_plik_z_znakiem_sterujacym_w_nazwie_klienta_jest_odrzucany(
    tmp_path: Path, znak: str
) -> None:
    # Plik zapisany ręcznie: znak sterujący trafia do TOML jako sekwencja ucieczki.
    kod = f"\\u{ord(znak):04x}"
    plik = _plik(tmp_path, f'nazwa_klienta = "Klient{kod}X"\n')

    with pytest.raises(BladTrwaly, match="nazwa_klienta.*znak sterujący"):
        wczytaj_konfiguracje(plik, srodowisko={})


def test_znak_sterujacy_w_elemencie_listy_jest_odrzucany(tmp_path: Path) -> None:
    plik = _plik(tmp_path, 'jezyki_napisow = ["pl", "e\\u000dn"]\n')

    with pytest.raises(BladTrwaly, match="jezyki_napisow"):
        wczytaj_konfiguracje(plik, srodowisko={})


def test_znak_sterujacy_w_srodku_zmiennej_srodowiskowej_jest_odrzucany(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="nazwa_klienta"):
        wczytaj_konfiguracje(
            tmp_path / "brak.toml",
            srodowisko={"GNB_NAZWA_KkLIENTA": "x", "GNB_NAZWA_KLIENTA": "a\r\nb"},
        )


def test_zwykle_znaki_unicode_w_nazwie_klienta_nie_sa_odrzucane(tmp_path: Path) -> None:
    plik = _plik(tmp_path, 'nazwa_klienta = "Zażółć gęślą jaźń 1.0"\n')

    assert wczytaj_konfiguracje(plik, srodowisko={}).nazwa_klienta == "Zażółć gęślą jaźń 1.0"
