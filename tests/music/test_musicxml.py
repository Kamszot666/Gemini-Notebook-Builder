"""Testy odczytu plików MusicXML i kontenera MXL do opisu partytury."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.music.model import opis_jako_tekst
from gnb.music.musicxml import przeczytaj_musicxml

_MELODIA = Path("tests/dane/melodia.musicxml")


def test_fikstura_melodii_daje_dokladna_liczbe_taktow_i_tonacje() -> None:
    opis = przeczytaj_musicxml(_MELODIA.read_bytes())
    assert opis.tonacja == "C-dur"
    assert opis.metrum == "4/4"
    assert opis.instrumenty == ["Fortepian"]
    assert opis.liczba_taktow == 2
    assert opis.liczba_taktow_przyblizona is False
    assert opis.tytul == "Melodia testowa"
    assert opis.format_zrodlowy == "musicxml"


def test_opis_tekstowy_fikstury_nie_zawiera_wiersza_o_tempie() -> None:
    # Ta fikstura celowo nie ma elementu sound tempo ani metronome. Opis ma
    # pominąć wiersz o tempie, a nie podstawić domyślną wartość.
    tekst = opis_jako_tekst(przeczytaj_musicxml(_MELODIA.read_bytes()))
    assert "Tempo" not in tekst


def test_brak_elementu_mode_daje_uwage_o_przyjeciu_trybu_durowego() -> None:
    opis = przeczytaj_musicxml(_MELODIA.read_bytes())
    assert any("tryb durowy" in uwaga for uwaga in opis.uwagi_odczytu)


def test_kontener_mxl_czyta_sie_jak_goly_plik() -> None:
    wewnetrzny = _MELODIA.read_bytes()
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        archiwum.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container><rootfiles>'
            '<rootfile full-path="partytura.musicxml"/></rootfiles></container>',
        )
        archiwum.writestr("partytura.musicxml", wewnetrzny)

    opis = przeczytaj_musicxml(bufor.getvalue())
    assert opis.format_zrodlowy == "mxl"
    assert opis.liczba_taktow == 2
    assert opis.tonacja == "C-dur"


def test_mxl_bez_dokumentu_partytury_konczy_sie_bledem() -> None:
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        archiwum.writestr("META-INF/container.xml", "<container/>")
        archiwum.writestr("czytajto.txt", "brak partytury")
    with pytest.raises(BladTrwaly):
        przeczytaj_musicxml(bufor.getvalue())


def test_zmiana_tonacji_w_kolejnym_takcie_daje_ostrzezenie() -> None:
    xml = (
        '<?xml version="1.0"?><score-partwise version="4.0"><part-list>'
        '<score-part id="P1"><part-name>Flet</part-name></score-part></part-list>'
        '<part id="P1">'
        '<measure number="1"><attributes>'
        "<key><fifths>0</fifths><mode>major</mode></key>"
        "<time><beats>4</beats><beat-type>4</beat-type></time>"
        "</attributes></measure>"
        '<measure number="2"><attributes>'
        "<key><fifths>2</fifths><mode>major</mode></key>"
        "</attributes></measure>"
        "</part></score-partwise>"
    )
    opis = przeczytaj_musicxml(xml.encode("utf-8"))
    assert opis.tonacja == "C-dur"
    assert any("zmienia się tonacja" in ostrzezenie for ostrzezenie in opis.ostrzezenia_zmian)


def test_tempo_z_elementu_sound() -> None:
    xml = (
        '<?xml version="1.0"?><score-partwise version="4.0"><part-list>'
        '<score-part id="P1"><part-name>Flet</part-name></score-part></part-list>'
        '<part id="P1"><measure number="1">'
        '<sound tempo="90"/>'
        "<attributes><time><beats>3</beats><beat-type>4</beat-type></time></attributes>"
        "</measure></part></score-partwise>"
    )
    opis = przeczytaj_musicxml(xml.encode("utf-8"))
    assert opis.tempo_bpm == 90


def test_uciety_xml_konczy_sie_bledem_trwalym() -> None:
    with pytest.raises(BladTrwaly):
        przeczytaj_musicxml(b"<?xml version='1.0'?><score-partwise><part>")


def test_score_timewise_liczy_takty_poprawnie() -> None:
    xml = (
        '<?xml version="1.0"?><score-timewise version="4.0"><part-list>'
        '<score-part id="P1"><part-name>Obój</part-name></score-part></part-list>'
        '<measure number="1"><part id="P1"><attributes>'
        "<key><fifths>1</fifths><mode>minor</mode></key>"
        "<time><beats>2</beats><beat-type>4</beat-type></time>"
        "</attributes></part></measure>"
        '<measure number="2"><part id="P1"/></measure>'
        '<measure number="3"><part id="P1"/></measure>'
        "</score-timewise>"
    )
    opis = przeczytaj_musicxml(xml.encode("utf-8"))
    assert opis.liczba_taktow == 3
    assert opis.tonacja == "e-moll"
