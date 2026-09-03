"""Testy ekstraktora nagrań mowy: pominięcia, obrona przed halucynacjami, metadane.

Testy jednostkowe podmieniają dekodowanie i transkrypcję na atrapy, więc działają
bez FFmpega i bez modelu. Test odrzucenia materiału muzycznego korzysta
z prawdziwego filtra aktywności mowy, więc pomija się bez faster-whisper i bez
FFmpega. Test pełnej transkrypcji wymaga pobranego modelu i nosi marker ``wolne``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from gnb.audio.transkrypcja import SegmentTranskrypcji, UstawieniaTranskrypcji, WynikTranskrypcji
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BrakNarzedzia, PominietoZrodlo
from gnb.extractors import plik_audio
from gnb.extractors.plik_audio import EkstraktorAudio

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def _segment(tekst: str, poczatek: float = 0.0, logprob: float = -0.2) -> SegmentTranskrypcji:
    return SegmentTranskrypcji(poczatek, poczatek + 3.0, tekst, logprob, 0.05)


@pytest.fixture
def audio_zamockowane(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Podmienia dekodowanie i sprawdzanie biblioteki na atrapy dostępne wszędzie."""
    monkeypatch.setattr(plik_audio.dekodowanie, "czy_dostepny", lambda: True)
    monkeypatch.setattr(
        plik_audio.dekodowanie,
        "dekoduj_do_fali",
        lambda _bajty, **_k: np.zeros(160_000, dtype=np.float32),
    )
    monkeypatch.setattr(plik_audio.dekodowanie, "dlugosc_fali_sekundy", lambda _fala: 10.0)
    monkeypatch.setattr(plik_audio, "czy_dostepna_biblioteka", lambda: True)
    yield


def test_obsluguje_wylacznie_audio_jako_zrodlo_typu_audio() -> None:
    ekstraktor = EkstraktorAudio(transkrypcja_wlaczona=True)
    assert ekstraktor.obsluguje(TypZrodla.PLIK_AUDIO, "mp3") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_AUDIO, "wav") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_AUDIO, "pdf") is False
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "mp3") is False


def test_wylaczona_transkrypcja_pomija_zrodlo_bez_dotykania_narzedzi() -> None:
    """Wyłączona transkrypcja daje kontrolowane pominięcie, sprawdzane przed czymkolwiek."""
    with pytest.raises(PominietoZrodlo, match="wyłączona"):
        EkstraktorAudio(transkrypcja_wlaczona=False).wyekstrahuj("audio-1", b"cokolwiek")


def test_brak_ffmpega_daje_brak_narzedzia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(plik_audio.dekodowanie, "czy_dostepny", lambda: False)

    with pytest.raises(BrakNarzedzia, match="FFmpeg"):
        EkstraktorAudio(transkrypcja_wlaczona=True).wyekstrahuj("audio-2", b"cokolwiek")


def test_brak_biblioteki_daje_brak_narzedzia(
    audio_zamockowane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plik_audio, "czy_dostepna_biblioteka", lambda: False)

    with pytest.raises(BrakNarzedzia, match="faster-whisper"):
        EkstraktorAudio(transkrypcja_wlaczona=True).wyekstrahuj("audio-3", b"cokolwiek")


def test_material_niemowny_jest_pomijany_bez_transkrypcji(
    audio_zamockowane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plik_audio, "dlugosc_mowy_sekundy", lambda _fala, _prog: 0.5)
    wolane: list[str] = []
    monkeypatch.setattr(
        plik_audio, "transkrybuj", lambda *a, **k: wolane.append("transkrybuj") or None
    )

    with pytest.raises(PominietoZrodlo, match="niemowny"):
        EkstraktorAudio(transkrypcja_wlaczona=True, prog_udzialu_mowy=0.5).wyekstrahuj(
            "audio-4", b"cokolwiek"
        )
    assert wolane == []


def test_wymuszenie_transkrypcji_przelamuje_odrzucenie_niemownego(
    audio_zamockowane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plik_audio, "dlugosc_mowy_sekundy", lambda _fala, _prog: 0.5)
    monkeypatch.setattr(
        plik_audio,
        "transkrybuj",
        lambda *_a, **_k: WynikTranskrypcji(
            segmenty=(_segment("Mimo szumu w tle to jest wypowiedź."),),
            jezyk="pl",
            dlugosc_nagrania_sekundy=10.0,
        ),
    )

    dokument = EkstraktorAudio(
        transkrypcja_wlaczona=True, prog_udzialu_mowy=0.5, wymus_transkrypcje=True
    ).wyekstrahuj("audio-5", b"cokolwiek")

    assert "wypowiedź" in dokument.tekst
    assert dokument.metadane["transkrypcja_wymuszona"] == "tak"


