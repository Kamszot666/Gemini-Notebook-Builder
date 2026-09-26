"""Ekstrakcja treści z prezentacji PPTX, wyłącznie biblioteką standardową.

Plik PPTX jest archiwum ZIP z plikami XML w formacie Office Open XML. Odczyt
używa `zipfile` i `xml.etree.ElementTree`, bez zależności zewnętrznej, tak samo
jak odczyt ODP w `gnb.extractors.plik_odf`. Bezpieczny odczyt archiwum jest
w `gnb.extractors.pakiet_xml`.

Kolejność slajdów wynika z listy w `ppt/presentation.xml`, a nie z numerów
w nazwach plików: użytkownik potrafi przestawić slajdy, a pliki zostają pod
starymi nazwami. Każdy slajd jest nagłówkiem „Slajd N: tytuł”, po którym idzie
jego treść w kolejności występowania kształtów, a na końcu notatki mówcy.

Akapit w kształcie zastępczym treści slajdu jest elementem listy, jeżeli nie ma
wyłączonego wypunktowania, bo takie kształty dziedziczą wypunktowanie z wzorca,
którego ekstraktor nie odczytuje. Akapit w zwykłym polu tekstowym jest akapitem,
chyba że ma jawnie zapisane wypunktowanie. Tytuł, numer slajdu, data i stopka
z kształtów zastępczych nie są treścią slajdu.

Obrazy, wykresy i diagramy nie są odczytywane. Ich liczba trafia do ostrzeżeń
ekstraktora, żeby utrata treści nie była cicha.
"""

from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from gnb.core.model import BlokTresci, DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, RodzajBloku, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.blok_tabeli import blok_tabeli, oczysc_komorke
from gnb.extractors.bloki_markdown import zapisz_bloki_jako_markdown
from gnb.extractors.pakiet_xml import (
    czy_ma_wpis,
    otworz_archiwum,
    wczytaj_xml,
    wczytaj_xml_opcjonalny,
)

METODA_EKSTRAKCJI = "pptx"
FORMATY_PPTX = frozenset({"pptx"})

_P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_DCTERMS = "{http://purl.org/dc/terms/}"

_TYPY_TYTULU = frozenset({"title", "ctrTitle"})
_TYPY_POMIJANE = frozenset({"sldNum", "dt", "ftr", "hdr", "sldImg"})

KOMUNIKAT_NIEPOPRAWNY = (
    "Plik nie jest poprawną prezentacją PPTX: nie dało się odczytać jego archiwum. "
    "Prezentacja zaszyfrowana hasłem nie jest odczytywana. Zapisz ją bez szyfrowania."
)


@dataclass(slots=True)
class _Zliczenia:
    obrazy: int = 0
    obiekty: int = 0


class EkstraktorPptx:
    """Ekstraktor prezentacji PPTX zachowujący kolejność slajdów, listy i tabele."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_PPTX

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Odczytuje prezentację slajd po slajdzie. Argument `postep` nie jest używany."""
        try:
            archiwum = otworz_archiwum(bajty, identyfikator_zrodla, "prezentacją PPTX")
        except BladTrwaly as blad:
            raise BladTrwaly(KOMUNIKAT_NIEPOPRAWNY, identyfikator_zrodla) from blad
        if not czy_ma_wpis(archiwum, "ppt/presentation.xml"):
            raise BladTrwaly(
                "Plik nie jest poprawną prezentacją PPTX: brak wpisu „ppt/presentation.xml”.",
                identyfikator_zrodla,
            )
        sciezki = _sciezki_slajdow(archiwum, identyfikator_zrodla)
        zliczenia = _Zliczenia()
        bloki: list[BlokTresci] = []
        for numer, sciezka in enumerate(sciezki, start=1):
            bloki.extend(_bloki_slajdu(archiwum, sciezka, numer, zliczenia, identyfikator_zrodla))
        tytul, metadane = _metadane(archiwum, identyfikator_zrodla)
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=zapisz_bloki_jako_markdown(bloki),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.WYSOKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=tytul,
            bloki=bloki,
            metadane=metadane,
            ostrzezenia=_ostrzezenia(zliczenia),
        )


def _sciezki_slajdow(archiwum: zipfile.ZipFile, identyfikator: str) -> list[str]:
    """Zwraca ścieżki plików slajdów w kolejności z listy prezentacji."""
    prezentacja = wczytaj_xml(archiwum, "ppt/presentation.xml", identyfikator)
    relacje = wczytaj_xml_opcjonalny(archiwum, "ppt/_rels/presentation.xml.rels", identyfikator)
    cele: dict[str, str] = {}
    if relacje is not None:
        for relacja in relacje.iter(f"{_REL}Relationship"):
            identyfikator_relacji = relacja.get("Id")
            cel = relacja.get("Target")
            if identyfikator_relacji and cel:
                cele[identyfikator_relacji] = _rozwiaz_sciezke("ppt", cel)
    sciezki: list[str] = []
    for slajd in prezentacja.iter(f"{_P}sldId"):
        cel = cele.get(slajd.get(f"{_R}id", ""))
        if cel and czy_ma_wpis(archiwum, cel):
            sciezki.append(cel)
    return sciezki


