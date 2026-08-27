"""Testy asynchronicznego pobierania stron, prowadzone na sztucznym transporcie.

Żaden test w tym pliku nie korzysta z sieci ani nie czeka naprawdę. Transport
jest podstawiony przez `httpx.MockTransport`, a usypianie przez funkcję, która
tylko zapisuje żądany czas. Dzięki temu ponowienia, rosnący odstęp, odstęp
między żądaniami i zapytania warunkowe są sprawdzane deterministycznie.
"""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly
from gnb.ingestion.pobieranie import (
    OdpowiedzPobrania,
    Pobieracz,
    PominietePobranie,
    UstawieniaPobierania,
    Zadanie,
)
from gnb.persistence.cache import PamiecPodreczna, WpisCache, otworz

_MOMENT = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
_ADRES = "https://przyklad.pl/artykul"
_STRONA = b"<html><head><title>Test</title></head><body><p>Tresc</p></body></html>"


def _ustawienia(**nadpisania: object) -> UstawieniaPobierania:
    """Buduje ustawienia pobierania z krótkimi odstępami, wygodne w testach."""
    domyslne: dict[str, object] = {
        "nazwa_klienta": "GeminiNotebookBuilder/test",
        "limit_czasu_sekundy": 5.0,
        "liczba_ponowien": 2,
        "podstawa_odstepu_sekundy": 1.0,
        "maksymalny_odstep_sekundy": 10.0,
        "odstep_miedzy_zadaniami_sekundy": 0.5,
        "polaczenia_na_domene": 3,
        "respektuj_robots": False,
        "maksymalny_rozmiar_pobrania_mb": 1,
        "uzywaj_cache": False,
        "maksymalny_wiek_cache_dni": 30,
    }
    domyslne.update(nadpisania)
    return UstawieniaPobierania(**domyslne)  # type: ignore[arg-type]


class _Zegar:
    """Zegar monotoniczny sterowany ręcznie, wraz z usypiaczem, który tylko liczy czas."""

    def __init__(self) -> None:
        self.teraz = 0.0
        self.przespane: list[float] = []

    def __call__(self) -> float:
        return self.teraz

    async def uspij(self, sekundy: float) -> None:
        self.przespane.append(sekundy)
        self.teraz += sekundy


def _transport(obsluga: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(obsluga)


def _transport_stalej_odpowiedzi(**naglowki: str) -> httpx.MockTransport:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=_STRONA, headers={"content-type": "text/html; charset=utf-8", **naglowki}
        )

    return _transport(obsluga)


async def _pobierz(
    ustawienia: UstawieniaPobierania,
    transport: httpx.MockTransport,
    *,
    pamiec: PamiecPodreczna | None = None,
    zegar: _Zegar | None = None,
    adres: str = _ADRES,
    zegar_utc: Callable[[], datetime] | None = None,
) -> object:
    zegar = zegar if zegar is not None else _Zegar()
    async with Pobieracz(
        ustawienia,
        transport=transport,
        pamiec=pamiec,
        usypiacz=zegar.uspij,
        zegar_monotoniczny=zegar,
        zegar_utc=zegar_utc if zegar_utc is not None else (lambda: _MOMENT),
    ) as pobieracz:
        return await pobieracz.pobierz(Zadanie(adres_pobierania=adres, klucz_kanoniczny=adres))


def test_udane_pobranie_zwraca_tresc_i_dane_odpowiedzi() -> None:
    wynik = asyncio.run(_pobierz(_ustawienia(), _transport_stalej_odpowiedzi(etag='W/"abc"')))

    assert isinstance(wynik, OdpowiedzPobrania)
    assert wynik.tresc == _STRONA
    assert wynik.kod_odpowiedzi == 200
    assert wynik.adres_koncowy == _ADRES
    assert wynik.typ_zawartosci == "text/html"
    assert wynik.deklarowane_kodowanie == "utf-8"
    assert wynik.etag == 'W/"abc"'
    assert wynik.z_pamieci_podrecznej is False


def test_klient_przedstawia_sie_ustalona_nazwa() -> None:
    widziane: list[str] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        widziane.append(zadanie.headers["user-agent"])
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    asyncio.run(_pobierz(_ustawienia(), _transport(obsluga)))

    assert widziane == ["GeminiNotebookBuilder/test"]


def test_blad_serwera_jest_ponawiany_z_rosnacym_odstepem() -> None:
    proby: list[int] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        proby.append(1)
        if len(proby) < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    zegar = _Zegar()
    wynik = asyncio.run(_pobierz(_ustawienia(), _transport(obsluga), zegar=zegar))

    assert isinstance(wynik, OdpowiedzPobrania)
    assert len(proby) == 3
    # Pierwsze usypianie to odstęp między żądaniami do domeny, kolejne to
    # rosnący odstęp ponowień: jedna sekunda, potem dwie.
    assert zegar.przespane[0] == pytest.approx(1.0)
    assert zegar.przespane[1] == pytest.approx(2.0)