def test_niepewna_transkrypcja_trafia_do_ostrzezen(
    audio_zamockowane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plik_audio, "dlugosc_mowy_sekundy", lambda _fala, _prog: 9.0)
    monkeypatch.setattr(
        plik_audio,
        "transkrybuj",
        lambda *_a, **_k: WynikTranskrypcji(
            segmenty=tuple(_segment("Dziękuję za uwagę.", poczatek=float(i)) for i in range(4)),
            jezyk="pl",
            dlugosc_nagrania_sekundy=12.0,
        ),
    )

    dokument = EkstraktorAudio(transkrypcja_wlaczona=True).wyekstrahuj("audio-6", b"cokolwiek")

    assert dokument.ostrzezenia
    assert any("powtarza się" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)


def test_pusta_transkrypcja_po_odfiltrowaniu_ciszy_jest_pomijana(
    audio_zamockowane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plik_audio, "dlugosc_mowy_sekundy", lambda _fala, _prog: 9.0)
    monkeypatch.setattr(
        plik_audio,
        "transkrybuj",
        lambda *_a, **_k: WynikTranskrypcji(segmenty=(), jezyk="pl", dlugosc_nagrania_sekundy=10.0),
    )

    with pytest.raises(PominietoZrodlo, match="nic do"):
        EkstraktorAudio(transkrypcja_wlaczona=True).wyekstrahuj("audio-7", b"cokolwiek")


def test_wynik_ma_metadane_dlugosci_jezyka_i_modelu(
    audio_zamockowane: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(plik_audio, "dlugosc_mowy_sekundy", lambda _fala, _prog: 9.5)
    monkeypatch.setattr(
        plik_audio,
        "transkrybuj",
        lambda *_a, **_k: WynikTranskrypcji(
            segmenty=(_segment("Zdanie pierwsze."), _segment("Zdanie drugie.", 3.0)),
            jezyk="pl",
            dlugosc_nagrania_sekundy=10.0,
        ),
    )

    dokument = EkstraktorAudio(
        UstawieniaTranskrypcji(model="tiny"), transkrypcja_wlaczona=True
    ).wyekstrahuj("audio-8", b"cokolwiek")

    assert dokument.metadane["dlugosc_sekundy"] == "10"
    assert dokument.metadane["jezyk"] == "pl"
    assert dokument.metadane["model_transkrypcji"] == "tiny"
    assert dokument.metoda_ekstrakcji == "transkrypcja_audio"
    assert dokument.poziom_pewnosci_struktury.value == "niski"


def test_nagranie_muzyczne_jest_odrzucane_prawdziwym_filtrem_mowy(
    wymaga_faster_whisper: None, wymaga_ffmpeg: None
) -> None:
    """Materiał muzyczny bez mowy jest pomijany, nigdy transkrybowany.

    Test czerwieni się, gdyby filtr aktywności mowy przestał odrzucać akordy,
    przez co nagranie muzyczne przeszłoby do transkrypcji.
    """
    bajty = (KATALOG_DANYCH / "audio_muzyka.wav").read_bytes()

    with pytest.raises(PominietoZrodlo, match="niemowny"):
        EkstraktorAudio(transkrypcja_wlaczona=True).wyekstrahuj("audio-9", bajty)


@pytest.mark.wolne
def test_nagranie_mowy_jest_przepisywane_od_poczatku_do_konca(
    wymaga_model_whisper: None, wymaga_ffmpeg: None
) -> None:
    bajty = (KATALOG_DANYCH / "audio_mowa.wav").read_bytes()

    dokument = EkstraktorAudio(
        UstawieniaTranskrypcji(model="tiny"), transkrypcja_wlaczona=True
    ).wyekstrahuj("audio-10", bajty)

    assert dokument.tekst.strip()
    assert dokument.metadane["jezyk"]
    assert dokument.metadane["dlugosc_sekundy"].isdigit()
