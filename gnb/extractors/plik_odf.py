"""Ekstrakcja treści z plików ODT, ODS i ODP, czyli dokumentów OpenDocument.

Pliki OpenDocument są archiwami ZIP, w których treść leży w pliku `content.xml`,
a metadane w `meta.xml`. Odczyt opiera się wyłącznie na bibliotece standardowej:
`zipfile` i `xml.etree.ElementTree`, bez żadnej zależności zewnętrznej. Bezpieczny
odczyt archiwum, w tym ograniczenie rozmiaru rozpakowanej treści i odrzucenie
encji XML, jest w `gnb.extractors.pakiet_xml`.

Format niesie prawdziwą strukturę: element `text:h` to nagłówek z poziomem,
`text:list` to lista, `table:table` to tabela. Dzięki temu ekstraktory zgłaszają
wysoki poziom pewności struktury. Numeracja listy wynika ze stylu listy zapisanego
w dokumencie, a nie z zgadywania po treści.

Trzy ekstraktory mają wspólny rdzeń odczytu bloków:

1. ODT, dokument tekstowy: nagłówki, akapity, listy, tabele. Treść przypisów
   dolnych trafia jako osobne akapity „Przypis: …” zaraz po akapicie, w którym
   przypis stoi, żeby nie przepadła.
2. ODS, arkusz: każdy arkusz jest nagłówkiem i tabelą. Komórka jest zapisana
   tak, jak widzi ją użytkownik, czyli sformatowana, na przykład walutą albo
   datą, a nie surową liczbą. Pierwszy wiersz arkusza jest nagłówkiem z założenia.
3. ODP, prezentacja: każdy slajd jest nagłówkiem „Slajd N: tytuł”, po którym
   idzie treść slajdu, a na końcu notatki mówcy.

Obrazy i obiekty osadzone, na przykład wykresy, nie są odczytywane. Ich liczba
trafia do ostrzeżeń ekstraktora, żeby utrata treści nie była cicha.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.blok_tabeli import blok_tabeli, oczysc_komorke
from gnb.extractors.bloki_markdown import zapisz_bloki_jako_markdown
from gnb.extractors.pakiet_xml import (
    atrybut,
    czy_ma_wpis,
    jeden_wiersz,
    otworz_archiwum,
    wczytaj_bajty_wpisu,
    wczytaj_xml,
    wczytaj_xml_opcjonalny,
    zbuduj_drzewo,
)

_OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
_TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
_DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
_PRES = "{urn:oasis:names:tc:opendocument:xmlns:presentation:1.0}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_META = "{urn:oasis:names:tc:opendocument:xmlns:meta:1.0}"

METODA_ODT = "odt"
METODA_ODS = "ods"
METODA_ODP = "odp"

# Ile pustych albo powtórzonych komórek i wierszy ze znacznikiem powtórzenia
# jest rozwijanych. Arkusz zapisuje puste komórki do końca wiersza jednym
# elementem z liczbą powtórzeń rzędu tysięcy, więc bez granicy jeden wiersz
# rozrósłby się do tysięcy pustych komórek.
_MAKSYMALNE_POWTORZENIE_KOMORKI = 200
_MAKSYMALNE_POWTORZENIE_WIERSZA = 1000
_MAKSYMALNA_LICZBA_SPACJI = 50

# Elementy treści dokumentu tekstowego, które nie są treścią autora: spisy
# generowane automatycznie, śledzone zmiany, których usunięty tekst nie należy
# do dokumentu, oraz deklaracje pól.
_POMIJANE = frozenset(
    {
        _TEXT + "tracked-changes",
        _TEXT + "table-of-content",
        _TEXT + "illustration-index",
        _TEXT + "table-index",
        _TEXT + "object-index",
        _TEXT + "user-index",
        _TEXT + "alphabetical-index",
        _TEXT + "bibliography",
        _TEXT + "sequence-decls",
        _TEXT + "variable-decls",
        _TEXT + "user-field-decls",
        _TEXT + "soft-page-break",
        _OFFICE + "forms",
    }
)

# Klasy ramek prezentacji, które nie niosą treści slajdu.
_KLASY_POMIJANE_NA_SLAJDZIE = frozenset({"page-number", "date-time", "footer", "header"})

# Klasy ramek na stronie notatek, które nie są notatką mówcy: miniatura slajdu
# oraz nagłówek, stopka, data i numer strony. Notatka mówcy jest każdą inną
# ramką z tekstem, także taką bez klasy, bo nie każdy program zapisuje klasę.
_KLASY_POMIJANE_W_NOTATKACH = frozenset({"page", "header", "footer", "date-time", "page-number"})

KOMUNIKAT_ZASZYFROWANY = (
    "Plik jest zaszyfrowany hasłem, więc jego treści nie da się odczytać. Zapisz go "
    "w programie bez szyfrowania i dodaj ponownie."
)


@dataclass(slots=True)
class _Kontekst:
    """Stan odczytu jednego dokumentu: przypisy czekające na zapis i liczniki pominiętych."""

    numerowane_style: frozenset[str]
    przypisy: list[str] = field(default_factory=list)
    obrazy: int = 0
    obiekty: int = 0
    powtorzenia_obciete: int = 0


class _EkstraktorOdf:
    """Wspólny szkielet trzech ekstraktorów: odczyt archiwum, metadane, ostrzeżenia."""

    metoda = ""
    tekst_zawiera_znaczniki = True
    _format = ""
    _opis_formatu = ""

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla == self._format

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Odczytuje dokument OpenDocument i zwraca bloki w kolejności występowania.

        Ekstrakcja nie ma etapu długotrwałego, więc argument `postep` jest
        przyjmowany dla zgodności z kontraktem i nie jest używany.
        """
        archiwum = otworz_archiwum(bajty, identyfikator_zrodla, self._opis_formatu)
        if not czy_ma_wpis(archiwum, "content.xml"):
            raise BladTrwaly(
                f"Plik nie jest poprawnym {self._opis_formatu}: w archiwum nie ma wpisu "
                "„content.xml”.",
                identyfikator_zrodla,
            )
        if _jest_zaszyfrowany(archiwum, identyfikator_zrodla):
            raise BladTrwaly(KOMUNIKAT_ZASZYFROWANY, identyfikator_zrodla)

        tresc = wczytaj_xml(archiwum, "content.xml", identyfikator_zrodla)
        style = wczytaj_xml_opcjonalny(archiwum, "styles.xml", identyfikator_zrodla)
        kontekst = _Kontekst(numerowane_style=_numerowane_style(tresc, style))
        cialo = tresc.find(f"{_OFFICE}body")
        if cialo is None:
            raise BladTrwaly(
                f"Plik nie jest poprawnym {self._opis_formatu}: brak treści dokumentu.",
                identyfikator_zrodla,
            )
        bloki = self._bloki_dokumentu(cialo, kontekst)
        meta = wczytaj_xml_opcjonalny(archiwum, "meta.xml", identyfikator_zrodla)
        tytul_z_metadanych, metadane = _metadane(meta)
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=zapisz_bloki_jako_markdown(bloki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=self.metoda,
            tytul=self._tytul(tytul_z_metadanych, bloki),
            bloki=bloki,
            metadane=metadane,
            ostrzezenia=_ostrzezenia(kontekst),
        )

    def _bloki_dokumentu(self, cialo: ET.Element, kontekst: _Kontekst) -> list[BlokTresci]:
        raise NotImplementedError

    def _tytul(self, tytul_z_metadanych: str | None, bloki: list[BlokTresci]) -> str | None:
        return tytul_z_metadanych


