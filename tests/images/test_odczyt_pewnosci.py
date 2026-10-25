"""Testy odczytu pewności słów, przygotowania zdjęcia i oceny po pewności.

Obrazy są syntetyczne. Testy zależne od Tesseracta pomijają się z komunikatem,
gdy nie da się rozpoznać polskiego tekstu (fikstura ``wymaga_ocr_pol``).
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from gnb.images import odczyt_strony
from gnb.images.ocena_ocr import (
    OCENA_OCR_NISKA_PEWNOSC,
    OCENA_OCR_POPRAWNA,
    OCENA_OCR_PUSTA,
    ocen_ocr,
)
from gnb.images.odczyt_strony import PROG_PEWNOSCI_BEZ_PONOWIENIA, odczytaj_strone
from gnb.images.przygotowanie import powieksz_jesli_maly, przygotuj_do_ocr, wykryj_kat_przechylenia
from gnb.images.tesseract import UstawieniaOcr, WynikOcrZPewnoscia, _odczytaj_tsv

KROJ = (
    Path(__file__).resolve().parent.parent.parent / "gnb" / "images" / "czcionki" / "DejaVuSans.ttf"
)

_NAGLOWEK_TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def _wiersz_slowa(blok: int, akapit: int, linia: int, numer: int, pewnosc: str, tekst: str) -> str:
    return f"5\t1\t{blok}\t{akapit}\t{linia}\t{numer}\t0\t0\t10\t10\t{pewnosc}\t{tekst}"


def test_tsv_sklada_tekst_z_wierszami_i_akapitami_oraz_liczy_srednia_pewnosc() -> None:
    tsv = "\n".join(
        [
            _NAGLOWEK_TSV,
            "1\t1\t0\t0\t0\t0\t0\t0\t100\t100\t-1\t",
            _wiersz_slowa(1, 1, 1, 1, "90.0", "Ala"),
            _wiersz_slowa(1, 1, 1, 2, "70.0", "ma"),
            _wiersz_slowa(1, 1, 2, 1, "80.0", "kota"),
            _wiersz_slowa(2, 1, 1, 1, "60.0", "Nowy"),
            _wiersz_slowa(2, 1, 1, 2, "-1", "pominięty"),
            _wiersz_slowa(2, 1, 1, 3, "50.0", " "),
        ]
    )
    wynik = _odczytaj_tsv(tsv)
    assert wynik.tekst == "Ala ma\nkota\n\nNowy"
    assert wynik.liczba_slow == 4
    assert wynik.srednia_pewnosc == pytest.approx(75.0)


def test_pusty_tsv_daje_zerowa_pewnosc_i_pusty_tekst() -> None:
    wynik = _odczytaj_tsv(_NAGLOWEK_TSV + "\n")
    assert wynik == WynikOcrZPewnoscia(tekst="", srednia_pewnosc=0.0, liczba_slow=0)


def test_niska_pewnosc_czytelnego_tekstu_daje_ocene_nieczytelna() -> None:
    tekst = "Sąd Rejonowy wydał wyrok w sprawie o zapłatę w dniu wczorajszym"
    ocena = ocen_ocr(tekst, srednia_pewnosc=42.0, prog_pewnosci=50.0)
    assert ocena.ocena == OCENA_OCR_NISKA_PEWNOSC
    assert ocena.czy_nieczytelne
    assert "42" in ocena.powody[0]
    assert ocen_ocr(tekst, srednia_pewnosc=88.0, prog_pewnosci=50.0).ocena == OCENA_OCR_POPRAWNA
    # Bez pewności ocena zachowuje się jak dotąd.
    assert ocen_ocr(tekst).ocena == OCENA_OCR_POPRAWNA
    assert ocen_ocr("", srednia_pewnosc=90.0).ocena == OCENA_OCR_PUSTA
    # Próg zero wyłącza ocenę po pewności.
    assert ocen_ocr(tekst, srednia_pewnosc=1.0, prog_pewnosci=0.0).ocena == OCENA_OCR_POPRAWNA


def _strona_druku(rozmiar_czcionki: int = 34, wierszy: int = 24, ziarno: int = 7) -> Image.Image:
    losowy = random.Random(ziarno)
    slowa = "sąd wyrok wniosek pozwany powód świadek rozprawa termin odpis dowód".split()
    obraz = Image.new("L", (1700, 1500), 255)
    rysunek = ImageDraw.Draw(obraz)
    czcionka = ImageFont.truetype(str(KROJ), rozmiar_czcionki)
    for indeks in range(wierszy):
        wiersz = " ".join(losowy.choices(slowa, k=9))
        rysunek.text((100, 80 + indeks * (rozmiar_czcionki + 30)), wiersz, font=czcionka, fill=0)
    return obraz


def test_wykrycie_kata_przechylenia_proponuje_obrot_przywracajacy_poziom() -> None:
    prosta = _strona_druku()
    przechylona = prosta.rotate(-3, expand=True, fillcolor=255, resample=Image.Resampling.BICUBIC)
    kat = wykryj_kat_przechylenia(przechylona)
    assert kat == pytest.approx(3.0, abs=1.0)
    assert wykryj_kat_przechylenia(prosta) == 0.0
    assert wykryj_kat_przechylenia(Image.new("L", (800, 800), 255)) == 0.0


def test_przygotowanie_powiększa_maly_obraz_i_zwraca_odcienie_szarosci() -> None:
    maly = Image.new("RGB", (600, 400), "white")
    wynik = przygotuj_do_ocr(maly)
    assert wynik.mode == "L"
    assert max(wynik.size) >= 1500
    duzy = Image.new("L", (2400, 1800), 255)
    assert powieksz_jesli_maly(duzy) is duzy


def _strona_prosta_wedlug_osd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Podstawia wykrywanie orientacji tak, żeby wskazywało stronę prostą."""
    monkeypatch.setattr(odczyt_strony, "dane_orientacji_dostepne", lambda *_a: True)
    monkeypatch.setattr(odczyt_strony, "wykryj_obrot_osd", lambda *_a, **_n: 0)


