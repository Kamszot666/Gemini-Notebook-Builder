"""Testy serwera: otwieranie plików wynikowych, podgląd i przycisk aktywnego projektu.

Projekt powstaje prawdziwym przebiegiem przez formularz strony głównej. Otwarcie
pliku w aplikacji domyślnej jest podmieniane, żeby test nigdy nie uruchamiał
programów na komputerze: sprawdzana jest cała reszta, czyli którą ścieżkę serwer
przekazałby systemowi i kiedy odmawia.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.persistence.projekt import UkladProjektu, ustal_uklad
from gnb.ui import serwer
from gnb.ui.podglad_markdown import NAGLOWEK_POLITYKI_PODGLADU
from gnb.ui.serwer import zbuduj_serwer
from gnb.ui.zadania import RejestrZadan

_GRANICA = "----TestGranicaPlikow"
_NAZWA = "Projekt Plikow"
_INNY = "Drugi Projekt"
_TEKST = "Pierwsze źródło opowiada o porządkowaniu materiałów przed importem do bazy."


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
        naglowki_dodatkowe: dict[str, str] | None = None,
    ) -> tuple[http.client.HTTPResponse, bytes]:
        polaczenie = http.client.HTTPConnection(self._host, self._port, timeout=5)
        naglowki: dict[str, str] = dict(naglowki_dodatkowe or {})
        if self.ciasteczko:
            naglowki["Cookie"] = self.ciasteczko
        if cialo is not None:
            naglowki["Content-Type"] = f"multipart/form-data; boundary={_GRANICA}"
            naglowki["Content-Length"] = str(len(cialo))
        polaczenie.request(metoda, sciezka, body=cialo, headers=naglowki)
        odpowiedz = polaczenie.getresponse()
        surowe = odpowiedz.getheader("Set-Cookie")
        if surowe:
            self.ciasteczko = surowe.split(";", 1)[0]
        return odpowiedz, odpowiedz.read()

    def get(self, sciezka: str) -> tuple[http.client.HTTPResponse, str]:
        odpowiedz, tresc = self._wyslij("GET", sciezka)
        return odpowiedz, tresc.decode("utf-8")

    def get_bajty(self, sciezka: str) -> tuple[http.client.HTTPResponse, bytes]:
        return self._wyslij("GET", sciezka)

    def post(
        self, sciezka: str, pola: dict[str, str], *, json_odpowiedz: bool = False
    ) -> tuple[http.client.HTTPResponse, str]:
        czesci = "".join(
            f'--{_GRANICA}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'
            for nazwa, wartosc in pola.items()
        )
        cialo = (czesci + f"--{_GRANICA}--\r\n").encode("utf-8")
        naglowki = {"Accept": "application/json"} if json_odpowiedz else None
        odpowiedz, tresc = self._wyslij("POST", sciezka, cialo, naglowki)
        return odpowiedz, tresc.decode("utf-8")

    def token(self) -> str:
        return self.ciasteczko.split("=", 1)[1] if self.ciasteczko else ""


@pytest.fixture
def srodowisko(
    tmp_path: Path,
) -> Iterator[tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer]]:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    rejestr = RejestrZadan()
    instancja = zbuduj_serwer(konfiguracja, rejestr)
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    klient = _Klient(str(instancja.server_address[0]), int(instancja.server_address[1]))
    klient.get("/")
    try:
        yield klient, rejestr, konfiguracja, instancja
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


def _utworz_projekt(
    klient: _Klient, rejestr: RejestrZadan, nazwa: str = _NAZWA, tresc: str = _TEKST
) -> None:
    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "nazwa_projektu": nazwa,
            "tekst": tresc,
            "wybor_grupy": "__nowa__",
            "nazwa_grupy": "G",
        },
    )
    assert odpowiedz.status == 303
    _czekaj(rejestr)


def _uklad(konfiguracja: Konfiguracja, nazwa: str = _NAZWA) -> UkladProjektu:
    return ustal_uklad(konfiguracja.katalog_wynikow, nazwa)


def _plik_wynikowy(konfiguracja: Konfiguracja) -> Path:
    (plik,) = _uklad(konfiguracja).pliki_wynikowe.iterdir()
    return plik


def _adres(akcja: str, nazwa: str = _NAZWA) -> str:
    return f"/projekt/{quote(nazwa, safe='')}/{akcja}"


@pytest.fixture
def otwarte(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Zapamiętuje ścieżki, które serwer chciałby otworzyć w aplikacji domyślnej."""
    otwarte: list[Path] = []

    def falszywe_otwarcie(sciezka: Path) -> str | None:
        otwarte.append(sciezka)
        return None

    monkeypatch.setattr(serwer, "otworz_plik", falszywe_otwarcie)
    return otwarte


