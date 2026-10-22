"""Testy czystej logiki rozpoznania źródła z globalnego skrótu.

Moduł `gnb.hotkeys.rozpoznanie` nie zależy od Windows, więc te testy budują
`InformacjeOOknie` ręcznie i uruchamiają się na każdym systemie, zgodnie
z sekcją piątą CLAUDE.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.hotkeys.model import DodanieZeSkrotu, InformacjeOOknie, RodzajZaznaczenia, TypDodania
from gnb.hotkeys.rozpoznanie import (
    KOMUNIKAT_ADRES_INTERFEJSU,
    PorazkaRozpoznania,
    czy_adres_interfejsu,
    rozpoznaj,
    sklasyfikuj_zaznaczenie,
)


def _okno(*, nazwa_procesu: str = "", nazwa_klasy: str = "", tytul: str = "") -> InformacjeOOknie:
    return InformacjeOOknie(
        uchwyt=1, tytul=tytul, nazwa_klasy=nazwa_klasy, nazwa_procesu=nazwa_procesu
    )


def test_pasek_adresu_nieodczytany_daje_porazke_inna_niz_pusty_pasek() -> None:
    """`None` i pusty napis to dwa różne, celowo rozróżnione wyniki."""
    okno = _okno(nazwa_procesu="chrome", tytul="Strona testowa")

    wynik_brak_odczytu = rozpoznaj(okno, None, [])
    wynik_pusty = rozpoznaj(okno, "", [])

    assert isinstance(wynik_brak_odczytu, PorazkaRozpoznania)
    assert "nie udało się odczytać" in wynik_brak_odczytu.powod.lower()
    assert isinstance(wynik_pusty, PorazkaRozpoznania)
    assert "pusty" in wynik_pusty.powod.lower()
    assert wynik_brak_odczytu.powod != wynik_pusty.powod


def test_pasek_adresu_ze_schematem_zostaje_bez_zmian() -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Przykład")
    wynik = rozpoznaj(okno, "http://przyklad.pl/artykul", [])

    assert wynik.typ is TypDodania.ADRES  # type: ignore[union-attr]
    assert wynik.adres == "http://przyklad.pl/artykul"  # type: ignore[union-attr]


def test_pasek_adresu_bez_schematu_dostaje_https() -> None:
    okno = _okno(nazwa_procesu="firefox", tytul="Przykład")
    wynik = rozpoznaj(okno, "przyklad.pl/artykul", [])

    assert wynik.adres == "https://przyklad.pl/artykul"  # type: ignore[union-attr]


def test_pasek_adresu_ze_spacjami_jest_przycinany() -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Przykład")
    wynik = rozpoznaj(okno, "   przyklad.pl  ", [])

    assert wynik.adres == "https://przyklad.pl"  # type: ignore[union-attr]


def test_tekst_wyszukiwania_bez_kropki_w_pasku_adresu_daje_porazke() -> None:
    """Wpisywane hasło wyszukiwania, jeszcze bez przejścia na stronę wyników,
    nie może zostać po cichu potraktowane jako adres."""
    okno = _okno(nazwa_procesu="chrome", tytul="Nowa karta")
    wynik = rozpoznaj(okno, "jak naprawić drukarkę", [])

    assert isinstance(wynik, PorazkaRozpoznania)
    assert "nie wygląda na adres" in wynik.powod


def test_tekst_wyszukiwania_z_dwukropkiem_w_pasku_adresu_daje_porazke() -> None:
    okno = _okno(nazwa_procesu="firefox", tytul="Nowa karta")
    wynik = rozpoznaj(okno, "wyszukaj: najlepsza kawa w Krakowie", [])

    assert isinstance(wynik, PorazkaRozpoznania)
    assert "nie wygląda na adres" in wynik.powod


def test_opis_adresu_uzywa_tytulu_okna_gdy_dostepny() -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Tytuł strony")
    wynik = rozpoznaj(okno, "przyklad.pl", [])

    assert wynik.opis == "Tytuł strony"  # type: ignore[union-attr]


def test_eksplorator_bez_zaznaczenia_daje_porazke() -> None:
    okno = _okno(nazwa_klasy="CabinetWClass")
    wynik = rozpoznaj(okno, None, [])

    assert isinstance(wynik, PorazkaRozpoznania)
    assert "bez zaznaczenia" in wynik.powod


def test_eksplorator_z_jednym_plikiem() -> None:
    okno = _okno(nazwa_klasy="CabinetWClass")
    plik = Path("C:/Dane/dokument.txt")
    wynik = rozpoznaj(okno, None, [plik])

    assert wynik.typ is TypDodania.PLIKI  # type: ignore[union-attr]
    assert wynik.opis == "dokument.txt"  # type: ignore[union-attr]
    assert wynik.pliki == (plik,)  # type: ignore[union-attr]


def test_eksplorator_z_wieloma_plikami_liczy_pozostale() -> None:
    okno = _okno(nazwa_klasy="CabinetWClass")
    pliki = [Path("a.txt"), Path("b.txt"), Path("c.txt")]
    wynik = rozpoznaj(okno, None, pliki)

    assert wynik.opis == "a.txt i 2 więcej"  # type: ignore[union-attr]
    assert wynik.pliki == tuple(pliki)  # type: ignore[union-attr]


def test_pulpit_daje_czytelna_porazke() -> None:
    for klasa in ("Progman", "WorkerW", "Shell_TrayWnd"):
        wynik = rozpoznaj(_okno(nazwa_procesu="explorer", nazwa_klasy=klasa), None, [])
        assert isinstance(wynik, PorazkaRozpoznania)
        assert wynik.powod == "Aktywne okno to pulpit. Nic nie dodano."


def test_nierozpoznany_program_nazywa_go_po_procesie() -> None:
    okno = _okno(nazwa_procesu="notepad", nazwa_klasy="Notepad")
    wynik = rozpoznaj(okno, None, [])

    assert isinstance(wynik, PorazkaRozpoznania)
    assert "notepad" in wynik.powod


def test_nierozpoznany_program_bez_nazwy_procesu_mowi_nieznany() -> None:
    okno = _okno(nazwa_procesu="", nazwa_klasy="JakasKlasa")
    wynik = rozpoznaj(okno, None, [])

    assert isinstance(wynik, PorazkaRozpoznania)
    assert "nieznany" in wynik.powod


# --- zaznaczony tekst (etap piętnasty, część D2) -----------------------------


def test_klasyfikacja_pustego_zaznaczenia_zwraca_nic() -> None:
    assert sklasyfikuj_zaznaczenie("") is None
    assert sklasyfikuj_zaznaczenie(" \r\n\t  \n") is None


def test_klasyfikacja_jednego_adresu() -> None:
    wynik = sklasyfikuj_zaznaczenie("  https://przyklad.pl/artykul \r\n")

    assert wynik is not None
    assert wynik.rodzaj is RodzajZaznaczenia.ADRESY
    assert wynik.adresy == ("https://przyklad.pl/artykul",)


def test_klasyfikacja_kilku_adresow_w_osobnych_wierszach_bez_powtorzen() -> None:
    wynik = sklasyfikuj_zaznaczenie(
        "https://a.example/x\r\n\r\nhttp://b.example/y\nhttps://a.example/x\n"
    )

    assert wynik is not None
    assert wynik.rodzaj is RodzajZaznaczenia.ADRESY
    assert wynik.adresy == ("https://a.example/x", "http://b.example/y")


@pytest.mark.parametrize(
    "tekst",
    [
        "Zwykłe zdanie bez adresu.",
        "https://a.example/x i jeszcze słowo",
        "https://a.example/x\nZwykłe zdanie.",
        "przyklad.pl/bez-schematu",
        "ftp://serwer.example/plik",
    ],
)
def test_klasyfikacja_wszystkiego_innego_niz_same_adresy_to_zwykly_tekst(tekst: str) -> None:
    wynik = sklasyfikuj_zaznaczenie(tekst)

    assert wynik is not None
    assert wynik.rodzaj is RodzajZaznaczenia.TEKST
    assert wynik.tekst == tekst.strip()


def test_klasyfikacja_tekstu_ujednolica_konce_wierszy() -> None:
    wynik = sklasyfikuj_zaznaczenie("Pierwszy\r\nDrugi\rTrzeci")

    assert wynik is not None
    assert wynik.tekst == "Pierwszy\nDrugi\nTrzeci"


def test_zaznaczony_zwykly_tekst_w_przegladarce_jest_tekstem_nie_zrodlem() -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")

    wynik = rozpoznaj(okno, "przyklad.pl", [], zaznaczony_tekst="Zaznaczone zdanie.")

    assert isinstance(wynik, DodanieZeSkrotu)
    assert wynik.typ is TypDodania.TEKST
    assert wynik.tekst == "Zaznaczone zdanie."


def test_zaznaczone_adresy_w_przegladarce_sa_zrodlami() -> None:
    okno = _okno(nazwa_procesu="firefox", tytul="Strona")

    wynik = rozpoznaj(
        okno, "przyklad.pl", [], zaznaczony_tekst="https://a.example/x\nhttps://b.example/y"
    )

    assert isinstance(wynik, DodanieZeSkrotu)
    assert wynik.typ is TypDodania.ADRESY_Z_ZAZNACZENIA
    assert wynik.adresy == ("https://a.example/x", "https://b.example/y")


@pytest.mark.parametrize("zaznaczenie", [None, "", "   \n  "])
def test_bez_zaznaczenia_skrot_bierze_adres_z_paska_adresu(zaznaczenie: str | None) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")

    wynik = rozpoznaj(okno, "przyklad.pl/artykul", [], zaznaczony_tekst=zaznaczenie)

    assert isinstance(wynik, DodanieZeSkrotu)
    assert wynik.typ is TypDodania.ADRES
    assert wynik.adres == "https://przyklad.pl/artykul"


def test_zaznaczenie_nie_dotyczy_eksploratora() -> None:
    okno = _okno(nazwa_klasy="CabinetWClass")

    wynik = rozpoznaj(okno, None, [], zaznaczony_tekst="Cokolwiek")

    assert isinstance(wynik, PorazkaRozpoznania)
    assert "bez zaznaczenia" in wynik.powod


# --- adres samego interfejsu (część D3) --------------------------------------


@pytest.mark.parametrize(
    "adres",
    [
        "https://127.0.0.1:8765/",
        "http://127.0.0.1:8765/projekt/X",
        "http://127.0.0.1/",
        "http://localhost:8765/",
        "https://LOCALHOST/",
        "http://[::1]:8765/",
        "http://127.0.0.2:9000/",
        "http://127.0.0.1:1/",
        "http://localhost./",
        "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0:8765/",
        "http://[::ffff:0.0.0.0]:8765/",
    ],
)
def test_adresy_petli_zwrotnej_sa_adresami_interfejsu(adres: str) -> None:
    assert czy_adres_interfejsu(adres, "127.0.0.1", 8765) is True


def test_adres_i_port_nasluchu_z_konfiguracji_jest_adresem_interfejsu() -> None:
    assert czy_adres_interfejsu("http://moj-host.example:7000/", "moj-host.example", 7000)
    assert not czy_adres_interfejsu("http://moj-host.example:7001/", "moj-host.example", 7000)
    assert czy_adres_interfejsu("http://moj-host.example/", "moj-host.example", 80)
    assert czy_adres_interfejsu("https://moj-host.example/", "moj-host.example", 443)


@pytest.mark.parametrize(
    "adres", ["https://przyklad.pl/", "http://example.com:8765/", "https://127.0.0.1.example.pl/"]
)
def test_zwykle_adresy_nie_sa_adresami_interfejsu(adres: str) -> None:
    assert czy_adres_interfejsu(adres, "127.0.0.1", 8765) is False


def test_pasek_adresu_z_adresem_interfejsu_gra_porazke_z_dokladnym_komunikatem() -> None:
    """Odtwarza log z 1 października: pasek chowa schemat, skrót dopisuje https."""
    okno = _okno(nazwa_procesu="chrome", tytul="Gemini Notebook Builder")

    wynik = rozpoznaj(okno, "127.0.0.1:8765", [], port_nasluchu=8765)

    assert isinstance(wynik, PorazkaRozpoznania)
    assert wynik.powod == (
        "To jest adres interfejsu Gemini Notebook Builder, nie dodano go jako źródła."
    )


def test_zaznaczony_adres_interfejsu_jest_odrzucany() -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")

    wynik = rozpoznaj(okno, "przyklad.pl", [], zaznaczony_tekst="http://127.0.0.1:8765/projekt/A")

    assert isinstance(wynik, PorazkaRozpoznania)
    assert wynik.powod == KOMUNIKAT_ADRES_INTERFEJSU


def test_z_zaznaczonych_adresow_przechodza_tylko_te_spoza_interfejsu() -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")

    wynik = rozpoznaj(
        okno,
        None,
        [],
        zaznaczony_tekst="https://a.example/x\nhttp://localhost:8765/\n",
        port_nasluchu=8765,
    )

    assert isinstance(wynik, DodanieZeSkrotu)
    assert wynik.adresy == ("https://a.example/x",)
    assert wynik.liczba_pominietych_adresow_interfejsu == 1
