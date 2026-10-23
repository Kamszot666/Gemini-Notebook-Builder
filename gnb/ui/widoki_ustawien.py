"""Strona ustawień: zakładki tematyczne z polami konfiguracji.

Zakładki są zbudowane według wzorca WAI-ARIA Authoring Practices „Tabs”:
``tablist``, ``tab`` i ``tabpanel``, strzałki przesuwają między zakładkami,
a klawisz Tab prowadzi do pól w panelu. Bez JavaScriptu lista zakładek jest
ukryta, a wszystkie panele są widoczne jeden pod drugim, każdy z nagłówkiem.

Moduł buduje wyłącznie HTML. Nie czyta ani nie zapisuje pliku konfiguracji.
Każdy napis, także nazwa zmiennej środowiskowej i ścieżka z konfiguracji,
przechodzi przez ``gnb.ui.html.escapuj``. Pola tekstowe mają widoczną etykietę
``label for``, a nie mają ``placeholder`` ani ``aria-label``; opis pola jest
przypięty przez ``aria-describedby``.
"""

from __future__ import annotations

from collections.abc import Mapping

from gnb.core.konfiguracja import SCHEMAT_KOLOROW_WLASNY, Konfiguracja
from gnb.core.skrot import KLAWISZE_SKROTU, rozbierz_kombinacje
from gnb.ui.html import escapuj
from gnb.ui.ustawienia import (
    PRZYROSTEK_KLAWISZA_SKROTU,
    ZAKLADKI,
    PoleUstawien,
    Rodzaj,
    Zakladka,
    nazwa_kontrolki_skrotu,
    opis_zmiany,
    wartosc_do_pola_formularza,
    wartosc_domyslna_slowami,
    wartosc_slowami,
)
from gnb.ui.widoki import (
    BladPola,
    _dokument,  # pyright: ignore[reportPrivateUsage]
    _pole_csrf,  # pyright: ignore[reportPrivateUsage]
)
from gnb.ui.wyglad import kolory_wlasne, opis_kontrastu_tekstu, ostrzezenia_kontrastu

SCIEZKA_USTAWIEN = "/ustawienia"
SCIEZKA_ZAPISU_USTAWIEN = "/ustawienia/zapisz"
SCIEZKA_PRZYWRACANIA_USTAWIEN = "/ustawienia/przywroc"
SCIEZKA_PRZYWRACANIA_SCHEMATU = "/ustawienia/przywroc-schemat"
NAZWA_PRZYCISKU_SCHEMATU = "Przywróć schemat domyślny"
IDENTYFIKATOR_ZAKLADKI_WYGLADU = "wyglad"
NAZWA_PRZYCISKU_ZAPISU = "Zapisz ustawienia"
NAZWA_PRZYCISKU_PRZYWRACANIA = "Przywróć ustawienia domyślne tej zakładki"

_STYL_USTAWIEN = """
[role="tablist"] { display: flex; flex-wrap: wrap; gap: 0.5rem; margin: 1.5rem 0 0; }
[role="tablist"][hidden] { display: none; }
[role="tab"] {
  margin: 0; min-height: 2.75rem; background: var(--tlo); color: var(--tekst);
  border: 2px solid var(--ramka);
}
[role="tab"][aria-selected="true"] {
  background: var(--przycisk-tlo); color: var(--przycisk-tekst);
  border: 4px solid var(--fokus); text-decoration: underline;
}
.pole-wyboru {
  display: flex; align-items: flex-start; gap: 0.6rem; margin-top: 1.25rem; min-height: 2.75rem;
}
.pole-wyboru input { width: 1.5rem; height: 1.5rem; margin-top: 0.3rem; flex: none; }
.pole-wyboru label { margin-top: 0; }
input[type="number"], select { max-width: 20rem; }
fieldset { margin: 1.25rem 0 0; padding: 0.75rem 1rem; border: 2px solid var(--ramka); }
legend { font-weight: 600; padding: 0 0.5rem; }
.przyciski-zakladki { display: flex; flex-wrap: wrap; gap: 0.75rem; }
.wartosc-stala { margin: 1.25rem 0 0; font-weight: 600; }
""".strip()

