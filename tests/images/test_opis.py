"""Testy budowania opisu merytorycznego obrazu z dostępnego materiału."""

from __future__ import annotations

from gnb.images.opis import BRAK_OPISU, MaterialDoOpisu, zbuduj_opis


def test_brak_jakiegokolwiek_materialu_daje_jawny_komunikat_o_braku() -> None:
    opis = zbuduj_opis(MaterialDoOpisu(nazwa_pliku="IMG_20240101_1200.jpg"))

    assert opis == BRAK_OPISU


def test_opisowa_nazwa_pliku_trafia_do_opisu() -> None:
    opis = zbuduj_opis(
        MaterialDoOpisu(
            nazwa_pliku="raport wykres kwartalny.png", format_obrazu="png", wymiary=(900, 600)
        )
    )

    assert "raport wykres kwartalny" in opis
    assert "PNG, 900 na 600 pikseli" in opis
    assert opis != BRAK_OPISU


def test_tekst_alternatywny_i_podpis_sa_zachowane_doslownie() -> None:
    opis = zbuduj_opis(
        MaterialDoOpisu(
            tekst_alternatywny="Schemat potoku przetwarzania",
            podpis="Rysunek 1. Kolejność etapów.",
        )
    )

    assert "Schemat potoku przetwarzania" in opis
    assert "Rysunek 1. Kolejność etapów." in opis


def test_opis_bierze_pole_opisowe_z_metadanych_obrazu() -> None:
    opis = zbuduj_opis(MaterialDoOpisu(metadane_obrazu={"opis": "Zdjęcie tablicy z notatkami"}))

    assert "Zdjęcie tablicy z notatkami" in opis


def test_opis_nie_wkleja_calego_tekstu_ocr_a_jedynie_go_odnotowuje() -> None:
    dlugi_ocr = "Pierwszy wiersz rozpoznanego tekstu.\n" + "słowo " * 200

    opis = zbuduj_opis(MaterialDoOpisu(tekst_ocr=dlugi_ocr))

    assert "Pierwszy wiersz rozpoznanego tekstu." in opis
    assert opis.count("słowo") < 50
    assert "rozpoznano" in opis


def test_sam_format_i_wymiary_bez_reszty_materialu_daje_brak_opisu() -> None:
    opis = zbuduj_opis(
        MaterialDoOpisu(nazwa_pliku="DSC_0001.jpg", format_obrazu="jpeg", wymiary=(4000, 3000))
    )

    # Format i wymiary to tylko uzupełnienie, nie opis merytoryczny.
    assert opis == BRAK_OPISU
