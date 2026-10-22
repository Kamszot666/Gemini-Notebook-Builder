"""Testy serwera i widoków dla szkicu tekstu zaznaczonego globalnym skrótem.

Szkic jest jeden na projekt i wypełnia pole „Tu wklej tekst” na stronie głównej
(gdy lista „Projekt” wskazuje ten projekt) oraz w formularzu dosyłania na stronie
projektu. Trasa ``/projekt/NAZWA/szkic`` służy skryptowi strony do dopisywania
nowego tekstu bez przeładowania. Projekty powstają prawdziwym przebiegiem, bez
sieci zewnętrznej.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlencode

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.ui.serwer import przygotuj_stan_skrotu, zbuduj_serwer
from gnb.ui.stan_skrotu import (
    NAZWA_PLIKU_STANU_SKROTU,
    AktywnyProjektSkrotu,
    SzkicTekstuSkrotu,
)
from gnb.ui.zadania import RejestrZadan

_GRANICA = "----TestGranicaSzkic"
_TEKST = "Tekst testowy o porządkowaniu materiałów przed importem do notatnika."


class _Klient:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self.ciasteczko: str | None = None

    def _wyslij(
        self, metoda: str, sciezka: str, cialo: bytes | None = None, typ: str | None = None
    ) -> tuple[http.client.HTTPResponse, str]:
        polaczenie = http.client.HTTPConnection(self._host, self._port, timeout=5)
        naglowki: dict[str, str] = {}
        if self.ciasteczko:
            naglowki["Cookie"] = self.ciasteczko
        if cialo is not None and typ is not None:
            naglowki["Content-Type"] = typ
            naglowki["Content-Length"] = str(len(cialo))
        polaczenie.request(metoda, sciezka, body=cialo, headers=naglowki)
        odpowiedz = polaczenie.getresponse()
        surowe = odpowiedz.getheader("Set-Cookie")
        if surowe:
            self.ciasteczko = surowe.split(";", 1)[0]
        return odpowiedz, odpowiedz.read().decode("utf-8")

    def get(self, sciezka: str) -> tuple[http.client.HTTPResponse, str]:
        return self._wyslij("GET", sciezka)

    def post(self, sciezka: str, pola: dict[str, str]) -> tuple[http.client.HTTPResponse, str]:
        czesci = "".join(
            f'--{_GRANICA}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'
            for nazwa, wartosc in pola.items()
        )
        cialo = (czesci + f"--{_GRANICA}--\r\n").encode("utf-8")
        return self._wyslij("POST", sciezka, cialo, f"multipart/form-data; boundary={_GRANICA}")

    def token(self) -> str:
        return self.ciasteczko.split("=", 1)[1] if self.ciasteczko else ""


@pytest.fixture
def srodowisko(
    tmp_path: Path,
) -> Iterator[tuple[_Klient, RejestrZadan, AktywnyProjektSkrotu, SzkicTekstuSkrotu]]:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    rejestr = RejestrZadan()
    aktywny = AktywnyProjektSkrotu()
    szkic = SzkicTekstuSkrotu()
    instancja = zbuduj_serwer(
        konfiguracja, rejestr, aktywny_projekt_skrotu=aktywny, szkic_tekstu_skrotu=szkic
    )
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    klient = _Klient(str(instancja.server_address[0]), int(instancja.server_address[1]))
    klient.get("/")
    try:
        yield klient, rejestr, aktywny, szkic
    finally:
        instancja.shutdown()
        instancja.server_close()
        watek.join(timeout=5)


def _czekaj(rejestr: RejestrZadan) -> None:
    for _ in range(500):
        informacja = rejestr.informacja()
        if informacja is not None and informacja.stan.value != "trwa":
            return
        time.sleep(0.02)
    raise AssertionError("przetwarzanie nie zakończyło się w oczekiwanym czasie")


def _nowy_projekt(klient: _Klient, rejestr: RejestrZadan, nazwa: str) -> None:
    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "",
            "nazwa_projektu": nazwa,
            "tekst": _TEKST,
            "wybor_grupy": "__nowa__",
            "nazwa_grupy": "Wiedza",
        },
    )
    assert odpowiedz.status == 303
    _czekaj(rejestr)


# --- trasa szkicu ------------------------------------------------------------


def test_trasa_szkicu_zwraca_tekst_i_wersje(srodowisko) -> None:
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Pierwszy")

    odpowiedz, tresc = klient.get("/projekt/Projekt%20A/szkic")

    assert odpowiedz.status == 200
    assert odpowiedz.getheader("Content-Type", "").startswith("application/json")
    assert json.loads(tresc) == {"tekst": "Pierwszy\n", "wersja": 1}


def test_trasa_szkicu_pustego_projektu_zwraca_pusty_tekst_i_wersje_zero(srodowisko) -> None:
    klient, rejestr, _, _ = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")

    _, tresc = klient.get("/projekt/Projekt%20A/szkic")

    assert json.loads(tresc) == {"tekst": "", "wersja": 0}


@pytest.mark.parametrize("nazwa", ["Nie%20ma%20takiego", "CON", "..%2F..%2Fx"])
def test_trasa_szkicu_dla_nieistniejacego_projektu_daje_404_a_nie_500(srodowisko, nazwa) -> None:
    klient, _, _, _ = srodowisko

    odpowiedz, _ = klient.get(f"/projekt/{nazwa}/szkic")

    assert odpowiedz.status == 404


# --- strona główna -----------------------------------------------------------


def test_strona_glowna_wypelnia_pole_tekstu_szkicem_aktywnego_projektu(srodowisko) -> None:
    klient, rejestr, aktywny, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    aktywny.ustaw("Projekt A")
    szkic.dopisz("Projekt A", "Zaznaczone zdanie.")

    _, strona = klient.get("/")

    assert 'data-wersja-szkicu="1"' in strona
    assert ">Zaznaczone zdanie.\n</textarea>" in strona
    # Skrypt ogłasza dopisanie dokładnie tym zdaniem, w regionie stanu.
    assert 'id="komunikat-szkicu" role="status" aria-live="polite"' in strona
    assert "Dodano zaznaczony tekst do pola Tu wklej tekst." in strona


def test_strona_glowna_bez_aktywnego_projektu_ma_puste_pole_tekstu(srodowisko) -> None:
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Zaznaczone zdanie.")

    _, strona = klient.get("/")

    assert "Zaznaczone zdanie." not in strona


def test_szkic_innego_projektu_nie_trafia_do_pola_wybranego_projektu(srodowisko) -> None:
    klient, rejestr, aktywny, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    _nowy_projekt(klient, rejestr, "Projekt B")
    aktywny.ustaw("Projekt A")
    szkic.dopisz("Projekt B", "Tekst do B.")

    _, strona = klient.get("/")

    assert "Tekst do B." not in strona


def test_tekst_ze_szkicu_trafia_do_strony_wylacznie_jako_tekst_z_escapowaniem(srodowisko) -> None:
    klient, rejestr, aktywny, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    aktywny.ustaw("Projekt A")
    szkic.dopisz("Projekt A", "</textarea><script>alert(1)</script>")

    _, glowna = klient.get("/")
    _, projekt = klient.get("/projekt/Projekt%20A")

    for strona in (glowna, projekt):
        assert "<script>alert(1)</script>" not in strona
        assert "&lt;/textarea&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in strona


def test_blad_walidacji_zachowuje_to_co_wyslal_uzytkownik_a_nie_szkic(srodowisko) -> None:
    klient, rejestr, aktywny, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    aktywny.ustaw("Projekt A")
    szkic.dopisz("Projekt A", "Ze szkicu.")

    odpowiedz, strona = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "Projekt A",
            "nazwa_projektu": "",
            "tekst": "Własna edycja.",
            "adresy": "to nie jest adres",
            "wybor_grupy": "__nowa__",
            "nazwa_grupy": "",
        },
    )

    assert odpowiedz.status == 400
    assert ">Własna edycja.</textarea>" in strona
    # Nieudane wysłanie nie czyści szkicu.
    assert szkic.pobierz("Projekt A").tekst == "Ze szkicu.\n"


# --- strona projektu ---------------------------------------------------------


def test_strona_projektu_wypelnia_pole_dosylania_szkicem(srodowisko) -> None:
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Pierwszy.")
    szkic.dopisz("Projekt A", "Drugi.")

    odpowiedz, strona = klient.get("/projekt/Projekt%20A")

    assert odpowiedz.status == 200
    assert ">Pierwszy.\nDrugi.\n</textarea>" in strona
    assert 'data-projekt="Projekt A"' in strona
    assert 'data-wersja-szkicu="2"' in strona
    assert 'id="komunikat-szkicu-dosylania" role="status" aria-live="polite"' in strona


# --- czyszczenie szkicu ------------------------------------------------------


def test_wyslanie_formularza_dosylania_czyści_szkic(srodowisko) -> None:
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Zaznaczone zdanie.")

    odpowiedz, _ = klient.post(
        "/projekt/Projekt%20A/dosylanie",
        {
            "token_csrf": klient.token(),
            "tekst": "Zaznaczone zdanie, uzupełnione przez użytkownika o dalsze uwagi.",
            "adresy": "",
            "grupa": "Wiedza",
        },
    )
    _czekaj(rejestr)

    assert odpowiedz.status == 303
    assert szkic.pobierz("Projekt A").tekst == ""


def test_dosylanie_z_pustym_polem_tekstu_tez_czysci_szkic(srodowisko) -> None:
    """Ręczne wyczyszczenie pola przez użytkownika czyści szkic przy wysłaniu."""
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Niechciane zdanie.")

    odpowiedz, _ = klient.post(
        "/projekt/Projekt%20A/dosylanie",
        {
            "token_csrf": klient.token(),
            "tekst": "",
            "adresy": "https://przyklad.invalid/artykul",
            "grupa": "Wiedza",
        },
    )
    _czekaj(rejestr)

    assert odpowiedz.status == 303
    assert szkic.pobierz("Projekt A").tekst == ""


def test_nieudane_dosylanie_nie_czysci_szkicu(srodowisko) -> None:
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Zaznaczone zdanie.")

    odpowiedz, _ = klient.post(
        "/projekt/Projekt%20A/dosylanie",
        {"token_csrf": klient.token(), "tekst": "Tekst", "adresy": "", "grupa": ""},
    )

    assert odpowiedz.status == 400
    assert szkic.pobierz("Projekt A").tekst == "Zaznaczone zdanie.\n"


def test_wyslanie_formularza_glownego_z_istniejacym_projektem_czysci_jego_szkic(
    srodowisko,
) -> None:
    klient, rejestr, _, szkic = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    szkic.dopisz("Projekt A", "Zaznaczone zdanie.")
    szkic.dopisz("Projekt B", "Szkic innego projektu.")

    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "Projekt A",
            "nazwa_projektu": "",
            "tekst": "Zaznaczone zdanie, dopisane dalej przez użytkownika, żeby było inne.",
            "wybor_grupy": "g:Wiedza",
            "nazwa_grupy": "",
        },
    )
    _czekaj(rejestr)

    assert odpowiedz.status == 303
    assert szkic.pobierz("Projekt A").tekst == ""
    assert szkic.pobierz("Projekt B").tekst == "Szkic innego projektu.\n"


# --- stan skrótu przy starcie serwera ----------------------------------------


def test_przygotuj_stan_skrotu_przywraca_zapamietany_projekt(tmp_path: Path) -> None:
    dane = tmp_path / "dane"
    wyniki = tmp_path / "wyniki"
    (wyniki / "Projekt A").mkdir(parents=True)
    (wyniki / "Projekt A" / "checkpoint.json").write_text("{}", encoding="utf-8")
    AktywnyProjektSkrotu(dane / NAZWA_PLIKU_STANU_SKROTU).ustaw("Projekt A")

    aktywny, komunikat = przygotuj_stan_skrotu(dane, wyniki)

    assert aktywny.aktualny() == "Projekt A"
    assert komunikat.aktualny() is None


def test_przygotuj_stan_skrotu_dla_usunietego_projektu_zostawia_komunikat(tmp_path: Path) -> None:
    dane = tmp_path / "dane"
    wyniki = tmp_path / "wyniki"
    wyniki.mkdir()
    AktywnyProjektSkrotu(dane / NAZWA_PLIKU_STANU_SKROTU).ustaw("Projekt Usunięty")

    aktywny, komunikat = przygotuj_stan_skrotu(dane, wyniki)

    assert aktywny.aktualny() is None
    ostatni = komunikat.aktualny()
    assert ostatni is not None and ostatni.sukces is False
    assert "Projekt Usunięty" in ostatni.tekst
    assert not (dane / NAZWA_PLIKU_STANU_SKROTU).exists()


def test_przygotuj_stan_skrotu_z_uszkodzonym_plikiem_nie_wywraca_startu(tmp_path: Path) -> None:
    dane = tmp_path / "dane"
    dane.mkdir()
    (dane / NAZWA_PLIKU_STANU_SKROTU).write_text("{ uszkodzone", encoding="utf-8")

    aktywny, komunikat = przygotuj_stan_skrotu(dane, tmp_path)

    assert aktywny.aktualny() is None
    assert komunikat.aktualny() is not None


def test_wybor_projektu_przyciskiem_jest_zapamietywany_trwale(tmp_path: Path) -> None:
    """Zmiana aktywnego projektu przez serwer trafia do pliku stanu, nie tylko do pamięci."""
    plik = tmp_path / "dane" / NAZWA_PLIKU_STANU_SKROTU
    aktywny = AktywnyProjektSkrotu(plik)
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    (konfiguracja.katalog_wynikow / "Projekt A").mkdir(parents=True)
    instancja = zbuduj_serwer(konfiguracja, RejestrZadan(), aktywny_projekt_skrotu=aktywny)
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    try:
        klient = _Klient(str(instancja.server_address[0]), int(instancja.server_address[1]))
        klient.get("/")
        cialo = urlencode({"token_csrf": klient.token()}).encode()
        odpowiedz, _ = klient._wyslij(
            "POST",
            "/projekt/Projekt%20A/aktywny-skrot",
            cialo,
            "application/x-www-form-urlencoded",
        )
    finally:
        instancja.shutdown()
        instancja.server_close()
        watek.join(timeout=5)

    assert odpowiedz.status == 303
    assert json.loads(plik.read_text(encoding="utf-8"))["aktywny_projekt"] == "Projekt A"


def test_skrypt_szkicu_oddziela_nowy_tekst_od_recznie_wpisanego_nowym_wierszem(
    srodowisko,
) -> None:
    """Szkic na serwerze dopisuje nowy wiersz przed tekstem, więc skrypt robi to samo."""
    klient, rejestr, aktywny, _ = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A")
    aktywny.ustaw("Projekt A")

    _, strona = klient.get("/")

    assert "charAt(koniec - 1) !== '\\n'" in strona
    assert "setRangeText(tekst, koniec, koniec, 'preserve')" in strona
