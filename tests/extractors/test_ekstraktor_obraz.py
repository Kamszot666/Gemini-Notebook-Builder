"""Testy ekstraktora plików obrazów: opis merytoryczny i tekst z OCR.

Testy używające OCR pomijają się z komunikatem, gdy nie da się rozpoznać
polskiego tekstu: brak Tesseracta albo brak jego danych językowych
``pol.traineddata``. Rozróżnienie tych braków niesie fikstura ``wymaga_ocr_pol``.
Reszta, w tym budowanie opisu z metadanych i obsługa plików uszkodzonych, działa
niezależnie od obecności Tesseracta.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import FormatNieobslugiwany
from gnb.extractors import plik_obraz
from gnb.extractors.plik_obraz import (
    KOMUNIKAT_BRAK_PILLOW_HEIF,
    EkstraktorObrazu,
)
from gnb.images.tesseract import UstawieniaOcr

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_obsluguje_wylacznie_obrazy_jako_zrodlo_typu_obraz() -> None:
    ekstraktor = EkstraktorObrazu()
    assert ekstraktor.obsluguje(TypZrodla.PLIK_OBRAZ, "png") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_OBRAZ, "heic") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "png") is False
    assert ekstraktor.obsluguje(TypZrodla.PLIK_OBRAZ, "pdf") is False


def test_bez_ocr_wynik_ma_wymiary_i_zaznacza_ze_ocr_nie_wykonano() -> None:
    bajty = (KATALOG_DANYCH / "obraz_wykres.png").read_bytes()

    dokument = EkstraktorObrazu().wyekstrahuj("obraz-1", bajty)

    assert "900 na 600 pikseli" in dokument.tekst
    assert "OCR nie został wykonany" in dokument.tekst
    assert dokument.metadane["ocr_wykonany"] == "nie"
    assert dokument.metoda_ekstrakcji == "obraz"


def test_metadane_opisowe_z_pliku_png_trafiaja_do_opisu(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obraz = Image.open(io.BytesIO(obraz_z_tekstem(["cokolwiek"])))
    informacje = PngInfo()
    informacje.add_text("Description", "Diagram architektury potoku przetwarzania")
    bufor = io.BytesIO()
    obraz.save(bufor, format="PNG", pnginfo=informacje)

    dokument = EkstraktorObrazu().wyekstrahuj("obraz-2", bufor.getvalue())

    assert "Diagram architektury potoku przetwarzania" in dokument.tekst


def test_uszkodzony_obraz_konczy_sie_formatnieobslugiwany() -> None:
    bajty = (KATALOG_DANYCH / "obraz_uszkodzony.jpg").read_bytes()

    with pytest.raises(FormatNieobslugiwany):
        EkstraktorObrazu().wyekstrahuj("obraz-3", bajty)


def test_brak_pillow_heif_dla_pliku_heic_daje_czytelny_komunikat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plik z sygnaturą HEIF bez biblioteki pillow-heif kończy się wskazówką instalacji.

    Rejestracja obsługi HEIF jest podmieniona na pustą, więc test działa tak
    samo, gdy pillow-heif jest zainstalowany, jak i gdy go nie ma.
    """
    monkeypatch.setattr(plik_obraz, "_zarejestruj_heif_jesli_dostepne", lambda: None)
    bajty = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64

    with pytest.raises(FormatNieobslugiwany, match="pillow-heif"):
        EkstraktorObrazu().wyekstrahuj("obraz-4", bajty)

    assert "pip install gnb[obrazy-heic]" in KOMUNIKAT_BRAK_PILLOW_HEIF


def test_obraz_bez_opisu_i_bez_ocr_zapisuje_jawny_brak_opisu(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    """Obraz bez metadanych i bez OCR nie jest pomijany: zapisuje jawny brak opisu.

    Decyzja siódma etapu ósmego: brak opisu ma być zapisany wprost, a nie
    zamieniony na pusty plik ani na ciche pominięcie.
    """
    dokument = EkstraktorObrazu().wyekstrahuj("obraz-5", obraz_z_tekstem(["x"]))

    assert dokument.tekst != ""
    assert "Brak opisu" in dokument.tekst
    assert "pikseli" in dokument.tekst


def test_z_wlaczonym_ocr_wynik_zawiera_rozpoznany_tekst(wymaga_ocr_pol: None) -> None:
    bajty = (KATALOG_DANYCH / "obraz_wykres.png").read_bytes()

    dokument = EkstraktorObrazu(UstawieniaOcr(jezyk="pol"), ocr_wlaczony=True).wyekstrahuj(
        "obraz-6", bajty
    )

    assert "Wykres testowy" in dokument.tekst
    assert dokument.metoda_ekstrakcji == "obraz-ocr"
    assert dokument.metadane["ocr_wykonany"] == "tak"
    assert dokument.metadane["ocena_ocr"] in {"poprawna", "pusta", "podejrzana"}


def test_wlaczony_ocr_bez_tesseracta_daje_ostrzezenie(
    monkeypatch: pytest.MonkeyPatch, obraz_z_tekstem: Callable[..., bytes]
) -> None:
    monkeypatch.setattr(plik_obraz, "czy_dostepny", lambda _sciezka="": False)

    dokument = EkstraktorObrazu(UstawieniaOcr(), ocr_wlaczony=True).wyekstrahuj(
        "obraz-7", obraz_z_tekstem(["opis w metadanych brak"])
    )

    assert any("Tesseract" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)
    assert dokument.metadane["ocr_wykonany"] == "nie"
