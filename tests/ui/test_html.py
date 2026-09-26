"""Testy escapowania treści przed wstawieniem do HTML interfejsu."""

from __future__ import annotations

from gnb.ui.html import atrybut, escapuj, tekst_z_odnosnikami


def test_znaczniki_html_ze_zrodla_nie_przechodza_jako_html() -> None:
    """Treść źródła ze znacznikami i cudzysłowami trafia na stronę wyłącznie jako tekst.

    To jest podatność opisana w sekcji jedenastej punkt drugi CLAUDE.md: podgląd
    artykułu ze strony trzeciej wstawiony jako HTML pozwoliłby wykonać obcy skrypt.
    """
    zlosliwa_tresc = '<script>alert("x")</script> & <img src=a onerror=b>'
    wynik = escapuj(zlosliwa_tresc)

    assert "<script>" not in wynik
    assert "<img" not in wynik
    assert "&lt;script&gt;" in wynik
    assert "&amp;" in wynik
    assert "&quot;" in wynik


def test_atrybut_escapuje_cudzyslow_i_nie_pozwala_wyjsc_z_wartosci() -> None:
    wynik = atrybut("value", 'a" onmouseover="zle()')
    assert wynik.startswith('value="')
    assert wynik.endswith('"')
    assert 'onmouseover="zle()' not in wynik
    assert "&quot;" in wynik


def test_polskie_znaki_nie_sa_zmieniane() -> None:
    assert escapuj("Zażółć gęślą jaźń") == "Zażółć gęślą jaźń"


def test_tekst_z_odnosnikami_linkuje_tylko_http_i_https() -> None:
    wynik = tekst_z_odnosnikami("Zajrzyj: https://a.pl/x, oraz javascript:alert(1) i <b>")

    assert '<a href="https://a.pl/x" target="_blank" rel="noopener noreferrer">' in wynik
    assert "javascript:alert(1)" in wynik and 'href="javascript' not in wynik
    assert "&lt;b&gt;" in wynik and "<b>" not in wynik


def test_tekst_z_odnosnikami_nie_pozwala_uciec_z_atrybutu() -> None:
    wynik = tekst_z_odnosnikami('https://a.pl/"onmouseover="x')

    assert 'onmouseover="x' not in wynik.replace("&quot;", "")
    assert wynik.count("<a ") == 1
