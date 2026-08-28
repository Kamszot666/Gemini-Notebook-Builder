"""Testy ekstraktora plików EPUB."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from ebooklib import epub

from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.plik_epub import EkstraktorEpub

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


# Napis występujący wyłącznie w dokumencie nawigacyjnym, w żadnym rozdziale.
# Pozwala sprawdzić, czy spis treści rzeczywiście nie trafia do wyniku.
_MARKER_SPISU_TRESCI = "POZYCJA SPISU TRESCI"


def _epub_z_jednym_rozdzialem(tresc: str) -> bytes:
    """Buduje plik EPUB z jednym rozdziałem o podanej treści XHTML."""
    ksiazka = epub.EpubBook()
    ksiazka.set_identifier("test-ksiazka-2")
    ksiazka.set_title("Testowa Książka")
    ksiazka.set_language("pl")

    rozdzial = epub.EpubHtml(title="Rozdział", file_name="rozdzial.xhtml", lang="pl")
    rozdzial.content = tresc
    ksiazka.add_item(rozdzial)

    ksiazka.add_item(epub.EpubNcx())
    nawigacja = epub.EpubNav()
    ksiazka.add_item(nawigacja)
    ksiazka.spine = [nawigacja, rozdzial]

    bufor = io.BytesIO()
    epub.write_epub(bufor, ksiazka)
    return bufor.getvalue()


def _epub_z_dwoma_rozdzialami(
    *, tytul: str = "Testowa Książka", pozycja_spisu: str | None = None
) -> bytes:
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

    if pozycja_spisu is not None:
        ksiazka.toc = (epub.Link("rozdzial1.xhtml", pozycja_spisu, "rozdzial1"),)
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
    """Spis treści EPUB nie jest treścią książki i nie może trafić do wyniku.

    Sprawdzany jest napis występujący wyłącznie w dokumencie nawigacyjnym,
    a nie w żadnym rozdziale. Poprzednia postać tego testu szukała w tekście
    słowa „nav”, którego dokument nawigacyjny i tak nie zawiera, więc przechodziła
    także po wyłączeniu filtru, który miała chronić.
    """
    dokument = EkstraktorEpub().wyekstrahuj(
        "plik_dokument-2", _epub_z_dwoma_rozdzialami(pozycja_spisu=_MARKER_SPISU_TRESCI)
    )

    assert _MARKER_SPISU_TRESCI not in dokument.tekst
    assert "Rozdział pierwszy" in dokument.tekst


def test_wiersz_tabeli_z_komorka_naglowkowa_i_zwykla_zachowuje_kolejnosc() -> None:
    """Komórki wiersza mają wyjść w kolejności z dokumentu, a nie pogrupowane rodzajem.

    Wiersz „Rok, 1939, Miejsce, Gdańsk” zapisany jako th, td, th, td wychodził
    wcześniej jako „1939, Gdańsk, Rok, Miejsce”, ponieważ komórki były wynikiem
    dwóch osobnych wyszukiwań sklejonych jedno po drugim. Odwrócona kolejność
    kolumn to naruszenie poprawności danych, a nie usterka kosmetyczna.
    """
    tresc_rozdzialu = (
        "<html><body><h1>Tabela</h1><table><tr>"
        "<th>Rok</th><td>1939</td><th>Miejsce</th><td>Gdańsk</td>"
        "</tr></table></body></html>"
    )
    dokument = EkstraktorEpub().wyekstrahuj(
        "plik_dokument-8", _epub_z_jednym_rozdzialem(tresc_rozdzialu)
    )

    tabele = [blok for blok in dokument.bloki if blok.rodzaj is RodzajBloku.TABELA]
    assert len(tabele) == 1
    assert tabele[0].tresc.split("	") == ["Rok", "1939", "Miejsce", "Gdańsk"]


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


def test_plik_testowy_ma_naglowek_i_akapity() -> None:
    dane = (KATALOG_DANYCH / "ksiazka.epub").read_bytes()
    dokument = EkstraktorEpub().wyekstrahuj("plik_dokument-6", dane)

    rodzaje = [blok.rodzaj for blok in dokument.bloki]
    assert RodzajBloku.NAGLOWEK in rodzaje
    assert RodzajBloku.AKAPIT in rodzaje
    assert dokument.tytul is not None


def _archiwum_zip_bez_ksiazki() -> bytes:
    """Buduje poprawne archiwum zip, które nie jest książką EPUB."""
    bufor = io.BytesIO()
    with zipfile.ZipFile(bufor, "w") as archiwum:
        archiwum.writestr("cokolwiek.txt", "to nie jest książka")
    return bufor.getvalue()


def test_uszkodzony_plik_konczy_sie_bledem_trwalym() -> None:
    """Plik, który nie jest archiwum zip, nie może wywrócić całego przebiegu.

    Biblioteka zgłasza tu wyjątek spoza taksonomii projektu, więc potok go nie
    łapał i poprawne źródła z tej samej partii nie były przetwarzane.
    """
    with pytest.raises(BladTrwaly, match="uszkodzony"):
        EkstraktorEpub().wyekstrahuj("plik_dokument-9", b"to nie jest plik EPUB")


def test_archiwum_bez_spisu_zawartosci_konczy_sie_bledem_trwalym() -> None:
    """Poprawne archiwum zip bez pliku container.xml też jest błędem trwałym."""
    with pytest.raises(BladTrwaly, match="uszkodzony"):
        EkstraktorEpub().wyekstrahuj("plik_dokument-10", _archiwum_zip_bez_ksiazki())


def _epub_z_pustym_rozdzialem() -> bytes:
    """Buduje poprawny plik EPUB, w którym pierwszy rozdział jest pusty.

    Zawartość rozdziału jest podmieniana już w gotowym archiwum, ponieważ
    biblioteka zapisująca EPUB nie pozwala utworzyć rozdziału o pustej treści.
    Tak wygląda plik uszkodzony po drodze, a nie plik wadliwie wygenerowany.
    """
    zrodlowe = _epub_z_dwoma_rozdzialami()
    bufor = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(zrodlowe)) as wejscie:
        with zipfile.ZipFile(bufor, "w") as wyjscie:
            for pozycja in wejscie.infolist():
                dane = wejscie.read(pozycja.filename)
                if pozycja.filename.endswith("rozdzial1.xhtml"):
                    dane = b"   "
                wyjscie.writestr(pozycja, dane)
    return bufor.getvalue()


def test_rozdzial_ktorego_nie_da_sie_sparsowac_daje_ostrzezenie() -> None:
    """Nieodczytany rozdział nie może zniknąć bez śladu.

    Wcześniej taki rozdział znikał w całości: bez ostrzeżenia, bez wpisu w logu
    i bez wpisu w manifeście. Pozostałe rozdziały mają się przy tym odczytać.
    """
    dokument = EkstraktorEpub().wyekstrahuj("plik_dokument-11", _epub_z_pustym_rozdzialem())

    assert dokument.ostrzezenia
    assert "nie dało się sparsować" in dokument.ostrzezenia[0]
    assert "Rozdział pierwszy" not in dokument.tekst
    assert "Rozdział drugi" in dokument.tekst
