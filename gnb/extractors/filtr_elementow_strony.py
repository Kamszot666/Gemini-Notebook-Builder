"""Deterministyczny filtr elementów strony, które nie są treścią artykułu.

Trafilatura w trybie domyślnym zachowuje całą treść artykułu z dużych portali,
ale razem z nią także elementy strony: wiersze „REKLAMA”, przyciski udostępniania,
podpisy zdjęć, blok newslettera, notkę o autorze, licznik komentarzy i bloki
polecanych artykułów. Ten moduł usuwa je z drzewa XML zwróconego przez
trafilaturę, zanim z drzewa powstaną bloki treści i wykaz odnośników. Dzięki temu
adresy z usuniętych bloków nie trafiają do wykazu odnośników.

Filtr jest deterministyczny i oparty na jawnej liście zwrotów i wzorców, którą
łatwo rozszerzyć: wszystkie są zebrane na początku pliku. Nie używa żadnego
modelu ani zewnętrznej usługi.

Filtr nigdy nie usuwa niczego po cichu. Każdy usunięty fragment trafia do wyniku
razem z powodem, a wywołujący zapisuje go w wynikach pośrednich. Gdy filtr
usunąłby więcej niż ``LIMIT_ODSETKA_USUNIETEJ_TRESCI`` słów dokumentu, nie usuwa
nic i zgłasza ostrzeżenie, bo tak duży odsetek oznacza błąd filtra, a nie
reklamy. Utrata treści jest gorsza niż drobny szum (sekcja czwarta CLAUDE.md).

Po usunięciu bloku, który przerywał zdanie, sąsiednie akapity są łączone, ale
tylko wtedy, gdy pierwszy nie kończy się znakiem końca zdania, a drugi zaczyna
się od małej litery.

Moduł nie pobiera niczego z sieci i nie wykonuje niczego z treści strony: tekst
bloków jest wyłącznie porównywany ze wzorcami.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from gnb.core.liczenie_slow import policz_slowa

LIMIT_ODSETKA_USUNIETEJ_TRESCI = 0.35
PROG_GESTOSCI_ODNOSNIKOW = 0.9
MINIMALNA_DLUGOSC_SERII_ODNOSNIKOW = 3
MAKSYMALNA_DLUGOSC_TYTULU_PO_WIDEO = 140
MAKSYMALNA_DLUGOSC_ELEMENTU_SERII = 160
MAKSYMALNA_DLUGOSC_PODPISU_ZDJECIA = 130
MAKSYMALNA_LICZBA_BLOKOW_NEWSLETTERA = 5
MAKSYMALNA_DLUGOSC_NAGLOWKA_NEWSLETTERA = 25
MAKSYMALNA_DLUGOSC_NOTKI_O_AUTORZE = 100
MAKSYMALNA_DLUGOSC_RESZTY_PO_NAZWISKU = 60
MAKSYMALNA_DLUGOSC_BLOKU_ELEMENTU_STRONY = 180

# Elementy drzewa trafilatury, które filtr bada jako bloki. Listy, tabele,
# cytaty i kod nie są sprawdzane: są treścią, a nie elementami strony.
_ZNACZNIKI_BADANYCH_BLOKOW = frozenset({"p", "head"})

# Tekst bloku (bez wielkości liter) i powód usunięcia. Dokładne dopasowanie.
ZWROTY_DOKLADNE: dict[str, str] = {
    "reklama": "reklama",
    "zespół redakcyjny": "podpis redakcji",
    "zapisz mnie": "przycisk newslettera",
    "zapisz się": "przycisk newslettera",
}

# Zwroty otwierające blok polecanych artykułów. Usuwane razem z kolejnymi
# blokami złożonymi głównie z odnośników. Porównanie po usunięciu końcowego
# dwukropka.
ZNACZNIKI_POLECANYCH_ARTYKULOW: frozenset[str] = frozenset(
    {
        "czytaj także",
        "czytaj również",
        "zobacz także",
        "zobacz również",
        "przeczytaj także",
        "przeczytaj też",
        "polecane",
        "polecamy",
    }
)

# Zwroty otwierające blok newslettera i zwroty go zamykające.
POCZATKI_NEWSLETTERA: tuple[str, ...] = ("newsletter",)
ZAMKNIECIA_NEWSLETTERA: frozenset[str] = frozenset(
    {"zapisz mnie", "zapisz się", "subskrybuj", "zapisz sie"}
)

# Słowa otwierające biogram autora. Biogram jest usuwany tylko wtedy, gdy stoi
# bezpośrednio po usuniętej notce o autorze.
_ROLE_AUTORA = "Dziennikarz|Dziennikarka|Redaktor|Redaktorka|Autor|Autorka|Reporter|Reporterka"

# Agencje i serwisy fotograficzne występujące w podpisach zdjęć.
_AGENCJE = (
    "Getty Images|East News|PAP|Forum|Reuters|AP Photo|AFP|NurPhoto|Shutterstock|"
    "Newspix|Agencja Gazeta|Fotonews"
)

# Wzorce dla całego tekstu bloku i powód usunięcia. Kolejność ma znaczenie tylko
# dla powodu zapisanego przy fragmencie.
WZORCE_BLOKOW: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"^(?:\s*(?:Udostępnij(?: na [^\W\d_]+?)?|Kopiuj link|Skopiuj link))+\s*$",
            re.IGNORECASE,
        ),
        "przyciski udostępniania",
    ),
    (
        re.compile(
            r"^Źródło (?:zdjęć|zdjęcia|wideo|grafiki|artykułu|filmu|ilustracji)\s*:.{0,80}$",
            re.IGNORECASE,
        ),
        "źródło zdjęcia, wideo albo artykułu",
    ),
    (
        re.compile(r"^\d[\d\s]*\s+komentarz(?:y|e|a|i)?$|^komentarze(?: \(\d+\))?$", re.IGNORECASE),
        "licznik komentarzy",
    ),
    (
        re.compile(rf"^(?:{_ROLE_AUTORA})(?: [\w.\-]+){{0,3}}$", re.IGNORECASE),
        "notka o autorze",
    ),
    (
        re.compile(
            rf"^[^\W\d_]+(?: [^\W\d_\-]+(?:-[^\W\d_]+)?){{0,2}} ?"
            rf"(?:{_ROLE_AUTORA})(?: [\w.\-]+){{0,3}}$"
        ),
        "notka o autorze",
    ),
)

_PODPIS_ZDJECIA = re.compile(
    rf"(?:/|\bvia\b)\s*(?:[^/]{{0,40}}\s)?(?:{_AGENCJE})\b[^.]{{0,30}}$",
    re.IGNORECASE,
)
_BIOGRAM_AUTORA = re.compile(rf"^(?:{_ROLE_AUTORA})\b", re.IGNORECASE)
_KONIEC_ZDANIA = (".", "!", "?", "…", ":", ";", '"', "”", "»", ")", "]")

POWOD_NOTKA_O_AUTORZE = "notka o autorze"
POWOD_BIOGRAM_AUTORA = "biogram autora"
POWOD_WIDEO = "znacznik wideo"
POWOD_TYTUL_WIDEO = "tytuł polecanego wideo"
POWOD_PODPIS_ZDJECIA = "podpis zdjęcia"
POWOD_NEWSLETTER = "blok newslettera"
POWOD_POLECANE = "blok polecanych artykułów"
POWOD_SERIA_ODNOSNIKOW = "seria odnośników"


@dataclass(frozen=True, slots=True)
class UsunietyFragment:
    """Jeden fragment strony usunięty przez filtr, z powodem usunięcia."""

    powod: str
    tekst: str


@dataclass(slots=True)
class WynikFiltra:
    """Wynik filtrowania: co usunięto, co złączono i czy zadziałał bezpiecznik.

    Gdy zadziałał bezpiecznik, lista ``usuniete`` jest pusta, a to, co filtr chciał
    usunąć, jest w ``zaproponowane``, żeby dało się ocenić, dlaczego filtr
    się pomylił.
    """

    usuniete: list[UsunietyFragment] = field(default_factory=list)
    zlaczenia: list[str] = field(default_factory=list)
    zaproponowane: list[UsunietyFragment] = field(default_factory=list)
    ostrzezenie: str | None = None

    def zawiera_cos_do_zapisu(self) -> bool:
        """Mówi, czy jest cokolwiek, co trzeba pokazać w wynikach pośrednich."""
        return bool(self.usuniete or self.zlaczenia or self.zaproponowane or self.ostrzezenie)

    def jako_tekst(self, identyfikator_zrodla: str) -> str:
        """Buduje czytelny liniowo zapis do pliku w wynikach pośrednich."""
        wiersze = [
            f"Fragmenty usunięte przez filtr elementów strony, źródło {identyfikator_zrodla}.",
            f"Liczba usuniętych fragmentów: {len(self.usuniete)}.",
        ]
        if self.ostrzezenie:
            wiersze.append(f"Ostrzeżenie: {self.ostrzezenie}")
        wiersze.append("")
        for numer, fragment in enumerate(self.usuniete, start=1):
            wiersze.append(f"{numer}. Powód: {fragment.powod}. Tekst: {fragment.tekst}")
        if self.zaproponowane:
            wiersze.append("Fragmenty, które filtr chciał usunąć, ale nie usunął (bezpiecznik):")
            for numer, fragment in enumerate(self.zaproponowane, start=1):
                wiersze.append(f"{numer}. Powód: {fragment.powod}. Tekst: {fragment.tekst}")
        if self.zlaczenia:
            wiersze.append("")
            wiersze.append("Akapity złączone po usunięciu bloku, który przerywał zdanie:")
            wiersze.extend(f"- {opis}" for opis in self.zlaczenia)
        return "\n".join(wiersze) + "\n"


def przefiltruj_drzewo(drzewo: etree._Element) -> WynikFiltra:
    """Usuwa z elementu ``main`` drzewa trafilatury bloki będące elementami strony.

    Zmienia drzewo w miejscu, o ile bezpiecznik nie zadziałał. Zwraca opis tego,
    co usunięto. Drzewo bez elementu ``main`` albo bez bloków zostaje nietknięte.
    """
    glowny = drzewo.find("main")
    if glowny is None or len(glowny) == 0:
        return WynikFiltra()

    dzieci = list(glowny)
    decyzje = _wyznacz_bloki_do_usuniecia(dzieci, _autorzy_z_metadanych(drzewo))
    if not decyzje:
        return WynikFiltra()

    usuniete = [UsunietyFragment(powod, _tekst(dzieci[indeks])) for indeks, powod in decyzje]
    slowa_usuniete = sum(policz_slowa(fragment.tekst) for fragment in usuniete)
    slowa_razem = sum(policz_slowa(_tekst(blok)) for blok in dzieci)
    if slowa_razem and slowa_usuniete / slowa_razem > LIMIT_ODSETKA_USUNIETEJ_TRESCI:
        procent = round(100 * slowa_usuniete / slowa_razem)
        return WynikFiltra(
            zaproponowane=usuniete,
            ostrzezenie=(
                f"Filtr elementów strony usunąłby {procent} procent treści "
                f"({slowa_usuniete} z {slowa_razem} słów), więc treść zostawiono bez "
                "filtrowania. To prawdopodobnie błąd filtra, a nie reklamy: sprawdź "
                "stronę i listę fragmentów w wynikach pośrednich."
            ),
        )

    indeksy_usuniete = {indeks for indeks, _ in decyzje}
    zlaczenia = _usun_i_zlacz(glowny, dzieci, indeksy_usuniete)
    return WynikFiltra(usuniete=usuniete, zlaczenia=zlaczenia)


def _wyznacz_bloki_do_usuniecia(
    dzieci: list[etree._Element], autorzy: list[str]
) -> list[tuple[int, str]]:
    """Zwraca pary (indeks bloku, powód) dla bloków do usunięcia, w kolejności dokumentu."""
    powody: dict[int, str] = {}
    teksty = [_tekst(blok) for blok in dzieci]

    for indeks, blok in enumerate(dzieci):
        if indeks in powody or blok.tag not in _ZNACZNIKI_BADANYCH_BLOKOW:
            continue
        powod = _powod_bloku_pojedynczego(teksty[indeks], autorzy)
        if powod:
            powody[indeks] = powod

    _dodaj_wideo(dzieci, teksty, powody)
    _dodaj_newslettery(dzieci, teksty, powody)
    _dodaj_biogramy_autorow(dzieci, teksty, powody)
    _dodaj_polecane(dzieci, teksty, powody)
    _dodaj_serie_odnosnikow(dzieci, teksty, powody)
    return sorted(powody.items())


def _powod_bloku_pojedynczego(tekst: str, autorzy: list[str]) -> str | None:
    """Rozstrzyga o jednym bloku na podstawie jego samego tekstu."""
    if not tekst:
        return None
    klucz = tekst.casefold()
    if klucz in ZWROTY_DOKLADNE:
        return ZWROTY_DOKLADNE[klucz]
    for wzorzec, powod in WZORCE_BLOKOW:
        if len(tekst) > MAKSYMALNA_DLUGOSC_BLOKU_ELEMENTU_STRONY or not wzorzec.search(tekst):
            continue
        # Krótkie zdanie kończące się kropką, na przykład „Autor zaprzecza.”,
        # jest treścią, a nie podpisem.
        if powod == POWOD_NOTKA_O_AUTORZE and tekst.endswith((".", "!", "?")):
            continue
        return powod
    if _jest_notka_z_nazwiskiem(tekst, autorzy):
        return POWOD_NOTKA_O_AUTORZE
    if _jest_podpisem_zdjecia(tekst):
        return POWOD_PODPIS_ZDJECIA
    return None


def _jest_notka_z_nazwiskiem(tekst: str, autorzy: list[str]) -> bool:
    """Mówi, czy blok to nazwisko autora z metadanych i krótka reszta, na przykład rola."""
    if len(tekst) > MAKSYMALNA_DLUGOSC_NOTKI_O_AUTORZE:
        return False
    male = tekst.casefold()
    for autor in autorzy:
        if male.startswith(autor.casefold()):
            reszta = tekst[len(autor) :].strip()
            # Rola autora („Dziennikarka”, „Content Creator”) nie ma interpunkcji
            # zdania; dwukropek albo przecinek wskazuje wypowiedź lub opis w tekście.
            if (
                len(reszta) <= MAKSYMALNA_DLUGOSC_RESZTY_PO_NAZWISKU
                and not reszta.endswith(".")
                and not any(znak in reszta for znak in ",:;")
            ):
                return True
    return False


def _jest_podpisem_zdjecia(tekst: str) -> bool:
    """Mówi, czy blok to krótki podpis zdjęcia z nazwą agencji, bez zdania."""
    if len(tekst) > MAKSYMALNA_DLUGOSC_PODPISU_ZDJECIA or tekst.endswith((".", "!", "?")):
        return False
    return _PODPIS_ZDJECIA.search(tekst) is not None


def _dodaj_wideo(dzieci: list[etree._Element], teksty: list[str], powody: dict[int, str]) -> None:
    """Oznacza wiersz „WIDEO” razem z następnym krótkim wierszem, który jest tytułem filmu."""
    for indeks, tekst in enumerate(teksty):
        if tekst.casefold() != "wideo" or dzieci[indeks].tag not in _ZNACZNIKI_BADANYCH_BLOKOW:
            continue
        powody.setdefault(indeks, POWOD_WIDEO)
        nastepny = indeks + 1
        if (
            nastepny < len(dzieci)
            and dzieci[nastepny].tag == "p"
            and 0 < len(teksty[nastepny]) <= MAKSYMALNA_DLUGOSC_TYTULU_PO_WIDEO
        ):
            powody.setdefault(nastepny, POWOD_TYTUL_WIDEO)


def _dodaj_newslettery(
    dzieci: list[etree._Element], teksty: list[str], powody: dict[int, str]
) -> None:
    """Oznacza blok newslettera od jego początku do przycisku zapisu, jeśli ten jest blisko."""
    for indeks, tekst in enumerate(teksty):
        if not tekst.casefold().startswith(POCZATKI_NEWSLETTERA):
            continue
        if dzieci[indeks].tag not in _ZNACZNIKI_BADANYCH_BLOKOW:
            continue
        koniec = indeks
        granica = min(len(teksty), indeks + MAKSYMALNA_LICZBA_BLOKOW_NEWSLETTERA + 1)
        for kolejny in range(indeks + 1, granica):
            if teksty[kolejny].casefold() in ZAMKNIECIA_NEWSLETTERA:
                koniec = kolejny
                break
        for numer in range(indeks, koniec + 1):
            powody.setdefault(numer, POWOD_NEWSLETTER)
        poprzedni = indeks - 1
        if (
            poprzedni >= 0
            and 0 < len(teksty[poprzedni]) <= MAKSYMALNA_DLUGOSC_NAGLOWKA_NEWSLETTERA
            and teksty[poprzedni].isupper()
        ):
            powody.setdefault(poprzedni, POWOD_NEWSLETTER)


def _dodaj_biogramy_autorow(
    dzieci: list[etree._Element], teksty: list[str], powody: dict[int, str]
) -> None:
    """Oznacza biogram autora stojący bezpośrednio po usuniętej notce o autorze."""
    for indeks in range(1, len(teksty)):
        if powody.get(indeks - 1) != POWOD_NOTKA_O_AUTORZE or indeks in powody:
            continue
        if dzieci[indeks].tag == "p" and _BIOGRAM_AUTORA.search(teksty[indeks]):
            powody[indeks] = POWOD_BIOGRAM_AUTORA


def _dodaj_polecane(
    dzieci: list[etree._Element], teksty: list[str], powody: dict[int, str]
) -> None:
    """Oznacza zwrot „Czytaj także” i kolejne bloki złożone głównie z odnośników."""
    for indeks, tekst in enumerate(teksty):
        if tekst.rstrip(":").strip().casefold() not in ZNACZNIKI_POLECANYCH_ARTYKULOW:
            continue
        if dzieci[indeks].tag not in _ZNACZNIKI_BADANYCH_BLOKOW:
            continue
        powody.setdefault(indeks, POWOD_POLECANE)
        kolejny = indeks + 1
        while kolejny < len(dzieci) and _jest_blokiem_odnosnikow(dzieci[kolejny], teksty[kolejny]):
            powody.setdefault(kolejny, POWOD_POLECANE)
            kolejny += 1


def _dodaj_serie_odnosnikow(
    dzieci: list[etree._Element], teksty: list[str], powody: dict[int, str]
) -> None:
    """Oznacza serie co najmniej trzech kolejnych bloków złożonych głównie z odnośników.

    Pojedynczy akapit będący w całości odnośnikiem bywa zwykłym zdaniem artykułu
    z odnośnikiem wokół całego zdania, dlatego krótsze serie zostają.
    """
    seria: list[int] = []
    for indeks in [*range(len(dzieci)), len(dzieci)]:
        if indeks < len(dzieci) and _jest_blokiem_odnosnikow(dzieci[indeks], teksty[indeks]):
            seria.append(indeks)
            continue
        if len(seria) >= MINIMALNA_DLUGOSC_SERII_ODNOSNIKOW:
            for numer in seria:
                powody.setdefault(numer, POWOD_SERIA_ODNOSNIKOW)
        seria = []


def _jest_blokiem_odnosnikow(blok: etree._Element, tekst: str) -> bool:
    """Mówi, czy blok jest krótkim akapitem lub nagłówkiem złożonym głównie z odnośników."""
    if blok.tag not in _ZNACZNIKI_BADANYCH_BLOKOW:
        return False
    if not tekst or len(tekst) > MAKSYMALNA_DLUGOSC_ELEMENTU_SERII:
        return False
    znaki_odnosnikow = sum(len(_zwin(_polaczony_tekst(ref))) for ref in blok.iter("ref"))
    return znaki_odnosnikow / len(tekst) >= PROG_GESTOSCI_ODNOSNIKOW


def _usun_i_zlacz(
    glowny: etree._Element, dzieci: list[etree._Element], usuniete: set[int]
) -> list[str]:
    """Usuwa bloki z drzewa i łączy akapity rozcięte usuniętym blokiem."""
    zlaczenia: list[str] = []
    zachowane: list[etree._Element] = []
    przerwa = False
    for indeks, blok in enumerate(dzieci):
        if indeks in usuniete:
            przerwa = bool(zachowane)
            glowny.remove(blok)
            continue
        if przerwa and zachowane and _akapit_rozciety(zachowane[-1], blok):
            zlaczenia.append(_opis_zlaczenia(zachowane[-1], blok))
            _dolacz_akapit(zachowane[-1], blok)
            glowny.remove(blok)
        else:
            zachowane.append(blok)
        przerwa = False
    return zlaczenia


def _akapit_rozciety(poprzedni: etree._Element, nastepny: etree._Element) -> bool:
    """Mówi, czy dwa akapity rozdzielone usuniętym blokiem tworzą jedno zdanie."""
    if poprzedni.tag != "p" or nastepny.tag != "p":
        return False
    tekst_poprzedni = _tekst(poprzedni)
    tekst_nastepny = _tekst(nastepny)
    if not tekst_poprzedni or not tekst_nastepny:
        return False
    return not tekst_poprzedni.endswith(_KONIEC_ZDANIA) and tekst_nastepny[0].islower()


def _dolacz_akapit(poprzedni: etree._Element, nastepny: etree._Element) -> None:
    """Dokleja zawartość następnego akapitu na koniec poprzedniego, zachowując odnośniki."""
    ciag = (nastepny.text or "").lstrip()
    if len(poprzedni):
        ostatni = poprzedni[-1]
        ostatni.tail = f"{ostatni.tail or ''} {ciag}"
    else:
        poprzedni.text = f"{poprzedni.text or ''} {ciag}"
    for dziecko in list(nastepny):
        poprzedni.append(dziecko)


def _opis_zlaczenia(poprzedni: etree._Element, nastepny: etree._Element) -> str:
    """Opisuje miejsce złączenia końcówką pierwszego i początkiem drugiego akapitu."""
    return f"…{_tekst(poprzedni)[-40:]} + {_tekst(nastepny)[:40]}…"


def _autorzy_z_metadanych(drzewo: etree._Element) -> list[str]:
    """Wydobywa nazwiska autorów z atrybutu ``author`` korzenia wyniku trafilatury."""
    surowy = str(drzewo.get("author") or "")
    nazwiska = [_zwin(czesc) for czesc in surowy.split(";")]
    return [nazwisko for nazwisko in nazwiska if len(nazwisko) >= 5 and " " in nazwisko]


def _polaczony_tekst(element: etree._Element) -> str:
    """Skleja cały tekst elementu bez dodawania spacji."""
    fragmenty = (
        fragment.decode("utf-8", "replace") if isinstance(fragment, bytes) else str(fragment)
        for fragment in element.itertext()
    )
    return "".join(fragmenty)


def _zwin(tekst: str) -> str:
    """Zamienia ciągi białych znaków na pojedynczą spację i obcina brzegi."""
    return " ".join(tekst.split())


def _tekst(element: etree._Element) -> str:
    """Zwraca tekst bloku ze zwiniętymi białymi znakami."""
    return _zwin(_polaczony_tekst(element))
