"""Testy przyjmowania list adresów i podsumowania pokazywanego przed pobraniem."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.ingestion.lista_url import (
    opis_podsumowania,
    wczytaj_liste_z_pliku,
    zbierz_adresy,
)

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_pojedynczy_adres_jest_przyjmowany() -> None:
    podsumowanie = zbierz_adresy("https://przyklad.pl/artykul")
    assert podsumowanie.liczba_poprawnych == 1
    assert podsumowanie.adresy[0].podany == "https://przyklad.pl/artykul"


def test_wiele_adresow_rozdzielonych_spacjami_w_jednym_wierszu() -> None:
    podsumowanie = zbierz_adresy("https://przyklad.pl/a https://przyklad.pl/b")
    assert podsumowanie.liczba_poprawnych == 2


def test_wiele_adresow_w_osobnych_wierszach() -> None:
    podsumowanie = zbierz_adresy("https://przyklad.pl/a\nhttps://przyklad.pl/b\n")
    assert podsumowanie.liczba_poprawnych == 2


def test_duplikat_jest_wykrywany_po_postaci_kanonicznej() -> None:
    tekst = (
        "https://przyklad.pl/artykul?id=1\n"
        "https://przyklad.pl/artykul?id=1&utm_source=newsletter\n"
        "HTTPS://Przyklad.pl/artykul?id=1\n"
    )
    podsumowanie = zbierz_adresy(tekst)

    assert podsumowanie.liczba_poprawnych == 1
    assert podsumowanie.liczba_duplikatow == 2
    assert podsumowanie.adresy[0].podany == "https://przyklad.pl/artykul?id=1"


def test_wpis_ktory_nie_jest_adresem_trafia_do_odrzuconych_z_powodem() -> None:
    podsumowanie = zbierz_adresy("to nie jest adres\nhttps://przyklad.pl/a\n")

    assert podsumowanie.liczba_poprawnych == 1
    assert podsumowanie.liczba_odrzuconych == 1
    assert podsumowanie.odrzucone[0].wartosc == "to nie jest adres"
    assert podsumowanie.odrzucone[0].powod


def test_komentarz_nie_jest_liczony_jako_wpis() -> None:
    podsumowanie = zbierz_adresy("# lista artykułów\nhttps://przyklad.pl/a\n")
    assert podsumowanie.liczba_wykrytych == 1
    assert podsumowanie.liczba_poprawnych == 1


def test_pusty_tekst_daje_puste_podsumowanie() -> None:
    podsumowanie = zbierz_adresy("   \n\n")
    assert podsumowanie.liczba_wykrytych == 0
    assert podsumowanie.adresy == ()


def test_plik_z_danymi_testowymi_daje_spodziewany_rozklad() -> None:
    podsumowanie = wczytaj_liste_z_pliku(KATALOG_DANYCH / "lista_url.txt")

    assert podsumowanie.liczba_poprawnych == 4
    assert podsumowanie.liczba_duplikatow == 2
    assert podsumowanie.liczba_odrzuconych == 2
    assert podsumowanie.liczba_wykrytych == 8


def test_brak_pliku_listy_konczy_sie_bledem_trwalym(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="nie istnieje"):
        wczytaj_liste_z_pliku(tmp_path / "nie_ma.txt")


def test_katalog_zamiast_pliku_listy_konczy_sie_bledem_trwalym(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="zwykłego pliku"):
        wczytaj_liste_z_pliku(tmp_path)


def test_opis_podsumowania_jest_czytelny_liniowo() -> None:
    podsumowanie = wczytaj_liste_z_pliku(KATALOG_DANYCH / "lista_url.txt")
    opis = opis_podsumowania(podsumowanie)

    assert "Wykryte adresy: 8" in opis
    assert "Adresy poprawne: 4" in opis
    assert "Duplikaty pominięte: 2" in opis
    assert "Wpisy odrzucone: 2" in opis
    assert "|" not in opis
    assert "\t" not in opis


def test_dodatkowy_parametr_sledzacy_wplywa_na_wykrywanie_duplikatow() -> None:
    tekst = "https://przyklad.pl/a?znacznik=1\nhttps://przyklad.pl/a?znacznik=2\n"

    assert zbierz_adresy(tekst).liczba_poprawnych == 2
    assert zbierz_adresy(tekst, ["znacznik"]).liczba_poprawnych == 1


def test_wiersz_prozy_jest_odrzucany_jako_jeden_wpis() -> None:
    podsumowanie = zbierz_adresy("Kilka słów, które nie są adresem.\n")
    assert podsumowanie.liczba_odrzuconych == 1
    assert podsumowanie.odrzucone[0].wartosc == "Kilka słów, które nie są adresem."


def test_wiersz_mieszany_dzieli_sie_na_fragmenty() -> None:
    podsumowanie = zbierz_adresy("zobacz https://przyklad.pl/a oraz bzdura\n")
    assert podsumowanie.liczba_poprawnych == 1
    assert podsumowanie.liczba_odrzuconych == 3
