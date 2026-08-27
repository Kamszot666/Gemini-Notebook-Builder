"""Test end-to-end potoku etapu pierwszego, w tym wznowienia z checkpointu."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik, przyjmij_tekst
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 8, 26, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _pozycje() -> list[PozycjaWejsciowa]:
    moment = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
    return [
        przyjmij_plik(KATALOG_DANYCH / "dokument_strukturalny.md", moment),
        przyjmij_plik(KATALOG_DANYCH / "tekst_plaski.txt", moment),
        przyjmij_plik(KATALOG_DANYCH / "tekst_windows1250.txt", moment),
        przyjmij_tekst("Krótki tekst wklejony do testu end-to-end.", moment),
    ]


def test_potok_przetwarza_rozne_zrodla_i_stosuje_regule_md(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test etapu 1", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_przetworzonych == 4
    assert wynik.liczba_bledow == 0

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    pliki = {p.name for p in katalog_wynikow.iterdir()}

    trzon = "jak_przygotować_bazę_wiedzy_dla_asystenta_ai"
    assert len(list(katalog_wynikow.glob(f"{trzon}__*.txt"))) == 1
    assert len(list(katalog_wynikow.glob(f"{trzon}__*.md"))) == 1

    liczba_md = sum(1 for nazwa in pliki if nazwa.endswith(".md"))
    assert liczba_md == 1, "wersję MD dostaje tylko dokument_strukturalny.md"


def test_nazwa_pliku_wynikowego_wiaze_plik_ze_zrodlem_z_manifestu(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test nazw", zegar=_zegar_krokowy()
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    for zrodlo in manifest["zrodla"]:
        skrot = zrodlo["identyfikator"].rsplit("-", 1)[-1][:8]
        for sciezka_wzgledna in zrodlo["pliki_wynikowe"]:
            nazwa = Path(sciezka_wzgledna).stem
            assert nazwa.endswith(f"__{skrot}"), nazwa
            assert " " not in nazwa
            assert nazwa == nazwa.lower()


def test_plik_windows1250_jest_odczytany_bez_utraty_polskich_znakow(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test kodowania", zegar=_zegar_krokowy()
    )

    pasujace = list(
        (wynik.katalog_projektu / "pliki_wynikowe").glob("zażółć_gęślą_jaźń__*.txt")
    )
    assert len(pasujace) == 1, "polskie znaki mają zostać zachowane także w nazwie pliku"
    assert "Zażółć gęślą jaźń." in pasujace[0].read_text(encoding="utf-8")


def test_manifest_i_checkpoint_powstaja_i_sa_spojne(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test spójności", zegar=_zegar_krokowy()
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert len(manifest["zrodla"]) == 4
    assert wynik.sciezka_raportu.exists()

    log_wazny = (wynik.katalog_projektu / "logi" / "log_wazne.txt").read_text(encoding="utf-8")
    assert log_wazny.startswith("--- 2026-08-26 ---")
    assert "Projekt zakończony|" in log_wazny


def test_wznowienie_nie_duplikuje_ani_nie_gubi_zrodel(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pierwsze = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test wznowienia", zegar=_zegar_krokowy()
    )
    pliki_po_pierwszym = sorted(
        p.name for p in (pierwsze.katalog_projektu / "pliki_wynikowe").iterdir()
    )
    manifest_pierwszy = json.loads(pierwsze.sciezka_manifestu.read_text(encoding="utf-8"))

    drugie = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test wznowienia", zegar=_zegar_krokowy()
    )
    pliki_po_drugim = sorted(p.name for p in (drugie.katalog_projektu / "pliki_wynikowe").iterdir())
    manifest_drugi = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))

    assert drugie.wznowiono is True
    assert pliki_po_drugim == pliki_po_pierwszym
    assert len(manifest_drugi["zrodla"]) == len(manifest_pierwszy["zrodla"]) == 4
    assert len(manifest_drugi["wyniki"]) == len(manifest_pierwszy["wyniki"])

    identyfikatory = [zrodlo["identyfikator"] for zrodlo in manifest_drugi["zrodla"]]
    assert len(identyfikatory) == len(set(identyfikatory))


def test_bledne_wejscie_nie_zatrzymuje_potoku(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pozycje = [
        *_pozycje(),
        przyjmij_plik(
            KATALOG_DANYCH / "nie_ma_takiego_pliku.txt", datetime(2026, 8, 26, tzinfo=UTC)
        ),
    ]
    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test odporności", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_przetworzonych == 4
    assert wynik.liczba_bledow == 1

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    statusy = [zrodlo["status"] for zrodlo in manifest["zrodla"]]
    assert statusy.count("blad") == 1
