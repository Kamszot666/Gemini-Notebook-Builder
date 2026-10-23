"""Generowanie stron HTML interfejsu WWW.

Strony są semantycznym HTML5 z ciemnym motywem o wysokim kontraście, bez żadnego
zasobu z zewnętrznego serwera. Style są w jednym elemencie ``style`` na stronie,
a dwa krótkie skrypty — odpytywanie postępu i licznik znaków — są wbudowane
w stronę, nie ładowane z pliku. Wymagania z sekcji jedenastej CLAUDE.md są
realizowane wprost: prawdziwe elementy ``button``, ``a``, ``input``, ``textarea``;
etykieta ``label for`` przy każdym polu; błędy walidacji powiązane z polem przez
``aria-describedby`` i ``aria-invalid`` oraz zebrane w liście na górze formularza;
postęp i licznik znaków w regionie ``role="status"`` z ``aria-live="polite"``.

Cała treść pochodząca ze źródła, z nazwy pliku, z pola użytkownika i z komunikatu
błędu przechodzi przez ``gnb.ui.html.escapuj``. Widok nigdy nie wstawia surowego
napisu do HTML.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from gnb.persistence.pola_notatnika import PolaNotatnika
from gnb.ui import wyglad
from gnb.ui.csrf import NAZWA_POLA_FORMULARZA
from gnb.ui.html import escapuj, tekst_z_odnosnikami
from gnb.ui.projekty import ProjektNaLiscie
from gnb.ui.stan_skrotu import KomunikatSkrotu, StanSzkicu
from gnb.ui.zadania import InformacjaOZadaniu, StanZadania

SCIEZKA_POSTEPU = "/postep"
# Miejsce, w które serwer wstawia arkusz z wyglądem wybranym przez użytkownika.
ZNACZNIK_WYGLADU = "<!--gnb-wyglad-->"


@dataclass(frozen=True, slots=True)
class BladPola:
    """Jeden błąd walidacji powiązany z konkretnym polem formularza po jego identyfikatorze."""

    pole: str
    komunikat: str


@dataclass(frozen=True, slots=True)
class DaneFormularzaProjektu:
    """Wpisane wartości formularza nowego projektu, zwracane przy błędzie walidacji."""

    nazwa_projektu: str = ""
    tekst: str = ""
    adresy: str = ""
    grupa: str = ""
    projekt: str = ""
    wybor_grupy: str = ""
    nazwa_grupy: str = ""


@dataclass(frozen=True, slots=True)
class PodsumowanieWyniku:
    """Liczby z zakończonego przetwarzania, pokazywane na stronie projektu."""

    liczba_przetworzonych: int
    liczba_pominietych: int
    liczba_bledow: int
    katalog_projektu: str
    wznowiono: bool


_STYLE = (
    wyglad.deklaracje_czcionek()
    + "\n"
    + wyglad.zmienne_domyslne()
    + """
