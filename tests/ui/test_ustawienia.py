"""Testy strony ustawień: opis pól, widok zakładek i zapis przez serwer.

Serwer działa na porcie wybranym przez system, z plikiem konfiguracji w katalogu
tymczasowym. Zmienne środowiskowe ``GNB_*`` użytkownika są usuwane na czas testu,
żeby nie zmieniały wyniku.
"""

from __future__ import annotations

import http.client
import re
import threading
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlencode

import pytest

from gnb.core.konfiguracja import Konfiguracja, pola_konfiguracji, wczytaj_konfiguracje
from gnb.ui import widoki_ustawien
from gnb.ui.serwer import zbuduj_serwer
from gnb.ui.ustawienia import (
    MODELE_TRANSKRYPCJI,
    ZAKLADKI,
    Rodzaj,
    odczytaj_zakladke,
    pola_bez_zakladki,
    pole_ustawien,
    wartosc_domyslna_slowami,
    zakladka_o_identyfikatorze,
)
from gnb.ui.widoki import strona_glowna
from gnb.ui.zadania import RejestrZadan

_PLIK = """\
# Komentarz użytkownika
limit_zrodel = 50
klucz_obcy = "zostaje"
"""


def _html_zakladki(zawartosc: str, identyfikator: str) -> str:
    poczatek = zawartosc.index(f'id="panel-{identyfikator}"')
    koniec = zawartosc.index("</section>", poczatek)
    return zawartosc[poczatek:koniec]


# --- opis pól --------------------------------------------------------------


def test_kazde_pole_konfiguracji_jest_w_dokladnie_jednej_zakladce() -> None:
    umieszczone = [pole.nazwa for zakladka in ZAKLADKI for pole in zakladka.pola]

    assert pola_bez_zakladki() == ()
    assert sorted(umieszczone) == sorted(pola_konfiguracji())
    assert len(umieszczone) == len(set(umieszczone))


def test_zakladka_wyglad_istnieje_i_nie_ma_pustych_zakladek() -> None:
    assert all(zakladka.pola for zakladka in ZAKLADKI)
    assert "wyglad" in {zakladka.identyfikator for zakladka in ZAKLADKI}
    identyfikatory = [zakladka.identyfikator for zakladka in ZAKLADKI]
    assert len(identyfikatory) == len(set(identyfikatory))


def test_aktywny_projekt_skrotu_nie_jest_polem_konfiguracji() -> None:
    assert not any("aktywny" in nazwa for nazwa in pola_konfiguracji())
    tekst = " ".join(pole.etykieta + pole.opis for zakladka in ZAKLADKI for pole in zakladka.pola)
    assert "stan_skrotu" not in tekst


def test_domyslny_model_transkrypcji_jest_na_liscie_i_zgadza_sie_z_kodem() -> None:
    assert Konfiguracja().transkrypcja_model in MODELE_TRANSKRYPCJI
    assert wartosc_domyslna_slowami(pole_ustawien("transkrypcja_model")) == "medium"


def test_pola_wymagajace_restartu_sa_wskazane() -> None:
    restart = {pole.nazwa for zakladka in ZAKLADKI for pole in zakladka.pola if pole.restart}

    assert {"port_nasluchu", "adres_nasluchu", "globalny_skrot_wlaczony"} <= restart
    assert "limit_zrodel" not in restart


def test_adres_nasluchu_jest_tylko_do_odczytu() -> None:
    assert pole_ustawien("adres_nasluchu").rodzaj is Rodzaj.TYLKO_ODCZYT


def test_odczyt_zakladki_zamienia_typy_i_brak_pola_wyboru_oznacza_falsz() -> None:
    zakladka = zakladka_o_identyfikatorze("pobieranie")
    assert zakladka is not None

    wartosci, bledy = odczytaj_zakladke(
        zakladka,
        {"limit_czasu_sekundy": "12,5", "liczba_ponowien": "2", "respektuj_robots": "1"},
        frozenset(),
    )

    assert not [blad for blad in bledy if blad.pole in ("limit_czasu_sekundy", "liczba_ponowien")]
    assert wartosci["limit_czasu_sekundy"] == 12.5
    assert wartosci["liczba_ponowien"] == 2
    assert wartosci["respektuj_robots"] is True
    assert wartosci["uzywaj_cache"] is False


