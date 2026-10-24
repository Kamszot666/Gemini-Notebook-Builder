"""Testy składania plików ze skanami kartek: nagłówki, kolejność i escapowanie."""

from __future__ import annotations

from gnb.core.nazwy import klucz_porzadku_naturalnego
from gnb.output.skany import (
    SkanDoPliku,
    nazwa_pliku_skanu,
    polacz_tresc_skanu,
    rozdziel_tresc_skanu,
    zloz_skany_markdown,
    zloz_skany_txt,
)

_NAGLOWEK = "Typ źródła: obraz\nPlik: {nazwa}\nIdentyfikator źródła: obraz-abc"


def _skan(nazwa: str, numer: int, ocr: str, dopiski: str = "") -> SkanDoPliku:
    return SkanDoPliku(
        naglowek_metadanych=_NAGLOWEK.format(nazwa=nazwa),
        numer=numer,
        ocena_ocr="poprawna",
        srednia_pewnosc="91.5",
        ma_dopiski=bool(dopiski),
        tresc_ocr=ocr,
        dopiski=dopiski,
    )


def test_sortowanie_naturalne_stawia_2_przed_10_i_ignoruje_wielkosc_liter() -> None:
    nazwy = ["IMG_10.jpg", "img_2.jpg", "IMG_1.jpg", "IMG_100.jpg", "IMG_20.jpg"]
    assert sorted(nazwy, key=klucz_porzadku_naturalnego) == [
        "IMG_1.jpg",
        "img_2.jpg",
        "IMG_10.jpg",
        "IMG_20.jpg",
        "IMG_100.jpg",
    ]
    # Nazwa zaczynająca się cyfrą i nazwa zaczynająca się literą nie powodują błędu porównania.
    assert sorted(["a1", "1a", "10a", "2a"], key=klucz_porzadku_naturalnego) == [
        "1a",
        "2a",
        "10a",
        "a1",
    ]


def test_tresc_ocr_i_dopiski_rozdzielaja_sie_po_polaczeniu() -> None:
    polaczone = polacz_tresc_skanu("Odczyt OCR.", "Dopisek.")
    assert rozdziel_tresc_skanu(polaczone) == ("Odczyt OCR.", "Dopisek.")
    assert polacz_tresc_skanu("Odczyt OCR.", "") == "Odczyt OCR."
    assert rozdziel_tresc_skanu("Odczyt OCR.") == ("Odczyt OCR.", "")


def test_nazwa_pliku_skanu_pochodzi_z_pola_plik_naglowka() -> None:
    assert nazwa_pliku_skanu(_NAGLOWEK.format(nazwa="017.jpg")) == "017.jpg"
    assert nazwa_pliku_skanu("Typ źródła: obraz") == ""


def test_markdown_ma_sekcje_z_nazwa_pliku_metadanymi_i_osobnymi_dopiskami() -> None:
    tresc = zloz_skany_markdown(
        [
            _skan("017.jpg", 1, "# To nie jest nagłówek\n\n- ani lista", "Dopisek ołówkiem."),
            _skan("018.jpg", 2, "Drugi skan."),
        ],
        tytul_pliku="Grupa „akta”",
    )
    wiersze = tresc.split("\n")
    assert wiersze[0] == "# Grupa „akta”"
    assert "## 017.jpg" in wiersze
    assert "## 018.jpg" in wiersze
    assert "- Numer skanu w grupie: 1" in wiersze
    assert "- Ocena OCR: poprawna" in wiersze
    assert "- Średnia pewność słów: 91.5" in wiersze
    assert "- Dopiski odręczne: tak" in wiersze
    assert "- Dopiski odręczne: nie" in wiersze
    assert "### Dopiski odręczne przepisane przez osobę widzącą" in wiersze
    assert tresc.count("### ") == 1
    # Składnia w odczycie OCR jest escapowana, więc nie powstaje fałszywy nagłówek ani lista.
    assert "# To nie jest nagłówek" not in wiersze
    assert "\\# To nie jest nagłówek" in wiersze
    # Dopiski leżą pod wynikiem OCR, a nie przed nim.
    assert tresc.index("To nie jest") < tresc.index("Dopisek ołówkiem.")


def test_txt_ma_metadane_i_dopiski_pod_odczytem() -> None:
    tresc = zloz_skany_txt([_skan("017.jpg", 1, "Odczyt.", "Dopisek.")], oznaczenie_pliku="Grupa")
    assert "Plik: 017.jpg" in tresc
    assert "Numer skanu w grupie: 1" in tresc
    assert "Dopiski odręczne: tak" in tresc
    assert tresc.index("Odczyt.") < tresc.index("Dopiski odręczne przepisane przez osobę widzącą:")
    assert tresc.index("Dopiski odręczne przepisane przez osobę widzącą:") < tresc.index("Dopisek.")
