"""Wspólne wytwórnie danych testowych dostępne we wszystkich katalogach testów.

Tryb importu „importlib” nie dokłada katalogów testów do ścieżki modułów, więc
wspólne pomoce nie mogą być zwykłym modułem importowanym między plikami. Są tu
udostępnione jako wytwórnie: fikstura zwraca funkcję, którą test woła z własnymi
argumentami.

Dane obrazów i skanów są tworzone programowo, żeby żaden test nie wymagał
dostarczenia próbek z zewnątrz.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import pytest
from PIL import Image, ImageDraw, ImageFont


def _obraz_z_tekstem(
    wiersze: list[str],
    *,
    format_pliku: str = "PNG",
    rozmiar: tuple[int, int] = (900, 500),
) -> bytes:
    """Rysuje białą kartkę z wierszami czarnego tekstu dużą czcionką i zwraca jej bajty.

    Duża, wyraźna czcionka na białym tle rozpoznaje się pewnie niezależnie od
    wersji Tesseracta, więc test OCR nie czerwieni się od drobiazgów renderowania.
    """
    obraz = Image.new("RGB", rozmiar, "white")
    rysownik = ImageDraw.Draw(obraz)
    czcionka = ImageFont.load_default(size=48)
    for numer, wiersz in enumerate(wiersze):
        rysownik.text((40, 40 + numer * 70), wiersz, fill="black", font=czcionka)
    bufor = io.BytesIO()
    obraz.save(bufor, format=format_pliku)
    return bufor.getvalue()


def _pdf_ze_stron_z_tekstem(strony: list[list[str]]) -> bytes:
    """Buduje PDF, którego każda strona jest obrazem z tekstem, bez warstwy tekstowej.

    Taki PDF odwzorowuje skan: pypdf nie odczyta z niego żadnego tekstu, więc
    potok musi rozpoznać brak warstwy tekstowej i uruchomić OCR.
    """
    obrazy = [
        Image.open(io.BytesIO(_obraz_z_tekstem(wiersze, rozmiar=(1000, 700)))).convert("RGB")
        for wiersze in strony
    ]
    bufor = io.BytesIO()
    obrazy[0].save(bufor, format="PDF", save_all=True, append_images=obrazy[1:])
    return bufor.getvalue()


@pytest.fixture
def obraz_z_tekstem() -> Callable[..., bytes]:
    """Wytwórnia obrazu z tekstem. Wołanie: ``obraz_z_tekstem(["WIERSZ"], format_pliku=...)``."""
    return _obraz_z_tekstem


@pytest.fixture
def pdf_ze_stron_z_tekstem() -> Callable[[list[list[str]]], bytes]:
    """Wytwórnia skanu PDF. Wołanie: ``pdf_ze_stron_z_tekstem([["strona 1"], ["strona 2"]])``."""
    return _pdf_ze_stron_z_tekstem