* { box-sizing: border-box; }
html { font-size: calc(125% * var(--skala)); }
body {
  margin: 0; padding: 1.5rem;
  background: var(--tlo); color: var(--tekst);
  font-family: var(--czcionka); font-size: 1rem; line-height: 1.6;
  overflow-wrap: anywhere;
}
main { max-width: 52rem; margin: 0 auto; }
h1, h2, h3 { line-height: 1.3; }
a { color: var(--odnosnik); text-decoration: underline; text-underline-offset: 0.15em; }
:focus-visible, [tabindex="-1"]:focus {
  outline: 3px solid var(--fokus); outline-offset: 2px;
}
label { display: block; font-weight: 600; margin-top: 1.25rem; }
input[type="text"], input[type="number"], select, textarea {
  width: 100%; max-width: 100%; min-height: 2.75rem; margin-top: 0.35rem; padding: 0.6rem;
  background: var(--tlo); color: var(--tekst);
  border: 2px solid var(--ramka); border-radius: 4px;
  font: inherit;
}
input[type="checkbox"] { accent-color: var(--odnosnik); }
textarea { min-height: 8rem; }
button {
  margin-top: 1.25rem; padding: 0.6rem 1.2rem; min-height: 2.75rem; min-width: 2.75rem;
  background: var(--przycisk-tlo); color: var(--przycisk-tekst);
  border: 2px solid var(--ramka); border-radius: 4px;
  font: inherit; cursor: pointer;
}
button:hover { text-decoration: underline; }
.pole-pliku, .akcja-formularza { display: block; }
.blok { margin: 2rem 0; padding: 1.25rem; border: 2px solid var(--ramka); border-radius: 6px; }
.bledy { border: 3px solid var(--blad); }
.bledy h2, .bledy h3 { color: var(--blad); }
.bledy ul { margin: 0.5rem 0 0; }
[role="status"] { margin-top: 0.5rem; font-weight: 600; }
pre {
  white-space: pre-wrap; word-wrap: break-word;
  background: var(--tlo); border: 2px solid var(--ramka); padding: 1rem; border-radius: 4px;
  font: 1rem/1.5 ui-monospace, "Consolas", monospace;
}
.pomoc { color: var(--tekst); font-weight: 400; font-size: 0.95rem; }
.ratunek {
  margin: 1.5rem 0; padding: 1rem; background: #000000; color: #ffffff;
  border: 3px solid #ffff00; border-radius: 6px;
}
.ratunek button {
  background: #ffff00; color: #000000; border: 3px solid #ffffff;
}
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
@media (forced-colors: active) {
  button, [role="tab"], .blok { border: 2px solid ButtonText; }
  [role="tab"][aria-selected="true"] { border: 4px solid Highlight; }
  :focus-visible, [tabindex="-1"]:focus { outline: 3px solid Highlight; }
}
""".strip()
)


def _dokument(tytul: str, tresc: str, *, skrypt: str = "", styl_dodatkowy: str = "") -> str:
    """Składa pełny dokument HTML wokół treści strony."""
    dodatek_stylu = f"\n{styl_dodatkowy}" if styl_dodatkowy else ""
    fragment_skryptu = f"\n<script>\n{skrypt}\n</script>" if skrypt else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="pl">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escapuj(tytul)}</title>\n"
        f"<style>\n{_STYLE}{dodatek_stylu}\n</style>\n"
        f"{ZNACZNIK_WYGLADU}\n"
        "</head>\n<body>\n<main>\n"
        f"{tresc}\n"
        "</main>"
        f"{fragment_skryptu}\n"
        "</body>\n</html>\n"
    )


def _lista_bledow(bledy: list[BladPola]) -> str:
    """Buduje widoczną listę błędów walidacji z odnośnikami do pól."""
    if not bledy:
        return ""
    pozycje = "".join(
        f'<li><a href="#{escapuj(blad.pole)}">{escapuj(blad.komunikat)}</a></li>' for blad in bledy
    )
    return (
        '<div class="blok bledy" id="bledy-formularza" role="alert" tabindex="-1">\n'
        "<h2>Formularz zawiera błędy</h2>\n"
        f"<ul>{pozycje}</ul>\n"
        "</div>"
    )


def _opis_bledu_pola(bledy: list[BladPola], pole: str) -> tuple[str, str]:
    """Zwraca parę: fragment atrybutów pola oraz fragment z komunikatem błędu pod polem."""
    for blad in bledy:
        if blad.pole == pole:
            opis_id = f"{pole}-blad"
            atrybuty = f' aria-invalid="true" aria-describedby="{escapuj(opis_id)}"'
            komunikat = f'<p class="pomoc" id="{escapuj(opis_id)}">{escapuj(blad.komunikat)}</p>'
            return atrybuty, komunikat
    return "", ""


def _pole_csrf(token_csrf: str) -> str:
    return (
        f'<input type="hidden" name="{escapuj(NAZWA_POLA_FORMULARZA)}" '
        f'value="{escapuj(token_csrf)}">'
    )


def sciezka_projektu(nazwa: str) -> str:
    """Buduje ścieżkę adresu strony projektu, z nazwą zakodowaną do postaci bezpiecznej w URL."""
    return "/projekt/" + quote(nazwa, safe="")


NAZWA_POLA_TEKSTU = "Tu wklej tekst"
NAZWA_POLA_ADRESOW = "Tu wklej adresy stron www i adresy do YouTube, po jednym w każdym wierszu"


SCIEZKA_WYBORU_PROJEKTU = "/przejdz-do-projektu"
WYBOR_BEZ_GRUPY = "__bez__"
WYBOR_NOWA_GRUPA = "__nowa__"
PREFIKS_GRUPY = "g:"
NAZWA_PROJEKTU_NOWEGO = "Nowy projekt"


def _atrybuty_pola_z_opisem(
    bledy: list[BladPola], pole: str, pomoc_id: str | None = None
) -> tuple[str, str]:
    """Jak `_opis_bledu_pola`, ale łączy opis pomocniczy pola z komunikatem błędu.

    Atrybut `aria-describedby` może wystąpić w znaczniku tylko raz, więc przy polu,
    które ma i stały opis, i błąd, oba identyfikatory trafiają do jednego atrybutu.
    """
    opisy = [pomoc_id] if pomoc_id else []
    nieprawidlowe = ""
    komunikat = ""
    for blad in bledy:
        if blad.pole == pole:
            opis_id = f"{pole}-blad"
            opisy.append(opis_id)
            nieprawidlowe = ' aria-invalid="true"'
            komunikat = f'<p class="pomoc" id="{escapuj(opis_id)}">{escapuj(blad.komunikat)}</p>'
            break
    opis = f' aria-describedby="{escapuj(" ".join(opisy))}"' if opisy else ""
    return nieprawidlowe + opis, komunikat


def _opcje_projektow(projekty: list[ProjektNaLiscie], wybrany: str) -> str:
    """Pozycje listy „Projekt”: „Nowy projekt”, a pod nim wszystkie projekty ze stanem."""
    opcje = [
        f'<option value=""{" selected" if not wybrany else ""}>{NAZWA_PROJEKTU_NOWEGO}</option>'
    ]
    for projekt in projekty:
        zaznaczona = " selected" if projekt.nazwa == wybrany else ""
        opcje.append(
            f'<option value="{escapuj(projekt.nazwa)}"{zaznaczona}>'
            f"{escapuj(projekt.nazwa)}, {projekt.stan}</option>"
        )
    return "\n".join(opcje)


def _opcje_grup(grupy: list[str], wybrana: str) -> str:
    """Pozycje listy „Grupa”: „Bez grupy”, „Nowa grupa” i grupy wybranego projektu."""
    opcje = [
        (WYBOR_BEZ_GRUPY, "Bez grupy"),
        (WYBOR_NOWA_GRUPA, "Nowa grupa"),
        *((PREFIKS_GRUPY + grupa, grupa) for grupa in grupy),
    ]
    return "\n".join(
        f'<option value="{escapuj(wartosc)}"{" selected" if wartosc == wybrana else ""}>'
        f"{escapuj(tekst)}</option>"
        for wartosc, tekst in opcje
    )


def strona_glowna(
    *,
    projekty: list[ProjektNaLiscie],
    token_csrf: str,
    dane: DaneFormularzaProjektu | None = None,
    bledy: list[BladPola] | None = None,
    aktywny_projekt_skrotu: str | None = None,
    ostatni_komunikat_skrotu: KomunikatSkrotu | None = None,
    grupy_projektu: list[str] | None = None,
    wybrany_projekt: str = "",
    szkic_tekstu: StanSzkicu | None = None,
) -> str:
    """Strona główna: jeden formularz dodawania materiałów do nowego albo istniejącego projektu.

    Argument `wybrany_projekt` to nazwa projektu zaznaczonego na liście „Projekt”
    przy wczytaniu strony, a `grupy_projektu` to grupy tego projektu. Po błędzie
    walidacji zaznaczenie wraca do tego, co użytkownik wybrał w wysłanym formularzu.

    Argument `szkic_tekstu` to tekst zaznaczony w przeglądarce globalnym skrótem
    dla wybranego projektu. Wypełnia pole „Tu wklej tekst” bez JavaScriptu, ale
    tylko przy zwykłym wczytaniu strony: po błędzie walidacji pole zachowuje to,
    co użytkownik wysłał.
    """
    szkic = szkic_tekstu or StanSzkicu("", 0)
    tekst_pola = dane.tekst if dane is not None else szkic.tekst
    dane = dane or DaneFormularzaProjektu()
    bledy = bledy or []
    grupy = grupy_projektu or []
    wybrany = dane.projekt if dane.projekt or dane.wybor_grupy else wybrany_projekt
    domyslna_grupa = dane.wybor_grupy or (PREFIKS_GRUPY + grupy[-1] if grupy else WYBOR_BEZ_GRUPY)

    atrybuty_projekt, blad_projekt = _atrybuty_pola_z_opisem(bledy, "projekt")
    atrybuty_nazwa, blad_nazwa = _atrybuty_pola_z_opisem(
        bledy, "nazwa_projektu", "pomoc-nazwa-projektu"
    )
    atrybuty_grupa, blad_grupa = _atrybuty_pola_z_opisem(bledy, "wybor_grupy")
    atrybuty_nazwa_grupy, blad_nazwa_grupy = _atrybuty_pola_z_opisem(
        bledy, "nazwa_grupy", "pomoc-nazwa-grupy"
    )
    atrybuty_tekst, blad_tekst = _opis_bledu_pola(bledy, "tekst")
    atrybuty_adresy, blad_adresy = _opis_bledu_pola(bledy, "adresy")
    brak_projektow = (
        '<p class="pomoc">Nie ma jeszcze żadnych projektów.</p>\n' if not projekty else ""
    )

    formularz = f"""<h1>Gemini Notebook Builder</h1>
