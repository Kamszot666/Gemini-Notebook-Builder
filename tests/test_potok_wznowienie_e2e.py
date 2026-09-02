"""Test end-to-end wznowienia projektu wyłącznie z listy wejść w checkpoincie.

Interfejs WWW wznawia projekt bez ponownego podawania źródeł: potok odtwarza
wejścia z checkpointu przez `odtworz_wejscia` i przetwarza je od nowa. Etapy już
ukończone nie mają się powtarzać, a żadne źródło nie może po cichu zniknąć.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik, przyjmij_tekst
from gnb.persistence.checkpoint import wczytaj
from gnb.potok import odtworz_wejscia, przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 2, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _pozycje() -> list[PozycjaWejsciowa]:
    moment = datetime(2026, 9, 2, 9, 0, tzinfo=UTC)
    return [
        przyjmij_plik(KATALOG_DANYCH / "dokument_strukturalny.md", moment, grupa="Wiedza"),
        przyjmij_tekst("Krótki tekst wklejony do testu wznowienia.", moment, grupa="Wiedza"),
    ]


def test_wejscia_sa_zapisywane_w_checkpoincie(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test zapisu wejść", zegar=_zegar_krokowy()
    )

    checkpoint = wczytaj(wynik.katalog_projektu / "checkpoint.json")
    assert checkpoint is not None
    rodzaje = sorted(wejscie.typ_wejscia for wejscie in checkpoint.wejscia)
    assert rodzaje == ["plik", "tekst"]
    assert all(wejscie.grupa == "Wiedza" for wejscie in checkpoint.wejscia)


def test_odtworzone_wejscia_daja_te_same_identyfikatory_zrodel(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pierwsze = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test odtworzenia", zegar=_zegar_krokowy()
    )
    manifest_pierwszy = json.loads(pierwsze.sciezka_manifestu.read_text(encoding="utf-8"))
    identyfikatory_pierwsze = sorted(z["identyfikator"] for z in manifest_pierwszy["zrodla"])

    checkpoint = wczytaj(pierwsze.katalog_projektu / "checkpoint.json")
    assert checkpoint is not None
    odtworzone = odtworz_wejscia(checkpoint, konfiguracja)

    assert {p.grupa for p in odtworzone} == {"Wiedza"}
    assert {p.format_zrodla for p in odtworzone} == {"md", "txt"}

    drugie = przetworz_projekt(
        odtworzone, konfiguracja, nazwa_projektu="Test odtworzenia", zegar=_zegar_krokowy()
    )
    assert drugie.wznowiono is True
    manifest_drugi = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))
    identyfikatory_drugie = sorted(z["identyfikator"] for z in manifest_drugi["zrodla"])
    assert identyfikatory_drugie == identyfikatory_pierwsze


def test_wznowienie_konczy_projekt_przerwany_przed_pakowaniem(tmp_path: Path) -> None:
    """Projekt z checkpointem po normalizacji, ale bez plików wynikowych, kończy się po wznowieniu.

    Checkpoint jest tu cofnięty ręcznie do stanu sprzed pakowania: źródła mają
    status „znormalizowane”, deduplikacja nie jest wykonana, nie ma żadnych
    wyników. Wznowienie wyłącznie z listy wejść musi dokończyć deduplikację
    i pakowanie, nie pomijając ani jednego źródła.
    """
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pierwsze = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test dokończenia", zegar=_zegar_krokowy()
    )
    sciezka_checkpointu = pierwsze.katalog_projektu / "checkpoint.json"
    dane = json.loads(sciezka_checkpointu.read_text(encoding="utf-8"))
    dane["zakonczony"] = False
    dane["deduplikacja"] = {"wykonana": False, "decyzje": []}
    for stan in dane["zrodla"].values():
        stan["status"] = "znormalizowane"
        stan["wyniki"] = []
    sciezka_checkpointu.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")
    for plik in (pierwsze.katalog_projektu / "pliki_wynikowe").iterdir():
        plik.unlink()

    checkpoint = wczytaj(sciezka_checkpointu)
    assert checkpoint is not None
    odtworzone = odtworz_wejscia(checkpoint, konfiguracja)

    drugie = przetworz_projekt(
        odtworzone, konfiguracja, nazwa_projektu="Test dokończenia", zegar=_zegar_krokowy()
    )

    assert drugie.wznowiono is True
    assert drugie.liczba_przetworzonych == 2
    assert drugie.liczba_pominietych == 0
    assert drugie.liczba_bledow == 0
    pliki = list((drugie.katalog_projektu / "pliki_wynikowe").iterdir())
    assert pliki, "wznowienie musi odtworzyć pliki wynikowe"
