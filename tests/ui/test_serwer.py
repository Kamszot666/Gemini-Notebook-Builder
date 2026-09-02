"""Testy integracyjne serwera HTTP interfejsu na losowym porcie pętli zwrotnej."""

from __future__ import annotations

import http.client
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.ui import csrf
from gnb.ui.serwer import zbuduj_serwer
from gnb.ui.zadania import RejestrZadan


class _Klient:
    """Cienki klient HTTP pamiętający ciasteczko sesji między żądaniami."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self.ciasteczko: str | None = None

    def _polaczenie(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection(self._host, self._port, timeout=5)

    def get(self, sciezka: str) -> http.client.HTTPResponse:
        polaczenie = self._polaczenie()
        naglowki = {"Cookie": self.ciasteczko} if self.ciasteczko else {}
        polaczenie.request("GET", sciezka, headers=naglowki)
        odpowiedz = polaczenie.getresponse()
        self._zapamietaj_ciasteczko(odpowiedz)
        odpowiedz.read()
        return odpowiedz

    def post(self, sciezka: str, cialo: bytes, typ: str) -> http.client.HTTPResponse:
        polaczenie = self._polaczenie()
        naglowki = {"Content-Type": typ, "Content-Length": str(len(cialo))}
        if self.ciasteczko:
            naglowki["Cookie"] = self.ciasteczko
        polaczenie.request("POST", sciezka, body=cialo, headers=naglowki)
        odpowiedz = polaczenie.getresponse()
        self._zapamietaj_ciasteczko(odpowiedz)
        odpowiedz.read()
        return odpowiedz

    def _zapamietaj_ciasteczko(self, odpowiedz: http.client.HTTPResponse) -> None:
        surowe = odpowiedz.getheader("Set-Cookie")
        if surowe:
            self.ciasteczko = surowe.split(";", 1)[0]


@pytest.fixture
def serwer(tmp_path: Path) -> Iterator[tuple[str, int, RejestrZadan]]:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    rejestr = RejestrZadan()
    instancja = zbuduj_serwer(konfiguracja, rejestr)
    host, port = instancja.server_address[0], instancja.server_address[1]
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    try:
        yield str(host), int(port), rejestr
    finally:
        instancja.shutdown()
        instancja.server_close()
        watek.join(timeout=5)


def test_serwer_nasluchuje_wylacznie_na_petli_zwrotnej(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    host, _, _ = serwer
    assert host in {"127.0.0.1", "::1"}


def test_strona_glowna_zwraca_formularz_i_ustawia_ciasteczko(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    host, port, _ = serwer
    klient = _Klient(host, port)
    odpowiedz = klient.get("/")

    assert odpowiedz.status == 200
    assert klient.ciasteczko is not None and klient.ciasteczko.startswith(csrf.NAZWA_CIASTECZKA)


def test_post_bez_tokenu_csrf_jest_odrzucany_z_403(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    host, port, _ = serwer
    klient = _Klient(host, port)
    klient.get("/")  # zdobądź ciasteczko sesji

    cialo = b"nazwa_projektu=Test&tekst=cos"
    odpowiedz = klient.post("/projekt/nowy", cialo, "application/x-www-form-urlencoded")
    assert odpowiedz.status == 403


def test_pelny_przebieg_tworzenia_projektu_z_tekstem(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    host, port, rejestr = serwer
    klient = _Klient(host, port)
    klient.get("/")
    token = klient.ciasteczko.split("=", 1)[1] if klient.ciasteczko else ""

    granica = "----TestGranica"

    def czesc(nazwa: str, wartosc: str) -> str:
        return f'--{granica}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'

    cialo = (
        czesc("token_csrf", token)
        + czesc("nazwa_projektu", "Projekt Testowy")
        + czesc("tekst", "Krótki tekst do testu serwera.")
        + f"--{granica}--\r\n"
    ).encode("utf-8")
    odpowiedz = klient.post("/projekt/nowy", cialo, f"multipart/form-data; boundary={granica}")
    assert odpowiedz.status == 303
    assert odpowiedz.getheader("Location") == "/projekt/Projekt%20Testowy"

    for _ in range(300):
        informacja = rejestr.informacja()
        if informacja is not None and informacja.stan.value != "trwa":
            break
        time.sleep(0.02)
    informacja = rejestr.informacja()
    assert informacja is not None
    assert informacja.stan.value == "zakonczone"

    strona = klient.get("/projekt/Projekt%20Testowy")
    assert strona.status == 200


def test_postep_zwraca_json(serwer: tuple[str, int, RejestrZadan]) -> None:
    host, port, _ = serwer
    odpowiedz = _Klient(host, port).get("/postep")
    assert odpowiedz.status == 200
    assert odpowiedz.getheader("Content-Type", "").startswith("application/json")


def test_nieznana_sciezka_daje_404(serwer: tuple[str, int, RejestrZadan]) -> None:
    host, port, _ = serwer
    odpowiedz = _Klient(host, port).get("/nie-ma-takiej-strony")
    assert odpowiedz.status == 404
