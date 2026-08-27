"""Testy ekstrakcji treści artykułu ze strony internetowej.

Testy pracują na plikach HTML z katalogu danych testowych oraz na krótkich
stronach budowanych w kodzie. Nie korzystają z sieci: ekstraktor dostaje gotowy
tekst strony, a pobieraniem zajmuje się osobny moduł.
"""

from __future__ import annotations

from pathlib import Path

from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.extractors.strona_www import (
    METODA_GLOWNA,
    METODA_ZAPASOWA,
    EkstraktorStronyWww,
    czy_wymaga_skryptow,
)
from gnb.output import regula_md

KATALOG_DANYCH = Path(__file__).resolve().parents[1] / "dane"

_STRONA_STRUKTURALNA = """<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><title>Poradnik</title></head>
<body>
<nav><a href="/">Strona główna</a></nav>
<article>
<h1>Poradnik przygotowania materiałów</h1>
<p>Ten poradnik opisuje, jak przygotować materiały źródłowe tak, aby dało się
je później zweryfikować, a każdy fragment miał ustalone pochodzenie.</p>
<h2>Kolejność pracy</h2>
<p>Kolejność ma znaczenie, ponieważ każdy kolejny krok korzysta z wyniku
poprzedniego i naprawianie pomyłki na końcu kosztuje znacznie więcej.</p>
<ol><li>Zebranie materiałów z wiarygodnych źródeł</li>
<li>Sprawdzenie powtórzeń i wersji tego samego dokumentu</li>
<li>Zapisanie pochodzenia każdego fragmentu</li></ol>
<h3>Czego unikać</h3>
<p>Unikaj wrzucania wszystkiego bez sprawdzenia, ponieważ powtórzenia zaśmiecają
bazę wiedzy i utrudniają odnalezienie właściwej odpowiedzi.</p>
<ul><li>Powtórzone artykuły</li><li>Materiały bez podanego autora</li></ul>
<h2>Porównanie metod</h2>
<table><tr><th>Metoda</th><th>Koszt</th></tr>
<tr><td>Suma kontrolna</td><td>bardzo niski</td></tr>
<tr><td>MinHash</td><td>średni</td></tr></table>
</article>
<footer>Wszelkie prawa zastrzeżone</footer>
</body></html>
"""

_STRONA_BEZ_ARTYKULU = """<!DOCTYPE html>
<html lang="pl"><head><meta charset="utf-8"><title>Spis treści serwisu</title></head>
<body><div id="lista"><a href="/a">Pierwszy</a><a href="/b">Drugi</a></div></body></html>
"""


def _ekstraktor() -> EkstraktorStronyWww:
    return EkstraktorStronyWww()


def test_ekstraktor_obsluguje_strony_www() -> None:
    ekstraktor = _ekstraktor()
    assert ekstraktor.obsluguje(TypZrodla.STRONA_WWW, "html") is True
    assert ekstraktor.obsluguje(TypZrodla.STRONA_WWW, "") is True
    assert ekstraktor.obsluguje(TypZrodla.PLIK_TEKSTOWY, "txt") is False


def test_tresc_artykulu_jest_oddzielona_od_nawigacji_i_stopki() -> None:
    tekst = (KATALOG_DANYCH / "artykul_oryginal.html").read_text(encoding="utf-8")
    dokument = _ekstraktor().wyekstrahuj("strona_www-1", tekst)

    assert dokument.metoda_ekstrakcji == METODA_GLOWNA
    assert "Baza wiedzy dla asystenta AI jest tym lepsza" in dokument.tekst
    assert "Zaakceptuj wszystkie" not in dokument.tekst
    assert "Reklama" not in dokument.tekst
    assert "Wszelkie prawa zastrzeżone" not in dokument.tekst
    assert "Strona główna" not in dokument.tekst


def test_tytul_i_metadane_sa_odczytane() -> None:
    tekst = (KATALOG_DANYCH / "artykul_oryginal.html").read_text(encoding="utf-8")
    dokument = _ekstraktor().wyekstrahuj("strona_www-1", tekst)

    assert dokument.tytul == "Jak przygotować bazę wiedzy dla asystenta AI"
    assert dokument.metadane["tytul"] == dokument.tytul


def test_poziom_pewnosci_z_trafilatury_jest_sredni() -> None:
    tekst = (KATALOG_DANYCH / "artykul_oryginal.html").read_text(encoding="utf-8")
    dokument = _ekstraktor().wyekstrahuj("strona_www-1", tekst)

    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.SREDNI


