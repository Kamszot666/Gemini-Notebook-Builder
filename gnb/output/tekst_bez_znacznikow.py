"""Zamiana treści Markdown na czysty tekst z zachowaną strukturą.

Moduł powstał dla wersji TXT dokumentu, który w źródle jest Markdownem. Wersja
MD zachowuje pełny zapis Markdown, a wersja TXT ma być czytelna liniowo
czytnikiem ekranu i wolna od znaków składni. Usunięcie znaczników nie może
jednak oznaczać utraty treści ani struktury, dlatego zamiana jest przepisaniem
dokumentu, a nie wycięciem znaków.

Reguły przepisania:

1. Nagłówek staje się osobnym wierszem tekstu bez krat.
2. Element listy wypunktowanej staje się wierszem zaczynającym się myślnikiem
   i spacją. Element listy numerowanej zachowuje swój numer w postaci numeru,
   kropki i spacji, ponieważ numer niesie znaczenie: kolejność kroków oraz
   możliwość odwołania się w tekście do konkretnego punktu. Zagnieżdżenie jest
   oddawane wcięciem dwóch spacji na poziom.
3. Tabela jest rozpisywana wierszami w postaci nazwa kolumny, dwukropek,
   wartość, po jednym wierszu na komórkę i pustym wierszu między rekordami.
4. Blok kodu traci ogrodzenie, ale zachowuje wcięcia i łamanie wierszy.
5. Cytat blokowy staje się zwykłymi wierszami tekstu.
6. Znaczniki wewnątrzwierszowe, czyli gwiazdki, podkreślenia i pojedyncze
   grawisy, znikają, a zostaje sam tekst. Adres odnośnika jest dopisywany
   w nawiasie po jego treści, bo inaczej informacja o pochodzeniu przepadłaby.

Blok surowego HTML jest przepisywany dosłownie. Jest to świadomy wybór: taki
blok bywa jedynym nośnikiem treści, a milczące pominięcie go byłoby utratą
materiału, czyli złamaniem drugiego priorytetu z sekcji czwartej CLAUDE.md.

Moduł nie decyduje o tym, czy wersja TXT ma powstać. Robi to `gnb.potok`
na podstawie tego, czy użyty ekstraktor zwraca tekst ze znacznikami.
"""

from __future__ import annotations

from dataclasses import dataclass

from markdown_it.token import Token

from gnb.extractors.markdown import utworz_parser

PREFIKS_ELEMENTU_LISTY_WYPUNKTOWANEJ = "- "
WCIECIE_ZAGNIEZDZENIA = "  "
ROZDZIELACZ_KOMORKI_TABELI = ": "
_PIERWSZY_NUMER_DOMYSLNY = 1

# Parser jest ten sam co w ekstraktorze Markdown. Obie ścieżki muszą widzieć
# dokładnie tę samą strukturę, w tym tabele, które nie należą do CommonMark.
_PARSER = utworz_parser()

_TOKEN_OTWARCIA_LISTY_NUMEROWANEJ = "ordered_list_open"
_TOKENY_OTWARCIA_LISTY = ("bullet_list_open", _TOKEN_OTWARCIA_LISTY_NUMEROWANEJ)
_TOKENY_ZAMKNIECIA_LISTY = ("bullet_list_close", "ordered_list_close")
_TOKENY_ZAMKNIECIA_BLOKU = ("heading_close", "paragraph_close", "blockquote_close")
_TOKENY_KODU = ("fence", "code_block")


def zamien_markdown_na_tekst(tekst: str) -> str:
    """Zwraca czysty tekst odpowiadający podanemu dokumentowi Markdown."""
    return _Przepisywacz().przepisz(_PARSER.parse(tekst))


@dataclass(slots=True)
class _StanListy:
    """Stan jednej otwartej listy: rodzaj oraz numer kolejnego elementu."""

    numerowana: bool
    numer_nastepnego: int = _PIERWSZY_NUMER_DOMYSLNY

    def kolejny_prefiks(self) -> str:
        """Zwraca prefiks kolejnego elementu i przesuwa numerację o jeden."""
        if not self.numerowana:
            return PREFIKS_ELEMENTU_LISTY_WYPUNKTOWANEJ
        prefiks = f"{self.numer_nastepnego}. "
        self.numer_nastepnego += 1
        return prefiks


