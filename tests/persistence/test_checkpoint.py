"""Testy checkpointu projektu z zapisem atomowym."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.persistence.checkpoint import (
    WERSJA_SCHEMATU,
    Checkpoint,
    StanWyniku,
    StanZrodla,
    wczytaj,
    zapisz,
)


def _przykladowy_checkpoint() -> Checkpoint:
    return Checkpoint(
        wersja_schematu=WERSJA_SCHEMATU,
        identyfikator_projektu="proj-abc",
        nazwa_projektu="Projekt",
        katalog_projektu="/tmp/projekt",
        konfiguracja={"limit_zrodel": "100"},
        czas_ostatniej_zmiany="2026-08-26T10:00:00+00:00",
        zrodla={
            "plik_tekstowy-1": StanZrodla(
                identyfikator="plik_tekstowy-1",
                typ="plik_tekstowy",
                pochodzenie="a.md",
                checksum="a" * 64,
                format_zrodla="md",
                status="spakowane",
                nazwa_bazowa_wyniku="a",
                wyniki=[
                    StanWyniku(
                        sciezka_wzgledna="pliki_wynikowe/a.txt",
                        format="txt",
                        liczba_slow=10,
                        liczba_znakow=60,
                        rozmiar_bajtow=61,
                        checksum="b" * 64,
                    )
                ],
                liczba_slow=10,
                liczba_znakow=60,
                decyzja_md=False,
            )
        },
    )


def test_zapis_i_odczyt_zwraca_ten_sam_stan(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    oryginal = _przykladowy_checkpoint()
    zapisz(sciezka, oryginal)

    wczytany = wczytaj(sciezka)
    assert wczytany == oryginal


def test_brak_pliku_checkpointu_daje_none(tmp_path: Path) -> None:
    assert wczytaj(tmp_path / "nie_ma.json") is None


def test_drugi_zapis_zostawia_kopie_zapasowa(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    zapisz(sciezka, _przykladowy_checkpoint())
    zmieniony = _przykladowy_checkpoint()
    zmieniony.zakonczony = True
    zapisz(sciezka, zmieniony)

    kopia = tmp_path / "checkpoint.json.bak"
    assert kopia.is_file()
    assert not (tmp_path / "checkpoint.json.tmp").exists()


def test_uszkodzony_plik_bez_kopii_daje_blad_trwaly(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    sciezka.write_text("to nie jest json", encoding="utf-8")
    with pytest.raises(BladTrwaly):
        wczytaj(sciezka)


def test_uszkodzony_plik_glowny_wczytuje_sie_z_kopii(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    zapisz(sciezka, _przykladowy_checkpoint())
    zmieniony = _przykladowy_checkpoint()
    zmieniony.zakonczony = True
    zapisz(sciezka, zmieniony)

    sciezka.write_text("uszkodzone", encoding="utf-8")
    wczytany = wczytaj(sciezka)
    assert wczytany is not None
    assert wczytany.zakonczony is False
