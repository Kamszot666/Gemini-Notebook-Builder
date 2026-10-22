"""Wygląd interfejsu: schematy kolorów, kroje pisma, rozmiar czcionki i kontrast.

Moduł wylicza arkusz stylów z ustawień wyglądu i liczy kontrast według wzoru
WCAG 2. Strony interfejsu używają wyłącznie zmiennych CSS, więc podmiana
jednego bloku ``:root`` zmienia wygląd wszystkich stron naraz.

Moduł nie czyta pliku konfiguracji i nie buduje stron. Do arkusza trafiają tylko
wartości z zamkniętych zbiorów (identyfikatory schematów i krojów, stopnie
rozmiaru) oraz kolory w postaci ``#rrggbb`` sprawdzone ścisłym wzorcem. Wartość,
która tego wzorca nie spełnia, jest zastępowana kolorem schematu domyślnego,
więc przez arkusz nie da się wstrzyknąć kodu CSS.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnb.core.konfiguracja import (
    DOMYSLNY_WYGLAD_KROJ_PISMA,
    DOMYSLNY_WYGLAD_SCHEMAT,
    KROJE_PISMA,
    SCHEMAT_KOLOROW_WLASNY,
    SCHEMATY_KOLOROW,
    STOPNIE_CZCIONKI,
    WZORZEC_KOLORU,
    Konfiguracja,
)

# Progi z wymagań dostępności interfejsu: tekst na poziomie AAA, a obramowania
# i wskaźnik fokusu co najmniej 3 do 1 wobec tła.
PROG_KONTRASTU_TEKSTU = 7.0
PROG_KONTRASTU_ELEMENTOW = 3.0
# Poniżej tej wartości strona ostrzega przy kolorach własnych (poziom AA).
PROG_OSTRZEZENIA_TEKSTU = 4.5

BAZOWY_ROZMIAR_CZCIONKI_PROCENT = 125

_CZARNY = "#000000"
_BIALY = "#ffffff"


@dataclass(frozen=True, slots=True)
class KoloryInterfejsu:
    """Osiem ról kolorystycznych interfejsu."""

    tlo: str
    tekst: str
    odnosnik: str
    przycisk_tlo: str
    przycisk_tekst: str
    obramowanie: str
    fokus: str
    blad: str


@dataclass(frozen=True, slots=True)
class SchematKolorow:
    """Gotowy schemat kolorów z nazwą dla użytkownika."""

    identyfikator: str
    nazwa: str
    kolory: KoloryInterfejsu


SCHEMATY: tuple[SchematKolorow, ...] = (
    SchematKolorow(
        "ciemny",
        "Ciemny, domyślny",
        KoloryInterfejsu(
            tlo="#10131a",
            tekst="#f2f4f8",
            odnosnik="#9ecbff",
            przycisk_tlo="#1d4f91",
            przycisk_tekst="#ffffff",
            obramowanie="#7f8fb3",
            fokus="#ffd54a",
            blad="#ffb4ab",
        ),
    ),
    SchematKolorow(
        "zolty_na_czarnym",
        "Wysoki kontrast: żółty na czarnym",
        KoloryInterfejsu(
            tlo="#000000",
            tekst="#ffff00",
            odnosnik="#00ffff",
            przycisk_tlo="#ffff00",
            przycisk_tekst="#000000",
            obramowanie="#ffff00",
            fokus="#ffffff",
            blad="#ff9e9e",
        ),
    ),
    SchematKolorow(
        "bialy_na_czarnym",
        "Biały na czarnym",
        KoloryInterfejsu(
            tlo="#000000",
            tekst="#ffffff",
            odnosnik="#8ec8ff",
            przycisk_tlo="#ffffff",
            przycisk_tekst="#000000",
            obramowanie="#ffffff",
            fokus="#ffd54a",
            blad="#ffb0b0",
        ),
    ),
    SchematKolorow(
        "czarny_na_bialym",
        "Czarny na białym",
        KoloryInterfejsu(
            tlo="#ffffff",
            tekst="#000000",
            odnosnik="#0033a0",
            przycisk_tlo="#000000",
            przycisk_tekst="#ffffff",
            obramowanie="#000000",
            fokus="#b00000",
            blad="#a00000",
        ),
    ),
    SchematKolorow(
        "ciemny_na_kremowym",
        "Ciemny tekst na kremowym tle",
        KoloryInterfejsu(
            tlo="#fff3d6",
            tekst="#1e1a12",
            odnosnik="#0a3c8c",
            przycisk_tlo="#1e3a6e",
            przycisk_tekst="#ffffff",
            obramowanie="#5c4a1c",
            fokus="#8a2a00",
            blad="#8c1a1a",
        ),
    ),
    SchematKolorow(
        "bezpieczny_dla_barw",
        "Bezpieczny przy zaburzeniach rozpoznawania barw",
        # Paleta oparta na zestawie Okabe i Ito, zaprojektowanym tak, żeby barwy
        # były rozróżnialne także przy najczęstszych zaburzeniach widzenia barw.
        # Błąd jest pomarańczowy, a nie czerwony, i zawsze ma też opis słowami.
        KoloryInterfejsu(
            tlo="#0b0b0b",
            tekst="#ffffff",
            odnosnik="#56b4e9",
            przycisk_tlo="#004f80",
            przycisk_tekst="#ffffff",
            obramowanie="#9aa5b1",
            fokus="#f0e442",
            blad="#e69f00",
        ),
    ),
    SchematKolorow(
        "zblizony_do_gemini",
        "Zbliżony do Gemini Notebook",
        # Przybliżenie na podstawie ciemnej palety bazowej Material Design 3
        # (Google), według tokenów ColorDarkTokens i PaletteTokens z kodu Material 3
        # w AndroidX: powierzchnia (Neutral6), tekst na powierzchni (Neutral90),
        # kolor główny (Primary80), tekst na kolorze głównym (Primary20), kontur
        # (NeutralVariant60), kolor trzeciorzędny (Tertiary80) i kolor błędu (Error80).
        KoloryInterfejsu(
            tlo="#141218",
            tekst="#e6e0e9",
            odnosnik="#d0bcff",
            przycisk_tlo="#d0bcff",
            przycisk_tekst="#381e72",
            obramowanie="#938f99",
            fokus="#efb8c8",
            blad="#f2b8b5",
        ),
    ),
)

_SCHEMAT_DOMYSLNY = SCHEMATY[0]

# Stosy krojów: zawsze kończą się rodziną ogólną, więc brak kroju w systemie
# daje czytelny krój bez szeryfów, a nie krój przeglądarki z szeryfami.
STOSY_KROJOW: dict[str, str] = {
    "atkinson": '"Atkinson Hyperlegible", system-ui, "Segoe UI", sans-serif',
    "systemowy": 'system-ui, "Segoe UI", sans-serif',
    "verdana": 'Verdana, "DejaVu Sans", sans-serif',
    "tahoma": 'Tahoma, "Segoe UI", sans-serif',
    "arial": 'Arial, "Liberation Sans", sans-serif',
    "calibri": 'Calibri, "Segoe UI", sans-serif',
}
NAZWY_KROJOW: dict[str, str] = {
    "atkinson": "Atkinson Hyperlegible",
    "systemowy": "Systemowy (Segoe UI w Windows)",
    "verdana": "Verdana",
    "tahoma": "Tahoma",
    "arial": "Arial",
    "calibri": "Calibri",
}


# Pliki kroju Atkinson Hyperlegible (SIL Open Font License 1.1) leżą w pakiecie
# i są serwowane lokalnie pod adresem /czcionki/NAZWA; bez zewnętrznego CDN.
SCIEZKA_CZCIONEK = "/czcionki/"
PLIKI_CZCIONEK: dict[str, tuple[str, str]] = {
    "AtkinsonHyperlegible-Regular.woff2": ("normal", "400"),
    "AtkinsonHyperlegible-Bold.woff2": ("normal", "700"),
    "AtkinsonHyperlegible-Italic.woff2": ("italic", "400"),
    "AtkinsonHyperlegible-BoldItalic.woff2": ("italic", "700"),
}


def deklaracje_czcionek() -> str:
    """Reguły ``@font-face`` kroju Atkinson Hyperlegible.

    Gdy plik kroju się nie wczyta, przeglądarka przechodzi na dalsze kroje
    z listy ``--czcionka``, czyli na krój systemowy.
    """
    reguly = [
        "@font-face {\n"
        '  font-family: "Atkinson Hyperlegible";\n'
        f"  font-style: {styl}; font-weight: {grubosc}; font-display: swap;\n"
        f'  src: url("{SCIEZKA_CZCIONEK}{plik}") format("woff2");\n'
        "}"
        for plik, (styl, grubosc) in PLIKI_CZCIONEK.items()
    ]
    return "\n".join(reguly)


def luminancja(kolor: str) -> float:
    """Luminancja względna koloru ``#rrggbb`` według WCAG 2."""
    kanaly: list[float] = []
    for poczatek in (1, 3, 5):
        wartosc = int(kolor[poczatek : poczatek + 2], 16) / 255
        kanaly.append(wartosc / 12.92 if wartosc <= 0.03928 else ((wartosc + 0.055) / 1.055) ** 2.4)
    return 0.2126 * kanaly[0] + 0.7152 * kanaly[1] + 0.0722 * kanaly[2]


