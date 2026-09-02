"""Testy dwóch limitów treści: liczby słów i rozmiaru w bajtach."""

from __future__ import annotations

from gnb.packing.limity import (
    LimityPakowania,
    liczba_bajtow,
    miesci_sie,
    przekracza_limit,
)


def test_liczba_bajtow_liczy_kodowanie_utf8() -> None:
    assert liczba_bajtow("abc") == 3
    # Znak „ą” zajmuje w UTF-8 dwa bajty, więc trzy litery ze znakiem diakrytycznym
    # to więcej bajtów niż znaków.
    assert liczba_bajtow("ąćż") == 6


def test_miesci_sie_wymaga_obu_limitow_naraz() -> None:
    limity = LimityPakowania(limit_slow=5, limit_bajtow=100)
    assert miesci_sie("jedno dwa trzy", limity)
    # Za dużo słów, choć rozmiar w normie.
    assert not miesci_sie("jedno dwa trzy cztery pięć sześć", limity)
    # Rozmiar poza normą, choć słów mało.
    assert not miesci_sie("x" * 200, limity)


def test_przekracza_limit_jest_zaprzeczeniem_miesci_sie() -> None:
    limity = LimityPakowania(limit_slow=3, limit_bajtow=50)
    assert przekracza_limit("a b c d", limity) is True
    assert przekracza_limit("a b c", limity) is False


def test_z_konfiguracji_przelicza_megabajty_na_bajty() -> None:
    limity = LimityPakowania.z_konfiguracji(bezpieczny_limit_slow=480_000, bezpieczny_limit_mb=190)
    assert limity.limit_slow == 480_000
    assert limity.limit_bajtow == 190 * 1024 * 1024


def test_pusty_tekst_miesci_sie_zawsze() -> None:
    assert miesci_sie("", LimityPakowania(limit_slow=0, limit_bajtow=0))
