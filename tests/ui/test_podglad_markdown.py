"""Testy zamiany pliku Markdown na bezpieczny HTML do podglądu jako strona.

To wąski wyjątek od zasady, że treść ze źródeł nigdy nie trafia do przeglądarki
jako HTML, więc większość testów to próby wstrzyknięcia: każda ma się skończyć
tekstem, a nie znacznikiem.
"""

from __future__ import annotations

import re

import pytest

from gnb.ui.podglad_markdown import NAGLOWEK_POLITYKI_PODGLADU, zamien_markdown_na_html


def test_naglowki_od_pierwszego_do_szostego_poziomu_zachowuja_poziom() -> None:
    html = zamien_markdown_na_html("# A\n\n## B\n\n### C\n\n#### D\n\n##### E\n\n###### F")

    for poziom, nazwa in enumerate("ABCDEF", start=1):
        assert f"<h{poziom}>{nazwa}</h{poziom}>" in html


def test_listy_tabele_cytaty_kod_i_akapity_dostaja_wlasciwe_elementy() -> None:
    html = zamien_markdown_na_html(
        "Akapit.\n\n- a\n- b\n\n1. c\n2. d\n\n> cytat\n\n```\nkod\n```\n\n"
        "| Kolumna | Druga |\n| --- | --- |\n| 1 | 2 |"
    )

    assert "<p>Akapit.</p>" in html
    assert "<ul>" in html and "<ol>" in html
    assert "<blockquote>" in html
    assert "<pre><code>kod\n</code></pre>" in html
    assert "<table>" in html
    assert "<th>Kolumna</th>" in html and "<td>1</td>" in html


def test_kolejne_wiersze_akapitu_sa_rozdzielone_znacznikiem_br() -> None:
    """Metadane źródła na początku pliku to kilka wierszy jednego akapitu."""
    html = zamien_markdown_na_html("Tytuł: A\nTyp: B")

    assert "Tytuł: A<br />\nTyp: B" in html


# --- próby wstrzyknięcia ---------------------------------------------------------


@pytest.mark.parametrize(
    ("wejscie", "oczekiwany_tekst"),
    [
        ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)&gt;"),
        ("Tekst <b onmouseover=x>pogrubiony</b> inline", "&lt;b onmouseover=x&gt;"),
        ('<iframe src="https://zlosliwa.example"></iframe>', "&lt;iframe"),
        ('<a href="javascript:alert(1)">klik</a>', "&lt;a href="),
    ],
)
def test_surowy_html_z_pliku_jest_pokazany_jako_tekst(wejscie: str, oczekiwany_tekst: str) -> None:
    html = zamien_markdown_na_html(wejscie)

    assert oczekiwany_tekst in html
    assert not re.search(r"<(script|img|iframe|b|a)\b", html)


def test_naglowek_z_html_jest_escapowany() -> None:
    html = zamien_markdown_na_html("# Tytuł <script>alert(1)</script>")

    assert html.startswith("<h1>Tytuł &lt;script&gt;alert(1)&lt;/script&gt;</h1>")
    assert "<script" not in html


def test_komorka_tabeli_z_html_jest_escapowana() -> None:
    html = zamien_markdown_na_html("| a | b |\n| --- | --- |\n| <img src=x onerror=y> | ok |")

    assert "<td>&lt;img src=x onerror=y&gt;</td>" in html
    assert "<img" not in html


def test_blok_kodu_z_html_jest_escapowany() -> None:
    html = zamien_markdown_na_html("```\n<script>alert(1)</script>\n```")

    assert "<pre><code>&lt;script&gt;alert(1)&lt;/script&gt;\n</code></pre>" in html


@pytest.mark.parametrize(
    "adres",
    [
        "javascript:alert(1)",
        "JaVaScRiPt:alert(1)",
        "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        "vbscript:msgbox(1)",
        "file:///C:/Windows/System32/cmd.exe",
        "ftp://serwer.example/plik",
        "mailto:ktos@example.com",
        "/projekt/inny",
        "plik.md",
        "//zlosliwa.example/x",
    ],
)
def test_odnosnik_o_schemacie_innym_niz_http_i_https_jest_zwyklym_tekstem(adres: str) -> None:
    html = zamien_markdown_na_html(f"[klik]({adres})")

    assert "<a " not in html
    assert "href=" not in html


@pytest.mark.parametrize("adres", ["http://a.example/b", "https://a.example/b?c=1&d=2"])
def test_odnosnik_http_i_https_dostaje_rel_noopener_noreferrer(adres: str) -> None:
    html = zamien_markdown_na_html(f"[klik]({adres})")

    assert 'rel="noopener noreferrer"' in html
    assert 'href="http' in html


def test_rel_dostaje_tez_odnosnik_w_komorce_tabeli_i_w_liscie() -> None:
    html = zamien_markdown_na_html(
        "| a |\n| --- |\n| [x](https://a.example) |\n\n- [y](https://b.example)"
    )

    assert html.count('rel="noopener noreferrer"') == 2


def test_adres_z_cudzyslowem_nie_wychodzi_z_atrybutu() -> None:
    html = zamien_markdown_na_html('[x](https://a.example/"onmouseover="alert(1))')

    assert "onmouseover=" not in re.sub(r'href="[^"]*"', "", html)


def test_obraz_nie_jest_pokazywany() -> None:
    html = zamien_markdown_na_html("![opis](https://a.example/obraz.png)")

    assert "<img" not in html


def test_odnosnik_automatyczny_z_niebezpiecznym_schematem_jest_tekstem() -> None:
    html = zamien_markdown_na_html("<javascript:alert(1)> <https://dobry.example/>")

    assert 'href="javascript' not in html
    assert 'href="https://dobry.example/"' in html


def test_polityka_zawartosci_blokuje_skrypty_i_zasoby_zewnetrzne() -> None:
    assert "default-src 'none'" in NAGLOWEK_POLITYKI_PODGLADU
    assert "script-src" not in NAGLOWEK_POLITYKI_PODGLADU
    assert "http" not in NAGLOWEK_POLITYKI_PODGLADU