_SKRYPT_ZAKLADEK = """
(function () {
  var lista = document.getElementById('zakladki-ustawien');
  if (!lista) { return; }
  var karty = [].slice.call(lista.querySelectorAll('[role="tab"]'));
  var panele = karty.map(function (karta) {
    return document.getElementById(karta.getAttribute('aria-controls'));
  });
  function wybierz(numer, przenies) {
    karty.forEach(function (karta, i) {
      var wybrana = i === numer;
      karta.setAttribute('aria-selected', wybrana ? 'true' : 'false');
      karta.tabIndex = wybrana ? 0 : -1;
      panele[i].hidden = !wybrana;
    });
    if (przenies) { karty[numer].focus(); }
  }
  var poczatkowa = parseInt(lista.getAttribute('data-aktywna'), 10) || 0;
  lista.hidden = false;
  wybierz(poczatkowa, false);
  karty.forEach(function (karta, i) {
    karta.addEventListener('click', function () { wybierz(i, false); });
    karta.addEventListener('keydown', function (zdarzenie) {
      var n = karty.length;
      var cel = null;
      if (zdarzenie.key === 'ArrowRight') { cel = (i + 1) % n; }
      else if (zdarzenie.key === 'ArrowLeft') { cel = (i + n - 1) % n; }
      else if (zdarzenie.key === 'Home') { cel = 0; }
      else if (zdarzenie.key === 'End') { cel = n - 1; }
      if (cel !== null) { zdarzenie.preventDefault(); wybierz(cel, true); }
    });
  });
})();
""".strip()

_SKRYPT_FOKUS_KOMUNIKATU = """
(function () {
  var komunikat = document.getElementById('komunikat-ustawien');
  if (komunikat) { komunikat.focus(); }
  var bledy = document.getElementById('bledy-formularza');
  if (bledy) { bledy.focus(); }
})();
""".strip()


def strona_ustawien(
    *,
    konfiguracja: Konfiguracja,
    zablokowane: Mapping[str, tuple[str, str]],
    token_csrf: str,
    sciezka_pliku: str,
    aktywna_zakladka: str = "",
    komunikat: str = "",
    ostrzezenie: str = "",
    bledy: list[BladPola] | None = None,
    wpisane: Mapping[str, str] | None = None,
    zakladka_z_bledami: str = "",
) -> str:
    """Strona ustawień ze wszystkimi zakładkami.

    Argument ``zablokowane`` mapuje pole na parę: nazwa zmiennej środowiskowej
    i jej wartość. Takie pole jest pokazane jako niezmienialne. Argument
    ``wpisane`` to wartości z odrzuconego formularza zakładki
    ``zakladka_z_bledami``; zastępują wartości z konfiguracji, żeby użytkownik
    nie musiał wpisywać wszystkiego od nowa.
    """
    bledy = bledy or []
    wpisane = wpisane or {}
    numer_aktywnej = _numer_zakladki(aktywna_zakladka or zakladka_z_bledami)
    przyciski = "\n".join(
        f'<button type="button" role="tab" id="karta-{escapuj(zakladka.identyfikator)}" '
        f'aria-controls="panel-{escapuj(zakladka.identyfikator)}" '
        f'aria-selected="{"true" if numer == numer_aktywnej else "false"}" '
        f'tabindex="{0 if numer == numer_aktywnej else -1}">{escapuj(zakladka.tytul)}</button>'
        for numer, zakladka in enumerate(ZAKLADKI)
    )
    panele = "\n".join(
        _panel(
            zakladka,
            konfiguracja,
            zablokowane,
            token_csrf,
            wpisane if zakladka.identyfikator == zakladka_z_bledami else {},
            bledy if zakladka.identyfikator == zakladka_z_bledami else [],
        )
        for zakladka in ZAKLADKI
    )
    czesci = [
        "<h1>Ustawienia</h1>",
        '<p><a href="/">Wróć do strony głównej</a></p>',
        f'<p class="pomoc">Zmiany zapisują się w pliku konfiguracji: {escapuj(sciezka_pliku)}. '
        "Pole ustawione zmienną środowiskową jest tylko do odczytu, bo zmienna ma pierwszeństwo "
        "przed plikiem.</p>",
    ]
    if ostrzezenie:
        czesci.append(f'<p class="pomoc">{escapuj(ostrzezenie)}</p>')
    if komunikat:
        czesci.append(
            f'<div class="blok" id="komunikat-ustawien" role="status" aria-live="polite" '
            f'tabindex="-1">{escapuj(komunikat)}</div>'
        )
    if konfiguracja.wyglad_schemat == SCHEMAT_KOLOROW_WLASNY:
        czesci.insert(1, formularz_przywracania_schematu(token_csrf, "przywroc-schemat-gora"))
    czesci.append(
        f'<div role="tablist" id="zakladki-ustawien" aria-label="Zakładki ustawień" hidden '
        f'data-aktywna="{numer_aktywnej}">\n{przyciski}\n</div>'
    )
    czesci.append(panele)
    czesci.append('<p><a href="/">Wróć do strony głównej</a></p>')
    skrypt = _SKRYPT_ZAKLADEK
    if komunikat or bledy:
        skrypt += "\n" + _SKRYPT_FOKUS_KOMUNIKATU
    return _dokument("Ustawienia", "\n".join(czesci), skrypt=skrypt, styl_dodatkowy=_STYL_USTAWIEN)