<p><a href="/ustawienia">Ustawienia</a></p>
<form class="blok" id="formularz-glowny" method="post" action="/projekt/nowy"
  enctype="multipart/form-data">
{_pole_csrf(token_csrf)}
{_lista_bledow(bledy)}
<h2>Dodaj materiały</h2>
<button type="submit" hidden tabindex="-1" aria-hidden="true"></button>
<label for="projekt">Projekt</label>
<select id="projekt" name="projekt"{atrybuty_projekt}>
{_opcje_projektow(projekty, wybrany)}
</select>
{blad_projekt}{brak_projektow}<button type="submit" id="przejdz-do-projektu"
  formaction="{escapuj(SCIEZKA_WYBORU_PROJEKTU)}" formmethod="post"
  formenctype="application/x-www-form-urlencoded" formnovalidate>Przejdź do projektu</button>
<button type="submit" id="ustaw-aktywny-projekt"
  formaction="{escapuj(sciezka_projektu(wybrany or "nowy"))}/aktywny-skrot" formmethod="post"
  formenctype="application/x-www-form-urlencoded" formnovalidate>
Ustaw jako aktywny projekt skrótu</button>
<div id="blok-nazwy-projektu">
<label for="nazwa_projektu">Nazwa nowego projektu</label>
<input type="text" id="nazwa_projektu" name="nazwa_projektu"
  value="{escapuj(dane.nazwa_projektu)}"{atrybuty_nazwa}>
<p class="pomoc" id="pomoc-nazwa-projektu">Wpisz tylko wtedy, gdy na liście Projekt
wybrano Nowy projekt.</p>
{blad_nazwa}</div>
<label for="wybor_grupy">Grupa</label>
<select id="wybor_grupy" name="wybor_grupy"{atrybuty_grupa}>
{_opcje_grup(grupy, domyslna_grupa)}
</select>
{blad_grupa}<div id="blok-nazwy-grupy">
<label for="nazwa_grupy">Nazwa nowej grupy</label>
<input type="text" id="nazwa_grupy" name="nazwa_grupy"
  value="{escapuj(dane.nazwa_grupy)}"{atrybuty_nazwa_grupy}>
<p class="pomoc" id="pomoc-nazwa-grupy">Wpisz tylko wtedy, gdy na liście Grupa
wybrano Nowa grupa.</p>
{blad_nazwa_grupy}</div>
<p id="komunikat-formularza" role="status" aria-live="polite"></p>
<label for="tekst">{NAZWA_POLA_TEKSTU}</label>
<textarea id="tekst" name="tekst" data-wersja-szkicu="{szkic.wersja}"
  {atrybuty_tekst}>{escapuj(tekst_pola)}</textarea>
