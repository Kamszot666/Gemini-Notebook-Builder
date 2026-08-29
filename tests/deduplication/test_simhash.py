"""Testy SimHash na shinglach i porównania sekwencyjnego krótkich tekstów."""

from __future__ import annotations

from gnb.deduplication.simhash import (
    LICZBA_BITOW,
    odleglosc_hamminga,
    podobienstwo_sekwencyjne,
    podobienstwo_simhash,
    simhash_tekstu,
)

_DLUGI_TEKST = (
    "Baza wiedzy dla asystenta sztucznej inteligencji jest tym lepsza, im mniej "
    "zawiera powtórzeń oraz im dokładniej wiadomo, skąd pochodzi każdy pojedynczy "
    "fragment tekstu. Najczęstszym błędem jest wrzucanie do jednego zbioru "
    "wszystkiego, co wpadnie w ręce, bez sprawdzenia, czy te same treści nie "
    "występują już w kilku innych miejscach tego samego zbioru danych. Drugim "
    "częstym błędem jest usuwanie materiałów tylko dlatego, że na pierwszy rzut "
    "oka wyglądają podobnie do innych, mimo że niosą własną, unikalną informację. "
) * 3


def test_simhash_jest_powtarzalny_miedzy_wywolaniami() -> None:
    """Odcisk musi być stały, bo decyzja o duplikacie ma być powtarzalna.

    Gdyby SimHash korzystał z wbudowanej funkcji `hash`, ten test czerwieniłby
    się losowo, bo `hash` dla łańcuchów jest losowany przy starcie procesu.
    """
    assert simhash_tekstu(_DLUGI_TEKST) == simhash_tekstu(_DLUGI_TEKST)


def test_simhash_tego_samego_tekstu_ma_zerowa_odleglosc() -> None:
    odcisk = simhash_tekstu(_DLUGI_TEKST)
    assert odleglosc_hamminga(odcisk, odcisk) == 0
    assert podobienstwo_simhash(odcisk, odcisk) == 1.0


def test_simhash_bliskiego_tekstu_jest_bliski_a_odleglego_daleki() -> None:
    prawie_to_samo = _DLUGI_TEKST.replace("Najczęstszym", "Bardzo częstym")
    zupelnie_inny = (
        "Wczoraj wieczorem padał deszcz, a rano nad rzeką unosiła się gęsta mgła, "
        "przez którą ledwie było widać drugi brzeg i stojące tam wierzby. "
    ) * 3

    bliskie = podobienstwo_simhash(simhash_tekstu(_DLUGI_TEKST), simhash_tekstu(prawie_to_samo))
    dalekie = podobienstwo_simhash(simhash_tekstu(_DLUGI_TEKST), simhash_tekstu(zupelnie_inny))

    assert bliskie > 0.9
    assert dalekie < 0.75
    assert bliskie > dalekie


def test_odleglosc_hamminga_liczy_rozniace_sie_bity() -> None:
    assert odleglosc_hamminga(0b1011, 0b1110) == 2
    assert odleglosc_hamminga(0, (1 << LICZBA_BITOW) - 1) == LICZBA_BITOW


def test_podobienstwo_sekwencyjne_rozroznia_bliskie_i_odlegle_krotkie_teksty() -> None:
    baza = "Krótka notatka o przygotowaniu materiałów do notatnika."
    bliska = "Krótka notatka o przygotowaniu materiałów do notatnika AI."
    daleka = "Zupełnie inny tekst o pogodzie i spacerze nad rzeką."

    assert podobienstwo_sekwencyjne(baza, baza) == 1.0
    assert podobienstwo_sekwencyjne(baza, bliska) > 0.8
    assert podobienstwo_sekwencyjne(baza, daleka) < 0.5