class _Przepisywacz:
    """Stan przepisywania jednego dokumentu z tokenów na wiersze tekstu."""

    def __init__(self) -> None:
        self._wiersze: list[str] = []
        self._stos_list: list[_StanListy] = []
        self._prefiks_elementu: str | None = None
        self._w_tabeli = False
        self._w_naglowku_tabeli = False
        self._naglowki_tabeli: list[str] = []
        self._komorki_wiersza: list[str] = []

    def przepisz(self, tokeny: list[Token]) -> str:
        """Przechodzi po tokenach dokumentu i składa z nich czysty tekst."""
        for token in tokeny:
            self._obsluz(token)
        return "\n".join(self._wiersze).strip("\n")

    def _obsluz(self, token: Token) -> None:
        typ = token.type

        if typ == "inline":
            self._obsluz_inline(token)
        elif typ in _TOKENY_OTWARCIA_LISTY:
            self._stos_list.append(_nowa_lista(token))
        elif typ in _TOKENY_ZAMKNIECIA_LISTY:
            if self._stos_list:
                self._stos_list.pop()
            if not self._stos_list:
                self._pusty_wiersz()
        elif typ == "list_item_open":
            self._prefiks_elementu = (
                self._stos_list[-1].kolejny_prefiks() if self._stos_list else None
            )
        elif typ in _TOKENY_KODU:
            self._obsluz_kod(token)
        elif typ == "html_block":
            self._obsluz_html(token)
        elif typ in _TOKENY_ZAMKNIECIA_BLOKU:
            if not self._stos_list:
                self._pusty_wiersz()
        elif typ == "table_open":
            self._w_tabeli = True
            self._naglowki_tabeli = []
        elif typ == "table_close":
            self._w_tabeli = False
            self._pusty_wiersz()
        elif typ == "thead_open":
            self._w_naglowku_tabeli = True
        elif typ == "thead_close":
            self._w_naglowku_tabeli = False
        elif typ == "tr_open":
            self._komorki_wiersza = []
        elif typ == "tr_close":
            self._zamknij_wiersz_tabeli()
        elif typ == "hr":
            self._pusty_wiersz()

    def _obsluz_inline(self, token: Token) -> None:
        """Kieruje treść tokenu wewnątrzwierszowego do tabeli, listy albo akapitu."""
        tresc = tekst_inline(token)
        if self._w_tabeli:
            self._komorki_wiersza.append(tresc)
            return
        if not tresc:
            return
        if self._stos_list:
            self._dopisz_element_listy(tresc)
            return
        self._wiersze.extend(tresc.split("\n"))

    def _dopisz_element_listy(self, tresc: str) -> None:
        """Dopisuje treść jako element listy, z wcięciem odpowiadającym zagnieżdżeniu.

        Pierwszy wiersz elementu dostaje prefiks wyznaczony przy otwarciu
        elementu: myślnik ze spacją w liście wypunktowanej albo numer, kropkę
        i spację w liście numerowanej. Kolejne wiersze tego samego elementu są
        wcięte, żeby nie wyglądały na nowy punkt.
        """
        wciecie = WCIECIE_ZAGNIEZDZENIA * (len(self._stos_list) - 1)
        prefiks = self._prefiks_elementu or WCIECIE_ZAGNIEZDZENIA
        linie = tresc.split("\n")
        self._wiersze.append(f"{wciecie}{prefiks}{linie[0]}")
        for dalsza_linia in linie[1:]:
            self._wiersze.append(f"{wciecie}{WCIECIE_ZAGNIEZDZENIA}{dalsza_linia}")
        self._prefiks_elementu = None

    def _obsluz_kod(self, token: Token) -> None:
        """Dopisuje zawartość bloku kodu bez ogrodzenia, zachowując wcięcia."""
        wciecie = WCIECIE_ZAGNIEZDZENIA * len(self._stos_list)
        self._pusty_wiersz()
        for wiersz in token.content.rstrip("\n").split("\n"):
            self._wiersze.append(f"{wciecie}{wiersz}" if wiersz else "")
        self._pusty_wiersz()

    def _obsluz_html(self, token: Token) -> None:
        """Dopisuje surowy blok HTML dosłownie, żeby nie zgubić jego treści."""
        for wiersz in token.content.rstrip("\n").split("\n"):
            self._wiersze.append(wiersz)
        self._pusty_wiersz()

    def _zamknij_wiersz_tabeli(self) -> None:
        """Zapisuje nagłówki tabeli albo rozpisuje rekord na wiersze komórek."""
        if self._w_naglowku_tabeli:
            self._naglowki_tabeli = list(self._komorki_wiersza)
            return
        for indeks, komorka in enumerate(self._komorki_wiersza):
            if not komorka:
                continue
            naglowek = self._naglowki_tabeli[indeks] if indeks < len(self._naglowki_tabeli) else ""
            self._wiersze.append(
                f"{naglowek}{ROZDZIELACZ_KOMORKI_TABELI}{komorka}" if naglowek else komorka
            )
        self._pusty_wiersz()

    def _pusty_wiersz(self) -> None:
        """Dopisuje pusty wiersz, o ile poprzedni wiersz nie jest już pusty."""
        if self._wiersze and self._wiersze[-1] != "":
            self._wiersze.append("")


