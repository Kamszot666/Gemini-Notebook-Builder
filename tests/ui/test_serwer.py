"""Testy integracyjne serwera HTTP interfejsu na losowym porcie pętli zwrotnej."""

from __future__ import annotations

import http.client
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.persistence.projekt import ustal_uklad, utworz_katalogi
from gnb.ui import csrf
from gnb.ui.serwer import zbuduj_serwer
from gnb.ui.stan_skrotu import AktywnyProjektSkrotu
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

    def get_tekst(self, sciezka: str) -> tuple[http.client.HTTPResponse, str]:
        """Jak `get`, ale zwraca też treść odpowiedzi jako tekst do przeszukania."""
        polaczenie = self._polaczenie()
        naglowki = {"Cookie": self.ciasteczko} if self.ciasteczko else {}
        polaczenie.request("GET", sciezka, headers=naglowki)
        odpowiedz = polaczenie.getresponse()
        self._zapamietaj_ciasteczko(odpowiedz)
        tekst = odpowiedz.read().decode("utf-8")
        return odpowiedz, tekst

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
        + czesc("grupa", "Wiedza")
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


def _wielloczesciowe(granica: str, pola: dict[str, str]) -> bytes:
    czesci = "".join(
        f'--{granica}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'
        for nazwa, wartosc in pola.items()
    )
    return (czesci + f"--{granica}--\r\n").encode("utf-8")


def _czekaj_na_zakonczenie(rejestr: RejestrZadan) -> None:
    for _ in range(300):
        informacja = rejestr.informacja()
        if informacja is not None and informacja.stan.value != "trwa":
            return
        time.sleep(0.02)


