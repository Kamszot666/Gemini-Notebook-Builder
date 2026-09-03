"""Testy heurystyki wykrywania mowy i odrzucania materiału niemownego.

Sama decyzja o progu jest czystą funkcją i testuje się bez żadnych zależności.
Pomiar udziału mowy używa filtra Silero wbudowanego w faster-whisper, więc te
testy pomijają się bez tej biblioteki oraz bez FFmpega.
"""

from __future__ import annotations

from pathlib import Path

from gnb.audio.dekodowanie import dekoduj_do_fali
from gnb.audio.wykrywanie_mowy import (
    OCENA_MOWA,
    OCENA_NIEMOWNE,
    dlugosc_mowy_sekundy,
    ocen_mowe,
)

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_udzial_powyzej_progu_to_mowa() -> None:
    ocena = ocen_mowe(dlugosc_mowy=8.0, dlugosc_nagrania=10.0, prog_udzialu=0.5)

    assert ocena.ocena == OCENA_MOWA
    assert ocena.czy_mowa is True
    assert ocena.udzial_procent == 80


def test_udzial_ponizej_progu_to_material_niemowny() -> None:
    ocena = ocen_mowe(dlugosc_mowy=1.0, dlugosc_nagrania=10.0, prog_udzialu=0.5)

    assert ocena.ocena == OCENA_NIEMOWNE
    assert ocena.czy_mowa is False
    assert ocena.udzial_procent == 10
    assert ocena.prog_procent == 50


def test_prog_zero_nigdy_nie_odrzuca_nawet_ciszy() -> None:
    """Próg równy zeru to globalny odpowiednik wymuszenia transkrypcji."""
    ocena = ocen_mowe(dlugosc_mowy=0.0, dlugosc_nagrania=10.0, prog_udzialu=0.0)

    assert ocena.czy_mowa is True


def test_nagranie_bez_dzwieku_jest_niemowne() -> None:
    ocena = ocen_mowe(dlugosc_mowy=0.0, dlugosc_nagrania=0.0, prog_udzialu=0.5)

    assert ocena.ocena == OCENA_NIEMOWNE


def test_udzial_mowy_nie_przekracza_stu_procent() -> None:
    """Padding filtra VAD może dać sumę odcinków dłuższą niż nagranie — ucinamy do 100%."""
    ocena = ocen_mowe(dlugosc_mowy=12.0, dlugosc_nagrania=10.0, prog_udzialu=0.5)

    assert ocena.udzial_mowy == 1.0


def test_dlugosc_mowy_dla_nagrania_mowy_jest_bliska_pelnej(
    wymaga_faster_whisper: None, wymaga_ffmpeg: None
) -> None:
    fala = dekoduj_do_fali((KATALOG_DANYCH / "audio_mowa.wav").read_bytes())

    dlugosc_mowy = dlugosc_mowy_sekundy(fala, prog_vad=0.5)

    assert dlugosc_mowy > len(fala) / 16000 * 0.5


def test_dlugosc_mowy_dla_nagrania_muzycznego_jest_bliska_zeru(
    wymaga_faster_whisper: None, wymaga_ffmpeg: None
) -> None:
    """Nagranie muzyczne bez mowy: filtr aktywności mowy prawie nic nie znajduje.

    Test czerwieni się, gdyby filtr zaczął klasyfikować akordy jako mowę, przez co
    materiał muzyczny przeszedłby do transkrypcji zamiast zostać pominięty.
    """
    fala = dekoduj_do_fali((KATALOG_DANYCH / "audio_muzyka.wav").read_bytes())

    dlugosc_mowy = dlugosc_mowy_sekundy(fala, prog_vad=0.5)

    assert dlugosc_mowy < len(fala) / 16000 * 0.2