class EkstraktorOdt(_EkstraktorOdf):
    """Ekstraktor dokumentów tekstowych ODT."""

    metoda = METODA_ODT
    _format = "odt"
    _opis_formatu = "dokumentem ODT"

    def _bloki_dokumentu(self, cialo: ET.Element, kontekst: _Kontekst) -> list[BlokTresci]:
        tekst = cialo.find(f"{_OFFICE}text")
        return _bloki(tekst, kontekst) if tekst is not None else []

    def _tytul(self, tytul_z_metadanych: str | None, bloki: list[BlokTresci]) -> str | None:
        if tytul_z_metadanych:
            return tytul_z_metadanych
        for blok in bloki:
            if blok.rodzaj is RodzajBloku.NAGLOWEK:
                return blok.tresc
        return None


class EkstraktorOds(_EkstraktorOdf):
    """Ekstraktor arkuszy ODS: każdy arkusz jako nagłówek i tabela."""

    metoda = METODA_ODS
    _format = "ods"
    _opis_formatu = "arkuszem ODS"

    def _bloki_dokumentu(self, cialo: ET.Element, kontekst: _Kontekst) -> list[BlokTresci]:
        arkusze = cialo.find(f"{_OFFICE}spreadsheet")
        bloki: list[BlokTresci] = []
        if arkusze is None:
            return bloki
        for arkusz in arkusze.findall(f"{_TABLE}table"):
            nazwa = atrybut(arkusz, "name") or "bez nazwy"
            tabela = blok_tabeli(_wiersze_tabeli(arkusz, kontekst))
            if tabela is None:
                continue
            bloki.append(
                BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=2, tresc=f"Arkusz: {nazwa}")
            )
            bloki.append(tabela)
        return bloki