def _rozwiaz_sciezke(katalog_bazowy: str, cel: str) -> str:
    """Zamienia cel relacji na ścieżkę wpisu w archiwum."""
    if cel.startswith("/"):
        return posixpath.normpath(cel.lstrip("/"))
    return posixpath.normpath(posixpath.join(katalog_bazowy, cel))


def _bloki_slajdu(
    archiwum: zipfile.ZipFile,
    sciezka: str,
    numer: int,
    zliczenia: _Zliczenia,
    identyfikator: str,
) -> list[BlokTresci]:
    slajd = wczytaj_xml(archiwum, sciezka, identyfikator)
    drzewo_ksztaltow = slajd.find(f"{_P}cSld/{_P}spTree")
    tytul: list[str] = []
    tresc: list[BlokTresci] = []
    if drzewo_ksztaltow is not None:
        _przejdz_ksztalty(drzewo_ksztaltow, tytul, tresc, zliczenia)
    naglowek = f"Slajd {numer}"
    if tytul:
        naglowek += f": {' '.join(tytul)}"
    if slajd.get("show") == "0":
        naglowek += " (slajd ukryty)"
    bloki = [BlokTresci(rodzaj=RodzajBloku.NAGLOWEK, poziom=2, tresc=naglowek), *tresc]
    notatki = _notatki(archiwum, sciezka, identyfikator)
    if notatki:
        bloki.append(
            BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=f"Notatki mówcy: {notatki}")
        )
    return bloki


def _przejdz_ksztalty(
    rodzic: ET.Element,
    tytul: list[str],
    tresc: list[BlokTresci],
    zliczenia: _Zliczenia,
) -> None:
    """Dodaje do treści slajdu tekst kształtów, rozwijając grupy kształtów."""
    for ksztalt in rodzic:
        if ksztalt.tag == f"{_P}grpSp":
            _przejdz_ksztalty(ksztalt, tytul, tresc, zliczenia)
        elif ksztalt.tag == f"{_P}sp":
            _tekst_ksztaltu(ksztalt, tytul, tresc)
        elif ksztalt.tag == f"{_P}pic":
            zliczenia.obrazy += 1
        elif ksztalt.tag == f"{_P}graphicFrame":
            _ramka_graficzna(ksztalt, tresc, zliczenia)


def _typ_ksztaltu_zastepczego(ksztalt: ET.Element) -> tuple[bool, str | None]:
    """Zwraca parę: czy kształt jest zastępczy, oraz jego typ, jeżeli go zapisano."""
    zastepczy = ksztalt.find(f"{_P}nvSpPr/{_P}nvPr/{_P}ph")
    if zastepczy is None:
        return False, None
    return True, zastepczy.get("type")


def _tekst_ksztaltu(ksztalt: ET.Element, tytul: list[str], tresc: list[BlokTresci]) -> None:
    zastepczy, typ = _typ_ksztaltu_zastepczego(ksztalt)
    if typ in _TYPY_POMIJANE:
        return
    akapity = ksztalt.findall(f"{_P}txBody/{_A}p")
    if typ in _TYPY_TYTULU:
        tekst = " ".join(filter(None, (_tekst_akapitu(akapit) for akapit in akapity)))
        if tekst and not tytul:
            tytul.append(tekst)
        return
    elementy: list[str] = []
    numerowana = False

    def zamknij_liste() -> None:
        if elementy:
            tresc.append(
                BlokTresci(
                    rodzaj=RodzajBloku.LISTA,
                    poziom=1 if numerowana else 0,
                    tresc="\n".join(elementy),
                )
            )
            elementy.clear()

    for akapit in akapity:
        tekst = _tekst_akapitu(akapit)
        if not tekst:
            continue
        rodzaj = _rodzaj_akapitu(akapit, zastepczy and typ in (None, "body", "subTitle", "obj"))
        if rodzaj == "lista":
            elementy.append(tekst)
            numerowana = akapit.find(f"{_A}pPr/{_A}buAutoNum") is not None
        else:
            zamknij_liste()
            tresc.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc=tekst))
    zamknij_liste()