def kontrast(kolor_a: str, kolor_b: str) -> float:
    """Współczynnik kontrastu dwóch kolorów, od 1 do 21 (wzór WCAG 2)."""
    jasniejszy, ciemniejszy = sorted((luminancja(kolor_a), luminancja(kolor_b)), reverse=True)
    return (jasniejszy + 0.05) / (ciemniejszy + 0.05)


def schemat_o_identyfikatorze(identyfikator: str) -> SchematKolorow | None:
    for schemat in SCHEMATY:
        if schemat.identyfikator == identyfikator:
            return schemat
    return None


def nazwy_schematow() -> dict[str, str]:
    """Identyfikator i nazwa każdego schematu, z kolorami własnymi na końcu."""
    nazwy = {schemat.identyfikator: schemat.nazwa for schemat in SCHEMATY}
    nazwy[SCHEMAT_KOLOROW_WLASNY] = "Kolory własne"
    return nazwy


def kolory_wlasne(konfiguracja: Konfiguracja) -> KoloryInterfejsu:
    """Kolory z pól konfiguracji. Wartość niezgodna ze wzorcem zastępuje kolor domyślny."""
    domyslne = _SCHEMAT_DOMYSLNY.kolory

    def pewny(wartosc: str, zapas: str) -> str:
        return wartosc.lower() if WZORZEC_KOLORU.fullmatch(wartosc) else zapas

    return KoloryInterfejsu(
        tlo=pewny(konfiguracja.wyglad_kolor_tla, domyslne.tlo),
        tekst=pewny(konfiguracja.wyglad_kolor_tekstu, domyslne.tekst),
        odnosnik=pewny(konfiguracja.wyglad_kolor_odnosnikow, domyslne.odnosnik),
        przycisk_tlo=pewny(konfiguracja.wyglad_kolor_przycisku_tla, domyslne.przycisk_tlo),
        przycisk_tekst=pewny(konfiguracja.wyglad_kolor_przycisku_tekstu, domyslne.przycisk_tekst),
        obramowanie=pewny(konfiguracja.wyglad_kolor_obramowania, domyslne.obramowanie),
        fokus=pewny(konfiguracja.wyglad_kolor_fokusu, domyslne.fokus),
        blad=pewny(konfiguracja.wyglad_kolor_bledu, domyslne.blad),
    )