<p id="komunikat-szkicu" role="status" aria-live="polite"></p>
{blad_tekst}
<label for="adresy">{NAZWA_POLA_ADRESOW}</label>
<textarea id="adresy" name="adresy"{atrybuty_adresy}>{escapuj(dane.adresy)}</textarea>
{blad_adresy}
<div class="pole-pliku">
<label for="pliki">Pliki z dysku</label>
<input type="file" id="pliki" name="pliki" multiple>
</div>
<div class="akcja-formularza">
<button type="submit">Dodaj materiały i rozpocznij przetwarzanie</button>
</div>
</form>"""

    tresc = formularz + _sekcja_skrotu_glowna(aktywny_projekt_skrotu, ostatni_komunikat_skrotu)
    skrypt = _SKRYPT_FORMULARZA_GLOWNEGO.replace("NAZWA_POLA_CSRF", NAZWA_POLA_FORMULARZA)
    skrypt = skrypt.replace("WYBOR_BEZ_GRUPY", WYBOR_BEZ_GRUPY)
    skrypt = skrypt.replace("WYBOR_NOWA_GRUPA", WYBOR_NOWA_GRUPA)
    skrypt = skrypt.replace("PREFIKS_GRUPY", PREFIKS_GRUPY)
    skrypt += "\n" + _skrypt_szkicu("tekst", "komunikat-szkicu", lista_projektow="projekt")
    if bledy:
        skrypt += "\n" + _SKRYPT_FOKUS_BLEDOW
    return _dokument("Gemini Notebook Builder", tresc, skrypt=skrypt)


def _sekcja_skrotu_glowna(
    aktywny_projekt_skrotu: str | None, ostatni_komunikat_skrotu: KomunikatSkrotu | None
) -> str:
    """Stan globalnego skrótu na stronie głównej: bez przycisku, on jest przy projekcie."""
    status = (
        f"Aktywny projekt skrótu: {escapuj(aktywny_projekt_skrotu)}."
        if aktywny_projekt_skrotu
        else "Brak aktywnego projektu skrótu."
    )
    return (
        '<div class="blok">\n<h2>Globalny skrót klawiszowy</h2>\n'
        f'<p id="stan-aktywnego-projektu">{status}</p>\n'
        f"{_akapit_ostatniego_komunikatu(ostatni_komunikat_skrotu)}\n</div>"
    )


def _akapit_ostatniego_komunikatu(komunikat: KomunikatSkrotu | None) -> str:
    if komunikat is None:
        return ""
    wynik = "powodzenie" if komunikat.sukces else "porażka"
    tekst = tekst_z_odnosnikami(komunikat.tekst)
    return f'<p class="pomoc">Ostatnie zdarzenie skrótu ({wynik}): {tekst}</p>'


def _sekcja_stanu_projektu(
    sciezka: str, opis: ProjektNaLiscie | None, mozna_wznowic: bool, token_csrf: str
) -> str:
    """Stan projektu na jego stronie, z przyciskiem wznowienia dla niedokończonego."""
    if opis is None:
        return ""
    czesci = ['<div class="blok">', "<h2>Stan projektu</h2>"]
    if opis.komunikat_bledu:
        czesci.append(f"<p>Stan: uszkodzony. {tekst_z_odnosnikami(opis.komunikat_bledu)}</p>")
    else:
        czesci.append(
            f"<p>Stan: {opis.stan}. Źródeł w checkpoincie: {opis.liczba_zrodel}. "
            f"Ostatnia zmiana: {escapuj(opis.czas_ostatniej_zmiany or 'nieznana')}.</p>"
        )
        if not opis.zakonczony and mozna_wznowic:
            czesci.append(
                f'<form method="post" action="{escapuj(sciezka)}/wznow">\n'
                f"{_pole_csrf(token_csrf)}\n"
                '<button type="submit">Wznów ten projekt</button>\n</form>'
            )
    czesci.append("</div>")
    return "\n".join(czesci)


def strona_projektu(
    *,
    nazwa: str,
    informacja: InformacjaOZadaniu | None,
    pola: PolaNotatnika,
    limit_znakow_instrukcji: int,
    token_csrf: str,
    podsumowanie: PodsumowanieWyniku | None = None,
    raport: str | None = None,
    bledy: list[BladPola] | None = None,
    aktywny_projekt_skrotu: str | None = None,
    ostatni_komunikat_skrotu: KomunikatSkrotu | None = None,
    grupy_projektu: list[str] | None = None,
    dane_dosylania: DaneFormularzaProjektu | None = None,
    bledy_dosylania: list[BladPola] | None = None,
    zrodla_html: str = "",
    opis_projektu: ProjektNaLiscie | None = None,
    szkic_tekstu: StanSzkicu | None = None,
    pliki_wynikowe: list[str] | None = None,
    komunikat_pliku: str = "",
) -> str:
    """Strona projektu: region postępu, dwa pola tekstowe oraz raport po zakończeniu.

    Argument `zrodla_html` to gotowy fragment z wykazem źródeł i ich działaniami,
    zbudowany przez `gnb.ui.widoki_zrodel`. Jest przekazywany jako napis, żeby
    ten moduł nie zależał od modułu, który sam z niego korzysta.
    """
    bledy = bledy or []
    sciezka = sciezka_projektu(nazwa)
    trwa = informacja is not None and informacja.stan is StanZadania.TRWA
    czesci = [
        f"<h1>Projekt: {escapuj(nazwa)}</h1>",
        '<p><a href="/ustawienia">Ustawienia</a></p>',
        _sekcja_stanu_projektu(sciezka, opis_projektu, not trwa, token_csrf),
        _sekcja_postepu(sciezka, informacja),
    ]

    fragment_wyniku = _fragment_wyniku(
        podsumowanie,
        raport,
        sciezka,
        grupy_projektu or [],
        token_csrf,
        dane_dosylania,
        bledy_dosylania,
        zrodla_html,
        nazwa,
        szkic_tekstu or StanSzkicu("", 0),
        pliki_wynikowe or [],
        komunikat_pliku,
    )
    czesci.append(f'<div id="wynik-po-zakonczeniu">{fragment_wyniku}</div>')

    czesci.append(
        _sekcja_skrotu_projektu(
            sciezka, nazwa, aktywny_projekt_skrotu, ostatni_komunikat_skrotu, token_csrf
        )
    )
    czesci.append(_sekcja_pol(sciezka, pola, limit_znakow_instrukcji, token_csrf, bledy))
    czesci.append(f'<p><a href="{escapuj(sciezka)}">Odśwież stan</a></p>')
    czesci.append('<p><a href="/">Wróć do strony głównej</a></p>')

    fragmenty_skryptu = [
        _SKRYPT_LICZNIKA,
        _skrypt_szkicu("dosylanie-tekst", "komunikat-szkicu-dosylania"),
        _SKRYPT_OTWIERANIA_PLIKOW,
        _SKRYPT_FOKUS_WYNIKOW,
    ]
    if trwa:
        fragmenty_skryptu.append(
            _SKRYPT_POSTEPU.replace("SCIEZKA_POSTEPU", escapuj(SCIEZKA_POSTEPU))
        )
    if bledy or bledy_dosylania:
        fragmenty_skryptu.append(_SKRYPT_FOKUS_BLEDOW)
    return _dokument(f"Projekt: {nazwa}", "\n".join(czesci), skrypt="\n".join(fragmenty_skryptu))


def _fragment_wyniku(
    podsumowanie: PodsumowanieWyniku | None,
    raport: str | None,
    sciezka: str,
    grupy_projektu: list[str],
    token_csrf: str,
    dane_dosylania: DaneFormularzaProjektu | None,
    bledy_dosylania: list[BladPola] | None,
    zrodla_html: str = "",
    nazwa: str = "",
    szkic: StanSzkicu | None = None,
    pliki_wynikowe: list[str] | None = None,
    komunikat_pliku: str = "",
) -> str:
    """Buduje blok pokazywany po zakończeniu przebiegu: podsumowanie, raport, źródła i dosyłanie.

    Blok jest częścią strony budowanej przy wejściu na nią. Po zakończeniu
    przebiegu w trakcie odsłuchu skrypt ``_SKRYPT_POSTEPU`` niczego nie wstawia
    do strony, tylko dodaje odnośnik do jej ponownego wczytania: wstawianie
    bloku w miejscu przy działającym czytniku ekranu przenosiło fokus. Formularz
    dosyłania pojawia się tylko wtedy, gdy jest już co najmniej jeden raport.
    """
    if podsumowanie is None and raport is None and not zrodla_html:
        return ""
    czesci = []
    if podsumowanie is not None:
        czesci.append(_sekcja_podsumowania(podsumowanie, naglowek_wynikow=True))
    if raport is not None:
        czesci.append(_sekcja_raportu(raport, naglowek_wynikow=podsumowanie is None))
        czesci.append(
            _sekcja_plikow_wynikowych(sciezka, pliki_wynikowe or [], token_csrf, komunikat_pliku)
        )
    if zrodla_html:
        czesci.append(zrodla_html)
    if raport is not None:
        czesci.append(
            _formularz_dosylania(
                sciezka, grupy_projektu, token_csrf, dane_dosylania, bledy_dosylania, nazwa, szkic
            )
        )
    return "\n".join(czesci)


def _sekcja_raportu(raport: str, *, naglowek_wynikow: bool = False) -> str:
    """Blok raportu końcowego z adresami http i https jako klikalnymi odnośnikami.

    Gdy blok jest pierwszą sekcją wyników, jego nagłówek można ustawić jako cel
    przejścia po zakończeniu przetwarzania (``naglowek_wynikow``).
    """
    atrybuty = ' id="naglowek-wynikow" tabindex="-1"' if naglowek_wynikow else ""
    return (
        f'<div class="blok">\n<h2{atrybuty}>Raport końcowy</h2>\n'
        f"<pre>{tekst_z_odnosnikami(raport)}</pre>\n</div>"
    )


def _sekcja_plikow_wynikowych(
    sciezka: str, pliki: list[str], token_csrf: str, komunikat: str
) -> str:
    """Wykaz plików wynikowych projektu, każdy z przyciskiem otwarcia i podglądem tekstu.

    Przeglądarka nie otworzy pliku lokalnego z odnośnika ``file://`` na stronie
    wczytanej przez http, więc otwarcie robi serwer: przycisk wysyła metodą POST
    z tokenem CSRF samą nazwę pliku. Podgląd jako tekst jest zwykłym odnośnikiem
    i pokazuje treść jako zwykły tekst, nigdy jako HTML.
    """
    if not pliki:
        return ""
    pozycje = []
    for nazwa_pliku in pliki:
        podglad = ""
        if nazwa_pliku.lower().endswith((".md", ".txt")):
            podglad = (
                f'<p><a href="{escapuj(sciezka)}/plik/{quote(nazwa_pliku, safe="")}">'
                f"Podgląd pliku {escapuj(nazwa_pliku)} jako tekst</a></p>"
            )
        pozycje.append(
            f'<li>\n<form class="otworz-plik" method="post" '
            f'action="{escapuj(sciezka)}/otworz-plik">\n'
            f"{_pole_csrf(token_csrf)}\n"
            f'<input type="hidden" name="plik" value="{escapuj(nazwa_pliku)}">\n'
            f'<div class="akcja-formularza">'
            f'<button type="submit">Otwórz plik {escapuj(nazwa_pliku)}</button></div>\n'
            f"</form>\n{podglad}\n</li>"
        )
    return (
        '<div class="blok">\n<h2>Pliki wynikowe</h2>\n'
        '<p class="pomoc">Przycisk otwiera plik w aplikacji domyślnej systemu na tym '
        "komputerze, na przykład w Notepad++.</p>\n"
        f'<p id="komunikat-plikow" role="status" aria-live="polite">{escapuj(komunikat)}</p>\n'
        f"<ul>\n{chr(10).join(pozycje)}\n</ul>\n</div>"
    )


def _formularz_dosylania(
    sciezka: str,
    grupy_projektu: list[str],
    token_csrf: str,
    dane: DaneFormularzaProjektu | None,
    bledy: list[BladPola] | None,
    nazwa: str = "",
    szkic: StanSzkicu | None = None,
) -> str:
    """Formularz dosyłania kolejnych źródeł do już przetworzonego projektu.

    Nazwy pól niesie widoczna etykieta `label for`, tak jak na stronie głównej,
    bez podpowiedzi wewnątrz pola i bez `aria-label`. Nazwa grupy jest wymagana
    i ma listę podpowiedzi z grupami, które projekt już zna, więc kolejne źródło
    trafia do istniejącego pliku grupy bez przepisywania jej nazwy.

    Pole „Tu wklej tekst” jest wypełnione szkicem tekstu zaznaczonego w przeglądarce
    globalnym skrótem, bez JavaScriptu. Po błędzie walidacji zachowuje to, co
    użytkownik wysłał.
    """
    szkic = szkic or StanSzkicu("", 0)
    tekst_pola = dane.tekst if dane is not None else szkic.tekst
    dane = dane or DaneFormularzaProjektu(grupa=grupy_projektu[-1] if grupy_projektu else "")
    bledy = bledy or []
    atrybuty_tekst, blad_tekst = _opis_bledu_pola(bledy, "dosylanie-tekst")
    atrybuty_adresy, blad_adresy = _opis_bledu_pola(bledy, "dosylanie-adresy")
    atrybuty_grupa, blad_grupa = _opis_bledu_pola(bledy, "dosylanie-grupa")
    opcje_grup = "".join(f'<option value="{escapuj(grupa)}">' for grupa in grupy_projektu)
    return f"""<form class="blok" method="post" action="{escapuj(sciezka)}/dosylanie"
  enctype="multipart/form-data">
{_pole_csrf(token_csrf)}
{_lista_bledow(bledy)}
<h2>Dodaj kolejne źródła</h2>
<label for="dosylanie-tekst">{NAZWA_POLA_TEKSTU}</label>
<textarea id="dosylanie-tekst" name="tekst" data-projekt="{escapuj(nazwa)}"
  data-wersja-szkicu="{szkic.wersja}"{atrybuty_tekst}>{escapuj(tekst_pola)}</textarea>
