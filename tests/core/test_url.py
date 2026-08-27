"""Testy walidacji adresów oraz ich postaci kanonicznej i pobierania."""

from __future__ import annotations

import pytest

from gnb.core.url import (
    adres_kanoniczny,
    adres_pobierania,
    bez_danych_logowania,
    czy_parametr_sledzacy,
    czy_wyglada_na_adres,
    waliduj_adres,
)
from gnb.core.wyjatki import BladTrwaly


@pytest.mark.parametrize(
    "adres",
    [
        "",
        "   ",
        "przykład.pl/artykul",
        "ftp://przyklad.pl/plik.txt",
        "file:///C:/dokument.txt",
        "https://",
        "https://localhost-bez-kropki/artykul",
    ],
)
def test_niepoprawny_adres_konczy_sie_bledem_trwalym(adres: str) -> None:
    with pytest.raises(BladTrwaly):
        waliduj_adres(adres)


def test_poprawny_adres_przechodzi_walidacje_i_traci_biale_znaki() -> None:
    assert waliduj_adres("  https://przyklad.pl/artykul  ") == "https://przyklad.pl/artykul"


def test_czy_wyglada_na_adres_nie_zglasza_wyjatku() -> None:
    assert czy_wyglada_na_adres("https://przyklad.pl") is True
    assert czy_wyglada_na_adres("to nie jest adres") is False


def test_postac_kanoniczna_sprowadza_schemat_i_host_do_malych_liter() -> None:
    assert adres_kanoniczny("HTTPS://Przyklad.PL/Artykul") == "https://przyklad.pl/Artykul"


def test_postac_kanoniczna_usuwa_domyslny_port_a_zostawia_nietypowy() -> None:
    assert adres_kanoniczny("https://przyklad.pl:443/artykul") == "https://przyklad.pl/artykul"
    assert adres_kanoniczny("http://przyklad.pl:80/artykul") == "http://przyklad.pl/artykul"
    assert adres_kanoniczny("https://przyklad.pl:8443/a") == "https://przyklad.pl:8443/a"


def test_postac_kanoniczna_uzupelnia_pusta_sciezke() -> None:
    assert adres_kanoniczny("https://przyklad.pl") == adres_kanoniczny("https://przyklad.pl/")


def test_postac_kanoniczna_nie_usuwa_przedrostka_www() -> None:
    assert adres_kanoniczny("https://www.przyklad.pl/a") != adres_kanoniczny(
        "https://przyklad.pl/a"
    )


def test_postac_kanoniczna_usuwa_parametry_sledzace_a_zostawia_tresciowe() -> None:
    adres = "https://przyklad.pl/artykul?id=12&utm_source=newsletter&fbclid=abc&strona=2"
    assert adres_kanoniczny(adres) == "https://przyklad.pl/artykul?id=12&strona=2"


def test_postac_kanoniczna_sortuje_parametry_wiec_kolejnosc_nie_zmienia_klucza() -> None:
    pierwszy = adres_kanoniczny("https://przyklad.pl/a?b=2&a=1")
    drugi = adres_kanoniczny("https://przyklad.pl/a?a=1&b=2")
    assert pierwszy == drugi == "https://przyklad.pl/a?a=1&b=2"


def test_postac_kanoniczna_usuwa_zwykly_fragment() -> None:
    assert adres_kanoniczny("https://przyklad.pl/a#rozdzial-2") == "https://przyklad.pl/a"


def test_postac_kanoniczna_zachowuje_fragment_wskazujacy_tresc() -> None:
    assert (
        adres_kanoniczny("https://przyklad.pl/#!/artykul/12") == "https://przyklad.pl/#!/artykul/12"
    )
    assert adres_kanoniczny("https://przyklad.pl/#/wpis/7") == "https://przyklad.pl/#/wpis/7"


def test_adres_pobierania_zachowuje_kolejnosc_parametrow() -> None:
    adres = "https://przyklad.pl/a?b=2&utm_medium=mail&a=1"
    assert adres_pobierania(adres) == "https://przyklad.pl/a?b=2&a=1"


def test_dodatkowy_parametr_sledzacy_z_konfiguracji_jest_usuwany() -> None:
    adres = "https://przyklad.pl/a?id=3&nasz_znacznik=xyz"
    assert adres_kanoniczny(adres, ["nasz_znacznik"]) == "https://przyklad.pl/a?id=3"
    assert adres_kanoniczny(adres) == "https://przyklad.pl/a?id=3&nasz_znacznik=xyz"


@pytest.mark.parametrize(
    ("nazwa", "oczekiwane"),
    [
        ("utm_source", True),
        ("UTM_Campaign", True),
        ("fbclid", True),
        ("gclid", True),
        ("id", False),
        ("strona", False),
        ("p", False),
    ],
)
def test_rozpoznawanie_parametrow_sledzacych(nazwa: str, oczekiwane: bool) -> None:
    assert czy_parametr_sledzacy(nazwa) is oczekiwane


def test_pusty_zestaw_parametrow_nie_zostawia_znaku_zapytania() -> None:
    assert adres_kanoniczny("https://przyklad.pl/a?utm_source=x") == "https://przyklad.pl/a"


def test_postac_kanoniczna_nie_zawiera_danych_logowania() -> None:
    kanoniczny = adres_kanoniczny("https://uzytkownik:tajne@przyklad.pl/a")
    assert kanoniczny == "https://przyklad.pl/a"
    assert "tajne" not in kanoniczny


def test_adres_pobierania_zachowuje_dane_logowania() -> None:
    assert (
        adres_pobierania("https://uzytkownik:tajne@przyklad.pl/a")
        == "https://uzytkownik:tajne@przyklad.pl/a"
    )


def test_usuwanie_danych_logowania_z_dowolnego_adresu() -> None:
    assert (
        bez_danych_logowania("https://uzytkownik:tajne@przyklad.pl/a?b=1")
        == "https://przyklad.pl/a?b=1"
    )
    assert bez_danych_logowania("https://przyklad.pl/a") == "https://przyklad.pl/a"
