"""Ocena jakości ekstrakcji, wykonywana po ekstrakcji, a przed zapisem.

Źródło, z którego wyciągnięto trzysta znaków zamiast dwunastu tysięcy, wygląda
w wynikach dokładnie tak samo jak poprawne: ma plik, ma wpis w manifeście, ma
sumę kontrolną. To jest cicha utrata treści, czyli naruszenie drugiego priorytetu
z sekcji czwartej CLAUDE.md. Ten moduł istnieje po to, żeby takie przypadki dało
się zauważyć bez otwierania każdego pliku.

Ocena jest jedną z dwóch: ekstrakcja poprawna albo ekstrakcja podejrzana. Nie ma
trzeciej, pośredniej, ponieważ ocena ma prowadzić do prostej decyzji: sprawdzić
albo nie sprawdzać. Każda ocena podejrzana niesie listę powodów, żeby użytkownik
wiedział, czego szukać.

Źródło z oceną podejrzaną jest zapisywane normalnie i nigdy nie jest kasowane.
Trafia dodatkowo do osobnej sekcji raportu końcowego.

Heurystyki są celowo ostrożne. Fałszywe podejrzenie kosztuje jedno zajrzenie do
pliku, a przeoczona utrata treści kosztuje wiarygodność całej bazy wiedzy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gnb.core.liczenie_slow import policz_slowa

OCENA_POPRAWNA = "poprawna"
OCENA_PODEJRZANA = "podejrzana"

# Progi heurystyk. Wartości są zachowawcze: mają wyłapywać wyniki oczywiście
# ułomne, a nie oceniać, czy artykuł jest dobrze napisany.
MINIMALNA_LICZBA_SLOW = 50
MINIMALNA_LICZBA_AKAPITOW = 2
MINIMALNA_LICZBA_POWTORZEN = 3
MINIMALNA_LICZBA_NAGLOWKOW_DO_POROWNANIA = 2
MINIMALNA_LICZBA_PUSTYCH_SEKCJI = 2
KROTNOSC_TRESCI_POROWNAWCZEJ = 2.0

# Zwroty typowe dla stron błędu oraz dla stron żądających włączenia skryptów.
ZWROTY_PODEJRZANE = (
    "włącz javascript",
    "wlacz javascript",
    "enable javascript",
    "javascript is required",
    "please enable",
    "strona nie została znaleziona",
    "nie znaleziono strony",
    "page not found",
    "404 not found",
    "access denied",
    "odmowa dostępu",
    "dostęp zabroniony",
)

POWOD_ZA_MALO_SLOW = "treść ma mniej niż {prog} słów, dokładnie {liczba}"
POWOD_BRAK_TYTULU = "źródło nie ma tytułu"
POWOD_BRAK_AKAPITOW = "treść nie ma podziału na akapity"
POWOD_ZWROT_PODEJRZANY = (
    "treść zawiera zwrot typowy dla strony błędu albo żądania skryptów: {zwrot}"
)
POWOD_POWTORZENIA = "ten sam fragment powtarza się {liczba} razy"
POWOD_PRZEWAGA_NAGLOWKOW = "w treści jest więcej nagłówków ({naglowki}) niż akapitów ({akapity})"
POWOD_PUSTE_SEKCJE = "nagłówki bez treści pod spodem, liczba: {liczba}"
POWOD_NAWIGACJA = "w oryginale jest więcej odnośników ({odnosniki}) niż słów w treści ({slowa})"
POWOD_TRESC_POROWNAWCZA = (
    "dane strukturalne strony zawierają znacznie więcej treści niż wynik ekstrakcji: "
    "{porownawcza} słów wobec {wyekstrahowane}"
)

_ZNACZNIK_ODNOSNIKA = "<a "
_ZNACZNIK_NAGLOWKA = "#"


@dataclass(frozen=True, slots=True)
class OcenaJakosci:
    """Wynik oceny jakości ekstrakcji jednego źródła."""

    ocena: str
    powody: tuple[str, ...] = ()

    @property
    def czy_podejrzana(self) -> bool:
        """Prawda, gdy wynik ekstrakcji wymaga sprawdzenia przez człowieka."""
        return self.ocena == OCENA_PODEJRZANA


def ocen_jakosc(
    tekst: str,
    *,
    tytul: str | None = None,
    tekst_zrodla: str | None = None,
    tresc_porownawcza: str | None = None,
) -> OcenaJakosci:
    """Ocenia wynik ekstrakcji zestawem heurystyk i zwraca ocenę wraz z powodami.

    Argument `tekst_zrodla` to oryginalna postać źródła, na przykład kod strony.
    Argument `tresc_porownawcza` to treść z danych strukturalnych, używana
    wyłącznie do porównania objętości, nigdy jako źródło treści.
    """
    powody: list[str] = []
    liczba_slow = policz_slowa(tekst)

    if liczba_slow < MINIMALNA_LICZBA_SLOW:
        powody.append(POWOD_ZA_MALO_SLOW.format(prog=MINIMALNA_LICZBA_SLOW, liczba=liczba_slow))
    if not tytul or not tytul.strip():
        powody.append(POWOD_BRAK_TYTULU)

    akapity = _akapity(tekst)
    if len(akapity) < MINIMALNA_LICZBA_AKAPITOW:
        powody.append(POWOD_BRAK_AKAPITOW)

    zwrot = _znajdz_zwrot_podejrzany(tekst)
    if zwrot is not None:
        powody.append(POWOD_ZWROT_PODEJRZANY.format(zwrot=zwrot))

    liczba_powtorzen = _najczestsze_powtorzenie(akapity)
    if liczba_powtorzen >= MINIMALNA_LICZBA_POWTORZEN:
        powody.append(POWOD_POWTORZENIA.format(liczba=liczba_powtorzen))

    liczba_naglowkow, liczba_pustych_sekcji = _struktura_naglowkow(tekst)
    liczba_akapitow_tresci = len(akapity) - liczba_naglowkow
    if (
        liczba_naglowkow >= MINIMALNA_LICZBA_NAGLOWKOW_DO_POROWNANIA
        and liczba_naglowkow > liczba_akapitow_tresci
    ):
        powody.append(
            POWOD_PRZEWAGA_NAGLOWKOW.format(
                naglowki=liczba_naglowkow, akapity=max(liczba_akapitow_tresci, 0)
            )
        )
    if liczba_pustych_sekcji >= MINIMALNA_LICZBA_PUSTYCH_SEKCJI:
        powody.append(POWOD_PUSTE_SEKCJE.format(liczba=liczba_pustych_sekcji))

    if tekst_zrodla:
        odnosniki = tekst_zrodla.lower().count(_ZNACZNIK_ODNOSNIKA)
        if odnosniki > liczba_slow:
            powody.append(POWOD_NAWIGACJA.format(odnosniki=odnosniki, slowa=liczba_slow))

    if tresc_porownawcza:
        slowa_porownawcze = policz_slowa(tresc_porownawcza)
        if slowa_porownawcze > liczba_slow * KROTNOSC_TRESCI_POROWNAWCZEJ:
            powody.append(
                POWOD_TRESC_POROWNAWCZA.format(
                    porownawcza=slowa_porownawcze, wyekstrahowane=liczba_slow
                )
            )

    if not powody:
        return OcenaJakosci(ocena=OCENA_POPRAWNA)
    return OcenaJakosci(ocena=OCENA_PODEJRZANA, powody=tuple(powody))


def _akapity(tekst: str) -> list[str]:
    """Dzieli tekst na akapity, pomijając puste."""
    return [akapit.strip() for akapit in tekst.split("\n\n") if akapit.strip()]


def _struktura_naglowkow(tekst: str) -> tuple[int, int]:
    """Zwraca liczbę nagłówków oraz liczbę nagłówków bez treści pod spodem.

    Nagłówek rozpoznawany jest po zapisie Markdown, bo w tej postaci ekstraktory
    zwracają rozpoznaną strukturę dokumentu. Tekst bez nagłówków, na przykład
    transkrypcja filmu, daje dwa zera i nie podlega tym dwóm heurystykom.

    Nagłówek pusty to nagłówek, po którym do następnego nagłówka albo do końca
    dokumentu nie ma żadnej treści. Sam szkielet nagłówków bez treści świadczy
    o tym, że ekstrakcja wzięła spis rozdziałów zamiast artykułu.
    """
    wiersze = [wiersz.strip() for wiersz in tekst.splitlines()]
    liczba_naglowkow = 0
    liczba_pustych = 0
    otwarty_naglowek = False
    for wiersz in wiersze:
        if wiersz.startswith(_ZNACZNIK_NAGLOWKA):
            if otwarty_naglowek:
                liczba_pustych += 1
            liczba_naglowkow += 1
            otwarty_naglowek = True
        elif wiersz:
            otwarty_naglowek = False
    if otwarty_naglowek:
        liczba_pustych += 1
    return liczba_naglowkow, liczba_pustych


def _znajdz_zwrot_podejrzany(tekst: str) -> str | None:
    """Zwraca pierwszy znaleziony zwrot typowy dla strony błędu albo żądania skryptów."""
    maly = tekst.lower()
    for zwrot in ZWROTY_PODEJRZANE:
        if zwrot in maly:
            return zwrot
    return None


def _najczestsze_powtorzenie(akapity: Sequence[str]) -> int:
    """Zwraca liczbę wystąpień najczęściej powtórzonego akapitu.

    Powtórzony akapit świadczy zwykle o tym, że do wyniku trafił element
    powtarzalny strony, na przykład zajawka wyświetlana przy każdym artykule.
    """
    if not akapity:
        return 0
    liczniki: dict[str, int] = {}
    for akapit in akapity:
        liczniki[akapit] = liczniki.get(akapit, 0) + 1
    return max(liczniki.values())