class EkstraktorOdp(_EkstraktorOdf):
    """Ekstraktor prezentacji ODP: slajd po slajdzie, z notatkami mówcy."""

    metoda = METODA_ODP
    _format = "odp"
    _opis_formatu = "prezentacją ODP"

    def _bloki_dokumentu(self, cialo: ET.Element, kontekst: _Kontekst) -> list[BlokTresci]:
        prezentacja = cialo.find(f"{_OFFICE}presentation")
        bloki: list[BlokTresci] = []
        if prezentacja is None:
            return bloki
        for numer, strona in enumerate(prezentacja.findall(f"{_DRAW}page"), start=1):
            bloki.extend(_bloki_slajdu(strona, numer, kontekst))
        return bloki


# --- odczyt bloków ---------------------------------------------------------


def _jest_zaszyfrowany(archiwum: zipfile.ZipFile, identyfikator: str) -> bool:
    """Sprawdza w manifeście archiwum, czy dowolny wpis jest zaszyfrowany."""
    if not czy_ma_wpis(archiwum, "META-INF/manifest.xml"):
        return False
    manifest = zbuduj_drzewo(
        wczytaj_bajty_wpisu(archiwum, "META-INF/manifest.xml", identyfikator),
        "META-INF/manifest.xml",
        identyfikator,
    )
    return any(element.tag.endswith("}encryption-data") for element in manifest.iter())


def _numerowane_style(*drzewa: ET.Element | None) -> frozenset[str]:
    """Zwraca nazwy stylów list, których pierwszy poziom jest numerowany.

    Numeracja listy nie wynika z jej treści, tylko ze stylu, do którego odwołuje
    się atrybut `text:style-name`. Styl, którego pierwszy poziom jest zdefiniowany
    elementem `list-level-style-number`, daje listę numerowaną, a każdy inny
    listę wypunktowaną.
    """
    numerowane: set[str] = set()
    for drzewo in drzewa:
        if drzewo is None:
            continue
        for styl in drzewo.iter(f"{_TEXT}list-style"):
            nazwa = atrybut(styl, "name")
            pierwszy = next(iter(styl), None)
            if nazwa and pierwszy is not None and pierwszy.tag.endswith("}list-level-style-number"):
                numerowane.add(nazwa)
    return frozenset(numerowane)


