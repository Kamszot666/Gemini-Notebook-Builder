"""Testy widoków źródeł: dostępność formularzy, escapowanie i potwierdzenie usunięcia."""

from __future__ import annotations

import re

from gnb.ui.widoki_zrodel import (
    BrakujacyPlikDoWidoku,
    ZrodloDoWidoku,
    sekcje_zrodel,
)

_TOKEN = "token-testowy"


def _zrodlo(**nadpisania: object) -> ZrodloDoWidoku:
    dane: dict[str, object] = {
        "identyfikator": "strona_www-abc123",
        "pochodzenie": "https://przyklad.pl/artykul",
        "status": "spakowane",
        "pliki_wynikowe": ("artykul.txt",),
        "czy_material_do_sprawdzenia": True,
        "powody_do_sprawdzenia": ("treść ma mniej niż 50 słów",),
        "czy_mozna_zastapic_tresc": True,
    }
    dane.update(nadpisania)
    return ZrodloDoWidoku(**dane)  # type: ignore[arg-type]


def test_kazdy_formularz_ma_token_csrf_i_metode_post() -> None:
    html = sekcje_zrodel("Projekt", [_zrodlo()], [], _TOKEN)

    formularze = re.findall(r"<form[^>]*>", html)
    assert len(formularze) == 3
    assert all('method="post"' in formularz for formularz in formularze)
    assert html.count(f'value="{_TOKEN}"') == 3


def test_pole_pliku_ma_etykiete_a_przyciski_opisuja_sie_naglowkiem_zrodla() -> None:
    html = sekcje_zrodel("Projekt", [_zrodlo()], [], _TOKEN)

    assert 'aria-label="Plik z ręcznie zapisaną treścią tego źródła"' in html
    assert 'id="zastap-strona_www-abc123"' in html
    assert 'id="zrodlo-strona_www-abc123-opis"' in html
    assert html.count('aria-describedby="zrodlo-strona_www-abc123-opis"') == 4
    assert "<h3" in html
    assert "Usuń źródło z projektu</button>" in html


def test_zrodlo_bez_uwag_nie_ma_przycisku_weryfikacji() -> None:
    html = sekcje_zrodel(
        "Projekt",
        [_zrodlo(czy_material_do_sprawdzenia=False, powody_do_sprawdzenia=())],
        [],
        _TOKEN,
    )

    assert "Oznacz jako zweryfikowane" not in html
    assert "Zastąp treść plikiem" in html


def test_zrodlo_bez_mozliwosci_zastapienia_nie_ma_formularza_pliku() -> None:
    html = sekcje_zrodel(
        "Projekt", [_zrodlo(czy_mozna_zastapic_tresc=False, status="duplikat")], [], _TOKEN
    )

    assert "Zastąp treść plikiem" not in html
    assert 'type="file"' not in html
    assert "Usuń źródło z projektu" in html


def test_zweryfikowane_zrodlo_pokazuje_informacje_zamiast_przycisku() -> None:
    html = sekcje_zrodel("Projekt", [_zrodlo(zweryfikowane_recznie=True)], [], _TOKEN)

    assert "Zweryfikowane ręcznie przez użytkownika." in html
    assert "Oznacz jako zweryfikowane" not in html


def test_tresc_ze_zrodla_jest_escapowana() -> None:
    zrodlo = _zrodlo(
        pochodzenie="<img src=x onerror=alert(1)>",
        komunikat='<script>alert("komunikat")</script>',
        powody_do_sprawdzenia=("<b>powód</b>",),
        grupa="<i>grupa</i>",
    )

    html = sekcje_zrodel("Projekt", [zrodlo], [], _TOKEN)

    assert "<img" not in html
    assert "<script>" not in html
    assert "<b>powód" not in html
    assert "<i>grupa" not in html
    assert "&lt;img" in html


def test_brakujace_pliki_sa_opisane_jako_tylko_odczyt() -> None:
    brakujace = [
        BrakujacyPlikDoWidoku("grupa.txt", ("źródło A", "źródło B"), czy_zajmuje_slot=True),
        BrakujacyPlikDoWidoku("a.md", ("źródło A",), czy_zajmuje_slot=False),
    ]

    html = sekcje_zrodel("Projekt", [], brakujace, _TOKEN)

    assert "<h2>Pliki wynikowe brakujące na dysku</h2>" in html
    assert "niczego nie zmienia" in html
    assert "grupa.txt. Źródła: źródło A; źródło B." in html
    assert "zostaną pominięte na początku następnego przebiegu" in html
    assert "To wersja MD" in html
    assert "<form" not in html


def test_bez_zrodel_i_bez_brakujacych_plikow_sekcje_sa_puste() -> None:
    assert sekcje_zrodel("Projekt", [], [], _TOKEN) == ""


def test_usuniecie_to_przycisk_formularza_bez_pola_potwierdzenia() -> None:
    html = sekcje_zrodel("Projekt", [_zrodlo()], [], _TOKEN)

    assert 'action="/projekt/Projekt/zrodlo/' in html and '/usun"' in html
    assert "Usuń źródło z projektu</button>" in html
    assert 'name="potwierdzenie"' not in html
    assert "wpisz słowo" not in html


def test_adres_w_pochodzeniu_zrodla_jest_klikalny_bez_znaku_konca_zdania() -> None:
    zrodlo = _zrodlo(pochodzenie="Zobacz https://przyklad.pl/a.")

    html = sekcje_zrodel("Projekt", [zrodlo], [], _TOKEN)

    assert '<a href="https://przyklad.pl/a" target="_blank"' in html
