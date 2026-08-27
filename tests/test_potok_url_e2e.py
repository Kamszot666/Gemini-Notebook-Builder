"""Test end-to-end potoku dla adresów stron internetowych, bez sieci.

Transport HTTP jest podstawiony, więc cały przebieg — pobranie, ekstrakcja,
normalizacja, reguła formatu, zapis, manifest, checkpoint i raport — jest
sprawdzany deterministycznie i bez połączenia z internetem.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_url
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"
_ADRES_ARTYKULU = "https://przyklad.pl/artykul"
_MOMENT = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 8, 26, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _konfiguracja(tmp_path: Path, **nadpisania: object) -> Konfiguracja:
    """Konfiguracja testowa: bez pamięci podręcznej, bez robots, bez odstępów."""
    domyslne: dict[str, object] = {
        "katalog_wynikow": tmp_path / "wyniki",
        "sciezka_cache": tmp_path / "cache.sqlite3",
        "uzywaj_cache": False,
        "respektuj_robots": False,
        "odstep_miedzy_zadaniami_sekundy": 0.0,
        "liczba_ponowien": 0,
    }
    domyslne.update(nadpisania)
    return Konfiguracja(**domyslne)  # type: ignore[arg-type]


def _artykul() -> bytes:
    return (KATALOG_DANYCH / "artykul_oryginal.html").read_bytes()


class _Serwer:
    """Sztuczny serwer HTTP zliczający żądania, używany zamiast prawdziwej sieci."""

    def __init__(self, odpowiedzi: dict[str, httpx.Response] | None = None) -> None:
        self.zadania: list[str] = []
        self._odpowiedzi = odpowiedzi or {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._obsluz)

    def _obsluz(self, zadanie: httpx.Request) -> httpx.Response:
        sciezka = zadanie.url.path
        self.zadania.append(str(zadanie.url))
        if sciezka in self._odpowiedzi:
            return self._odpowiedzi[sciezka]
        if sciezka == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, content=_artykul(), headers={"content-type": "text/html; charset=utf-8"}
        )


def _pozycje(*adresy: str) -> list[PozycjaWejsciowa]:
    return [przyjmij_url(adres, _MOMENT) for adres in adresy]


def test_adres_przechodzi_caly_potok_i_daje_plik_wynikowy(tmp_path: Path) -> None:
    serwer = _Serwer()
    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test URL",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    assert wynik.liczba_przetworzonych == 1
    assert wynik.liczba_bledow == 0

    pliki = sorted(p.name for p in (wynik.katalog_projektu / "pliki_wynikowe").iterdir())
    assert len(pliki) == 1
    tresc = (wynik.katalog_projektu / "pliki_wynikowe" / pliki[0]).read_text(encoding="utf-8")
    assert "Baza wiedzy dla asystenta AI jest tym lepsza" in tresc
    assert "Zaakceptuj wszystkie" not in tresc


def test_manifest_zapisuje_dane_odpowiedzi_http(tmp_path: Path) -> None:
    odpowiedz = httpx.Response(
        200,
        content=_artykul(),
        headers={
            "content-type": "text/html; charset=utf-8",
            "etag": 'W/"abc"',
            "last-modified": "Wed, 26 Aug 2026 08:00:00 GMT",
        },
    )
    serwer = _Serwer({"/artykul": odpowiedz})

    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test manifestu",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    (zrodlo,) = manifest["zrodla"]
    pobranie = zrodlo["pobranie"]

    assert zrodlo["typ"] == "strona_www"
    assert zrodlo["pochodzenie"] == _ADRES_ARTYKULU
    assert pobranie["adres_koncowy"] == _ADRES_ARTYKULU
    assert pobranie["kod_odpowiedzi"] == 200
    assert pobranie["deklarowane_kodowanie"] == "utf-8"
    assert pobranie["etag"] == 'W/"abc"'
    assert pobranie["last_modified"] == "Wed, 26 Aug 2026 08:00:00 GMT"
    assert pobranie["z_pamieci_podrecznej"] is False
    assert zrodlo["checksum"]


def test_oryginal_strony_jest_zapisany_jako_surowe_bajty(tmp_path: Path) -> None:
    serwer = _Serwer()
    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test oryginału",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    materialy = list((wynik.katalog_projektu / "materialy_zrodlowe").iterdir())
    assert len(materialy) == 1
    assert materialy[0].suffix == ".html"
    assert materialy[0].read_bytes() == _artykul()


def test_adres_z_parametrem_sledzacym_jest_tym_samym_zrodlem(tmp_path: Path) -> None:
    serwer = _Serwer()
    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU, _ADRES_ARTYKULU + "?utm_source=newsletter"),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test duplikatu",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert len(manifest["zrodla"]) == 1
    assert len([adres for adres in serwer.zadania if "robots" not in adres]) == 1


def test_zakaz_w_robots_konczy_sie_statusem_pominiete(tmp_path: Path) -> None:
    serwer = _Serwer({"/robots.txt": httpx.Response(200, text="User-agent: *\nDisallow: /")})

    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        _konfiguracja(tmp_path, respektuj_robots=True),
        nazwa_projektu="Test robots",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    (zrodlo,) = manifest["zrodla"]
    assert zrodlo["status"] == "pominiete"
    assert "robots.txt" in zrodlo["komunikat_bledu"]


def test_odpowiedz_404_konczy_sie_statusem_blad_a_reszta_przechodzi(tmp_path: Path) -> None:
    serwer = _Serwer({"/brak": httpx.Response(404)})

    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU, "https://przyklad.pl/brak"),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test błędu sieci",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    assert wynik.liczba_przetworzonych == 1
    assert wynik.liczba_bledow == 1

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    statusy = sorted(zrodlo["status"] for zrodlo in manifest["zrodla"])
    assert statusy == ["blad", "spakowane"]


def test_zasob_inny_niz_html_jest_pomijany(tmp_path: Path) -> None:
    odpowiedz = httpx.Response(
        200, content=b"%PDF-1.7", headers={"content-type": "application/pdf"}
    )
    serwer = _Serwer({"/artykul": odpowiedz})

    wynik = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test formatu",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0


def test_wznowienie_nie_pobiera_adresu_ponownie(tmp_path: Path) -> None:
    serwer = _Serwer()
    konfiguracja = _konfiguracja(tmp_path)

    przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        konfiguracja,
        nazwa_projektu="Test wznowienia URL",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )
    zadania_po_pierwszym = len(serwer.zadania)

    drugie = przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        konfiguracja,
        nazwa_projektu="Test wznowienia URL",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    assert drugie.wznowiono is True
    assert len(serwer.zadania) == zadania_po_pierwszym
    manifest = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))
    assert len(manifest["zrodla"]) == 1


def test_pamiec_podreczna_oszczedza_pobranie_w_drugim_projekcie(tmp_path: Path) -> None:
    serwer = _Serwer()
    konfiguracja = _konfiguracja(tmp_path, uzywaj_cache=True)

    przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        konfiguracja,
        nazwa_projektu="Pierwszy projekt",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )
    zadania_po_pierwszym = len(serwer.zadania)

    przetworz_projekt(
        _pozycje(_ADRES_ARTYKULU),
        konfiguracja,
        nazwa_projektu="Drugi projekt",
        zegar=_zegar_krokowy(),
        transport_http=serwer.transport(),
    )

    assert len(serwer.zadania) == zadania_po_pierwszym
