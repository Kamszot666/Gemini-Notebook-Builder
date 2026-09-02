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
from gnb.ui.csrf import NAZWA_POLA_FORMULARZA
from gnb.ui.html import escapuj
from gnb.ui.projekty import ProjektNaLiscie
from gnb.ui.zadania import InformacjaOZadaniu, StanZadania

SCIEZKA_POSTEPU = "/postep"


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


@dataclass(frozen=True, slots=True)
class PodsumowanieWyniku:
    """Liczby z zakończonego przetwarzania, pokazywane na stronie projektu."""

    liczba_przetworzonych: int
    liczba_pominietych: int
    liczba_bledow: int
    katalog_projektu: str
    wznowiono: bool


_STYLE = """
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 1.5rem;
  background: #10131a; color: #f2f4f8;
  font: 1.125rem/1.6 system-ui, "Segoe UI", sans-serif;
}
main { max-width: 52rem; margin: 0 auto; }
h1, h2 { line-height: 1.25; }
a { color: #9ecbff; }
a:focus-visible, button:focus-visible, input:focus-visible,
textarea:focus-visible, [tabindex]:focus-visible {
  outline: 3px solid #ffd54a; outline-offset: 2px;
}
label { display: block; font-weight: 600; margin-top: 1.25rem; }
input[type="text"], textarea {
  width: 100%; margin-top: 0.35rem; padding: 0.6rem;
  background: #1b2130; color: #f2f4f8;
  border: 1px solid #4a5878; border-radius: 4px;
  font: inherit;
}
textarea { min-height: 8rem; }
button {
  margin-top: 1.25rem; padding: 0.6rem 1.2rem;
  background: #2b6cb0; color: #fff;
  border: 1px solid #9ecbff; border-radius: 4px;
  font: inherit; cursor: pointer;
}
button:hover { background: #3182ce; }
.blok { margin: 2rem 0; padding: 1.25rem; border: 1px solid #2c3752; border-radius: 6px; }
.bledy { border-color: #f2a0a0; }
.bledy ul { margin: 0.5rem 0 0; }
[role="status"] { margin-top: 0.5rem; font-weight: 600; }
pre {
  white-space: pre-wrap; word-wrap: break-word;
  background: #1b2130; padding: 1rem; border-radius: 4px;
  font: 1rem/1.5 ui-monospace, "Consolas", monospace;
}
.pomoc { color: #c4cbe0; font-weight: 400; font-size: 0.95rem; }
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
""".strip()


def _dokument(tytul: str, tresc: str, *, skrypt: str = "") -> str:
    """Składa pełny dokument HTML wokół treści strony."""
    fragment_skryptu = f"\n<script>\n{skrypt}\n</script>" if skrypt else ""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="pl">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{escapuj(tytul)}</title>\n"
        f"<style>\n{_STYLE}\n</style>\n"
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


def strona_glowna(
    *,
    projekty: list[ProjektNaLiscie],
    token_csrf: str,
    dane: DaneFormularzaProjektu | None = None,
    bledy: list[BladPola] | None = None,
) -> str:
    """Strona główna: formularz nowego projektu oraz wykaz niedokończonych projektów."""
    dane = dane or DaneFormularzaProjektu()
    bledy = bledy or []

    atrybuty_nazwa, blad_nazwa = _opis_bledu_pola(bledy, "nazwa_projektu")
    atrybuty_tekst, blad_tekst = _opis_bledu_pola(bledy, "tekst")
    atrybuty_adresy, blad_adresy = _opis_bledu_pola(bledy, "adresy")

    formularz = f"""<h1>Gemini Notebook Builder</h1>
<form class="blok" method="post" action="/projekt/nowy" enctype="multipart/form-data">
{_pole_csrf(token_csrf)}
{_lista_bledow(bledy)}
<h2>Nowy projekt</h2>
<label for="nazwa_projektu">Nazwa projektu (wymagana)</label>
<input type="text" id="nazwa_projektu" name="nazwa_projektu"
  value="{escapuj(dane.nazwa_projektu)}" required{atrybuty_nazwa}>
{blad_nazwa}
<label for="tekst">Tekst wklejony</label>
<textarea id="tekst" name="tekst"{atrybuty_tekst}>{escapuj(dane.tekst)}</textarea>
{blad_tekst}
<label for="adresy">Adresy stron i filmów, po jednym w wierszu</label>
<textarea id="adresy" name="adresy"{atrybuty_adresy}>{escapuj(dane.adresy)}</textarea>
{blad_adresy}
<label for="pliki">Pliki z dysku</label>
<input type="file" id="pliki" name="pliki" multiple>
<label for="grupa">Nazwa grupy tematycznej (opcjonalna)</label>
<input type="text" id="grupa" name="grupa" value="{escapuj(dane.grupa)}">
<p class="pomoc">Źródła z tą samą nazwą grupy są łączone w jak najmniej plików wynikowych.</p>
<button type="submit">Utwórz projekt i rozpocznij przetwarzanie</button>
</form>"""

    tresc = formularz + _sekcja_niedokonczone(projekty, token_csrf)
    return _dokument("Gemini Notebook Builder", tresc, skrypt=_SKRYPT_FOKUS_BLEDOW if bledy else "")


