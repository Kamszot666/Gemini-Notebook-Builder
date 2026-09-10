"""Testy czterech adapterów ekstrakcji materiałów nutowych."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly, BrakNarzedzia
from gnb.extractors.bazowy import domyslny_rejestr_binarny
from gnb.extractors.plik_guitarpro import EkstraktorGuitarPro
from gnb.extractors.plik_midi import EkstraktorMidi
from gnb.extractors.plik_musicxml import EkstraktorMusicXml
from gnb.extractors.plik_nuty_skanowane import (
    EkstraktorNutSkanowanych,
    _numery_pustych_taktow,
    _sygnaly_kontrolne,
    _uruchom_audiveris,
)
from gnb.music.model import OpisPartytury


def test_obsluguje_bramkuje_sie_na_typie_i_formacie() -> None:
    assert EkstraktorMidi().obsluguje(TypZrodla.PLIK_NUTY, "mid")
    assert EkstraktorMidi().obsluguje(TypZrodla.PLIK_NUTY, "midi")
    assert not EkstraktorMidi().obsluguje(TypZrodla.PLIK_NUTY, "musicxml")
    assert not EkstraktorMidi().obsluguje(TypZrodla.PLIK_DOKUMENT, "mid")

    assert EkstraktorMusicXml().obsluguje(TypZrodla.PLIK_NUTY, "mxl")
    assert EkstraktorGuitarPro().obsluguje(TypZrodla.PLIK_NUTY, "gp5")
    assert not EkstraktorGuitarPro().obsluguje(TypZrodla.PLIK_NUTY, "gp")

    assert EkstraktorNutSkanowanych().obsluguje(TypZrodla.PLIK_NUTY, "pdf")
    assert EkstraktorNutSkanowanych().obsluguje(TypZrodla.PLIK_NUTY, "png")
    assert not EkstraktorNutSkanowanych().obsluguje(TypZrodla.PLIK_NUTY, "mid")


def test_ekstraktor_midi_buduje_dokument_z_opisem(wymaga_mido: None) -> None:
    dokument = EkstraktorMidi().wyekstrahuj("zr-1", Path("tests/dane/melodia.mid").read_bytes())
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert "Metrum" in dokument.tekst
    assert "Tempo" in dokument.tekst
    assert dokument.tytul == "Melodia testowa"
    assert dokument.metadane["nuty_format"] == "midi"
    assert all(isinstance(wartosc, str) for wartosc in dokument.metadane.values())


def test_ekstraktor_nut_skanowanych_zglasza_uszkodzony_plik_bez_audiverisa() -> None:
    # Sprawdzenie treści pliku wypada przed odnalezieniem programu Audiveris,
    # więc ten test nie potrzebuje fikstury `wymaga_audiveris` i jest szybki.
    with pytest.raises(BladTrwaly) as informacja:
        EkstraktorNutSkanowanych().wyekstrahuj("zr-2", b"to nie jest ani PDF, ani obraz")
    assert informacja.value.identyfikator_zrodla == "zr-2"


def test_ekstraktor_nut_skanowanych_zglasza_brak_narzedzia_dla_zlej_sciezki() -> None:
    zly_ekstraktor = EkstraktorNutSkanowanych("C:/nie/ma/takiego/audiveris.exe")
    with pytest.raises(BrakNarzedzia):
        zly_ekstraktor.wyekstrahuj("zr-3", Path("tests/dane/nuty_skan.png").read_bytes())


@pytest.mark.wolne
def test_ekstraktor_nut_skanowanych_rozpoznaje_obraz(wymaga_audiveris: None) -> None:
    zdarzenia: list[tuple[int, int]] = []
    dokument = EkstraktorNutSkanowanych().wyekstrahuj(
        "zr-4",
        Path("tests/dane/nuty_skan.png").read_bytes(),
        postep=lambda wykonano, wszystkich: zdarzenia.append((wykonano, wszystkich)),
    )
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert "rozpoznanie optyczne" in dokument.metadane["nuty_format"]
    assert "Audiveris" in dokument.metadane["nuty_metoda_odczytu"]
    # Materiał rozpoznany optycznie trafia bezwarunkowo do „Materiałów do
    # sprawdzenia”, niezależnie od tego, czy któryś sygnał kontrolny coś wykrył.
    assert dokument.ostrzezenia
    assert any("optycznie" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)
    assert dokument.plik_posredni is not None
    sufiks, mxl_bajty = dokument.plik_posredni
    assert sufiks == "audiveris.mxl"
    assert mxl_bajty.startswith(b"PK")  # kontener MXL to archiwum ZIP
    assert zdarzenia == [(1, 1)]


@pytest.mark.wolne
def test_ekstraktor_nut_skanowanych_rozpoznaje_pdf_i_liczy_strony(
    wymaga_audiveris: None,
) -> None:
    dokument = EkstraktorNutSkanowanych().wyekstrahuj(
        "zr-5", Path("tests/dane/nuty_skan.pdf").read_bytes()
    )
    assert "PDF" in dokument.metadane["nuty_format"]


@pytest.mark.wolne
def test_ekstraktor_nut_skanowanych_laczy_wielostronicowy_pdf_w_jeden_opis(
    wymaga_audiveris: None,
) -> None:
    """Audiveris przetwarza wielostronicowy plik jednym wywołaniem i sam łączy
    strony w jedną ciągłą partyturę — zweryfikowane ręcznie na tym samym pliku
    przy projektowaniu części B. Ten test chroni to założenie przed regresją:
    dwie strony po dwa takty każda mają dać jeden opis z czterema taktami, a nie
    dwa osobne opisy albo opis tylko pierwszej strony.
    """
    zdarzenia: list[tuple[int, int]] = []
    dokument = EkstraktorNutSkanowanych().wyekstrahuj(
        "zr-8",
        Path("tests/dane/nuty_skan_2str.pdf").read_bytes(),
        postep=lambda wykonano, wszystkich: zdarzenia.append((wykonano, wszystkich)),
    )
    assert dokument.metadane["nuty_liczba_taktow"] == "4"
    assert "2 stron" in dokument.metadane["nuty_format"]
    assert zdarzenia == [(1, 2), (2, 2)]


def test_sygnaly_kontrolne_zglasza_brak_tonacji_metrum_i_taktow() -> None:
    opis = OpisPartytury(format_zrodlowy="obraz", metoda_odczytu="Audiveris")
    sygnaly = _sygnaly_kontrolne(opis, b"")
    assert any("tonacj" in sygnal for sygnal in sygnaly)
    assert any("metr" in sygnal for sygnal in sygnaly)
    assert any("takt" in sygnal for sygnal in sygnaly)


def test_numery_pustych_taktow_wykrywa_takt_bez_tresci() -> None:
    musicxml = b"""<?xml version="1.0"?>
    <score-partwise>
      <part id="P1">
        <measure number="1"><note><pitch><step>C</step><octave>4</octave></pitch>
        <duration>4</duration></note></measure>
        <measure number="2"></measure>
      </part>
    </score-partwise>"""
    assert _numery_pustych_taktow(musicxml) == ["2"]


def test_uruchom_audiveris_zglasza_blad_przejsciowy_po_przekroczeniu_limitu(
    tmp_path: Path,
) -> None:
    polecenie = [sys.executable, "-c", "import time; time.sleep(5)"]
    with pytest.raises(BladPrzejsciowy):
        _uruchom_audiveris(polecenie, tmp_path / "dziennik.txt", 0.2, 1, None, "zr-6")


def test_uruchom_audiveris_zglasza_postep_strona_po_stronie(tmp_path: Path) -> None:
    skrypt = (
        "import sys, time\n"
        "print('krok | PAGE'); sys.stdout.flush()\n"
        "time.sleep(1.0)\n"
        "print('krok | PAGE'); sys.stdout.flush()\n"
    )
    polecenie = [sys.executable, "-c", skrypt]
    zdarzenia: list[tuple[int, int]] = []
    kod = _uruchom_audiveris(
        polecenie,
        tmp_path / "dziennik.txt",
        30.0,
        2,
        lambda wykonano, wszystkich: zdarzenia.append((wykonano, wszystkich)),
        "zr-7",
    )
    assert kod == 0
    assert zdarzenia == [(1, 2), (2, 2)]


def test_ekstraktor_midi_dokłada_identyfikator_do_bledu(wymaga_mido: None) -> None:
    with pytest.raises(BladTrwaly) as informacja:
        EkstraktorMidi().wyekstrahuj("zr-3", b"MThd" + b"\x00" * 8)
    assert informacja.value.identyfikator_zrodla == "zr-3"


def test_rejestr_binarny_dobiera_wlasciwy_adapter_nutowy() -> None:
    rejestr = domyslny_rejestr_binarny()
    assert isinstance(rejestr.dobierz(TypZrodla.PLIK_NUTY, "gp4"), EkstraktorGuitarPro)
    assert isinstance(rejestr.dobierz(TypZrodla.PLIK_NUTY, "mid"), EkstraktorMidi)
    assert isinstance(rejestr.dobierz(TypZrodla.PLIK_NUTY, "mxl"), EkstraktorMusicXml)
    assert isinstance(rejestr.dobierz(TypZrodla.PLIK_NUTY, "pdf"), EkstraktorNutSkanowanych)
