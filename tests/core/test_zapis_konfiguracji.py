"""Testy zapisu ustawień do pliku konfiguracji TOML.

Pliki wejściowe są napisane ręcznie, z komentarzami i kluczem nieznanym
aplikacji, żeby test nie sprawdzał wyłącznie tego, co sam zapisze bieżący kod.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.konfiguracja import wczytaj_konfiguracje
from gnb.core.wyjatki import BladTrwaly
from gnb.core.zapis_konfiguracji import SUFIKS_KOPII_ZAPASOWEJ, zapisz_ustawienia

_STARY_PLIK = """\
# Moja konfiguracja, komentarz użytkownika.
limit_zrodel = 50  # plan Standard
klucz_obcy = "zostaje"

# Komentarz nad pozycją
respektuj_robots = false
"""


def _zapisz_stary(katalog: Path) -> Path:
    plik = katalog / "konfiguracja.toml"
    plik.write_text(_STARY_PLIK, encoding="utf-8")
    return plik


def test_zmiana_zachowuje_komentarze_i_klucze_nieznane(tmp_path: Path) -> None:
    plik = _zapisz_stary(tmp_path)

    zapisz_ustawienia(plik, {"limit_zrodel": 100, "respektuj_robots": True})

    tresc = plik.read_text(encoding="utf-8")
    assert "# Moja konfiguracja, komentarz użytkownika." in tresc
    assert "# plan Standard" in tresc
    assert "# Komentarz nad pozycją" in tresc
    assert 'klucz_obcy = "zostaje"' in tresc
    konfiguracja = wczytaj_konfiguracje(plik, srodowisko={})
    assert konfiguracja.limit_zrodel == 100
    assert konfiguracja.respektuj_robots is True


def test_poprzednia_wersja_zostaje_jako_kopia_zapasowa(tmp_path: Path) -> None:
    plik = _zapisz_stary(tmp_path)

    zapisz_ustawienia(plik, {"limit_zrodel": 100})

    kopia = plik.with_name(plik.name + SUFIKS_KOPII_ZAPASOWEJ)
    assert kopia.read_text(encoding="utf-8") == _STARY_PLIK
    assert not list(tmp_path.glob("*.nowy"))


def test_niepoprawna_wartosc_nie_zmienia_pliku_i_nie_zostawia_smieci(tmp_path: Path) -> None:
    plik = _zapisz_stary(tmp_path)

    with pytest.raises(BladTrwaly, match="limit_zrodel"):
        zapisz_ustawienia(plik, {"limit_zrodel": -5})

    assert plik.read_text(encoding="utf-8") == _STARY_PLIK
    assert not list(tmp_path.glob("*.nowy"))
    assert not plik.with_name(plik.name + SUFIKS_KOPII_ZAPASOWEJ).exists()


def test_regula_wielu_pol_jest_sprawdzana_na_calym_pliku(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("deduplikacja_prog_duplikatu = 0.9\n", encoding="utf-8")

    with pytest.raises(BladTrwaly, match="deduplikacja_prog_do_przegladu"):
        zapisz_ustawienia(plik, {"deduplikacja_prog_do_przegladu": 0.95})

    assert plik.read_text(encoding="utf-8") == "deduplikacja_prog_duplikatu = 0.9\n"


def test_brak_pliku_jest_tworzony_wraz_z_katalogiem(tmp_path: Path) -> None:
    plik = tmp_path / "nowy_katalog" / "konfiguracja.toml"

    zapisz_ustawienia(plik, {"limit_zrodel": 60})

    assert wczytaj_konfiguracje(plik, srodowisko={}).limit_zrodel == 60


def test_usuniecie_klucza_przywraca_wartosc_domyslna_i_nie_rusza_reszty(tmp_path: Path) -> None:
    plik = _zapisz_stary(tmp_path)

    zapisz_ustawienia(plik, {}, usun=["limit_zrodel", "klucz_nieistniejacy"])

    tresc = plik.read_text(encoding="utf-8")
    assert "limit_zrodel" not in tresc
    assert 'klucz_obcy = "zostaje"' in tresc
    assert wczytaj_konfiguracje(plik, srodowisko={}).limit_zrodel == 100


def test_lista_i_wartosc_logiczna_zapisuja_sie_jako_typy_toml(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"

    zapisz_ustawienia(plik, {"jezyki_napisow": ["de", "fr"], "napisy_automatyczne": False})

    tresc = plik.read_text(encoding="utf-8")
    assert 'jezyki_napisow = ["de", "fr"]' in tresc
    assert "napisy_automatyczne = false" in tresc
    konfiguracja = wczytaj_konfiguracje(plik, srodowisko={})
    assert konfiguracja.jezyki_napisow == ("de", "fr")
    assert konfiguracja.napisy_automatyczne is False


def test_uszkodzony_plik_daje_blad_trwaly_a_nie_wyjatek_biblioteki(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("to nie jest = = toml [", encoding="utf-8")

    with pytest.raises(BladTrwaly, match="Nie udało się wczytać pliku konfiguracji"):
        zapisz_ustawienia(plik, {"limit_zrodel": 60})

    assert plik.read_text(encoding="utf-8") == "to nie jest = = toml ["


def test_wyjatek_robots_dla_zrodel_jawnych_jest_czytany_z_pliku_i_ze_srodowiska(
    tmp_path: Path,
) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("wyjatek_robots_dla_zrodel_jawnych = false\n", encoding="utf-8")

    assert wczytaj_konfiguracje(plik, srodowisko={}).wyjatek_robots_dla_zrodel_jawnych is False
    ze_srodowiska = wczytaj_konfiguracje(
        plik, srodowisko={"GNB_WYJATEK_ROBOTS_DLA_ZRODEL_JAWNYCH": "tak"}
    )
    assert ze_srodowiska.wyjatek_robots_dla_zrodel_jawnych is True


def test_wartosc_rowna_domyslnej_nie_trafia_do_pliku_gdy_klucza_nie_bylo(tmp_path: Path) -> None:
    plik = _zapisz_stary(tmp_path)

    zapisz_ustawienia(
        plik, {"limit_adresow_z_pliku": 200, "limit_zrodel": 100, "formaty_wynikowe": ("txt", "md")}
    )

    tresc = plik.read_text(encoding="utf-8")
    assert "limit_adresow_z_pliku" not in tresc
    assert "formaty_wynikowe" not in tresc
    assert "limit_zrodel = 100" in tresc
