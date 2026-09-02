"""Testy sanityzacji nazw projektów i plików do postaci bezpiecznej dla Windows."""

from __future__ import annotations

import pytest

from gnb.core.nazwy import (
    bezpieczna_nazwa_pliku,
    nazwa_pliku_czesci,
    nazwa_pliku_grupy,
    nazwa_pliku_wynikowego,
    sanityzuj_nazwe_projektu,
    wygeneruj_nazwe_projektu,
)
from gnb.core.wyjatki import BladTrwaly


@pytest.mark.parametrize("nazwa_zarezerwowana", ["CON", "con", "PRN", "COM1", "LPT9", "nul"])
def test_nazwa_zarezerwowana_jest_odrzucana(nazwa_zarezerwowana: str) -> None:
    with pytest.raises(BladTrwaly):
        sanityzuj_nazwe_projektu(nazwa_zarezerwowana)


def test_znaki_niedozwolone_sa_zamieniane_na_podkreslenie() -> None:
    assert sanityzuj_nazwe_projektu("raport: 2026/08 <wersja>") == "raport_ 2026_08 _wersja_"


def test_koncowe_kropki_i_spacje_sa_usuwane() -> None:
    assert sanityzuj_nazwe_projektu("Projekt testowy...  ") == "Projekt testowy"


def test_pusta_nazwa_po_oczyszczeniu_jest_bledem() -> None:
    with pytest.raises(BladTrwaly):
        sanityzuj_nazwe_projektu("   ...   ")


def test_wygeneruj_nazwe_bierze_poczatkowe_slowa() -> None:
    nazwa = wygeneruj_nazwe_projektu("Jak przygotować bazę wiedzy dla asystenta AI krok po kroku")
    assert nazwa == "jak_przygotować_bazę_wiedzy_dla_asystenta_ai_krok"


def test_wygeneruj_nazwe_zwraca_awaryjna_dla_pustej_podstawy() -> None:
    assert wygeneruj_nazwe_projektu("   ") == "projekt"


def test_bezpieczna_nazwa_pliku_uzywa_awaryjnej_dla_nazwy_zarezerwowanej() -> None:
    assert (
        bezpieczna_nazwa_pliku("CON", nazwa_awaryjna="tekst_wklejony-abc") == "tekst_wklejony-abc"
    )


def test_bezpieczna_nazwa_pliku_zachowuje_poprawny_tytul() -> None:
    assert (
        bezpieczna_nazwa_pliku("Notatka o kodowaniu", nazwa_awaryjna="x") == "Notatka o kodowaniu"
    )


def test_nazwa_pliku_wynikowego_laczy_trzon_tytulu_ze_skrotem_zrodla() -> None:
    nazwa = nazwa_pliku_wynikowego("Baza wiedzy dla asystenta AI", "plik_tekstowy-3f2a9c1d0e8b7a65")
    assert nazwa == "baza_wiedzy_dla_asystenta_ai_3f2a9c1d"


def test_nazwa_pliku_wynikowego_zachowuje_polskie_znaki() -> None:
    nazwa = nazwa_pliku_wynikowego("Zażółć gęślą jaźń", "plik_tekstowy-abcdef0123456789")
    assert nazwa == "zażółć_gęślą_jaźń_abcdef01"


def test_nazwa_pliku_wynikowego_tnie_trzon_na_granicy_slowa() -> None:
    tytul = (
        "Baza wiedzy dla asystenta AI jest tym lepsza, im mniej zawiera powtórzeń "
        "i im dokładniej wiadomo, skąd pochodzi każdy fragment"
    )
    nazwa = nazwa_pliku_wynikowego(tytul, "plik_tekstowy-7be0e41de03fb311")

    trzon = nazwa.rsplit("_", 1)[0]
    assert len(trzon) <= 60
    assert trzon == "baza_wiedzy_dla_asystenta_ai_jest_tym_lepsza_im_mniej"
    assert nazwa.endswith("_7be0e41d")


def test_nazwa_pliku_wynikowego_uzywa_typu_zrodla_gdy_brak_tytulu() -> None:
    assert (
        nazwa_pliku_wynikowego(None, "tekst_wklejony-8d1b80c0b30c0cd4") == "tekst_wklejony_8d1b80c0"
    )


def test_nazwa_pliku_wynikowego_nie_powtarza_sie_dla_roznych_zrodel() -> None:
    pierwsza = nazwa_pliku_wynikowego("Ten sam tytuł", "plik_tekstowy-1111111111111111")
    druga = nazwa_pliku_wynikowego("Ten sam tytuł", "plik_tekstowy-2222222222222222")
    assert pierwsza != druga


def test_nazwa_pliku_wynikowego_odrzuca_nazwe_zarezerwowana_windows() -> None:
    nazwa = nazwa_pliku_wynikowego("CON", "plik_tekstowy-99887766aabbccdd")
    assert nazwa == "plik_tekstowy_99887766"


def test_nazwa_pliku_nie_zawiera_ciagow_podkreslen() -> None:
    """Czytnik ekranu odczytuje każde podkreślenie osobno, więc ciągi są uciążliwe."""
    nazwa = nazwa_pliku_wynikowego(
        "Do schools kill creativity? | Sir Ken Robinson | TED", "youtube-a2aa00a5ffff1111"
    )

    assert "__" not in nazwa
    assert nazwa == "do_schools_kill_creativity_sir_ken_robinson_ted_a2aa00a5"


def test_tytul_zakonczony_interpunkcja_nie_daje_podwojnego_podkreslenia() -> None:
    nazwa = nazwa_pliku_wynikowego("Raport za rok 2026...", "plik_tekstowy-1234567890abcdef")

    assert nazwa == "raport_za_rok_2026_12345678"
    assert "__" not in nazwa


def test_ciag_znakow_niedozwolonych_nie_daje_ciagu_podkreslen() -> None:
    nazwa = nazwa_pliku_wynikowego("Raport: 2026//08 <wersja>", "plik_tekstowy-1234567890abcdef")

    assert "__" not in nazwa
    assert not nazwa.startswith("_")
    assert not nazwa.endswith("_")


def test_nazwa_pliku_czesci_dokleja_oznaczenie_bez_uzupelniania_zerami_dla_malej_liczby() -> None:
    assert nazwa_pliku_czesci("raport_12345678", 2, 3) == "raport_12345678_czesc_2_z_3"


def test_nazwa_pliku_czesci_uzupelnia_zerami_do_szerokosci_liczby_wszystkich_czesci() -> None:
    assert nazwa_pliku_czesci("raport_12345678", 2, 12) == "raport_12345678_czesc_02_z_12"
    assert nazwa_pliku_czesci("raport_12345678", 11, 12) == "raport_12345678_czesc_11_z_12"


def test_nazwa_pliku_grupy_jest_stabilna_i_zalezy_od_skladu() -> None:
    a = nazwa_pliku_grupy("Podatki 2026", ["plik_tekstowy-b", "plik_tekstowy-a"])
    b = nazwa_pliku_grupy("Podatki 2026", ["plik_tekstowy-a", "plik_tekstowy-b"])
    inny_sklad = nazwa_pliku_grupy("Podatki 2026", ["plik_tekstowy-a", "plik_tekstowy-c"])

    assert a == b
    assert a.startswith("podatki_2026_")
    assert a != inny_sklad
    assert "__" not in a


def test_nazwa_pliku_grupy_z_pusta_nazwa_uzywa_czlonu_awaryjnego() -> None:
    nazwa = nazwa_pliku_grupy("///", ["plik_tekstowy-a"])

    assert nazwa.startswith("grupa_")
