"""Testy serwera dla jedynego formularza strony głównej z listami „Projekt” i „Grupa”.

Sprawdzają trasę zwracającą grupy projektu, wysyłanie formularza dla nowego
i istniejącego projektu, walidację po stronie serwera niezależną od JavaScriptu
oraz to, że wybór projektu ustawia aktywny projekt skrótu, a „Nowy projekt” go
nie zmienia. Projekty powstają prawdziwym przebiegiem, bez sieci zewnętrznej.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote, urlencode

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.persistence.checkpoint import wczytaj
from gnb.persistence.projekt import ustal_uklad
from gnb.ui.serwer import zbuduj_serwer
from gnb.ui.stan_skrotu import AktywnyProjektSkrotu
from gnb.ui.zadania import RejestrZadan

_GRANICA = "----TestGranicaGlowny"
_TEKST = "Tekst testowy o porządkowaniu materiałów przed importem do notatnika."
_NAZWA_ZLA = "CON"


class _Klient:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self.ciasteczko: str | None = None

    def _wyslij(
        self,
        metoda: str,
        sciezka: str,
        cialo: bytes | None = None,
        typ: str | None = None,
        naglowki_dodatkowe: dict[str, str] | None = None,
    ) -> tuple[http.client.HTTPResponse, str]:
        polaczenie = http.client.HTTPConnection(self._host, self._port, timeout=5)
        naglowki: dict[str, str] = dict(naglowki_dodatkowe or {})
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

    def get(
        self, sciezka: str, *, json_zadany: bool = False
    ) -> tuple[http.client.HTTPResponse, str]:
        naglowki = {"Accept": "application/json"} if json_zadany else None
        return self._wyslij("GET", sciezka, naglowki_dodatkowe=naglowki)

    def post(self, sciezka: str, pola: dict[str, str]) -> tuple[http.client.HTTPResponse, str]:
        czesci = "".join(
            f'--{_GRANICA}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'
            for nazwa, wartosc in pola.items()
        )
        cialo = (czesci + f"--{_GRANICA}--\r\n").encode("utf-8")
        return self._wyslij("POST", sciezka, cialo, f"multipart/form-data; boundary={_GRANICA}")

    def post_urlencoded(
        self, sciezka: str, pola: dict[str, str], *, json_zadany: bool = False
    ) -> tuple[http.client.HTTPResponse, str]:
        naglowki = {"Accept": "application/json"} if json_zadany else None
        return self._wyslij(
            "POST",
            sciezka,
            urlencode(pola).encode("utf-8"),
            "application/x-www-form-urlencoded",
            naglowki,
        )

    def token(self) -> str:
        return self.ciasteczko.split("=", 1)[1] if self.ciasteczko else ""


@pytest.fixture
def srodowisko(
    tmp_path: Path,
) -> Iterator[tuple[_Klient, RejestrZadan, Konfiguracja, AktywnyProjektSkrotu]]:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    rejestr = RejestrZadan()
    aktywny = AktywnyProjektSkrotu()
    instancja = zbuduj_serwer(konfiguracja, rejestr, aktywny_projekt_skrotu=aktywny)
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    klient = _Klient(str(instancja.server_address[0]), int(instancja.server_address[1]))
    klient.get("/")
    try:
        yield klient, rejestr, konfiguracja, aktywny
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


def _nowy_projekt(
    klient: _Klient, rejestr: RejestrZadan, nazwa: str, grupa: str | None, tekst: str = _TEKST
) -> None:
    pola = {
        "token_csrf": klient.token(),
        "projekt": "",
        "nazwa_projektu": nazwa,
        "tekst": tekst,
        "wybor_grupy": "__bez__" if grupa is None else "__nowa__",
        "nazwa_grupy": grupa or "",
    }
    odpowiedz, _ = klient.post("/projekt/nowy", pola)
    assert odpowiedz.status == 303
    _czekaj(rejestr)


def _grupy_w_checkpoincie(konfiguracja: Konfiguracja, nazwa: str) -> list[str | None]:
    checkpoint = wczytaj(ustal_uklad(konfiguracja.katalog_wynikow, nazwa).checkpoint)
    assert checkpoint is not None
    return [wejscie.grupa for wejscie in checkpoint.wejscia]


# --- trasa zwracająca grupy projektu ---------------------------------------


def test_trasa_grup_zwraca_grupy_projektu_i_ostatnia_jako_domyslna(srodowisko) -> None:
    klient, rejestr, _, _ = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt A", "Zwierzęta")

    odpowiedz, tresc = klient.get("/projekt/Projekt%20A/grupy", json_zadany=True)

    assert odpowiedz.status == 200
    assert json.loads(tresc) == {"grupy": ["Zwierzęta"], "domyslna": "Zwierzęta"}


def test_trasa_grup_dla_projektu_bez_grup_zwraca_pusta_liste(srodowisko) -> None:
    klient, rejestr, _, _ = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt B", None)

    _, tresc = klient.get("/projekt/Projekt%20B/grupy", json_zadany=True)

    assert json.loads(tresc) == {"grupy": [], "domyslna": ""}


@pytest.mark.parametrize("nazwa", ["Nie%20ma%20takiego", _NAZWA_ZLA, "..%2F..%2Fx"])
def test_trasa_grup_dla_nieistniejacego_projektu_daje_404_a_nie_500(srodowisko, nazwa: str) -> None:
    klient, _, _, _ = srodowisko

    odpowiedz, _ = klient.get(f"/projekt/{nazwa}/grupy", json_zadany=True)

    assert odpowiedz.status == 404


def test_trasa_grup_dla_uszkodzonego_checkpointu_daje_pusta_liste_a_nie_500(srodowisko) -> None:
    klient, _, konfiguracja, _ = srodowisko
    katalog = konfiguracja.katalog_wynikow / "Zepsuty"
    katalog.mkdir(parents=True)
    (katalog / "checkpoint.json").write_text("to nie jest json", encoding="utf-8")

    odpowiedz, tresc = klient.get("/projekt/Zepsuty/grupy", json_zadany=True)

    assert odpowiedz.status == 200
    assert json.loads(tresc) == {"grupy": [], "domyslna": ""}


def test_nazwy_grup_trafiaja_do_strony_wylacznie_jako_tekst_z_escapowaniem(srodowisko) -> None:
    klient, rejestr, _, aktywny = srodowisko
    zlosliwa = "<script>alert(1)</script>"
    _nowy_projekt(klient, rejestr, "Projekt C", zlosliwa)
    aktywny.ustaw("Projekt C")

    _, json_grup = klient.get("/projekt/Projekt%20C/grupy", json_zadany=True)
    odpowiedz, strona = klient.get("/")

    assert json.loads(json_grup)["grupy"] == [zlosliwa]
    assert odpowiedz.status == 200
    assert "<script>alert(1)</script>" not in strona
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in strona


def test_strona_glowna_zaznacza_aktywny_projekt_i_jego_grupy(srodowisko) -> None:
    klient, rejestr, _, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt D", "Wiedza")
    aktywny.ustaw("Projekt D")

    _, strona = klient.get("/")

    assert '<option value="Projekt D" selected>Projekt D, zakończony</option>' in strona
    assert '<option value="g:Wiedza" selected>Wiedza</option>' in strona
    assert "Aktywny projekt skrótu: Projekt D." in strona


# --- wysyłanie formularza ---------------------------------------------------


def test_nowy_projekt_bez_grupy_dziala_i_nie_zmienia_aktywnego_projektu(srodowisko) -> None:
    klient, rejestr, konfiguracja, aktywny = srodowisko
    aktywny.ustaw("Inny projekt")

    _nowy_projekt(klient, rejestr, "Nowy bez grupy", None)

    assert _grupy_w_checkpoincie(konfiguracja, "Nowy bez grupy") == [None]
    assert aktywny.aktualny() == "Inny projekt"


def test_nowy_projekt_z_nowa_grupa_zapisuje_grupe(srodowisko) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko

    _nowy_projekt(klient, rejestr, "Nowy z grupa", "Wiedza")

    assert _grupy_w_checkpoincie(konfiguracja, "Nowy z grupa") == ["Wiedza"]


def test_istniejacy_projekt_z_istniejaca_grupa_dodaje_zrodlo_i_ustawia_aktywny(srodowisko) -> None:
    klient, rejestr, konfiguracja, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt E", "Wiedza")

    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "Projekt E",
            "nazwa_projektu": "",
            "tekst": "Drugi, inny tekst dosłany do tego samego projektu i tej samej grupy.",
            "wybor_grupy": "g:Wiedza",
            "nazwa_grupy": "",
        },
    )
    _czekaj(rejestr)

    assert odpowiedz.status == 303
    assert odpowiedz.getheader("Location") == "/projekt/Projekt%20E"
    assert _grupy_w_checkpoincie(konfiguracja, "Projekt E") == ["Wiedza", "Wiedza"]
    assert aktywny.aktualny() == "Projekt E"


def test_istniejacy_projekt_z_nowa_grupa_dodaje_ja_do_projektu(srodowisko) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt F", "Wiedza")

    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "Projekt F",
            "tekst": "Tekst do zupełnie nowej grupy tematycznej tego samego projektu.",
            "wybor_grupy": "__nowa__",
            "nazwa_grupy": "Druga",
        },
    )
    _czekaj(rejestr)

    assert odpowiedz.status == 303
    assert _grupy_w_checkpoincie(konfiguracja, "Projekt F") == ["Wiedza", "Druga"]


@pytest.mark.parametrize(
    ("pola", "komunikat"),
    [
        (
            {"projekt": "", "nazwa_projektu": "", "wybor_grupy": "__bez__"},
            "Nazwa nowego projektu jest wymagana.",
        ),
        (
            {"projekt": "", "nazwa_projektu": "X", "wybor_grupy": "__nowa__", "nazwa_grupy": ""},
            "Nazwa nowej grupy jest wymagana.",
        ),
        (
            {"projekt": "Nie ma takiego", "wybor_grupy": "__bez__"},
            "nie istnieje",
        ),
        (
            {"projekt": _NAZWA_ZLA, "wybor_grupy": "__bez__"},
            "nie istnieje",
        ),
        (
            {"projekt": "", "nazwa_projektu": _NAZWA_ZLA, "wybor_grupy": "__bez__"},
            "zarezerwowan",
        ),
        (
            {"projekt": "", "nazwa_projektu": "X", "wybor_grupy": "g:Cos"},
            "Wybrana grupa nie istnieje w tym projekcie.",
        ),
        (
            {"projekt": "", "nazwa_projektu": "X", "wybor_grupy": "cokolwiek"},
            "Wybierz grupę z listy.",
        ),
    ],
)
def test_bledy_walidacji_po_stronie_serwera_wracaja_na_strone_glowna(
    srodowisko, pola: dict[str, str], komunikat: str
) -> None:
    klient, _, konfiguracja, _ = srodowisko
    wszystkie = {"token_csrf": klient.token(), "tekst": _TEKST, **pola}

    odpowiedz, strona = klient.post("/projekt/nowy", wszystkie)

    assert odpowiedz.status == 400
    assert komunikat in strona
    assert 'id="bledy-formularza"' in strona
    assert not konfiguracja.katalog_wynikow.exists() or not any(
        konfiguracja.katalog_wynikow.iterdir()
    )


def test_formularz_bez_zadnego_zrodla_daje_blad_przy_polu_tekstu(srodowisko) -> None:
    klient, _, _, _ = srodowisko

    odpowiedz, strona = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "",
            "nazwa_projektu": "Pusty",
            "wybor_grupy": "__bez__",
        },
    )

    assert odpowiedz.status == 400
    assert "Podaj przynajmniej jedno źródło" in strona


def test_istniejacy_projekt_z_uszkodzonym_checkpointem_jest_odrzucony(srodowisko) -> None:
    klient, _, konfiguracja, _ = srodowisko
    katalog = konfiguracja.katalog_wynikow / "Zepsuty"
    katalog.mkdir(parents=True)
    (katalog / "checkpoint.json").write_text("to nie jest json", encoding="utf-8")

    odpowiedz, strona = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "projekt": "Zepsuty",
            "tekst": _TEKST,
            "wybor_grupy": "__bez__",
        },
    )

    assert odpowiedz.status == 400
    assert "Checkpoint projektu jest uszkodzony." in strona


def test_wysylanie_bez_tokenu_csrf_jest_odrzucane(srodowisko) -> None:
    klient, _, _, _ = srodowisko

    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {"token_csrf": "zly", "projekt": "", "nazwa_projektu": "X", "tekst": _TEKST},
    )

    assert odpowiedz.status == 403


# --- aktywny projekt skrótu wybierany listą ---------------------------------


def test_wybor_projektu_na_liscie_ustawia_aktywny_projekt_i_zwraca_json(srodowisko) -> None:
    klient, rejestr, _, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt G", "Wiedza")
    assert aktywny.aktualny() is None

    odpowiedz, tresc = klient.post_urlencoded(
        f"/projekt/{quote('Projekt G', safe='')}/aktywny-skrot",
        {"token_csrf": klient.token()},
        json_zadany=True,
    )

    assert odpowiedz.status == 200
    assert json.loads(tresc) == {"aktywny": "Projekt G"}
    assert aktywny.aktualny() == "Projekt G"


def test_zmiana_aktywnego_projektu_wymaga_tokenu_csrf(srodowisko) -> None:
    klient, rejestr, _, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt H", None)

    odpowiedz, _ = klient.post_urlencoded(
        "/projekt/Projekt%20H/aktywny-skrot", {"token_csrf": "zly"}, json_zadany=True
    )

    assert odpowiedz.status == 403
    assert aktywny.aktualny() is None


def test_przycisk_przejdz_do_projektu_ustawia_aktywny_projekt_i_przechodzi(srodowisko) -> None:
    klient, rejestr, _, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt I", None)

    odpowiedz, _ = klient.post_urlencoded(
        "/przejdz-do-projektu", {"token_csrf": klient.token(), "projekt": "Projekt I"}
    )

    assert odpowiedz.status == 303
    assert odpowiedz.getheader("Location") == "/projekt/Projekt%20I"
    assert aktywny.aktualny() == "Projekt I"


def test_przycisk_przejdz_przy_nowym_projekcie_daje_komunikat_i_nie_zmienia_aktywnego(
    srodowisko,
) -> None:
    klient, rejestr, _, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt J", None)
    aktywny.ustaw("Projekt J")

    odpowiedz, strona = klient.post_urlencoded(
        "/przejdz-do-projektu",
        {"token_csrf": klient.token(), "projekt": "", "tekst": "Wpisany tekst zostaje."},
    )

    assert odpowiedz.status == 400
    assert "Wybierz istniejący projekt, żeby do niego przejść." in strona
    assert "Wpisany tekst zostaje." in strona
    assert aktywny.aktualny() == "Projekt J"


def test_przejscie_do_nieistniejacego_projektu_przyciskiem_daje_404(srodowisko) -> None:
    klient, _, _, aktywny = srodowisko

    odpowiedz, strona = klient.post_urlencoded(
        "/przejdz-do-projektu", {"token_csrf": klient.token(), "projekt": "Nie ma takiego"}
    )

    assert odpowiedz.status == 404
    assert "Nie ma projektu o nazwie" in strona
    assert aktywny.aktualny() is None


def test_przejscie_przyciskiem_bez_tokenu_csrf_jest_odrzucane(srodowisko) -> None:
    klient, rejestr, _, aktywny = srodowisko
    _nowy_projekt(klient, rejestr, "Projekt K", None)

    odpowiedz, _ = klient.post_urlencoded(
        "/przejdz-do-projektu", {"token_csrf": "zly", "projekt": "Projekt K"}
    )

    assert odpowiedz.status == 403
    assert aktywny.aktualny() is None
