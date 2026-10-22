"""Testy modułu wyglądu: kontrast schematów, bezpieczeństwo arkusza i arkusz podstawowy."""

from __future__ import annotations

import re
from dataclasses import fields

import pytest

from gnb.core.konfiguracja import (
    KROJE_PISMA,
    SCHEMAT_KOLOROW_WLASNY,
    SCHEMATY_KOLOROW,
    STOPNIE_CZCIONKI,
    Konfiguracja,
)
from gnb.ui import widoki, wyglad
from gnb.ui.wyglad import (
    PROG_KONTRASTU_ELEMENTOW,
    PROG_KONTRASTU_TEKSTU,
    SCHEMATY,
    KoloryInterfejsu,
    SchematKolorow,
    css_wygladu,
    fokus_widoczny,
    kolory_obowiazujace,
    kolory_wlasne,
    kontrast,
    ostrzezenia_kontrastu,
    zmienne_css,
)

_IDENTYFIKATORY = [schemat.identyfikator for schemat in SCHEMATY]


# --- wzór kontrastu ----------------------------------------------------------


def test_kontrast_czerni_i_bieli_wynosi_dwadziescia_jeden() -> None:
    assert kontrast("#000000", "#ffffff") == pytest.approx(21.0)
    assert kontrast("#ffffff", "#000000") == pytest.approx(21.0)


def test_kontrast_tego_samego_koloru_wynosi_jeden() -> None:
    assert kontrast("#336699", "#336699") == pytest.approx(1.0)


def test_kontrast_znanej_pary_zgadza_sie_z_wartoscia_z_wcag() -> None:
    # Szary #767676 na bieli to najjaśniejszy szary spełniający 4,5 do 1.
    assert kontrast("#767676", "#ffffff") == pytest.approx(4.54, abs=0.01)
    assert kontrast("#777777", "#ffffff") == pytest.approx(4.48, abs=0.01)


# --- schematy ----------------------------------------------------------------


def test_lista_schematow_zgadza_sie_z_identyfikatorami_w_konfiguracji() -> None:
    assert _IDENTYFIKATORY + [SCHEMAT_KOLOROW_WLASNY] == list(SCHEMATY_KOLOROW)


def test_schemat_domyslny_ma_kolory_domyslne_pol_konfiguracji() -> None:
    domyslna = Konfiguracja()
    kolory = SCHEMATY[0].kolory

    assert kolory == kolory_wlasne(domyslna)
    assert domyslna.wyglad_schemat == SCHEMATY[0].identyfikator


def test_jest_schemat_zblizony_do_gemini_notebook() -> None:
    nazwy = {schemat.nazwa for schemat in SCHEMATY}

    assert "Zbliżony do Gemini Notebook" in nazwy


@pytest.mark.parametrize("identyfikator", _IDENTYFIKATORY)
def test_schemat_spelnia_progi_kontrastu(identyfikator: str) -> None:
    schemat = next(s for s in SCHEMATY if s.identyfikator == identyfikator)
    k = schemat.kolory

    assert kontrast(k.tekst, k.tlo) >= PROG_KONTRASTU_TEKSTU, "tekst"
    assert kontrast(k.odnosnik, k.tlo) >= PROG_KONTRASTU_TEKSTU, "odnośniki"
    assert kontrast(k.przycisk_tekst, k.przycisk_tlo) >= PROG_KONTRASTU_TEKSTU, "przyciski"
    assert kontrast(k.blad, k.tlo) >= PROG_KONTRASTU_TEKSTU, "komunikat błędu"
    assert kontrast(k.obramowanie, k.tlo) >= PROG_KONTRASTU_ELEMENTOW, "obramowanie"
    assert kontrast(k.fokus, k.tlo) >= PROG_KONTRASTU_ELEMENTOW, "fokus"


def test_test_progow_wykrywa_schemat_o_zbyt_niskim_kontrascie() -> None:
    zly = KoloryInterfejsu(
        tlo="#10131a",
        tekst="#555555",
        odnosnik="#9ecbff",
        przycisk_tlo="#1d4f91",
        przycisk_tekst="#ffffff",
        obramowanie="#7f8fb3",
        fokus="#ffd54a",
        blad="#ffb4ab",
    )

    assert kontrast(zly.tekst, zly.tlo) < PROG_KONTRASTU_TEKSTU