# --- otwieranie pliku wynikowego -----------------------------------------------


def test_strona_projektu_pokazuje_przycisk_otwarcia_dla_pliku_wynikowego(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    nazwa_pliku = _plik_wynikowy(konfiguracja).name

    odpowiedz, strona = klient.get(_adres(""))

    assert odpowiedz.status == 200
    assert nazwa_pliku.endswith(".md")
    assert f"Otwórz plik {nazwa_pliku}</button>" in strona
    assert f'href="{_adres("plik")}/{quote(nazwa_pliku, safe="")}"' in strona
    assert f'action="{_adres("otworz-plik")}"' in strona


def test_otwarcie_pliku_przekazuje_systemowi_dokladna_sciezke_z_katalogu_wynikow(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    otwarte: list[Path],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)

    odpowiedz, tresc = klient.post(
        _adres("otworz-plik"),
        {"token_csrf": klient.token(), "plik": plik.name},
        json_odpowiedz=True,
    )

    assert odpowiedz.status == 200
    assert json.loads(tresc) == {
        "ok": True,
        "komunikat": f"Otwarto plik {plik.name} w aplikacji domyślnej.",
    }
    assert otwarte == [plik]


@pytest.mark.parametrize(
    "nazwa",
    [
        "checkpoint.json",
        "../checkpoint.json",
        "..\\checkpoint.json",
        "../../Drugi Projekt/checkpoint.json",
        "/etc/passwd",
        "C:\\Windows\\win.ini",
        "%2e%2e/checkpoint.json",
        "..%2fcheckpoint.json",
        "nie_ma_takiego.md",
        "",
        ".",
        "..",
    ],
)
def test_otwarcie_odrzuca_nazwy_spoza_wykazu_i_proby_przejscia_po_katalogu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    otwarte: list[Path],
    nazwa: str,
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    assert (_uklad(konfiguracja).katalog_projektu / "checkpoint.json").is_file()

    odpowiedz, tresc = klient.post(
        _adres("otworz-plik"),
        {"token_csrf": klient.token(), "plik": nazwa},
        json_odpowiedz=True,
    )

    assert odpowiedz.status == 404
    assert json.loads(tresc)["ok"] is False
    assert otwarte == []


def test_otwarcie_pliku_innego_projektu_przez_nazwe_z_wykazu_tego_projektu_jest_odrzucone(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    otwarte: list[Path],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    _utworz_projekt(klient, rejestr, _INNY, "Zupełnie inna treść drugiego projektu o podatkach.")
    nazwa_drugiego = _plik_wynikowy_projektu(konfiguracja, _INNY).name

    odpowiedz, _ = klient.post(
        _adres("otworz-plik"),
        {"token_csrf": klient.token(), "plik": nazwa_drugiego},
        json_odpowiedz=True,
    )

    assert odpowiedz.status == 404
    assert otwarte == []


def _plik_wynikowy_projektu(konfiguracja: Konfiguracja, nazwa: str) -> Path:
    (plik,) = _uklad(konfiguracja, nazwa).pliki_wynikowe.iterdir()
    return plik


def test_otwarcie_bez_tokenu_csrf_jest_odrzucone(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    otwarte: list[Path],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)

    odpowiedz, _ = klient.post(_adres("otworz-plik"), {"plik": _plik_wynikowy(konfiguracja).name})

    assert odpowiedz.status == 403
    assert otwarte == []


def test_otwarcie_w_nieistniejacym_projekcie_daje_404(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    otwarte: list[Path],
) -> None:
    klient, _rejestr, _konfiguracja, _ = srodowisko

    odpowiedz, _ = klient.post(
        _adres("otworz-plik", "Nie ma"), {"token_csrf": klient.token(), "plik": "a.md"}
    )

    assert odpowiedz.status == 404
    assert otwarte == []


def test_gdy_system_nie_moze_otworzyc_pliku_komunikat_wraca_jako_json_i_na_strone(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)
    komunikat = 'Nie udało się: <b>"brak aplikacji"</b>'
    monkeypatch.setattr(serwer, "otworz_plik", lambda _sciezka: komunikat)
    pola = {"token_csrf": klient.token(), "plik": plik.name}

    odpowiedz_json, tresc_json = klient.post(_adres("otworz-plik"), pola, json_odpowiedz=True)
    odpowiedz_html, strona = klient.post(_adres("otworz-plik"), pola)

    assert odpowiedz_json.status == 500
    assert json.loads(tresc_json) == {"ok": False, "komunikat": komunikat}
    assert odpowiedz_html.status == 500
    assert "<b>" not in strona
    assert "&lt;b&gt;" in strona
    assert 'id="komunikat-plikow" role="status"' in strona


def test_na_systemie_innym_niz_windows_otwarcie_zwraca_czytelny_komunikat(
    tmp_path: Path,
) -> None:
    import sys

    from gnb.ui import otwieranie

    wynik = otwieranie.otworz_plik(tmp_path / "plik.md")

    if sys.platform == "win32":
        assert wynik is not None  # plik nie istnieje, więc system odmawia
        assert "plik.md" in wynik
    else:
        assert wynik == otwieranie.KOMUNIKAT_NIE_WINDOWS


# --- podgląd pliku jako tekst ----------------------------------------------------


def test_podglad_pokazuje_tresc_pliku_jako_zwykly_tekst_bez_html(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)
    plik.write_text('# Tytuł\n<script>alert("x")</script>\n', encoding="utf-8")

    odpowiedz, tresc = klient.get_bajty(f"{_adres('plik')}/{quote(plik.name, safe='')}")

    assert odpowiedz.status == 200
    assert odpowiedz.getheader("Content-Type") == "text/plain; charset=utf-8"
    assert odpowiedz.getheader("X-Content-Type-Options") == "nosniff"
    assert tresc == plik.read_bytes()


@pytest.mark.parametrize(
    "fragment",
    ["checkpoint.json", "..%2Fcheckpoint.json", "..%5Ccheckpoint.json", "nie_ma.md", "%2e%2e"],
)
def test_podglad_odrzuca_nazwy_spoza_wykazu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    fragment: str,
) -> None:
    klient, rejestr, _konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)

    odpowiedz, tresc = klient.get_bajty(f"{_adres('plik')}/{fragment}")

    assert odpowiedz.status == 404
    assert b"proj-" not in tresc