def _bloki(rodzic: ET.Element, kontekst: _Kontekst) -> list[BlokTresci]:
    """Zamienia dzieci elementu na bloki treści, rozwijając sekcje i ramki tekstowe."""
    bloki: list[BlokTresci] = []
    for dziecko in rodzic:
        znacznik = dziecko.tag
        if znacznik in _POMIJANE:
            continue
        if znacznik == f"{_TEXT}h":
            tekst = jeden_wiersz(_tekst_wiersza(dziecko, kontekst))
            if tekst:
                poziom = _liczba(atrybut(dziecko, "outline-level"), 1)
                bloki.append(BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=poziom, tresc=tekst))
            _zapisz_przypisy(bloki, kontekst)
        elif znacznik == f"{_TEXT}p":
            tekst = jeden_wiersz(_tekst_wiersza(dziecko, kontekst))
            if tekst:
                bloki.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=tekst))
            _zapisz_przypisy(bloki, kontekst)
        elif znacznik == f"{_TEXT}list":
            blok_listy = _blok_listy(dziecko, kontekst)
            if blok_listy is not None:
                bloki.append(blok_listy)
            _zapisz_przypisy(bloki, kontekst)
        elif znacznik == f"{_TABLE}table":
            tabela = blok_tabeli(_wiersze_tabeli(dziecko, kontekst))
            if tabela is not None:
                bloki.append(tabela)
            _zapisz_przypisy(bloki, kontekst)
        elif znacznik == f"{_DRAW}image":
            kontekst.obrazy += 1
        elif znacznik == f"{_DRAW}object" or znacznik == f"{_DRAW}object-ole":
            kontekst.obiekty += 1
        else:
            bloki.extend(_bloki(dziecko, kontekst))
    return bloki


def _zapisz_przypisy(bloki: list[BlokTresci], kontekst: _Kontekst) -> None:
    """Dopisuje po bloku treść przypisów dolnych, które w nim stały."""
    for przypis in kontekst.przypisy:
        if przypis:
            bloki.append(
                BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=f"Przypis: {przypis}")
            )
    kontekst.przypisy.clear()


def _tekst_wiersza(element: ET.Element, kontekst: _Kontekst) -> str:
    """Składa tekst akapitu albo nagłówka, obsługując spacje, tabulatory i przypisy."""
    czesci = [element.text or ""]
    for dziecko in element:
        znacznik = dziecko.tag
        if znacznik == f"{_TEXT}s":
            czesci.append(" " * min(_liczba(atrybut(dziecko, "c"), 1), _MAKSYMALNA_LICZBA_SPACJI))
        elif znacznik in (f"{_TEXT}tab", f"{_TEXT}line-break"):
            czesci.append(" ")
        elif znacznik == f"{_TEXT}note":
            kontekst.przypisy.append(_tekst_przypisu(dziecko, kontekst))
        elif znacznik == f"{_DRAW}image":
            kontekst.obrazy += 1
        elif znacznik in (f"{_DRAW}object", f"{_DRAW}object-ole"):
            kontekst.obiekty += 1
        else:
            czesci.append(_tekst_wiersza(dziecko, kontekst))
        czesci.append(dziecko.tail or "")
    return "".join(czesci)


def _tekst_przypisu(przypis: ET.Element, kontekst: _Kontekst) -> str:
    """Zwraca treść przypisu dolnego albo końcowego, bez jego numeru."""
    tresc = przypis.find(f"{_TEXT}note-body")
    if tresc is None:
        return ""
    akapity = [
        jeden_wiersz(_tekst_wiersza(akapit, kontekst))
        for akapit in tresc
        if akapit.tag in (f"{_TEXT}p", f"{_TEXT}h")
    ]
    return " ".join(akapit for akapit in akapity if akapit)


