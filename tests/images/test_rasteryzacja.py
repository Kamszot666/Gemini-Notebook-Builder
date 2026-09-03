"""Testy rasteryzacji stron PDF do obrazów."""

from __future__ import annotations

import io

import pytest
from PIL import Image
from pomoce import pdf_ze_stron_z_tekstem

from gnb.core.wyjatki import BladTrwaly
from gnb.images.rasteryzacja import liczba_stron, rasteryzuj_strony


def test_liczba_stron_liczy_strony_skanu() -> None:
    pdf = pdf_ze_stron_z_tekstem([["A"], ["B"], ["C"]])
    assert liczba_stron(pdf) == 3


def test_rasteryzuj_strony_zwraca_obraz_na_strone_w_kolejnosci() -> None:
    pdf = pdf_ze_stron_z_tekstem([["PIERWSZA"], ["DRUGA"]])

    strony = rasteryzuj_strony(pdf, rozdzielczosc_dpi=150)

    assert len(strony) == 2
    for png in strony:
        obraz = Image.open(io.BytesIO(png))
        assert obraz.format == "PNG"
        assert obraz.width > 0 and obraz.height > 0


def test_wyzsza_rozdzielczosc_daje_wiekszy_obraz() -> None:
    pdf = pdf_ze_stron_z_tekstem([["JEDNA STRONA"]])

    maly = Image.open(io.BytesIO(rasteryzuj_strony(pdf, rozdzielczosc_dpi=72)[0]))
    duzy = Image.open(io.BytesIO(rasteryzuj_strony(pdf, rozdzielczosc_dpi=200)[0]))

    assert duzy.width > maly.width


def test_rasteryzuj_strony_zglasza_postep_po_kazdej_stronie() -> None:
    pdf = pdf_ze_stron_z_tekstem([["A"], ["B"], ["C"]])
    postep: list[tuple[int, int]] = []

    rasteryzuj_strony(pdf, rozdzielczosc_dpi=100, przy_postepie=lambda a, b: postep.append((a, b)))

    assert postep == [(1, 3), (2, 3), (3, 3)]


def test_uszkodzony_pdf_konczy_sie_bledem_trwalym() -> None:
    with pytest.raises(BladTrwaly):
        rasteryzuj_strony(b"%PDF-1.4 uciety naglowek bez reszty", rozdzielczosc_dpi=100)