def _rodzaj_akapitu(akapit: ET.Element, domyslnie_lista: bool | None) -> str:
    """Rozstrzyga, czy akapit jest elementem listy.

    Jawne wypunktowanie, znakiem albo numeracją, zawsze daje listę, a jawne jego
    wyłączenie zawsze zwykły akapit. Przy braku jawnego zapisu decyduje rodzaj
    kształtu: treść slajdu dziedziczy wypunktowanie z wzorca, pole tekstowe nie.
    """
    wlasciwosci = akapit.find(f"{_A}pPr")
    if wlasciwosci is not None:
        if wlasciwosci.find(f"{_A}buNone") is not None:
            return "akapit"
        if (
            wlasciwosci.find(f"{_A}buChar") is not None
            or wlasciwosci.find(f"{_A}buAutoNum") is not None
        ):
            return "lista"
    return "lista" if domyslnie_lista else "akapit"


def _tekst_akapitu(akapit: ET.Element) -> str:
    """Składa tekst akapitu z fragmentów, pól i łamań wiersza."""
    czesci: list[str] = []
    for element in akapit:
        if element.tag in (f"{_A}r", f"{_A}fld"):
            tekst = element.find(f"{_A}t")
            if tekst is not None and tekst.text:
                czesci.append(tekst.text)
        elif element.tag == f"{_A}br":
            czesci.append(" ")
    return oczysc_komorke("".join(czesci))


def _ramka_graficzna(ramka: ET.Element, tresc: list[BlokTresci], zliczenia: _Zliczenia) -> None:
    """Odczytuje tabelę z ramki graficznej, a wykres albo diagram zlicza jako obiekt."""
    tabela = ramka.find(f".//{_A}tbl")
    if tabela is not None:
        wiersze = [
            [
                "" if komorka.get("hMerge") == "1" else _tekst_komorki(komorka)
                for komorka in wiersz.findall(f"{_A}tc")
            ]
            for wiersz in tabela.findall(f"{_A}tr")
        ]
        blok = blok_tabeli(wiersze)
        if blok is not None:
            tresc.append(blok)
        return
    zliczenia.obiekty += 1


def _tekst_komorki(komorka: ET.Element) -> str:
    akapity = komorka.findall(f"{_A}txBody/{_A}p")
    return " ".join(filter(None, (_tekst_akapitu(akapit) for akapit in akapity)))


def _notatki(archiwum: zipfile.ZipFile, sciezka_slajdu: str, identyfikator: str) -> str:
    """Zwraca tekst notatek mówcy slajdu albo pusty napis."""
    katalog, nazwa = posixpath.split(sciezka_slajdu)
    relacje = wczytaj_xml_opcjonalny(archiwum, f"{katalog}/_rels/{nazwa}.rels", identyfikator)
    if relacje is None:
        return ""
    for relacja in relacje.iter(f"{_REL}Relationship"):
        if (relacja.get("Type") or "").endswith("/notesSlide") and relacja.get("Target"):
            cel = _rozwiaz_sciezke(katalog, relacja.get("Target", ""))
            if not czy_ma_wpis(archiwum, cel):
                return ""
            strona = wczytaj_xml(archiwum, cel, identyfikator)
            teksty: list[str] = []
            for ksztalt in strona.iter(f"{_P}sp"):
                _, typ = _typ_ksztaltu_zastepczego(ksztalt)
                if typ in _TYPY_POMIJANE:
                    continue
                for akapit in ksztalt.findall(f"{_P}txBody/{_A}p"):
                    tekst = _tekst_akapitu(akapit)
                    if tekst:
                        teksty.append(tekst)
            return " ".join(teksty)
    return ""


def _metadane(archiwum: zipfile.ZipFile, identyfikator: str) -> tuple[str | None, dict[str, str]]:
    """Odczytuje tytuł, autora i daty z właściwości dokumentu."""
    wlasciwosci = wczytaj_xml_opcjonalny(archiwum, "docProps/core.xml", identyfikator)
    if wlasciwosci is None:
        return None, {}

    def tekst(znacznik: str) -> str | None:
        element = wlasciwosci.find(znacznik)
        return element.text.strip() if element is not None and element.text else None

    metadane: dict[str, str] = {}
    autor = tekst(f"{_DC}creator")
    if autor:
        metadane["autor"] = autor
    utworzono = tekst(f"{_DCTERMS}created")
    if utworzono:
        metadane["data_publikacji"] = utworzono[:10]
    zmieniono = tekst(f"{_DCTERMS}modified")
    if zmieniono:
        metadane["data_aktualizacji"] = zmieniono[:10]
    return tekst(f"{_DC}title"), metadane


def _ostrzezenia(zliczenia: _Zliczenia) -> list[str]:
    ostrzezenia: list[str] = []
    if zliczenia.obrazy:
        ostrzezenia.append(
            f"Prezentacja zawiera obrazy ({zliczenia.obrazy}), których treść nie została "
            "odczytana. Jeżeli niosą informację, opisz ją w tekście albo dodaj je osobno."
        )
    if zliczenia.obiekty:
        ostrzezenia.append(
            f"Prezentacja zawiera wykresy albo diagramy ({zliczenia.obiekty}), których treść "
            "nie została odczytana."
        )
    return ostrzezenia