def _numer_zakladki(identyfikator: str) -> int:
    for numer, zakladka in enumerate(ZAKLADKI):
        if zakladka.identyfikator == identyfikator:
            return numer
    return 0


def _panel(
    zakladka: Zakladka,
    konfiguracja: Konfiguracja,
    zablokowane: Mapping[str, tuple[str, str]],
    token_csrf: str,
    wpisane: Mapping[str, str],
    bledy: list[BladPola],
) -> str:
    identyfikator = escapuj(zakladka.identyfikator)
    pola = "\n".join(
        _pole(pole, konfiguracja, zablokowane, wpisane, bledy) for pole in zakladka.pola
    )
    lista_bledow = ""
    if bledy:
        pozycje = "".join(
            f'<li><a href="#pole-{escapuj(blad.pole)}">{escapuj(blad.komunikat)}</a></li>'
            for blad in bledy
        )
        lista_bledow = (
            '<div class="blok bledy" id="bledy-formularza" role="alert" tabindex="-1">\n'
            f"<h3>Formularz zawiera błędy</h3>\n<ul>{pozycje}</ul>\n</div>\n"
        )
    dodatek_wygladu = ""
    po_formularzu = ""
    if zakladka.identyfikator == IDENTYFIKATOR_ZAKLADKI_WYGLADU:
        dodatek_wygladu = _informacja_o_kontrascie(konfiguracja)
        po_formularzu = "\n" + formularz_przywracania_schematu(token_csrf, "przywroc-schemat-panel")
    return (
        f'<section role="tabpanel" id="panel-{identyfikator}" '
        f'aria-labelledby="naglowek-{identyfikator}">\n'
        f'<h2 id="naglowek-{identyfikator}">{escapuj(zakladka.tytul)}</h2>\n'
        f'<p class="pomoc">{escapuj(zakladka.wstep)}</p>\n'
        f"{dodatek_wygladu}"
        f'<form method="post" action="{SCIEZKA_ZAPISU_USTAWIEN}" '
        f'enctype="application/x-www-form-urlencoded">\n'
        f"{_pole_csrf(token_csrf)}\n"
        f'<input type="hidden" name="zakladka" value="{identyfikator}">\n'
        f"{lista_bledow}{pola}\n"
        '<div class="przyciski-zakladki">\n'
        f'<button type="submit">{NAZWA_PRZYCISKU_ZAPISU}</button>\n'
        f'<button type="submit" formaction="{SCIEZKA_PRZYWRACANIA_USTAWIEN}" formnovalidate>'
        f"{NAZWA_PRZYCISKU_PRZYWRACANIA}</button>\n"
        f"</div>\n</form>{po_formularzu}\n</section>"
    )


