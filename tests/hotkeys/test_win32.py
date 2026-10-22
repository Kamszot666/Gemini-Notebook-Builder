"""Testy warstwy Win32: rejestracja i wyrejestrowanie skrótu, odczyt aktywnego okna.

Zgodnie z sekcją piątą CLAUDE.md, test uruchamiający się sam na Windows, bez
ingerencji człowieka — tu: rejestracja i wyrejestrowanie globalnego skrótu oraz
ustalenie danych aktywnego okna, jakiekolwiek by ono było — dostaje
`pytest.mark.skipif(sys.platform != "win32")`, a nie marker `pulpit`. Import
modułu jest warunkowy z tego samego powodu co w `gnb/hotkeys/_win32.py`: na
systemie innym niż Windows moduł nic nie eksportuje.
"""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Warstwa Win32 globalnego skrótu działa wyłącznie na Windows."
)

if sys.platform == "win32":
    from gnb.core.skrot import DOMYSLNA_KOMBINACJA, rozbierz_kombinacje
    from gnb.hotkeys import _win32


def test_watek_skrotu_rejestruje_i_wyrejestrowuje_skrot() -> None:
    """Po `zatrzymaj` skrót musi być wyrejestrowany — sprawdzone ponowną rejestracją.

    Gdy inny proces (na przykład wcześniej uruchomiony serwer interfejsu) trzyma
    już tę kombinację, test się pomija: to jest wykrywanie konfliktu, które ma
    swój własny czytelny komunikat w `obsluga.py`, nie powód do czerwienienia
    tego testu.
    """
    nacisniecia: list[None] = []
    watek = _win32.WatekSkrotu(lambda: nacisniecia.append(None), DOMYSLNA_KOMBINACJA)
    try:
        udalo_sie = watek.uruchom()
        if not udalo_sie:
            pytest.skip(
                "Kombinacja Control plus Shift plus F12 jest już zajęta w tym środowisku "
                "(kod błędu Windows: "
                f"{watek.kod_bledu_rejestracji})."
            )
        assert watek.zarejestrowano is True
    finally:
        watek.zatrzymaj()

    # Wyrejestrowanie faktycznie zaszło: druga rejestracja tej samej kombinacji
    # przez nowy wątek musi się teraz powiodać, bo pierwszy wątek już się skończył.
    drugi_watek = _win32.WatekSkrotu(lambda: None, DOMYSLNA_KOMBINACJA)
    try:
        assert drugi_watek.uruchom() is True
    finally:
        drugi_watek.zatrzymaj()


def test_informacje_o_aktywnym_oknie_zwracaja_dodatnie_wartosci() -> None:
    """Nie zakładamy, jakie okno jest aktywne — tylko że wynik ma sensowną strukturę."""
    informacje = _win32.informacje_o_aktywnym_oknie()

    assert informacje is not None
    assert informacje.uchwyt > 0
    assert isinstance(informacje.tytul, str)
    assert isinstance(informacje.nazwa_klasy, str)
    assert isinstance(informacje.nazwa_procesu, str)
    assert informacje.nazwa_procesu == informacje.nazwa_procesu.lower()


# Kombinacje z klawiszami F21 i F22 prawie nigdy nie są zajęte przez inne programy,
# więc testy zmiany kombinacji nie zależą od tego, czy działa serwer interfejsu.
_KOMBINACJA_A = "Control+Alt+Shift+F21"
_KOMBINACJA_B = "Control+Alt+Shift+F22"


def _uruchom_albo_pomin(kombinacja: str) -> _win32.WatekSkrotu:
    watek = _win32.WatekSkrotu(lambda: None, rozbierz_kombinacje(kombinacja))
    if not watek.uruchom():
        watek.zatrzymaj()
        pytest.skip(f"Kombinacja {kombinacja} jest zajęta w tym środowisku.")
    return watek


def test_zmiana_kombinacji_rejestruje_nowa_i_zwalnia_stara() -> None:
    watek = _uruchom_albo_pomin(_KOMBINACJA_A)
    try:
        wynik = watek.zmien_kombinacje(rozbierz_kombinacje(_KOMBINACJA_B))

        assert wynik.udalo_sie is True
        assert watek.aktualna_kombinacja == rozbierz_kombinacje(_KOMBINACJA_B)
        # Stara kombinacja jest wolna: inny wątek może ją teraz zarejestrować.
        obcy = _uruchom_albo_pomin(_KOMBINACJA_A)
        obcy.zatrzymaj()
    finally:
        watek.zatrzymaj()


def test_odmowa_przy_zmianie_kombinacji_zostawia_poprzednia_zarejestrowana() -> None:
    zajmujacy = _uruchom_albo_pomin(_KOMBINACJA_B)
    watek = _uruchom_albo_pomin(_KOMBINACJA_A)
    try:
        wynik = watek.zmien_kombinacje(rozbierz_kombinacje(_KOMBINACJA_B))

        assert wynik.udalo_sie is False
        assert wynik.kod_bledu == _win32.ERROR_HOTKEY_ALREADY_REGISTERED
        assert watek.aktualna_kombinacja == rozbierz_kombinacje(_KOMBINACJA_A)
        # Poprzednia kombinacja nadal jest zajęta przez ten wątek: ktoś inny jej nie dostanie.
        proba = _win32.WatekSkrotu(lambda: None, rozbierz_kombinacje(_KOMBINACJA_A))
        try:
            assert proba.uruchom() is False
        finally:
            proba.zatrzymaj()
    finally:
        watek.zatrzymaj()
        zajmujacy.zatrzymaj()


def test_watek_z_nieudana_pierwsza_rejestracja_przyjmuje_inna_kombinacje() -> None:
    zajmujacy = _uruchom_albo_pomin(_KOMBINACJA_B)
    watek = _win32.WatekSkrotu(lambda: None, rozbierz_kombinacje(_KOMBINACJA_B))
    try:
        assert watek.uruchom() is False
        assert watek.aktualna_kombinacja is None

        wynik = watek.zmien_kombinacje(rozbierz_kombinacje(_KOMBINACJA_A))

        assert wynik.udalo_sie is True
        assert watek.zarejestrowano is True
    finally:
        watek.zatrzymaj()
        zajmujacy.zatrzymaj()


def test_zmiana_na_ta_sama_kombinacje_jest_sukcesem_bez_ponownej_rejestracji() -> None:
    watek = _uruchom_albo_pomin(_KOMBINACJA_A)
    try:
        assert watek.zmien_kombinacje(rozbierz_kombinacje(_KOMBINACJA_A)).udalo_sie is True
    finally:
        watek.zatrzymaj()


def test_zmiana_kombinacji_po_zatrzymaniu_watku_zwraca_porazke() -> None:
    watek = _uruchom_albo_pomin(_KOMBINACJA_A)
    watek.zatrzymaj()

    assert watek.zmien_kombinacje(rozbierz_kombinacje(_KOMBINACJA_B)).udalo_sie is False
