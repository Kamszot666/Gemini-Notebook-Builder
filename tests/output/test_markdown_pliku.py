"""Testy składania plików MD: nagłówki źródeł w grupie, hierarchia i liczenie słów."""

from __future__ import annotations

from gnb.core.liczenie_slow import policz_slowa
from gnb.extractors.markdown import utworz_parser
from gnb.output.markdown_pliku import (
    FragmentGrupyMarkdown,
    naglowek_metadanych_jako_liste,
    policz_slowa_markdown,
    przesun_naglowki,
    tytul_zrodla,
    zloz_plik_grupy_markdown,
)
from gnb.output.tekst_bez_znacznikow import zamien_markdown_na_tekst


def _naglowki(tekst: str) -> list[tuple[int, str]]:
    """Poziomy i treści nagłówków dokumentu, odczytane niezależnym parserem."""
    tokeny = utworz_parser().parse(tekst)
    return [
        (int(token.tag[1:]), tokeny[indeks + 1].content)
        for indeks, token in enumerate(tokeny)
        if token.type == "heading_open"
    ]


def test_przesuniecie_podnosi_najplytszy_naglowek_do_poziomu_docelowego() -> None:
    tekst = "# Tytuł\n\nAkapit.\n\n## Sekcja\n\n### Podsekcja"

    wynik = przesun_naglowki(tekst, 3)

    assert _naglowki(wynik) == [(3, "Tytuł"), (4, "Sekcja"), (5, "Podsekcja")]


def test_przesuniecie_zachowuje_wzgledna_hierarchie_a_poziom_szosty_jest_sufitem() -> None:
    tekst = "# A\n\n#### B\n\n###### C"

    assert _naglowki(przesun_naglowki(tekst, 3)) == [(3, "A"), (6, "B"), (6, "C")]


def test_naglowki_plytsze_niz_docelowy_nie_sa_przesuwane_gdy_juz_sa_gleboko() -> None:
    tekst = "#### Głęboki\n\nTreść."

    assert przesun_naglowki(tekst, 3) == tekst


def test_tekst_bez_naglowkow_zostaje_bez_zmian() -> None:
    tekst = "Sam akapit.\n\n- lista"

    assert przesun_naglowki(tekst, 3) == tekst


def test_naglowek_z_podkresleniem_staje_sie_naglowkiem_z_krzyzykami() -> None:
    tekst = "Tytuł\n=====\n\nAkapit.\n\nSekcja\n------"

    wynik = przesun_naglowki(tekst, 3)

    assert _naglowki(wynik) == [(3, "Tytuł"), (4, "Sekcja")]
    assert "=====" not in wynik and "------" not in wynik


def test_wiersz_z_krzyzykiem_w_bloku_kodu_nie_jest_przesuwany() -> None:
    tekst = "# Prawdziwy\n\n```\n# komentarz w kodzie\n```\n"

    wynik = przesun_naglowki(tekst, 3)

    assert "# komentarz w kodzie" in wynik
    assert "### komentarz w kodzie" not in wynik
    assert _naglowki(wynik) == [(3, "Prawdziwy")]


def test_nagłowek_zamkniety_krzyzykami_traci_je_po_przesunieciu_poprawnie() -> None:
    wynik = przesun_naglowki("# Tytuł #\n\nTreść.", 3)

    assert _naglowki(wynik) == [(3, "Tytuł")]


def test_tytul_zrodla_bierze_tytul_potem_plik_potem_adres_potem_identyfikator() -> None:
    assert tytul_zrodla("Tytuł: Artykuł\nPlik: a.txt") == "Artykuł"
    assert tytul_zrodla("Typ źródła: dokument\nPlik: a.txt\nAdres: https://x.pl") == "a.txt"
    assert tytul_zrodla("Adres: https://x.pl\nIdentyfikator źródła: id-1") == "https://x.pl"
    assert tytul_zrodla("Identyfikator źródła: id-1") == "id-1"
    assert tytul_zrodla("") == "Źródło bez tytułu"


def test_naglowek_metadanych_jako_lista_escapuje_wartosci() -> None:
    wynik = naglowek_metadanych_jako_liste("Tytuł: *ważne*\nAdres: https://x.pl/a_b")

    assert wynik == "- Tytuł: \\*ważne\\*\n- Adres: https://x.pl/a_b"


def test_plik_grupy_ma_jeden_naglowek_pierwszego_poziomu_i_drugiego_na_zrodlo() -> None:
    tekst = zloz_plik_grupy_markdown(
        [
            FragmentGrupyMarkdown(
                "Tytuł: Pierwszy\nIdentyfikator źródła: a", "# Pierwszy\n\nTreść A."
            ),
            FragmentGrupyMarkdown(
                "Tytuł: Drugi\nIdentyfikator źródła: b", "# Drugi\n\n## Część\n\nTreść B."
            ),
        ],
        tytul_pliku="Grupa „Notatki”",
    )

    assert _naglowki(tekst) == [
        (1, "Grupa „Notatki”"),
        (2, "Pierwszy"),
        (3, "Pierwszy"),
        (2, "Drugi"),
        (3, "Drugi"),
        (4, "Część"),
    ]


def test_metadane_zrodla_w_grupie_sa_lista_pod_naglowkiem_a_nie_naglowkiem() -> None:
    tekst = zloz_plik_grupy_markdown(
        [FragmentGrupyMarkdown("Tytuł: A\nIdentyfikator źródła: id-a", "Treść.")],
        tytul_pliku="Grupa „G”",
    )

    assert "## A\n\n- Tytuł: A\n- Identyfikator źródła: id-a\n\nTreść." in tekst
    assert not any(
        wiersz.startswith("#") and "Identyfikator" in wiersz for wiersz in tekst.split("\n")
    )


def test_tytul_zrodla_z_podejrzana_skladnia_jest_escapowany_w_naglowku() -> None:
    tekst = zloz_plik_grupy_markdown(
        [FragmentGrupyMarkdown("Tytuł: *Ważne* #1", "Treść.")], tytul_pliku="Grupa"
    )

    assert _naglowki(tekst)[1] == (2, "\\*Ważne\\* #1")
    assert zamien_markdown_na_tekst(tekst).split()[:4] == ["Grupa", "*Ważne*", "#1", "-"]


def test_liczenie_slow_md_pomija_znaczniki_skladni_i_zgadza_sie_z_txt() -> None:
    tekst_md = (
        "# Tytuł\n\nAkapit z **pogrubieniem**.\n\n- jeden\n- dwa\n\n"
        "| a | b |\n| --- | --- |\n| 1 | 2 |"
    )

    tekst_txt = zamien_markdown_na_tekst(tekst_md)

    assert policz_slowa_markdown(tekst_md) == policz_slowa(tekst_txt)
    assert policz_slowa_markdown(tekst_md) < len(tekst_md.split()), (
        "znaczniki składni (krzyżyki, gwiazdki, kreski tabeli) nie są słowami"
    )
    assert "**" not in tekst_txt
