"""Testy podpolecenia wiersza poleceń ``gnb przetworz``."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.cli import _postep_wiersza_polecen, main
from gnb.core.postep import FazaPotoku, ZdarzeniePostepu

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"


def test_przetworz_konczy_sie_kodem_zero_dla_poprawnego_wejscia(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(
        [
            "przetworz",
            "--projekt",
            "Test CLI",
            "--plik",
            str(KATALOG_DANYCH / "dokument_strukturalny.md"),
            "--tekst",
            "Krótki tekst wklejony.",
        ]
    )

    assert kod == 0
    wyjscie = capsys.readouterr().out
    assert "Przetworzono 2 źródeł, pominięto 0." in wyjscie
    assert "Wyniki są w katalogu:" in wyjscie
    assert (tmp_path / "Test CLI" / "manifest.json").exists()


def test_przetworz_bez_zrodel_konczy_sie_kodem_niezerowym(
    capsys: pytest.CaptureFixture[str],
) -> None:
    kod = main(["przetworz", "--projekt", "Bez źródeł"])
    assert kod == 2
    assert "Nie podano żadnego źródła" in capsys.readouterr().out


def test_przetworz_z_bledna_sciezka_pliku_konczy_sie_kodem_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(["przetworz", "--projekt", "Test błędu", "--plik", str(tmp_path / "nie_ma.txt")])

    assert kod == 0
    assert "Źródła z błędem: 1" in capsys.readouterr().out


def test_sprawdz_liste_konczy_sie_kodem_zero_mimo_blednych_wpisow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(
        [
            "przetworz",
            "--projekt",
            "Test listy",
            "--lista-url",
            str(KATALOG_DANYCH / "lista_url.txt"),
            "--sprawdz-liste",
        ]
    )

    wyjscie = capsys.readouterr().out
    assert kod == 0
    assert "Adresy poprawne: 4" in wyjscie
    assert "Duplikaty pominięte: 2" in wyjscie
    assert "Wpisy odrzucone: 2" in wyjscie
    assert "Nie pobrano żadnego adresu" in wyjscie
    assert not (tmp_path / "Test listy").exists()


def test_sprawdz_liste_laczy_adresy_z_opcji_i_z_pliku(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    lista = tmp_path / "adresy.txt"
    lista.write_text("https://przyklad.pl/a\nhttps://przyklad.pl/b\n", encoding="utf-8")

    kod = main(
        [
            "przetworz",
            "--projekt",
            "Test łączenia",
            "--url",
            "https://przyklad.pl/c https://przyklad.pl/a",
            "--lista-url",
            str(lista),
            "--sprawdz-liste",
        ]
    )

    wyjscie = capsys.readouterr().out
    assert kod == 0
    assert "Adresy poprawne: 3" in wyjscie
    assert "Duplikaty pominięte: 1" in wyjscie


def test_brak_pliku_listy_konczy_sie_kodem_niezerowym(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(
        [
            "przetworz",
            "--projekt",
            "Test braku listy",
            "--lista-url",
            str(tmp_path / "nie_ma.txt"),
            "--sprawdz-liste",
        ]
    )

    assert kod == 1
    assert "listy adresów" in capsys.readouterr().out


def test_polecenie_pamiec_pokazuje_sciezke_i_stan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("GNB_SCIEZKA_CACHE", str(tmp_path / "cache.sqlite3"))

    kod = main(["pamiec"])

    wyjscie = capsys.readouterr().out
    assert kod == 0
    assert "Plik pamięci podręcznej:" in wyjscie
    assert "cache.sqlite3" in wyjscie
    assert "Plik jeszcze nie istnieje" in wyjscie


def test_polecenie_pamiec_czysci_zawartosc(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("GNB_SCIEZKA_CACHE", str(tmp_path / "cache.sqlite3"))

    assert main(["pamiec", "--wyczysc"]) == 0
    assert "Usunięto wpisów: 0." in capsys.readouterr().out


def test_postep_wiersza_polecen_wypisuje_tylko_faze_ocr_i_dlawi(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wiersze postępu OCR są dławione, a zdarzenia innych faz są pomijane.

    Test czerwieni się, gdyby postęp zaczął wypisywać każdą stronę skanu albo
    zdarzenia faz, które i tak są szybkie.
    """
    zegar = {"teraz": 100.0}
    monkeypatch.setattr("gnb.cli.time.monotonic", lambda: zegar["teraz"])
    zglos = _postep_wiersza_polecen()

    zglos(ZdarzeniePostepu(faza=FazaPotoku.EKSTRAKCJA, wykonano=1, wszystkich=3, opis="ekstrakcja"))
    zglos(ZdarzeniePostepu(faza=FazaPotoku.OCR, wykonano=1, wszystkich=10, opis="skan strona 1"))
    zglos(ZdarzeniePostepu(faza=FazaPotoku.OCR, wykonano=2, wszystkich=10, opis="skan strona 2"))
    zegar["teraz"] += 5.0
    zglos(ZdarzeniePostepu(faza=FazaPotoku.OCR, wykonano=6, wszystkich=10, opis="skan strona 6"))
    zglos(ZdarzeniePostepu(faza=FazaPotoku.OCR, wykonano=10, wszystkich=10, opis="skan strona 10"))

    wiersze = [w for w in capsys.readouterr().out.splitlines() if w]
    assert "ekstrakcja" not in wiersze
    assert wiersze == ["skan strona 1", "skan strona 6", "skan strona 10"]


def test_przetworz_z_grupa_laczy_zrodla_w_jeden_plik(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GNB_KATALOG_WYNIKOW", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))

    kod = main(
        [
            "przetworz",
            "--projekt",
            "Test grupy CLI",
            "--grupa",
            "Notatki podatkowe",
            "--tekst",
            "Pierwsza notatka o rozliczeniu rocznym.",
            "--tekst",
            "Druga notatka o zaliczkach kwartalnych.",
        ]
    )

    assert kod == 0
    capsys.readouterr()
    pliki_txt = list((tmp_path / "Test grupy CLI" / "pliki_wynikowe").glob("*.txt"))
    assert len(pliki_txt) == 1
    tresc = pliki_txt[0].read_text(encoding="utf-8")
    assert "Pierwsza notatka o rozliczeniu rocznym." in tresc
    assert "Druga notatka o zaliczkach kwartalnych." in tresc
    assert tresc.count("Identyfikator źródła: ") == 2
