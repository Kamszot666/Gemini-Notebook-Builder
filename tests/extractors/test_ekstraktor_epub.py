"""Testy ekstraktora plików EPUB."""

from __future__ import annotations

import io

from ebooklib import epub

from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.extractors.plik_epub import EkstraktorEpub


def _epub_z_dwoma_rozdzialami(*, tytul: str = "Testowa Książka") -> bytes:
    """Buduje plik EPUB z dwoma rozdziałami w ustalonej kolejności lektury."""
    ksiazka = epub.EpubBook()
    ksiazka.set_identifier("test-ksiazka-1")
    ksiazka.set_title(tytul)
    ksiazka.set_language("pl")
    ksiazka.add_author("Jan Kowalski")
    ksiazka.add_metadata("DC", "date", "2024-03-15")

    rozdzial1 = epub.EpubHtml(title="Rozdział 1", file_name="rozdzial1.xhtml", lang="pl")
    rozdzial1.content = (
        "<html><body>"
        "<h1>Rozdział pierwszy</h1>"
        "<p>To jest wprowadzający akapit.</p>"
        "<ul><li>Punkt A</li><li>Punkt B</li></ul>"
        "</body></html>"
    )
    ksiazka.add_item(rozdzial1)

    rozdzial2 = epub.EpubHtml(title="Rozdział 2", file_name="rozdzial2.xhtml", lang="pl")
    rozdzial2.content = (
        "<html><body><h1>Rozdział drugi</h1><p>Kolejny akapit w drugim rozdziale.</p></body></html>"
    )
    ksiazka.add_item(rozdzial2)

    ksiazka.add_item(epub.EpubNcx())
    nawigacja = epub.EpubNav()
    ksiazka.add_item(nawigacja)
    ksiazka.spine = [nawigacja, rozdzial1, rozdzial2]

    bufor = io.BytesIO()
    epub.write_epub(bufor, ksiazka)
    return bufor.getvalue()


def test_rozdzialy_sa_czytane_w_kolejnosci_spine() -> None:
    dokument = EkstraktorEpub().wyekstrahuj("plik_dokument-1", _epub_z_dwoma_rozdzialami())

    pozycja_pierwszego = dokument.tekst.index("Rozdział pierwszy")
    pozycja_drugiego = dokument.tekst.index("Rozdział drugi")
    assert pozycja_pierwszego < pozycja_drugiego


def test_dokument_nawigacyjny_nie_trafia_do_tresci() -> None:
    dokument = EkstraktorEpub().wyekstrahuj("plik_dokument-2", _epub_z_dwoma_rozdzialami())
    assert "nav" not in dokument.tekst.lower()


def test_naglowki_akapity_i_listy_sa_rozpoznane() -> None:
    dokument = EkstraktorEpub().wyekstrahuj("plik_dokument-3", _epub_z_dwoma_rozdzialami())

    rodzaje = [blok.rodzaj for blok in dokument.bloki]
    assert rodzaje.count(RodzajBloku.NAGLOWEK) == 2
    assert RodzajBloku.AKAPIT in rodzaje
    assert RodzajBloku.LISTA in rodzaje
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.WYSOKI


def test_tytul_i_metadane_pochodza_z_dublin_core() -> None:
    dokument = EkstraktorEpub().wyekstrahuj(
        "plik_dokument-4", _epub_z_dwoma_rozdzialami(tytul="Inny Tytuł")
    )

    assert dokument.tytul == "Inny Tytuł"
    assert dokument.metadane["autor"] == "Jan Kowalski"
    assert dokument.metadane["data_publikacji"] == "2024-03-15"


def test_obsluguje_wylacznie_format_epub() -> None:
    ekstraktor = EkstraktorEpub()
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "epub") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_DOKUMENT, "docx") is False
