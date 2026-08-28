"""Testy raportu końcowego projektu."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from gnb.output.raport import (
    MaterialDoSprawdzenia,
    PodsumowanieProjektu,
    zapisz_raport,
    zbuduj_raport,
)

_PODSUMOWANIE = PodsumowanieProjektu(
    liczba_wejsc=5,
    liczba_zrodel_poprawnych=4,
    liczba_zrodel_pominietych=0,
    liczba_zrodel_blednych=1,
    liczba_duplikatow=0,
    liczba_zrodel_po_deduplikacji=4,
    liczba_plikow_txt=4,
    liczba_plikow_md=1,
    liczba_plikow_pdf=0,
    limit_zrodel=100,
    najwiekszy_plik_nazwa="pliki_wynikowe/duzy.txt",
    najwiekszy_plik_bajtow=1453,
    laczna_liczba_slow=341,
    czas_pracy_sekundy=92.4,
)


def test_raport_zawiera_wszystkie_pozycje() -> None:
    tekst = zbuduj_raport("Projekt testowy", _PODSUMOWANIE)

    for fragment in (
        "Liczba wejść: 5",
        "Liczba źródeł poprawnych: 4",
        "Liczba źródeł z błędem: 1",
        "Liczba wykrytych duplikatów: 0",
        "Liczba plików TXT: 4",
        "Liczba plików MD: 1",
        "Liczba plików PDF: 0",
        "Wykorzystanie limitu źródeł: 4 procent",
        "Największy plik wynikowy: pliki_wynikowe/duzy.txt, 1453 bajtów",
        "Łączna liczba słów w plikach wynikowych: 341",
        "Czas pracy: 1 min 32 s",
    ):
        assert fragment in tekst


def test_raport_nie_zawiera_tabel_ani_znakow_ozdobnych() -> None:
    tekst = zbuduj_raport("Projekt testowy", _PODSUMOWANIE)
    assert "|" not in tekst
    assert "---" not in tekst
    assert "==" not in tekst


def test_raport_zapisuje_sie_do_pliku(tmp_path: Path) -> None:
    sciezka = tmp_path / "raport.txt"
    zapisz_raport(sciezka, zbuduj_raport("Projekt testowy", _PODSUMOWANIE))
    assert sciezka.read_text(encoding="utf-8").startswith(
        "Raport końcowy projektu: Projekt testowy"
    )


def test_raport_bez_materialow_do_sprawdzenia_nie_ma_takiej_sekcji() -> None:
    tekst = zbuduj_raport("Projekt testowy", _PODSUMOWANIE)

    assert "Materiały do sprawdzenia" not in tekst


def test_raport_wymienia_materialy_do_sprawdzenia_wraz_z_powodami() -> None:
    podsumowanie = replace(
        _PODSUMOWANIE,
        materialy_do_sprawdzenia=(
            MaterialDoSprawdzenia(
                identyfikator="abc123",
                pochodzenie="https://przyklad.pl/artykul",
                powody=("treść ma mniej niż 50 słów, dokładnie 12", "źródło nie ma tytułu"),
            ),
        ),
    )

    tekst = zbuduj_raport("Projekt testowy", podsumowanie)

    assert "Materiały do sprawdzenia, liczba: 1" in tekst
    assert "Żadne z nich nie zostało usunięte." in tekst
    assert "Źródło: https://przyklad.pl/artykul" in tekst
    assert "  Identyfikator: abc123" in tekst
    assert "    - źródło nie ma tytułu" in tekst
