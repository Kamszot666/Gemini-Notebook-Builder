"""Testy wykrywania obrotu strony o 90, 180 i 270 stopni przed odczytem.

Wszystkie obrazy są syntetyczne. Testy zależne od OCR pomijają się z komunikatem,
gdy nie da się rozpoznać polskiego tekstu (fikstura ``wymaga_ocr_pol``); testy
wymagające danych orientacji pomijają się, gdy nie ma ``osd.traineddata``.
"""

from __future__ import annotations

import difflib
import shutil
from pathlib import Path

import pytest
from PIL import Image

from gnb.images import obrot_strony, odczyt_strony
from gnb.images.obrot_strony import (
    OSTRZEZENIE_BRAK_DANYCH_ORIENTACJI,
    dane_orientacji_dostepne,
    obroc_zgodnie_z_zegarem,
)
from gnb.images.odczyt_strony import odczytaj_strone, zapisz_png
from gnb.images.tesseract import (
    UstawieniaOcr,
    WynikOcrZPewnoscia,
    dostepne_jezyki,
    rozpoznaj_z_pewnoscia,
)
from tests.images.test_odczyt_pewnosci import _strona_druku
from tests.images.test_tesseract_pewnosc import _znajdz_pol_traineddata


@pytest.fixture
def wymaga_osd(wymaga_ocr_pol: None) -> None:
    if "osd" not in dostepne_jezyki():
        pytest.skip("Tesseract nie ma danych orientacji osd.traineddata.")


def _obrocona_zgodnie_z_zegarem(kat: int) -> Image.Image:
    """Zwraca syntetyczną stronę druku, którą ktoś obrócił zgodnie z zegarem o `kat`."""
    return _strona_druku().convert("RGB").rotate(-kat, expand=True, fillcolor=(255, 255, 255))