def test_struktura_strony_trafia_do_blokow() -> None:
    dokument = _ekstraktor().wyekstrahuj("strona_www-2", _STRONA_STRUKTURALNA)

    rodzaje = {blok.rodzaj for blok in dokument.bloki}
    assert RodzajBloku.NAGLOWEK in rodzaje
    assert RodzajBloku.LISTA in rodzaje
    assert RodzajBloku.TABELA in rodzaje


def test_tekst_wyniku_jest_zapisem_markdown() -> None:
    dokument = _ekstraktor().wyekstrahuj("strona_www-2", _STRONA_STRUKTURALNA)

    assert "# Poradnik przygotowania materiałów" in dokument.tekst
    assert "## Kolejność pracy" in dokument.tekst
    assert "1. Zebranie materiałów z wiarygodnych źródeł" in dokument.tekst
    assert "- Powtórzone artykuły" in dokument.tekst
    assert "| Metoda | Koszt |" in dokument.tekst


def test_dobrze_zbudowany_artykul_moze_dostac_wersje_md() -> None:
    dokument = _ekstraktor().wyekstrahuj("strona_www-2", _STRONA_STRUKTURALNA)
    decyzja = regula_md.ocen(dokument)

    assert decyzja.poziom_pewnosci_wystarczajacy is True
    assert decyzja.generuj_md is True


def test_prosty_artykul_bez_struktury_nie_dostaje_wersji_md() -> None:
    tekst = (KATALOG_DANYCH / "artykul_oryginal.html").read_text(encoding="utf-8")
    dokument = _ekstraktor().wyekstrahuj("strona_www-1", tekst)

    assert regula_md.ocen(dokument).generuj_md is False


def test_strona_bez_artykulu_trafia_do_mechanizmu_zapasowego() -> None:
    dokument = _ekstraktor().wyekstrahuj("strona_www-3", _STRONA_BEZ_ARTYKULU)

    assert dokument.metoda_ekstrakcji == METODA_ZAPASOWA
    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.ostrzezenia
    assert regula_md.ocen(dokument).generuj_md is False


def test_mechanizm_zapasowy_odzyskuje_akapity_i_tytul() -> None:
    strona = (
        "<html><head><title>Notatka techniczna</title></head><body>"
        "<script>alert('nie wykonuj tego')</script>"
        "<nav>Menu serwisu z odnośnikami do innych działów</nav>"
        "<div>Ten akapit jest wystarczająco długi, żeby mechanizm zapasowy uznał go "
        "za treść, a nie za element nawigacji serwisu.</div>"
        "</body></html>"
    )
    strona = strona.replace("<div>", "<p>").replace("</div>", "</p>")

    dokument = _ekstraktor().wyekstrahuj("strona_www-4", strona)

    assert dokument.tytul == "Notatka techniczna"
    assert "wystarczająco długi" in dokument.tekst
    assert "alert" not in dokument.tekst
    assert "Menu serwisu" not in dokument.tekst


def _strona_ze_skryptami() -> str:
    """Buduje rozbudowaną stronę, w której treść powstaje dopiero w przeglądarce."""
    szkielet = '<div class="kontener"></div>' * 100
    skrypt = "<script>window.__DANE__ = [];</script>" * 20
    return (
        '<!DOCTYPE html><html lang="pl"><head><meta charset="utf-8">'
        '<title>Aplikacja</title></head><body><div id="root"></div>'
        f"{szkielet}{skrypt}</body></html>"
    )


def test_strona_budowana_skryptami_jest_rozpoznana() -> None:
    strona = _strona_ze_skryptami()
    dokument = _ekstraktor().wyekstrahuj("strona_www-5", strona)

    assert czy_wymaga_skryptow(strona, dokument.tekst) is True


def test_zwykly_artykul_nie_jest_uznany_za_wymagajacy_skryptow() -> None:
    tekst = (KATALOG_DANYCH / "artykul_oryginal.html").read_text(encoding="utf-8")
    dokument = _ekstraktor().wyekstrahuj("strona_www-1", tekst)

    assert czy_wymaga_skryptow(tekst, dokument.tekst) is False


def test_krotka_poprawna_strona_nie_jest_uznana_za_wymagajaca_skryptow() -> None:
    strona = (
        "<html><head><title>Notatka</title></head><body>"
        "<script>console.log(1)</script>"
        "<p>Krótka, ale poprawna notatka.</p></body></html>"
    )
    assert czy_wymaga_skryptow(strona, "Krótka, ale poprawna notatka.") is False