def test_dosylanie_zrodel_dodaje_je_do_istniejacego_projektu(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    """Pozycja czwarta listy zmian etapu czternastego.

    Formularz dosyłania pod raportem idzie tą samą ścieżką co formularz strony
    głównej z nazwą istniejącego projektu: dodaje wejście do tego samego
    checkpointu, zamiast zakładać nowy projekt.
    """
    host, port, rejestr = serwer
    klient = _Klient(host, port)
    klient.get("/")
    granica = "----TestGranica"

    pierwsze = klient.post(
        "/projekt/nowy",
        _wielloczesciowe(
            granica,
            {
                "token_csrf": _token(klient),
                "nazwa_projektu": "Projekt Dosylania",
                "tekst": "Pierwszy tekst wklejony do testu dosyłania.",
                "grupa": "Wiedza",
            },
        ),
        f"multipart/form-data; boundary={granica}",
    )
    assert pierwsze.status == 303
    _czekaj_na_zakonczenie(rejestr)

    drugie = klient.post(
        "/projekt/Projekt%20Dosylania/dosylanie",
        _wielloczesciowe(
            granica,
            {
                "token_csrf": _token(klient),
                "tekst": "Drugi tekst dosłany pod raportem.",
                "grupa": "Wiedza",
            },
        ),
        f"multipart/form-data; boundary={granica}",
    )
    assert drugie.status == 303
    assert drugie.getheader("Location") == "/projekt/Projekt%20Dosylania"
    _czekaj_na_zakonczenie(rejestr)

    informacja = rejestr.informacja()
    assert informacja is not None
    assert informacja.stan.value == "zakonczone"
    assert informacja.wynik is not None
    assert informacja.wynik.wznowiono is True

    _, tekst = klient.get_tekst("/projekt/Projekt%20Dosylania")
    assert "Liczba wejść: 2" in tekst
    assert "Liczba źródeł poprawnych: 2" in tekst


def test_dosylanie_zrodel_bez_tokenu_csrf_jest_odrzucane(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    host, port, _ = serwer
    klient = _Klient(host, port)
    klient.get("/")

    odpowiedz = klient.post(
        "/projekt/Nieistniejacy/dosylanie", b"tekst=cos", "application/x-www-form-urlencoded"
    )
    assert odpowiedz.status == 403


def test_dosylanie_zrodel_bez_zadnego_zrodla_wraca_na_strone_projektu_z_bledem(
    serwer: tuple[str, int, RejestrZadan],
) -> None:
    host, port, rejestr = serwer
    klient = _Klient(host, port)
    klient.get("/")
    granica = "----TestGranica"

    klient.post(
        "/projekt/nowy",
        _wielloczesciowe(
            granica,
            {
                "token_csrf": _token(klient),
                "nazwa_projektu": "Projekt Pusty",
                "tekst": "Materiał startowy projektu.",
                "grupa": "Wiedza",
            },
        ),
        f"multipart/form-data; boundary={granica}",
    )
    _czekaj_na_zakonczenie(rejestr)

    odpowiedz, tekst = klient.get_tekst("/postep")  # tylko po to, by ciasteczko było świeże
    assert odpowiedz.status == 200

    odpowiedz = klient.post(
        "/projekt/Projekt%20Pusty/dosylanie",
        _wielloczesciowe(granica, {"token_csrf": _token(klient)}),
        f"multipart/form-data; boundary={granica}",
    )
    # Błąd wraca na stronę PROJEKTU, nie na stronę główną — inaczej użytkownik,
    # który wysłał formularz spod raportu, trafiłby w nieoczekiwane miejsce.
    assert odpowiedz.status == 400


def test_postep_zwraca_json(serwer: tuple[str, int, RejestrZadan]) -> None:
    host, port, _ = serwer
    odpowiedz = _Klient(host, port).get("/postep")
    assert odpowiedz.status == 200
    assert odpowiedz.getheader("Content-Type", "").startswith("application/json")


def test_nieznana_sciezka_daje_404(serwer: tuple[str, int, RejestrZadan]) -> None:
    host, port, _ = serwer
    odpowiedz = _Klient(host, port).get("/nie-ma-takiej-strony")
    assert odpowiedz.status == 404


@pytest.fixture
def serwer_z_projektem(
    tmp_path: Path,
) -> Iterator[tuple[str, int, AktywnyProjektSkrotu]]:
    """Serwer z jednym już istniejącym katalogiem projektu, do testów skrótu."""
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    uklad = ustal_uklad(konfiguracja.katalog_wynikow, "Projekt Testowy")
    utworz_katalogi(uklad, z_materialami_zrodlowymi=False)

    aktywny_projekt_skrotu = AktywnyProjektSkrotu()
    instancja = zbuduj_serwer(
        konfiguracja, RejestrZadan(), aktywny_projekt_skrotu=aktywny_projekt_skrotu
    )
    host, port = instancja.server_address[0], instancja.server_address[1]
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    try:
        yield str(host), int(port), aktywny_projekt_skrotu
    finally:
        instancja.shutdown()
        instancja.server_close()
        watek.join(timeout=5)


def _token(klient: _Klient) -> str:
    return klient.ciasteczko.split("=", 1)[1] if klient.ciasteczko else ""


def test_ustawienie_aktywnego_projektu_skrotu_zapisuje_stan_i_przekierowuje(
    serwer_z_projektem: tuple[str, int, AktywnyProjektSkrotu],
) -> None:
    host, port, aktywny_projekt_skrotu = serwer_z_projektem
    klient = _Klient(host, port)
    klient.get("/")

    cialo = f"token_csrf={_token(klient)}".encode()
    odpowiedz = klient.post(
        "/projekt/Projekt%20Testowy/aktywny-skrot", cialo, "application/x-www-form-urlencoded"
    )

    assert odpowiedz.status == 303
    assert odpowiedz.getheader("Location") == "/projekt/Projekt%20Testowy"
    assert aktywny_projekt_skrotu.aktualny() == "Projekt Testowy"


def test_ustawienie_aktywnego_projektu_skrotu_bez_csrf_jest_odrzucane(
    serwer_z_projektem: tuple[str, int, AktywnyProjektSkrotu],
) -> None:
    host, port, aktywny_projekt_skrotu = serwer_z_projektem
    klient = _Klient(host, port)
    klient.get("/")

    odpowiedz = klient.post(
        "/projekt/Projekt%20Testowy/aktywny-skrot", b"", "application/x-www-form-urlencoded"
    )

    assert odpowiedz.status == 403
    assert aktywny_projekt_skrotu.aktualny() is None


def test_ustawienie_aktywnego_projektu_skrotu_dla_nieistniejacego_projektu_daje_404(
    serwer_z_projektem: tuple[str, int, AktywnyProjektSkrotu],
) -> None:
    host, port, _ = serwer_z_projektem
    klient = _Klient(host, port)
    klient.get("/")

    cialo = f"token_csrf={_token(klient)}".encode()
    odpowiedz = klient.post(
        "/projekt/Nie%20Ma%20Takiego/aktywny-skrot", cialo, "application/x-www-form-urlencoded"
    )

    assert odpowiedz.status == 404


def test_strona_projektu_po_ustawieniu_aktywnym_nie_pokazuje_juz_przycisku(
    serwer_z_projektem: tuple[str, int, AktywnyProjektSkrotu],
) -> None:
    host, port, _ = serwer_z_projektem
    klient = _Klient(host, port)
    klient.get("/")
    cialo = f"token_csrf={_token(klient)}".encode()
    klient.post(
        "/projekt/Projekt%20Testowy/aktywny-skrot", cialo, "application/x-www-form-urlencoded"
    )

    strona, tekst = klient.get_tekst("/projekt/Projekt%20Testowy")
    assert strona.status == 200
    assert "Ten projekt jest teraz aktywnym projektem globalnego skrótu." in tekst
    assert "Ustaw jako aktywny projekt skrótu" not in tekst
