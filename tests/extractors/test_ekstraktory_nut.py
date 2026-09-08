"""Testy czterech adapterów ekstrakcji materiałów nutowych."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly, PominietoZrodlo
from gnb.extractors.bazowy import domyslny_rejestr_binarny
from gnb.extractors.plik_guitarpro import EkstraktorGuitarPro
from gnb.extractors.plik_midi import EkstraktorMidi
from gnb.extractors.plik_musicxml import EkstraktorMusicXml
from gnb.extractors.plik_nuty_skanowane import EkstraktorNutSkanowanych


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


def test_ekstraktor_nut_skanowanych_zawsze_pomija_z_komunikatem_o_audiverisie() -> None:
    for nazwa_pliku in ("nuty_skan.png", "nuty_skan.pdf"):
        bajty = Path("tests/dane", nazwa_pliku).read_bytes()
        with pytest.raises(PominietoZrodlo) as informacja:
            EkstraktorNutSkanowanych().wyekstrahuj("zr-2", bajty)
        assert "Audiveris" in informacja.value.komunikat
        assert informacja.value.identyfikator_zrodla == "zr-2"


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
