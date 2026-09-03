"""Rozkodowanie nagrań audio do fali dźwiękowej przez podproces FFmpeg.

Ścieżka audio używa wyłącznie FFmpega do zamiany dowolnego formatu nagrania na
jednolitą falę: częstotliwość szesnaście kiloherców, jeden kanał, próbki
zmiennoprzecinkowe pojedynczej precyzji. Jest to jedna ścieżka kodu na każdym
systemie, bez rozgałęzień.

Nie korzystamy z dekodera wbudowanego w faster-whisper, czyli z biblioteki PyAV,
z dwóch powodów naraz. Po pierwsze, na komputerze deweloperskim Inteligentne
sterowanie aplikacjami Windows blokuje niepodpisane biblioteki natywne PyAV,
przez co sama próba jej zaimportowania kończy się błędem — patrz strażnik atrapy
w `gnb.audio.transkrypcja`. Po drugie, nawet gdyby PyAV działało, dwie ścieżki
dekodowania to dwa źródła subtelnych różnic w wyniku; jedna ścieżka jest
prostsza w utrzymaniu i przewidywalna. FFmpeg jest podpisany, jest w zmiennej
PATH i jest już narzędziem sprawdzanym przez diagnostykę.

FFmpeg jest wołany tym samym wzorcem co Tesseract w `gnb.images.tesseract`:
podproces z pełną ścieżką odnalezioną w PATH, wynik odbierany strumieniem.
Nagranie trafia do FFmpega jako plik tymczasowy, a nie przez standardowe
wejście, ponieważ kontenery takie jak MP4 i M4A trzymają nagłówek na końcu pliku
i wymagają wejścia, po którym można się przemieszczać; strumień standardowego
wejścia tego nie zapewnia. Plik tymczasowy powstaje poza katalogiem projektu
i jest usuwany w bloku `finally`, także przy błędzie.

Brak FFmpega nie wywraca aplikacji: kończy się wyjątkiem `BrakNarzedzia`
z czytelnym komunikatem, a potok zamienia go na kontrolowane pominięcie źródła.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import numpy.typing as npt

from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly, BrakNarzedzia

NAZWA_PLIKU_WYKONYWALNEGO = "ffmpeg"

# Częstotliwość próbkowania, do której sprowadzane jest każde nagranie. Modele
# Whisper są trenowane na szesnastu kilohercach i faster-whisper oczekuje takiej
# fali, więc wartość nie jest konfigurowalna.
CZESTOTLIWOSC_PROBKOWANIA = 16_000

# Górny limit czasu jednego wywołania FFmpega. Rozkodowanie godzinnego nagrania
# zajmuje FFmpegowi około minuty; wartość jest wielokrotnie wyższa, żeby nie
# ucinać pracy na wolniejszym sprzęcie ani przy bardzo długim nagraniu, ale
# skończona, żeby zawieszony proces nie zatrzymał całego potoku.
LIMIT_CZASU_DEKODOWANIA_SEKUNDY = 1800

KOMUNIKAT_BRAK_FFMPEGA = (
    "Nie znaleziono programu FFmpeg, który rozkodowuje nagrania audio przed "
    "transkrypcją. Zainstaluj FFmpeg i dopisz go do zmiennej PATH. Bez niego "
    "nagrania mowy nie zostaną przepisane, a pozostałe formaty źródeł działają "
    "normalnie."
)

Fala = npt.NDArray[np.float32]


def znajdz_ffmpeg() -> Path:
    """Zwraca ścieżkę pliku wykonywalnego FFmpega albo zgłasza `BrakNarzedzia`."""
    znaleziony = shutil.which(NAZWA_PLIKU_WYKONYWALNEGO)
    if znaleziony is None:
        raise BrakNarzedzia(KOMUNIKAT_BRAK_FFMPEGA)
    return Path(znaleziony)


def czy_dostepny() -> bool:
    """Zwraca prawdę, gdy FFmpeg jest w zmiennej PATH, i nie zgłasza wyjątku."""
    return shutil.which(NAZWA_PLIKU_WYKONYWALNEGO) is not None


def dekoduj_do_fali(
    bajty_audio: bytes,
    *,
    identyfikator_zrodla: str | None = None,
) -> Fala:
    """Rozkodowuje bajty nagrania na jednokanałową falę float32 o częstotliwości 16 kHz.

    Bajty są zapisywane do pliku tymczasowego, FFmpeg czyta ten plik, a surowy
    strumień próbek ``f32le`` wraca standardowym wyjściem i jest zamieniany na
    tablicę NumPy. Niezerowy kod wyjścia oznacza plik uszkodzony albo
    w nieobsługiwanym formacie i kończy się błędem trwałym; przekroczenie limitu
    czasu błędem przejściowym; brak FFmpega błędem `BrakNarzedzia`.
    """
    program = znajdz_ffmpeg()

    uchwyt, sciezka_tymczasowa = tempfile.mkstemp(prefix="gnb-audio-", suffix=".bin")
    plik_tymczasowy = Path(sciezka_tymczasowa)
    try:
        with os.fdopen(uchwyt, "wb") as plik:
            plik.write(bajty_audio)
        polecenie = [
            str(program),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(plik_tymczasowy),
            "-f",
            "f32le",
            "-ac",
            "1",
            "-ar",
            str(CZESTOTLIWOSC_PROBKOWANIA),
            "-acodec",
            "pcm_f32le",
            "pipe:1",
        ]
        try:
            wynik = subprocess.run(
                polecenie,
                capture_output=True,
                timeout=LIMIT_CZASU_DEKODOWANIA_SEKUNDY,
                check=False,
            )
        except FileNotFoundError as blad:
            raise BrakNarzedzia(KOMUNIKAT_BRAK_FFMPEGA, identyfikator_zrodla) from blad
        except subprocess.TimeoutExpired as blad:
            raise BladPrzejsciowy(
                "Rozkodowanie nagrania przez FFmpeg przekroczyło limit czasu "
                f"{LIMIT_CZASU_DEKODOWANIA_SEKUNDY} sekund.",
                identyfikator_zrodla,
            ) from blad
    finally:
        plik_tymczasowy.unlink(missing_ok=True)

    if wynik.returncode != 0:
        powod = wynik.stderr.decode("utf-8", errors="replace").strip() or "brak szczegółów"
        raise BladTrwaly(
            f"FFmpeg nie rozkodował nagrania (kod {wynik.returncode}): {powod}.",
            identyfikator_zrodla,
        )

    fala = np.frombuffer(wynik.stdout, dtype=np.float32)
    if fala.size == 0:
        raise BladTrwaly(
            "Nagranie nie zawiera żadnych próbek dźwięku po rozkodowaniu. Plik może "
            "być uszkodzony albo nie zawierać ścieżki dźwiękowej.",
            identyfikator_zrodla,
        )
    # Kopia, bo tablica z ``np.frombuffer`` jest tylko do odczytu, a filtr VAD
    # i transkrypcja mogą chcieć pracować na tablicy zapisywalnej.
    return np.array(fala, dtype=np.float32)


def dlugosc_fali_sekundy(fala: Fala) -> float:
    """Zwraca długość fali w sekundach, przy stałej częstotliwości próbkowania."""
    return len(fala) / CZESTOTLIWOSC_PROBKOWANIA
