"""Testy wspólnej pamięci podręcznej pobranych zasobów."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly
from gnb.persistence.cache import (
    WERSJA_SCHEMATU,
    PamiecPodreczna,
    WpisCache,
    otworz,
    wyczysc_pamiec_podreczna,
)

_MOMENT = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)


def _wpis(klucz: str = "https://przyklad.pl/a", pobrano: datetime = _MOMENT) -> WpisCache:
    return WpisCache(
        klucz=klucz,
        adres_koncowy=klucz,
        kod_odpowiedzi=200,
        typ_zawartosci="text/html",
        deklarowane_kodowanie="utf-8",
        etag='W/"abc"',
        last_modified="Wed, 26 Aug 2026 08:00:00 GMT",
        tresc=b"<html><body>Tre\xc5\x9b\xc4\x87</body></html>",
        pobrano=pobrano,
    )


def test_zapis_i_odczyt_zachowuje_wszystkie_pola(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        pamiec.zapisz(_wpis())
        odczytany = pamiec.odczytaj("https://przyklad.pl/a")

    assert odczytany == _wpis()


def test_odczyt_nieznanego_klucza_daje_wartosc_pusta(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        assert pamiec.odczytaj("https://przyklad.pl/nie-ma") is None


def test_ponowny_zapis_tego_samego_klucza_nadpisuje_wpis(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        pamiec.zapisz(_wpis())
        nowszy = replace(_wpis(), tresc=b"nowa")
        pamiec.zapisz(nowszy)

        assert pamiec.liczba_wpisow() == 1
        wpis = pamiec.odczytaj("https://przyklad.pl/a")
        assert wpis is not None
        assert wpis.tresc == b"nowa"


def test_swiezosc_wpisu_zalezy_od_maksymalnego_wieku() -> None:
    wpis = _wpis()
    assert wpis.czy_swiezy(30, _MOMENT + timedelta(days=29)) is True
    assert wpis.czy_swiezy(30, _MOMENT + timedelta(days=31)) is False


def test_odswiezenie_czasu_pobrania_przedluza_swiezosc(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        pamiec.zapisz(_wpis())
        pamiec.odswiez_czas_pobrania("https://przyklad.pl/a", _MOMENT + timedelta(days=40))

        wpis = pamiec.odczytaj("https://przyklad.pl/a")
        assert wpis is not None
        assert wpis.pobrano == _MOMENT + timedelta(days=40)


def test_usuwanie_przeterminowanych_zostawia_swieze(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        pamiec.zapisz(_wpis("https://przyklad.pl/stary", _MOMENT - timedelta(days=90)))
        pamiec.zapisz(_wpis("https://przyklad.pl/swiezy", _MOMENT))

        usuniete = pamiec.usun_przeterminowane(30, _MOMENT)

        assert usuniete == 1
        assert pamiec.odczytaj("https://przyklad.pl/stary") is None
        assert pamiec.odczytaj("https://przyklad.pl/swiezy") is not None


def test_czyszczenie_usuwa_wszystko_i_zwraca_liczbe(tmp_path: Path) -> None:
    sciezka = tmp_path / "cache.sqlite3"
    with otworz(sciezka) as pamiec:
        pamiec.zapisz(_wpis("https://przyklad.pl/a"))
        pamiec.zapisz(_wpis("https://przyklad.pl/b"))

    assert wyczysc_pamiec_podreczna(sciezka) == 2

    with otworz(sciezka) as pamiec:
        assert pamiec.liczba_wpisow() == 0


def test_czyszczenie_nieistniejacego_pliku_nie_jest_bledem(tmp_path: Path) -> None:
    assert wyczysc_pamiec_podreczna(tmp_path / "nie_ma.sqlite3") == 0


def test_tryb_wal_jest_wlaczony(tmp_path: Path) -> None:
    sciezka = tmp_path / "cache.sqlite3"
    with otworz(sciezka):
        pass

    polaczenie = sqlite3.connect(sciezka)
    try:
        tryb = polaczenie.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        polaczenie.close()
    assert tryb.lower() == "wal"


def test_wersja_schematu_jest_zapisana_w_bazie(tmp_path: Path) -> None:
    sciezka = tmp_path / "cache.sqlite3"
    with otworz(sciezka):
        pass

    polaczenie = sqlite3.connect(sciezka)
    try:
        numer = polaczenie.execute("SELECT numer FROM wersja_schematu").fetchone()[0]
    finally:
        polaczenie.close()
    assert numer == WERSJA_SCHEMATU


def test_niezgodna_wersja_schematu_odrzuca_stara_zawartosc(tmp_path: Path) -> None:
    sciezka = tmp_path / "cache.sqlite3"
    with otworz(sciezka) as pamiec:
        pamiec.zapisz(_wpis())

    polaczenie = sqlite3.connect(sciezka)
    try:
        polaczenie.execute("UPDATE wersja_schematu SET numer = ?", (WERSJA_SCHEMATU + 1,))
        polaczenie.commit()
    finally:
        polaczenie.close()

    with otworz(sciezka) as pamiec:
        assert pamiec.liczba_wpisow() == 0
        assert pamiec.odczytaj("https://przyklad.pl/a") is None


class _PolaczenieZajete:
    """Podstawka udająca połączenie, które zawsze zgłasza zajętość bazy."""

    def execute(self, *_argumenty: object, **_nazwane: object) -> None:
        raise sqlite3.OperationalError("database is locked")

    def close(self) -> None:
        return None


def test_zajeta_baza_jest_bledem_przejsciowym(tmp_path: Path) -> None:
    pamiec = otworz(tmp_path / "cache.sqlite3")
    pamiec._polaczenie.close()
    pamiec._polaczenie = _PolaczenieZajete()  # type: ignore[assignment]

    with pytest.raises(BladPrzejsciowy, match="zajęta"):
        pamiec.odczytaj("https://przyklad.pl/a")


def test_uszkodzony_plik_jest_bledem_trwalym(tmp_path: Path) -> None:
    sciezka = tmp_path / "cache.sqlite3"
    sciezka.write_bytes(b"to nie jest baza danych SQLite, tylko przypadkowe bajty")

    with pytest.raises(BladTrwaly):
        PamiecPodreczna(sciezka)