def test_schemat_bezpieczny_dla_barw_nie_rozroznia_stanow_czerwienia_i_zielenia() -> None:
    schemat = next(s for s in SCHEMATY if s.identyfikator == "bezpieczny_dla_barw")

    def odcien(kolor: str) -> str:
        r, g, b = (int(kolor[i : i + 2], 16) for i in (1, 3, 5))
        if r > 150 and g < 120 and b < 120:
            return "czerwien"
        if g > 150 and r < 120 and b < 120:
            return "zielen"
        return "inny"

    for pole in fields(schemat.kolory):
        assert odcien(getattr(schemat.kolory, pole.name)) not in ("czerwien", "zielen")


# --- kolory własne i fokus ----------------------------------------------------


def test_kolory_wlasne_sa_brane_z_pol_konfiguracji_tylko_przy_schemacie_wlasnym() -> None:
    konfiguracja = Konfiguracja(wyglad_schemat="wlasny", wyglad_kolor_tla="#112233")
    inna = Konfiguracja(wyglad_schemat="czarny_na_bialym", wyglad_kolor_tla="#112233")

    assert kolory_obowiazujace(konfiguracja).tlo == "#112233"
    assert kolory_obowiazujace(inna).tlo == "#ffffff"


def test_nieznany_schemat_daje_schemat_domyslny() -> None:
    assert kolory_obowiazujace(Konfiguracja(wyglad_schemat="nie_ma")) == SCHEMATY[0].kolory


def test_fokus_o_niskim_kontrascie_jest_zastepowany_czernia_albo_biela() -> None:
    zle = Konfiguracja(
        wyglad_schemat="wlasny", wyglad_kolor_tla="#202020", wyglad_kolor_fokusu="#222222"
    )
    dobre = Konfiguracja(
        wyglad_schemat="wlasny", wyglad_kolor_tla="#202020", wyglad_kolor_fokusu="#ffff00"
    )

    assert fokus_widoczny(kolory_obowiazujace(zle)) == "#ffffff"
    assert fokus_widoczny(kolory_obowiazujace(dobre)) == "#ffff00"
    jasne = Konfiguracja(
        wyglad_schemat="wlasny", wyglad_kolor_tla="#f0f0f0", wyglad_kolor_fokusu="#eeeeee"
    )
    assert fokus_widoczny(kolory_obowiazujace(jasne)) == "#000000"


def test_arkusz_zawiera_widoczny_fokus_nawet_przy_fokusie_w_kolorze_tla() -> None:
    konfiguracja = Konfiguracja(
        wyglad_schemat="wlasny", wyglad_kolor_tla="#202020", wyglad_kolor_fokusu="#202020"
    )

    assert "--fokus: #ffffff;" in zmienne_css(konfiguracja)


def test_ostrzezenie_przy_kontrascie_ponizej_czterech_i_pol() -> None:
    nieczytelne = Konfiguracja(
        wyglad_schemat="wlasny", wyglad_kolor_tla="#777777", wyglad_kolor_tekstu="#888888"
    )

    uwagi = ostrzezenia_kontrastu(kolory_obowiazujace(nieczytelne))

    assert any("tekstu do tła" in zdanie and "4,5 do 1" in zdanie for zdanie in uwagi)


def test_brak_ostrzezenia_dla_czytelnych_kolorow() -> None:
    for schemat in SCHEMATY:
        assert ostrzezenia_kontrastu(schemat.kolory) == []


# --- bezpieczeństwo arkusza --------------------------------------------------


def test_zlosliwy_kolor_wstawiony_wprost_do_konfiguracji_nie_trafia_do_arkusza() -> None:
    zlosliwy = "#fff;}</style><script>alert(1)</script>"
    konfiguracja = Konfiguracja(
        wyglad_schemat="wlasny",
        wyglad_kolor_tla=zlosliwy,
        wyglad_kolor_tekstu="red; background:url(x)",
    )

    arkusz = css_wygladu(konfiguracja)

    assert "<script" not in arkusz
    assert "url(" not in arkusz
    assert "alert" not in arkusz
    assert arkusz.count("</style>") == 1
    assert "--tlo: #10131a;" in arkusz


def test_nieznany_kroj_i_stopien_nie_trafiaja_do_arkusza() -> None:
    konfiguracja = Konfiguracja(
        wyglad_kroj_pisma="x; } body{display:none", wyglad_rozmiar_czcionki=9999
    )

    arkusz = zmienne_css(konfiguracja)

    assert "display" not in arkusz
    assert "--skala: 1;" in arkusz