def test_odczyt_zakladki_zbiera_wszystkie_bledy_liczb_i_pomija_zablokowane() -> None:
    zakladka = zakladka_o_identyfikatorze("limity")
    assert zakladka is not None

    wartosci, bledy = odczytaj_zakladke(
        zakladka,
        {"limit_zrodel": "abc", "limit_adresow_z_pliku": "x", "bezpieczny_limit_slow": "5"},
        frozenset({"bezpieczny_limit_mb"}),
    )

    assert {blad.pole for blad in bledy} == {"limit_zrodel", "limit_adresow_z_pliku"}
    assert "bezpieczny_limit_mb" not in wartosci
    assert wartosci["bezpieczny_limit_slow"] == 5


# --- widok -----------------------------------------------------------------


def _strona(**nadpisania: object) -> str:
    argumenty: dict[str, object] = {
        "konfiguracja": Konfiguracja(),
        "zablokowane": {},
        "token_csrf": "tokentestowy",
        "sciezka_pliku": "konfiguracja.toml",
    }
    argumenty.update(nadpisania)
    return widoki_ustawien.strona_ustawien(**argumenty)  # type: ignore[arg-type]


def test_widok_ma_wzorzec_zakladek_i_panel_dla_kazdej() -> None:
    strona = _strona()

    assert strona.count('<div role="tablist"') == 1
    assert strona.count('<button type="button" role="tab"') == len(ZAKLADKI)
    assert strona.count('<section role="tabpanel"') == len(ZAKLADKI)
    for zakladka in ZAKLADKI:
        assert f'aria-controls="panel-{zakladka.identyfikator}"' in strona
        assert f'<h2 id="naglowek-{zakladka.identyfikator}">{zakladka.tytul}</h2>' in strona
    # Lista zakładek jest ukryta, dopóki skrypt jej nie pokaże, więc bez
    # JavaScriptu zostają widoczne wszystkie panele.
    assert re.search(r'<div role="tablist"[^>]* hidden', strona)
    assert '<section role="tabpanel"' in strona
    assert (
        'role="tabpanel" id="panel-limity" aria-labelledby="naglowek-limity" hidden' not in strona
    )


def test_kazde_pole_ma_dokladnie_jedna_kontrolke_z_etykieta_i_opisem() -> None:
    strona = _strona()

    for zakladka in ZAKLADKI:
        for pole in zakladka.pola:
            identyfikator = f"pole-{pole.nazwa}"
            if pole.rodzaj is Rodzaj.TYLKO_ODCZYT:
                assert f'id="{identyfikator}-opis"' in strona
                continue
            assert strona.count(f'for="{identyfikator}"') == 1, pole.nazwa
            assert strona.count(f'id="{identyfikator}"') == 1, pole.nazwa
            assert f'aria-describedby="{identyfikator}-opis"' in strona, pole.nazwa
            assert f'id="{identyfikator}-opis"' in strona, pole.nazwa


def test_pola_tekstowe_nie_maja_placeholder_ani_aria_label() -> None:
    strona = _strona()

    pola_tekstowe = re.findall(r'<input type="text"[^>]*>', strona)
    assert pola_tekstowe
    for pole in pola_tekstowe:
        assert "placeholder" not in pole
        assert "aria-label" not in pole
    assert "placeholder" not in strona


def test_kontrolki_pasuja_do_typu_pola() -> None:
    strona = _strona()

    assert re.search(r'<input type="checkbox" id="pole-respektuj_robots"[^>]* checked', strona)
    assert re.search(
        r'<input type="number" id="pole-port_nasluchu"[^>]*min="1"[^>]*max="65535"', strona
    )
    assert '<select id="pole-transkrypcja_model"' in strona
    assert re.search(r'<input type="text" id="pole-sciezka_tesseract"', strona)
    assert re.search(
        r'<input type="number" id="pole-limit_czasu_sekundy" name="limit_czasu_sekundy" step="any"',
        strona,
    )


