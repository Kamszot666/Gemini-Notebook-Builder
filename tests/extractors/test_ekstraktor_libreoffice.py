"""Testy odczytu plików DOC i PPT przez konwersję programem LibreOffice.

Większość testów podstawia konwersję gotowymi bajtami DOCX i PPTX, więc sprawdza
całą logikę adaptera bez uruchamiania programu. Testy z prawdziwym LibreOffice są
oznaczone jako wolne, bo pierwsze uruchomienie z nowym profilem trwa kilkanaście
sekund, i pomijają się, gdy programu nie ma na komputerze.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia
from gnb.extractors import libreoffice, plik_libreoffice
from gnb.extractors.libreoffice import czy_dostepny, konwertuj, znajdz_libreoffice
from gnb.extractors.plik_libreoffice import EkstraktorDoc, EkstraktorPpt

DANE = Path(__file__).resolve().parents[1] / "dane" / "formaty"


@pytest.fixture
def program_podstawiony(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Podstawia znalezienie programu, żeby testy nie zależały od instalacji LibreOffice."""
    program = tmp_path / "soffice.com"
    program.write_bytes(b"")
    monkeypatch.setattr(plik_libreoffice, "znajdz_libreoffice", lambda sciezka="": program)
    return program


def _podstaw_konwersje(monkeypatch: pytest.MonkeyPatch, wynik: bytes) -> list[tuple[str, str]]:
    wywolania: list[tuple[str, str]] = []

    def falszywa(
        program: Path, bajty: bytes, rozszerzenie: str, docelowy: str, identyfikator: str
    ) -> bytes:
        wywolania.append((rozszerzenie, docelowy))
        return wynik

    monkeypatch.setattr(plik_libreoffice, "konwertuj", falszywa)
    return wywolania


def test_doc_jest_konwertowany_na_docx_i_czytany_ekstraktorem_docx(
    monkeypatch: pytest.MonkeyPatch, program_podstawiony: Path
) -> None:
    wywolania = _podstaw_konwersje(monkeypatch, (DANE / "dokument.docx").read_bytes())

    dokument = EkstraktorDoc().wyekstrahuj("id", b"bajty pliku doc")

    assert wywolania == [("doc", "docx")]
    assert dokument.metoda_ekstrakcji == "libreoffice+docx"
    assert "Wstęp do żółwi" in dokument.tekst
    assert any(
        "po konwersji programem LibreOffice na DOCX" in ostrzezenie
        for ostrzezenie in dokument.ostrzezenia
    )


def test_ppt_jest_konwertowany_na_pptx_i_czytany_ekstraktorem_pptx(
    monkeypatch: pytest.MonkeyPatch, program_podstawiony: Path
) -> None:
    wywolania = _podstaw_konwersje(monkeypatch, (DANE / "prezentacja.pptx").read_bytes())

    dokument = EkstraktorPpt().wyekstrahuj("id", b"bajty pliku ppt")

    assert wywolania == [("ppt", "pptx")]
    assert dokument.metoda_ekstrakcji == "libreoffice+pptx"
    assert "## Slajd 1" in dokument.tekst
    assert any("na PPTX" in ostrzezenie for ostrzezenie in dokument.ostrzezenia)


def test_brak_libreoffice_zglasza_brak_narzedzia_z_komunikatem_o_zamiennikach(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(libreoffice.shutil, "which", lambda nazwa: None)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path))

    with pytest.raises(BrakNarzedzia, match="DOCX albo PPTX"):
        EkstraktorDoc().wyekstrahuj("id", b"x")
    assert not czy_dostepny()


def test_ustawienie_wskazujace_nieistniejacy_plik_daje_brak_narzedzia() -> None:
    with pytest.raises(BrakNarzedzia, match="sciezka_libreoffice"):
        znajdz_libreoffice("C:/nie/ma/takiego/soffice.com")


def test_znajdz_libreoffice_uzywa_sciezki_z_konfiguracji_i_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    plik = tmp_path / "soffice.com"
    plik.write_bytes(b"")
    assert znajdz_libreoffice(str(plik)) == plik

    monkeypatch.setattr(
        libreoffice.shutil, "which", lambda nazwa: str(plik) if nazwa == "soffice.com" else None
    )
    assert znajdz_libreoffice() == plik


def test_konwersja_z_bledem_programu_zglasza_blad_trwaly(tmp_path: Path) -> None:
    # Interpreter Pythona przyjmuje role programu: odrzuca nieznane opcje i kończy się kodem
    # niezerowym, tak jak LibreOffice, który nie zdołał odczytać pliku.
    with pytest.raises(BladTrwaly, match="nie zdołał odczytać pliku"):
        konwertuj(Path(sys.executable), b"x", "doc", "docx", "id")


def test_konwersja_ponad_limit_czasu_zglasza_blad_trwaly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def zawiesz(*argumenty: object, **opcje: object) -> None:
        raise subprocess.TimeoutExpired(cmd="soffice", timeout=1)

    monkeypatch.setattr(libreoffice.subprocess, "run", zawiesz)

    with pytest.raises(BladTrwaly, match="została przerwana"):
        konwertuj(tmp_path / "soffice.com", b"x", "doc", "docx", "id")


def test_konwersja_nieuruchamialnego_programu_zglasza_blad_trwaly(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="Nie udało się uruchomić"):
        konwertuj(tmp_path / "nie_ma.exe", b"x", "doc", "docx", "id")


@pytest.mark.parametrize(
    ("ekstraktor", "format_zrodla"), [(EkstraktorDoc(), "doc"), (EkstraktorPpt(), "ppt")]
)
def test_ekstraktory_obsluguja_tylko_swoj_format(ekstraktor: object, format_zrodla: str) -> None:
    obsluguje = ekstraktor.obsluguje  # type: ignore[attr-defined]

    assert obsluguje(TypZrodla.PLIK_DOKUMENT, format_zrodla)
    assert not obsluguje(TypZrodla.PLIK_DOKUMENT, "docx")
    assert not obsluguje(TypZrodla.PLIK_TEKSTOWY, format_zrodla)


# --- prawdziwy LibreOffice ---------------------------------------------------------


@pytest.mark.wolne
@pytest.mark.skipif(not czy_dostepny(), reason="LibreOffice nie jest zainstalowany")
def test_prawdziwy_libreoffice_czyta_doc_i_ppt_z_polskimi_znakami() -> None:
    program = znajdz_libreoffice()
    doc = konwertuj(program, (DANE / "dokument.fodt").read_bytes(), "fodt", "doc", "id")
    ppt = konwertuj(program, (DANE / "prezentacja.fodp").read_bytes(), "fodp", "ppt", "id")

    dokument = EkstraktorDoc().wyekstrahuj("id", doc)
    prezentacja = EkstraktorPpt().wyekstrahuj("id", ppt)

    assert "Zażółć gęślą jaźń" in dokument.tekst
    assert "| Gatunek | Długość | Waga |" in dokument.tekst
    assert "## Slajd 1" in prezentacja.tekst
    assert "Pancerz chroni żółwia" in prezentacja.tekst
