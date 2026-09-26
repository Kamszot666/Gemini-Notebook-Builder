"""Testy serwera dla ręcznych działań na źródłach: zweryfikowanie, usunięcie, zastąpienie treści.

Projekt powstaje prawdziwym przebiegiem przez formularz strony głównej, a testy
sprawdzają odpowiedzi HTTP, stan checkpointu i pliki na dysku. Osobno sprawdzają,
że samo wyświetlenie strony niczego nie zmienia, a każde działanie wymaga tokenu
CSRF i odmawia, gdy trwa przetwarzanie.
"""

from __future__ import annotations

import http.client
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import quote

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.postep import WywolanieZwrotnePostepu
from gnb.persistence.checkpoint import Checkpoint, wczytaj, zapisz
from gnb.persistence.projekt import UkladProjektu, ustal_uklad
from gnb.potok import WynikPrzetwarzania
from gnb.ui.serwer import zbuduj_serwer
from gnb.ui.zadania import RejestrZadan

_NAZWA = "Projekt Zrodel"
_GRANICA = "----TestGranicaZrodel"
_TEKST_A = "Pierwsze źródło opowiada o porządkowaniu materiałów przed importem do bazy."
_TEKST_B = "Drugie źródło przypomina o sprawdzaniu dat publikacji artykułów w bazie."


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

    def post(
        self,
        sciezka: str,
        pola: dict[str, str],
        *,
        plik: tuple[str, bytes] | None = None,
        pole_pliku: str = "plik",
    ) -> tuple[http.client.HTTPResponse, str]:
        czesci = "".join(
            f'--{_GRANICA}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'
            for nazwa, wartosc in pola.items()
        )
        cialo = czesci.encode("utf-8")
        if plik is not None:
            nazwa_pliku, zawartosc = plik
            cialo += (
                (
                    f'--{_GRANICA}\r\nContent-Disposition: form-data; name="plik"; '
                    f'filename="{nazwa_pliku}"\r\nContent-Type: text/plain\r\n\r\n'
                ).encode()
                + zawartosc
                + b"\r\n"
            )
        cialo += f"--{_GRANICA}--\r\n".encode()
        return self._wyslij("POST", sciezka, cialo, f"multipart/form-data; boundary={_GRANICA}")

    def token(self) -> str:
        return self.ciasteczko.split("=", 1)[1] if self.ciasteczko else ""


@pytest.fixture
def srodowisko(tmp_path: Path) -> Iterator[tuple[_Klient, RejestrZadan, Konfiguracja]]:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    rejestr = RejestrZadan()
    instancja = zbuduj_serwer(konfiguracja, rejestr)
    watek = threading.Thread(target=instancja.serve_forever, daemon=True)
    watek.start()
    klient = _Klient(str(instancja.server_address[0]), int(instancja.server_address[1]))
    klient.get("/")
    try:
        yield klient, rejestr, konfiguracja
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


def _utworz_projekt(klient: _Klient, rejestr: RejestrZadan, tresc: str, grupa: str = "G") -> None:
    odpowiedz, _ = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "nazwa_projektu": _NAZWA,
            "tekst": tresc,
            "grupa": grupa,
        },
    )
    assert odpowiedz.status == 303
    _czekaj(rejestr)


def _uklad(konfiguracja: Konfiguracja) -> UkladProjektu:
    return ustal_uklad(konfiguracja.katalog_wynikow, _NAZWA)


def _checkpoint(konfiguracja: Konfiguracja) -> Checkpoint:
    checkpoint = wczytaj(_uklad(konfiguracja).checkpoint)
    assert checkpoint is not None
    return checkpoint


def _adres(identyfikator: str, akcja: str) -> str:
    return f"/projekt/{quote(_NAZWA, safe='')}/zrodlo/{quote(identyfikator, safe='')}/{akcja}"


def _pierwsze_zrodlo(konfiguracja: Konfiguracja) -> str:
    return next(iter(_checkpoint(konfiguracja).zrodla))


