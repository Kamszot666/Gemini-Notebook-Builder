"""Testy ekstraktora plików napisów SRT i VTT."""

from __future__ import annotations

from pathlib import Path

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.extractors.napisy import EkstraktorNapisow
from gnb.normalization.kodowanie import zdekoduj

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"

_SRT = """1
00:00:01,000 --> 00:00:04,000
Witajcie na dzisiejszym wykładzie.

2
00:00:04,500 --> 00:00:08,000
Zaczniemy od podstaw.
"""

_VTT = """WEBVTT

00:00:01.000 --> 00:00:04.000
Witajcie na dzisiejszym wykładzie.

NOTE To jest komentarz, nie napis.

00:00:04.500 --> 00:00:08.000 align:middle line:90%
Zaczniemy od <b>podstaw</b>.
"""

_VTT_Z_GODZINA = """WEBVTT

01:00:00.000 --> 01:00:03.000
Segment po godzinie nagrania.
"""


def test_plik_srt_daje_polaczony_tekst() -> None:
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-1", _SRT)

    assert "Witajcie na dzisiejszym wykładzie." in dokument.tekst
    assert "Zaczniemy od podstaw." in dokument.tekst
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.bloki == []


def test_plik_vtt_pomija_naglowek_i_komentarz_note() -> None:
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-2", _VTT)

    assert "WEBVTT" not in dokument.tekst
    assert "komentarz" not in dokument.tekst
    assert "Witajcie na dzisiejszym wykładzie." in dokument.tekst


def test_znaczniki_wewnatrzwierszowe_vtt_sa_usuwane() -> None:
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-3", _VTT)

    assert "<b>" not in dokument.tekst
    assert "podstaw" in dokument.tekst


def test_znacznik_czasu_z_godzina_jest_poprawnie_odczytany() -> None:
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-4", _VTT_Z_GODZINA)

    assert "Segment po godzinie nagrania." in dokument.tekst


def test_plik_bez_tresci_daje_ostrzezenie() -> None:
    tekst = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n\n"
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-5", tekst)

    assert dokument.tekst == ""
    assert dokument.ostrzezenia


def test_obsluguje_srt_i_vtt_ale_nie_inne_formaty() -> None:
    ekstraktor = EkstraktorNapisow()
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "srt") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "vtt") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "csv") is False


def test_plik_testowy_srt_daje_polaczony_tekst_bez_znacznikow_czasu() -> None:
    dane = (KATALOG_DANYCH / "napisy.srt").read_bytes()
    tekst, _ = zdekoduj(dane)
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-6", tekst)

    assert "-->" not in dokument.tekst
    assert "Dzisiaj porozmawiamy o przygotowaniu bazy wiedzy" in dokument.tekst
    assert "utrata informacji o pochodzeniu" in dokument.tekst


def test_plik_testowy_vtt_daje_polaczony_tekst_bez_naglowka() -> None:
    dane = (KATALOG_DANYCH / "napisy.vtt").read_bytes()
    tekst, _ = zdekoduj(dane)
    dokument = EkstraktorNapisow().wyekstrahuj("plik_dokument-7", tekst)

    assert "WEBVTT" not in dokument.tekst
    assert "Dzisiaj porozmawiamy o przygotowaniu bazy wiedzy" in dokument.tekst
