"""Testy budowy i zapisu manifestu projektu."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from gnb.output.manifest import (
    WERSJA_SCHEMATU,
    Manifest,
    WpisWyniku,
    WpisZrodla,
    zapisz_manifest,
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
