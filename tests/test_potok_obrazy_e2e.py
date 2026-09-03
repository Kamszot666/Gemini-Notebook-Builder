"""Testy end-to-end potoku dla źródeł będących obrazami oraz skanami PDF.

Testy zależne od OCR pomijają się z komunikatem, gdy Tesseract nie jest
zainstalowany. Na komputerze użytkownika Tesseract jest, więc realnie się
wykonują.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader

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

    pliki_pdf = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.pdf"))
    assert len(pliki_pdf) == 1
    czytnik = PdfReader(io.BytesIO(pliki_pdf[0].read_bytes()))
    tekst_pdf = "".join((strona.extract_text() or "") for strona in czytnik.pages)
    assert "Wykres testowy" in tekst_pdf
    assert zrodlo["identyfikator"] in tekst_pdf

    wpis_wyniku = next(w for w in manifest["wyniki"] if w["format"] == "pdf")
    assert wpis_wyniku["liczba_slow"] > 0


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


def test_grupa_obrazow_daje_jeden_plik_pdf_zajmujacy_jeden_slot(tmp_path: Path) -> None:
    """Kilka obrazów jednej grupy tematycznej trafia do jednego pliku PDF.

    Plik PDF ma stronę na obraz, a w limicie źródeł notatnika zajmuje jeden slot,
    mimo że łączy kilka obrazów.
    """
    obrazy = [
        przyjmij_plik(KATALOG_DANYCH / nazwa, _MOMENT, grupa="Materiały wizualne")
        for nazwa in ("obraz_wykres.png", "obraz_zdjecie.jpg", "obraz.webp")
    ]
    # Deduplikacja jest tu wyłączona: obrazy testowe bez OCR mają niemal
    # identyczny opis, więc inaczej zlałyby się w jeden. Test dotyczy pakowania
    # grupy w jeden plik PDF, a nie deduplikacji.
    wynik = przetworz_projekt(
        obrazy,
        Konfiguracja(
            katalog_wynikow=tmp_path,
            ocr_wlaczony=False,
            deduplikacja_hash_wlaczona=False,
            deduplikacja_kosmetyczna_wlaczona=False,
            deduplikacja_podobienstwo_wlaczone=False,
        ),
        nazwa_projektu="Grupa obrazów",
        zegar=_zegar_krokowy(),
    )

    pliki_pdf = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.pdf"))
    assert len(pliki_pdf) == 1
    czytnik = PdfReader(io.BytesIO(pliki_pdf[0].read_bytes()))
    assert len(czytnik.pages) == 3

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    wpisy_pdf = [w for w in manifest["wyniki"] if w["format"] == "pdf"]
    assert len(wpisy_pdf) == 1
    assert wpisy_pdf[0]["liczba_zrodel"] == 3

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba plików PDF: 1" in raport
    assert "plików do wgrania 1" in raport


def test_obrazy_bez_grupy_tez_daja_plik_pdf(tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        [
            przyjmij_plik(KATALOG_DANYCH / "obraz_wykres.png", _MOMENT),
            przyjmij_plik(KATALOG_DANYCH / "obraz.tiff", _MOMENT),
        ],
        Konfiguracja(
            katalog_wynikow=tmp_path,
            ocr_wlaczony=False,
            deduplikacja_hash_wlaczona=False,
            deduplikacja_kosmetyczna_wlaczona=False,
            deduplikacja_podobienstwo_wlaczone=False,
        ),
        nazwa_projektu="Obrazy bez grupy",
        zegar=_zegar_krokowy(),
    )

    pliki_pdf = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.pdf"))
    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_pdf) == 1
    assert pliki_txt == []


def test_grupa_mieszana_daje_pdf_dla_obrazow_i_txt_dla_tekstu(tmp_path: Path) -> None:
    """Grupa z obrazem i tekstem daje dwa pliki: PDF dla obrazu, TXT dla tekstu.

    To jest świadomie przyjęte uproszczenie: mieszana grupa zajmuje dwa sloty.
    """
    from gnb.ingestion.wejscie import przyjmij_tekst

    wynik = przetworz_projekt(
        [
            przyjmij_plik(KATALOG_DANYCH / "obraz_wykres.png", _MOMENT, grupa="Temat"),
            przyjmij_tekst("Notatka tekstowa w tej samej grupie.", _MOMENT, grupa="Temat"),
        ],
        Konfiguracja(katalog_wynikow=tmp_path, ocr_wlaczony=False),
        nazwa_projektu="Grupa mieszana",
        zegar=_zegar_krokowy(),
    )

    katalog = wynik.katalog_projektu / "pliki_wynikowe"
    assert len(list(katalog.glob("*.pdf"))) == 1
    assert len(list(katalog.glob("*.txt"))) == 1


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
