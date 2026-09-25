"""Testy bezpiecznego odczytu archiwów ZIP z plikami XML."""

from __future__ import annotations

import io
import zipfile

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.extractors import pakiet_xml
from gnb.extractors.pakiet_xml import (
    atrybut,
    jeden_wiersz,
    nazwa_lokalna,
    otworz_archiwum,
    wczytaj_bajty_wpisu,
    wczytaj_xml,
    wczytaj_xml_opcjonalny,
    zbuduj_drzewo,
)


def _archiwum(wpisy: dict[str, bytes]) -> bytes:
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w", zipfile.ZIP_DEFLATED) as zip_:
        for nazwa, dane in wpisy.items():
            zip_.writestr(nazwa, dane)
    return bufor.getvalue()


def test_poprawne_archiwum_i_xml_sa_odczytane() -> None:
    archiwum = otworz_archiwum(_archiwum({"a.xml": b"<a><b>tekst</b></a>"}), "id", "dokumentem")

    korzen = wczytaj_xml(archiwum, "a.xml", "id")

    assert korzen.tag == "a"
    assert korzen.findtext("b") == "tekst"


def test_plik_niebedacy_archiwum_zglasza_blad_trwaly() -> None:
    with pytest.raises(BladTrwaly, match="nie jest poprawnym dokumentem ODT"):
        otworz_archiwum(b"to nie jest zip", "id", "dokumentem ODT")


def test_brak_wymaganego_wpisu_zglasza_blad_trwaly() -> None:
    archiwum = otworz_archiwum(_archiwum({"a.xml": b"<a/>"}), "id", "dokumentem")

    with pytest.raises(BladTrwaly, match="brakuje wymaganego wpisu"):
        wczytaj_xml(archiwum, "b.xml", "id")
    assert wczytaj_xml_opcjonalny(archiwum, "b.xml", "id") is None


def test_deklaracja_typu_dokumentu_jest_odrzucana() -> None:
    dane = b'<?xml version="1.0"?><!DOCTYPE a [<!ELEMENT a ANY>]><a>x</a>'

    with pytest.raises(BladTrwaly, match="deklarację typu dokumentu albo definicję encji"):
        zbuduj_drzewo(dane, "wpis", "id")


def test_rozszerzanie_encji_jest_odrzucane_zanim_dojdzie_do_parsera() -> None:
    """Klasyczna bomba „miliard śmiechów”: małe archiwum rozwijające się do gigabajtów."""
    dane = (
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
        b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        b"<lolz>&lol2;</lolz>"
    )

    with pytest.raises(BladTrwaly, match="niebezpieczny"):
        zbuduj_drzewo(dane, "wpis", "id")


def test_entity_bez_doctype_tez_jest_odrzucane() -> None:
    with pytest.raises(BladTrwaly):
        zbuduj_drzewo(b'<a><!ENTITY x "y"></a>', "wpis", "id")


def test_niepoprawny_xml_zglasza_blad_trwaly() -> None:
    with pytest.raises(BladTrwaly, match="nie jest poprawnym XML"):
        zbuduj_drzewo(b"<a><b></a>", "wpis", "id")


def test_wpis_ponad_limit_rozmiaru_jest_odrzucany_wedlug_deklaracji(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pakiet_xml, "LIMIT_ROZMIARU_WPISU_BAJTOW", 100)
    archiwum = otworz_archiwum(_archiwum({"duzy.xml": b"<a>" + b"x" * 500 + b"</a>"}), "id", "d")

    with pytest.raises(BladTrwaly, match="ponad limit"):
        wczytaj_bajty_wpisu(archiwum, "duzy.xml", "id")


def test_wpis_z_zanizonym_rozmiarem_w_naglowku_jest_odrzucany_wedlug_odczytu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deklaracja rozmiaru w archiwum może kłamać: odczyt kończy się błędem, nie pamięcią."""
    monkeypatch.setattr(pakiet_xml, "LIMIT_ROZMIARU_WPISU_BAJTOW", 100)
    archiwum = otworz_archiwum(_archiwum({"duzy.xml": b"<a>" + b"x" * 500 + b"</a>"}), "id", "d")
    informacja = archiwum.getinfo("duzy.xml")
    informacja.file_size = 10

    with pytest.raises(BladTrwaly):
        wczytaj_bajty_wpisu(archiwum, "duzy.xml", "id")


def test_archiwum_z_ogromna_liczba_wpisow_jest_odrzucane(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pakiet_xml, "LIMIT_LICZBY_WPISOW", 3)
    wpisy = {f"{numer}.xml": b"<a/>" for numer in range(5)}

    with pytest.raises(BladTrwaly, match="wpisów"):
        otworz_archiwum(_archiwum(wpisy), "id", "d")


def test_pomocniki_nazw_i_tekstu() -> None:
    korzen = zbuduj_drzewo(b'<x:a xmlns:x="urn:x" x:c="1"/>', "wpis", "id")

    assert nazwa_lokalna(korzen.tag) == "a"
    assert atrybut(korzen, "c") == "1"
    assert atrybut(korzen, "brak") is None
    assert jeden_wiersz("  a\t b \n c  ") == "a b c"
