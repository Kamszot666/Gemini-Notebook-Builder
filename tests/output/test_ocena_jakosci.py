"""Testy heurystyk oceniających jakość wyniku ekstrakcji."""

from __future__ import annotations

from gnb.output.ocena_jakosci import (
    OCENA_PODEJRZANA,
    OCENA_POPRAWNA,
    ocen_jakosc,
)

_AKAPIT = (
    "Baza wiedzy jest tym lepsza, im mniej zawiera powtórzeń i im dokładniej wiadomo, "
    "skąd pochodzi każdy jej fragment, bo bez tego nie da się niczego zweryfikować."
)


def _tekst_poprawny(liczba_akapitow: int = 4) -> str:
    return "\n\n".join(f"{_AKAPIT} Akapit numer {numer}." for numer in range(liczba_akapitow))


def test_poprawny_wynik_nie_budzi_zastrzezen() -> None:
    ocena = ocen_jakosc(_tekst_poprawny(), tytul="Tytuł artykułu")

    assert ocena.ocena == OCENA_POPRAWNA
    assert ocena.powody == ()
    assert not ocena.czy_podejrzana


def test_zbyt_krotka_tresc_jest_podejrzana() -> None:
    ocena = ocen_jakosc("Trzy słowa tutaj.", tytul="Tytuł")

    assert ocena.ocena == OCENA_PODEJRZANA
    assert any("mniej niż 50 słów" in powod for powod in ocena.powody)


def test_brak_tytulu_jest_podejrzany() -> None:
    ocena = ocen_jakosc(_tekst_poprawny(), tytul="   ")

    assert ocena.czy_podejrzana
    assert any("nie ma tytułu" in powod for powod in ocena.powody)


def test_brak_podzialu_na_akapity_jest_podejrzany() -> None:
    ocena = ocen_jakosc(_tekst_poprawny(1) + " " + _AKAPIT, tytul="Tytuł")

    assert ocena.czy_podejrzana
    assert any("podziału na akapity" in powod for powod in ocena.powody)


def test_zwrot_strony_bledu_jest_podejrzany() -> None:
    ocena = ocen_jakosc(_tekst_poprawny() + "\n\nStrona nie została znaleziona.", tytul="Tytuł")

    assert ocena.czy_podejrzana
    assert any("strony błędu" in powod for powod in ocena.powody)


def test_zadanie_wlaczenia_skryptow_jest_podejrzane() -> None:
    ocena = ocen_jakosc(_tekst_poprawny() + "\n\nWłącz JavaScript, aby czytać dalej.", tytul="T")

    assert ocena.czy_podejrzana
    assert any("javascript" in powod.lower() for powod in ocena.powody)


def test_powtorzony_akapit_jest_podejrzany() -> None:
    tekst = "\n\n".join([_AKAPIT, _AKAPIT, _AKAPIT, "Inny akapit z zupełnie inną treścią."])
    ocena = ocen_jakosc(tekst, tytul="Tytuł")

    assert ocena.czy_podejrzana
    assert any("powtarza się 3 razy" in powod for powod in ocena.powody)


def test_dwa_powtorzenia_nie_wystarczaja_do_podejrzenia() -> None:
    tekst = "\n\n".join([_AKAPIT, _AKAPIT] + [f"{_AKAPIT} {numer}" for numer in range(3)])
    ocena = ocen_jakosc(tekst, tytul="Tytuł")

    assert ocena.ocena == OCENA_POPRAWNA


def test_przewaga_odnosnikow_nad_trescia_jest_podejrzana() -> None:
    tekst_zrodla = "<html><body>" + '<a href="/x">link</a>' * 300 + "</body></html>"
    ocena = ocen_jakosc(_tekst_poprawny(), tytul="Tytuł", tekst_zrodla=tekst_zrodla)

    assert ocena.czy_podejrzana
    assert any("odnośników" in powod for powod in ocena.powody)


def test_niewielka_liczba_odnosnikow_nie_budzi_zastrzezen() -> None:
    tekst_zrodla = "<html><body>" + '<a href="/x">link</a>' * 5 + "</body></html>"
    ocena = ocen_jakosc(_tekst_poprawny(), tytul="Tytuł", tekst_zrodla=tekst_zrodla)

    assert ocena.ocena == OCENA_POPRAWNA


def test_znacznie_dluzsza_tresc_porownawcza_jest_podejrzana() -> None:
    ocena = ocen_jakosc(
        _tekst_poprawny(2),
        tytul="Tytuł",
        tresc_porownawcza=_tekst_poprawny(10),
    )

    assert ocena.czy_podejrzana
    assert any("dane strukturalne" in powod for powod in ocena.powody)


def test_porownywalna_tresc_porownawcza_nie_budzi_zastrzezen() -> None:
    ocena = ocen_jakosc(
        _tekst_poprawny(4),
        tytul="Tytuł",
        tresc_porownawcza=_tekst_poprawny(4),
    )

    assert ocena.ocena == OCENA_POPRAWNA


def test_kilka_powodow_naraz_trafia_do_wyniku() -> None:
    ocena = ocen_jakosc("Krótko.", tytul=None)

    assert ocena.czy_podejrzana
    assert len(ocena.powody) == 3


def test_sam_szkielet_naglowkow_jest_podejrzany() -> None:
    tekst = "\n\n".join(
        [
            "# Rozdział pierwszy",
            "## Rozdział drugi",
            "## Rozdział trzeci",
            _AKAPIT,
        ]
    )
    ocena = ocen_jakosc(tekst, tytul="Tytuł")

    assert ocena.czy_podejrzana
    assert any("więcej nagłówków" in powod for powod in ocena.powody)


def test_naglowki_z_trescia_nie_budza_zastrzezen() -> None:
    tekst = "\n\n".join(
        [
            "# Rozdział pierwszy",
            _AKAPIT,
            f"{_AKAPIT} Drugi.",
            "## Rozdział drugi",
            f"{_AKAPIT} Trzeci.",
            f"{_AKAPIT} Czwarty.",
        ]
    )
    ocena = ocen_jakosc(tekst, tytul="Tytuł")

    assert ocena.ocena == OCENA_POPRAWNA


def test_puste_sekcje_sa_podejrzane() -> None:
    tekst = "\n\n".join(
        [
            "# Rozdział pierwszy",
            "## Rozdział drugi",
            "## Rozdział trzeci",
            _AKAPIT,
            f"{_AKAPIT} Drugi.",
            f"{_AKAPIT} Trzeci.",
            f"{_AKAPIT} Czwarty.",
        ]
    )
    ocena = ocen_jakosc(tekst, tytul="Tytuł")

    assert ocena.czy_podejrzana
    assert any("nagłówki bez treści pod spodem, liczba: 2" in powod for powod in ocena.powody)


def test_jedna_pusta_sekcja_nie_wystarcza() -> None:
    tekst = "\n\n".join(
        [
            "# Rozdział pierwszy",
            _AKAPIT,
            f"{_AKAPIT} Drugi.",
            f"{_AKAPIT} Trzeci.",
            "## Rozdział bez treści",
        ]
    )
    ocena = ocen_jakosc(tekst, tytul="Tytuł")

    assert ocena.ocena == OCENA_POPRAWNA


def test_tekst_bez_naglowkow_nie_podlega_heurystykom_naglowkowym() -> None:
    """Transkrypcja filmu nie ma nagłówków i nie może być z tego powodu podejrzana."""
    ocena = ocen_jakosc(_tekst_poprawny(), tytul="Tytuł filmu")

    assert ocena.ocena == OCENA_POPRAWNA
