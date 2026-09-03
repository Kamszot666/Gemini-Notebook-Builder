"""Testy wczytywania konfiguracji z wartości domyślnych, pliku TOML i środowiska."""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.konfiguracja import (
    DOMYSLNY_ADRES_NASLUCHU,
    DOMYSLNY_BEZPIECZNY_LIMIT_SLOW,
    DOMYSLNY_LIMIT_ZNAKOW_INSTRUKCJI_SYSTEMOWEJ,
    DOMYSLNY_LIMIT_ZRODEL,
    DOMYSLNY_PORT_NASLUCHU,
    wczytaj_konfiguracje,
)
from gnb.core.wyjatki import BladTrwaly


def test_brak_pliku_daje_wartosci_domyslne(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})
    assert konfiguracja.limit_zrodel == DOMYSLNY_LIMIT_ZRODEL
    assert konfiguracja.bezpieczny_limit_slow == DOMYSLNY_BEZPIECZNY_LIMIT_SLOW
    assert konfiguracja.formaty_wynikowe == ("txt", "md")


def test_wartosci_z_pliku_toml_sa_wczytywane(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text(
        'katalog_wynikow = "D:/Wyniki"\n'
        "limit_zrodel = 300\n"
        "bezpieczny_limit_slow = 200000\n"
        'formaty_wynikowe = ["txt"]\n',
        encoding="utf-8",
    )
    konfiguracja = wczytaj_konfiguracje(plik, srodowisko={})
    assert konfiguracja.katalog_wynikow == Path("D:/Wyniki")
    assert konfiguracja.limit_zrodel == 300
    assert konfiguracja.bezpieczny_limit_slow == 200000
    assert konfiguracja.formaty_wynikowe == ("txt",)


def test_zmienna_srodowiskowa_ma_pierwszenstwo_przed_plikiem(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("limit_zrodel = 300\n", encoding="utf-8")
    konfiguracja = wczytaj_konfiguracje(plik, srodowisko={"GNB_LIMIT_ZRODEL": "50"})
    assert konfiguracja.limit_zrodel == 50


def test_zmienna_srodowiskowa_katalogu_wynikow(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml", srodowisko={"GNB_KATALOG_WYNIKOW": "/dane/wyniki"}
    )
    assert konfiguracja.katalog_wynikow == Path("/dane/wyniki")


def test_uszkodzony_plik_toml_daje_blad_trwaly(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("to nie jest = poprawny [ toml", encoding="utf-8")
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(plik, srodowisko={})


def test_niepoprawna_liczba_daje_blad_trwaly(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={"GNB_LIMIT_ZRODEL": "sto"})


def test_nieznany_format_wynikowy_daje_blad_trwaly(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml", srodowisko={"GNB_FORMATY_WYNIKOWE": "txt,pdf"}
        )


def test_zachowuj_oryginaly_jest_domyslnie_wlaczone_i_da_sie_wylaczyc(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("limit_zrodel = 50\n", encoding="utf-8")

    assert wczytaj_konfiguracje(plik, {}).zachowuj_oryginaly is True

    plik.write_text("zachowuj_oryginaly = false\n", encoding="utf-8")
    assert wczytaj_konfiguracje(plik, {}).zachowuj_oryginaly is False

    assert wczytaj_konfiguracje(plik, {"GNB_ZACHOWUJ_ORYGINALY": "tak"}).zachowuj_oryginaly is True


def test_niepoprawna_wartosc_logiczna_konczy_sie_bledem(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text('zachowuj_oryginaly = "moze"\n', encoding="utf-8")
    with pytest.raises(BladTrwaly, match="wartością logiczną"):
        wczytaj_konfiguracje(plik, {})


def test_deduplikacja_ma_domyslne_wlaczenie_i_progi(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})

    assert konfiguracja.deduplikacja_hash_wlaczona is True
    assert konfiguracja.deduplikacja_kosmetyczna_wlaczona is True
    assert konfiguracja.deduplikacja_podobienstwo_wlaczone is True
    assert konfiguracja.deduplikacja_embeddingi_wlaczone is False
    assert konfiguracja.deduplikacja_prog_duplikatu == 0.9
    assert konfiguracja.deduplikacja_prog_do_przegladu == 0.75


def test_progi_deduplikacji_da_sie_ustawic_z_pliku_i_srodowiska(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text("deduplikacja_prog_duplikatu = 0.95\n", encoding="utf-8")
    assert wczytaj_konfiguracje(plik, {}).deduplikacja_prog_duplikatu == 0.95

    z_srodowiska = wczytaj_konfiguracje(plik, {"GNB_DEDUPLIKACJA_PROG_DUPLIKATU": "0,8"})
    assert z_srodowiska.deduplikacja_prog_duplikatu == 0.8


def test_prog_deduplikacji_spoza_przedzialu_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="od zera do jednego"):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml", srodowisko={"GNB_DEDUPLIKACJA_PROG_DUPLIKATU": "1.5"}
        )


def test_prog_do_przegladu_wyzszy_niz_prog_duplikatu_konczy_sie_bledem(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text(
        "deduplikacja_prog_duplikatu = 0.7\ndeduplikacja_prog_do_przegladu = 0.9\n",
        encoding="utf-8",
    )
    with pytest.raises(BladTrwaly, match="nie może być wyższe"):
        wczytaj_konfiguracje(plik, {})


def test_ustawienia_interfejsu_maja_wartosci_domyslne(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})

    assert konfiguracja.adres_nasluchu == DOMYSLNY_ADRES_NASLUCHU == "127.0.0.1"
    assert konfiguracja.port_nasluchu == DOMYSLNY_PORT_NASLUCHU
    assert (
        konfiguracja.limit_znakow_instrukcji_systemowej
        == DOMYSLNY_LIMIT_ZNAKOW_INSTRUKCJI_SYSTEMOWEJ
        == 10_000
    )


def test_adres_nasluchu_da_sie_ustawic_na_localhost(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text('adres_nasluchu = "localhost"\nport_nasluchu = 9000\n', encoding="utf-8")
    konfiguracja = wczytaj_konfiguracje(plik, {})
    assert konfiguracja.adres_nasluchu == "localhost"
    assert konfiguracja.port_nasluchu == 9000


def test_adres_nasluchu_spoza_petli_zwrotnej_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="pętlę zwrotną"):
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={"GNB_ADRES_NASLUCHU": "0.0.0.0"})


def test_port_nasluchu_ponad_zakres_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="numerem portu"):
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={"GNB_PORT_NASLUCHU": "70000"})