def formularz_przywracania_schematu(token_csrf: str, identyfikator: str) -> str:
    """Osobny formularz z przyciskiem powrotu do schematu domyślnego.

    Blok ma stałe, własne kolory (klasa ``ratunek``), niezależne od wybranego
    schematu, żeby przycisk był widoczny nawet wtedy, gdy kolory własne
    zrobiły z reszty strony nieczytelną plamę.
    """
    return (
        f'<form method="post" action="{SCIEZKA_PRZYWRACANIA_SCHEMATU}" class="ratunek" '
        f'id="{escapuj(identyfikator)}">\n'
        f"{_pole_csrf(token_csrf)}\n"
        f'<button type="submit">{NAZWA_PRZYCISKU_SCHEMATU}</button>\n'
        "<p>Ustawia schemat Ciemny, domyślny. Zapisane kolory własne zostają w pliku.</p>\n"
        "</form>"
    )


def _informacja_o_kontrascie(konfiguracja: Konfiguracja) -> str:
    """Akapit o kontraście kolorów własnych; dla gotowych schematów pusty."""
    if konfiguracja.wyglad_schemat != SCHEMAT_KOLOROW_WLASNY:
        return ""
    kolory = kolory_wlasne(konfiguracja)
    zdania = [
        f"Używasz kolorów własnych. {opis_kontrastu_tekstu(kolory)}",
        *ostrzezenia_kontrastu(kolory),
    ]
    return f'<p class="pomoc" id="kontrast-kolorow">{escapuj(" ".join(zdania))}</p>\n'


def _opis(pole: PoleUstawien, *, zablokowane: bool) -> str:
    """Opis pola: do czego służy, wartość domyślna i od kiedy działa zmiana."""
    czesci = [pole.opis, f"Wartość domyślna: {wartosc_domyslna_slowami(pole)}."]
    if not zablokowane and pole.rodzaj is not Rodzaj.TYLKO_ODCZYT:
        czesci.append(opis_zmiany(pole))
    return " ".join(czesci)


