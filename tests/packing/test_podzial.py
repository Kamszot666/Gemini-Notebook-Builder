"""Testy podziału treści przekraczającej limit na części.

Sprawdzają cztery poziomy hierarchii granic z sekcji dziesiątej CLAUDE.md oraz
zasadę bezwzględną: podział nie może stracić ani jednego słowa.
"""

from __future__ import annotations

from gnb.packing.limity import LimityPakowania
from gnb.packing.podzial import (
    OSTRZEZENIE_PODZIAL_W_ZDANIU,
    OSTRZEZENIE_SLOWO_PONAD_LIMIT,
    podziel_na_czesci,
)

_DUZY_ROZMIAR = 10_000_000


def _wszystkie_slowa(tekst: str) -> list[str]:
    return tekst.split()


def test_tresc_w_limicie_zostaje_jedna_czescia_bez_ostrzezen() -> None:
    tekst = "Krótka notatka o porządkowaniu źródeł przed wgraniem."
    wynik = podziel_na_czesci(tekst, LimityPakowania(limit_slow=100, limit_bajtow=_DUZY_ROZMIAR))

    assert wynik.czesci == [tekst]
    assert wynik.ostrzezenia == []


def test_podzial_na_granicy_akapitu_nie_lamie_akapitow() -> None:
    akapit = " ".join(["slowo"] * 8)
    tekst = "\n\n".join([akapit, akapit, akapit])
    limity = LimityPakowania(limit_slow=10, limit_bajtow=_DUZY_ROZMIAR)

    wynik = podziel_na_czesci(tekst, limity)

    assert len(wynik.czesci) == 3
    assert wynik.ostrzezenia == []
    # Skoro podział wypadł wyłącznie na granicy akapitu, sklejenie części tym
    # samym separatorem odtwarza tekst wejściowy co do znaku.
    assert "\n\n".join(wynik.czesci) == tekst
    for czesc in wynik.czesci:
        assert czesc == akapit


def test_zbyt_duzy_akapit_dzieli_sie_na_granicy_zdania_bez_ostrzezenia() -> None:
    zdanie = "To jest bardzo krótkie zdanie testowe."
    akapit = " ".join([zdanie] * 4)
    limity = LimityPakowania(limit_slow=10, limit_bajtow=_DUZY_ROZMIAR)

    wynik = podziel_na_czesci(akapit, limity)

    assert len(wynik.czesci) == 4
    assert wynik.ostrzezenia == []
    assert " ".join(wynik.czesci) == akapit
    for czesc in wynik.czesci:
        assert czesc.endswith(".")


def test_zbyt_dlugie_zdanie_dzieli_sie_na_granicy_slowa_z_ostrzezeniem() -> None:
    zdanie = " ".join(["slowo"] * 20)
    limity = LimityPakowania(limit_slow=5, limit_bajtow=_DUZY_ROZMIAR)

    wynik = podziel_na_czesci(zdanie, limity)

    assert len(wynik.czesci) == 4
    assert OSTRZEZENIE_PODZIAL_W_ZDANIU in wynik.ostrzezenia
    # Żadne słowo nie może zniknąć ani zostać rozcięte.
    assert _wszystkie_slowa(" ".join(wynik.czesci)) == _wszystkie_slowa(zdanie)
    for czesc in wynik.czesci:
        assert len(czesc.split()) <= 5


def test_limit_rozmiaru_dziala_niezaleznie_od_limitu_slow() -> None:
    tekst = "abcd efgh\n\nijkl mnop"
    limity = LimityPakowania(limit_slow=1_000, limit_bajtow=12)

    wynik = podziel_na_czesci(tekst, limity)

    assert wynik.czesci == ["abcd efgh", "ijkl mnop"]
    assert wynik.ostrzezenia == []


def test_fragment_bez_bialych_znakow_ponad_limit_zostaje_w_calosci_z_ostrzezeniem() -> None:
    tekst = "x" * 100
    limity = LimityPakowania(limit_slow=1_000, limit_bajtow=10)

    wynik = podziel_na_czesci(tekst, limity)

    assert wynik.czesci == [tekst]
    assert wynik.ostrzezenia == [OSTRZEZENIE_SLOWO_PONAD_LIMIT]


def test_podzial_jest_powtarzalny() -> None:
    tekst = "\n\n".join(" ".join(["wyraz"] * 7) for _ in range(9))
    limity = LimityPakowania(limit_slow=15, limit_bajtow=_DUZY_ROZMIAR)

    pierwszy = podziel_na_czesci(tekst, limity)
    drugi = podziel_na_czesci(tekst, limity)

    assert pierwszy == drugi


def test_zadne_slowo_nie_ginie_przy_podziale_wielopoziomowym() -> None:
    akapit_krotki = " ".join(["a"] * 3)
    akapit_dlugi = " ".join(["b"] * 40)
    tekst = "\n\n".join([akapit_krotki, akapit_dlugi, akapit_krotki])
    limity = LimityPakowania(limit_slow=12, limit_bajtow=_DUZY_ROZMIAR)

    wynik = podziel_na_czesci(tekst, limity)

    assert _wszystkie_slowa(" ".join(wynik.czesci)) == _wszystkie_slowa(tekst)
    for czesc in wynik.czesci:
        assert len(czesc.split()) <= 12
