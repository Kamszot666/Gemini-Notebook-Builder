"""Testy ekstraktora plików MHTML: dekodowanie części HTML i obsługa błędów."""

from __future__ import annotations

import base64
import quopri
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.plik_mhtml import EkstraktorMhtml
from gnb.ingestion.wejscie import czy_format_binarny, przyjmij_plik
from gnb.potok import przetworz_projekt

_ARTYKUL_HTML = (
    "<html><head><title>Żółć i pancerze</title></head><body><article>"
    "<h1>Żółwie w domu</h1>"
    "<p>Żółwie mają pancerz, który chroni je przed drapieżnikami. To zdanie jest "
    "dostatecznie długie, żeby ekstraktor uznał je za treść artykułu, a nie stopkę.</p>"
    "<p>Drugi akapit opisuje, jak dbać o zwierzę: światło, ciepło i zdrowe jedzenie "
    "muszą być zapewnione każdego dnia, także zimą.</p>"
    "</article></body></html>"
)


def _mhtml(kodowanie: str = "quoted-printable") -> bytes:
    surowe = _ARTYKUL_HTML.encode("utf-8")
    if kodowanie == "base64":
        czesc = base64.encodebytes(surowe).decode("ascii")
    else:
        czesc = quopri.encodestring(surowe).decode("ascii")
    return (
        "From: <Saved by Blink>\r\n"
        "Snapshot-Content-Location: https://przyklad.pl/zolwie\r\n"
        "Subject: =?utf-8?Q?=C5=BB=C3=B3=C5=82wie?=\r\n"
        "MIME-Version: 1.0\r\n"
        'Content-Type: multipart/related; type="text/html"; boundary="GRANICA"\r\n'
        "\r\n--GRANICA\r\n"
        "Content-Type: text/html\r\n"
        "Content-Transfer-Encoding: " + kodowanie + "\r\n"
        "Content-Location: https://przyklad.pl/zolwie\r\n\r\n" + czesc + "\r\n--GRANICA\r\n"
        "Content-Type: image/png\r\n"
        "Content-Transfer-Encoding: base64\r\n\r\n"
        "iVBORw0KGgo=\r\n"
        "--GRANICA--\r\n"
    ).encode("ascii")


@pytest.mark.parametrize("kodowanie", ["quoted-printable", "base64"])
def test_czesc_html_jest_dekodowana_z_polskimi_znakami(kodowanie: str) -> None:
    dokument = EkstraktorMhtml().wyekstrahuj("id", _mhtml(kodowanie))

    assert "Żółwie mają pancerz" in dokument.tekst
    assert "image/png" not in dokument.tekst
    assert dokument.metadane["adres_zapisanej_strony"] == "https://przyklad.pl/zolwie"


def test_ekstraktor_obsluguje_mhtml_i_mht_jako_dokument() -> None:
    ekstraktor = EkstraktorMhtml()

    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "mhtml")
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "mht")
    assert not ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "html")
    assert czy_format_binarny("mhtml") and czy_format_binarny("mht")


def test_plik_bez_czesci_html_i_tekstu_daje_blad_trwaly() -> None:
    bajty = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/related; boundary="G"\r\n\r\n'
        b"--G\r\nContent-Type: image/png\r\nContent-Transfer-Encoding: base64\r\n\r\n"
        b"iVBORw0KGgo=\r\n--G--\r\n"
    )

    with pytest.raises(BladTrwaly):
        EkstraktorMhtml().wyekstrahuj("id", bajty)


def test_plik_mhtml_przechodzi_caly_potok(tmp_path: Path) -> None:
    plik = tmp_path / "zolwie.mhtml"
    plik.write_bytes(_mhtml())
    moment = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)

    wynik = przetworz_projekt(
        [przyjmij_plik(plik, moment)],
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test MHTML",
    )

    assert wynik.liczba_przetworzonych == 1 and wynik.liczba_bledow == 0
    (plik_wynikowy,) = (wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt")
    assert "Żółwie mają pancerz" in plik_wynikowy.read_text(encoding="utf-8")


def test_zadeklarowany_zestaw_znakow_jest_respektowany() -> None:
    tresc = _ARTYKUL_HTML.encode("windows-1250")
    bajty = (
        b"MIME-Version: 1.0\r\n"
        b'Content-Type: multipart/related; boundary="G"\r\n\r\n'
        b'--G\r\nContent-Type: text/html; charset="windows-1250"\r\n'
        b"Content-Transfer-Encoding: 8bit\r\n\r\n" + tresc + b"\r\n--G--\r\n"
    )

    assert "Żółwie mają pancerz" in EkstraktorMhtml().wyekstrahuj("id", bajty).tekst