# --- przycisk aktywnego projektu na stronie głównej -------------------------------


def _dwa_projekty(klient: _Klient, rejestr: RejestrZadan, instancja: ThreadingHTTPServer) -> None:
    """Tworzy dwa projekty i ustawia drugi jako aktywny, jak robi to strona projektu."""
    _utworz_projekt(klient, rejestr)
    _utworz_projekt(klient, rejestr, _INNY, "Inna treść drugiego projektu o ubezpieczeniach.")
    odpowiedz, _ = klient.post(
        _adres("aktywny-skrot", _INNY), {"token_csrf": klient.token()}, json_odpowiedz=True
    )
    assert odpowiedz.status == 200
    assert _aktywny(instancja) == _INNY


def _aktywny(instancja: ThreadingHTTPServer) -> str | None:
    return instancja.aktywny_projekt_skrotu.aktualny()  # type: ignore[attr-defined,no-any-return]


def test_przycisk_na_stronie_glownej_ustawia_projekt_z_listy_i_wraca_na_strone_glowna(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, _konfiguracja, instancja = srodowisko
    _dwa_projekty(klient, rejestr, instancja)

    odpowiedz, strona = klient.post(
        _adres("aktywny-skrot"),
        {
            "token_csrf": klient.token(),
            "projekt": _NAZWA,
            "tekst": "Niedokończony tekst użytkownika",
            "nazwa_projektu": "",
            "wybor_grupy": "__bez_grupy__",
            "nazwa_grupy": "",
        },
    )

    assert odpowiedz.status == 200
    assert _aktywny(instancja) == _NAZWA
    assert f"Aktywny projekt skrótu: {_NAZWA}." in strona
    assert "<h1>Gemini Notebook Builder</h1>" in strona
    assert "Niedokończony tekst użytkownika" in strona


def test_lista_projekt_rozstrzyga_gdy_adres_przycisku_wskazuje_inny_projekt(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    """Bez JavaScriptu adres przycisku zostaje z chwili wczytania strony."""
    klient, rejestr, _konfiguracja, instancja = srodowisko
    _dwa_projekty(klient, rejestr, instancja)

    odpowiedz, _ = klient.post(
        _adres("aktywny-skrot", _INNY),
        {"token_csrf": klient.token(), "projekt": _NAZWA},
    )

    assert odpowiedz.status == 200
    assert _aktywny(instancja) == _NAZWA


def test_przycisk_przy_nowym_projekcie_nic_nie_zmienia_i_mowi_dlaczego(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, _konfiguracja, instancja = srodowisko
    _dwa_projekty(klient, rejestr, instancja)

    odpowiedz, strona = klient.post(
        _adres("aktywny-skrot", "nowy"), {"token_csrf": klient.token(), "projekt": ""}
    )

    assert odpowiedz.status == 400
    assert _aktywny(instancja) == _INNY
    assert "Najpierw wybierz istniejący projekt z listy Projekt." in strona


def test_przycisk_aktywnego_projektu_wymaga_tokenu_csrf(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, _konfiguracja, instancja = srodowisko
    _dwa_projekty(klient, rejestr, instancja)

    odpowiedz, _ = klient.post(_adres("aktywny-skrot"), {"projekt": _NAZWA})

    assert odpowiedz.status == 403
    assert _aktywny(instancja) == _INNY


def test_trasa_aktywnego_projektu_ze_strony_projektu_dziala_jak_dawniej(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, _konfiguracja, instancja = srodowisko
    _dwa_projekty(klient, rejestr, instancja)

    odpowiedz, _ = klient.post(_adres("aktywny-skrot"), {"token_csrf": klient.token()})

    assert odpowiedz.status == 303
    assert odpowiedz.getheader("Location") == f"/projekt/{quote(_NAZWA, safe='')}"
    assert _aktywny(instancja) == _NAZWA


def test_odpowiedz_json_na_przycisk_nie_wymaga_wartosci_z_listy(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    """Skrypt strony wysyła tylko token, a projekt wynika z adresu."""
    klient, rejestr, _konfiguracja, instancja = srodowisko
    _dwa_projekty(klient, rejestr, instancja)

    odpowiedz, tresc = klient.post(
        _adres("aktywny-skrot"), {"token_csrf": klient.token()}, json_odpowiedz=True
    )

    assert odpowiedz.status == 200
    assert json.loads(tresc) == {"aktywny": _NAZWA}
    assert _aktywny(instancja) == _NAZWA


def test_postep_po_zakonczeniu_mowi_o_przejsciu_do_wynikow(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, _konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)

    odpowiedz, tresc = klient.get("/postep")

    assert odpowiedz.status == 200
    assert json.loads(tresc)["komunikat"] == "Przetwarzanie zakończone. Przechodzę do wyników."


# --- podgląd pliku MD jako strona -------------------------------------------------

_PLIK_MD = (
    "# Tytuł grupy\n\n"
    "## Sekcja pierwsza\n\nAkapit z [odnośnikiem](https://a.example/b).\n\n"
    "- punkt\n\n1. numer\n\n> cytat\n\n```\nkod\n```\n\n"
    "| Kolumna | Druga |\n| --- | --- |\n| 1 | 2 |\n"
)


def _adres_strony(plik: Path, nazwa: str = _NAZWA) -> str:
    return f"{_adres('strona', nazwa)}/{quote(plik.name, safe='')}"


def test_podglad_jako_strona_zamienia_plik_md_na_html_z_nagludkami(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)
    plik.write_text(_PLIK_MD, encoding="utf-8")

    odpowiedz, strona = klient.get(_adres_strony(plik))

    assert odpowiedz.status == 200
    assert odpowiedz.getheader("Content-Type") == "text/html; charset=utf-8"
    assert f"<title>Podgląd pliku {plik.name}</title>" in strona
    assert "<h1>Tytuł grupy</h1>" in strona
    assert "<h2>Sekcja pierwsza</h2>" in strona
    assert "<ul>" in strona and "<ol>" in strona
    assert "<th>Kolumna</th>" in strona
    assert "<blockquote>" in strona
    assert "<pre><code>kod" in strona
    assert 'rel="noopener noreferrer"' in strona
    assert f'<a href="{_adres("").rstrip("/")}">Wróć do projektu</a>' in strona


def test_strona_podgladu_ma_naglowki_bezpieczenstwa_i_nie_ma_skryptu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)
    plik.write_text(_PLIK_MD, encoding="utf-8")

    odpowiedz, strona = klient.get(_adres_strony(plik))

    assert odpowiedz.getheader("Content-Security-Policy") == NAGLOWEK_POLITYKI_PODGLADU
    assert odpowiedz.getheader("X-Content-Type-Options") == "nosniff"
    assert odpowiedz.getheader("Referrer-Policy") == "no-referrer"
    assert odpowiedz.getheader("X-Frame-Options") == "DENY"
    assert "<script" not in strona


@pytest.mark.parametrize(
    "tresc",
    [
        '# Nagłówek\n\n<script>alert("x")</script>\n',
        "# Nagłówek\n\n<img src=x onerror=alert(1)>\n",
        "# Nagłówek\n\n[klik](javascript:alert(1))\n",
        "# Nagłówek <script>alert(1)</script>\n",
        "| a | b |\n| --- | --- |\n| <img src=x onerror=alert(1)> | ok |\n",
    ],
)
def test_proba_wstrzykniecia_w_pliku_md_konczy_sie_tekstem_a_nie_znacznikiem(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    tresc: str,
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)
    plik.write_text(tresc, encoding="utf-8")

    _, strona = klient.get(_adres_strony(plik))

    assert "<script" not in strona
    assert "<img" not in strona
    assert "onerror=alert(1)>" not in strona
    assert 'href="javascript' not in strona


@pytest.mark.parametrize(
    "fragment",
    ["checkpoint.json", "..%2Fcheckpoint.json", "..%5Ccheckpoint.json", "nie_ma.md", "%2e%2e"],
)
def test_podglad_jako_strona_odrzuca_nazwy_spoza_wykazu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    fragment: str,
) -> None:
    klient, rejestr, _konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)

    odpowiedz, tresc = klient.get_bajty(f"{_adres('strona')}/{fragment}")

    assert odpowiedz.status == 404
    assert b"proj-" not in tresc


def test_podglad_jako_strona_nie_dziala_dla_pliku_innego_projektu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    _utworz_projekt(klient, rejestr, _INNY, "Inna treść drugiego projektu o ubezpieczeniach.")
    (plik_innego,) = _uklad(konfiguracja, _INNY).pliki_wynikowe.iterdir()

    odpowiedz, _ = klient.get(_adres_strony(plik_innego, _NAZWA))

    assert odpowiedz.status == 404


def test_podglad_jako_strona_w_nieistniejacym_projekcie_daje_404(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, *_ = srodowisko

    odpowiedz, _ = klient.get(f"{_adres('strona', 'Nie ma takiego')}/plik.md")

    assert odpowiedz.status == 404


def test_podglad_jako_strona_odrzuca_plik_txt(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik_md = _plik_wynikowy(konfiguracja)
    plik_txt = plik_md.with_suffix(".txt")
    plik_txt.write_text("Zwykły tekst.", encoding="utf-8")
    checkpoint = _uklad(konfiguracja).checkpoint
    checkpoint.write_text(
        checkpoint.read_text(encoding="utf-8").replace(plik_md.name, plik_txt.name),
        encoding="utf-8",
    )

    odpowiedz, _ = klient.get(_adres_strony(plik_txt))

    assert odpowiedz.status == 404


def test_zbyt_duzy_plik_nie_jest_zamieniany_na_strone(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)
    monkeypatch.setattr(serwer, "MAKSYMALNY_ROZMIAR_PODGLADU_STRONY", 10)

    odpowiedz, tresc = klient.get(_adres_strony(plik))

    assert odpowiedz.status == 413
    assert "podglądu jako tekst" in tresc


def test_strona_projektu_ma_przy_pliku_md_trzy_sposoby_otwarcia(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja, ThreadingHTTPServer],
) -> None:
    klient, rejestr, konfiguracja, _ = srodowisko
    _utworz_projekt(klient, rejestr)
    plik = _plik_wynikowy(konfiguracja)

    _, strona = klient.get(_adres(""))

    assert f"Otwórz plik {plik.name}</button>" in strona
    assert f"Podgląd pliku {plik.name} jako strona</a>" in strona
    assert f"Podgląd pliku {plik.name} jako tekst</a>" in strona
    assert strona.index("jako strona</a>") < strona.index("jako tekst</a>")
    assert f'href="{_adres("strona")}/{quote(plik.name, safe="")}"' in strona
