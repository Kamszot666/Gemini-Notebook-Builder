"""Test przez cały potok: filtr reklam i innych elementów strony.

Strona jest wymyślona, ale ma budowę spotykaną na dużych portalach: wiersze
„REKLAMA” w środku artykułu, przyciski udostępniania, podpis zdjęcia, blok
newslettera i licznik komentarzy na końcu. Pobieranie podstawia sztuczny serwer,
a ekstrakcję wykonuje prawdziwa trafilatura.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_url
from gnb.potok import WynikPrzetwarzania, przetworz_projekt

_ADRES = "https://przyklad.pl/artykul"
_MOMENT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)


def _akapit(numer: int) -> str:
    return (
        f"<p>Akapit numer {numer} opisuje przebieg obrad rady miasta nad planem zagospodarowania "
        "terenów nad rzeką, a także stanowiska mieszkańców, radnych i urzędników, którzy przez "
        "wiele godzin wymieniali argumenty za oraz przeciw proponowanym zmianom w planie.</p>"
    )


_STRONA = (
    '<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">'
    "<title>Rada miasta przyjęła plan</title></head><body><article>"
    "<h1>Rada miasta przyjęła plan zagospodarowania terenów nad rzeką</h1>"
    "<p>Udostępnij na FacebookuUdostępnij na XKopiuj link</p>"
    f"{_akapit(1)}{_akapit(2)}<p>REKLAMA</p>{_akapit(3)}{_akapit(4)}<p>REKLAMA</p>"
    f"{_akapit(5)}{_akapit(6)}"
    "<p>BLISKO LUDZI</p><p>Newsletter portalu przykładowego, co tydzień na Twoją skrzynkę.</p>"
    "<p>Zapisz mnie</p><p>2139 komentarzy</p>"
    "</article></body></html>"
).encode()


def _zegar() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 10, 23, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _przetworz(tmp_path: Path, **nadpisania: object) -> WynikPrzetwarzania:
    konfiguracja = Konfiguracja(
        **{
            "formaty_wynikowe": ("txt",),
            "katalog_wynikow": tmp_path / "wyniki",
            "sciezka_cache": tmp_path / "cache.sqlite3",
            "uzywaj_cache": False,
            "respektuj_robots": False,
            "odstep_miedzy_zadaniami_sekundy": 0.0,
            "liczba_ponowien": 0,
            **nadpisania,
        }  # type: ignore[arg-type]
    )

    def obsluz(zadanie: httpx.Request) -> httpx.Response:
        if zadanie.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(
            200, content=_STRONA, headers={"content-type": "text/html; charset=utf-8"}
        )

    pozycje: list[PozycjaWejsciowa] = [przyjmij_url(_ADRES, _MOMENT)]
    return przetworz_projekt(
        pozycje,
        konfiguracja,
        nazwa_projektu="Filtr",
        zegar=_zegar(),
        transport_http=httpx.MockTransport(obsluz),
    )


def _tresc_wyniku(wynik: WynikPrzetwarzania) -> str:
    (plik,) = (wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt")
    return plik.read_text(encoding="utf-8")


def test_wylaczony_filtr_zostawia_elementy_strony_w_pliku_wynikowym(tmp_path: Path) -> None:
    wynik = _przetworz(tmp_path, filtr_elementow_strony=False)

    tresc = _tresc_wyniku(wynik)

    assert "REKLAMA" in tresc
    assert "Newsletter portalu" in tresc
    assert not list((wynik.katalog_projektu / "wyniki_posrednie").glob("*.usuniete-fragmenty.txt"))


def test_filtr_usuwa_elementy_strony_ale_zostawia_caly_artykul(tmp_path: Path) -> None:
    wynik = _przetworz(tmp_path)

    tresc = _tresc_wyniku(wynik)

    assert "REKLAMA" not in tresc
    assert "Newsletter portalu" not in tresc
    assert "Zapisz mnie" not in tresc
    assert "2139 komentarzy" not in tresc
    for numer in range(1, 7):
        assert f"Akapit numer {numer} opisuje" in tresc


def test_usuniete_fragmenty_sa_w_wynikach_posrednich_a_licznik_w_manifescie(
    tmp_path: Path,
) -> None:
    wynik = _przetworz(tmp_path)

    (plik,) = (wynik.katalog_projektu / "wyniki_posrednie").glob("*.usuniete-fragmenty.txt")
    zapis = plik.read_text(encoding="utf-8")
    assert zapis.count("Powód: reklama. Tekst: REKLAMA") == 2
    assert "Newsletter portalu" in zapis

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    (zrodlo,) = manifest["zrodla"]
    assert int(zrodlo["metadane"]["liczba_usunietych_fragmentow"]) >= 6
    assert zrodlo["status"] == "spakowane"
