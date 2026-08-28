"""Testy ekstraktora plików PDF.

Testy wykrywania powtarzalnego nagłówka i numeru strony oraz testy błędów
kontrolowanych korzystają z gotowych plików w `tests/dane`, opisanych w
`tests/dane/README_dane_testowe.md`. Pozostałe testy budują plik PDF ręcznie,
bez zewnętrznych narzędzi, jako minimalny poprawny dokument ze stronami
zawierającymi prosty ciąg tekstu rysowany operatorem `Tj`.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.plik_pdf import EkstraktorPdf

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def _pdf_z_tekstem(*strony_tekstow: str) -> bytes:
    """Buduje minimalny, poprawny plik PDF z podanym tekstem na każdej stronie."""
    obiekty: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    liczba_stron = len(strony_tekstow)
    dzieci = " ".join(f"{3 + i} 0 R" for i in range(liczba_stron))
    obiekty.append(f"<< /Type /Pages /Kids [{dzieci}] /Count {liczba_stron} >>".encode())

    numer_fontu = 3 + liczba_stron
    for i in range(liczba_stron):
        obiekty.append(
            (
                f"<< /Type /Page /Parent 2 0 R "
                f"/Resources << /Font << /F1 {numer_fontu} 0 R >> >> "
                f"/MediaBox [0 0 300 300] /Contents {numer_fontu + 1 + i} 0 R >>"
            ).encode()
        )
    obiekty.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for tekst in strony_tekstow:
        tresc = f"BT /F1 12 Tf 20 150 Td ({tekst}) Tj ET".encode("latin-1")
        obiekty.append(f"<< /Length {len(tresc)} >>\nstream\n".encode() + tresc + b"\nendstream")

    bufor = io.BytesIO()
    bufor.write(b"%PDF-1.4\n")
    przesuniecia = []
    for numer, obiekt in enumerate(obiekty, start=1):
        przesuniecia.append(bufor.tell())
        bufor.write(f"{numer} 0 obj\n".encode())
        bufor.write(obiekt)
        bufor.write(b"\nendobj\n")

    przesuniecie_xref = bufor.tell()
    liczba_wpisow = len(obiekty) + 1
    bufor.write(f"xref\n0 {liczba_wpisow}\n".encode())
    bufor.write(b"0000000000 65535 f \n")
    for przesuniecie in przesuniecia:
        bufor.write(f"{przesuniecie:010d} 00000 n \n".encode())

    bufor.write(
        f"trailer\n<< /Size {liczba_wpisow} /Root 1 0 R >>\n"
        f"startxref\n{przesuniecie_xref}\n%%EOF".encode()
    )
    return bufor.getvalue()


def test_tekst_z_dwoch_stron_jest_polaczony() -> None:
    dane = _pdf_z_tekstem("Pierwsza strona", "Druga strona")
    dokument = EkstraktorPdf().wyekstrahuj("plik_dokument-1", dane)

    assert "Pierwsza strona" in dokument.tekst
    assert "Druga strona" in dokument.tekst
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.bloki == []
    assert dokument.ostrzezenia == []


def test_zaszyfrowany_plik_konczy_sie_bledem_trwalym() -> None:
    zapis = PdfWriter()
    zapis.add_blank_page(width=200, height=200)
    zapis.encrypt("haslo123")
    bufor = io.BytesIO()
    zapis.write(bufor)

    with pytest.raises(BladTrwaly, match="zaszyfrowany"):
        EkstraktorPdf().wyekstrahuj("plik_dokument-2", bufor.getvalue())


def test_uszkodzony_plik_konczy_sie_bledem_trwalym() -> None:
    with pytest.raises(BladTrwaly, match="uszkodzony"):
        EkstraktorPdf().wyekstrahuj("plik_dokument-3", b"to nie jest plik PDF")


def test_pdf_bez_warstwy_tekstowej_daje_ostrzezenie() -> None:
    zapis = PdfWriter()
    zapis.add_blank_page(width=200, height=200)
    bufor = io.BytesIO()
    zapis.write(bufor)

    dokument = EkstraktorPdf().wyekstrahuj("plik_dokument-4", bufor.getvalue())

    assert dokument.tekst == ""
    assert dokument.ostrzezenia


def test_obsluguje_wylacznie_format_pdf() -> None:
    ekstraktor = EkstraktorPdf()
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "pdf") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "docx") is False


def test_powtarzalny_naglowek_i_numer_strony_znikaja_bez_utraty_tresci() -> None:
    dane = (KATALOG_DANYCH / "pdf_tekstowy.pdf").read_bytes()
    dokument = EkstraktorPdf().wyekstrahuj("plik_dokument-6", dane)

    assert "Nagłówek powtarzany na każdej stronie" not in dokument.tekst
    assert "Strona 1" not in dokument.tekst
    assert "Strona 2" not in dokument.tekst
    assert "Strona 3" not in dokument.tekst
    assert dokument.tekst.count("Trzecim błędem jest utrata informacji") == 3
    assert "Drugim częstym błędem jest usuwanie materiałów" in dokument.tekst


def test_skan_bez_warstwy_tekstowej_daje_ostrzezenie() -> None:
    dane = (KATALOG_DANYCH / "pdf_skan.pdf").read_bytes()
    dokument = EkstraktorPdf().wyekstrahuj("plik_dokument-7", dane)

    assert dokument.tekst == ""
    assert dokument.ostrzezenia


def test_plik_uszkodzony_z_danych_testowych_konczy_sie_bledem_trwalym() -> None:
    dane = (KATALOG_DANYCH / "pdf_uszkodzony.pdf").read_bytes()

    with pytest.raises(BladTrwaly, match="uszkodzony"):
        EkstraktorPdf().wyekstrahuj("plik_dokument-8", dane)
