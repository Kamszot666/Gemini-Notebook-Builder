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
    from gnb.hotkeys import _win32


def test_watek_skrotu_rejestruje_i_wyrejestrowuje_skrot() -> None:
    """Po `zatrzymaj` skrót musi być wyrejestrowany — sprawdzone ponowną rejestracją.

    Gdy inny proces (na przykład wcześniej uruchomiony serwer interfejsu) trzyma
    już tę kombinację, test się pomija: to jest wykrywanie konfliktu, które ma
    swój własny czytelny komunikat w `obsluga.py`, nie powód do czerwienienia
    tego testu.
    """
    nacisniecia: list[None] = []
    watek = _win32.WatekSkrotu(lambda: nacisniecia.append(None))
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
    drugi_watek = _win32.WatekSkrotu(lambda: None)
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
