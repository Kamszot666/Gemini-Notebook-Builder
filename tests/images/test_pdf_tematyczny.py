"""Testy generowania tematycznego pliku PDF z obrazami i opisami."""

from __future__ import annotations

import io
from collections.abc import Callable

from pypdf import PdfReader

from gnb.images.pdf_tematyczny import ObrazDoPdf, UstawieniaPdf, zbuduj_pdf


def _czytaj(pdf_bajty: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(pdf_bajty))


def test_pdf_ma_strone_na_obraz_i_zaczyna_sie_od_sygnatury(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obrazy = [
        ObrazDoPdf(
            naglowek="Identyfikator źródła: obraz-1\nTyp: obraz",
            tresc="Opis pierwszego obrazu.\n\nRozpoznany tekst (OCR):\nPierwszy",
            obraz_png=obraz_z_tekstem(["PIERWSZY"]),
        ),
        ObrazDoPdf(
            naglowek="Identyfikator źródła: obraz-2\nTyp: obraz",
            tresc="Opis drugiego obrazu.\n\nRozpoznany tekst (OCR):\nDrugi",
            obraz_png=obraz_z_tekstem(["DRUGI"]),
        ),
    ]

    pdf = zbuduj_pdf("Grupa testowa", obrazy)

    assert pdf.startswith(b"%PDF")
    assert len(_czytaj(pdf).pages) == 2


def test_tekst_opisu_i_naglowka_trafia_do_pdf(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obrazy = [
        ObrazDoPdf(
            naglowek="Identyfikator źródła: obraz-9",
            tresc="Zażółć gęślą jaźń w opisie obrazu.",
            obraz_png=obraz_z_tekstem(["x"]),
        )
    ]

    pdf = zbuduj_pdf("Grupa", obrazy)
    strona_tekst = _czytaj(pdf).pages[0].extract_text() or ""

    assert "obraz-9" in strona_tekst
    assert "Zażółć gęślą jaźń" in strona_tekst


def test_brak_bajtow_obrazu_nie_przerywa_budowania(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obrazy = [
        ObrazDoPdf(naglowek="Identyfikator źródła: obraz-0", tresc="Opis.", obraz_png=None),
        ObrazDoPdf(
            naglowek="Identyfikator źródła: obraz-1",
            tresc="Opis drugiego.",
            obraz_png=obraz_z_tekstem(["ok"]),
        ),
    ]

    pdf = zbuduj_pdf("Grupa", obrazy)
    tekst = "".join((strona.extract_text() or "") for strona in _czytaj(pdf).pages)

    assert "nie udało się osadzić" in tekst
    assert len(_czytaj(pdf).pages) == 2


def test_nizsza_jakosc_grafik_daje_mniejszy_plik(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obraz = obraz_z_tekstem(["JAKOŚĆ"], rozmiar=(1600, 1200))

    def wpis() -> list[ObrazDoPdf]:
        return [ObrazDoPdf(naglowek="n", tresc="t", obraz_png=obraz)]

    duzy = zbuduj_pdf("g", wpis(), UstawieniaPdf(jakosc_grafik=95))
    maly = zbuduj_pdf("g", wpis(), UstawieniaPdf(jakosc_grafik=30))

    assert len(maly) < len(duzy)


def test_zbyt_duzy_obraz_jest_zmniejszany(obraz_z_tekstem: Callable[..., bytes]) -> None:
    wielki = obraz_z_tekstem(["DUZY"], rozmiar=(5000, 4000))
    obrazy = [ObrazDoPdf(naglowek="n", tresc="t", obraz_png=wielki)]

    z_limitem = zbuduj_pdf("g", obrazy, UstawieniaPdf(maksymalny_wymiar_px=800))
    bez_limitu = zbuduj_pdf("g", obrazy, UstawieniaPdf(maksymalny_wymiar_px=6000))

    assert len(z_limitem) < len(bez_limitu)
