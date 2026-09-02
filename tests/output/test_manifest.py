"""Testy budowy i zapisu manifestu projektu."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from gnb.output.manifest import (
    WERSJA_SCHEMATU,
    Manifest,
    WpisDeduplikacji,
    WpisWyniku,
    WpisZrodla,
    zapisz_manifest,
    zbuduj_widok_tekstowy,
)

_MANIFEST = Manifest(
    wersja_schematu=WERSJA_SCHEMATU,
    identyfikator_projektu="proj-abc123",
    nazwa_projektu="Projekt testowy",
    zrodla=(
        WpisZrodla(
            identyfikator="plik_tekstowy-1111",
            typ="plik_tekstowy",
            pochodzenie="dokument_strukturalny.md",
            checksum="a" * 64,
            status="spakowane",
            duplikat=None,
            decyzja_md=True,
            uzasadnienie_md=("co najmniej jedna tabela", "co najmniej dwie listy"),
            pliki_wynikowe=("pliki_wynikowe/notatka.txt", "pliki_wynikowe/notatka.md"),
            komunikat_bledu=None,
        ),
        WpisZrodla(
            identyfikator="blad-2222",
            typ="plik",
            pochodzenie="nie_ma_pliku.txt",
            checksum="",
            status="blad",
            duplikat=None,
            decyzja_md=None,
            uzasadnienie_md=(),
            pliki_wynikowe=(),
            komunikat_bledu="Plik nie istnieje.",
        ),
    ),
    wyniki=(
        WpisWyniku(
            sciezka="pliki_wynikowe/notatka.txt",
            format="txt",
            liczba_zrodel=1,
            liczba_slow=120,
            liczba_znakow_pliku=800,
            rozmiar_bajtow=812,
            checksum="b" * 64,
            status="spakowane",
        ),
    ),
)


def test_manifest_json_zawiera_wymagane_pola(tmp_path: Path) -> None:
    zapisz_manifest(tmp_path / "manifest.json", tmp_path / "manifest.txt", _MANIFEST)

    dane = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert dane["wersja_schematu"] == WERSJA_SCHEMATU
    assert len(dane["zrodla"]) == 2
    assert dane["zrodla"][0]["decyzja_md"] is True
    assert dane["zrodla"][0]["uzasadnienie_md"] == [
        "co najmniej jedna tabela",
        "co najmniej dwie listy",
    ]
    assert dane["zrodla"][1]["status"] == "blad"
    assert dane["wyniki"][0]["liczba_slow"] == 120


def test_manifest_txt_jest_czytelny_liniowo_bez_tabel(tmp_path: Path) -> None:
    zapisz_manifest(tmp_path / "manifest.json", tmp_path / "manifest.txt", _MANIFEST)

    tekst = (tmp_path / "manifest.txt").read_text(encoding="utf-8")
    assert "Źródło: plik_tekstowy-1111" in tekst
    assert "Wygenerowano wersję MD: tak" in tekst
    assert "Komunikat błędu: Plik nie istnieje." in tekst
    assert "|" not in tekst
    assert "---" not in tekst


def test_manifest_zapisuje_decyzje_deduplikacji_w_json_i_w_widoku_tekstowym(
    tmp_path: Path,
) -> None:
    manifest = replace(
        _MANIFEST,
        zrodla=(
            replace(
                _MANIFEST.zrodla[0], status="duplikat", duplikat="duplikat źródła plik_tekstowy-9"
            ),
            _MANIFEST.zrodla[1],
        ),
        deduplikacja=(
            WpisDeduplikacji(
                identyfikator_zrodla_glownego="plik_tekstowy-9",
                identyfikator_duplikatu="plik_tekstowy-1111",
                metoda="SimHash",
                wynik_podobienstwa=0.94,
                decyzja="duplikat",
                uzasadnienie="Podobieństwo 0.94 osiągnęło próg pewnego duplikatu 0.90.",
            ),
        ),
    )

    zapisz_manifest(tmp_path / "manifest.json", tmp_path / "manifest.txt", manifest)

    dane = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert dane["deduplikacja"][0]["identyfikator_duplikatu"] == "plik_tekstowy-1111"
    assert dane["deduplikacja"][0]["metoda"] == "SimHash"
    assert dane["zrodla"][0]["duplikat"] == "duplikat źródła plik_tekstowy-9"

    tekst = (tmp_path / "manifest.txt").read_text(encoding="utf-8")
    assert "Decyzje deduplikacji, liczba: 1" in tekst
    assert "Źródło główne: plik_tekstowy-9" in tekst
    assert "Podobieństwo: 0.94" in tekst
    assert "Duplikat: duplikat źródła plik_tekstowy-9" in tekst


def test_manifest_bez_deduplikacji_ma_pusta_liste(tmp_path: Path) -> None:
    zapisz_manifest(tmp_path / "manifest.json", tmp_path / "manifest.txt", _MANIFEST)

    dane = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert dane["deduplikacja"] == []
    assert "Decyzje deduplikacji, liczba: 0" in (tmp_path / "manifest.txt").read_text(
        encoding="utf-8"
    )


def test_manifest_zapisuje_ocene_jakosci_wraz_z_powodami(tmp_path: Path) -> None:
    manifest = replace(
        _MANIFEST,
        zrodla=(
            replace(
                _MANIFEST.zrodla[0],
                ocena_jakosci="podejrzana",
                powody_oceny=("źródło nie ma tytułu",),
            ),
            _MANIFEST.zrodla[1],
        ),
    )

    zapisz_manifest(tmp_path / "manifest.json", tmp_path / "manifest.txt", manifest)

    dane = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert dane["zrodla"][0]["ocena_jakosci"] == "podejrzana"
    assert dane["zrodla"][0]["powody_oceny"] == ["źródło nie ma tytułu"]
    assert dane["zrodla"][1]["ocena_jakosci"] is None

    tekst = (tmp_path / "manifest.txt").read_text(encoding="utf-8")
    assert "Ocena jakości ekstrakcji: podejrzana" in tekst
    assert "    - źródło nie ma tytułu" in tekst


def test_manifest_pokazuje_grupe_czesci_i_zrodla_w_pliku() -> None:
    manifest = replace(
        _MANIFEST,
        zrodla=(
            replace(
                _MANIFEST.zrodla[0],
                grupa_pakowania="Podatki 2026",
                ostrzezenia_pakowania=("Cięcie wewnątrz zdania.",),
            ),
        ),
        wyniki=(
            WpisWyniku(
                sciezka="pliki_wynikowe/podatki_2026_ab12_czesc_1_z_2.txt",
                format="txt",
                liczba_zrodel=3,
                liczba_slow=400,
                liczba_znakow_pliku=2600,
                rozmiar_bajtow=2650,
                checksum="c" * 64,
                status="spakowane",
                identyfikatory_zrodel=("plik_tekstowy-1", "plik_tekstowy-2", "plik_tekstowy-3"),
                numer_czesci=1,
                liczba_czesci=2,
            ),
        ),
    )

    widok = zbuduj_widok_tekstowy(manifest)

    assert "Grupa pakowania: Podatki 2026" in widok
    assert "Ostrzeżenia podziału:" in widok
    assert "    - Cięcie wewnątrz zdania." in widok
    assert "Część: 1 z 2" in widok
    assert "Liczba źródeł: 3" in widok
    assert "Źródła w pliku:" in widok
    assert "    - plik_tekstowy-2" in widok


def test_manifest_json_zapisuje_pola_pakowania(tmp_path: Path) -> None:
    manifest = replace(
        _MANIFEST,
        zrodla=(replace(_MANIFEST.zrodla[0], grupa_pakowania="Grupa"),),
        wyniki=(
            replace(
                _MANIFEST.wyniki[0],
                identyfikatory_zrodel=("plik_tekstowy-1", "plik_tekstowy-2"),
                numer_czesci=None,
                liczba_czesci=None,
            ),
        ),
    )
    zapisz_manifest(tmp_path / "manifest.json", tmp_path / "manifest.txt", manifest)
    dane = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    assert dane["zrodla"][0]["grupa_pakowania"] == "Grupa"
    assert dane["zrodla"][0]["ostrzezenia_pakowania"] == []
    assert dane["wyniki"][0]["identyfikatory_zrodel"] == ["plik_tekstowy-1", "plik_tekstowy-2"]
    assert dane["wyniki"][0]["numer_czesci"] is None
