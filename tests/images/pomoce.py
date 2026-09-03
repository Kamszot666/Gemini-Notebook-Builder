"""Wspólne pomoce testów modułu obrazów: generowanie obrazów i skanów PDF.

Dane testowe są tworzone programowo, żeby test nie wymagał od nikogo dostarczenia
próbek. Obraz z tekstem jest rysowany dużą czcionką na białym tle, bo taki
rozpoznaje się pewnie, niezależnie od wersji Tesseracta.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont


def obraz_z_tekstem(
    wiersze: list[str],
    *,
    format_pliku: str = "PNG",
    rozmiar: tuple[int, int] = (900, 500),
) -> bytes:
    """Rysuje białą kartkę z podanymi wierszami czarnego tekstu i zwraca jej bajty."""
    obraz = Image.new("RGB", rozmiar, "white")
    rysownik = ImageDraw.Draw(obraz)
    czcionka = ImageFont.load_default(size=48)
    odstep = 70
    for numer, wiersz in enumerate(wiersze):
        rysownik.text((40, 40 + numer * odstep), wiersz, fill="black", font=czcionka)
    bufor = io.BytesIO()
    obraz.save(bufor, format=format_pliku)
    return bufor.getvalue()


def pdf_ze_stron_z_tekstem(strony: list[list[str]]) -> bytes:
    """Buduje PDF, którego każda strona jest obrazem z tekstem, bez warstwy tekstowej.

    Taki PDF odwzorowuje skan: pypdf nie odczyta z niego żadnego tekstu, więc
    potok musi rozpoznać brak warstwy tekstowej i uruchomić OCR.
    """
    obrazy = [
        Image.open(io.BytesIO(obraz_z_tekstem(wiersze, rozmiar=(1000, 700)))).convert("RGB")
        for wiersze in strony
    ]
    bufor = io.BytesIO()
    obrazy[0].save(bufor, format="PDF", save_all=True, append_images=obrazy[1:])
    return bufor.getvalue()
