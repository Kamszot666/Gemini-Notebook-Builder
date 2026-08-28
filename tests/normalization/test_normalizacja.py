"""Testy normalizacji tekstu źródła."""

from __future__ import annotations

import unicodedata

from gnb.normalization.normalizacja import zbuduj_dokument_znormalizowany, znormalizuj


def test_konce_wierszy_sa_sprowadzane_do_lf() -> None:
    assert znormalizuj("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_biale_znaki_z_koncow_wierszy_sa_usuwane() -> None:
    assert (
        znormalizuj("wiersz z ogonem   \n  wcięty wiersz  ") == "wiersz z ogonem\n  wcięty wiersz"
    )


def test_nadmiarowe_puste_wiersze_sa_skracane() -> None:
    assert znormalizuj("a\n\n\n\n\nb") == "a\n\nb"


def test_puste_wiersze_z_poczatku_i_konca_sa_usuwane() -> None:
    assert znormalizuj("\n\n  treść  \n\n") == "treść"


def test_znaki_unicode_sa_sprowadzane_do_nfc() -> None:
    tekst_nfd = unicodedata.normalize("NFD", "ąćź")
    wynik = znormalizuj(tekst_nfd)
    assert wynik == "ąćź"
    assert unicodedata.is_normalized("NFC", wynik)


def test_normalizacja_jest_idempotentna() -> None:
    surowy = "\r\n Tytuł  \r\n\r\n\r\n Treść z ogonem \t\n"
    raz = znormalizuj(surowy)
    assert znormalizuj(raz) == raz


def test_dokument_znormalizowany_ma_liczniki_z_tekstu_po_normalizacji() -> None:
    dokument = zbuduj_dokument_znormalizowany("zrodlo-1", "  dwa\r\n\r\n\r\nsłowa  ")
    assert dokument.tekst == "dwa\n\nsłowa"
    assert dokument.liczba_slow == 2
    assert dokument.liczba_znakow == len("dwa\n\nsłowa")


def test_tabulator_staje_sie_pojedyncza_spacja() -> None:
    """Znak tabulacji przychodzi z napisów i jest odczytywany przez NVDA osobno."""
    assert znormalizuj("we\twszystkich prezentacjach") == "we wszystkich prezentacjach"


def test_twarda_spacja_staje_sie_zwykla_spacja() -> None:
    assert znormalizuj("we\u00a0wszystkich") == "we wszystkich"


def test_waska_spacja_niepodzielna_staje_sie_zwykla_spacja() -> None:
    assert znormalizuj("we\u202fwszystkich") == "we wszystkich"


def test_ciag_spacji_jest_skracany_do_jednej() -> None:
    assert znormalizuj("we        wszystkich") == "we wszystkich"


def test_bialy_znak_sterujacy_staje_sie_spacja() -> None:
    """Pionowy tabulator jest jednocześnie znakiem sterującym i białym znakiem."""
    assert znormalizuj("we\x0bwszystkich") == "we wszystkich"


def test_niebialy_znak_sterujacy_znika_bez_sladu() -> None:
    assert znormalizuj("tekst\x07koniec") == "tekstkoniec"


def test_spacja_o_zerowej_szerokosci_znika_bez_dodawania_odstepu() -> None:
    """Ten znak jest niewidoczny, więc jego usunięcie zachowuje zapis widziany przez czytelnika."""
    assert znormalizuj("we\u200bwszystkich") == "wewszystkich"


def test_miekki_lacznik_znika() -> None:
    assert znormalizuj("pre\u00adzentacja") == "prezentacja"


def test_znacznik_kolejnosci_bajtow_w_srodku_tekstu_znika() -> None:
    assert znormalizuj("tekst\ufeffdalej") == "tekstdalej"


def test_spoiwo_slow_znika() -> None:
    assert znormalizuj("tekst\u2060dalej") == "tekstdalej"


def test_spoiwo_sekwencji_emoji_jest_zachowane() -> None:
    """Znak ZWJ zmienia znaczenie zapisu, więc nie jest usuwany razem z niewidocznymi."""
    tekst = "rodzina \U0001f468\u200d\U0001f469"

    assert "\u200d" in znormalizuj(tekst)


def test_znak_nowej_linii_nie_jest_zamieniany_na_spacje() -> None:
    assert znormalizuj("pierwszy\ndrugi") == "pierwszy\ndrugi"


def test_normalizacja_bialych_znakow_jest_idempotentna() -> None:
    tekst = "we\twszystkich\u00a0prezentacjach\u200b, tak\x07jest"

    raz = znormalizuj(tekst)

    assert znormalizuj(raz) == raz


def test_wciecie_na_poczatku_wiersza_jest_zachowane() -> None:
    """Wcięcie niesie znaczenie: tak zapisujemy zagnieżdżenie list i wnętrze bloków kodu."""
    tekst = "- Poziom pierwszy\n  - Poziom drugi\n    - Poziom trzeci"

    assert znormalizuj(tekst) == tekst


def test_wciecie_bloku_kodu_nie_jest_skracane() -> None:
    assert znormalizuj("def f():\n    return 1") == "def f():\n    return 1"


def test_wciecie_tabulatorem_staje_sie_wcieciem_spacjami() -> None:
    """Wiersz poprzedzający jest konieczny, bo białe znaki z brzegów tekstu są usuwane."""
    assert znormalizuj("pierwszy wiersz\n\t\twcięty") == "pierwszy wiersz\n  wcięty"


def test_ciag_spacji_w_srodku_wiersza_jest_skracany_mimo_zachowania_wciecia() -> None:
    tekst = "pierwszy wiersz\n    we    wszystkich"

    assert znormalizuj(tekst) == "pierwszy wiersz\n    we wszystkich"