def _blok_listy(lista: ET.Element, kontekst: _Kontekst) -> BlokTresci | None:
    """Zamienia listę, także zagnieżdżoną, na jeden blok listy.

    Elementy zagnieżdżonych list są dopisywane po elemencie, w którym stoją,
    a wcięcie nie jest zachowywane: format bloku listy jest płaski. Numeracja
    wynika ze stylu zewnętrznej listy.
    """
    elementy: list[str] = []

    def zbierz(biezaca: ET.Element) -> None:
        for pozycja in biezaca:
            wlasny = [
                jeden_wiersz(_tekst_wiersza(akapit, kontekst))
                for akapit in pozycja
                if akapit.tag in (f"{_TEXT}p", f"{_TEXT}h")
            ]
            tekst = " ".join(fragment for fragment in wlasny if fragment)
            if tekst:
                elementy.append(tekst)
            for zagniezdzona in pozycja:
                if zagniezdzona.tag == f"{_TEXT}list":
                    zbierz(zagniezdzona)

    zbierz(lista)
    if not elementy:
        return None
    styl = atrybut(lista, "style-name")
    numerowana = styl is not None and styl in kontekst.numerowane_style
    return BlokTresci(
        rodzaj=RodzajBloku.LISTA, poziom=1 if numerowana else 0, tresc="\n".join(elementy)
    )


def _wiersze_tabeli(tabela: ET.Element, kontekst: _Kontekst) -> list[list[str]]:
    """Zwraca wiersze tabeli z komórkami jako tekst, rozwijając powtórzenia z ograniczeniem."""
    wiersze: list[list[str]] = []
    for wiersz in _elementy_wierszy(tabela):
        komorki: list[str] = []
        for komorka in wiersz:
            if komorka.tag not in (f"{_TABLE}table-cell", f"{_TABLE}covered-table-cell"):
                continue
            tekst = (
                ""
                if komorka.tag == f"{_TABLE}covered-table-cell"
                else _tekst_komorki(komorka, kontekst)
            )
            powtorzen = _liczba(atrybut(komorka, "number-columns-repeated"), 1)
            if powtorzen > _MAKSYMALNE_POWTORZENIE_KOMORKI:
                kontekst.powtorzenia_obciete += 1 if tekst else 0
            komorki.extend([tekst] * min(powtorzen, _MAKSYMALNE_POWTORZENIE_KOMORKI))
        if not any(komorki):
            continue
        powtorzen_wiersza = _liczba(atrybut(wiersz, "number-rows-repeated"), 1)
        if powtorzen_wiersza > _MAKSYMALNE_POWTORZENIE_WIERSZA:
            kontekst.powtorzenia_obciete += 1
        wiersze.extend([komorki] * min(powtorzen_wiersza, _MAKSYMALNE_POWTORZENIE_WIERSZA))
    return wiersze


def _elementy_wierszy(tabela: ET.Element) -> list[ET.Element]:
    """Zwraca wiersze tabeli, także z grup nagłówków i grup wierszy."""
    wiersze: list[ET.Element] = []
    for dziecko in tabela:
        if dziecko.tag == f"{_TABLE}table-row":
            wiersze.append(dziecko)
        elif dziecko.tag in (
            f"{_TABLE}table-header-rows",
            f"{_TABLE}table-rows",
            f"{_TABLE}table-row-group",
        ):
            wiersze.extend(_elementy_wierszy(dziecko))
    return wiersze


def _tekst_komorki(komorka: ET.Element, kontekst: _Kontekst) -> str:
    """Zwraca tekst komórki tak, jak widzi go użytkownik, a przy braku tekstu jej wartość."""
    tekst = " ".join(oczysc_komorke(blok.tresc) for blok in _bloki(komorka, kontekst))
    if tekst:
        return tekst
    wartosc = atrybut(komorka, "value") or atrybut(komorka, "string-value")
    return oczysc_komorke(wartosc) if wartosc else ""


