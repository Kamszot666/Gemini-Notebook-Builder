"""Testy ekstraktora PPTX na prawdziwym pliku z LibreOffice i na plikach budowanych ręcznie."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.plik_pptx import EkstraktorPptx

DANE = Path(__file__).resolve().parents[1] / "dane" / "formaty"

_NS = (
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
)
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _kształt(tekst: str, *, ph: str | None = None, punkt: str = "") -> str:
    znacznik_ph = f'<p:nvPr><p:ph type="{ph}"/></p:nvPr>' if ph else "<p:nvPr/>"
    wlasciwosci = f"<a:pPr>{punkt}</a:pPr>" if punkt else ""
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="1" name="k"/><p:cNvSpPr/>{znacznik_ph}</p:nvSpPr>'
        f"<p:txBody><a:p>{wlasciwosci}<a:r><a:t>{tekst}</a:t></a:r></a:p></p:txBody></p:sp>"
    )


def _slajd(ksztalty: str, *, ukryty: bool = False) -> str:
    pokaz = ' show="0"' if ukryty else ""
    return f"<p:sld {_NS}{pokaz}><p:cSld><p:spTree>{ksztalty}</p:spTree></p:cSld></p:sld>"


def _pptx(
    slajdy: dict[str, str],
    kolejnosc: list[str],
    *,
    notatki: dict[str, str] | None = None,
    wlasciwosci: str | None = None,
) -> bytes:
    """Buduje minimalny PPTX: `slajdy` to nazwa pliku slajdu na jego XML, `kolejnosc` to lista."""
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        identyfikatory = "".join(
            f'<p:sldId id="{256 + numer}" r:id="rId{numer + 1}"/>'
            for numer, _ in enumerate(kolejnosc)
        )
        archiwum.writestr(
            "ppt/presentation.xml",
            f"<p:presentation {_NS}><p:sldIdLst>{identyfikatory}</p:sldIdLst></p:presentation>",
        )
        relacje = "".join(
            f'<Relationship Id="rId{numer + 1}" Type="{_REL}/slide" Target="slides/{nazwa}"/>'
            for numer, nazwa in enumerate(kolejnosc)
        )
        archiwum.writestr(
            "ppt/_rels/presentation.xml.rels",
            f'<Relationships xmlns="{_REL}">{relacje}</Relationships>',
        )
        for nazwa, tresc in slajdy.items():
            archiwum.writestr(f"ppt/slides/{nazwa}", tresc)
        for nazwa, tresc in (notatki or {}).items():
            numer = nazwa.removeprefix("notesSlide").removesuffix(".xml")
            archiwum.writestr(f"ppt/notesSlides/{nazwa}", tresc)
            archiwum.writestr(
                f"ppt/slides/_rels/slide{numer}.xml.rels",
                f'<Relationships xmlns="{_REL}"><Relationship Id="rId1" '
                f'Type="{_REL}/notesSlide" Target="../notesSlides/{nazwa}"/></Relationships>',
            )
        if wlasciwosci:
            archiwum.writestr("docProps/core.xml", wlasciwosci)
    return bufor.getvalue()


def test_prawdziwy_plik_z_libreoffice_daje_slajdy_liste_i_notatki() -> None:
    dokument = EkstraktorPptx().wyekstrahuj("id", (DANE / "prezentacja.pptx").read_bytes())

    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.WYSOKI
    assert "## Slajd 1" in dokument.tekst
    assert "- Pancerz chroni żółwia" in dokument.tekst
    assert "Notatki mówcy: Powiedz o pancerzu." in dokument.tekst
    assert "## Slajd 2" in dokument.tekst
    assert "Dziękuję za uwagę." in dokument.tekst


def test_kolejnosc_slajdow_wynika_z_listy_prezentacji_a_nie_z_nazw_plikow() -> None:
    slajdy = {
        "slide1.xml": _slajd(_kształt("Pierwszy plik", ph="title")),
        "slide2.xml": _slajd(_kształt("Drugi plik", ph="title")),
    }

    dokument = EkstraktorPptx().wyekstrahuj(
        "id", _pptx(slajdy, kolejnosc=["slide2.xml", "slide1.xml"])
    )

    assert dokument.tekst.index("Slajd 1: Drugi plik") < dokument.tekst.index(
        "Slajd 2: Pierwszy plik"
    )


def test_tytul_lista_akapit_i_ksztalty_zastepcze() -> None:
    ksztalty = (
        _kształt("Tytuł slajdu", ph="title")
        + _kształt("Punkt z wzorca", ph="body")
        + _kształt("Pole tekstowe bez punktora")
        + _kształt("Jawny punkt", punkt="<a:buChar/>")
        + _kształt("Numer slajdu 3", ph="sldNum")
        + _kształt("Stopka", ph="ftr")
    )

    dokument = EkstraktorPptx().wyekstrahuj("id", _pptx({"s.xml": _slajd(ksztalty)}, ["s.xml"]))

    assert dokument.tekst.startswith("## Slajd 1: Tytuł slajdu")
    assert "- Punkt z wzorca" in dokument.tekst
    assert "Pole tekstowe bez punktora" in dokument.tekst
    assert "- Pole tekstowe" not in dokument.tekst
    assert "- Jawny punkt" in dokument.tekst
    assert "Numer slajdu" not in dokument.tekst
    assert "Stopka" not in dokument.tekst


def test_wylaczone_wypunktowanie_w_ksztalcie_zastepczym_daje_akapit() -> None:
    ksztalty = _kształt("Zwykły akapit", ph="body", punkt="<a:buNone/>")

    dokument = EkstraktorPptx().wyekstrahuj("id", _pptx({"s.xml": _slajd(ksztalty)}, ["s.xml"]))

    assert "Zwykły akapit" in dokument.tekst
    assert "- Zwykły akapit" not in dokument.tekst


def test_lista_numerowana_ma_poziom_jeden() -> None:
    ksztalty = _kształt("Krok", punkt="<a:buAutoNum/>")

    dokument = EkstraktorPptx().wyekstrahuj("id", _pptx({"s.xml": _slajd(ksztalty)}, ["s.xml"]))

    assert "1. Krok" in dokument.tekst


def test_tabela_grupa_ksztaltow_obraz_i_wykres() -> None:
    tabela = (
        "<p:graphicFrame><a:graphic><a:graphicData><a:tbl>"
        "<a:tr><a:tc><a:txBody><a:p><a:r><a:t>A</a:t></a:r></a:p></a:txBody></a:tc>"
        "<a:tc><a:txBody><a:p><a:r><a:t>B</a:t></a:r></a:p></a:txBody></a:tc></a:tr>"
        "<a:tr><a:tc><a:txBody><a:p><a:r><a:t>1</a:t></a:r></a:p></a:txBody></a:tc>"
        '<a:tc hMerge="1"><a:txBody><a:p/></a:txBody></a:tc></a:tr>'
        "</a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )
    grupa = f"<p:grpSp>{_kształt('W grupie')}</p:grpSp>"
    obraz = "<p:pic/>"
    wykres = (
        "<p:graphicFrame><a:graphic><a:graphicData>"
        '<c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart"/>'
        "</a:graphicData></a:graphic></p:graphicFrame>"
    )

    dokument = EkstraktorPptx().wyekstrahuj(
        "id", _pptx({"s.xml": _slajd(tabela + grupa + obraz + wykres)}, ["s.xml"])
    )

    assert "| A | B |" in dokument.tekst
    assert "W grupie" in dokument.tekst
    assert any("obrazy (1)" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)
    assert any("wykresy albo diagramy (1)" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)


def test_slajd_ukryty_jest_odczytany_i_oznaczony() -> None:
    dokument = EkstraktorPptx().wyekstrahuj(
        "id", _pptx({"s.xml": _slajd(_kształt("Sekret"), ukryty=True)}, ["s.xml"])
    )

    assert "## Slajd 1 (slajd ukryty)" in dokument.tekst
    assert "Sekret" in dokument.tekst


def test_notatki_mowcy_pomijaja_miniature_i_numer_strony() -> None:
    notatki = _slajd(
        _kształt("obraz", ph="sldImg") + _kształt("Powiedz to głośno", ph="body")
    ).replace("p:sld", "p:notes")
    dokument = EkstraktorPptx().wyekstrahuj(
        "id",
        _pptx(
            {"slide1.xml": _slajd(_kształt("Treść"))},
            ["slide1.xml"],
            notatki={"notesSlide1.xml": notatki},
        ),
    )

    assert "Notatki mówcy: Powiedz to głośno" in dokument.tekst
    assert "obraz" not in dokument.tekst


def test_metadane_z_wlasciwosci_dokumentu() -> None:
    wlasciwosci = (
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/'
        'core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/">'
        "<dc:title>Tytuł prezentacji</dc:title><dc:creator>Jan</dc:creator>"
        "<dcterms:created>2026-01-02T10:00:00Z</dcterms:created>"
        "<dcterms:modified>2026-02-03T10:00:00Z</dcterms:modified></cp:coreProperties>"
    )

    dokument = EkstraktorPptx().wyekstrahuj(
        "id", _pptx({"s.xml": _slajd(_kształt("x"))}, ["s.xml"], wlasciwosci=wlasciwosci)
    )

    assert dokument.tytul == "Tytuł prezentacji"
    assert dokument.metadane == {
        "autor": "Jan",
        "data_publikacji": "2026-01-02",
        "data_aktualizacji": "2026-02-03",
    }


def test_plik_niebedacy_prezentacja_zglasza_blad_trwaly() -> None:
    with pytest.raises(BladTrwaly, match="zaszyfrowana hasłem"):
        EkstraktorPptx().wyekstrahuj("id", b"to nie jest zip")
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        archiwum.writestr("inny.txt", "x")
    with pytest.raises(BladTrwaly, match="ppt/presentation.xml"):
        EkstraktorPptx().wyekstrahuj("id", bufor.getvalue())


def test_ekstraktor_pptx_obsluguje_tylko_pptx() -> None:
    ekstraktor = EkstraktorPptx()

    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "pptx")
    assert not ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "ppt")
    assert not ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "odp")
