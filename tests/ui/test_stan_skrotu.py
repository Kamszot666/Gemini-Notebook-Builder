"""Testy stanu globalnego skrótu widocznego w interfejsie: aktywny projekt i komunikat."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gnb.ui.stan_skrotu import (
    NAZWA_PLIKU_STANU_SKROTU,
    AktywnyProjektSkrotu,
    OstatniKomunikatSkrotu,
    StanSzkicu,
    SzkicTekstuSkrotu,
    dolacz_do_szkicu,
)


def test_aktywny_projekt_jest_pusty_na_starcie() -> None:
    assert AktywnyProjektSkrotu().aktualny() is None


def test_aktywny_projekt_po_ustawieniu() -> None:
    stan = AktywnyProjektSkrotu()
    stan.ustaw("Projekt testowy")

    assert stan.aktualny() == "Projekt testowy"


def test_aktywny_projekt_zmiana_nadpisuje_poprzedni() -> None:
    stan = AktywnyProjektSkrotu()
    stan.ustaw("Pierwszy")
    stan.ustaw("Drugi")

    assert stan.aktualny() == "Drugi"


def test_ostatni_komunikat_jest_pusty_na_starcie() -> None:
    assert OstatniKomunikatSkrotu().aktualny() is None


def test_ostatni_komunikat_po_ustawieniu_niesie_tekst_i_wynik() -> None:
    stan = OstatniKomunikatSkrotu()
    stan.ustaw("Dodano adres strony: Przykład", sukces=True)

    komunikat = stan.aktualny()
    assert komunikat is not None
    assert komunikat.tekst == "Dodano adres strony: Przykład"
    assert komunikat.sukces is True


def test_ostatni_komunikat_porazki() -> None:
    stan = OstatniKomunikatSkrotu()
    stan.ustaw("Brak aktywnego projektu skrótu.", sukces=False)

    komunikat = stan.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is False


def test_ostatni_komunikat_zapamietuje_tylko_najnowszy() -> None:
    stan = OstatniKomunikatSkrotu()
    stan.ustaw("Pierwszy", sukces=True)
    stan.ustaw("Drugi", sukces=False)

    komunikat = stan.aktualny()
    assert komunikat is not None
    assert komunikat.tekst == "Drugi"
    assert komunikat.sukces is False


# --- trwały zapis aktywnego projektu ----------------------------------------


def _utworz_projekt_z_checkpointem(katalog_wynikow: Path, nazwa: str) -> None:
    katalog = katalog_wynikow / nazwa
    katalog.mkdir(parents=True)
    (katalog / "checkpoint.json").write_text("{}", encoding="utf-8")


def test_aktywny_projekt_jest_przywracany_po_ponownym_utworzeniu(tmp_path: Path) -> None:
    plik = tmp_path / "dane" / NAZWA_PLIKU_STANU_SKROTU
    wyniki = tmp_path / "wyniki"
    _utworz_projekt_z_checkpointem(wyniki, "Projekt A")
    AktywnyProjektSkrotu(plik).ustaw("Projekt A")

    nowy = AktywnyProjektSkrotu(plik)
    komunikat = nowy.przywroc(wyniki)

    assert komunikat is None
    assert nowy.aktualny() == "Projekt A"


def test_zapis_stanu_jest_atomowy_i_ma_numer_wersji_schematu(tmp_path: Path) -> None:
    plik = tmp_path / NAZWA_PLIKU_STANU_SKROTU

    AktywnyProjektSkrotu(plik).ustaw("Projekt Zażółć")

    assert json.loads(plik.read_text(encoding="utf-8")) == {
        "wersja_schematu": 1,
        "aktywny_projekt": "Projekt Zażółć",
    }
    assert not plik.with_name(plik.name + ".tmp").exists()


def test_przywracanie_z_recznie_napisanego_pliku_stanu(tmp_path: Path) -> None:
    """Plik napisany ręcznie, nie wygenerowany bieżącym kodem."""
    plik = tmp_path / NAZWA_PLIKU_STANU_SKROTU
    plik.write_text('{"wersja_schematu": 1, "aktywny_projekt": "Stary"}', encoding="utf-8")
    wyniki = tmp_path / "wyniki"
    _utworz_projekt_z_checkpointem(wyniki, "Stary")

    stan = AktywnyProjektSkrotu(plik)

    assert stan.przywroc(wyniki) is None
    assert stan.aktualny() == "Stary"


def test_projekt_usuniety_z_dysku_nie_jest_aktywny_a_zapis_jest_czyszczony(
    tmp_path: Path,
) -> None:
    plik = tmp_path / NAZWA_PLIKU_STANU_SKROTU
    wyniki = tmp_path / "wyniki"
    wyniki.mkdir()
    plik.write_text('{"wersja_schematu": 1, "aktywny_projekt": "Zniknął"}', encoding="utf-8")

    stan = AktywnyProjektSkrotu(plik)
    komunikat = stan.przywroc(wyniki)

    assert stan.aktualny() is None
    assert komunikat is not None
    assert "Zniknął" in komunikat and "już nie ma" in komunikat
    assert not plik.exists()
    # Katalogu nie tworzy się od nowa tylko dlatego, że projekt był zapamiętany.
    assert not (wyniki / "Zniknął").exists()


def test_katalog_bez_checkpointu_nie_jest_projektem_do_przywrocenia(tmp_path: Path) -> None:
    plik = tmp_path / NAZWA_PLIKU_STANU_SKROTU
    wyniki = tmp_path / "wyniki"
    (wyniki / "Pusty").mkdir(parents=True)
    plik.write_text('{"wersja_schematu": 1, "aktywny_projekt": "Pusty"}', encoding="utf-8")

    stan = AktywnyProjektSkrotu(plik)

    assert stan.przywroc(wyniki) is not None
    assert stan.aktualny() is None


@pytest.mark.parametrize(
    "zawartosc",
    ["to nie jest json", "[1, 2, 3]", '{"wersja_schematu": 99, "aktywny_projekt": "X"}'],
)
def test_uszkodzony_albo_nowszy_plik_stanu_daje_komunikat_a_nie_blad(
    tmp_path: Path, zawartosc: str
) -> None:
    plik = tmp_path / NAZWA_PLIKU_STANU_SKROTU
    plik.write_text(zawartosc, encoding="utf-8")
    wyniki = tmp_path / "wyniki"
    _utworz_projekt_z_checkpointem(wyniki, "X")

    stan = AktywnyProjektSkrotu(plik)
    komunikat = stan.przywroc(wyniki)

    assert stan.aktualny() is None
    assert komunikat is not None and "Ustaw" in komunikat


def test_brak_pliku_stanu_nie_daje_komunikatu(tmp_path: Path) -> None:
    stan = AktywnyProjektSkrotu(tmp_path / NAZWA_PLIKU_STANU_SKROTU)

    assert stan.przywroc(tmp_path) is None
    assert stan.aktualny() is None


def test_nazwa_zapamietana_z_niedozwolonym_znakiem_nie_wywraca_przywracania(
    tmp_path: Path,
) -> None:
    plik = tmp_path / NAZWA_PLIKU_STANU_SKROTU
    plik.write_text('{"wersja_schematu": 1, "aktywny_projekt": "CON"}', encoding="utf-8")

    stan = AktywnyProjektSkrotu(plik)

    assert stan.przywroc(tmp_path) is not None
    assert stan.aktualny() is None


# --- szkic tekstu ze skrótu -------------------------------------------------


def test_dolacz_do_szkicu_pusty_szkic_konczy_sie_nowym_wierszem() -> None:
    assert dolacz_do_szkicu("", "Pierwszy") == "Pierwszy\n"


def test_dolacz_do_szkicu_dopisuje_na_koncu_bez_zastepowania() -> None:
    assert dolacz_do_szkicu("Pierwszy\n", "Drugi") == "Pierwszy\nDrugi\n"


def test_dolacz_do_szkicu_dodaje_nowy_wiersz_gdy_szkic_go_nie_ma_na_koncu() -> None:
    assert dolacz_do_szkicu("Wpisane ręcznie", "Drugi") == "Wpisane ręcznie\nDrugi\n"


def test_szkic_jest_osobny_dla_kazdego_projektu() -> None:
    szkic = SzkicTekstuSkrotu()
    szkic.dopisz("A", "tekst a")
    szkic.dopisz("B", "tekst b")
    szkic.dopisz("A", "drugi a")

    assert szkic.pobierz("A").tekst == "tekst a\ndrugi a\n"
    assert szkic.pobierz("B").tekst == "tekst b\n"
    assert szkic.pobierz("C") == StanSzkicu("", 0)


def test_wersja_szkicu_rosnie_przy_dopisaniu_i_wyczyszczeniu() -> None:
    szkic = SzkicTekstuSkrotu()
    szkic.dopisz("A", "x")
    szkic.dopisz("A", "y")
    assert szkic.pobierz("A").wersja == 2

    szkic.wyczysc("A")

    stan = szkic.pobierz("A")
    assert stan.tekst == ""
    assert stan.wersja == 3


def test_wyczyszczenie_pustego_szkicu_nie_zmienia_wersji() -> None:
    szkic = SzkicTekstuSkrotu()

    szkic.wyczysc("A")

    assert szkic.pobierz("A").wersja == 0


def test_szkic_nie_przekracza_limitu_znakow() -> None:
    szkic = SzkicTekstuSkrotu(limit_znakow=20)
    assert szkic.dopisz("A", "dziesięć zn") is True

    assert szkic.dopisz("A", "to się już nie zmieści") is False
    assert szkic.pobierz("A").tekst == "dziesięć zn\n"