def test_ustawienia_ocr_maja_wartosci_domyslne(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})

    assert konfiguracja.ocr_wlaczony is True
    assert konfiguracja.ocr_jezyk == "pol"
    assert konfiguracja.ocr_psm == 3
    assert konfiguracja.ocr_rozdzielczosc_pdf_dpi == 300
    assert konfiguracja.ocr_liczba_procesow == 0
    assert konfiguracja.sciezka_tesseract == ""
    assert konfiguracja.sciezka_tessdata == ""
    assert konfiguracja.jakosc_grafik == 85
    assert konfiguracja.maksymalny_wymiar_grafiki_px == 2600
    assert konfiguracja.maksymalny_rozmiar_pdf_mb == 190


def test_jezyk_ocr_da_sie_ustawic_na_kilka_jezykow(tmp_path: Path) -> None:
    plik = tmp_path / "konfiguracja.toml"
    plik.write_text('ocr_jezyk = "pol+eng"\n', encoding="utf-8")
    assert wczytaj_konfiguracje(plik, {}).ocr_jezyk == "pol+eng"

    z_srodowiska = wczytaj_konfiguracje(plik, {"GNB_OCR_WLACZONY": "nie"})
    assert z_srodowiska.ocr_wlaczony is False


def test_tryb_segmentacji_strony_spoza_zakresu_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="od 0 do 13"):
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={"GNB_OCR_PSM": "99"})


def test_jakosc_grafik_spoza_zakresu_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="od 1 do 100"):
        wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={"GNB_JAKOSC_GRAFIK": "0"})


def test_sciezka_tessdata_musi_wskazywac_istniejacy_katalog(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="katalog, którego nie ma"):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml",
            srodowisko={"GNB_SCIEZKA_TESSDATA": str(tmp_path / "brak_katalogu")},
        )

    istniejacy = tmp_path / "tessdata"
    istniejacy.mkdir()
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml", srodowisko={"GNB_SCIEZKA_TESSDATA": str(istniejacy)}
    )
    assert konfiguracja.sciezka_tessdata == str(istniejacy)


def test_domyslne_ustawienia_transkrypcji(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(tmp_path / "nie_ma.toml", srodowisko={})
    assert konfiguracja.transkrypcja_wlaczona is True
    assert konfiguracja.transkrypcja_model == "medium"
    assert konfiguracja.transkrypcja_jezyk == "pl"
    assert konfiguracja.transkrypcja_urzadzenie == "procesor"
    assert konfiguracja.transkrypcja_typ_obliczen == "int8"
    assert konfiguracja.transkrypcja_liczba_watkow == 0
    assert konfiguracja.transkrypcja_prog_vad == 0.5
    assert konfiguracja.transkrypcja_prog_udzialu_mowy == 0.5


def test_ustawienia_transkrypcji_ze_srodowiska(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml",
        srodowisko={
            "GNB_TRANSKRYPCJA_MODEL": "small",
            "GNB_TRANSKRYPCJA_LICZBA_WATKOW": "4",
            "GNB_TRANSKRYPCJA_PROG_UDZIALU_MOWY": "0",
        },
    )
    assert konfiguracja.transkrypcja_model == "small"
    assert konfiguracja.transkrypcja_liczba_watkow == 4
    assert konfiguracja.transkrypcja_prog_udzialu_mowy == 0.0


def test_transkrypcja_urzadzenie_karta_graficzna_konczy_sie_bledem(tmp_path: Path) -> None:
    """Decyzja trzecia etapu dziewiątego: karta graficzna to jawny błąd konfiguracji.

    Test czerwieni się, gdyby ustawienie zaczęło po cichu wracać do wartości
    „procesor” zamiast zgłaszać, że ta ścieżka nie jest w tej wersji obsługiwana.
    """
    with pytest.raises(BladTrwaly, match="wyłącznie na procesorze"):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml",
            srodowisko={"GNB_TRANSKRYPCJA_URZADZENIE": "cuda"},
        )


def test_transkrypcja_urzadzenie_cpu_jest_dozwolone(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml", srodowisko={"GNB_TRANSKRYPCJA_URZADZENIE": "cpu"}
    )
    assert konfiguracja.transkrypcja_urzadzenie == "procesor"


def test_transkrypcja_prog_udzialu_mowy_powyzej_jednego_konczy_sie_bledem(tmp_path: Path) -> None:
    with pytest.raises(BladTrwaly, match="od zera do jednego"):
        wczytaj_konfiguracje(
            tmp_path / "nie_ma.toml",
            srodowisko={"GNB_TRANSKRYPCJA_PROG_UDZIALU_MOWY": "1.5"},
        )
