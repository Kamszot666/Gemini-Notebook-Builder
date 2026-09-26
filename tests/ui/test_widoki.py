"""Testy generowania stron HTML interfejsu: dostępność i brak wstrzyknięć."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path

from gnb.persistence.pola_notatnika import PolaNotatnika
from gnb.ui.projekty import ProjektNaLiscie
from gnb.ui.stan_skrotu import KomunikatSkrotu
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
    # Pola tekstowe mają nazwę w aria-label i tę samą nazwę w podpowiedzi
    # wewnątrz pola, bez widocznych etykiet; pole pliku zachowuje etykietę.
    assert 'aria-label="Nazwa projektu"' in html
    assert 'placeholder="Nazwa projektu"' in html
    assert 'placeholder="Tekst wklejony"' in html
    assert 'placeholder="Nazwa grupy tematycznej"' in html
    assert '<label for="nazwa_projektu">' not in html
    assert '<label for="tekst">' not in html
    assert '<label for="adresy">' not in html
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


def _strona_z_raportem(raport: str) -> str:
    informacja = InformacjaOZadaniu(
        nazwa_projektu="Projekt",
        stan=StanZadania.ZAKONCZONE,
        komunikat_postepu="Projekt zakończony",
        komunikat_bledu=None,
        wynik=None,
    )
    return strona_projektu(
        nazwa="Projekt",
        informacja=informacja,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
        podsumowanie=PodsumowanieWyniku(
            liczba_przetworzonych=1,
            liczba_pominietych=0,
            liczba_bledow=0,
            katalog_projektu="C:/wyniki/Projekt",
            wznowiono=False,
        ),
        raport=raport,
    )


def test_adres_http_w_raporcie_staje_sie_odnosnikiem_w_nowej_karcie() -> None:
    html = _strona_z_raportem("Źródło: https://przyklad.pl/artykul\n")

    assert (
        '<a href="https://przyklad.pl/artykul" target="_blank" '
        'rel="noopener noreferrer">https://przyklad.pl/artykul '
        "(otwiera się w nowej karcie)</a>" in html
    )


def test_zlosliwy_adres_w_raporcie_nie_wyrywa_sie_z_atrybutu_ani_nie_wstawia_znacznika() -> None:
    """Test ma się czerwienić, gdyby escapowanie adresu kiedyś zniknęło.

    Adres kończy się cudzysłowem, nawiasem ostrym i tagiem script — dokładnie
    tak, jak wymaga tego lista zmian etapu czternastego, pozycja trzecia.
    """
    zlosliwy = 'https://zly.pl/"><script>alert(1)</script>'
    html = _strona_z_raportem(f"Źródło: {zlosliwy}\n")

    assert "<script>alert(1)</script>" not in html
    assert '"><script>' not in html
    # Sam odnośnik istnieje, ale cały złośliwy ogon jest escapowany w środku
    # tekstu i atrybutu href, nie wyrywa się z nich.
    assert "&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_adres_javascript_w_raporcie_nigdy_nie_staje_sie_odnosnikiem() -> None:
    html = _strona_z_raportem("Uwaga: javascript:alert(1) w treści.\n")
    assert '<a href="javascript:' not in html


def test_strona_projektu_po_zakonczeniu_ma_formularz_dosylania_zrodel() -> None:
    html = _strona_z_raportem("Raport końcowy projektu: Projekt\n")

    assert 'placeholder="Tekst wklejony"' in html
    assert '<label for="dosylanie-tekst">' not in html
    assert 'action="/projekt/Projekt/dosylanie"' in html
    assert "Dodaj źródła i uruchom kolejny przebieg" in html


def test_strona_projektu_w_trakcie_przetwarzania_odpytuje_od_razu_i_ma_id_nagłowka() -> None:
    informacja = InformacjaOZadaniu(
        nazwa_projektu="Projekt",
        stan=StanZadania.TRWA,
        komunikat_postepu="Postęp: 20 procent, pobrano 3 z 11 źródeł",
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
    assert '<h2 id="naglowek-stanu">' in html
    # Skrypt musi odpytać stan od razu, nie dopiero po pierwszych 4 sekundach —
    # w przeciwnym razie krótki przebieg (kilka sekund) kończy się, zanim
    # pierwszy odczyt w ogóle nastąpi, i użytkownik nie usłyszy żadnego
    # pośredniego komunikatu postępu.
    assert "odswiez();\n  setInterval(odswiez, 4000);" in html


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


def test_strona_glowna_bez_aktywnego_projektu_skrotu_mowi_to_wprost() -> None:
    html = strona_glowna(projekty=[], token_csrf="t")
    assert "Brak aktywnego projektu skrótu." in html


def test_strona_glowna_pokazuje_nazwe_aktywnego_projektu_skrotu() -> None:
    html = strona_glowna(projekty=[], token_csrf="t", aktywny_projekt_skrotu="Podatki 2026")
    assert "Aktywny projekt skrótu: Podatki 2026." in html


def test_strona_glowna_pokazuje_ostatni_komunikat_skrotu() -> None:
    komunikat = KomunikatSkrotu(
        tekst="Dodano adres strony: Przykład", sukces=True, czas=datetime.now(UTC)
    )
    html = strona_glowna(projekty=[], token_csrf="t", ostatni_komunikat_skrotu=komunikat)
    assert "Dodano adres strony: Przykład" in html
    assert "powodzenie" in html


def test_strona_projektu_bez_aktywnego_skrotu_ma_przycisk_ustawienia() -> None:
    html = strona_projektu(
        nazwa="Projekt",
        informacja=None,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
    )
    assert "Ustaw jako aktywny projekt skrótu" in html
    assert "Brak aktywnego projektu skrótu." in html


def test_strona_projektu_juz_aktywnego_nie_ma_przycisku_ustawienia() -> None:
    html = strona_projektu(
        nazwa="Projekt",
        informacja=None,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
        aktywny_projekt_skrotu="Projekt",
    )
    assert "Ustaw jako aktywny projekt skrótu" not in html
    assert "Ten projekt jest teraz aktywnym projektem globalnego skrótu." in html


def test_strona_projektu_innego_aktywnego_pokazuje_jego_nazwe_i_przycisk() -> None:
    html = strona_projektu(
        nazwa="Projekt B",
        informacja=None,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
        aktywny_projekt_skrotu="Projekt A",
    )
    assert "Aktywny projekt skrótu: Projekt A." in html
    assert "Ustaw jako aktywny projekt skrótu" in html


def test_ostatni_komunikat_skrotu_z_niebezpieczna_trescia_jest_escapowany() -> None:
    zlosliwy = "</p><script>alert(1)</script>"
    komunikat = KomunikatSkrotu(tekst=zlosliwy, sukces=False, czas=datetime.now(UTC))
    html = strona_glowna(projekty=[], token_csrf="t", ostatni_komunikat_skrotu=komunikat)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_formularz_dosylania_podpowiada_grupy_projektu_i_wymaga_grupy() -> None:
    html = strona_projektu(
        nazwa="Projekt",
        informacja=None,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
        raport="Raport końcowy projektu: Projekt\n",
        grupy_projektu=["Zwierzęta", "Rośliny"],
    )
    assert '<datalist id="dosylanie-grupy">' in html
    assert '<option value="Zwierzęta">' in html
    assert '<option value="Rośliny">' in html
    # Domyślnie wpisana jest ostatnia grupa projektu, a pole jest wymagane.
    assert 'value="Rośliny" required' in html


class _ZbieraczPolTekstowych(HTMLParser):
    """Zbiera pola tekstowe i pola tekstowe wieloliniowe oraz etykiety z całej strony."""

    def __init__(self) -> None:
        super().__init__()
        self.pola: list[dict[str, str | None]] = []
        self.etykiety: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        atrybuty = dict(attrs)
        if tag == "textarea" or (tag == "input" and atrybuty.get("type") == "text"):
            self.pola.append(atrybuty)
        elif tag == "label" and atrybuty.get("for"):
            self.etykiety.add(atrybuty["for"] or "")


def _strony_z_polami_tekstowymi() -> list[str]:
    informacja = InformacjaOZadaniu(
        nazwa_projektu="Projekt",
        stan=StanZadania.ZAKONCZONE,
        komunikat_postepu="Projekt zakończony",
        komunikat_bledu=None,
        wynik=None,
    )
    return [
        strona_glowna(projekty=[], token_csrf="t"),
        _strona_z_raportem("Raport końcowy projektu: Projekt" + chr(10)),
        strona_projektu(
            nazwa="Projekt",
            informacja=informacja,
            pola=PolaNotatnika(),
            limit_znakow_instrukcji=10_000,
            token_csrf="t",
            podsumowanie=None,
            raport=None,
            bledy=[BladPola(pole="instrukcja_systemowa", komunikat="Za dużo znaków.")],
        ),
        strona_promptu(nazwa="Projekt", prompt="Treść"),
    ]


def test_kazde_pole_tekstowe_ma_aria_label_i_taki_sam_placeholder_bez_widocznej_etykiety() -> None:
    """Wzorzec z decyzji użytkownika: podwójny odczyt nazwy w NVDA przy etykiecie i podpowiedzi."""
    liczba_pol = 0
    for html in _strony_z_polami_tekstowymi():
        zbieracz = _ZbieraczPolTekstowych()
        zbieracz.feed(html)
        for pole in zbieracz.pola:
            liczba_pol += 1
            identyfikator = pole.get("id")
            assert pole.get("aria-label"), identyfikator
            assert pole.get("placeholder") == pole.get("aria-label"), identyfikator
            assert identyfikator not in zbieracz.etykiety, identyfikator
    assert liczba_pol >= 10


def test_pole_promptu_ma_opis_pomocniczy_przez_aria_describedby_a_nie_w_nazwie() -> None:
    html = strona_projektu(
        nazwa="Projekt",
        informacja=None,
        pola=PolaNotatnika(),
        limit_znakow_instrukcji=10_000,
        token_csrf="t",
        podsumowanie=None,
        raport=None,
    )

    assert 'aria-describedby="pomoc-prompt"' in html
    assert 'id="pomoc-prompt"' in html
    assert 'aria-label="Prompt dla mechanizmu wyszukującego źródła"' in html
