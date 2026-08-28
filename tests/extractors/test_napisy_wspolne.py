"""Testy sklejania segmentów napisów w akapity.

Moduł `gnb.extractors.napisy_wspolne` obsługuje dwa mechanizmy, które łatwo
napisać za szeroko i po cichu stracić przez nie treść: usuwanie oznaczeń
dźwięków oraz usuwanie powtórzeń wynikających z przewijania tekstu na ekranie.
Te testy pilnują granicy obu mechanizmów w obie strony: prawdziwe oznaczenie
dźwięku ma znikać, a treść merytoryczna ma zostawać.
"""

from __future__ import annotations

from gnb.extractors.napisy_wspolne import zapisz_akapity, zbuduj_akapity
from gnb.ingestion.youtube import SegmentNapisow


def _tekst_z_segmentow(*teksty: str) -> str:
    segmenty = [
        SegmentNapisow(poczatek_sekundy=float(numer), tekst=tekst)
        for numer, tekst in enumerate(teksty)
    ]
    return zapisz_akapity(zbuduj_akapity(segmenty))


def test_nawias_z_data_zostaje_w_tresci() -> None:
    """Zakres lat w nawiasie nie jest oznaczeniem dźwięku i nie może zniknąć."""
    wynik = _tekst_z_segmentow("Wojna trwała (1939-1945) i objęła cały kontynent.")

    assert wynik == "Wojna trwała (1939-1945) i objęła cały kontynent."


def test_nawias_z_liczba_zostaje_w_tresci() -> None:
    wynik = _tekst_z_segmentow("Ustawa (art. 12) weszła w życie.")

    assert "(art. 12)" in wynik


def test_dluzszy_nawias_wewnatrz_zdania_zostaje_w_tresci() -> None:
    """Nawias dłuższy niż krótka etykieta jest zdaniem pobocznym wypowiedzi."""
    wynik = _tekst_z_segmentow("Metoda (co warto od razu podkreślić) wymaga cierpliwości.")

    assert "(co warto od razu podkreślić)" in wynik


def test_krotkie_oznaczenie_dzwieku_jest_usuwane() -> None:
    wynik = _tekst_z_segmentow("[muzyka] Dzień dobry państwu (śmiech) zaczynamy.")

    assert wynik == "Dzień dobry państwu zaczynamy."


def test_segment_zlozony_wylacznie_z_nawiasu_jest_usuwany() -> None:
    """Segment będący samym nawiasem to etykieta, nawet gdy jest długa."""
    wynik = _tekst_z_segmentow(
        "Zaczynamy wykład.",
        "[spokojna muzyka gra w tle przez dłuższą chwilę]",
        "Temat jest trudny.",
    )

    assert wynik == "Zaczynamy wykład. Temat jest trudny."


def test_powtorzone_krotkie_zdanie_nie_ginie() -> None:
    """Zdanie powtórzone po innej wypowiedzi jest treścią, a nie nakładaniem się.

    Wcześniej kasowany był każdy segment, którego tekst występował gdziekolwiek
    w bieżącym akapicie, więc sekwencja „Tak.”, pytanie, „Tak.” traciła drugie
    wystąpienie.
    """
    wynik = _tekst_z_segmentow("Tak.", "Czy to jest właściwa odpowiedź?", "Tak.")

    assert wynik == "Tak. Czy to jest właściwa odpowiedź? Tak."


def test_nakladajaca_sie_koncowka_segmentu_jest_usuwana() -> None:
    """Przewijanie tekstu na ekranie nadal nie dubluje treści."""
    wynik = _tekst_z_segmentow(
        "Dzisiaj porozmawiamy o tym,", "porozmawiamy o tym, jak zbudować bazę wiedzy."
    )

    assert wynik == "Dzisiaj porozmawiamy o tym, jak zbudować bazę wiedzy."


def test_powtorzenie_wewnatrz_wyrazu_nie_obcina_slowa() -> None:
    """Porównanie idzie po słowach, więc końcówka wyrazu nie kasuje całego wyrazu."""
    wynik = _tekst_z_segmentow("To była właściwa odpowiedź", "iedź dalej tą drogą.")

    assert "iedź dalej tą drogą." in wynik