def _dopisz_ostrzezenie(konfiguracja: Konfiguracja, identyfikator: str) -> None:
    checkpoint = _checkpoint(konfiguracja)
    checkpoint.zrodla[identyfikator].ostrzezenia = ["Ostrzeżenie ekstraktora do sprawdzenia."]
    zapisz(_uklad(konfiguracja).checkpoint, checkpoint)


def test_strona_projektu_pokazuje_zrodla_z_dzialaniami_powiazanymi_z_nazwa_zrodla(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)
    _dopisz_ostrzezenie(konfiguracja, identyfikator)

    odpowiedz, strona = klient.get(f"/projekt/{quote(_NAZWA, safe='')}")

    assert odpowiedz.status == 200
    assert "<h2>Źródła projektu</h2>" in strona
    assert "Liczba źródeł: 1." in strona
    assert "Oznacz jako zweryfikowane" in strona
    assert "Zastąp treść plikiem" in strona
    assert "Usuń źródło z projektu" in strona
    assert "Ostrzeżenie ekstraktora do sprawdzenia." in strona
    # Przyciski i odnośnik nie noszą nazwy źródła, tylko wskazują jej nagłówek.
    opis = f"zrodlo-{identyfikator}-opis"
    assert f'id="{opis}"' in strona
    assert strona.count(f'aria-describedby="{opis}"') >= 3
    assert 'aria-label="Plik z ręcznie zapisaną treścią tego źródła"' in strona


def test_nazwa_zrodla_jest_escapowana_w_wykazie(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    checkpoint = _checkpoint(konfiguracja)
    stan = next(iter(checkpoint.zrodla.values()))
    stan.pochodzenie = '<script>alert("x")</script>'
    zapisz(_uklad(konfiguracja).checkpoint, checkpoint)

    _, strona = klient.get(f"/projekt/{quote(_NAZWA, safe='')}")

    assert "<script>alert" not in strona
    assert "&lt;script&gt;" in strona


def test_wyswietlenie_strony_pokazuje_brakujacy_plik_ale_nie_zmienia_stanu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    (plik,) = _uklad(konfiguracja).pliki_wynikowe.glob("*.txt")
    plik.unlink()
    przed = _uklad(konfiguracja).checkpoint.read_bytes()

    _, strona = klient.get(f"/projekt/{quote(_NAZWA, safe='')}")
    klient.get(f"/projekt/{quote(_NAZWA, safe='')}")

    assert "<h2>Pliki wynikowe brakujące na dysku</h2>" in strona
    assert plik.name in strona
    assert "niczego nie zmienia" in strona
    assert _uklad(konfiguracja).checkpoint.read_bytes() == przed
    (stan,) = _checkpoint(konfiguracja).zrodla.values()
    assert stan.status == "spakowane"


def test_zweryfikowanie_zmienia_checkpoint_i_wymaga_tokenu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)
    _dopisz_ostrzezenie(konfiguracja, identyfikator)

    bez_tokenu, _ = klient.post(_adres(identyfikator, "zweryfikowane"), {"token_csrf": "zly"})
    assert bez_tokenu.status == 403
    assert _checkpoint(konfiguracja).zrodla[identyfikator].zweryfikowane_recznie is False

    odpowiedz, _ = klient.post(
        _adres(identyfikator, "zweryfikowane"), {"token_csrf": klient.token()}
    )

    assert odpowiedz.status == 303
    assert _checkpoint(konfiguracja).zrodla[identyfikator].zweryfikowane_recznie is True
    _, strona = klient.get(f"/projekt/{quote(_NAZWA, safe='')}")
    assert "Zweryfikowane ręcznie przez użytkownika." in strona
    assert "Oznacz jako zweryfikowane" not in strona