def kolory_obowiazujace(konfiguracja: Konfiguracja) -> KoloryInterfejsu:
    """Kolory wybranego schematu albo kolory własne; nieznany schemat daje domyślny."""
    if konfiguracja.wyglad_schemat == SCHEMAT_KOLOROW_WLASNY:
        return kolory_wlasne(konfiguracja)
    schemat = schemat_o_identyfikatorze(konfiguracja.wyglad_schemat)
    return (schemat or _SCHEMAT_DOMYSLNY).kolory


def fokus_widoczny(kolory: KoloryInterfejsu) -> str:
    """Kolor wskaźnika fokusu, który na pewno widać na tle strony.

    Gdy kolor wybrany przez użytkownika ma wobec tła mniej niż 3 do 1,
    wskaźnik dostaje czerń albo biel, zależnie od tego, co daje większy
    kontrast z tłem. Dzięki temu przy kolorach własnych fokus nie znika.
    """
    if kontrast(kolory.fokus, kolory.tlo) >= PROG_KONTRASTU_ELEMENTOW:
        return kolory.fokus
    return max((_CZARNY, _BIALY), key=lambda kandydat: kontrast(kandydat, kolory.tlo))


def kontrasty_tekstu(kolory: KoloryInterfejsu) -> dict[str, float]:
    """Kontrast każdej pary tekst i tło, z nazwą pary po polsku."""
    return {
        "tekstu do tła": kontrast(kolory.tekst, kolory.tlo),
        "odnośników do tła": kontrast(kolory.odnosnik, kolory.tlo),
        "tekstu przycisków do tła przycisków": kontrast(kolory.przycisk_tekst, kolory.przycisk_tlo),
        "komunikatów o błędach do tła": kontrast(kolory.blad, kolory.tlo),
    }


