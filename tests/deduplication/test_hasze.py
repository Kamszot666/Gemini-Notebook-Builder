"""Testy kluczy porównawczych dwóch pierwszych etapów deduplikacji."""

from __future__ import annotations

import unicodedata

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


def test_klucz_kosmetyczny_nie_zleca_slow_rozniacych_sie_diakrytykiem() -> None:
    """„pas” i „pąs” to różne słowa i muszą dawać różne klucze.

    Klucz etapu drugiego trafia w orkiestratorze wprost w decyzję „duplikat”,
    bez progu i bez ścieżki do rozstrzygnięcia, więc jego zlanie tych dwóch słów
    usunęłoby bezpowrotnie jedno z dwóch różnych źródeł. Wersja klucza oparta na
    rozkładzie NFKD i usuwaniu znaków łączących dawała tu ten sam klucz.
    """
    assert klucz_kosmetyczny("pas") != klucz_kosmetyczny("pąs")
    assert klucz_kosmetyczny("łąka na wzgórzu") != klucz_kosmetyczny("laka na wzgorzu")
    assert klucz_kosmetyczny("zażółć gęślą jaźń") != klucz_kosmetyczny("zazolc gesla jazn")


def test_klucz_kosmetyczny_jest_niezalezny_od_postaci_zapisu_diakrytyku() -> None:
    """Ogonek zapisany osobno i w jednym znaku daje ten sam klucz.

    To jest normalizacja NFC, czyli składanie znaków, a nie NFKD, czyli rozkład
    zgodności, który dodatkowo zdejmuje diakrytyk.
    """
    zlozony = "pąs"
    rozlozony = unicodedata.normalize("NFD", zlozony)
    assert zlozony != rozlozony
    assert klucz_kosmetyczny(zlozony) == klucz_kosmetyczny(rozlozony)
    assert klucz_kosmetyczny(zlozony) != klucz_kosmetyczny("pas")


def test_klucz_kosmetyczny_nie_skleja_slow_po_usunieciu_lacznika() -> None:
    """Usunięcie łącznika nie może utworzyć słowa, którego w tekście nie było.

    Bez rozdzielania grup znaków treści spacją „biało-czerwony” i „białoczerwony”
    dawałyby ten sam klucz co „biało czerwony”, a to trzy różne zapisy.
    """
    assert klucz_kosmetyczny("biało-czerwony") == klucz_kosmetyczny("biało czerwony")
    assert klucz_kosmetyczny("białoczerwony") != klucz_kosmetyczny("biało czerwony")