def test_wyczerpanie_ponowien_konczy_sie_bledem_przejsciowym() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(BladPrzejsciowy, match="500"):
        asyncio.run(_pobierz(_ustawienia(liczba_ponowien=1), _transport(obsluga)))


def test_odpowiedz_404_jest_bledem_trwalym_i_nie_jest_ponawiana() -> None:
    proby: list[int] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        proby.append(1)
        return httpx.Response(404)

    with pytest.raises(BladTrwaly, match="404"):
        asyncio.run(_pobierz(_ustawienia(), _transport(obsluga)))
    assert len(proby) == 1


def test_odpowiedz_429_respektuje_naglowek_retry_after() -> None:
    proby: list[int] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        proby.append(1)
        if len(proby) == 1:
            return httpx.Response(429, headers={"retry-after": "7"})
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    zegar = _Zegar()
    wynik = asyncio.run(_pobierz(_ustawienia(), _transport(obsluga), zegar=zegar))

    assert isinstance(wynik, OdpowiedzPobrania)
    assert 7.0 in zegar.przespane


def test_odstep_z_naglowka_jest_ograniczony_maksimum_z_konfiguracji() -> None:
    proby: list[int] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        proby.append(1)
        if len(proby) == 1:
            return httpx.Response(429, headers={"retry-after": "3600"})
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    zegar = _Zegar()
    asyncio.run(
        _pobierz(_ustawienia(maksymalny_odstep_sekundy=10.0), _transport(obsluga), zegar=zegar)
    )

    assert max(zegar.przespane) == pytest.approx(10.0)


def test_przekroczony_limit_czasu_jest_bledem_przejsciowym() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("czas minął", request=zadanie)

    with pytest.raises(BladPrzejsciowy, match="limit czasu"):
        asyncio.run(_pobierz(_ustawienia(liczba_ponowien=0), _transport(obsluga)))


def test_zerwane_polaczenie_jest_bledem_przejsciowym() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("brak połączenia", request=zadanie)

    with pytest.raises(BladPrzejsciowy, match="Błąd połączenia"):
        asyncio.run(_pobierz(_ustawienia(liczba_ponowien=0), _transport(obsluga)))


def test_zasob_inny_niz_html_jest_pomijany() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"})

    wynik = asyncio.run(_pobierz(_ustawienia(), _transport(obsluga)))

    assert isinstance(wynik, PominietePobranie)
    assert "application/pdf" in wynik.powod


def test_zasob_ponad_limit_rozmiaru_jest_pomijany() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"x" * (2 * 1024 * 1024), headers={"content-type": "text/html"}
        )

    wynik = asyncio.run(
        _pobierz(_ustawienia(maksymalny_rozmiar_pobrania_mb=1), _transport(obsluga))
    )

    assert isinstance(wynik, PominietePobranie)
    assert "limit pobrania" in wynik.powod


def test_zakaz_w_robots_konczy_sie_pominieciem() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /artykul")
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    wynik = asyncio.run(_pobierz(_ustawienia(respektuj_robots=True), _transport(obsluga)))

    assert isinstance(wynik, PominietePobranie)
    assert "robots.txt" in wynik.powod


def test_zgoda_w_robots_pozwala_pobrac() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /prywatne")
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    wynik = asyncio.run(_pobierz(_ustawienia(respektuj_robots=True), _transport(obsluga)))

    assert isinstance(wynik, OdpowiedzPobrania)


def test_brak_pliku_robots_oznacza_zgode() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    wynik = asyncio.run(_pobierz(_ustawienia(respektuj_robots=True), _transport(obsluga)))

    assert isinstance(wynik, OdpowiedzPobrania)


def test_odmowa_dostepu_do_robots_oznacza_zakaz() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == "/robots.txt":
            return httpx.Response(403)
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    wynik = asyncio.run(_pobierz(_ustawienia(respektuj_robots=True), _transport(obsluga)))

    assert isinstance(wynik, PominietePobranie)


def test_swiezy_wpis_pamieci_podrecznej_oszczedza_zadanie_sieciowe(tmp_path: Path) -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        raise AssertionError("świeży wpis nie może sięgać do sieci")

    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        pamiec.zapisz(
            WpisCache(
                klucz=_ADRES,
                adres_koncowy=_ADRES,
                kod_odpowiedzi=200,
                typ_zawartosci="text/html",
                deklarowane_kodowanie="utf-8",
                etag=None,
                last_modified=None,
                tresc=_STRONA,
                pobrano=_MOMENT,
            )
        )
        wynik = asyncio.run(
            _pobierz(
                _ustawienia(uzywaj_cache=True),
                _transport(obsluga),
                pamiec=pamiec,
                zegar_utc=lambda: _MOMENT + timedelta(days=1),
            )
        )

    assert isinstance(wynik, OdpowiedzPobrania)
    assert wynik.z_pamieci_podrecznej is True
    assert wynik.tresc == _STRONA