def _zgodnosc(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


@pytest.mark.parametrize("kat", [90, 180, 270])
def test_obrocona_strona_jest_odczytana_z_zapisanym_obrotem(wymaga_osd: None, kat: int) -> None:
    ustawienia = UstawieniaOcr(jezyk="pol")
    wzorzec = rozpoznaj_z_pewnoscia(zapisz_png(_strona_druku()), ustawienia)

    wynik = odczytaj_strone(
        _obrocona_zgodnie_z_zegarem(kat), ustawienia, przygotowanie_wlaczone=True
    )

    assert wynik.srednia_pewnosc > 85
    assert _zgodnosc(wynik.tekst, wzorzec.tekst) > 0.95
    # Strona obrócona zgodnie z zegarem o `kat` wraca na miejsce obrotem o dopełnienie do 360.
    oczekiwany = (360 - kat) % 360
    if kat == 90:
        # Tesseract 5.4 sam odczytuje stronę obróconą zgodnie z zegarem o 90 stopni,
        # więc pierwszy odczyt bywa już dobry i obrót nie jest potrzebny; starsze
        # wersje tego nie robią.
        assert wynik.obrot_stopnie in (0, oczekiwany)
    else:
        assert wynik.obrot_stopnie == oczekiwany


def test_kierunek_obrotu_poprawia_odczyt_a_przeciwny_go_psuje(wymaga_ocr_pol: None) -> None:
    ustawienia = UstawieniaOcr(jezyk="pol")
    strona_obrocona = _obrocona_zgodnie_z_zegarem(90)

    poprawny = rozpoznaj_z_pewnoscia(
        zapisz_png(obroc_zgodnie_z_zegarem(strona_obrocona, 270)), ustawienia
    )
    przeciwny = rozpoznaj_z_pewnoscia(
        zapisz_png(obroc_zgodnie_z_zegarem(strona_obrocona, 90)), ustawienia
    )

    assert poprawny.srednia_pewnosc > 85
    assert przeciwny.srednia_pewnosc < 60


def test_prosta_strona_nie_ma_obrotu_a_dobry_odczyt_nie_wola_wykrywania_orientacji(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wywolania: list[list[str]] = []

    def licznik(polecenie: list[str], **_nazwane: object) -> None:
        wywolania.append(polecenie)
        raise AssertionError("Wykrywanie orientacji nie powinno być uruchomione.")

    monkeypatch.setattr(obrot_strony.subprocess, "run", licznik)
    monkeypatch.setattr(
        odczyt_strony,
        "rozpoznaj_z_pewnoscia",
        lambda *_a, **_n: WynikOcrZPewnoscia("dobry odczyt", 95.0, 50),
    )

    wynik = odczytaj_strone(
        Image.new("L", (300, 300), 255), UstawieniaOcr(), przygotowanie_wlaczone=True
    )

    assert wynik.obrot_stopnie == 0
    assert wynik.ostrzezenia == ()
    assert wywolania == []


def test_prosta_strona_ze_slabym_odczytem_zostaje_bez_obrotu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(odczyt_strony, "dane_orientacji_dostepne", lambda *_a: True)
    monkeypatch.setattr(odczyt_strony, "wykryj_obrot_osd", lambda *_a, **_n: 0)
    monkeypatch.setattr(
        odczyt_strony,
        "rozpoznaj_z_pewnoscia",
        lambda *_a, **_n: WynikOcrZPewnoscia("blade", 78.0, 40),
    )

    wynik = odczytaj_strone(
        Image.new("L", (300, 300), 255), UstawieniaOcr(), przygotowanie_wlaczone=False
    )

    assert wynik.obrot_stopnie == 0


def test_bledna_podpowiedz_orientacji_nie_pogarsza_wyniku(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(odczyt_strony, "dane_orientacji_dostepne", lambda *_a: True)
    monkeypatch.setattr(odczyt_strony, "wykryj_obrot_osd", lambda *_a, **_n: 90)
    odczyty = iter(
        [
            WynikOcrZPewnoscia("dobry", 80.0, 50),
            WynikOcrZPewnoscia("belkot", 30.0, 50),
            WynikOcrZPewnoscia("belkot", 30.0, 50),
            WynikOcrZPewnoscia("belkot", 30.0, 50),
        ]
    )
    monkeypatch.setattr(odczyt_strony, "rozpoznaj_z_pewnoscia", lambda *_a, **_n: next(odczyty))

    wynik = odczytaj_strone(
        Image.new("L", (300, 300), 255), UstawieniaOcr(), przygotowanie_wlaczone=False
    )

    assert wynik.tekst == "dobry"
    assert wynik.obrot_stopnie == 0


def test_zly_kat_z_osd_nie_blokuje_sprawdzenia_pozostalych_katow(
    wymaga_ocr_pol: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Strona obrócona zgodnie z zegarem o 270 stopni wraca obrotem o 90; podpowiedź 270
    # jest błędna. (Strona obrócona o 90 stopni jest czytana przez Tesseract 5.4 bez
    # obrotu, więc nie nadaje się do sprawdzenia tej luki.)
    monkeypatch.setattr(odczyt_strony, "dane_orientacji_dostepne", lambda *_a: True)
    monkeypatch.setattr(odczyt_strony, "wykryj_obrot_osd", lambda *_a, **_n: 270)

    wynik = odczytaj_strone(
        _obrocona_zgodnie_z_zegarem(270),
        UstawieniaOcr(jezyk="pol"),
        przygotowanie_wlaczone=True,
    )

    assert wynik.obrot_stopnie == 90
    assert wynik.srednia_pewnosc > 85


def test_osd_wskazujace_zero_dla_strony_do_gory_nogami_nie_blokuje_obrotu(
    wymaga_ocr_pol: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(odczyt_strony, "dane_orientacji_dostepne", lambda *_a: True)
    monkeypatch.setattr(odczyt_strony, "wykryj_obrot_osd", lambda *_a, **_n: 0)

    wynik = odczytaj_strone(
        _obrocona_zgodnie_z_zegarem(180),
        UstawieniaOcr(jezyk="pol"),
        przygotowanie_wlaczone=True,
    )

    assert wynik.obrot_stopnie == 180
    assert wynik.srednia_pewnosc > 85


def test_strona_poprawiona_obrotem_wedlug_osd_nie_dostaje_dodatkowych_odczytow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(odczyt_strony, "dane_orientacji_dostepne", lambda *_a: True)
    monkeypatch.setattr(odczyt_strony, "wykryj_obrot_osd", lambda *_a, **_n: 180)
    odczyty = iter([WynikOcrZPewnoscia("slaby", 40.0, 50), WynikOcrZPewnoscia("dobry", 92.0, 50)])
    wywolania: list[int] = []

    def odczyt(*_a: object, **_n: object) -> WynikOcrZPewnoscia:
        wywolania.append(1)
        return next(odczyty)

    monkeypatch.setattr(odczyt_strony, "rozpoznaj_z_pewnoscia", odczyt)

    wynik = odczytaj_strone(
        Image.new("L", (300, 300), 255), UstawieniaOcr(), przygotowanie_wlaczone=False
    )

    assert wynik.obrot_stopnie == 180
    assert len(wywolania) == 2


def test_brak_danych_orientacji_sprawdza_obroty_po_kolei_i_zglasza_ostrzezenie(
    wymaga_osd: None, tmp_path: Path
) -> None:
    pol = _znajdz_pol_traineddata()
    if pol is None:
        pytest.skip("Nie ustalono położenia pol.traineddata w instalacji Tesseracta.")
    katalog_danych = tmp_path / "bez_osd"
    katalog_danych.mkdir()
    shutil.copy(pol, katalog_danych / "pol.traineddata")
    ustawienia = UstawieniaOcr(jezyk="pol", sciezka_tessdata=str(katalog_danych))
    assert not dane_orientacji_dostepne("", str(katalog_danych))

    # Syntetyczna strona do góry nogami czyta się z pewnością około 52, a prawdziwe
    # zdjęcia z testu użytkownika około 41, więc próg nieczytelności jest tu
    # podniesiony do 60, żeby ścieżka bez danych orientacji została uruchomiona.
    wynik = odczytaj_strone(
        _obrocona_zgodnie_z_zegarem(180),
        ustawienia,
        przygotowanie_wlaczone=True,
    )

    assert wynik.srednia_pewnosc > 85
    assert wynik.obrot_stopnie == 180
    assert wynik.ostrzezenia == (OSTRZEZENIE_BRAK_DANYCH_ORIENTACJI,)
