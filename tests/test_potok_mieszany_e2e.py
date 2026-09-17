"""Test end-to-end scalający: wiele typów źródeł naraz w jednym przebiegu.

Dziesięć istniejących testów end-to-end sprawdzają pojedyncze ścieżki potoku.
Ten sprawdza coś, czego żaden z nich nie sprawdza osobno: że manifest, raport
końcowy i rzeczywista zawartość katalogu wyników jednego przebiegu — łączącego
tekst wklejony, plik Markdown, dokument PDF, obraz, materiał nutowy natywny
oraz źródło pominięte z braku narzędzia — opowiadają dokładnie tę samą
historię, a nie tylko każde z osobna wygląda poprawnie.

Obraz jest przetwarzany z wyłączonym OCR-em (``ocr_wlaczony=False``), tak jak
w ``test_potok_obrazy_e2e.py``, żeby wynik testu nie zależał od tego, czy na
maszynie uruchamiającej testy jest zainstalowany Tesseract z polskimi danymi
językowymi.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik, przyjmij_tekst
from gnb.music import audiveris
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"
_MOMENT = datetime(2026, 9, 17, 9, 0, tzinfo=UTC)
_GRUPA = "Materiały mieszane etapu dwunastego"
# Liczba źródeł, które naprawdę powinny przejść potok: tekst wklejony, plik MD,
# dokument PDF, obraz i materiał nutowy natywny. Szósty wpis, skan nut bez
# Audiverisa, ma zostać pominięty i celowo nie wchodzi do tej liczby.
_LICZBA_PRAWDZIWYCH_ZRODEL = 5


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": _MOMENT}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _wymus_brak_audiverisa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wymusza „nie znaleziono” dla Audiverisa, niezależnie od tego, co jest na tej maszynie.

    Ten sam sposób co w ``test_potok_nuty_e2e.py``, żeby ścieżka pominięcia z braku
    narzędzia była deterministyczna, a nie zależna od tego, czy akurat ta maszyna
    ma zainstalowanego Audiverisa.
    """
    monkeypatch.setattr(shutil, "which", lambda _nazwa: None)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.setattr(audiveris, "_DOMYSLNE_SCIEZKI_WINDOWS", ())


def _pozycje() -> list[PozycjaWejsciowa]:
    return [
        # Pierwsze w kolejności: skan nut, który stanie się źródłem pominiętym.
        # Celowo na początku listy, a nie na końcu — jeśli pominięcie z braku
        # narzędzia błędnie zajmowałoby slot limitu (regresja z pull requestów
        # 31 i 32), ujawniłoby się to dopiero przy kolejnych, prawdziwych
        # źródłach, nie przy nim samym.
        przyjmij_plik(KATALOG_DANYCH / "nuty_skan.png", _MOMENT, nuty=True),
        przyjmij_tekst(
            "Krótka notatka wklejona bezpośrednio do testu scalającego etapu dwunastego.",
            _MOMENT,
            grupa=_GRUPA,
        ),
        przyjmij_plik(KATALOG_DANYCH / "dokument_strukturalny.md", _MOMENT, grupa=_GRUPA),
        przyjmij_plik(KATALOG_DANYCH / "pdf_tekstowy.pdf", _MOMENT, grupa=_GRUPA),
        przyjmij_plik(KATALOG_DANYCH / "obraz_wykres.png", _MOMENT, grupa=_GRUPA),
        # Materiał nutowy nie podlega grupowaniu tematycznemu niezależnie od
        # tego, czy dostanie nazwę grupy — zostaje bez niej dla czytelności.
        przyjmij_plik(KATALOG_DANYCH / "melodia.musicxml", _MOMENT),
    ]


def _konfiguracja(tmp_path: Path) -> Konfiguracja:
    return Konfiguracja(
        katalog_wynikow=tmp_path,
        deduplikacja_hash_wlaczona=False,
        deduplikacja_kosmetyczna_wlaczona=False,
        deduplikacja_podobienstwo_wlaczone=False,
        ocr_wlaczony=False,
        # Dokładnie tyle, ile prawdziwych źródeł jest w tym przebiegu. Gdyby
        # pominięty skan nut wciąż liczył się do limitu w trakcie przyjmowania
        # wejść, piąte prawdziwe źródło (obraz) zostałoby odrzucone, zanim
        # w ogóle doszłoby do pakowania.
        limit_zrodel=_LICZBA_PRAWDZIWYCH_ZRODEL,
    )


def _sha256(sciezka: Path) -> str:
    return hashlib.sha256(sciezka.read_bytes()).hexdigest()


