"""Testy przepisania Markdown na czysty tekst dla wersji TXT dokumentu.

Najważniejszy test porównuje wersję TXT z wersją MD pliku
`tests/dane/dokument_strukturalny.md` i sprawdza, że z wersji TXT zniknęły
wyłącznie znaki składni, a nie treść: żaden wiersz tekstu ani żadna komórka
tabeli nie może przepaść.
"""

from __future__ import annotations

import re
from pathlib import Path

from gnb.normalization.normalizacja import znormalizuj
from gnb.output.tekst_bez_znacznikow import zamien_markdown_na_tekst

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"
PLIK_STRUKTURALNY = KATALOG_DANYCH / "dokument_strukturalny.md"

_PREFIKSY_BLOKOWE = re.compile(r"^\s*(#{1,6}\s+|[-*+]\s+|\d+[.)]\s+|>\s?)")
_ZNACZNIKI_WEWNATRZWIERSZOWE = re.compile(r"[*`]")
_WIERSZ_ROZDZIELAJACY_TABELI = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _wersja_txt(zrodlo: str) -> str:
    """Buduje wersję TXT dokładnie tak, jak robi to potok przetwarzania."""
    return znormalizuj(zamien_markdown_na_tekst(zrodlo))


def _bez_skladni(wiersz: str) -> str:
    """Usuwa z wiersza Markdown znaki składni, zostawiając samą treść."""
    bez_prefiksu = _PREFIKSY_BLOKOWE.sub("", wiersz)
    return _ZNACZNIKI_WEWNATRZWIERSZOWE.sub("", bez_prefiksu).strip()


def _komorki_tabeli(zrodlo: str) -> list[str]:
    """Zwraca treść wszystkich komórek tabel z dokumentu Markdown."""
    komorki: list[str] = []
    for wiersz in zrodlo.splitlines():
        oczyszczony = wiersz.strip()
        if not oczyszczony.startswith("|") or _WIERSZ_ROZDZIELAJACY_TABELI.match(oczyszczony):
            continue
        komorki.extend(
            czesc.strip() for czesc in oczyszczony.strip("|").split("|") if czesc.strip()
        )
    return komorki


def test_wersja_txt_nie_gubi_zadnego_wiersza_tresci() -> None:
    zrodlo = PLIK_STRUKTURALNY.read_text(encoding="utf-8")
    txt = _wersja_txt(zrodlo)

    for wiersz in zrodlo.splitlines():
        if wiersz.strip().startswith("|"):
            continue
        tresc = _bez_skladni(wiersz)
        if not tresc:
            continue
        assert tresc in txt, f"z wersji TXT zniknął wiersz treści: {tresc}"


def test_wersja_txt_nie_gubi_zadnej_komorki_tabeli() -> None:
    zrodlo = PLIK_STRUKTURALNY.read_text(encoding="utf-8")
    txt = _wersja_txt(zrodlo)

    komorki = _komorki_tabeli(zrodlo)
    assert komorki, "plik testowy ma zawierać tabelę"
    for komorka in komorki:
        assert komorka in txt, f"z wersji TXT zniknęła komórka tabeli: {komorka}"


def test_wersja_txt_rozni_sie_od_wersji_md_tylko_brakiem_skladni() -> None:
    zrodlo = PLIK_STRUKTURALNY.read_text(encoding="utf-8")
    txt = _wersja_txt(zrodlo)
    md = znormalizuj(zrodlo)

    assert txt != md
    assert "#" not in txt
    assert "|" not in txt
    assert "**" not in txt


def test_naglowek_staje_sie_osobnym_wierszem_bez_krat() -> None:
    txt = _wersja_txt("# Tytuł dokumentu\n\nAkapit pierwszy.\n")
    assert txt.splitlines()[0] == "Tytuł dokumentu"


def test_elementy_listy_zaczynaja_sie_myslnikiem_i_spacja() -> None:
    txt = _wersja_txt("- Pierwszy\n- Drugi\n")
    assert txt.splitlines() == ["- Pierwszy", "- Drugi"]


