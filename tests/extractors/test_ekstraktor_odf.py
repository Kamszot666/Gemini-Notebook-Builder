"""Testy ekstraktorów ODT, ODS i ODP na prawdziwych plikach z LibreOffice i na plikach ręcznych.

Pliki `dokument.odt`, `arkusz.ods` i `prezentacja.odp` w `tests/dane/formaty`
powstały z ręcznie napisanych plików płaskiego XML (`*.fodt`, `*.fods`, `*.fodp`)
przez konwersję programem LibreOffice, więc to prawdziwe pliki tego formatu, a nie
zapis zgodny z tym, jak czyta je testowany kod. Przypadki, których LibreOffice nie
tworzy z tak prostego źródła, na przykład ramka slajdu z klasą tytułu, testują pliki
budowane ręcznie w samym teście.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.plik_odf import EkstraktorOdp, EkstraktorOds, EkstraktorOdt

DANE = Path(__file__).resolve().parents[1] / "dane" / "formaty"

_NAGLOWEK_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
    'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
    'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" '
    'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
    'office:version="1.3">'
)


def _odf(tresc: str, *, dodatkowe: dict[str, bytes] | None = None) -> bytes:
    """Buduje minimalne archiwum ODF z podanym ciałem dokumentu."""
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        archiwum.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        archiwum.writestr("content.xml", _NAGLOWEK_XML + tresc + "</office:document-content>")
        for nazwa, dane in (dodatkowe or {}).items():
            archiwum.writestr(nazwa, dane)
    return bufor.getvalue()


def _odt(cialo: str, **argumenty: dict[str, bytes]) -> bytes:
    return _odf(f"<office:body><office:text>{cialo}</office:text></office:body>", **argumenty)


# --- ODT: prawdziwy plik ---------------------------------------------------------


def test_odt_zachowuje_naglowki_listy_tabele_i_przypisy() -> None:
    dokument = EkstraktorOdt().wyekstrahuj("id", (DANE / "dokument.odt").read_bytes())

    assert dokument.tytul == "Raport o żółwiach"
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.WYSOKI
    assert dokument.metadane == {
        "autor": "Anna Nowak",
        "data_publikacji": "2026-03-14",
        "data_aktualizacji": "2026-04-02",
    }
    tekst = dokument.tekst
    assert "# Wstęp do żółwi" in tekst
    assert "## Gatunki" in tekst
    assert "Zażółć gęślą jaźń. Koniec zdania." in tekst
    assert "Przypis: Przypis o pancerzu żółwia." in tekst
    assert "- żółw grecki" in tekst
    assert "- podgatunek zagnieżdżony" in tekst
    assert "1. pierwszy krok\n2. drugi krok" in tekst
    assert "| Gatunek | Długość | Waga |" in tekst
    assert "| grecki | 25 cm | 2 kg |" in tekst
    assert tekst.rstrip().endswith("Ostatni akapit po tabeli.")
    assert dokument.ostrzezenia == []


def test_odt_lista_wypunktowana_i_numerowana_sa_rozroznione_po_stylu() -> None:
    dokument = EkstraktorOdt().wyekstrahuj("id", (DANE / "dokument.odt").read_bytes())

    poziomy = [blok.poziom for blok in dokument.bloki if blok.rodzaj.value == "lista"]
    assert poziomy == [0, 1]


# --- ODT: pliki ręczne --------------------------------------------------------------


def test_odt_pomija_spis_tresci_i_zmiany_sledzone() -> None:
    plik = _odt(
        "<text:table-of-content><text:index-body><text:p>Spis: rozdział 1</text:p>"
        "</text:index-body></text:table-of-content>"
        "<text:tracked-changes><text:changed-region><text:deletion><text:p>USUNIĘTY TEKST"
        "</text:p></text:deletion></text:changed-region></text:tracked-changes>"
        "<text:p>Treść właściwa.</text:p>"
    )

    tekst = EkstraktorOdt().wyekstrahuj("id", plik).tekst

    assert tekst == "Treść właściwa."


def test_odt_rozwija_sekcje_i_ramki_tekstowe() -> None:
    plik = _odt(
        '<text:section text:name="s"><text:p>W sekcji.</text:p></text:section>'
        "<draw:frame><draw:text-box><text:p>W ramce.</text:p></draw:text-box></draw:frame>"
    )

    tekst = EkstraktorOdt().wyekstrahuj("id", plik).tekst

    assert "W sekcji." in tekst and "W ramce." in tekst


def test_odt_obraz_i_obiekt_trafiaja_do_ostrzezen() -> None:
    plik = _odt(
        "<text:p>Tekst.<draw:frame><draw:image/></draw:frame></text:p>"
        "<draw:frame><draw:object/></draw:frame>"
    )

    ostrzezenia = EkstraktorOdt().wyekstrahuj("id", plik).ostrzezenia

    assert any("obrazy (1)" in ostrzezenie for ostrzezenie in ostrzezenia)
    assert any("obiekty osadzone" in ostrzezenie for ostrzezenie in ostrzezenia)


def test_odt_bez_tytulu_w_metadanych_bierze_pierwszy_naglowek() -> None:
    plik = _odt('<text:h text:outline-level="2">Pierwszy nagłówek</text:h><text:p>x</text:p>')

    assert EkstraktorOdt().wyekstrahuj("id", plik).tytul == "Pierwszy nagłówek"


def test_odt_zaszyfrowany_jest_odrzucany_z_czytelnym_komunikatem() -> None:
    manifest = (
        b'<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
        b'<manifest:file-entry manifest:full-path="content.xml">'
        b"<manifest:encryption-data/></manifest:file-entry></manifest:manifest>"
    )
    plik = _odt("<text:p>x</text:p>", dodatkowe={"META-INF/manifest.xml": manifest})

    with pytest.raises(BladTrwaly, match="zaszyfrowany hasłem"):
        EkstraktorOdt().wyekstrahuj("id", plik)


def test_odt_bez_content_xml_i_plik_niebedacy_zip_zglaszaja_blad_trwaly() -> None:
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        archiwum.writestr("inny.txt", "x")

    with pytest.raises(BladTrwaly, match="content.xml"):
        EkstraktorOdt().wyekstrahuj("id", bufor.getvalue())
    with pytest.raises(BladTrwaly, match="nie jest poprawnym dokumentem ODT"):
        EkstraktorOdt().wyekstrahuj("id", b"nie zip")


def test_odt_z_encjami_xml_jest_odrzucany() -> None:
    plik = _odf(
        '<!DOCTYPE x [<!ENTITY a "aaaa">]><office:body><office:text>'
        "<text:p>&a;</text:p></office:text></office:body>"
    )
    # Deklaracja typu dokumentu stoi po znaczniku głównym, więc dopisujemy ją
    # do treści wpisu wprost, tak jak zrobiłby to złośliwy plik.
    bufor = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(plik)) as zrodlo, zipfile.ZipFile(bufor, "w") as cel:
        for wpis in zrodlo.namelist():
            dane = zrodlo.read(wpis)
            if wpis == "content.xml":
                dane = dane.replace(
                    b"<office:document-content", b'<!ENTITY a "b"><office:document-content', 1
                )
            cel.writestr(wpis, dane)

    with pytest.raises(BladTrwaly, match="niebezpieczny"):
        EkstraktorOdt().wyekstrahuj("id", bufor.getvalue())


# --- ODS ------------------------------------------------------------------------------


def test_ods_zapisuje_kazdy_arkusz_jako_naglowek_i_tabele_z_widocznym_formatem() -> None:
    dokument = EkstraktorOds().wyekstrahuj("id", (DANE / "arkusz.ods").read_bytes())

    tekst = dokument.tekst
    assert "## Arkusz: Sprzedaż" in tekst
    assert "| Produkt | Cena | Data |" in tekst
    # Komórka jest zapisana tak, jak widzi ją użytkownik, z walutą, a nie jako surowa liczba.
    assert "| Żółta ścierka | 1 234,50 zł | 2026-05-07 |" in tekst
    assert "## Arkusz: Drugi" in tekst
    assert "| a | 3 |" in tekst


def test_ods_rozwija_powtorzenia_z_ograniczeniem_i_pomija_puste_wiersze() -> None:
    plik = _odf(
        "<office:body><office:spreadsheet>"
        '<table:table table:name="A">'
        "<table:table-row>"
        "<table:table-cell><text:p>x</text:p></table:table-cell>"
        '<table:table-cell table:number-columns-repeated="1000000"/>'
        "</table:table-row>"
        '<table:table-row table:number-rows-repeated="1048000">'
        '<table:table-cell table:number-columns-repeated="1024"/></table:table-row>'
        '<table:table-row table:number-rows-repeated="2">'
        "<table:table-cell><text:p>y</text:p></table:table-cell></table:table-row>"
        "</table:table></office:spreadsheet></office:body>"
    )

    dokument = EkstraktorOds().wyekstrahuj("id", plik)

    tabela = next(blok for blok in dokument.bloki if blok.rodzaj.value == "tabela")
    assert tabela.tresc.split("\n") == ["x", "y", "y"]


def test_ods_bez_tresci_daje_pusty_dokument() -> None:
    plik = _odf(
        "<office:body><office:spreadsheet>"
        '<table:table table:name="Pusty"><table:table-row><table:table-cell/></table:table-row>'
        "</table:table></office:spreadsheet></office:body>"
    )

    dokument = EkstraktorOds().wyekstrahuj("id", plik)

    assert dokument.tekst == ""
    assert dokument.bloki == []


# --- ODP -------------------------------------------------------------------------------


def test_odp_zapisuje_slajdy_z_trescia_i_notatkami_mowcy() -> None:
    dokument = EkstraktorOdp().wyekstrahuj("id", (DANE / "prezentacja.odp").read_bytes())

    tekst = dokument.tekst
    assert "## Slajd 1" in tekst
    assert "- Pancerz chroni żółwia" in tekst
    assert "Notatki mówcy: Powiedz o pancerzu." in tekst
    assert "## Slajd 2" in tekst
    assert "Dziękuję za uwagę." in tekst


def test_odp_z_ramka_tytulowa_uzywa_tytulu_w_naglowku_slajdu_i_pomija_stopke() -> None:
    plik = _odf(
        "<office:body><office:presentation>"
        '<draw:page draw:name="p1">'
        '<draw:frame presentation:class="title"><draw:text-box>'
        "<text:p>Tytuł slajdu</text:p></draw:text-box></draw:frame>"
        '<draw:frame presentation:class="outline"><draw:text-box>'
        "<text:p>Treść slajdu</text:p></draw:text-box></draw:frame>"
        '<draw:frame presentation:class="page-number"><draw:text-box>'
        "<text:p>7</text:p></draw:text-box></draw:frame>"
        '<draw:frame presentation:class="footer"><draw:text-box>'
        "<text:p>Stopka firmowa</text:p></draw:text-box></draw:frame>"
        "<draw:frame><draw:image/></draw:frame>"
        "</draw:page></office:presentation></office:body>"
    )

    dokument = EkstraktorOdp().wyekstrahuj("id", plik)

    assert dokument.tekst.startswith("## Slajd 1: Tytuł slajdu")
    assert "Treść slajdu" in dokument.tekst
    assert "Stopka firmowa" not in dokument.tekst
    assert "7" not in dokument.tekst.replace("Slajd 1", "")
    assert any("obrazy (1)" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)


def test_odp_tabela_na_slajdzie_jest_tabela() -> None:
    plik = _odf(
        "<office:body><office:presentation><draw:page>"
        "<draw:frame><table:table>"
        "<table:table-row><table:table-cell><text:p>A</text:p></table:table-cell>"
        "<table:table-cell><text:p>B</text:p></table:table-cell></table:table-row>"
        "<table:table-row><table:table-cell><text:p>1</text:p></table:table-cell>"
        "<table:table-cell><text:p>2</text:p></table:table-cell></table:table-row>"
        "</table:table></draw:frame></draw:page></office:presentation></office:body>"
    )

    assert "| A | B |" in EkstraktorOdp().wyekstrahuj("id", plik).tekst


# --- obsługiwanie formatów -------------------------------------------------------------


@pytest.mark.parametrize(
    ("ekstraktor", "format_zrodla"),
    [(EkstraktorOdt(), "odt"), (EkstraktorOds(), "ods"), (EkstraktorOdp(), "odp")],
)
def test_ekstraktor_obsluguje_tylko_swoj_format(ekstraktor: object, format_zrodla: str) -> None:
    obsluguje = ekstraktor.obsluguje  # type: ignore[attr-defined]

    assert obsluguje(TypZrodla.PLIK_DOKUMENT, format_zrodla)
    assert not obsluguje(TypZrodla.PLIK_DOKUMENT, "docx")
    assert not obsluguje(TypZrodla.PLIK_TEKSTOWY, format_zrodla)
