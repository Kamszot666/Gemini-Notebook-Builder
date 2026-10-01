"""Testy blokady pojedynczej kopii serwera i wyłączności portu."""

from __future__ import annotations

import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja, sciezka_pliku_konfiguracji
from gnb.ui import server
from gnb.ui.blokada import (
    NAZWA_PLIKU_BLOKADY,
    BlokadaInstancji,
    odczytaj_adres_dzialajacej_kopii,
)
from gnb.ui.serwer import zbuduj_serwer

_KORZEN_REPOZYTORIUM = Path(__file__).resolve().parents[2]

_SKRYPT_PROCESU_Z_BLOKADA = textwrap.dedent(
    """
    import sys
    import time
    from pathlib import Path

    from gnb.ui.blokada import BlokadaInstancji

    blokada = BlokadaInstancji(Path(sys.argv[1]))
    if not blokada.zajmij():
        print("zajeta", flush=True)
        sys.exit(2)
    blokada.zapisz_adres("http://127.0.0.1:1/")
    print("gotowe", flush=True)
    time.sleep(120)
    """
)


def _uruchom_proces_z_blokada(katalog: Path) -> subprocess.Popen[str]:
    proces = subprocess.Popen(
        [sys.executable, "-c", _SKRYPT_PROCESU_Z_BLOKADA, str(katalog)],
        stdout=subprocess.PIPE,
        text=True,
        cwd=_KORZEN_REPOZYTORIUM,
    )
    assert proces.stdout is not None
    assert proces.stdout.readline().strip() == "gotowe"
    return proces


def test_druga_proba_zalozenia_blokady_zwraca_falsz(tmp_path: Path) -> None:
    pierwsza = BlokadaInstancji(tmp_path)
    druga = BlokadaInstancji(tmp_path)
    try:
        assert pierwsza.zajmij() is True
        assert druga.zajmij() is False
    finally:
        pierwsza.zwolnij()
        druga.zwolnij()


def test_blokada_zwolniona_pozwala_zajac_ja_ponownie(tmp_path: Path) -> None:
    pierwsza = BlokadaInstancji(tmp_path)
    assert pierwsza.zajmij() is True
    pierwsza.zwolnij()

    druga = BlokadaInstancji(tmp_path)
    try:
        assert druga.zajmij() is True
    finally:
        druga.zwolnij()


def test_adres_jest_czytelny_dla_innego_procesu_podczas_blokady(tmp_path: Path) -> None:
    blokada = BlokadaInstancji(tmp_path)
    try:
        assert blokada.zajmij() is True
        blokada.zapisz_adres("http://127.0.0.1:8765/")
        assert odczytaj_adres_dzialajacej_kopii(tmp_path) == "http://127.0.0.1:8765/"
    finally:
        blokada.zwolnij()


def test_brak_pliku_blokady_nie_daje_adresu(tmp_path: Path) -> None:
    assert odczytaj_adres_dzialajacej_kopii(tmp_path) is None


def test_blokada_trzymana_przez_inny_proces_blokuje_ten_proces(tmp_path: Path) -> None:
    proces = _uruchom_proces_z_blokada(tmp_path)
    try:
        wlasna = BlokadaInstancji(tmp_path)
        assert wlasna.zajmij() is False
        assert odczytaj_adres_dzialajacej_kopii(tmp_path) == "http://127.0.0.1:1/"
    finally:
        proces.kill()
        proces.wait(timeout=10)


def test_plik_po_zabitym_procesie_nie_blokuje(tmp_path: Path) -> None:
    proces = _uruchom_proces_z_blokada(tmp_path)
    proces.kill()
    proces.wait(timeout=10)

    assert (tmp_path / NAZWA_PLIKU_BLOKADY).is_file()
    wlasna = BlokadaInstancji(tmp_path)
    try:
        # Windows zwalnia blokadę zakresu bajtów chwilę po zakończeniu procesu,
        # nie w tej samej chwili, więc test czeka krótko zamiast zakładać natychmiast.
        koniec = time.monotonic() + 5.0
        zajeta = wlasna.zajmij()
        while not zajeta and time.monotonic() < koniec:
            time.sleep(0.1)
            zajeta = wlasna.zajmij()
        assert zajeta is True
    finally:
        wlasna.zwolnij()


def test_druga_kopia_serwera_nie_startuje_i_otwiera_adres_dzialajacej(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path / "wyniki"))
    katalog_danych = sciezka_pliku_konfiguracji().parent
    pierwsza = BlokadaInstancji(katalog_danych)
    assert pierwsza.zajmij() is True
    pierwsza.zapisz_adres("http://127.0.0.1:4321/")
    otwarte: list[str] = []
    try:
        kod = server.main(otworz_przegladarke=otwarte.append)
    finally:
        pierwsza.zwolnij()

    assert kod == server.KOD_JUZ_DZIALA
    assert kod != 0
    assert otwarte == ["http://127.0.0.1:4321/"]
    assert "już działa pod adresem http://127.0.0.1:4321/" in capsys.readouterr().out


def test_blad_przegladarki_nie_zmienia_kodu_wyjscia_drugiej_kopii(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path / "wyniki"))
    pierwsza = BlokadaInstancji(sciezka_pliku_konfiguracji().parent)
    assert pierwsza.zajmij() is True

    def przegladarka_zepsuta(adres: str) -> None:
        raise RuntimeError("brak przeglądarki")

    try:
        kod = server.main(otworz_przegladarke=przegladarka_zepsuta)
    finally:
        pierwsza.zwolnij()

    assert kod == server.KOD_JUZ_DZIALA
    assert "Otwórz ten adres ręcznie" in capsys.readouterr().out


def test_drugi_serwer_nie_zajmie_portu_zajetego_przez_pierwszy(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    pierwszy = zbuduj_serwer(konfiguracja)
    try:
        port = pierwszy.server_address[1]
        konfiguracja_drugiego = Konfiguracja(
            katalog_wynikow=tmp_path / "wyniki", port_nasluchu=port
        )
        with pytest.raises(OSError):
            zbuduj_serwer(konfiguracja_drugiego).server_close()
    finally:
        pierwszy.server_close()


def test_port_da_sie_zajac_ponownie_po_zamknieciu_serwera_z_polaczeniem(tmp_path: Path) -> None:
    """Wyłączność portu nie może utrudniać restartu zaraz po zamknięciu poprzedniej kopii."""
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=0)
    pierwszy = zbuduj_serwer(konfiguracja)
    port = pierwszy.server_address[1]
    klient = socket.create_connection(("127.0.0.1", port), timeout=5)
    polaczenie_serwera, _ = pierwszy.socket.accept()
    polaczenie_serwera.close()
    klient.close()
    pierwszy.server_close()

    drugi = zbuduj_serwer(Konfiguracja(katalog_wynikow=tmp_path / "wyniki", port_nasluchu=port))
    drugi.server_close()