def test_zweryfikowanie_zrodla_spoza_materialow_zwraca_400(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    odpowiedz, strona = klient.post(
        _adres(identyfikator, "zweryfikowane"), {"token_csrf": klient.token()}
    )

    assert odpowiedz.status == 400
    assert "nie jest na liście materiałów do sprawdzenia" in strona


def test_dzialanie_na_zrodle_jest_odrzucane_w_trakcie_przetwarzania(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)
    _dopisz_ostrzezenie(konfiguracja, identyfikator)
    zwolnij = threading.Event()

    def blokada(_postep: WywolanieZwrotnePostepu) -> WynikPrzetwarzania:
        zwolnij.wait(timeout=10)
        raise RuntimeError("koniec testu")

    rejestr.uruchom("Inny projekt", blokada)
    try:
        odpowiedz, strona = klient.post(
            _adres(identyfikator, "zweryfikowane"), {"token_csrf": klient.token()}
        )
    finally:
        zwolnij.set()
        _czekaj(rejestr)

    assert odpowiedz.status == 409
    assert "Trwa przetwarzanie projektu" in strona
    assert _checkpoint(konfiguracja).zrodla[identyfikator].zweryfikowane_recznie is False


def test_potwierdzenie_usuniecia_jest_strona_bez_zmiany_stanu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    odpowiedz, strona = klient.get(_adres(identyfikator, "usun"))

    assert odpowiedz.status == 200
    assert "<h1>Usunąć źródło z projektu?</h1>" in strona
    assert 'for="potwierdzenie"' in strona and 'id="potwierdzenie"' in strona
    assert "Anuluj i wróć do projektu" in strona
    assert identyfikator in _checkpoint(konfiguracja).zrodla


def test_usuniecie_wymaga_wpisanego_potwierdzenia(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    zle, strona = klient.post(
        _adres(identyfikator, "usun"), {"token_csrf": klient.token(), "potwierdzenie": "nie"}
    )

    assert zle.status == 400
    assert "Źródło nie zostało usunięte." in strona
    assert 'aria-invalid="true"' in strona
    assert identyfikator in _checkpoint(konfiguracja).zrodla

    dobre, _ = klient.post(
        _adres(identyfikator, "usun"), {"token_csrf": klient.token(), "potwierdzenie": " usuń "}
    )

    assert dobre.status == 303
    assert identyfikator not in _checkpoint(konfiguracja).zrodla
    assert not list(_uklad(konfiguracja).pliki_wynikowe.glob("*.txt"))


def test_usuniecie_zrodla_z_grupy_uruchamia_przepakowanie(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A, grupa="Grupa")
    _utworz_projekt(klient, rejestr, _TEKST_B, grupa="Grupa")
    (stary_plik,) = _uklad(konfiguracja).pliki_wynikowe.glob("*.txt")
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    odpowiedz, _ = klient.post(
        _adres(identyfikator, "usun"), {"token_csrf": klient.token(), "potwierdzenie": "USUŃ"}
    )
    assert odpowiedz.status == 303
    _czekaj(rejestr)

    (nowy_plik,) = _uklad(konfiguracja).pliki_wynikowe.glob("*.txt")
    assert nowy_plik != stary_plik
    assert nowy_plik.read_text(encoding="utf-8").count("Identyfikator źródła: ") == 1
    raport = _uklad(konfiguracja).raport.read_text(encoding="utf-8")
    assert f"Plik grupy zastąpiony: {stary_plik.name} → {nowy_plik.name}" in raport


def test_zastapienie_tresci_plikiem_uruchamia_przebieg_i_zapisuje_uwage(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    odpowiedz, _ = klient.post(
        _adres(identyfikator, "zastap"),
        {"token_csrf": klient.token()},
        plik=("reczny.txt", "Treść zapisana ręcznie zamiast pierwotnej treści źródła.".encode()),
    )
    assert odpowiedz.status == 303
    _czekaj(rejestr)

    stan = _checkpoint(konfiguracja).zrodla[identyfikator]
    assert stan.status == "spakowane"
    assert stan.tresc_zastapiona_plikiem == "reczny.txt"
    (plik,) = _uklad(konfiguracja).pliki_wynikowe.glob("*.txt")
    tresc = plik.read_text(encoding="utf-8")
    assert "Treść zapisana ręcznie zamiast pierwotnej treści źródła." in tresc
    assert "Uwaga o treści: treść zapisana ręcznie w pliku reczny.txt" in tresc
    assert list((_uklad(konfiguracja).pliki_wejsciowe / "zastepcze").glob("reczny*.txt"))


def test_zastapienie_bez_pliku_zwraca_400_i_niczego_nie_zmienia(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    odpowiedz, strona = klient.post(_adres(identyfikator, "zastap"), {"token_csrf": klient.token()})

    assert odpowiedz.status == 400
    assert "Nie wybrano pliku" in strona
    assert _checkpoint(konfiguracja).zrodla[identyfikator].tresc_zastapiona_plikiem is None


def test_nieznane_dzialanie_i_nieznane_zrodlo_daja_404(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)
    identyfikator = _pierwsze_zrodlo(konfiguracja)

    nieznane_dzialanie, _ = klient.post(
        _adres(identyfikator, "cos"), {"token_csrf": klient.token()}
    )
    nieznane_zrodlo, _ = klient.get(_adres("nie-ma-takiego", "usun"))

    assert nieznane_dzialanie.status == 404
    assert nieznane_zrodlo.status == 404


def test_dosylanie_adresu_bez_schematu_daje_blad_walidacji_a_nie_500(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, _ = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)

    odpowiedz, strona = klient.post(
        f"/projekt/{quote(_NAZWA, safe='')}/dosylanie",
        {"token_csrf": klient.token(), "adresy": "www.wp.pl", "grupa": "G"},
    )

    assert odpowiedz.status == 400
    assert "nie zaczyna się od http albo https" in strona
    assert "www.wp.pl" in strona


def test_dosylanie_pliku_z_dysku_dodaje_zrodlo(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, konfiguracja = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)

    odpowiedz, _ = klient.post(
        f"/projekt/{quote(_NAZWA, safe='')}/dosylanie",
        {"token_csrf": klient.token(), "grupa": "G"},
        plik=("dodatkowy.txt", "Treść dodatkowego pliku z dysku.".encode()),
        pole_pliku="pliki",
    )
    assert odpowiedz.status == 303
    _czekaj(rejestr)

    pochodzenia = {stan.pochodzenie for stan in _checkpoint(konfiguracja).zrodla.values()}
    assert "dodatkowy.txt" in pochodzenia


def test_nowy_projekt_bez_nazwy_grupy_daje_blad_walidacji(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, _, _ = srodowisko

    odpowiedz, strona = klient.post(
        "/projekt/nowy",
        {"token_csrf": klient.token(), "nazwa_projektu": _NAZWA, "tekst": _TEKST_A, "grupa": ""},
    )

    assert odpowiedz.status == 400
    assert "Nazwa grupy tematycznej jest wymagana." in strona


def test_dosylanie_bez_nazwy_grupy_daje_blad_walidacji(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, rejestr, _ = srodowisko
    _utworz_projekt(klient, rejestr, _TEKST_A)

    odpowiedz, strona = klient.post(
        f"/projekt/{quote(_NAZWA, safe='')}/dosylanie",
        {"token_csrf": klient.token(), "tekst": "Drugi tekst.", "grupa": ""},
    )

    assert odpowiedz.status == 400
    assert "Nazwa grupy tematycznej jest wymagana." in strona


def test_adres_bez_schematu_w_nowym_projekcie_nie_tworzy_katalogu(
    srodowisko: tuple[_Klient, RejestrZadan, Konfiguracja],
) -> None:
    klient, _, konfiguracja = srodowisko

    odpowiedz, strona = klient.post(
        "/projekt/nowy",
        {
            "token_csrf": klient.token(),
            "nazwa_projektu": _NAZWA,
            "adresy": "www.wp.pl",
            "grupa": "G",
        },
    )

    assert odpowiedz.status == 400
    assert "nie zaczyna się od http albo https" in strona
    assert not _uklad(konfiguracja).katalog_projektu.exists()
