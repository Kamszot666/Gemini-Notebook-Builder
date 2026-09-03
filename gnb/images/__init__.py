"""Obrazy: opisy merytoryczne, OCR, generowanie tematycznych plików PDF.

Obsługuje JPG, PNG, WebP, TIFF, BMP oraz statyczną klatkę GIF, a dla HEIC
i HEIF korzysta z biblioteki pillow-heif. Nie obsługuje materiałów nutowych
zapisanych jako obraz — tym zajmuje się `gnb.music`.
"""

from __future__ import annotations

from gnb.images.ocena_ocr import OcenaOcr, ocen_ocr
from gnb.images.opis import BRAK_OPISU, MaterialDoOpisu, zbuduj_opis
from gnb.images.rasteryzacja import liczba_stron, rasteryzuj_strony
from gnb.images.tesseract import (
    UstawieniaOcr,
    czy_dostepny,
    dostepne_jezyki,
    rozpoznaj_tekst,
    rozpoznaj_wiele,
    znajdz_tesseract,
)

__all__ = [
    "BRAK_OPISU",
    "MaterialDoOpisu",
    "OcenaOcr",
    "UstawieniaOcr",
    "czy_dostepny",
    "dostepne_jezyki",
    "liczba_stron",
    "ocen_ocr",
    "rasteryzuj_strony",
    "rozpoznaj_tekst",
    "rozpoznaj_wiele",
    "zbuduj_opis",
    "znajdz_tesseract",
]