def test_nieswiezy_wpis_wysyla_zapytanie_warunkowe_a_304_potwierdza_tresc(tmp_path: Path) -> None:
    widziane: list[dict[str, str]] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        widziane.append(dict(zadanie.headers))
        return httpx.Response(304)

    pozniej = _MOMENT + timedelta(days=60)
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        pamiec.zapisz(
            WpisCache(
                klucz=_ADRES,
                adres_koncowy=_ADRES,
                kod_odpowiedzi=200,
                typ_zawartosci="text/html",
                deklarowane_kodowanie="utf-8",
                etag='W/"abc"',
                last_modified="Wed, 26 Aug 2026 08:00:00 GMT",
                tresc=_STRONA,
                pobrano=_MOMENT,
            )
        )
        wynik = asyncio.run(
            _pobierz(
                _ustawienia(uzywaj_cache=True),
                _transport(obsluga),
                pamiec=pamiec,
                zegar_utc=lambda: pozniej,
            )
        )
        odswiezony = pamiec.odczytaj(_ADRES)

    assert isinstance(wynik, OdpowiedzPobrania)
    assert wynik.tresc == _STRONA
    assert wynik.z_pamieci_podrecznej is True
    assert widziane[0]["if-none-match"] == 'W/"abc"'
    assert widziane[0]["if-modified-since"] == "Wed, 26 Aug 2026 08:00:00 GMT"
    assert odswiezony is not None
    assert odswiezony.pobrano == pozniej


def test_pobranie_zapisuje_wpis_w_pamieci_podrecznej(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        asyncio.run(
            _pobierz(
                _ustawienia(uzywaj_cache=True),
                _transport_stalej_odpowiedzi(etag='W/"nowy"'),
                pamiec=pamiec,
            )
        )
        wpis = pamiec.odczytaj(_ADRES)

    assert wpis is not None
    assert wpis.tresc == _STRONA
    assert wpis.etag == 'W/"nowy"'


def test_wylaczona_pamiec_podreczna_nie_zapisuje_niczego(tmp_path: Path) -> None:
    with otworz(tmp_path / "cache.sqlite3") as pamiec:
        asyncio.run(
            _pobierz(_ustawienia(uzywaj_cache=False), _transport_stalej_odpowiedzi(), pamiec=pamiec)
        )
        assert pamiec.liczba_wpisow() == 0


def test_pobieranie_wielu_adresow_zachowuje_kolejnosc_i_nie_przerywa_sie_na_bledzie() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == "/brak":
            return httpx.Response(404)
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    async def uruchom() -> list[object]:
        zegar = _Zegar()
        async with Pobieracz(
            _ustawienia(),
            transport=_transport(obsluga),
            usypiacz=zegar.uspij,
            zegar_monotoniczny=zegar,
            zegar_utc=lambda: _MOMENT,
        ) as pobieracz:
            zadania = [
                Zadanie("https://przyklad.pl/pierwszy", "https://przyklad.pl/pierwszy"),
                Zadanie("https://przyklad.pl/brak", "https://przyklad.pl/brak"),
                Zadanie("https://przyklad.pl/trzeci", "https://przyklad.pl/trzeci"),
            ]
            return list(await pobieracz.pobierz_wiele(zadania))

    wyniki = asyncio.run(uruchom())

    assert isinstance(wyniki[0], OdpowiedzPobrania)
    assert isinstance(wyniki[1], BladTrwaly)
    assert isinstance(wyniki[2], OdpowiedzPobrania)


def test_zadania_do_jednej_domeny_zachowuja_odstep() -> None:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_STRONA, headers={"content-type": "text/html"})

    async def uruchom() -> list[float]:
        zegar = _Zegar()
        async with Pobieracz(
            _ustawienia(odstep_miedzy_zadaniami_sekundy=2.0, polaczenia_na_domene=1),
            transport=_transport(obsluga),
            usypiacz=zegar.uspij,
            zegar_monotoniczny=zegar,
            zegar_utc=lambda: _MOMENT,
        ) as pobieracz:
            await pobieracz.pobierz_wiele(
                [
                    Zadanie("https://przyklad.pl/a", "https://przyklad.pl/a"),
                    Zadanie("https://przyklad.pl/b", "https://przyklad.pl/b"),
                ]
            )
        return zegar.przespane

    przespane = asyncio.run(uruchom())

    assert pytest.approx(2.0) == przespane[-1]


def test_blad_certyfikatu_jest_bledem_trwalym_i_nie_jest_ponawiany() -> None:
    proby: list[int] = []

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        proby.append(1)
        przyczyna = ssl.SSLCertVerificationError("certificate verify failed")
        blad = httpx.ConnectError("nie udało się nawiązać połączenia", request=zadanie)
        raise blad from przyczyna

    with pytest.raises(BladTrwaly, match="certyfikat"):
        asyncio.run(_pobierz(_ustawienia(liczba_ponowien=3), _transport(obsluga)))

    assert len(proby) == 1