def test_wiele_typow_zrodel_w_jednym_przebiegu_daje_spojny_manifest_raport_i_katalog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _wymus_brak_audiverisa(monkeypatch)

    wynik = przetworz_projekt(
        _pozycje(),
        _konfiguracja(tmp_path),
        nazwa_projektu="Test scalający etapu dwunastego",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_bledow == 0
    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_przetworzonych == _LICZBA_PRAWDZIWYCH_ZRODEL

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    statusy = [zrodlo["status"] for zrodlo in manifest["zrodla"]]
    assert statusy.count("spakowane") == _LICZBA_PRAWDZIWYCH_ZRODEL
    assert statusy.count("pominiete") == 1
    assert statusy.count("blad") == 0

    # Kontrola wprost, że źródło pominięte nie zajęło slotu limitu: gdyby
    # zajęło, piąte prawdziwe źródło (obraz, ostatnie z grupy w kolejności
    # wejścia) nie zostałoby przyjęte, a powyższe dwie asercje już by padły.
    # Tu sprawdzamy dodatkowo, że to właśnie skan nut jest tym pominiętym,
    # a nie przypadkiem coś innego.
    pominiete = next(z for z in manifest["zrodla"] if z["status"] == "pominiete")
    assert pominiete["typ"] == "plik_nuty"
    assert pominiete["pliki_wynikowe"] == []
    assert "Audiveris" in (pominiete["komunikat_bledu"] or "")

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    pliki_na_dysku = sorted(katalog_wynikow.iterdir())

    # Grupa mieszana — tekst wklejony, plik MD i dokument PDF razem z obrazem —
    # daje dokładnie dwa pliki: jeden PDF dla obrazu, jeden TXT dla reszty
    # połączonej w jeden plik, zgodnie z punktem trzecim sekcji 18d CLAUDE.md.
    # Materiał nutowy, wyłączony z grupowania, dostaje własny, trzeci plik.
    pliki_pdf = [p for p in pliki_na_dysku if p.suffix == ".pdf"]
    pliki_txt = [p for p in pliki_na_dysku if p.suffix == ".txt"]
    pliki_md = [p for p in pliki_na_dysku if p.suffix == ".md"]
    assert len(pliki_pdf) == 1, "grupa mieszana ma dać jeden plik PDF dla obrazu"
    assert len(pliki_txt) == 2, "jeden TXT grupy plus jeden TXT materiału nutowego"
    assert pliki_md == [], "pliki grupy i materiału nutowego nie dostają wersji MD"
    assert len(pliki_na_dysku) == 3

    # Spójność manifestu z rzeczywistą zawartością katalogu: każdy plik
    # wymieniony w manifeście istnieje naprawdę, pod tą samą ścieżką, z tym
    # samym rozmiarem i sumą kontrolną policzoną niezależnie z bajtów na
    # dysku — nigdy z wartości, które kod sam sobie wcześniej zapisał.
    assert len(manifest["wyniki"]) == 3
    for wpis in manifest["wyniki"]:
        sciezka = wynik.katalog_projektu / wpis["sciezka"]
        assert sciezka.is_file(), f"plik {wpis['sciezka']} wymieniony w manifeście nie istnieje"
        assert sciezka.stat().st_size == wpis["rozmiar_bajtow"]
        assert _sha256(sciezka) == wpis["checksum"]

    # Raport końcowy zgadza się z manifestem i z katalogiem, nie tylko sam ze
    # sobą: te same liczby, policzone tu niezależnie od tego, co zapisał kod.
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert f"Liczba plików TXT: {len(pliki_txt)}" in raport
    assert f"Liczba plików MD: {len(pliki_md)}" in raport
    assert f"Liczba plików PDF: {len(pliki_pdf)}" in raport
    assert "Liczba źródeł pominiętych: 1" in raport
    assert f"Liczba źródeł poprawnych: {_LICZBA_PRAWDZIWYCH_ZRODEL}" in raport

    najwiekszy_na_dysku = max(pliki_na_dysku, key=lambda p: p.stat().st_size)
    assert najwiekszy_na_dysku.name in raport
    assert str(najwiekszy_na_dysku.stat().st_size) in raport

    laczne_slowa_z_manifestu = sum(
        wpis["liczba_slow"] for wpis in manifest["wyniki"] if wpis["format"] in ("txt", "pdf")
    )
    assert f"Łączna liczba słów w plikach wynikowych: {laczne_slowa_z_manifestu}" in raport

    liczba_slotow = len(pliki_txt) + len(pliki_pdf)
    procent = round(liczba_slotow * 100 / _LICZBA_PRAWDZIWYCH_ZRODEL)
    assert f"Wykorzystanie limitu źródeł: {procent} procent" in raport

    assert "Źródła nieprzetworzone" in raport
    assert "Audiveris" in raport
