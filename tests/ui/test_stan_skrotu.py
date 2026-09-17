"""Testy stanu globalnego skrótu widocznego w interfejsie: aktywny projekt i komunikat."""

from __future__ import annotations

from gnb.ui.stan_skrotu import AktywnyProjektSkrotu, OstatniKomunikatSkrotu


def test_aktywny_projekt_jest_pusty_na_starcie() -> None:
    assert AktywnyProjektSkrotu().aktualny() is None


def test_aktywny_projekt_po_ustawieniu() -> None:
    stan = AktywnyProjektSkrotu()
    stan.ustaw("Projekt testowy")

    assert stan.aktualny() == "Projekt testowy"


def test_aktywny_projekt_zmiana_nadpisuje_poprzedni() -> None:
    stan = AktywnyProjektSkrotu()
    stan.ustaw("Pierwszy")
    stan.ustaw("Drugi")

    assert stan.aktualny() == "Drugi"


def test_ostatni_komunikat_jest_pusty_na_starcie() -> None:
    assert OstatniKomunikatSkrotu().aktualny() is None


def test_ostatni_komunikat_po_ustawieniu_niesie_tekst_i_wynik() -> None:
    stan = OstatniKomunikatSkrotu()
    stan.ustaw("Dodano adres strony: Przykład", sukces=True)

    komunikat = stan.aktualny()
    assert komunikat is not None
    assert komunikat.tekst == "Dodano adres strony: Przykład"
    assert komunikat.sukces is True


def test_ostatni_komunikat_porazki() -> None:
    stan = OstatniKomunikatSkrotu()
    stan.ustaw("Brak aktywnego projektu skrótu.", sukces=False)

    komunikat = stan.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is False


def test_ostatni_komunikat_zapamietuje_tylko_najnowszy() -> None:
    stan = OstatniKomunikatSkrotu()
    stan.ustaw("Pierwszy", sukces=True)
    stan.ustaw("Drugi", sukces=False)

    komunikat = stan.aktualny()
    assert komunikat is not None
    assert komunikat.tekst == "Drugi"
    assert komunikat.sukces is False