def _sekcja_niedokonczone(projekty: list[ProjektNaLiscie], token_csrf: str) -> str:
    """Wykaz projektów do wznowienia. Każdy z przyciskiem wznowienia."""
    if not projekty:
        return (
            '<div class="blok">\n<h2>Projekty do wznowienia</h2>\n'
            "<p>Nie ma niedokończonych projektów.</p>\n</div>"
        )
    pozycje = []
    for projekt in projekty:
        sciezka = sciezka_projektu(projekt.nazwa)
        opis_bledu = (
            f'<p class="pomoc">Uwaga: {escapuj(projekt.komunikat_bledu)}</p>'
            if projekt.komunikat_bledu
            else ""
        )
        pozycje.append(
            "<li>\n"
            f'<a href="{escapuj(sciezka)}">{escapuj(projekt.nazwa)}</a> '
            f"— źródeł w checkpoincie: {projekt.liczba_zrodel}, "
            f"ostatnia zmiana: {escapuj(projekt.czas_ostatniej_zmiany or 'nieznana')}.\n"
            f"{opis_bledu}\n"
            f'<form method="post" action="{escapuj(sciezka)}/wznow">\n'
            f"{_pole_csrf(token_csrf)}\n"
            '<button type="submit">Wznów ten projekt</button>\n'
            "</form>\n"
            "</li>"
        )
    return (
        '<div class="blok">\n<h2>Projekty do wznowienia</h2>\n'
        f"<ul>\n{''.join(pozycje)}\n</ul>\n</div>"
    )


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
) -> str:
    """Strona projektu: region postępu, dwa pola tekstowe oraz raport po zakończeniu."""
    bledy = bledy or []
    sciezka = sciezka_projektu(nazwa)
    czesci = [f"<h1>Projekt: {escapuj(nazwa)}</h1>", _sekcja_postepu(sciezka, informacja)]

    if podsumowanie is not None:
        czesci.append(_sekcja_podsumowania(podsumowanie))
    if raport is not None:
        czesci.append(
            f'<div class="blok">\n<h2>Raport końcowy</h2>\n<pre>{escapuj(raport)}</pre>\n</div>'
        )

    czesci.append(_sekcja_pol(sciezka, pola, limit_znakow_instrukcji, token_csrf, bledy))
    czesci.append(f'<p><a href="{escapuj(sciezka)}">Odśwież stan</a></p>')
    czesci.append('<p><a href="/">Wróć do strony głównej</a></p>')

    trwa = informacja is not None and informacja.stan is StanZadania.TRWA
    fragmenty_skryptu = [_SKRYPT_LICZNIKA]
    if trwa:
        fragmenty_skryptu.append(
            _SKRYPT_POSTEPU.replace("SCIEZKA_POSTEPU", escapuj(SCIEZKA_POSTEPU))
        )
    if bledy:
        fragmenty_skryptu.append(_SKRYPT_FOKUS_BLEDOW)
    return _dokument(f"Projekt: {nazwa}", "\n".join(czesci), skrypt="\n".join(fragmenty_skryptu))