def test_lista_numerowana_zachowuje_numeracje() -> None:
    txt = _wersja_txt("1. Pierwszy krok\n2. Drugi krok\n3. Trzeci krok\n")
    assert txt.splitlines() == ["1. Pierwszy krok", "2. Drugi krok", "3. Trzeci krok"]


def test_lista_numerowana_zaczynajaca_sie_od_innego_numeru_zachowuje_start() -> None:
    txt = _wersja_txt("3. Trzeci krok\n4. Czwarty krok\n")
    assert txt.splitlines() == ["3. Trzeci krok", "4. Czwarty krok"]


def test_numeracja_kazdej_listy_liczy_sie_od_poczatku() -> None:
    txt = _wersja_txt("1. Pierwsza lista\n\nAkapit rozdzielający.\n\n1. Druga lista\n")
    wiersze = txt.splitlines()
    assert wiersze[0] == "1. Pierwsza lista"
    assert wiersze[-1] == "1. Druga lista"


def test_lista_zagniezdzona_jest_oddana_wcieciem_dwoch_spacji() -> None:
    txt = _wersja_txt("- Poziom pierwszy\n    - Poziom drugi\n")
    assert txt.splitlines() == ["- Poziom pierwszy", "  - Poziom drugi"]


def test_trzeci_poziom_listy_ma_wciecie_czterech_spacji() -> None:
    zrodlo = "- Poziom pierwszy\n    - Poziom drugi\n        - Poziom trzeci\n"
    assert _wersja_txt(zrodlo).splitlines() == [
        "- Poziom pierwszy",
        "  - Poziom drugi",
        "    - Poziom trzeci",
    ]


def test_lista_numerowana_zagniezdzona_w_wypunktowanej_zachowuje_oba_zapisy() -> None:
    zrodlo = "- Punkt nadrzędny\n    1. Pierwszy podpunkt\n    2. Drugi podpunkt\n"
    assert _wersja_txt(zrodlo).splitlines() == [
        "- Punkt nadrzędny",
        "  1. Pierwszy podpunkt",
        "  2. Drugi podpunkt",
    ]


def test_tabela_jest_rozpisana_nazwa_dwukropek_wartosc() -> None:
    zrodlo = "| Metoda | Koszt |\n| --- | --- |\n| MinHash | średni |\n"
    assert _wersja_txt(zrodlo).splitlines() == ["Metoda: MinHash", "Koszt: średni"]


def test_blok_kodu_traci_ogrodzenie_i_zachowuje_wciecia() -> None:
    zrodlo = "Opis.\n\n```python\ndef f():\n    return 1\n```\n"
    wiersze = _wersja_txt(zrodlo).splitlines()
    assert "def f():" in wiersze
    assert "    return 1" in wiersze
    assert "```" not in "\n".join(wiersze)


def test_znaczniki_wewnatrzwierszowe_znikaja_a_tekst_zostaje() -> None:
    txt = _wersja_txt("To jest **ważne**, to _mniej_, a to `kod`.\n")
    assert txt == "To jest ważne, to mniej, a to kod."


def test_odnosnik_zachowuje_tresc_i_adres() -> None:
    txt = _wersja_txt("Zobacz [dokumentację](https://example.org/dokument).\n")
    assert txt == "Zobacz dokumentację (https://example.org/dokument)."


def test_cytat_blokowy_staje_sie_zwyklym_tekstem() -> None:
    txt = _wersja_txt("> Cytowane zdanie.\n")
    assert txt == "Cytowane zdanie."


def test_blok_surowego_html_nie_jest_gubiony() -> None:
    txt = _wersja_txt("<div>Treść w surowym HTML</div>\n")
    assert "Treść w surowym HTML" in txt


def test_tekst_bez_znacznikow_jest_stabilny_przy_powtorzeniu() -> None:
    zrodlo = PLIK_STRUKTURALNY.read_text(encoding="utf-8")
    assert _wersja_txt(zrodlo) == _wersja_txt(zrodlo)
