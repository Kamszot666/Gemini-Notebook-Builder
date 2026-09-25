"""Test end-to-end potoku dla formatów biurowych i tekstowych z etapu czternastego.

Sprawdza ODT, ODS, ODP, PPTX, XLSX, XLS, RTF, TSV oraz pliki tekstu prostego przez
cały potok: walidację, ekstrakcję, normalizację, ocenę jakości, zapis wyników,
manifest i raport. Pliki biurowe w `tests/dane/formaty` to prawdziwe pliki
z LibreOffice, a plik z brakującym programem i pliki uszkodzone pokazują, że jeden
zły plik nie zatrzymuje reszty.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik
from gnb.potok import WynikPrzetwarzania, przetworz_projekt

DANE = Path(__file__).resolve().parent / "dane" / "formaty"
_MOMENT = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)


def _zegar() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 26, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _konfiguracja(tmp_path: Path, **nadpisania: Any) -> Konfiguracja:
    """Konfiguracja bez deduplikacji: te same treści w kilku formatach nie mają się scalać."""
    ustawienia: dict[str, Any] = {
        "katalog_wynikow": tmp_path / "wyniki",
        "deduplikacja_hash_wlaczona": False,
        "deduplikacja_kosmetyczna_wlaczona": False,
        "deduplikacja_podobienstwo_wlaczone": False,
    }
    ustawienia.update(nadpisania)
    return Konfiguracja(**ustawienia)


def _pozycje(*sciezki: Path) -> list[PozycjaWejsciowa]:
    return [przyjmij_plik(sciezka, _MOMENT) for sciezka in sciezki]


def _przetworz(
    tmp_path: Path, pozycje: list[PozycjaWejsciowa], **konfiguracja: Any
) -> WynikPrzetwarzania:
    return przetworz_projekt(
        pozycje,
        _konfiguracja(tmp_path, **konfiguracja),
        nazwa_projektu="Formaty biurowe",
        zegar=_zegar(),
    )


def _manifest(wynik: WynikPrzetwarzania) -> dict[str, Any]:
    return json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))


def _po_pochodzeniu(wynik: WynikPrzetwarzania) -> dict[str, dict[str, Any]]:
    return {zrodlo["pochodzenie"]: zrodlo for zrodlo in _manifest(wynik)["zrodla"]}


def _tresc_wynikow(wynik: WynikPrzetwarzania) -> str:
    katalog = wynik.katalog_projektu / "pliki_wynikowe"
    return "\n".join(plik.read_text(encoding="utf-8") for plik in sorted(katalog.glob("*.txt")))


def test_formaty_biurowe_przechodza_caly_potok_z_trescia_w_wynikach(tmp_path: Path) -> None:
    pliki = [
        DANE / "dokument.odt",
        DANE / "arkusz.ods",
        DANE / "prezentacja.odp",
        DANE / "prezentacja.pptx",
        DANE / "arkusz.xlsx",
        DANE / "arkusz.xls",
        DANE / "dokument.rtf",
    ]

    wynik = _przetworz(tmp_path, _pozycje(*pliki))

    assert wynik.liczba_bledow == 0
    assert wynik.liczba_pominietych == 0
    assert wynik.liczba_przetworzonych == len(pliki)
    zrodla = _po_pochodzeniu(wynik)
    assert {zrodlo["typ"] for zrodlo in zrodla.values()} == {"plik_dokument"}
    assert all(zrodlo["status"] == "spakowane" for zrodlo in zrodla.values())

    tresc = _tresc_wynikow(wynik)
    assert "Raport o żółwiach" in tresc  # ODT, tytuł z metadanych
    assert "Anna Nowak" in tresc
    assert "Zażółć gęślą jaźń" in tresc
    assert "Przypis o pancerzu żółwia." in tresc
    assert "Żółta ścierka" in tresc  # ODS, XLSX, XLS
    assert "2026-05-07" in tresc
    assert "Powiedz o pancerzu." in tresc  # ODP i PPTX, notatki mówcy
    assert "Dziękuję za uwagę." in tresc


def test_ostrzezenia_ekstraktorow_biurowych_trafiaja_do_raportu(tmp_path: Path) -> None:
    wynik = _przetworz(tmp_path, _pozycje(DANE / "arkusz.xlsx", DANE / "dokument.rtf"))

    zrodla = _po_pochodzeniu(wynik)
    assert any("formatem walutowym" in o for o in zrodla["arkusz.xlsx"]["ostrzezenia"])
    assert any("zawiera tabele" in o for o in zrodla["dokument.rtf"]["ostrzezenia"])
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Materiały do sprawdzenia" in raport
    assert "formatem walutowym" in raport


def test_xlsx_z_formula_bez_wyniku_jest_do_sprawdzenia(tmp_path: Path) -> None:
    zeszyt = Workbook()
    arkusz = zeszyt.active
    arkusz.append(["a", "b", "suma"])
    arkusz.append([1, 2, "=A2+B2"])
    plik = tmp_path / "wzory.xlsx"
    zeszyt.save(plik)

    wynik = _przetworz(tmp_path, _pozycje(plik))

    zrodlo = _po_pochodzeniu(wynik)["wzory.xlsx"]
    assert zrodlo["status"] == "spakowane"
    assert any("formuł bez zapisanego wyniku" in o for o in zrodlo["ostrzezenia"])


def test_tsv_i_pliki_tekstu_prostego_przechodza_potok(tmp_path: Path) -> None:
    pliki = {
        "dane.tsv": "Imię\tMiasto\nAnna\tKraków, Polska\n",
        "konfig.json": '{"nazwa": "żółw", "liczba": 3}\n',
        "opis.xml": '<?xml version="1.0"?>\n<a><b>zażółć</b></a>\n',
        "ustawienia.yaml": "klucz: wartość\nlista:\n  - a\n  - b\n",
        "ustawienia.toml": 'tytuł = "Test"\n[sekcja]\nx = 1\n',
        "stary.ini": "[a]\nb = c\n",
        "dziennik.log": "2026-09-26 zdarzenie pierwsze\n2026-09-26 zdarzenie drugie\n",
    }
    sciezki: list[Path] = []
    for nazwa, tresc in pliki.items():
        sciezka = tmp_path / nazwa
        sciezka.write_text(tresc, encoding="utf-8")
        sciezki.append(sciezka)

    wynik = _przetworz(tmp_path, _pozycje(*sciezki))

    assert wynik.liczba_bledow == 0
    assert wynik.liczba_przetworzonych == len(pliki)
    zrodla = _po_pochodzeniu(wynik)
    assert zrodla["dane.tsv"]["typ"] == "plik_dokument"
    assert zrodla["konfig.json"]["typ"] == "plik_tekstowy"
    tresc = _tresc_wynikow(wynik)
    assert "| Anna | Kraków, Polska |" in tresc or "Miasto: Kraków, Polska" in tresc
    assert '"nazwa": "żółw"' in tresc
    assert "<b>zażółć</b>" in tresc
    assert "klucz: wartość" in tresc
    assert "zdarzenie drugie" in tresc


def test_doc_i_ppt_bez_libreoffice_sa_pominiete_z_komunikatem_a_reszta_dziala(
    tmp_path: Path,
) -> None:
    doc = tmp_path / "stary.doc"
    doc.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 200)
    ppt = tmp_path / "stara.ppt"
    ppt.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x01" * 200)

    wynik = _przetworz(
        tmp_path,
        _pozycje(doc, ppt, DANE / "dokument.odt"),
        sciezka_libreoffice=str(tmp_path / "nie_ma" / "soffice.com"),
    )

    zrodla = _po_pochodzeniu(wynik)
    assert zrodla["stary.doc"]["status"] == "pominiete"
    assert zrodla["stara.ppt"]["status"] == "pominiete"
    assert "sciezka_libreoffice" in zrodla["stary.doc"]["komunikat_bledu"]
    assert zrodla["dokument.odt"]["status"] == "spakowane"
    assert wynik.liczba_bledow == 0
    assert wynik.liczba_pominietych == 2


def test_uszkodzone_pliki_biurowe_koncza_sie_bledem_ale_nie_zatrzymuja_reszty(
    tmp_path: Path,
) -> None:
    zly_odt = tmp_path / "zly.odt"
    zly_odt.write_bytes(b"to nie jest archiwum")
    zly_xlsx = tmp_path / "zly.xlsx"
    zly_xlsx.write_bytes(b"to nie jest skoroszyt")
    zly_rtf = tmp_path / "zly.rtf"
    zly_rtf.write_bytes(b"to nie jest rtf")
    zly_pptx = tmp_path / "zly.pptx"
    zly_pptx.write_bytes(b"to nie jest prezentacja")

    wynik = _przetworz(
        tmp_path, _pozycje(zly_odt, zly_xlsx, zly_rtf, zly_pptx, DANE / "arkusz.ods")
    )

    zrodla = _po_pochodzeniu(wynik)
    for nazwa in ("zly.odt", "zly.xlsx", "zly.rtf", "zly.pptx"):
        assert zrodla[nazwa]["status"] == "blad", nazwa
        assert zrodla[nazwa]["komunikat_bledu"]
    assert zrodla["arkusz.ods"]["status"] == "spakowane"
    assert wynik.liczba_bledow == 4


def test_nieobslugiwany_format_wymienia_nowe_formaty_w_komunikacie(tmp_path: Path) -> None:
    plik = tmp_path / "sekrety.env"
    plik.write_text("KLUCZ=wartosc\n", encoding="utf-8")

    wynik = _przetworz(tmp_path, _pozycje(plik))

    zrodlo = _manifest(wynik)["zrodla"][0]
    assert zrodlo["status"] == "blad"
    komunikat = zrodlo["komunikat_bledu"]
    for format_pliku in ("odt", "ods", "odp", "pptx", "xlsx", "xls", "rtf", "doc", "ppt", "tsv"):
        assert format_pliku in komunikat
    assert "env," not in komunikat
