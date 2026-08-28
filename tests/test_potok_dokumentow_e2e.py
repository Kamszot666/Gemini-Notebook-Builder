"""Test end-to-end potoku dla formatów dokumentowych etapu czwartego.

Sprawdza PDF, DOCX, EPUB, CSV, SRT, VTT i HTML lokalny razem, na gotowych
plikach z `tests/dane`, przez cały potok: walidację, ekstrakcję, normalizację,
ocenę jakości, zapis wyników, manifest i raport.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 8, 28, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _pozycje_formatow_dokumentowych() -> list[PozycjaWejsciowa]:
    moment = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    nazwy = (
        "pdf_tekstowy.pdf",
        "dokument.docx",
        "ksiazka.epub",
        "tabela_metod.csv",
        "napisy.srt",
        "napisy.vtt",
        "artykul_oryginal.html",
    )
    return [przyjmij_plik(KATALOG_DANYCH / nazwa, moment) for nazwa in nazwy]


def test_wszystkie_formaty_dokumentowe_sa_przetwarzane_bez_bledow(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje_formatow_dokumentowych(),
        konfiguracja,
        nazwa_projektu="Test formatów dokumentowych",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 7
    assert wynik.liczba_bledow == 0
    assert wynik.liczba_pominietych == 0

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    pliki_txt = list(katalog_wynikow.glob("*.txt"))
    assert len(pliki_txt) == 7


def test_csv_i_napisy_nie_dostaja_oceny_jakosci_mimo_ekstrakcji(tmp_path: Path) -> None:
    """CSV, SRT i VTT nie mają z natury formatu tytułu ani akapitów.

    Włączenie ich do oceny jakości dawałoby nienaprawialne ostrzeżenie przy
    każdym takim pliku, więc `gnb.potok` celowo je wyłącza.
    """
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje_formatow_dokumentowych(),
        konfiguracja,
        nazwa_projektu="Test wykluczenia oceny",
        zegar=_zegar_krokowy(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodla_wedlug_pochodzenia = {
        Path(zrodlo["pochodzenie"]).name: zrodlo for zrodlo in manifest["zrodla"]
    }

    for nazwa in ("tabela_metod.csv", "napisy.srt", "napisy.vtt"):
        assert zrodla_wedlug_pochodzenia[nazwa]["ocena_jakosci"] is None, nazwa

    # pdf_tekstowy.pdf ma celowo tę samą treść na każdej z trzech stron, patrz
    # tests/dane/README_dane_testowe.md, więc ocena słusznie wykrywa powtórzenie.
    for nazwa in ("dokument.docx", "ksiazka.epub", "artykul_oryginal.html"):
        assert zrodla_wedlug_pochodzenia[nazwa]["ocena_jakosci"] == "poprawna", nazwa
    assert zrodla_wedlug_pochodzenia["pdf_tekstowy.pdf"]["ocena_jakosci"] == "podejrzana"


def test_pdf_skanu_bez_warstwy_tekstowej_trafia_do_materialow_do_sprawdzenia(
    tmp_path: Path,
) -> None:
    moment = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    pozycje = [przyjmij_plik(KATALOG_DANYCH / "pdf_skan.pdf", moment)]

    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test skanu bez OCR", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_przetworzonych == 1
    assert wynik.liczba_bledow == 0

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert manifest["zrodla"][0]["ocena_jakosci"] == "podejrzana"
    assert "Materiały do sprawdzenia" in wynik.sciezka_raportu.read_text(encoding="utf-8")


def test_uszkodzony_pdf_nie_zatrzymuje_przetwarzania_pozostalych_zrodel(tmp_path: Path) -> None:
    moment = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    pozycje = [
        przyjmij_plik(KATALOG_DANYCH / "pdf_uszkodzony.pdf", moment),
        przyjmij_plik(KATALOG_DANYCH / "tabela_metod.csv", moment),
    ]

    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test pliku uszkodzonego", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_bledow == 1
    assert wynik.liczba_przetworzonych == 1


def test_naglowek_pliku_binarnego_ma_pole_plik_a_nie_adres(tmp_path: Path) -> None:
    moment = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    pozycje = [przyjmij_plik(KATALOG_DANYCH / "dokument.docx", moment)]

    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test nagłówka DOCX", zegar=_zegar_krokowy()
    )

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    plik_txt = next(katalog_wynikow.glob("*.txt"))
    naglowek, _, _ = plik_txt.read_text(encoding="utf-8").partition("\n\n")

    assert "Plik: dokument.docx" in naglowek
    assert "Adres:" not in naglowek