def test_adres_nasluchu_nie_ma_kontrolki() -> None:
    strona = _strona()

    assert 'name="adres_nasluchu"' not in strona
    assert "Adres nasłuchu: 127.0.0.1" in strona


def test_opis_pola_podaje_wartosc_domyslna_i_moment_dzialania_zmiany() -> None:
    strona = _strona()

    opis_portu = re.search(r'id="pole-port_nasluchu-opis">([^<]*)<', strona)
    assert opis_portu is not None
    assert "Wartość domyślna: 8765." in opis_portu.group(1)
    assert "dopiero po ponownym uruchomieniu serwera" in opis_portu.group(1)
    opis_limitu = re.search(r'id="pole-limit_zrodel-opis">([^<]*)<', strona)
    assert opis_limitu is not None
    assert "od następnego przebiegu" in opis_limitu.group(1)


def test_opis_modelu_transkrypcji_nie_podaje_liczb_pamieci_ani_czasow() -> None:
    strona = _strona()

    opis = re.search(r'id="pole-transkrypcja_model-opis">([^<]*)<', strona)
    assert opis is not None
    tekst = opis.group(1)
    assert "mocniejszego komputera" in tekst
    assert "mniej dokładny" in tekst
    assert not re.search(r"\d+\s*(GB|MB|s\b|min)", tekst)
    assert "Wartość domyślna: medium." in tekst


def test_pole_ze_zmiennej_srodowiskowej_jest_tylko_do_odczytu_z_nazwa_zmiennej() -> None:
    konfiguracja = Konfiguracja(limit_zrodel=77)
    strona = _strona(
        konfiguracja=konfiguracja, zablokowane={"limit_zrodel": ("GNB_LIMIT_ZRODEL", "77")}
    )

    assert 'name="limit_zrodel"' not in strona
    assert "GNB_LIMIT_ZRODEL" in strona
    assert "Limit liczby źródeł w notatniku: 77" in strona


def test_kazda_zakladka_ma_zapis_i_przywracanie_z_tokenem() -> None:
    strona = _strona()

    assert strona.count('<form method="post" action="/ustawienia/zapisz"') == len(ZAKLADKI)
    assert strona.count(">Zapisz ustawienia</button>") == len(ZAKLADKI)
    assert strona.count(">Przywróć ustawienia domyślne tej zakładki</button>") == len(ZAKLADKI)
    # Każda zakładka ma token w swoim formularzu, a zakładka Wygląd także w formularzu
    # przywracania schematu.
    assert strona.count('value="tokentestowy"') == len(ZAKLADKI) + 1


def test_wartosc_z_konfiguracji_jest_escapowana() -> None:
    konfiguracja = Konfiguracja(nazwa_klienta='"><script>alert(1)</script>')

    strona = _strona(konfiguracja=konfiguracja)

    assert "<script>alert(1)</script>" not in strona
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in strona


def test_blad_pola_jest_powiazany_przez_aria_invalid_i_describedby() -> None:
    from gnb.ui.widoki import BladPola

    strona = _strona(
        bledy=[BladPola("limit_zrodel", "Pole musi być liczbą.")],
        wpisane={"limit_zrodel": "abc"},
        zakladka_z_bledami="limity",
    )

    pole = re.search(r'<input type="number" id="pole-limit_zrodel"[^>]*>', strona)
    assert pole is not None
    assert 'aria-invalid="true"' in pole.group(0)
    assert "pole-limit_zrodel-blad" in pole.group(0)
    assert 'value="abc"' in pole.group(0)
    assert 'id="bledy-formularza"' in strona
    assert 'href="#pole-limit_zrodel"' in strona


def test_komunikat_o_zapisie_jest_regionem_statusu() -> None:
    strona = _strona(komunikat="Zapisano ustawienia zakładki Limity notatnika.")

    assert re.search(r'id="komunikat-ustawien" role="status" aria-live="polite"', strona)


def test_strona_glowna_ma_odnosnik_do_ustawien() -> None:
    strona = strona_glowna(projekty=[], token_csrf="t")

    assert '<a href="/ustawienia">Ustawienia</a>' in strona


# --- serwer ----------------------------------------------------------------