def _sekcja_postepu(sciezka: str, informacja: InformacjaOZadaniu | None) -> str:
    if informacja is None:
        return (
            '<div class="blok">\n<h2>Stan</h2>\n'
            "<p>Ten projekt nie ma bieżącego przetwarzania w tej sesji serwera. "
            'Możesz je <a href="/">rozpocząć od nowa albo wznowić ze strony głównej</a>.</p>\n'
            "</div>"
        )
    stan_slowny = {
        StanZadania.TRWA: "trwa",
        StanZadania.ZAKONCZONE: "zakończone",
        StanZadania.BLAD: "zakończone błędem",
    }[informacja.stan]
    tresc = escapuj(informacja.komunikat_postepu or "Przygotowanie do pracy.")
    blad = (
        f'<p class="pomoc">Powód błędu: {escapuj(informacja.komunikat_bledu)}</p>'
        if informacja.komunikat_bledu
        else ""
    )
    koniec = "nie" if informacja.stan is StanZadania.TRWA else "tak"
    akapit_postepu = (
        f'<p id="postep-tresc" role="status" aria-live="polite" data-koniec="{koniec}">{tresc}</p>'
    )
    return (
        f'<div class="blok">\n<h2>Stan przetwarzania: {stan_slowny}</h2>\n'
        f"{akapit_postepu}\n"
        f"{blad}\n</div>"
    )


def _sekcja_podsumowania(podsumowanie: PodsumowanieWyniku) -> str:
    wznowienie = "tak" if podsumowanie.wznowiono else "nie"
    return (
        '<div class="blok">\n<h2>Podsumowanie</h2>\n<ul>\n'
        f"<li>Źródła przetworzone: {podsumowanie.liczba_przetworzonych}</li>\n"
        f"<li>Źródła pominięte: {podsumowanie.liczba_pominietych}</li>\n"
        f"<li>Źródła z błędem: {podsumowanie.liczba_bledow}</li>\n"
        f"<li>Wznowiono istniejący projekt: {wznowienie}</li>\n"
        f"<li>Katalog projektu: {escapuj(podsumowanie.katalog_projektu)}</li>\n"
        "</ul>\n</div>"
    )


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
        '<textarea id="instrukcja_systemowa" name="instrukcja_systemowa" '
        f'data-limit="{limit_znakow_instrukcji}"{atrybuty_instrukcja}>'
        f"{escapuj(pola.instrukcja_systemowa)}</textarea>"
    )
    textarea_prompt = (
        '<textarea id="prompt_wyszukiwania" name="prompt_wyszukiwania">'
        f"{escapuj(pola.prompt_wyszukiwania)}</textarea>"
    )
    pomoc_prompt = (
        '<p class="pomoc">Aplikacja nigdy nie uruchamia tego promptu sama. '
        "Zapisuje go tylko z projektem.</p>"
    )
    return f"""<form class="blok" method="post" action="{escapuj(sciezka)}/pola">
{_pole_csrf(token_csrf)}
<h2>Pola notatnika</h2>
<label for="instrukcja_systemowa">Instrukcja systemowa notatnika</label>
{textarea_instrukcja}
<p id="licznik-instrukcji" role="status" aria-live="polite"
  data-limit="{limit_znakow_instrukcji}">{escapuj(licznik)}</p>
{blad_instrukcja}
<label for="prompt_wyszukiwania">Prompt dla mechanizmu wyszukującego źródła</label>
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
<p>{escapuj(komunikat)}</p>
</div>
<p><a href="/">Wróć do strony głównej</a></p>""",
    )


_SKRYPT_POSTEPU = """
(function () {
  var region = document.getElementById('postep-tresc');
  if (!region || region.getAttribute('data-koniec') === 'tak') { return; }
  function odswiez() {
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
          region.textContent =
            'Przetwarzanie zakończone. Aktywuj odnośnik „Odśwież stan”, aby zobaczyć raport.';
        }
      })
      .catch(function () {});
  }
  setInterval(odswiez, 4000);
})();
""".strip()

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
