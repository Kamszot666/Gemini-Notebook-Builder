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
from gnb.extractors.napisy import KOMUNIKAT_BRAK_TRESCI
from gnb.extractors.plik_csv import KOMUNIKAT_BRAK_DANYCH
from gnb.extractors.plik_pdf import KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik
from gnb.output.raport import NAGLOWEK_MATERIALOW_DO_SPRAWDZENIA
from gnb.potok import KOMUNIKAT_PLIK_BEZ_TRESCI, przetworz_projekt

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


def test_ostrzezenie_ekstraktora_dociera_do_manifestu_i_raportu(tmp_path: Path) -> None:
    """Ostrzeżenie zgłoszone przez ekstraktor przechodzi tę samą drogę co pominięcie.

    Pusty plik napisów i pusty plik CSV kończyły się wcześniej statusem
    „spakowane”, plikiem zawierającym sam nagłówek metadanych i raportem
    mówiącym, że oba źródła są poprawne. Ostrzeżenie ekstraktora nie było
    odczytywane przez nikogo, czyli mechanizm ostrzeżeń nie docierał do
    użytkownika wcale.
    """
    katalog_wejsc = tmp_path / "wejscia"
    katalog_wejsc.mkdir()
    (katalog_wejsc / "puste.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\n\n", encoding="utf-8"
    )
    (katalog_wejsc / "puste.csv").write_text("\n\n", encoding="utf-8")
    moment = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    pozycje = [
        przyjmij_plik(katalog_wejsc / "puste.srt", moment),
        przyjmij_plik(katalog_wejsc / "puste.csv", moment),
    ]

    wynik = przetworz_projekt(
        pozycje,
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test ostrzeżeń",
        zegar=_zegar_krokowy(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodla = {Path(zrodlo["pochodzenie"]).name: zrodlo for zrodlo in manifest["zrodla"]}
    assert KOMUNIKAT_BRAK_TRESCI in zrodla["puste.srt"]["ostrzezenia"]
    assert KOMUNIKAT_BRAK_DANYCH in zrodla["puste.csv"]["ostrzezenia"]
    # Plik złożony z samego nagłówka metadanych jest wykrywany niezależnie od
    # ekstraktora, bo ocena jakości celowo pomija formaty CSV, SRT i VTT.
    assert KOMUNIKAT_PLIK_BEZ_TRESCI in zrodla["puste.srt"]["ostrzezenia"]
    assert KOMUNIKAT_PLIK_BEZ_TRESCI in zrodla["puste.csv"]["ostrzezenia"]

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert NAGLOWEK_MATERIALOW_DO_SPRAWDZENIA in raport
    assert KOMUNIKAT_BRAK_TRESCI in raport
    assert KOMUNIKAT_BRAK_DANYCH in raport
    assert "puste.srt" in raport
    assert "puste.csv" in raport

    log_szczegolowy = (wynik.katalog_projektu / "logi" / "log_szczegolowy.txt").read_text(
        encoding="utf-8"
    )
    assert KOMUNIKAT_BRAK_DANYCH in log_szczegolowy

    # Widok tekstowy manifestu też musi wymieniać ostrzeżenie, bo to jego czyta
    # użytkownik, a nie postać JSON.
    manifest_txt = (wynik.katalog_projektu / "manifest.txt").read_text(encoding="utf-8")
    assert "Ostrzeżenia ekstrakcji:" in manifest_txt


def test_pdf_bez_warstwy_tekstowej_ostrzega_w_manifescie(tmp_path: Path) -> None:
    """Skan PDF bez warstwy tekstowej daje ostrzeżenie widoczne w manifeście i raporcie.

    Dokumentacja formatów obiecywała to zachowanie, zanim ostrzeżenia zaczęły
    docierać gdziekolwiek poza obiekt dokumentu.
    """
    moment = datetime(2026, 8, 28, 9, 0, tzinfo=UTC)
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "pdf_skan.pdf", moment)],
        Konfiguracja(katalog_wynikow=tmp_path),
        nazwa_projektu="Test skanu PDF",
        zegar=_zegar_krokowy(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ in manifest["zrodla"][0]["ostrzezenia"]
    assert KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ in wynik.sciezka_raportu.read_text(encoding="utf-8")