def test_jasny_schemat_ustawia_color_scheme_light_a_ciemny_dark() -> None:
    assert "color-scheme: light;" in zmienne_css(Konfiguracja(wyglad_schemat="czarny_na_bialym"))
    assert "color-scheme: dark;" in zmienne_css(Konfiguracja(wyglad_schemat="bialy_na_czarnym"))


# --- rozmiar i krój pisma ----------------------------------------------------


def test_stopnie_czcionki_obejmuja_od_stu_do_dwustu_procent() -> None:
    assert min(STOPNIE_CZCIONKI) == 100
    assert max(STOPNIE_CZCIONKI) == 200
    assert len(STOPNIE_CZCIONKI) >= 4


def test_kazdy_kroj_ma_stos_konczacy_sie_rodzina_bez_szeryfow() -> None:
    assert set(wyglad.STOSY_KROJOW) == set(KROJE_PISMA)
    for stos in wyglad.STOSY_KROJOW.values():
        assert stos.endswith("sans-serif")


def test_skala_czcionki_trafia_do_arkusza() -> None:
    assert "--skala: 2;" in zmienne_css(Konfiguracja(wyglad_rozmiar_czcionki=200))
    assert "--skala: 1.5;" in zmienne_css(Konfiguracja(wyglad_rozmiar_czcionki=150))


# --- arkusz podstawowy -------------------------------------------------------


def test_arkusz_podstawowy_uzywa_jednostek_wzglednych_dla_czcionek() -> None:
    arkusz = widoki._STYLE  # pyright: ignore[reportPrivateUsage]

    assert not re.search(r"font(-size)?:\s*[\d.]+px", arkusz)
    assert "calc(125% * var(--skala))" in arkusz


def test_arkusz_podstawowy_ma_cel_klikniecia_interlinie_i_tryby_dostepnosci() -> None:
    arkusz = widoki._STYLE  # pyright: ignore[reportPrivateUsage]

    assert "min-height: 2.75rem" in arkusz
    assert "line-height: 1.6" in arkusz
    assert "@media (forced-colors: active)" in arkusz
    assert "@media (prefers-reduced-motion: reduce)" in arkusz
    assert "overflow-wrap: anywhere" in arkusz


def test_arkusz_podstawowy_nie_koduje_kolorow_poza_blokiem_ratunkowym() -> None:
    arkusz = widoki._STYLE  # pyright: ignore[reportPrivateUsage]
    poza_ratunkiem = re.sub(r"\.ratunek[^}]*\}", "", arkusz)
    poza_ratunkiem = re.sub(r":root \{.*?\n\}", "", poza_ratunkiem, flags=re.DOTALL)

    assert not re.search(r"#[0-9a-fA-F]{6}\b", poza_ratunkiem)


def test_blok_ratunkowy_ma_stale_kolory_niezalezne_od_zmiennych() -> None:
    arkusz = widoki._STYLE  # pyright: ignore[reportPrivateUsage]
    blok = arkusz[arkusz.index(".ratunek {") : arkusz.index("@media (prefers-reduced-motion")]

    assert "var(" not in blok
    assert kontrast("#ffffff", "#000000") >= 7
    assert kontrast("#000000", "#ffff00") >= 7


def test_nic_nie_jest_przekazywane_wylacznie_kolorem() -> None:
    arkusz = widoki._STYLE  # pyright: ignore[reportPrivateUsage]

    # Odnośniki mają podkreślenie, najechanie przyciskiem je podkreśla, a błąd
    # ma też pogrubioną ramkę i nagłówek z tekstem.
    assert "text-decoration: underline" in arkusz
    assert "button:hover { text-decoration: underline; }" in arkusz
    assert ".bledy { border: 3px solid var(--blad); }" in arkusz


def test_dokument_ma_znacznik_wygladu_po_arkuszu_podstawowym() -> None:
    strona = widoki.strona_bledu(kod=404, tytul="X", komunikat="Y")

    assert widoki.ZNACZNIK_WYGLADU in strona
    assert strona.index("</style>") < strona.index(widoki.ZNACZNIK_WYGLADU)


def test_typ_schematu_ma_nazwy_polskie_i_unikalne() -> None:
    nazwy = [schemat.nazwa for schemat in SCHEMATY]

    assert len(nazwy) == len(set(nazwy))
    assert all(isinstance(schemat, SchematKolorow) for schemat in SCHEMATY)