def _bloki_slajdu(strona: ET.Element, numer: int, kontekst: _Kontekst) -> list[BlokTresci]:
    """Zamienia jeden slajd prezentacji na nagłówek, treść i notatki mówcy."""
    tytul: str | None = None
    tresc: list[BlokTresci] = []
    notatki: list[str] = []
    for dziecko in strona:
        if dziecko.tag == f"{_PRES}notes":
            for ramka in dziecko.iter(f"{_DRAW}frame"):
                if atrybut(ramka, "class") not in _KLASY_POMIJANE_W_NOTATKACH:
                    notatki.extend(
                        oczysc_komorke(blok.tresc)
                        for blok in _bloki(ramka, kontekst)
                        if blok.rodzaj is not RodzajBloku.TABELA
                    )
            continue
        klasa = atrybut(dziecko, "class") if dziecko.tag == f"{_DRAW}frame" else None
        if klasa in _KLASY_POMIJANE_NA_SLAJDZIE:
            continue
        bloki_ramki = _bloki(dziecko, kontekst) if dziecko.tag != f"{_DRAW}image" else []
        if dziecko.tag == f"{_DRAW}image":
            kontekst.obrazy += 1
        if klasa == "title" and tytul is None and bloki_ramki:
            tytul = " ".join(oczysc_komorke(blok.tresc) for blok in bloki_ramki)
            continue
        tresc.extend(bloki_ramki)
    naglowek = f"Slajd {numer}" + (f": {tytul}" if tytul else "")
    bloki = [BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=2, tresc=naglowek), *tresc]
    if notatki:
        bloki.append(
            BlokTresci(
                rodzaj=RodzajBloku.AKAPIT,
                poziom=0,
                tresc="Notatki mówcy: " + " ".join(notatki),
            )
        )
    return bloki


def _metadane(meta: ET.Element | None) -> tuple[str | None, dict[str, str]]:
    """Odczytuje tytuł, autora i daty z pliku `meta.xml`."""
    if meta is None:
        return None, {}
    opis = meta.find(f"{_OFFICE}meta")
    if opis is None:
        return None, {}

    def tekst(znacznik: str) -> str | None:
        element = opis.find(znacznik)
        return element.text.strip() if element is not None and element.text else None

    metadane: dict[str, str] = {}
    autor = tekst(f"{_META}initial-creator") or tekst(f"{_DC}creator")
    if autor:
        metadane["autor"] = autor
    utworzono = tekst(f"{_META}creation-date")
    if utworzono:
        metadane["data_publikacji"] = utworzono[:10]
    zmieniono = tekst(f"{_DC}date")
    if zmieniono:
        metadane["data_aktualizacji"] = zmieniono[:10]
    return tekst(f"{_DC}title"), metadane


def _ostrzezenia(kontekst: _Kontekst) -> list[str]:
    """Zbiera ostrzeżenia o treści, której ekstraktor nie odczytał."""
    ostrzezenia: list[str] = []
    if kontekst.obrazy:
        ostrzezenia.append(
            f"Dokument zawiera obrazy ({kontekst.obrazy}), których treść nie została odczytana. "
            "Jeżeli niosą informację, opisz ją w tekście albo dodaj je osobno jako obrazy."
        )
    if kontekst.obiekty:
        ostrzezenia.append(
            f"Dokument zawiera obiekty osadzone, na przykład wykresy albo wzory "
            f"({kontekst.obiekty}), których treść nie została odczytana."
        )
    if kontekst.powtorzenia_obciete:
        ostrzezenia.append(
            f"W dokumencie są komórki lub wiersze powtórzone ponad dopuszczalną granicę "
            f"({kontekst.powtorzenia_obciete} miejsc), więc ich powtórzenia zostały obcięte."
        )
    return ostrzezenia


def _liczba(wartosc: str | None, domyslna: int) -> int:
    """Zamienia atrybut na liczbę całkowitą dodatnią, a przy błędzie zwraca wartość domyślną."""
    if wartosc is None:
        return domyslna
    try:
        liczba = int(wartosc)
    except ValueError:
        return domyslna
    return liczba if liczba > 0 else domyslna