def _nowa_lista(token: Token) -> _StanListy:
    """Buduje stan listy na podstawie tokenu jej otwarcia.

    Lista numerowana może zaczynać się od numeru innego niż jeden. Markdown-it
    przekazuje wtedy atrybut ``start``, który jest tu uwzględniany, żeby TXT
    zachował tę samą numerację co dokument źródłowy.
    """
    if token.type != _TOKEN_OTWARCIA_LISTY_NUMEROWANEJ:
        return _StanListy(numerowana=False)
    surowy_start = token.attrGet("start")
    try:
        pierwszy_numer = int(str(surowy_start))
    except (TypeError, ValueError):
        pierwszy_numer = _PIERWSZY_NUMER_DOMYSLNY
    return _StanListy(numerowana=True, numer_nastepnego=pierwszy_numer)


def tekst_inline(token: Token) -> str:
    """Składa czysty tekst z tokenu wewnątrzwierszowego markdown-it.

    Znaczniki wyróżnień znikają, treść odnośnika zostaje uzupełniona o adres
    w nawiasie, a obraz o swój opis alternatywny. Miękkie i twarde złamanie
    wiersza staje się znakiem nowej linii, dzięki czemu podział wierszy z pliku
    źródłowego nie ginie.
    """
    if not token.children:
        return token.content.strip()

    fragmenty: list[str] = []
    poczatki_odnosnikow: list[int] = []
    adresy_odnosnikow: list[str] = []

    for dziecko in token.children:
        typ = dziecko.type
        if typ in ("text", "code_inline"):
            fragmenty.append(dziecko.content)
        elif typ in ("softbreak", "hardbreak"):
            fragmenty.append("\n")
        elif typ == "link_open":
            poczatki_odnosnikow.append(len(fragmenty))
            adresy_odnosnikow.append(str(dziecko.attrGet("href") or ""))
        elif typ == "link_close":
            _zamknij_odnosnik(fragmenty, poczatki_odnosnikow, adresy_odnosnikow)
        elif typ == "image":
            fragmenty.append(_tekst_obrazu(dziecko))

    return "".join(fragmenty).strip()


def _zamknij_odnosnik(fragmenty: list[str], poczatki: list[int], adresy: list[str]) -> None:
    """Dopisuje adres odnośnika w nawiasie, jeżeli nie powtarza jego treści."""
    poczatek = poczatki.pop() if poczatki else 0
    adres = adresy.pop() if adresy else ""
    tresc_odnosnika = "".join(fragmenty[poczatek:]).strip()
    if adres and adres != tresc_odnosnika:
        fragmenty.append(f" ({adres})")


def _tekst_obrazu(token: Token) -> str:
    """Zamienia obraz na jego opis alternatywny wraz z adresem pliku."""
    opis = token.content.strip()
    adres = str(token.attrGet("src") or "")
    if opis and adres and adres != opis:
        return f"{opis} ({adres})"
    return opis or adres
