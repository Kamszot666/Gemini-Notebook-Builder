"""Testy czystej logiki rozpoznania źródła z globalnego skrótu.

Moduł `gnb.hotkeys.rozpoznanie` nie zależy od Windows, więc te testy budują
`InformacjeOOknie` ręcznie i uruchamiają się na każdym systemie, zgodnie
z sekcją piątą CLAUDE.md.
"""

from __future__ import annotations

from pathlib import Path

from gnb.hotkeys.model import InformacjeOOknie, TypDodania
from gnb.hotkeys.rozpoznanie import PorazkaRozpoznania, rozpoznaj


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