def test_drugi_odczyt_z_przygotowanego_obrazu_tylko_gdy_pierwszy_jest_slaby(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _strona_prosta_wedlug_osd(monkeypatch)
    wywolania: list[int] = []
    wyniki = iter(
        [
            # Pierwszy odczyt, trzy pozostałe obroty (OSD wskazało 0) i odczyt przygotowany.
            WynikOcrZPewnoscia("slaby", 30.0, 10),
            WynikOcrZPewnoscia("slaby", 30.0, 10),
            WynikOcrZPewnoscia("slaby", 30.0, 10),
            WynikOcrZPewnoscia("slaby", 30.0, 10),
            WynikOcrZPewnoscia("lepszy", 80.0, 40),
        ]
    )

    def udawany_odczyt(*_argumenty, **_nazwane) -> WynikOcrZPewnoscia:
        wywolania.append(1)
        return next(wyniki)

    monkeypatch.setattr(odczyt_strony, "rozpoznaj_z_pewnoscia", udawany_odczyt)
    obraz = Image.new("L", (300, 300), 255)
    ustawienia = UstawieniaOcr()

    wynik = odczytaj_strone(obraz, ustawienia, przygotowanie_wlaczone=True)
    assert wynik.tekst == "lepszy"
    assert len(wywolania) == 5

    # Wyłączone przygotowanie: pierwszy odczyt i trzy obroty, bez odczytu przygotowanego.
    wywolania.clear()
    wyniki = iter([WynikOcrZPewnoscia("slaby", 30.0, 10)] * 4)
    assert odczytaj_strone(obraz, ustawienia, przygotowanie_wlaczone=False).tekst == "slaby"
    assert len(wywolania) == 4

    # Dobry pierwszy odczyt nie wywołuje drugiego.
    wywolania.clear()
    wyniki = iter([WynikOcrZPewnoscia("dobry", PROG_PEWNOSCI_BEZ_PONOWIENIA, 10)])
    assert odczytaj_strone(obraz, ustawienia, przygotowanie_wlaczone=True).tekst == "dobry"
    assert len(wywolania) == 1


def test_gorszy_drugi_odczyt_nie_zastepuje_pierwszego(monkeypatch: pytest.MonkeyPatch) -> None:
    _strona_prosta_wedlug_osd(monkeypatch)
    wyniki = iter(
        [
            WynikOcrZPewnoscia("pierwszy", 60.0, 100),
            *[WynikOcrZPewnoscia("obrot", 50.0, 5)] * 3,
            WynikOcrZPewnoscia("drugi", 70.0, 5),
        ]
    )
    monkeypatch.setattr(odczyt_strony, "rozpoznaj_z_pewnoscia", lambda *_a, **_n: next(wyniki))
    wynik = odczytaj_strone(
        Image.new("L", (300, 300), 255), UstawieniaOcr(), przygotowanie_wlaczone=True
    )
    assert wynik.tekst == "pierwszy"


def test_odczyt_z_pewnoscia_rozpoznaje_czysty_druk_wysoko(wymaga_ocr_pol: None) -> None:
    wynik = odczytaj_strone(
        _strona_druku(), UstawieniaOcr(jezyk="pol"), przygotowanie_wlaczone=True
    )
    assert wynik.liczba_slow > 100
    assert wynik.srednia_pewnosc > 80


def test_przechylona_strona_jest_odczytana_dzieki_przygotowaniu(wymaga_ocr_pol: None) -> None:
    przechylona = _strona_druku().rotate(
        -4, expand=True, fillcolor=255, resample=Image.Resampling.BICUBIC
    )
    ustawienia = UstawieniaOcr(jezyk="pol")
    bez = odczytaj_strone(przechylona, ustawienia, przygotowanie_wlaczone=False)
    z = odczytaj_strone(przechylona, ustawienia, przygotowanie_wlaczone=True)
    assert z.liczba_slow > 100
    assert z.srednia_pewnosc > 80
    assert z.srednia_pewnosc * z.liczba_slow > 3 * bez.srednia_pewnosc * bez.liczba_slow
