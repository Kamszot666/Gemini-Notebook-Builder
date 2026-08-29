"""Test end-to-end etapu piątego: deduplikacja w pełnym potoku.

Sprawdza trzy sytuacje na gotowych plikach i plikach budowanych w teście:
pewny duplikat znika z wyników ze statusem „duplikat”, para o średnim
podobieństwie zostaje w całości i trafia do materiałów do sprawdzenia, a
przerwana praca wznawia się bez ponownej ekstrakcji i bez zmiany decyzji.
"""

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
    stan = {"teraz": datetime(2026, 8, 29, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _pliki_o_tej_samej_tresci(tmp_path: Path) -> list[PozycjaWejsciowa]:
    """Dwa pliki różniące się tylko odstępami plus jeden osobny plik."""
    katalog = tmp_path / "wejscia"
    katalog.mkdir()
    tresc = (
        "Baza wiedzy dla asystenta AI jest lepsza, gdy zawiera mniej powtorzen. "
        "Najczestszym bledem jest wrzucanie do jednego zbioru wszystkiego naraz. "
        "Drugim bledem jest usuwanie materialow tylko dlatego, ze sa podobne."
    )
    (katalog / "wersja_a.txt").write_text(tresc, encoding="utf-8")
    (katalog / "wersja_b.txt").write_text(f"  {tresc}   \n\n", encoding="utf-8")
    (katalog / "osobny.txt").write_text(
        "Zupelnie inny tekst o pogodzie, mgle nad rzeka i spacerze wzdluz brzegu.",
        encoding="utf-8",
    )
    moment = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    return [
        przyjmij_plik(katalog / "wersja_a.txt", moment),
        przyjmij_plik(katalog / "wersja_b.txt", moment),
        przyjmij_plik(katalog / "osobny.txt", moment),
    ]


def test_pewny_duplikat_znika_z_wynikow_i_zwalnia_slot(tmp_path: Path) -> None:
    wynik = przetworz_projekt(
        _pliki_o_tej_samej_tresci(tmp_path),
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test pewnego duplikatu",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 2
    assert wynik.liczba_bledow == 0

    pliki = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki) == 2

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    statusy = sorted(zrodlo["status"] for zrodlo in manifest["zrodla"])
    assert statusy == ["duplikat", "spakowane", "spakowane"]

    (decyzja,) = manifest["deduplikacja"]
    assert decyzja["decyzja"] == "duplikat"
    assert decyzja["metoda"] in ("hash treści", "porównanie kosmetyczne")
    assert decyzja["zachowane_fragmenty_unikalne"] == []

    duplikat = next(z for z in manifest["zrodla"] if z["status"] == "duplikat")
    assert duplikat["duplikat"] == f"duplikat źródła {decyzja['identyfikator_zrodla_glownego']}"
    assert not duplikat["pliki_wynikowe"]

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba wykrytych duplikatów: 1" in raport
    assert "Liczba źródeł po deduplikacji: 2" in raport

    log_wazne = (wynik.katalog_projektu / "logi" / "log_wazne.txt").read_text(encoding="utf-8")
    assert "Źródło rozpoznane jako duplikat:" in log_wazne
    assert "Deduplikacja zakończona:" in log_wazne


def test_srednie_podobienstwo_zostawia_oba_zrodla_i_akapit_unikalny(tmp_path: Path) -> None:
    """Przedruk artykułu z jednym akapitem unikalnym nie może zniknąć w całości.

    Oryginał i przedruk z danych testowych mają podobieństwo w paśmie środkowym,
    więc obie wersje zostają w wynikach, a akapit obecny tylko w przedruku jest
    w jego pliku wynikowym. Para trafia do materiałów do sprawdzenia.
    """
    moment = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)
    pozycje = [
        przyjmij_plik(KATALOG_DANYCH / "artykul_oryginal.html", moment),
        przyjmij_plik(KATALOG_DANYCH / "artykul_przedruk.html", moment),
    ]

    wynik = przetworz_projekt(
        pozycje,
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test przedruku",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 2
    assert wynik.liczba_bledow == 0

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert all(zrodlo["status"] == "spakowane" for zrodlo in manifest["zrodla"])

    (decyzja,) = manifest["deduplikacja"]
    assert decyzja["decyzja"] == "wymaga_decyzji_uzytkownika"

    teksty = [
        plik.read_text(encoding="utf-8")
        for plik in (wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt")
    ]
    assert any("wyłącznie w przedruku" in tekst for tekst in teksty)

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba wykrytych duplikatów: 0" in raport
    assert "Materiały do sprawdzenia" in raport
    assert "Możliwe duplikaty do rozstrzygnięcia:" in raport


def test_wznowienie_po_normalizacji_nie_zmienia_decyzji_deduplikacji(tmp_path: Path) -> None:
    """Przerwanie i wznowienie nie może dać innego wyniku deduplikacji ani innych plików."""
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki")
    pozycje = _pliki_o_tej_samej_tresci(tmp_path)

    pierwsze = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test wznowienia dedup", zegar=_zegar_krokowy()
    )
    pliki_pierwsze = sorted(
        p.name for p in (pierwsze.katalog_projektu / "pliki_wynikowe").iterdir()
    )
    manifest_pierwszy = json.loads(pierwsze.sciezka_manifestu.read_text(encoding="utf-8"))

    drugie = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test wznowienia dedup", zegar=_zegar_krokowy()
    )
    pliki_drugie = sorted(p.name for p in (drugie.katalog_projektu / "pliki_wynikowe").iterdir())
    manifest_drugi = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))

    assert drugie.wznowiono is True
    assert pliki_drugie == pliki_pierwsze
    assert manifest_drugi["deduplikacja"] == manifest_pierwszy["deduplikacja"]
    statusy_pierwsze = sorted(z["status"] for z in manifest_pierwszy["zrodla"])
    statusy_drugie = sorted(z["status"] for z in manifest_drugi["zrodla"])
    assert statusy_drugie == statusy_pierwsze == ["duplikat", "spakowane", "spakowane"]


def test_wylaczona_deduplikacja_zostawia_wszystkie_zrodla(tmp_path: Path) -> None:
    """Wyłączenie wszystkich etapów w konfiguracji musi realnie zatrzymać deduplikację."""
    wynik = przetworz_projekt(
        _pliki_o_tej_samej_tresci(tmp_path),
        Konfiguracja(
            katalog_wynikow=tmp_path / "wyniki",
            deduplikacja_hash_wlaczona=False,
            deduplikacja_kosmetyczna_wlaczona=False,
            deduplikacja_podobienstwo_wlaczone=False,
        ),
        nazwa_projektu="Test bez deduplikacji",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 3
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert manifest["deduplikacja"] == []
    assert all(zrodlo["status"] == "spakowane" for zrodlo in manifest["zrodla"])


def test_tekst_wklejony_i_plik_o_tej_samej_tresci_sa_duplikatem(tmp_path: Path) -> None:
    """Deduplikacja działa też między różnymi typami wejścia, nie tylko plikami."""
    katalog = tmp_path / "wejscia"
    katalog.mkdir()
    tresc = "Notatka o tym, jak porzadkowac zrodla przed wgraniem ich do notatnika."
    (katalog / "notatka.txt").write_text(tresc, encoding="utf-8")
    moment = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)

    wynik = przetworz_projekt(
        [przyjmij_plik(katalog / "notatka.txt", moment), przyjmij_tekst(tresc, moment)],
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test duplikatu miedzy typami",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert sorted(z["status"] for z in manifest["zrodla"]) == ["duplikat", "spakowane"]