def _pole(
    pole: PoleUstawien,
    konfiguracja: Konfiguracja,
    zablokowane: Mapping[str, tuple[str, str]],
    wpisane: Mapping[str, str],
    bledy: list[BladPola],
) -> str:
    nazwa = escapuj(pole.nazwa)
    identyfikator = f"pole-{nazwa}"
    opis_id = f"{identyfikator}-opis"
    aktualna = getattr(konfiguracja, pole.nazwa)

    if pole.nazwa in zablokowane:
        zmienna, _wartosc = zablokowane[pole.nazwa]
        return (
            f'<p class="wartosc-stala" id="{identyfikator}">{escapuj(pole.etykieta)}: '
            f"{escapuj(wartosc_slowami(pole, aktualna))}</p>\n"
            f'<p class="pomoc" id="{opis_id}">Ta wartość jest ustawiona zmienną środowiskową '
            f"{escapuj(zmienna)}. Zmienna ma pierwszeństwo przed plikiem konfiguracji, więc "
            "zmień ją poza aplikacją. "
            f"{escapuj(_opis(pole, zablokowane=True))}</p>"
        )
    if pole.rodzaj is Rodzaj.TYLKO_ODCZYT:
        return (
            f'<p class="wartosc-stala" id="{identyfikator}">{escapuj(pole.etykieta)}: '
            f"{escapuj(wartosc_slowami(pole, aktualna))}</p>\n"
            f'<p class="pomoc" id="{opis_id}">{escapuj(_opis(pole, zablokowane=False))}</p>'
        )

    atrybut_bledu, komunikat_bledu = "", ""
    opisy = [opis_id]
    for blad in bledy:
        if blad.pole == pole.nazwa:
            blad_id = f"{identyfikator}-blad"
            opisy.append(blad_id)
            atrybut_bledu = ' aria-invalid="true"'
            komunikat_bledu = f'\n<p class="pomoc" id="{blad_id}">{escapuj(blad.komunikat)}</p>'
            break
    opisany = f' aria-describedby="{escapuj(" ".join(opisy))}"{atrybut_bledu}'
    opis = f'<p class="pomoc" id="{opis_id}">{escapuj(_opis(pole, zablokowane=False))}</p>'

    if pole.rodzaj is Rodzaj.SKROT:
        return _pole_skrotu(pole, aktualna, wpisane, opisany, opis, komunikat_bledu)

    if pole.rodzaj is Rodzaj.FORMATY:
        return _pole_formatow(pole, aktualna, wpisane, opisany, opis, komunikat_bledu)

    if pole.rodzaj is Rodzaj.LOGICZNE:
        zaznaczone = pole.nazwa in wpisane if wpisane else bool(aktualna)
        return (
            f'<div class="pole-wyboru"><input type="checkbox" id="{identyfikator}" '
            f'name="{nazwa}" value="1"{" checked" if zaznaczone else ""}{opisany}>'
            f'<label for="{identyfikator}">{escapuj(pole.etykieta)}</label></div>\n'
            f"{opis}{komunikat_bledu}"
        )

    wartosc = wpisane.get(pole.nazwa, wartosc_do_pola_formularza(pole, aktualna))
    etykieta = f'<label for="{identyfikator}">{escapuj(pole.etykieta)}</label>'
    if pole.rodzaj in (Rodzaj.WYBOR, Rodzaj.WYBOR_LICZBY):
        nazwy = dict(zip(pole.opcje, pole.nazwy_opcji or pole.opcje, strict=True))
        if wartosc and wartosc not in nazwy:
            nazwy[wartosc] = wartosc
        pozycje = "\n".join(
            f'<option value="{escapuj(opcja)}"{" selected" if opcja == wartosc else ""}>'
            f"{escapuj(nazwa_opcji)}</option>"
            for opcja, nazwa_opcji in nazwy.items()
        )
        kontrolka = f'<select id="{identyfikator}" name="{nazwa}"{opisany}>\n{pozycje}\n</select>'
    elif pole.rodzaj in (Rodzaj.LICZBA, Rodzaj.LICZBA_RZECZYWISTA):
        krok = "1" if pole.rodzaj is Rodzaj.LICZBA else "any"
        granice = "" if pole.minimum is None else f' min="{pole.minimum:g}"'
        granice += "" if pole.maksimum is None else f' max="{pole.maksimum:g}"'
        kontrolka = (
            f'<input type="number" id="{identyfikator}" name="{nazwa}" step="{krok}"'
            f'{granice} value="{escapuj(wartosc)}"{opisany}>'
        )
    else:
        kontrolka = (
            f'<input type="text" id="{identyfikator}" name="{nazwa}" '
            f'value="{escapuj(wartosc)}"{opisany}>'
        )
    return f"{etykieta}\n{kontrolka}\n{opis}{komunikat_bledu}"


_ETYKIETY_MODYFIKATOROW_SKROTU = (
    ("control", "Control"),
    ("alt", "Alt"),
    ("shift", "Shift"),
    ("windows", "Windows"),
)


_ETYKIETY_FORMATOW_WYNIKOWYCH = (
    ("md", "Plik Markdown (MD)"),
    ("txt", "Plik tekstowy (TXT)"),
)