def ostrzezenia_kontrastu(kolory: KoloryInterfejsu) -> list[str]:
    """Zdania ostrzeżenia dla kolorów, które mogą być nieczytelne. Pusta lista oznacza brak uwag."""
    wynik: list[str] = []
    for para, wartosc in kontrasty_tekstu(kolory).items():
        if wartosc < PROG_OSTRZEZENIA_TEKSTU:
            wynik.append(
                f"Kontrast {para} wynosi {_liczba(wartosc)} do 1, czyli mniej niż "
                f"{_liczba(PROG_OSTRZEZENIA_TEKSTU)} do 1. Tekst może być trudny do odczytania."
            )
    for nazwa, kolor in (
        ("obramowań", kolory.obramowanie),
        ("wskaźnika fokusu", kolory.fokus),
    ):
        wartosc = kontrast(kolor, kolory.tlo)
        if wartosc < PROG_KONTRASTU_ELEMENTOW:
            zdanie = (
                f"Kontrast {nazwa} do tła wynosi {_liczba(wartosc)} do 1, czyli mniej niż "
                f"{_liczba(PROG_KONTRASTU_ELEMENTOW)} do 1."
            )
            if nazwa == "wskaźnika fokusu":
                zdanie += " Wskaźnik fokusu dostanie automatycznie czerń albo biel."
            wynik.append(zdanie)
    return wynik


def opis_kontrastu_tekstu(kolory: KoloryInterfejsu) -> str:
    """Zdanie z wyliczonym kontrastem tekstu do tła, do pokazania na stronie ustawień."""
    return f"Kontrast tekstu do tła: {_liczba(kontrast(kolory.tekst, kolory.tlo))} do 1."


def _liczba(wartosc: float) -> str:
    return f"{wartosc:.1f}".replace(".", ",")


def _jasne_tlo(kolory: KoloryInterfejsu) -> bool:
    return luminancja(kolory.tlo) > 0.4


def zmienne_css(konfiguracja: Konfiguracja) -> str:
    """Blok ``:root`` ze zmiennymi koloru, kroju i skali czcionki dla podanej konfiguracji."""
    kolory = kolory_obowiazujace(konfiguracja)
    kroj = (
        konfiguracja.wyglad_kroj_pisma
        if konfiguracja.wyglad_kroj_pisma in KROJE_PISMA
        else DOMYSLNY_WYGLAD_KROJ_PISMA
    )
    stopien = (
        konfiguracja.wyglad_rozmiar_czcionki
        if konfiguracja.wyglad_rozmiar_czcionki in STOPNIE_CZCIONKI
        else 100
    )
    return (
        ":root {\n"
        f"  color-scheme: {'light' if _jasne_tlo(kolory) else 'dark'};\n"
        f"  --tlo: {kolory.tlo};\n"
        f"  --tekst: {kolory.tekst};\n"
        f"  --odnosnik: {kolory.odnosnik};\n"
        f"  --przycisk-tlo: {kolory.przycisk_tlo};\n"
        f"  --przycisk-tekst: {kolory.przycisk_tekst};\n"
        f"  --ramka: {kolory.obramowanie};\n"
        f"  --fokus: {fokus_widoczny(kolory)};\n"
        f"  --blad: {kolory.blad};\n"
        f"  --czcionka: {STOSY_KROJOW[kroj]};\n"
        f"  --skala: {stopien / 100:g};\n"
        "}"
    )


def css_wygladu(konfiguracja: Konfiguracja) -> str:
    """Element ``style`` z wyglądem wybranym przez użytkownika, wstawiany po arkuszu podstawowym."""
    return f'<style id="wyglad-uzytkownika">\n{zmienne_css(konfiguracja)}\n</style>'


def zmienne_domyslne() -> str:
    """Blok ``:root`` schematu domyślnego, wstawiany do arkusza podstawowego."""
    return zmienne_css(Konfiguracja())


__all__ = [
    "BAZOWY_ROZMIAR_CZCIONKI_PROCENT",
    "DOMYSLNY_WYGLAD_SCHEMAT",
    "NAZWY_KROJOW",
    "PROG_KONTRASTU_ELEMENTOW",
    "PROG_KONTRASTU_TEKSTU",
    "PROG_OSTRZEZENIA_TEKSTU",
    "SCHEMATY",
    "SCHEMATY_KOLOROW",
    "STOSY_KROJOW",
    "KoloryInterfejsu",
    "SchematKolorow",
    "css_wygladu",
    "fokus_widoczny",
    "kolory_obowiazujace",
    "kolory_wlasne",
    "kontrast",
    "kontrasty_tekstu",
    "luminancja",
    "nazwy_schematow",
    "opis_kontrastu_tekstu",
    "ostrzezenia_kontrastu",
    "schemat_o_identyfikatorze",
    "zmienne_css",
    "zmienne_domyslne",
]
