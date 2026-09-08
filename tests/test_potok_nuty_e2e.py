"""Testy end-to-end potoku dla materiałów nutowych.

Odczyt formatów natywnych trwa milisekundy, więc żaden z tych testów nie nosi
markera „wolne”. Testy MIDI i Guitar Pro wymagają bibliotek z grupy „nuty”,
które grupa „dev” instaluje.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import przyjmij_plik
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"
_MOMENT = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 8, 12, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _bez_deduplikacji(tmp_path: Path, **reszta: object) -> Konfiguracja:
    return Konfiguracja(
        katalog_wynikow=tmp_path,
        deduplikacja_hash_wlaczona=False,
        deduplikacja_kosmetyczna_wlaczona=False,
        deduplikacja_podobienstwo_wlaczone=False,
        **reszta,  # type: ignore[arg-type]
    )


def test_plik_midi_daje_jeden_txt_z_opisem_partytury(wymaga_mido: None, tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "melodia.mid", _MOMENT)],
        _bez_deduplikacji(tmp_path),
        nazwa_projektu="Nuty MIDI",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    pliki_md = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.md"))
    assert len(pliki_txt) == 1
    assert pliki_md == []

    tresc = pliki_txt[0].read_text(encoding="utf-8")
    assert "Metrum: 4/4" in tresc
    assert "Tempo: 120 uderzeń na minutę" in tresc

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    zrodlo = manifest["zrodla"][0]
    assert zrodlo["typ"] == "plik_nuty"
    assert zrodlo["status"] == "spakowane"
    assert zrodlo["metadane"]["nuty_format"] == "midi"
    assert "przybliżona" in zrodlo["metadane"]["nuty_liczba_taktow"]

    oryginaly = list((wynik.katalog_projektu / "materialy_zrodlowe").glob("*.mid"))
    assert len(oryginaly) == 1


def test_dwa_materialy_nutowe_w_grupie_daja_osobne_pliki_i_zdanie_w_raporcie(
    wymaga_mido: None, tmp_path: Path
) -> None:
    wejscia = [
        przyjmij_plik(KATALOG_DANYCH / "melodia.mid", _MOMENT, grupa="Muzyka"),
        przyjmij_plik(KATALOG_DANYCH / "melodia.musicxml", _MOMENT, grupa="Muzyka"),
    ]
    wynik = przetworz_projekt(
        wejscia,
        _bez_deduplikacji(tmp_path),
        nazwa_projektu="Nuty w grupie",
        zegar=_zegar_krokowy(),
    )

    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 2

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Materiały nutowe (2) nie podlegają grupowaniu" in raport


def test_skan_nut_z_flaga_nuty_jest_pomijany_z_powodem_o_audiverisie(tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "nuty_skan.png", _MOMENT, nuty=True)],
        _bez_deduplikacji(tmp_path),
        nazwa_projektu="Skan nut",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert manifest["zrodla"][0]["status"] == "pominiete"
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Audiveris" in raport


def test_plik_guitar_pro_daje_txt_z_liczba_taktow(wymaga_pyguitarpro: None, tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        [przyjmij_plik(KATALOG_DANYCH / "tabulatura_akordy.gp5", _MOMENT)],
        _bez_deduplikacji(tmp_path),
        nazwa_projektu="Nuty Guitar Pro",
        zegar=_zegar_krokowy(),
    )

    pliki_txt = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 1
    assert "Liczba taktów: 8" in pliki_txt[0].read_text(encoding="utf-8")