def _pole_formatow(
    pole: PoleUstawien,
    aktualna: object,
    wpisane: Mapping[str, str],
    opisany: str,
    opis: str,
    komunikat_bledu: str,
) -> str:
    """Pole formatów wynikowych: dwa pola wyboru w grupie z nazwą pola jako legendą.

    Każde pole wyboru ma zwykłą etykietę ``label for``, a opis pola jest
    przypięty do ``fieldset``, tak jak przy kombinacji skrótu.
    """
    identyfikator = f"pole-{escapuj(pole.nazwa)}"
    aktualne = (
        {str(wartosc) for wartosc in aktualna} if isinstance(aktualna, (tuple, list)) else set()
    )
    pola_wyboru: list[str] = []
    for klucz, etykieta in _ETYKIETY_FORMATOW_WYNIKOWYCH:
        nazwa_kontrolki = f"{pole.nazwa}_{klucz}"
        zaznaczone = nazwa_kontrolki in wpisane if wpisane else klucz in aktualne
        pola_wyboru.append(
            f'<div class="pole-wyboru"><input type="checkbox" id="{identyfikator}-{klucz}" '
            f'name="{escapuj(nazwa_kontrolki)}" value="1"{" checked" if zaznaczone else ""}>'
            f'<label for="{identyfikator}-{klucz}">{etykieta}</label></div>'
        )
    wnetrze = "\n".join(pola_wyboru)
    return (
        f'<fieldset id="{identyfikator}" tabindex="-1"{opisany}>\n'
        f"<legend>{escapuj(pole.etykieta)}</legend>\n{wnetrze}\n</fieldset>\n"
        f"{opis}{komunikat_bledu}"
    )


def _pole_skrotu(
    pole: PoleUstawien,
    aktualna: str,
    wpisane: Mapping[str, str],
    opisany: str,
    opis: str,
    komunikat_bledu: str,
) -> str:
    """Pole kombinacji skrótu: cztery pola wyboru modyfikatorów i lista „Klawisz”.

    Brak pola przechwytującego naciśnięcie, bo NVDA przechwytuje część
    klawiszy. Każda kontrolka ma zwykłą etykietę ``label for``. Całość leży
    w ``fieldset`` z ``legend``, a opis pola jest przypięty do ``fieldset``.
    """
    identyfikator = f"pole-{escapuj(pole.nazwa)}"
    kombinacja = rozbierz_kombinacje(aktualna)
    wybrane = {
        "control": kombinacja.control,
        "alt": kombinacja.alt,
        "shift": kombinacja.shift,
        "windows": kombinacja.windows,
    }
    klawisz = kombinacja.klawisz
    if wpisane:
        wybrane = {
            przyrostek: nazwa_kontrolki_skrotu(pole, przyrostek) in wpisane
            for przyrostek in wybrane
        }
        klawisz = wpisane.get(nazwa_kontrolki_skrotu(pole, PRZYROSTEK_KLAWISZA_SKROTU), "")
    pola_wyboru = "\n".join(
        f'<div class="pole-wyboru"><input type="checkbox" '
        f'id="{identyfikator}-{przyrostek}" '
        f'name="{escapuj(nazwa_kontrolki_skrotu(pole, przyrostek))}" value="1"'
        f"{' checked' if wybrane[przyrostek] else ''}>"
        f'<label for="{identyfikator}-{przyrostek}">{etykieta}</label></div>'
        for przyrostek, etykieta in _ETYKIETY_MODYFIKATOROW_SKROTU
    )
    identyfikator_klawisza = f"{identyfikator}-{PRZYROSTEK_KLAWISZA_SKROTU}"
    pozycje = "\n".join(
        f'<option value="{escapuj(nazwa)}"{" selected" if nazwa == klawisz else ""}>'
        f"{escapuj(nazwa)}</option>"
        for nazwa in KLAWISZE_SKROTU
    )
    nazwa_listy = escapuj(nazwa_kontrolki_skrotu(pole, PRZYROSTEK_KLAWISZA_SKROTU))
    lista = (
        f'<label for="{identyfikator_klawisza}">Klawisz</label>\n'
        f'<select id="{identyfikator_klawisza}" name="{nazwa_listy}">\n'
        f"{pozycje}\n</select>"
    )
    return (
        f'<fieldset id="{identyfikator}" tabindex="-1"{opisany}>\n'
        f"<legend>{escapuj(pole.etykieta)}</legend>\n{pola_wyboru}\n{lista}\n</fieldset>\n"
        f"{opis}{komunikat_bledu}"
    )
