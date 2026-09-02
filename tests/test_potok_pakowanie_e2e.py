"""Test end-to-end etapu szóstego: pakowanie, grupowanie i podział w pełnym potoku.

Sprawdza cztery sytuacje: łączenie małych źródeł jednej grupy w jeden plik bez
utraty treści, podział grupy zbyt licznej na kolejne pliki, zachowanie decyzji po
wznowieniu pracy oraz nagłówek metadanych przed treścią każdego fragmentu.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_tekst
from gnb.potok import przetworz_projekt


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 2, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _tresc_bez_naglowka(tekst: str) -> str:
    return tekst.partition("\n\n")[2]


def _pozycje_grupy(nazwa_grupy: str, tresci: list[str]) -> list[PozycjaWejsciowa]:
    moment = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    return [przyjmij_tekst(tresc, moment, grupa=nazwa_grupy) for tresc in tresci]


def test_male_zrodla_grupy_lacza_sie_w_jeden_plik_bez_utraty_tresci(tmp_path: Path) -> None:
    tresci = [
        "Notatka pierwsza mówi o porządkowaniu materiałów źródłowych przed importem.",
        "Notatka druga przypomina o sprawdzeniu dat publikacji artykułów.",
        "Notatka trzecia dotyczy rozróżniania oryginału od przedruku.",
    ]

    wynik = przetworz_projekt(
        _pozycje_grupy("Baza wiedzy", tresci),
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test łączenia grupy",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 3
    assert wynik.liczba_bledow == 0

    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 1
    tresc_pliku = pliki_txt[0].read_text(encoding="utf-8")
    for fragment in tresci:
        assert fragment in tresc_pliku
    # Nagłówek metadanych przed treścią każdego fragmentu.
    assert tresc_pliku.count("Identyfikator źródła: ") == 3
    assert tresc_pliku.count("Kolejny fragment tego pliku:") == 2

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert all(zrodlo["status"] == "spakowane" for zrodlo in manifest["zrodla"])
    assert all(zrodlo["grupa_pakowania"] == "Baza wiedzy" for zrodlo in manifest["zrodla"])
    (wpis_wyniku,) = manifest["wyniki"]
    assert wpis_wyniku["liczba_zrodel"] == 3
    assert len(wpis_wyniku["identyfikatory_zrodel"]) == 3

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba źródeł poprawnych: 3" in raport
    assert "Liczba plików TXT: 1" in raport

    log_wazne = (wynik.katalog_projektu / "logi" / "log_wazne.txt").read_text(encoding="utf-8")
    assert "Grupa źródeł spakowana do wspólnego pliku:" in log_wazne


def test_grupa_zbyt_liczna_dzieli_sie_na_kolejne_pliki(tmp_path: Path) -> None:
    tresci = [
        "Rozliczenie roczne wymaga zebrania wszystkich formularzy o dochodach.",
        "Zaliczki kwartalne opłaca się do dwudziestego dnia miesiąca następnego.",
        "Ulga na dziecko przysługuje rodzicom sprawującym opiekę przez cały rok.",
        "Amortyzacja środka trwałego zależy od przyjętej stawki i metody odpisów.",
        "Faktura korygująca zmienia podstawę opodatkowania w okresie jej wystawienia.",
        "Kasa fiskalna jest obowiązkowa po przekroczeniu progu obrotu detalicznego.",
    ]

    wynik = przetworz_projekt(
        _pozycje_grupy("Duża grupa", tresci),
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki", bezpieczny_limit_slow=20),
        nazwa_projektu="Test dużej grupy",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 6
    assert wynik.liczba_bledow == 0
    pliki_txt = sorted((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) >= 2
    for plik in pliki_txt:
        assert "_czesc_" in plik.name
        assert "Plik grupy „Duża grupa”, część" in plik.read_text(encoding="utf-8")

    slowa_wynikow = [
        slowo
        for plik in pliki_txt
        for slowo in _tresc_bez_naglowka(plik.read_text("utf-8")).split()
    ]
    for tresc in tresci:
        for slowo in tresc.split():
            assert slowo in slowa_wynikow


def test_wznowienie_grupy_nie_zmienia_plikow(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki")
    pozycje = _pozycje_grupy("Grupa", ["Notatka A krótka.", "Notatka B krótka.", "Notatka C."])

    pierwsze = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test wznowienia grupy", zegar=_zegar_krokowy()
    )
    pliki_pierwsze = sorted(
        (p.name, p.read_bytes()) for p in (pierwsze.katalog_projektu / "pliki_wynikowe").iterdir()
    )
    manifest_pierwszy = json.loads(pierwsze.sciezka_manifestu.read_text(encoding="utf-8"))

    drugie = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test wznowienia grupy", zegar=_zegar_krokowy()
    )
    pliki_drugie = sorted(
        (p.name, p.read_bytes()) for p in (drugie.katalog_projektu / "pliki_wynikowe").iterdir()
    )
    manifest_drugi = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))

    assert drugie.wznowiono is True
    assert pliki_drugie == pliki_pierwsze
    assert manifest_drugi["wyniki"] == manifest_pierwszy["wyniki"]


def test_zrodlo_bez_grupy_zostaje_osobnym_plikiem_obok_grupy(tmp_path: Path) -> None:
    moment = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    pozycje = [
        przyjmij_tekst("Notatka w grupie pierwsza.", moment, grupa="Wspólny temat"),
        przyjmij_tekst("Notatka w grupie druga.", moment, grupa="Wspólny temat"),
        przyjmij_tekst("Notatka zupełnie osobna, poza jakąkolwiek grupą.", moment),
    ]

    wynik = przetworz_projekt(
        pozycje,
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test grupy i osobnego",
        zegar=_zegar_krokowy(),
    )

    pliki_txt = sorted((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 2

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    liczby_zrodel = sorted(wpis["liczba_zrodel"] for wpis in manifest["wyniki"])
    assert liczby_zrodel == [1, 2]
