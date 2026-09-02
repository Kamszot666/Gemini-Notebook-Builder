"""Testy wykrywania niedokończonych projektów w katalogu wyników."""

from __future__ import annotations

from pathlib import Path

from gnb.persistence.checkpoint import WERSJA_SCHEMATU, Checkpoint, zapisz
from gnb.ui.projekty import niedokonczone, znajdz_projekty


def _zapisz_projekt(katalog_wynikow: Path, nazwa: str, *, zakonczony: bool, czas: str) -> None:
    katalog = katalog_wynikow / nazwa
    katalog.mkdir(parents=True)
    zapisz(
        katalog / "checkpoint.json",
        Checkpoint(
            wersja_schematu=WERSJA_SCHEMATU,
            identyfikator_projektu=f"proj-{nazwa}",
            nazwa_projektu=nazwa,
            katalog_projektu=str(katalog),
            konfiguracja={},
            czas_ostatniej_zmiany=czas,
            zakonczony=zakonczony,
        ),
    )


def test_projekt_niedokonczony_jest_wykryty_a_ukonczony_pominiety(tmp_path: Path) -> None:
    _zapisz_projekt(tmp_path, "gotowy", zakonczony=True, czas="2026-09-01T10:00:00+00:00")
    _zapisz_projekt(tmp_path, "w_toku", zakonczony=False, czas="2026-09-02T10:00:00+00:00")

    nazwy = [projekt.nazwa for projekt in niedokonczone(tmp_path)]
    assert nazwy == ["w_toku"]


def test_lista_jest_uporzadkowana_od_ostatnio_zmienionych(tmp_path: Path) -> None:
    _zapisz_projekt(tmp_path, "starszy", zakonczony=False, czas="2026-09-01T10:00:00+00:00")
    _zapisz_projekt(tmp_path, "nowszy", zakonczony=False, czas="2026-09-03T10:00:00+00:00")

    assert [projekt.nazwa for projekt in znajdz_projekty(tmp_path)] == ["nowszy", "starszy"]


def test_uszkodzony_checkpoint_nie_wywraca_listy(tmp_path: Path) -> None:
    _zapisz_projekt(tmp_path, "dobry", zakonczony=False, czas="2026-09-02T10:00:00+00:00")
    zepsuty = tmp_path / "zepsuty"
    zepsuty.mkdir()
    (zepsuty / "checkpoint.json").write_text("to nie jest json", encoding="utf-8")

    projekty = {projekt.nazwa: projekt for projekt in znajdz_projekty(tmp_path)}
    assert set(projekty) == {"dobry", "zepsuty"}
    assert projekty["zepsuty"].komunikat_bledu is not None
    assert projekty["zepsuty"] in niedokonczone(tmp_path)


def test_brak_katalogu_wynikow_daje_pusta_liste(tmp_path: Path) -> None:
    assert znajdz_projekty(tmp_path / "nie_ma") == []


def test_podkatalog_bez_checkpointu_jest_pomijany(tmp_path: Path) -> None:
    (tmp_path / "nie_projekt").mkdir()
    (tmp_path / "nie_projekt" / "cos.txt").write_text("x", encoding="utf-8")
    assert znajdz_projekty(tmp_path) == []