<p id="komunikat-szkicu-dosylania" role="status" aria-live="polite"></p>
{blad_tekst}
<label for="dosylanie-adresy">{NAZWA_POLA_ADRESOW}</label>
<textarea id="dosylanie-adresy" name="adresy"{atrybuty_adresy}>{escapuj(dane.adresy)}</textarea>
{blad_adresy}
<div class="pole-pliku">
<label for="dosylanie-pliki">Pliki z dysku</label>
<input type="file" id="dosylanie-pliki" name="pliki" multiple>
</div>
<label for="dosylanie-grupa">Nazwa grupy tematycznej</label>
<input type="text" id="dosylanie-grupa" name="grupa" list="dosylanie-grupy"
  value="{escapuj(dane.grupa)}" required{atrybuty_grupa}>
<datalist id="dosylanie-grupy">{opcje_grup}</datalist>
{blad_grupa}
<div class="akcja-formularza">
<button type="submit">Dodaj źródła i uruchom kolejny przebieg</button>
</div>
</form>"""


def _sekcja_postepu(sciezka: str, informacja: InformacjaOZadaniu | None) -> str:
    if informacja is None:
        return (
            '<div class="blok">\n<h2 id="naglowek-stanu">Stan</h2>\n'
            "<p>Ten projekt nie ma bieżącego przetwarzania w tej sesji serwera. "
            'Możesz je <a href="/">rozpocząć od nowa albo wznowić ze strony głównej</a>.</p>\n'
            "</div>"
        )
    stan_slowny = {
        StanZadania.TRWA: "trwa",
        StanZadania.ZAKONCZONE: "zakończone",
        StanZadania.BLAD: "zakończone błędem",
    }[informacja.stan]
    tresc = tekst_z_odnosnikami(informacja.komunikat_postepu or "Przygotowanie do pracy.")
    blad = (
        f'<p class="pomoc">Powód błędu: {tekst_z_odnosnikami(informacja.komunikat_bledu)}</p>'
        if informacja.komunikat_bledu
        else ""
    )
    koniec = "nie" if informacja.stan is StanZadania.TRWA else "tak"
    akapit_postepu = (
        f'<p id="postep-tresc" role="status" aria-live="polite" data-koniec="{koniec}">{tresc}</p>'
    )
    return (
        f'<div class="blok">\n<h2 id="naglowek-stanu" tabindex="-1">'
        f"Stan przetwarzania: {stan_slowny}</h2>\n"
        f"{akapit_postepu}\n"
        f"{blad}\n</div>"
    )


def _sekcja_podsumowania(
    podsumowanie: PodsumowanieWyniku, *, naglowek_wynikow: bool = False
) -> str:
    """Podsumowanie przebiegu; jego nagłówek jest celem przejścia po zakończeniu pracy."""
    wznowienie = "tak" if podsumowanie.wznowiono else "nie"
    atrybuty = ' id="naglowek-wynikow" tabindex="-1"' if naglowek_wynikow else ""
    return (
        f'<div class="blok">\n<h2{atrybuty}>Podsumowanie</h2>\n<ul>\n'
        f"<li>Źródła przetworzone: {podsumowanie.liczba_przetworzonych}</li>\n"
        f"<li>Źródła pominięte: {podsumowanie.liczba_pominietych}</li>\n"
        f"<li>Źródła z błędem: {podsumowanie.liczba_bledow}</li>\n"
        f"<li>Wznowiono istniejący projekt: {wznowienie}</li>\n"
        f"<li>Katalog projektu: {escapuj(podsumowanie.katalog_projektu)}</li>\n"
        "</ul>\n</div>"
    )


def _sekcja_skrotu_projektu(
    sciezka: str,
    nazwa: str,
    aktywny_projekt_skrotu: str | None,
    ostatni_komunikat_skrotu: KomunikatSkrotu | None,
    token_csrf: str,
) -> str:
    """Stan globalnego skrótu na stronie projektu, z przyciskiem ustawienia go jako aktywnego.

    Przycisk nie pokazuje się, gdy ten projekt już jest aktywny — nie ma co
    ustawiać jeszcze raz tego samego.
    """
    if aktywny_projekt_skrotu == nazwa:
        status = "Ten projekt jest teraz aktywnym projektem globalnego skrótu."
        przycisk = ""
    else:
        status = (
            f"Aktywny projekt skrótu: {escapuj(aktywny_projekt_skrotu)}."
            if aktywny_projekt_skrotu
            else "Brak aktywnego projektu skrótu."
        )
        przycisk = (
            f'<form method="post" action="{escapuj(sciezka)}/aktywny-skrot">\n'
            f"{_pole_csrf(token_csrf)}\n"
            '<button type="submit">Ustaw jako aktywny projekt skrótu</button>\n'
            "</form>"
        )
    return (
        '<div class="blok">\n<h2>Globalny skrót klawiszowy</h2>\n'
        f"<p>{status}</p>\n"
        f"{przycisk}\n"
        f"{_akapit_ostatniego_komunikatu(ostatni_komunikat_skrotu)}\n</div>"
    )


NAZWA_INSTRUKCJI = "Instrukcja systemowa notatnika"
NAZWA_PROMPTU = "Prompt dla mechanizmu wyszukującego źródła"


def _sekcja_pol(
    sciezka: str,
    pola: PolaNotatnika,
    limit_znakow_instrukcji: int,
    token_csrf: str,
    bledy: list[BladPola],
) -> str:
    atrybuty_instrukcja, blad_instrukcja = _opis_bledu_pola(bledy, "instrukcja_systemowa")
    uzyte = len(pola.instrukcja_systemowa)
    licznik = (
        f"Użyto {uzyte} z {limit_znakow_instrukcji} znaków, "
        f"pozostało {limit_znakow_instrukcji - uzyte}."
    )
    textarea_instrukcja = (
        f'<label for="instrukcja_systemowa">{NAZWA_INSTRUKCJI}</label>\n'
        '<textarea id="instrukcja_systemowa" name="instrukcja_systemowa" '
        f'data-limit="{limit_znakow_instrukcji}"{atrybuty_instrukcja}>'
        f"{escapuj(pola.instrukcja_systemowa)}</textarea>"
    )
    textarea_prompt = (
        f'<label for="prompt_wyszukiwania">{NAZWA_PROMPTU}</label>\n'
        '<textarea id="prompt_wyszukiwania" name="prompt_wyszukiwania" '
        'aria-describedby="pomoc-prompt">'
        f"{escapuj(pola.prompt_wyszukiwania)}</textarea>"
    )
    pomoc_prompt = (
        '<p class="pomoc" id="pomoc-prompt">Aplikacja nigdy nie uruchamia tego promptu sama. '
        "Zapisuje go tylko z projektem.</p>"
    )
    return f"""<form class="blok" method="post" action="{escapuj(sciezka)}/pola">
{_pole_csrf(token_csrf)}
<h2>Pola notatnika</h2>
{textarea_instrukcja}
<p id="licznik-instrukcji" role="status" aria-live="polite"
  data-limit="{limit_znakow_instrukcji}">{escapuj(licznik)}</p>
{blad_instrukcja}
{textarea_prompt}
{pomoc_prompt}
<button type="submit">Zapisz pola</button>
</form>
<p><a href="{escapuj(sciezka)}/prompt">Pokaż prompt wyszukiwania do skopiowania</a></p>"""


def strona_promptu(*, nazwa: str, prompt: str) -> str:
    """Osobna strona z samym promptem wyszukiwania w polu tylko do odczytu."""
    sciezka = sciezka_projektu(nazwa)
    tresc = prompt or "Pole promptu wyszukiwania jest puste."
    return _dokument(
        f"Prompt wyszukiwania: {nazwa}",
        f"""<h1>Prompt wyszukiwania — projekt {escapuj(nazwa)}</h1>
