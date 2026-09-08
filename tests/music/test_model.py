"""Testy modelu opisu materiału nutowego i jego zamiany na dokument wyekstrahowany."""

from __future__ import annotations

from gnb.core.stale import PoziomPewnosciStruktury
from gnb.music.model import (
    OpisPartytury,
    opis_jako_metadane,
    opis_jako_tekst,
    zbuduj_dokument_wyekstrahowany,
)


def _opis_pelny() -> OpisPartytury:
    return OpisPartytury(
        format_zrodlowy="musicxml",
        metoda_odczytu="xml.etree",
        tytul="Melodia testowa",
        tonacja="C-dur",
        metrum="4/4",
        tempo_bpm=120,
        liczba_taktow=8,
        liczba_taktow_przyblizona=False,
        instrumenty=["fortepian"],
        struktura_czesci=["Partia 1: Fortepian"],
        poziom_pewnosci=PoziomPewnosciStruktury.WYSOKI,
    )


def test_opis_jako_tekst_zawiera_wszystkie_znane_pola_i_koncowy_akapit() -> None:
    tekst = opis_jako_tekst(_opis_pelny())
    assert "Materiał nutowy: Melodia testowa" in tekst
    assert "Tonacja: C-dur" in tekst
    assert "Metrum: 4/4" in tekst
    assert "Tempo: 120 uderzeń na minutę" in tekst
    assert "Liczba taktów: 8" in tekst
    assert "Instrumenty: fortepian" in tekst
    assert "Struktura części:" in tekst
    assert "nie jest podglądem partytury" in tekst.lower()


def test_opis_jako_tekst_pomija_wiersze_pol_nieznanych() -> None:
    tekst = opis_jako_tekst(OpisPartytury(format_zrodlowy="midi", metoda_odczytu="mido"))
    assert "Materiał nutowy bez tytułu" in tekst
    assert "Tempo" not in tekst
    assert "Tonacja" not in tekst
    assert "Liczba taktów" not in tekst
    assert "nie odczytano" not in tekst
    assert "Struktura części" not in tekst
    assert "Ostrzeżenia odczytu" not in tekst


def test_opis_jako_tekst_oznacza_przybliżoną_liczbe_taktow() -> None:
    opis = OpisPartytury(
        format_zrodlowy="midi",
        metoda_odczytu="mido",
        liczba_taktow=8,
        liczba_taktow_przyblizona=True,
    )
    tekst = opis_jako_tekst(opis)
    assert "Liczba taktów: 8 (wartość przybliżona" in tekst


def test_opis_jako_metadane_pomija_klucze_pol_nieznanych() -> None:
    metadane = opis_jako_metadane(OpisPartytury(format_zrodlowy="midi", metoda_odczytu="mido"))
    assert metadane["nuty_format"] == "midi"
    assert metadane["nuty_metoda_odczytu"] == "mido"
    assert "nuty_tonacja" not in metadane
    assert "nuty_tempo_bpm" not in metadane
    assert "nuty_liczba_taktow" not in metadane


def test_opis_jako_metadane_zapisuje_przyblizona_liczbe_taktow_jako_napis() -> None:
    metadane = opis_jako_metadane(
        OpisPartytury(
            format_zrodlowy="midi",
            metoda_odczytu="mido",
            liczba_taktow=8,
            liczba_taktow_przyblizona=True,
        )
    )
    assert metadane["nuty_liczba_taktow"].startswith("8 (")
    assert "przybliżona" in metadane["nuty_liczba_taktow"]


def test_opis_jako_metadane_wszystkie_wartosci_sa_napisami() -> None:
    metadane = opis_jako_metadane(_opis_pelny())
    assert all(isinstance(wartosc, str) for wartosc in metadane.values())


def test_opis_jako_metadane_zapisuje_zmiany_tylko_gdy_sa() -> None:
    bez_zmian = opis_jako_metadane(_opis_pelny())
    assert "nuty_zmiany" not in bez_zmian

    opis = _opis_pelny()
    opis.ostrzezenia_zmian = ["Utwór zmienia metrum; opis podaje metrum początkowe (4/4)."]
    ze_zmianami = opis_jako_metadane(opis)
    assert "metrum" in ze_zmianami["nuty_zmiany"]


def test_zbuduj_dokument_wymusza_niski_poziom_pewnosci_struktury() -> None:
    opis = _opis_pelny()
    opis.ostrzezenia_zmian = ["Utwór zmienia tempo; opis podaje tempo początkowe."]
    dokument = zbuduj_dokument_wyekstrahowany("zr-1", opis, metoda_ekstrakcji="nuty-musicxml")
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.tytul == "Melodia testowa"
    assert dokument.metoda_ekstrakcji == "nuty-musicxml"
    assert dokument.ostrzezenia == ["Utwór zmienia tempo; opis podaje tempo początkowe."]
    assert "Materiał nutowy: Melodia testowa" in dokument.tekst
