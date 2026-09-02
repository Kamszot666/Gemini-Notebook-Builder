"""Testy składania treści pliku wynikowego z fragmentów wraz z nagłówkami."""

from __future__ import annotations

from gnb.output.skladanie import (
    WIERSZ_KOLEJNEGO_FRAGMENTU,
    oznaczenie_pliku_grupy,
    zloz_plik,
)


def test_pojedynczy_fragment_to_naglowek_pusty_wiersz_i_tresc() -> None:
    tekst = zloz_plik([("Tytuł: A\nIdentyfikator źródła: plik_tekstowy-1", "Treść źródła.")])

    assert tekst == "Tytuł: A\nIdentyfikator źródła: plik_tekstowy-1\n\nTreść źródła."
    assert WIERSZ_KOLEJNEGO_FRAGMENTU not in tekst


def test_wiele_fragmentow_ma_naglowek_przed_kazda_trescia_i_wiersz_rozdzielajacy() -> None:
    tekst = zloz_plik(
        [
            ("Tytuł: A", "Treść A."),
            ("Tytuł: B", "Treść B."),
            ("Tytuł: C", "Treść C."),
        ]
    )

    assert tekst.count("Tytuł: ") == 3
    assert tekst.count(WIERSZ_KOLEJNEGO_FRAGMENTU) == 2
    assert tekst.startswith("Tytuł: A\n\nTreść A.")
    assert f"{WIERSZ_KOLEJNEGO_FRAGMENTU}\n\nTytuł: B\n\nTreść B." in tekst


def test_oznaczenie_pliku_grupy_trafia_na_sam_poczatek() -> None:
    oznaczenie = oznaczenie_pliku_grupy("Podatki 2026", 2, 3)
    tekst = zloz_plik([("Tytuł: A", "Treść A.")], oznaczenie_pliku=oznaczenie)

    assert tekst.startswith("Plik grupy „Podatki 2026”, część 2 z 3.\n\nTytuł: A")


def test_brak_utraty_tresci_przy_skladaniu_wielu_zrodel() -> None:
    fragmenty = [
        (f"Identyfikator źródła: plik_tekstowy-{i}", f"Unikalna treść numer {i} do zapamiętania.")
        for i in range(5)
    ]
    tekst = zloz_plik(fragmenty)

    for i in range(5):
        assert f"Unikalna treść numer {i} do zapamiętania." in tekst
        assert f"Identyfikator źródła: plik_tekstowy-{i}" in tekst
