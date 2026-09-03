"""Testy oceny jakości tekstu rozpoznanego przez OCR."""

from __future__ import annotations

from gnb.images.ocena_ocr import (
    OCENA_OCR_PODEJRZANA,
    OCENA_OCR_POPRAWNA,
    OCENA_OCR_PUSTA,
    ocen_ocr,
)


def test_poprawny_tekst_polski_jest_oceniany_jako_poprawny() -> None:
    tekst = (
        "Wykres testowy przedstawia liczbę źródeł w kolejnych etapach "
        "przygotowania bazy wiedzy dla asystenta."
    )
    ocena = ocen_ocr(tekst)

    assert ocena.ocena == OCENA_OCR_POPRAWNA
    assert ocena.czy_wymaga_sprawdzenia is False


def test_pusty_wynik_jest_oznaczony_jako_pusty_i_wymaga_sprawdzenia() -> None:
    ocena = ocen_ocr("   \n\t  \n")

    assert ocena.ocena == OCENA_OCR_PUSTA
    assert ocena.czy_wymaga_sprawdzenia is True
    assert ocena.powody


def test_bełkot_ze_znakow_nietekstowych_jest_podejrzany() -> None:
    ocena = ocen_ocr("|]} ~~~ ▓▓▓ ¬¬ ‡‡ ╬╬ ∑∑ ##@@ ¤¤¤ ◊◊")

    assert ocena.ocena == OCENA_OCR_PODEJRZANA
    assert ocena.czy_wymaga_sprawdzenia is True


def test_ciag_slow_bez_samoglosek_jest_podejrzany() -> None:
    ocena = ocen_ocr("brtk plmn krst grzr wldk trnc szpk mmnt")

    assert ocena.ocena == OCENA_OCR_PODEJRZANA
    assert any("samogłoską" in powod for powod in ocena.powody)


def test_krotki_poprawny_napis_nie_jest_podejrzany() -> None:
    ocena = ocen_ocr("Wykres testowy")

    assert ocena.ocena == OCENA_OCR_POPRAWNA