class _Klient:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self.ciasteczko: str | None = None

    def _wyslij(
        self, metoda: str, sciezka: str, cialo: bytes | None = None
    ) -> tuple[http.client.HTTPResponse, str]:
        polaczenie = http.client.HTTPConnection(self._host, self._port, timeout=5)
        naglowki: dict[str, str] = {}
        if self.ciasteczko:
            naglowki["Cookie"] = self.ciasteczko
        if cialo is not None:
            naglowki["Content-Type"] = "application/x-www-form-urlencoded"
            naglowki["Content-Length"] = str(len(cialo))
        polaczenie.request(metoda, sciezka, body=cialo, headers=naglowki)
        odpowiedz = polaczenie.getresponse()
        surowe = odpowiedz.getheader("Set-Cookie")
        if surowe:
            self.ciasteczko = surowe.split(";", 1)[0]
        return odpowiedz, odpowiedz.read().decode("utf-8")

    def get(self, sciezka: str) -> tuple[http.client.HTTPResponse, str]:
        return self._wyslij("GET", sciezka)

    def post(
        self, sciezka: str, pola: dict[str, str], *, token: str | None = None
    ) -> tuple[http.client.HTTPResponse, str]:
        dane = dict(pola)
        dane["token_csrf"] = self.token() if token is None else token
        return self._wyslij("POST", sciezka, urlencode(dane).encode("utf-8"))

    def token(self) -> str:
        return self.ciasteczko.split("=", 1)[1] if self.ciasteczko else ""


