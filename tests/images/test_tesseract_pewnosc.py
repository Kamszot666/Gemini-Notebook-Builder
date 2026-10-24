"""Testy żądania TSV od Tesseracta niezależnego od podkatalogu ``configs``.

Słowo ``tsv`` na końcu polecenia Tesseract traktuje jako nazwę pliku ustawień
i szuka ``configs/tsv`` w katalogu danych językowych. Gdy katalog zawiera same
pliki ``*.traineddata``, Tesseract kończy się kodem zero i oddaje zwykły tekst,
a odczyt pewności bez bezpiecznika uznałby każdą stronę za nieczytelną.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.images import tesseract
from gnb.images.tesseract import UstawieniaOcr, rozpoznaj_tekst, rozpoznaj_z_pewnoscia
from tests.images.test_odczyt_pewnosci import _NAGLOWEK_TSV, _strona_druku

_TSV_Z_JEDNYM_SLOWEM = f"{_NAGLOWEK_TSV}\n5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t91.0\tSąd\n"


def _atrapa_uruchomienia(monkeypatch: pytest.MonkeyPatch, wyjscie: bytes) -> list[list[str]]:
    """Podstawia `subprocess.run` i zwraca listę poleceń, które by uruchomiono."""
    polecenia: list[list[str]] = []

    def atrapa(polecenie: list[str], **_nazwane: object) -> subprocess.CompletedProcess[bytes]:
        polecenia.append(list(polecenie))
        return subprocess.CompletedProcess(polecenie, 0, stdout=wyjscie, stderr=b"")

    monkeypatch.setattr(tesseract.subprocess, "run", atrapa)
    monkeypatch.setattr(tesseract, "znajdz_tesseract", lambda _sciezka="": Path("tesseract"))
    return polecenia


def test_odczyt_z_pewnoscia_prosi_o_tsv_ustawieniem_a_nie_slowem_tsv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polecenia = _atrapa_uruchomienia(monkeypatch, _TSV_Z_JEDNYM_SLOWEM.encode())

    wynik = rozpoznaj_z_pewnoscia(b"png", UstawieniaOcr(jezyk="pol"))

    (polecenie,) = polecenia
    assert "tsv" not in polecenie
    indeks = polecenie.index("-c")
    assert polecenie[indeks + 1] == "tessedit_create_tsv=1"
    assert wynik.liczba_slow == 1
    assert wynik.srednia_pewnosc == pytest.approx(91.0)


def test_zwykle_rozpoznanie_tekstu_nie_dostaje_ustawienia_tsv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    polecenia = _atrapa_uruchomienia(monkeypatch, "Zwykły tekst".encode())

    assert rozpoznaj_tekst(b"png", UstawieniaOcr(jezyk="pol")) == "Zwykły tekst"

    assert "-c" not in polecenia[0]


def test_zwykly_tekst_zamiast_tsv_jest_bledem_trwalym_a_nie_zerem_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _atrapa_uruchomienia(monkeypatch, "Sąd Rejonowy wydał wyrok.\n".encode())

    with pytest.raises(BladTrwaly, match="nie zwrócił danych o pewności") as blad:
        rozpoznaj_z_pewnoscia(b"png", UstawieniaOcr(jezyk="pol"), identyfikator_zrodla="obraz-1")

    assert "sciezka_tessdata" in blad.value.komunikat
    assert "nie została uznana za nieczytelną" in blad.value.komunikat


@pytest.mark.parametrize("wyjscie", [b"", b"\n  \n", f"{_NAGLOWEK_TSV}\n".encode()])
def test_pusty_wynik_i_tsv_z_samym_naglowkiem_to_zero_slow_bez_wyjatku(
    monkeypatch: pytest.MonkeyPatch, wyjscie: bytes
) -> None:
    _atrapa_uruchomienia(monkeypatch, wyjscie)

    wynik = rozpoznaj_z_pewnoscia(b"png", UstawieniaOcr(jezyk="pol"))

    assert wynik.liczba_slow == 0
    assert wynik.srednia_pewnosc == 0.0


def _znajdz_pol_traineddata() -> Path | None:
    """Szuka pliku ``pol.traineddata`` w instalacji Tesseracta; nic, gdy się nie da."""
    kandydaci: list[Path] = []
    prefiks = os.environ.get("TESSDATA_PREFIX")
    if prefiks:
        kandydaci += [Path(prefiks), Path(prefiks) / "tessdata"]
    try:
        program = tesseract.znajdz_tesseract()
        kandydaci.append(program.parent / "tessdata")
    except Exception:  # noqa: BLE001 - brak programu oznacza po prostu brak kandydata
        pass
    kandydaci += list(Path("/usr/share/tesseract-ocr").glob("*/tessdata"))
    kandydaci += [Path("/usr/share/tessdata"), Path("/usr/local/share/tessdata")]
    for katalog in kandydaci:
        plik = katalog / "pol.traineddata"
        if plik.is_file():
            return plik
    return None


def test_odczyt_z_pewnoscia_dziala_w_katalogu_danych_bez_podkatalogu_configs(
    wymaga_ocr_pol: None, tmp_path: Path
) -> None:
    pol = _znajdz_pol_traineddata()
    if pol is None:
        pytest.skip("Nie ustalono położenia pol.traineddata w instalacji Tesseracta.")
    katalog_danych = tmp_path / "tylko_dane"
    katalog_danych.mkdir()
    shutil.copy(pol, katalog_danych / "pol.traineddata")
    assert not (katalog_danych / "configs").exists()

    from gnb.images.odczyt_strony import zapisz_png

    wynik = rozpoznaj_z_pewnoscia(
        zapisz_png(_strona_druku()),
        UstawieniaOcr(jezyk="pol", sciezka_tessdata=str(katalog_danych)),
    )

    assert wynik.liczba_slow > 100
    assert wynik.srednia_pewnosc > 80
    assert "sąd" in wynik.tekst.lower()
