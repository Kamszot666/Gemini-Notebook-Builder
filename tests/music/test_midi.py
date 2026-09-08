"""Testy odczytu plików MIDI do opisu partytury."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from gnb.core.stale import PoziomPewnosciStruktury
from gnb.core.wyjatki import BladTrwaly
from gnb.music.midi import czy_dostepna_biblioteka, przeczytaj_midi

pytestmark = pytest.mark.usefixtures("wymaga_mido")

_MELODIA = Path("tests/dane/melodia.mid")


def _midi_z_komunikatami(*komunikaty: object, ticks_per_beat: int = 480) -> bytes:
    """Buduje w pamięci jednościeżkowy plik MIDI z podanych komunikatów meta."""
    import mido

    plik = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    sciezka = mido.MidiTrack()
    for komunikat in komunikaty:
        sciezka.append(komunikat)
    sciezka.append(mido.Message("note_on", note=60, velocity=64, time=0))
    sciezka.append(mido.Message("note_off", note=60, velocity=0, time=ticks_per_beat * 4))
    plik.tracks.append(sciezka)
    bufor = io.BytesIO()
    plik.save(file=bufor)
    return bufor.getvalue()


def test_fikstura_melodii_daje_metrum_tempo_i_tytul() -> None:
    opis = przeczytaj_midi(_MELODIA.read_bytes())
    assert opis.metrum == "4/4"
    assert opis.tempo_bpm == 120
    assert opis.tytul == "Melodia testowa"
    assert opis.format_zrodlowy == "midi"


def test_liczba_taktow_z_midi_jest_zawsze_przyblizona() -> None:
    # Format MIDI nie zapisuje podziału na takty. Gdyby ten znacznik był fałszem,
    # manifest podawałby liczbę taktów jako pewną, choć pochodzi z przeliczenia czasu.
    opis = przeczytaj_midi(_MELODIA.read_bytes())
    assert opis.liczba_taktow_przyblizona is True
    assert opis.liczba_taktow == 2


def test_dwa_rozne_metra_daja_ostrzezenie_i_wartosc_poczatkowa() -> None:
    import mido

    bajty = _midi_z_komunikatami(
        mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0),
        mido.MetaMessage("time_signature", numerator=3, denominator=4, time=480),
    )
    opis = przeczytaj_midi(bajty)
    assert opis.metrum == "4/4"
    assert any("zmienia metrum" in ostrzezenie for ostrzezenie in opis.ostrzezenia_zmian)


def test_dwa_rozne_tempa_daja_ostrzezenie_i_wartosc_poczatkowa() -> None:
    import mido

    bajty = _midi_z_komunikatami(
        mido.MetaMessage("set_tempo", tempo=500000, time=0),
        mido.MetaMessage("set_tempo", tempo=400000, time=480),
    )
    opis = przeczytaj_midi(bajty)
    assert opis.tempo_bpm == 120
    assert any("zmienia tempo" in ostrzezenie for ostrzezenie in opis.ostrzezenia_zmian)


def test_odczyt_tonacji_z_komunikatu_key_signature() -> None:
    import mido

    bajty = _midi_z_komunikatami(mido.MetaMessage("key_signature", key="Am", time=0))
    opis = przeczytaj_midi(bajty)
    assert opis.tonacja == "a-moll"


def test_instrumenty_z_program_change_i_kanalu_perkusyjnego() -> None:
    import mido

    bajty = _midi_z_komunikatami(
        mido.Message("program_change", program=24, channel=0, time=0),
        mido.Message("program_change", program=0, channel=9, time=0),
        mido.Message("note_on", note=38, velocity=64, channel=9, time=0),
        mido.Message("note_off", note=38, velocity=0, channel=9, time=10),
    )
    opis = przeczytaj_midi(bajty)
    assert any("nylon" in nazwa for nazwa in opis.instrumenty)
    assert "zestaw perkusyjny" in opis.instrumenty


def test_midi_typu_pierwszego_z_wieloma_sciezkami() -> None:
    import mido

    plik = mido.MidiFile(type=1, ticks_per_beat=480)
    sciezka_nazwy = mido.MidiTrack()
    sciezka_nazwy.append(mido.MetaMessage("track_name", name="Utwór", time=0))
    sciezka_nazwy.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    sciezka_nazwy.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    plik.tracks.append(sciezka_nazwy)
    sciezka_nut = mido.MidiTrack()
    sciezka_nut.append(mido.MetaMessage("track_name", name="Skrzypce", time=0))
    sciezka_nut.append(mido.Message("note_on", note=67, velocity=64, time=0))
    sciezka_nut.append(mido.Message("note_off", note=67, velocity=0, time=1920))
    plik.tracks.append(sciezka_nut)
    bufor = io.BytesIO()
    plik.save(file=bufor)

    opis = przeczytaj_midi(bufor.getvalue())
    assert opis.tytul == "Utwór"
    assert opis.metrum == "4/4"
    assert any("Skrzypce" in czesc for czesc in opis.struktura_czesci)


def test_uszkodzony_plik_konczy_sie_bledem_trwalym() -> None:
    with pytest.raises(BladTrwaly):
        przeczytaj_midi(b"MThd" + b"\x00" * 8)


def test_czy_dostepna_biblioteka_wykrywa_brak_importu(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    prawdziwy_import = builtins.__import__

    def blokuj_mido(nazwa: str, *reszta: object, **nazwane: object) -> object:
        if nazwa == "mido" or nazwa.startswith("mido."):
            raise ImportError("test: mido zablokowane")
        return prawdziwy_import(nazwa, *reszta, **nazwane)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", blokuj_mido)
    assert czy_dostepna_biblioteka() is False


def test_niski_poziom_pewnosci_bez_metrum_i_tempa() -> None:
    import mido

    plik = mido.MidiFile(ticks_per_beat=480)
    sciezka = mido.MidiTrack()
    sciezka.append(mido.Message("note_on", note=60, velocity=64, time=0))
    sciezka.append(mido.Message("note_off", note=60, velocity=0, time=480))
    plik.tracks.append(sciezka)
    bufor = io.BytesIO()
    plik.save(file=bufor)

    opis = przeczytaj_midi(bufor.getvalue())
    assert opis.poziom_pewnosci is PoziomPewnosciStruktury.NISKI
