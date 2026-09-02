"""Testy generowania stron HTML interfejsu: dostępność i brak wstrzyknięć."""

from __future__ import annotations

import re
from pathlib import Path

from gnb.persistence.pola_notatnika import PolaNotatnika
from gnb.ui.projekty import ProjektNaLiscie
from gnb.ui.widoki import (
    BladPola,
    DaneFormularzaProjektu,
    PodsumowanieWyniku,
    strona_bledu,
    strona_glowna,
    strona_projektu,
    strona_promptu,
)
from gnb.ui.zadania import InformacjaOZadaniu, StanZadania

_WZORZEC_ADRESU_ZEWNETRZNEGO = re.compile(r'(src|href)="https?://', re.IGNORECASE)


def test_strona_glowna_ma_etykiety_i_pole_csrf() -> None:
    html = strona_glowna(projekty=[], token_csrf="tok123")

    assert '<html lang="pl">' in html
    assert '<label for="nazwa_projektu">' in html
    assert '<label for="tekst">' in html
    assert '<label for="adresy">' in html
    assert '<label for="pliki">' in html
    assert 'name="token_csrf" value="tok123"' in html
    assert "Nie ma niedokończonych projektów." in html


def test_zadna_strona_nie_laduje_zasobu_zewnetrznego() -> None:
    strony = [
        strona_glowna(projekty=[], token_csrf="t"),
        strona_projektu(
            nazwa="Projekt",
            informacja=None,
            pola=PolaNotatnika(),
            limit_znakow_instrukcji=10_000,
            token_csrf="t",
        ),
        strona_bledu(kod=404, tytul="Nie znaleziono", komunikat="Brak takiej strony."),
    ]
    for html in strony:
        assert _WZORZEC_ADRESU_ZEWNETRZNEGO.search(html) is None
        assert "cdn" not in html.lower()
        assert "@import" not in html


def test_tresc_ze_zrodla_nie_przechodzi_jako_html_na_stronie_projektu() -> None:
    zlosliwa = "</textarea><script>alert(1)</script>"
    html = strona_projektu(
        nazwa="Projekt",
        informacja=None,
        pola=PolaNotatnika(instrukcja_systemowa=zlosliwa, prompt_wyszukiwania=zlosliwa),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
    )

    assert "</textarea><script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_nazwa_projektu_ze_znacznikami_jest_escapowana() -> None:
    html = strona_glowna(
        projekty=[],
        token_csrf="t",
        dane=DaneFormularzaProjektu(nazwa_projektu='"><img src=x onerror=y>'),
    )
    assert '"><img src=x onerror=y>' not in html
    assert "&gt;&lt;img" in html


def test_bledy_walidacji_sa_powiazane_z_polami() -> None:
    html = strona_glowna(
        projekty=[],
        token_csrf="t",
        bledy=[BladPola(pole="nazwa_projektu", komunikat="Nazwa projektu jest wymagana.")],
    )
    assert 'role="alert"' in html
    assert 'id="bledy-formularza"' in html
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="nazwa_projektu-blad"' in html
    assert "Nazwa projektu jest wymagana." in html
    # Sekcja 11 punkt 8 CLAUDE.md: fokus wolno przenieść po nieudanej walidacji.
    assert "getElementById('bledy-formularza')" in html
    assert ".focus()" in html


def test_strona_bez_bledow_nie_przenosi_fokusu() -> None:
    html = strona_glowna(projekty=[], token_csrf="t")
    assert "bledy-formularza" not in html
    assert ".focus()" not in html


def test_strona_projektu_w_trakcie_ma_region_status_i_skrypt_postepu() -> None:
    informacja = InformacjaOZadaniu(
        nazwa_projektu="Projekt",
        stan=StanZadania.TRWA,
        komunikat_postepu="Przetworzono 3 z 10 źródeł",
        komunikat_bledu=None,
        wynik=None,
    )
    html = strona_projektu(
        nazwa="Projekt",
        informacja=informacja,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
    )

    assert 'role="status"' in html
    assert 'aria-live="polite"' in html
    assert 'data-koniec="nie"' in html
    assert "Przetworzono 3 z 10 źródeł" in html
    assert "setInterval" in html
    assert 'id="licznik-instrukcji"' in html


def test_strona_projektu_po_zakonczeniu_pokazuje_raport_bez_skryptu_postepu() -> None:
    informacja = InformacjaOZadaniu(
        nazwa_projektu="Projekt",
        stan=StanZadania.ZAKONCZONE,
        komunikat_postepu="Projekt zakończony",
        komunikat_bledu=None,
        wynik=None,
    )
    html = strona_projektu(
        nazwa="Projekt",
        informacja=informacja,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
        podsumowanie=PodsumowanieWyniku(
            liczba_przetworzonych=5,
            liczba_pominietych=1,
            liczba_bledow=0,
            katalog_projektu="C:/wyniki/Projekt",
            wznowiono=False,
        ),
        raport="Raport końcowy projektu: Projekt\n\nLiczba wejść: 6\n",
    )

    assert 'data-koniec="tak"' in html
    assert "setInterval" not in html
    assert "Raport końcowy projektu: Projekt" in html
    assert "Źródła przetworzone: 5" in html


def test_strona_promptu_pokazuje_prompt_i_zapewnia_ze_nic_nie_wysyla() -> None:
    html = strona_promptu(nazwa="Projekt", prompt="Znajdź artykuły o NVDA.")
    assert "Znajdź artykuły o NVDA." in html
    assert "Aplikacja nigdzie jej nie wysyła." in html
    assert "readonly" in html


def test_strona_bledu_ma_kod_i_komunikat_po_polsku() -> None:
    html = strona_bledu(
        kod=403, tytul="Brak uprawnień", komunikat="Token formularza jest nieprawidłowy."
    )
    assert "Brak uprawnień" in html
    assert "Token formularza jest nieprawidłowy." in html


def test_projekt_do_wznowienia_ma_wlasny_przycisk() -> None:
    projekt = ProjektNaLiscie(
        nazwa="Podatki 2026",
        katalog=Path("x"),
        zakonczony=False,
        liczba_zrodel=4,
        czas_ostatniej_zmiany="2026-09-02T10:00:00+00:00",
    )
    html = strona_glowna(projekty=[projekt], token_csrf="t")
    assert "Podatki 2026" in html
    assert "/projekt/Podatki%202026/wznow" in html
    assert "Wznów ten projekt" in html