<div class="blok">
<p>Poniższa treść jest przeznaczona do skopiowania i użycia poza aplikacją.
Aplikacja nigdzie jej nie wysyła.</p>
<label for="prompt-do-skopiowania">Treść promptu</label>
<textarea id="prompt-do-skopiowania" readonly>{escapuj(tresc)}</textarea>
</div>
<p><a href="{escapuj(sciezka)}">Wróć do projektu</a></p>""",
    )


def strona_bledu(*, kod: int, tytul: str, komunikat: str) -> str:
    """Strona błędu 403, 404 albo błędu wewnętrznego, z komunikatem po polsku."""
    return _dokument(
        f"Błąd {kod}",
        f"""<h1>{escapuj(tytul)}</h1>
<div class="blok">
<p>{tekst_z_odnosnikami(komunikat)}</p>
</div>
<p><a href="/">Wróć do strony głównej</a></p>""",
    )


_SKRYPT_POSTEPU = """
(function () {
  var region = document.getElementById('postep-tresc');
  var naglowek = document.getElementById('naglowek-stanu');
  if (!region || region.getAttribute('data-koniec') === 'tak') { return; }
  function odswiez() {
    if (region.getAttribute('data-koniec') === 'tak') { return; }
    fetch('SCIEZKA_POSTEPU', { headers: { 'Accept': 'application/json' } })
      .then(function (o) { return o.ok ? o.text() : null; })
      .then(function (t) {
        if (t === null) { return; }
        var dane;
        try { dane = JSON.parse(t); } catch (e) { return; }
        if (dane.komunikat && dane.komunikat !== region.textContent) {
          region.textContent = dane.komunikat;
        }
        if (dane.stan && dane.stan !== 'trwa') {
          region.setAttribute('data-koniec', 'tak');
          if (naglowek && dane.naglowek) { naglowek.textContent = dane.naglowek; }
          setTimeout(function () {
            window.location.replace(window.location.pathname + '?gotowe=1#naglowek-wynikow');
          }, 700);
        }
      })
      .catch(function () {});
  }
  odswiez();
  setInterval(odswiez, 4000);
})();
""".strip()

_SKRYPT_OTWIERANIA_PLIKOW = """
(function () {
  var region = document.getElementById('komunikat-plikow');
  var formularze = document.querySelectorAll('form.otworz-plik');
  if (!region || !window.fetch) { return; }
  function obsluz(zdarzenie) {
    zdarzenie.preventDefault();
    var formularz = zdarzenie.currentTarget;
    var tresc = new URLSearchParams(new FormData(formularz)).toString();
    fetch(formularz.action, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: tresc
    })
      .then(function (o) { return o.json().catch(function () { return null; }); })
      .then(function (dane) {
        region.textContent = (dane && dane.komunikat) ? dane.komunikat
          : 'Nie udało się otworzyć pliku.';
      })
      .catch(function () { region.textContent = 'Nie udało się połączyć z serwerem.'; });
  }
  for (var i = 0; i < formularze.length; i++) {
    formularze[i].addEventListener('submit', obsluz);
  }
})();
""".strip()

_SKRYPT_FOKUS_WYNIKOW = """
(function () {
  if (window.location.hash !== '#naglowek-wynikow') { return; }
  var cel = document.getElementById('naglowek-wynikow')
    || document.getElementById('naglowek-stanu');
  if (cel) { cel.focus(); }
})();
""".strip()

_SKRYPT_FORMULARZA_GLOWNEGO = """
(function () {
  var projekt = document.getElementById('projekt');
  var grupa = document.getElementById('wybor_grupy');
  var blokProjektu = document.getElementById('blok-nazwy-projektu');
  var nazwaProjektu = document.getElementById('nazwa_projektu');
  var blokGrupy = document.getElementById('blok-nazwy-grupy');
  var nazwaGrupy = document.getElementById('nazwa_grupy');
  var przejdz = document.getElementById('przejdz-do-projektu');
  var ustaw = document.getElementById('ustaw-aktywny-projekt');
  var region = document.getElementById('komunikat-formularza');
  var stanAktywnego = document.getElementById('stan-aktywnego-projektu');
  var pole = document.querySelector('#formularz-glowny input[name="NAZWA_POLA_CSRF"]');
  if (!projekt || !grupa || !blokProjektu || !blokGrupy) { return; }
  var czasomierz = null;
  var numer = 0;
  function pokaz(blok, wejscie, widoczny) {
    blok.hidden = !widoczny;
    wejscie.required = widoczny;
  }
  function odswiezWidocznosc() {
    var nowy = projekt.value === '';
    pokaz(blokProjektu, nazwaProjektu, nowy);
    pokaz(blokGrupy, nazwaGrupy, grupa.value === 'WYBOR_NOWA_GRUPA');
    if (przejdz) { przejdz.hidden = nowy; }
    if (ustaw) {
      ustaw.hidden = nowy;
      if (!nowy) {
        ustaw.setAttribute('formaction',
          '/projekt/' + encodeURIComponent(projekt.value) + '/aktywny-skrot');
      }
    }
  }
  function ustawGrupy(lista, domyslna) {
    while (grupa.options.length) { grupa.remove(0); }
    grupa.add(new Option('Bez grupy', 'WYBOR_BEZ_GRUPY'));
    grupa.add(new Option('Nowa grupa', 'WYBOR_NOWA_GRUPA'));
    for (var i = 0; i < lista.length; i++) {
      grupa.add(new Option(lista[i], 'PREFIKS_GRUPY' + lista[i]));
    }
    grupa.value = domyslna ? 'PREFIKS_GRUPY' + domyslna : 'WYBOR_BEZ_GRUPY';
    odswiezWidocznosc();
  }
  function odmiana(n) {
    if (n === 1) { return 'grupa'; }
    var reszta = n % 10;
    var setki = n % 100;
    return (reszta >= 2 && reszta <= 4 && (setki < 12 || setki > 14)) ? 'grupy' : 'grup';
  }
  function ogloszenie(czesci) {
    if (region) { region.textContent = czesci.join(' '); }
  }
  function zmianaProjektu(nazwa, moj) {
    var baza = '/projekt/' + encodeURIComponent(nazwa);
    var grupyZapytanie = fetch(baza + '/grupy', { headers: { 'Accept': 'application/json' } })
      .then(function (o) { return o.ok ? o.json() : null; })
      .catch(function () { return null; });
    var aktywnyZapytanie = fetch(baza + '/aktywny-skrot', {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
      },
      body: 'NAZWA_POLA_CSRF=' + encodeURIComponent(pole ? pole.value : '')
    })
      .then(function (o) { return o.ok ? o.json() : null; })
      .catch(function () { return null; });
    Promise.all([grupyZapytanie, aktywnyZapytanie]).then(function (wyniki) {
      if (moj !== numer) { return; }
      var czesci = [];
      var dane = wyniki[0];
      var aktywny = wyniki[1];
      if (aktywny && aktywny.aktywny) {
        czesci.push('Aktywny projekt skrótu: ' + aktywny.aktywny + '.');
        if (stanAktywnego) {
          stanAktywnego.textContent = 'Aktywny projekt skrótu: ' + aktywny.aktywny + '.';
        }
      }
      if (dane) {
        ustawGrupy(dane.grupy, dane.domyslna);
        var liczba = dane.grupy.length;
        czesci.push(liczba === 0
          ? 'Ten projekt nie ma grup.'
          : 'Lista grup zaktualizowana, ' + liczba + ' ' + odmiana(liczba) + '.');
      } else {
        czesci.push('Nie udało się pobrać listy grup tego projektu.');
      }
      ogloszenie(czesci);
    });
  }
  projekt.addEventListener('change', function () {
    odswiezWidocznosc();
    if (czasomierz) { clearTimeout(czasomierz); }
    var moj = ++numer;
    var wybrany = projekt.value;
    if (wybrany === '') {
      ustawGrupy([], '');
      ogloszenie([]);
      return;
    }
    czasomierz = setTimeout(function () { zmianaProjektu(wybrany, moj); }, 700);
  });
  grupa.addEventListener('change', odswiezWidocznosc);
  if (ustaw) {
    ustaw.addEventListener('click', function (zdarzenie) {
      if (projekt.value === '' || !window.fetch) { return; }
      zdarzenie.preventDefault();
      fetch('/projekt/' + encodeURIComponent(projekt.value) + '/aktywny-skrot', {
        method: 'POST',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/x-www-form-urlencoded'
        },
        body: 'NAZWA_POLA_CSRF=' + encodeURIComponent(pole ? pole.value : '')
      })
        .then(function (o) { return o.ok ? o.json() : null; })
        .then(function (dane) {
          if (dane && dane.aktywny) {
            var zdanie = 'Aktywny projekt skrótu: ' + dane.aktywny + '.';
            if (stanAktywnego) { stanAktywnego.textContent = zdanie; }
            ogloszenie([zdanie]);
          } else {
            ogloszenie(['Nie udało się ustawić aktywnego projektu skrótu.']);
          }
        })
        .catch(function () {
          ogloszenie(['Nie udało się ustawić aktywnego projektu skrótu.']);
        });
    });
  }
  odswiezWidocznosc();
})();
""".strip()

_SKRYPT_SZKICU = """
(function () {
  var pole = document.getElementById('POLE_ID');
  var region = document.getElementById('REGION_ID');
  var lista = LISTA_PROJEKTOW;
  if (!pole || !region) { return; }
  function biezacyProjekt() {
    return lista ? lista.value : (pole.getAttribute('data-projekt') || '');
  }
  var projekt = biezacyProjekt();
  var znany = null;
  var wersja = null;
  var naKoniec = false;
  var ostatnieOgloszenie = 0;
  var ogloszenieOczekuje = false;
  function ustawNaKoncu() {
    var n = pole.value.length;
    pole.setSelectionRange(n, n);
  }
  function ogloszenie() {
    if (ogloszenieOczekuje) { return; }
    ogloszenieOczekuje = true;
    var opoznienie = Math.max(0, 4000 - (Date.now() - ostatnieOgloszenie));
    setTimeout(function () {
      region.textContent = '';
      setTimeout(function () {
        region.textContent = 'Dodano zaznaczony tekst do pola Tu wklej tekst.';
      }, 50);
      ostatnieOgloszenie = Date.now();
      ogloszenieOczekuje = false;
    }, opoznienie);
  }
  function dopisz(tekst) {
    var koniec = pole.value.length;
    if (koniec > 0 && pole.value.charAt(koniec - 1) !== '\\n') { tekst = '\\n' + tekst; }
    if (document.activeElement === pole) {
      pole.setRangeText(tekst, koniec, koniec, 'preserve');
    } else {
      pole.setRangeText(tekst, koniec, koniec, 'end');
      naKoniec = true;
    }
  }
  pole.addEventListener('focus', function () {
    if (naKoniec) { ustawNaKoncu(); naKoniec = false; }
  });
  if (pole.value !== '') {
    if (document.activeElement !== pole) { ustawNaKoncu(); }
    naKoniec = true;
  }
  function zastosuj(stan, zmianaProjektu) {
    if (zmianaProjektu) {
      if (znany !== null && pole.value === znany) { pole.value = ''; }
      if (pole.value === '' && stan.tekst !== '') {
        pole.value = stan.tekst;
        naKoniec = true;
      }
      znany = stan.tekst;
      wersja = stan.wersja;
      return;
    }
    if (znany === null) {
      znany = stan.tekst;
      wersja = stan.wersja;
      return;
    }
    if (stan.wersja === wersja) { return; }
    var nowy = stan.tekst.indexOf(znany) === 0 ? stan.tekst.slice(znany.length) : '';
    znany = stan.tekst;
    wersja = stan.wersja;
    if (nowy !== '') {
      dopisz(nowy);
      ogloszenie();
    }
  }
  function odswiez() {
    var nazwa = biezacyProjekt();
    if (nazwa === '') { projekt = ''; return; }
    var zmiana = nazwa !== projekt;
    projekt = nazwa;
    fetch('/projekt/' + encodeURIComponent(nazwa) + '/szkic', {
      headers: { 'Accept': 'application/json' }
    })
      .then(function (o) { return o.ok ? o.json() : null; })
      .then(function (stan) {
        if (!stan || nazwa !== biezacyProjekt()) { return; }
        zastosuj(stan, zmiana);
      })
      .catch(function () {});
  }
  odswiez();
  setInterval(odswiez, 3000);
})();
""".strip()


def _skrypt_szkicu(pole_id: str, region_id: str, *, lista_projektow: str = "") -> str:
    """Skrypt odpytujący serwer o szkic tekstu ze skrótu i dopisujący go do pola.

    Nie przenosi fokusu, nie przestawia kursora piszącego użytkownika i łączy
    kilka dopisań w jeden komunikat, nie częściej niż co cztery sekundy.
    """
    lista = f"document.getElementById('{lista_projektow}')" if lista_projektow else "null"
    return (
        _SKRYPT_SZKICU.replace("POLE_ID", pole_id)
        .replace("REGION_ID", region_id)
        .replace("LISTA_PROJEKTOW", lista)
    )


_SKRYPT_FOKUS_BLEDOW = """
(function () {
  var lista = document.getElementById('bledy-formularza');
  if (lista) { lista.focus(); }
})();
""".strip()

_SKRYPT_LICZNIKA = """
(function () {
  var pole = document.getElementById('instrukcja_systemowa');
  var licznik = document.getElementById('licznik-instrukcji');
  if (!pole || !licznik) { return; }
  var limit = parseInt(licznik.getAttribute('data-limit'), 10);
  var czasomierz = null;
  function aktualizuj() {
    var uzyte = pole.value.length;
    licznik.textContent =
      'Użyto ' + uzyte + ' z ' + limit + ' znaków, pozostało ' + (limit - uzyte) + '.';
  }
  pole.addEventListener('input', function () {
    if (czasomierz) { clearTimeout(czasomierz); }
    czasomierz = setTimeout(aktualizuj, 700);
  });
})();
""".strip()