@pytest.fixture(autouse=True)
def _bez_zmiennych_gnb(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for nazwa in list(os.environ):
        if nazwa.startswith("GNB_"):
            monkeypatch.delenv(nazwa)


@pytest.fixture
def srodowisko(tmp_path: Path) -> Iterator[tuple[_Klient, Path, RejestrZadan, object]]:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text(_PLIK, encoding="utf-8")
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    rejestr = RejestrZadan()
    instancja = zbuduj_serwer(konfiguracja, rejestr, sciezka_konfiguracji=plik)
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    klient = _Klient(str(instancja.server_address[0]), int(instancja.server_address[1]))
    klient.get("/")
    try:
        yield klient, plik, rejestr, instancja
    finally:
        instancja.shutdown()
        instancja.server_close()


def _formularz_zakladki(identyfikator: str, **nadpisania: str) -> dict[str, str]:
    """Wartości zakładki takie, jakie przeglądarka wysłałaby bez zmian, z nadpisaniami."""
    konfiguracja = wczytaj_konfiguracje(None or Path("brak.toml"), srodowisko={})
    zakladka = zakladka_o_identyfikatorze(identyfikator)
    assert zakladka is not None
    pola: dict[str, str] = {"zakladka": identyfikator}
    for pole in zakladka.pola:
        wartosc = getattr(konfiguracja, pole.nazwa)
        if pole.rodzaj is Rodzaj.TYLKO_ODCZYT:
            continue
        if pole.rodzaj is Rodzaj.LOGICZNE:
            if wartosc:
                pola[pole.nazwa] = "1"
        elif pole.rodzaj is Rodzaj.FORMATY:
            if "md" in wartosc:
                pola[pole.nazwa] = "1"
        elif isinstance(wartosc, (tuple, list)):
            pola[pole.nazwa] = ", ".join(wartosc)
        else:
            pola[pole.nazwa] = str(wartosc)
    pola.update(nadpisania)
    return pola


def test_get_ustawienia_pokazuje_strone(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko

    odpowiedz, tresc = klient.get("/ustawienia")

    assert odpowiedz.status == 200
    assert 'role="tablist"' in tresc
    assert "Limit liczby źródeł w notatniku" in tresc
    assert 'value="50"' in tresc


def test_zapis_zmienia_plik_zachowuje_komentarze_i_klucze_obce_i_przekierowuje(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko

    odpowiedz, _ = klient.post(
        "/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="120")
    )

    assert odpowiedz.status == 303
    lokalizacja = odpowiedz.getheader("Location") or ""
    assert lokalizacja.startswith("/ustawienia?zakladka=limity&wynik=zapisano")
    tresc = plik.read_text(encoding="utf-8")
    assert "# Komentarz użytkownika" in tresc
    assert 'klucz_obcy = "zostaje"' in tresc
    assert wczytaj_konfiguracje(plik, srodowisko={}).limit_zrodel == 120
    _, strona = klient.get(lokalizacja)
    assert "Zapisano ustawienia zakładki Limity notatnika." in strona
    assert 'value="120"' in strona


def test_zapis_wlacza_ustawienie_dzialajace_od_razu_i_zostawia_restart_bez_zmiany(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, instancja = srodowisko
    port_przed = instancja.konfiguracja.port_nasluchu  # type: ignore[attr-defined]

    klient.post("/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="120"))
    klient.post("/ustawienia/zapisz", _formularz_zakladki("serwer", port_nasluchu="9123"))

    assert instancja.konfiguracja.limit_zrodel == 120  # type: ignore[attr-defined]
    assert instancja.konfiguracja.port_nasluchu == port_przed  # type: ignore[attr-defined]
    assert wczytaj_konfiguracje(plik, srodowisko={}).port_nasluchu == 9123


def test_niepoprawna_wartosc_daje_400_z_bledem_przy_polu_i_nie_zmienia_pliku(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, strona = klient.post(
        "/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="-3")
    )

    assert odpowiedz.status == 400
    assert plik.read_text(encoding="utf-8") == przed
    assert 'id="bledy-formularza"' in strona
    assert 'href="#pole-limit_zrodel"' in strona
    assert 'value="-3"' in strona


def test_tekst_zamiast_liczby_daje_400_i_nie_zmienia_pliku(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, strona = klient.post(
        "/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="abc")
    )

    assert odpowiedz.status == 400
    assert plik.read_text(encoding="utf-8") == przed
    assert "musi być liczbą całkowitą" in strona


def test_zly_token_csrf_daje_403_i_nie_zmienia_pliku(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, _ = klient.post(
        "/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="120"), token="zly"
    )

    assert odpowiedz.status == 403
    assert plik.read_text(encoding="utf-8") == przed


def test_zapis_w_trakcie_przetwarzania_jest_odrzucany(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, rejestr, _instancja = srodowisko
    przed = plik.read_text(encoding="utf-8")
    czeka = threading.Event()
    rejestr.uruchom("Projekt", lambda _postep: czeka.wait(5) and None)  # type: ignore[arg-type,return-value]
    try:
        odpowiedz, strona = klient.post(
            "/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="120")
        )
    finally:
        czeka.set()

    assert odpowiedz.status == 409
    assert "Poczekaj na jego zakończenie" in strona
    assert plik.read_text(encoding="utf-8") == przed


def test_przywracanie_usuwa_klucze_zakladki_i_zostawia_reszte(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, instancja = srodowisko

    odpowiedz, _ = klient.post("/ustawienia/przywroc", {"zakladka": "limity"})

    assert odpowiedz.status == 303
    assert "wynik=przywrocono" in (odpowiedz.getheader("Location") or "")
    tresc = plik.read_text(encoding="utf-8")
    assert "limit_zrodel" not in tresc
    assert 'klucz_obcy = "zostaje"' in tresc
    assert instancja.konfiguracja.limit_zrodel == 100  # type: ignore[attr-defined]


def test_pole_ze_zmiennej_srodowiskowej_nie_jest_zapisywane(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    monkeypatch.setenv("GNB_LIMIT_ZRODEL", "77")

    _, strona = klient.get("/ustawienia")
    odpowiedz, _ = klient.post(
        "/ustawienia/zapisz", _formularz_zakladki("limity", limit_zrodel="120")
    )

    assert 'name="limit_zrodel"' not in strona
    assert "GNB_LIMIT_ZRODEL" in strona
    assert odpowiedz.status == 303
    assert wczytaj_konfiguracje(plik, srodowisko={}).limit_zrodel == 50


def test_nieznana_zakladka_daje_404(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, _plik, _rejestr, _instancja = srodowisko

    odpowiedz, _ = klient.post("/ustawienia/zapisz", {"zakladka": "nie-ma"})

    assert odpowiedz.status == 404


def test_komunikat_z_adresu_nie_wstawia_tekstu_przeslanego_w_adresie(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, _plik, _rejestr, _instancja = srodowisko

    _, strona = klient.get("/ustawienia?zakladka=%3Cscript%3E&wynik=zapisano")

    assert "<script>" not in strona.replace("<script>\n(function", "")
    assert 'id="komunikat-ustawien"' not in strona


def test_uszkodzony_plik_konfiguracji_nie_wywraca_strony(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    plik.write_text("to nie jest = = toml [", encoding="utf-8")

    odpowiedz, strona = klient.get("/ustawienia")

    assert odpowiedz.status == 200
    assert "Nie udało się wczytać pliku konfiguracji" in strona


def test_przywracanie_nie_usuwa_pol_zablokowanych_zmienna_ani_tylko_do_odczytu(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    plik.write_text(
        _PLIK + 'adres_nasluchu = "localhost"\nport_nasluchu = 9000\n', encoding="utf-8"
    )
    monkeypatch.setenv("GNB_LIMIT_ZRODEL", "77")

    klient.post("/ustawienia/przywroc", {"zakladka": "limity"})
    klient.post("/ustawienia/przywroc", {"zakladka": "serwer"})

    tresc = plik.read_text(encoding="utf-8")
    assert "limit_zrodel = 50" in tresc
    assert 'adres_nasluchu = "localhost"' in tresc
    assert "port_nasluchu" not in tresc


# --- zakładka Wygląd ---------------------------------------------------------


def test_opis_pola_odnosnikow_mowi_o_wykazie_a_nie_o_adresach_w_tekscie() -> None:
    pole = pole_ustawien("zachowuj_odnosniki")

    assert "wykaz odnośników" in pole.etykieta
    assert "wykaz" in pole.opis
    assert "nie zależą" in pole.opis
    assert "Zachowuje adresy" not in pole.opis


def test_zakladka_wyglad_ma_liste_schematow_rozmiarow_i_kroi_oraz_osiem_kolorow() -> None:
    zakladka = zakladka_o_identyfikatorze("wyglad")
    assert zakladka is not None
    pola = {pole.nazwa: pole for pole in zakladka.pola}

    assert pola["wyglad_schemat"].rodzaj is Rodzaj.WYBOR
    assert pola["wyglad_rozmiar_czcionki"].rodzaj is Rodzaj.WYBOR_LICZBY
    assert pola["wyglad_kroj_pisma"].rodzaj is Rodzaj.WYBOR
    kolory = [nazwa for nazwa in pola if nazwa.startswith("wyglad_kolor_")]
    assert len(kolory) == 8
    assert all(pola[nazwa].rodzaj is Rodzaj.TEKST for nazwa in kolory)
    assert not any(pole.restart for pole in zakladka.pola)


def test_widok_wygladu_ma_nazwane_schematy_i_pola_kolorow_z_etykietami() -> None:
    panel = _html_zakladki(_strona(), "wyglad")

    assert "Zbliżony do Gemini Notebook" in panel
    assert "Kolory własne" in panel
    assert "150 procent" in panel
    assert '<label for="pole-wyglad_kolor_tla">Kolor tła</label>' in panel
    assert "placeholder" not in panel
    assert ' aria-label="' not in panel
    assert 'name="wyglad_rozmiar_czcionki"' in panel
    assert "Przywróć schemat domyślny" in panel


def test_przycisk_przywracania_schematu_jest_w_osobnym_formularzu_z_tokenem() -> None:
    panel = _html_zakladki(_strona(), "wyglad")

    assert 'action="/ustawienia/przywroc-schemat"' in panel
    assert 'class="ratunek"' in panel
    assert 'name="token_csrf" value="tokentestowy"' in panel


def test_przy_kolorach_wlasnych_przycisk_ratunkowy_jest_tez_na_poczatku_strony() -> None:
    wlasne = Konfiguracja(wyglad_schemat="wlasny")

    domyslna = _strona()
    z_wlasnymi = _strona(konfiguracja=wlasne)

    assert 'id="przywroc-schemat-gora"' not in domyslna
    gora = z_wlasnymi.index('id="przywroc-schemat-gora"')
    assert gora < z_wlasnymi.index('id="zakladki-ustawien"')


def test_strona_pokazuje_kontrast_i_ostrzezenie_tylko_przy_kolorach_wlasnych() -> None:
    nieczytelne = Konfiguracja(
        wyglad_schemat="wlasny", wyglad_kolor_tla="#777777", wyglad_kolor_tekstu="#888888"
    )

    z_ostrzezeniem = _html_zakladki(_strona(konfiguracja=nieczytelne), "wyglad")
    bez = _html_zakladki(_strona(), "wyglad")

    assert "Kontrast tekstu do tła:" in z_ostrzezeniem
    assert "mniej niż 4,5 do 1" in z_ostrzezeniem
    assert "Kontrast tekstu do tła:" not in bez


def test_odczyt_wyboru_liczbowego_daje_liczbe_a_zly_tekst_daje_blad() -> None:
    zakladka = zakladka_o_identyfikatorze("wyglad")
    assert zakladka is not None

    wartosci, bledy = odczytaj_zakladke(zakladka, {"wyglad_rozmiar_czcionki": "150"}, frozenset())
    assert not [blad for blad in bledy if blad.pole == "wyglad_rozmiar_czcionki"]
    assert wartosci["wyglad_rozmiar_czcionki"] == 150

    _, bledy = odczytaj_zakladke(zakladka, {"wyglad_rozmiar_czcionki": "duzy"}, frozenset())
    assert "wyglad_rozmiar_czcionki" in {blad.pole for blad in bledy}


def test_zapis_wygladu_dziala_na_wszystkich_stronach_od_razu(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko

    odpowiedz, _ = klient.post(
        "/ustawienia/zapisz",
        _formularz_zakladki(
            "wyglad", wyglad_schemat="czarny_na_bialym", wyglad_rozmiar_czcionki="150"
        ),
    )

    assert odpowiedz.status == 303
    assert 'wyglad_schemat = "czarny_na_bialym"' in plik.read_text(encoding="utf-8")
    for adres in ("/", "/ustawienia", "/nie-ma-takiej-strony"):
        _, strona = klient.get(adres)
        assert '<style id="wyglad-uzytkownika">' in strona, adres
        assert "--tlo: #ffffff;" in strona, adres
        assert "--skala: 1.5;" in strona, adres


def test_kolory_wlasne_zapisuja_sie_a_ostrzezenie_nie_blokuje_zapisu(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko

    odpowiedz, _ = klient.post(
        "/ustawienia/zapisz",
        _formularz_zakladki(
            "wyglad",
            wyglad_schemat="wlasny",
            wyglad_kolor_tla="#777777",
            wyglad_kolor_tekstu="#888888",
        ),
    )

    assert odpowiedz.status == 303
    zapisane = wczytaj_konfiguracje(plik, srodowisko={})
    assert zapisane.wyglad_kolor_tla == "#777777"
    _, strona = klient.get(odpowiedz.getheader("Location") or "")
    assert "Zapisano ustawienia zakładki Wygląd." in strona
    assert "Uwaga:" in strona
    assert "mniej niż 4,5 do 1" in strona


@pytest.mark.parametrize(
    "zly_kolor",
    [
        "red",
        "#fff",
        "#12345g",
        "#1234567",
        "#fff;}</style><script>alert(1)</script>",
        "#ffffff; background: url(http://zlosliwy.example/x)",
        "#ffffff\n#000000",
    ],
)
def test_zly_kolor_daje_400_z_bledem_przy_polu_i_nie_zmienia_pliku(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object], zly_kolor: str
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, strona = klient.post(
        "/ustawienia/zapisz",
        _formularz_zakladki("wyglad", wyglad_schemat="wlasny", wyglad_kolor_tla=zly_kolor),
    )

    assert odpowiedz.status == 400
    assert plik.read_text(encoding="utf-8") == przed
    assert "wyglad_kolor_tla" in strona
    assert "<script>alert(1)" not in strona
    _, inna = klient.get("/")
    assert "zlosliwy.example" not in inna
    assert "<script>alert(1)" not in inna


def test_przywracanie_schematu_usuwa_wybor_schematu_ale_zostawia_kolory_wlasne(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    klient.post(
        "/ustawienia/zapisz",
        _formularz_zakladki(
            "wyglad",
            wyglad_schemat="wlasny",
            wyglad_kolor_tla="#112233",
            wyglad_kolor_tekstu="#112233",
        ),
    )

    odpowiedz, _ = klient.post("/ustawienia/przywroc-schemat", {})

    assert odpowiedz.status == 303
    tresc = plik.read_text(encoding="utf-8")
    assert "wyglad_schemat" not in tresc
    assert 'wyglad_kolor_tla = "#112233"' in tresc
    assert "# Komentarz użytkownika" in tresc
    _, strona = klient.get("/")
    assert "--tlo: #10131a;" in strona
    _, ustawienia = klient.get(odpowiedz.getheader("Location") or "")
    assert "Przywrócono schemat domyślny." in ustawienia


def test_przywracanie_schematu_wymaga_tokenu_csrf(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    klient.post("/ustawienia/zapisz", _formularz_zakladki("wyglad", wyglad_schemat="wlasny"))
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, _ = klient.post("/ustawienia/przywroc-schemat", {}, token="zly")

    assert odpowiedz.status == 403
    assert plik.read_text(encoding="utf-8") == przed


def test_przywracanie_schematu_jest_odrzucane_w_trakcie_przetwarzania(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, rejestr, _instancja = srodowisko
    klient.post("/ustawienia/zapisz", _formularz_zakladki("wyglad", wyglad_schemat="wlasny"))
    przed = plik.read_text(encoding="utf-8")

    czeka = threading.Event()
    rejestr.uruchom("Projekt", lambda _postep: czeka.wait(5) and None)  # type: ignore[arg-type,return-value]
    try:
        odpowiedz, _ = klient.post("/ustawienia/przywroc-schemat", {})
    finally:
        czeka.set()

    assert odpowiedz.status == 409
    assert plik.read_text(encoding="utf-8") == przed


def test_przywracanie_schematu_przy_zmiennej_srodowiskowej_mowi_o_zmiennej(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    monkeypatch.setenv("GNB_WYGLAD_SCHEMAT", "bialy_na_czarnym")
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, strona = klient.post("/ustawienia/przywroc-schemat", {})

    assert odpowiedz.status == 400
    assert "GNB_WYGLAD_SCHEMAT" in strona
    assert plik.read_text(encoding="utf-8") == przed


def test_przywracanie_zakladki_wyglad_czysci_wszystkie_pola_wygladu(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    klient.post(
        "/ustawienia/zapisz",
        _formularz_zakladki(
            "wyglad", wyglad_schemat="zolty_na_czarnym", wyglad_rozmiar_czcionki="200"
        ),
    )

    odpowiedz, _ = klient.post("/ustawienia/przywroc", {"zakladka": "wyglad"})

    assert odpowiedz.status == 303
    assert "wyglad_" not in plik.read_text(encoding="utf-8")


# --- znaki sterujące w polach tekstowych ------------------------------------


def test_zapis_pola_tekstowego_ze_znakami_sterujacymi_jest_odrzucany(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko
    przed = plik.read_text(encoding="utf-8")

    odpowiedz, strona = klient.post(
        "/ustawienia/zapisz",
        _formularz_zakladki("pobieranie", nazwa_klienta="Klient\r\nX-Wstrzykniety: tak"),
    )

    assert odpowiedz.status == 400
    assert "znak sterujący" in strona
    assert plik.read_text(encoding="utf-8") == przed
    pozniej, _ = klient.get("/")
    assert pozniej.status == 200


def test_zapis_poprawnej_nazwy_klienta_dziala(
    srodowisko: tuple[_Klient, Path, RejestrZadan, object],
) -> None:
    klient, plik, _rejestr, _instancja = srodowisko

    odpowiedz, _ = klient.post(
        "/ustawienia/zapisz", _formularz_zakladki("pobieranie", nazwa_klienta="Moj klient 1.0")
    )

    assert odpowiedz.status == 303
    assert wczytaj_konfiguracje(plik, srodowisko={}).nazwa_klienta == "Moj klient 1.0"
