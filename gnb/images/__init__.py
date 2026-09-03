"""Obrazy: opisy merytoryczne, OCR, generowanie tematycznych plików PDF.

Obsługuje JPG, PNG, WebP, TIFF, BMP oraz statyczną klatkę GIF, a dla HEIC
i HEIF korzysta z biblioteki pillow-heif. Nie obsługuje materiałów nutowych
zapisanych jako obraz — tym zajmuje się `gnb.music`.
"""

from __future__ import annotations

from gnb.images.tesseract import (
    UstawieniaOcr,
    czy_dostepny,
    dostepne_jezyki,
    rozpoznaj_tekst,
    rozpoznaj_wiele,
    znajdz_tesseract,
)

__all__ = [
    "UstawieniaOcr",
    "czy_dostepny",
    "dostepne_jezyki",
    "rozpoznaj_tekst",
    "rozpoznaj_wiele",
    "znajdz_tesseract",
]
