"""Testy ekstraktora tekstu płaskiego."""

from __future__ import annotations

from pathlib import Path

from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.extractors.bazowy import domyslny_rejestr
from gnb.extractors.tekst import EkstraktorTekstu

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"


def test_plik_txt_daje_niski_poziom_pewnosci_i_brak_blokow() -> None:
    tekst = (KATALOG_DANYCH / "tekst_plaski.txt").read_text(encoding="utf-8")
    dokument = EkstraktorTekstu().wyekstrahuj("plik_tekstowy-1", tekst)

    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.bloki == []
    assert dokument.metoda_ekstrakcji == "tekst_plaski"


def test_tytul_to_pierwszy_niepusty_wiersz() -> None:
    dokument = EkstraktorTekstu().wyekstrahuj(
        "tekst_wklejony-1", "\n\n  Pierwszy wiersz\nDrugi wiersz"
    )
    assert dokument.tytul == "Pierwszy wiersz"


def test_rejestr_dobiera_ekstraktor_tekstu_dla_txt_i_tekstu_wklejonego() -> None:
    rejestr = domyslny_rejestr()
    assert isinstance(rejestr.dobierz(TypZrodla.PLIK_TEKSTOWY, "txt"), EkstraktorTekstu)
    assert isinstance(rejestr.dobierz(TypZrodla.TEKST_WKLEJONY, ""), EkstraktorTekstu)


def test_ekstraktor_tekstu_nie_obsluguje_formatu_md() -> None:
    assert EkstraktorTekstu().obsluguje(TypZrodla.PLIK_TEKSTOWY, "md") is False
