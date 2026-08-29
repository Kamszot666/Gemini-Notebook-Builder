"""Testy kluczy porównawczych dwóch pierwszych etapów deduplikacji."""

from __future__ import annotations

from gnb.deduplication.hasze import hash_tresci, klucz_kosmetyczny


def test_hash_tresci_jest_rowny_dla_identycznego_tekstu_i_rozny_dla_innego() -> None:
    tekst = "Pierwsze zdanie. Drugie zdanie o czymś innym."
    assert hash_tresci(tekst) == hash_tresci(tekst)
    assert hash_tresci(tekst) != hash_tresci(tekst + " Trzecie zdanie.")


def test_hash_tresci_reaguje_na_sama_zmiane_wielkosci_liter() -> None:
    """Etap pierwszy porównuje treść dokładnie, więc wielkość liter go rozróżnia.

    To rozróżnienie jest właśnie powodem, dla którego istnieje osobny etap drugi.
    """
    assert hash_tresci("Baza wiedzy") != hash_tresci("baza wiedzy")


def test_klucz_kosmetyczny_pomija_interpunkcje_odstepy_i_wielkosc_liter() -> None:
    pierwszy = "Baza wiedzy dla asystenta AI jest lepsza, gdy zawiera mniej powtórzeń."
    drugi = "  baza   wiedzy dla asystenta ai jest lepsza gdy zawiera mniej powtórzeń  "
    assert klucz_kosmetyczny(pierwszy) == klucz_kosmetyczny(drugi)


def test_klucz_kosmetyczny_rozroznia_teksty_o_innej_tresci_slownej() -> None:
    """Klucz nie może zlewać tekstów, które różnią się słowami, a nie kosmetyką."""
    assert klucz_kosmetyczny("kot pije mleko") != klucz_kosmetyczny("pies pije mleko")


def test_klucz_kosmetyczny_nie_skleja_slow_po_usunieciu_lacznika() -> None:
    """Usunięcie łącznika nie może utworzyć słowa, którego w tekście nie było.

    Bez rozdzielania grup znaków treści spacją „biało-czerwony” i „białoczerwony”
    dawałyby ten sam klucz co „biało czerwony”, a to trzy różne zapisy.
    """
    assert klucz_kosmetyczny("biało-czerwony") == klucz_kosmetyczny("biało czerwony")
    assert klucz_kosmetyczny("białoczerwony") != klucz_kosmetyczny("biało czerwony")
