"""Wspólne wytwórnie danych testowych dostępne we wszystkich katalogach testów.

Tryb importu „importlib” nie dokłada katalogów testów do ścieżki modułów, więc
wspólne pomoce nie mogą być zwykłym modułem importowanym między plikami. Są tu
udostępnione jako wytwórnie: fikstura zwraca funkcję, którą test woła z własnymi
argumentami.

Dane obrazów i skanów są tworzone programowo, żeby żaden test nie wymagał
dostarczenia próbek z zewnątrz.
"""

from __future__ import annotations

import functools
import io
from collections.abc import Callable

import pytest
from PIL import Image, ImageDraw, ImageFont


@functools.lru_cache(maxsize=1)
def _powod_pominiecia_ocr_pol() -> str | None:
    """Zwraca powód pominięcia testów OCR po polsku albo ``None``, gdy OCR działa.

    Strażnik rozróżnia dwa braki, które w komunikacie błędu wyglądałyby tak samo:
    brak samego Tesseracta oraz obecny Tesseract bez danych językowych
    ``pol.traineddata``. Drugi przypadek nie jest regresją aplikacji — wołanie
    OCR z językiem ``pol`` kończy się wtedy błędem Tesseracta, choć kod aplikacji
    jest sprawny — więc test ma się pominąć z czytelnym powodem, a nie
    zaczerwienić. Wynik jest liczony raz na sesję testów.
    """
    from gnb.images.tesseract import brakujace_dane_jezykowe, czy_dostepny

    if not czy_dostepny():
        return "Tesseract nie jest zainstalowany w tym środowisku."
    brakujace = brakujace_dane_jezykowe("pol")
    if brakujace:
        return (
            "Tesseract jest zainstalowany, ale brakuje jego danych językowych dla "
            f"języka: {', '.join(brakujace)} (plik pol.traineddata). OCR polskiego "
            "tekstu nie zadziała, dopóki polskie dane językowe nie zostaną doinstalowane."
        )
    return None


@pytest.fixture
def wymaga_ocr_pol() -> None:
    """Pomija test, gdy w środowisku nie da się wykonać OCR polskiego tekstu.

    Test wołający Tesseract z językiem ``pol`` używa tej fikstury zamiast markera
    sprawdzającego samą obecność programu. Dzięki temu środowisko z Tesseractem,
    ale bez pliku ``pol.traineddata``, daje pominięcie z jasnym powodem, a nie
    serię błędów wyglądających jak regresja.
    """
    powod = _powod_pominiecia_ocr_pol()
    if powod is not None:
        pytest.skip(powod)


# Model transkrypcji używany w testach. Model średni z konfiguracji domyślnej
# służy jakości rozpoznania polskiego, a testy sprawdzają działanie kodu, nie
# jakość, więc biorą model najmniejszy.
MODEL_WHISPER_DO_TESTOW = "tiny"


@functools.lru_cache(maxsize=1)
def _powod_pominiecia_faster_whisper() -> str | None:
    """Zwraca powód pominięcia testów wymagających biblioteki faster-whisper.

    Na komputerze deweloperskim Inteligentne sterowanie aplikacjami blokuje PyAV,
    więc `czy_dostepna_biblioteka` sprawdza też, czy strażnik atrapy modułu ``av``
    pozwolił zaimportować resztę biblioteki. Wynik jest liczony raz na sesję.
    """
    from gnb.audio.transkrypcja import czy_dostepna_biblioteka

    if not czy_dostepna_biblioteka():
        return (
            "Biblioteka faster-whisper nie jest dostępna w tym środowisku "
            "(zainstaluj ją poleceniem „pip install gnb[audio]”)."
        )
    return None


@functools.lru_cache(maxsize=1)
def _powod_pominiecia_modelu_whisper() -> str | None:
    """Zwraca powód pominięcia testów wymagających pobranego modelu Whispera.

    Strażnik rozróżnia dwa braki: brak samej biblioteki oraz obecną bibliotekę
    bez pobranego modelu. Drugi przypadek nie jest regresją aplikacji — bez sieci
    modelu nie da się pobrać — więc test ma się pominąć z czytelnym powodem,
    a nie zaczerwienić. Wzoruje się na `_powod_pominiecia_ocr_pol`.
    """
    powod = _powod_pominiecia_faster_whisper()
    if powod is not None:
        return powod
    from gnb.audio.transkrypcja import model_dostepny_lokalnie

    if not model_dostepny_lokalnie(MODEL_WHISPER_DO_TESTOW, "int8"):
        return (
            f"Model transkrypcji „{MODEL_WHISPER_DO_TESTOW}” nie jest pobrany na dysk, "
            "a testy nie korzystają z sieci. Pobierz go raz, uruchamiając transkrypcję "
            "dowolnego nagrania mowy, albo uruchom te testy z markerem „siec”."
        )
    return None


@pytest.fixture
def wymaga_faster_whisper() -> None:
    """Pomija test, gdy biblioteki faster-whisper nie da się zaimportować."""
    powod = _powod_pominiecia_faster_whisper()
    if powod is not None:
        pytest.skip(powod)


@pytest.fixture
def wymaga_model_whisper() -> None:
    """Pomija test, gdy nie da się wykonać transkrypcji: brak biblioteki albo modelu."""
    powod = _powod_pominiecia_modelu_whisper()
    if powod is not None:
        pytest.skip(powod)


@pytest.fixture
def wymaga_ffmpeg() -> None:
    """Pomija test, gdy w środowisku nie ma programu FFmpeg."""
    from gnb.audio.dekodowanie import czy_dostepny

    if not czy_dostepny():
        pytest.skip("FFmpeg nie jest zainstalowany w tym środowisku.")


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
