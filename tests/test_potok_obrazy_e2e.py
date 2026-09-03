"""Testy end-to-end potoku dla źródeł będących obrazami oraz skanami PDF.

Testy zależne od OCR pomijają się z komunikatem, gdy Tesseract nie jest
zainstalowany. Na komputerze użytkownika Tesseract jest, więc realnie się
wykonują.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.images.tesseract import czy_dostepny
from gnb.ingestion.wejscie import przyjmij_plik
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"
_TESSERACT_JEST = czy_dostepny()
_wymaga_tesseracta = pytest.mark.skipif(
    not _TESSERACT_JEST, reason="Tesseract nie jest zainstalowany w tym środowisku."
)


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 3, 12, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


_MOMENT = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


@_wymaga_tesseracta
def test_obraz_przechodzi_potok_i_ma_rozpoznany_tekst_w_wyniku(tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "obraz_wykres.png", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path),
        nazwa_projektu="Obrazy test",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodlo = manifest["zrodla"][0]
    assert zrodlo["status"] == "spakowane"
    assert zrodlo["metadane"]["ocr_wykonany"] == "tak"

    pliki = list((wynik.katalog_projektu / "pliki_wynikowe").iterdir())
    assert pliki
    tresc_laczna = "".join(
        plik.read_text(encoding="utf-8", errors="ignore") for plik in pliki if plik.is_file()
    )
    assert "Wykres testowy" in tresc_laczna


@_wymaga_tesseracta
@pytest.mark.wolne
def test_skan_pdf_jest_rozpoznawany_strona_po_stronie(tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "pdf_skan.pdf", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path, ocr_rozdzielczosc_pdf_dpi=200),
        nazwa_projektu="Skan PDF test",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodlo = manifest["zrodla"][0]
    assert zrodlo["status"] == "spakowane"

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Materiały do sprawdzenia" in raport
    assert "OCR skanu" in raport


def test_skan_pdf_bez_ocr_trafia_do_materialow_do_sprawdzenia(tmp_path: Path) -> None:
    """Skan bez OCR nie znika po cichu: zostaje zapisany i oznaczony do sprawdzenia.

    Zgodne z sekcją ósmą CLAUDE.md: format oceniany z pustą treścią jest
    zapisywany, a nie pomijany, i trafia do sekcji „Materiały do sprawdzenia”
    razem z powodem — brakiem warstwy tekstowej.
    """
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "pdf_skan.pdf", _MOMENT)],
        Konfiguracja(katalog_wynikow=tmp_path, ocr_wlaczony=False),
        nazwa_projektu="Skan bez OCR",
        zegar=_zegar_krokowy(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodlo = manifest["zrodla"][0]
    assert zrodlo["ostrzezenia"]
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Materiały do sprawdzenia" in raport
    assert "warstwy tekstowej" in raport
