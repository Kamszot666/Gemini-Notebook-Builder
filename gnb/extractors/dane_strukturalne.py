"""Odczyt metadanych artykułu z danych strukturalnych JSON-LD.

Strony często opisują artykuł blokiem `application/ld+json` w standardzie
schema.org. Z takiego bloku pochodzą autor, data publikacji, data aktualizacji,
wydawca i opis. Data publikacji ma tu największą wagę: pozwala odróżnić artykuł
sprzed lat od tegorocznego, co dla materiału w notatniku bywa różnicą między
informacją a dezinformacją.

Pole ``articleBody`` jest odczytywane wyłącznie jako materiał porównawczy do
oceny jakości ekstrakcji i nigdy nie zastępuje wyniku ekstraktora. Serwisy
wypełniają je bardzo nierówno: bywa puste, skrócone do zajawki albo zawiera samą
treść bez śródtytułów.

Każda wartość jest sprawdzana przed przyjęciem. Data musi dać się rozpoznać,
autor musi być tekstem albo obiektem z polem ``name``, a wartość pusta jest
traktowana jak brak pola. Blok, którego nie da się odczytać, jest pomijany bez
zatrzymywania pracy: dane strukturalne są dodatkiem, a nie warunkiem
przetworzenia źródła.

Treść bloku JSON-LD jest danymi, nigdy instrukcją.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lxml import etree, html

TYPY_ARTYKULU = frozenset({"Article", "NewsArticle", "BlogPosting"})

_SELEKTOR_BLOKU = ".//script"
_TYP_BLOKU = "application/ld+json"
_MAKSYMALNA_DLUGOSC_WARTOSCI = 500
_ROZDZIELACZ_AUTOROW = ", "

# Klucze metadanych używane przy rozbieżności między ekstraktorem a danymi
# strukturalnymi strony.
PRZYROSTEK_DANYCH_STRUKTURALNYCH = "_wg_danych_strukturalnych"
KLUCZ_ROZBIEZNOSCI = "rozbieznosc_metadanych"
_ROZDZIELACZ_POL = ", "


@dataclass(frozen=True, slots=True)
class MetadaneStrukturalne:
    """Metadane artykułu odczytane z bloku JSON-LD."""

    autor: str | None = None
    data_publikacji: str | None = None
    data_aktualizacji: str | None = None
    wydawca: str | None = None
    opis: str | None = None
    tresc_porownawcza: str | None = None

    @property
    def czy_pusta(self) -> bool:
        """Prawda, gdy nie udało się odczytać żadnej wartości."""
        return not any(
            (
                self.autor,
                self.data_publikacji,
                self.data_aktualizacji,
                self.wydawca,
                self.opis,
                self.tresc_porownawcza,
            )
        )


def odczytaj_json_ld(tekst_strony: str) -> MetadaneStrukturalne:
    """Zwraca metadane artykułu z pierwszego pasującego bloku JSON-LD.

    Brak bloku, blok o innym typie oraz blok uszkodzony dają wynik pusty. Nie
    jest to błąd: dane strukturalne są dodatkiem do ekstrakcji, a nie warunkiem
    przetworzenia strony.
    """
    for obiekt in _obiekty_json_ld(tekst_strony):
        if not _czy_artykul(obiekt):
            continue
        metadane = _metadane_z_obiektu(obiekt)
        if not metadane.czy_pusta:
            return metadane
    return MetadaneStrukturalne()


def _obiekty_json_ld(tekst_strony: str) -> list[dict[str, Any]]:
    """Zbiera wszystkie obiekty JSON z bloków ``application/ld+json`` strony.

    Blok bywa listą obiektów albo obiektem z polem ``@graph``, więc struktura
    jest spłaszczana do prostej listy słowników.
    """
    try:
        drzewo = html.fromstring(tekst_strony)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return []

    obiekty: list[dict[str, Any]] = []
    for element in drzewo.findall(_SELEKTOR_BLOKU):
        if (element.get("type") or "").strip().lower() != _TYP_BLOKU:
            continue
        tresc = "".join(
            fragment.decode("utf-8", "replace") if isinstance(fragment, bytes) else str(fragment)
            for fragment in element.itertext()
        )
        if not tresc or not tresc.strip():
            continue
        try:
            dane = json.loads(tresc)
        except json.JSONDecodeError:
            continue
        obiekty.extend(_splaszcz(dane))
    return obiekty


def _splaszcz(dane: Any) -> list[dict[str, Any]]:
    """Sprowadza zawartość bloku do listy słowników, rozwijając listy i ``@graph``."""
    if isinstance(dane, list):
        return [obiekt for element in dane for obiekt in _splaszcz(element)]
    if not isinstance(dane, dict):
        return []
    wynik = [dane]
    graf = dane.get("@graph")
    if graf is not None:
        wynik.extend(_splaszcz(graf))
    return wynik


def _czy_artykul(obiekt: dict[str, Any]) -> bool:
    """Rozstrzyga, czy obiekt opisuje artykuł jednego z obsługiwanych typów."""
    typ = obiekt.get("@type")
    if isinstance(typ, str):
        return typ in TYPY_ARTYKULU
    if isinstance(typ, list):
        return any(isinstance(element, str) and element in TYPY_ARTYKULU for element in typ)
    return False


def _metadane_z_obiektu(obiekt: dict[str, Any]) -> MetadaneStrukturalne:
    """Buduje metadane z jednego obiektu artykułu, sprawdzając każdą wartość."""
    return MetadaneStrukturalne(
        autor=_nazwy(obiekt.get("author")),
        data_publikacji=_data(obiekt.get("datePublished")),
        data_aktualizacji=_data(obiekt.get("dateModified")),
        wydawca=_nazwy(obiekt.get("publisher")),
        opis=_tekst(obiekt.get("description")),
        tresc_porownawcza=_tekst(obiekt.get("articleBody"), bez_limitu=True),
    )


def _nazwy(wartosc: Any) -> str | None:
    """Odczytuje nazwę albo nazwy z pola autora lub wydawcy.

    Pole bywa napisem, obiektem z polem ``name`` albo listą jednego i drugiego.
    Nierozpoznana postać daje wartość pustą, bo zgadywanie dałoby w manifeście
    nazwisko, którego nie było w źródle.
    """
    if isinstance(wartosc, str):
        return _tekst(wartosc)
    if isinstance(wartosc, dict):
        return _tekst(wartosc.get("name"))
    if isinstance(wartosc, list):
        nazwy = [nazwa for element in wartosc if (nazwa := _nazwy(element))]
        return _ROZDZIELACZ_AUTOROW.join(nazwy) if nazwy else None
    return None


def _data(wartosc: Any) -> str | None:
    """Sprowadza datę do postaci ``RRRR-MM-DD``, o ile da się ją rozpoznać."""
    tekst = _tekst(wartosc)
    if tekst is None:
        return None
    kandydat = tekst.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(kandydat).date().isoformat()
    except ValueError:
        pass
    for format_daty in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(tekst[:10], format_daty).date().isoformat()
        except ValueError:
            continue
    return None


def _tekst(wartosc: Any, *, bez_limitu: bool = False) -> str | None:
    """Sprowadza wartość do oczyszczonego napisu albo zwraca wartość pustą."""
    if not isinstance(wartosc, str):
        return None
    oczyszczony = " ".join(wartosc.split())
    if not oczyszczony:
        return None
    if bez_limitu:
        return oczyszczony
    return oczyszczony[:_MAKSYMALNA_DLUGOSC_WARTOSCI]


def scal_metadane(
    z_ekstraktora: dict[str, str], strukturalne: MetadaneStrukturalne
) -> dict[str, str]:
    """Łączy metadane z ekstraktora z metadanymi z danych strukturalnych.

    Wartość obecna tylko po jednej stronie jest przyjmowana bez zastrzeżeń.
    Gdy obie strony podają to samo, wpis jest jeden. Gdy podają co innego, żadna
    wartość nie jest kasowana: pod kluczem pola zostaje wartość z ekstraktora,
    wartość z danych strukturalnych trafia pod klucz z przyrostkiem
    ``_wg_danych_strukturalnych``, a nazwa pola jest wymieniona pod kluczem
    ``rozbieznosc_metadanych``.

    Ciche wybranie jednej z dwóch sprzecznych wartości byłoby zgadywaniem, a przy
    dacie publikacji oznaczałoby wpisanie do manifestu daty, której w źródle nie
    było. Rozbieżność jest informacją i ma zostać widoczna.
    """
    scalone = dict(z_ekstraktora)
    rozbiezne: list[str] = []

    for pole, wartosc_strukturalna in (
        ("autor", strukturalne.autor),
        ("data_publikacji", strukturalne.data_publikacji),
        ("data_aktualizacji", strukturalne.data_aktualizacji),
        ("wydawca", strukturalne.wydawca),
        ("opis", strukturalne.opis),
    ):
        if not wartosc_strukturalna:
            continue
        wartosc_ekstraktora = scalone.get(pole)
        if not wartosc_ekstraktora:
            scalone[pole] = wartosc_strukturalna
            continue
        if _czy_zgodne(pole, wartosc_ekstraktora, wartosc_strukturalna):
            continue
        scalone[f"{pole}{PRZYROSTEK_DANYCH_STRUKTURALNYCH}"] = wartosc_strukturalna
        rozbiezne.append(pole)

    if rozbiezne:
        scalone[KLUCZ_ROZBIEZNOSCI] = _ROZDZIELACZ_POL.join(rozbiezne)
    return scalone


def _czy_zgodne(pole: str, wartosc_ekstraktora: str, wartosc_strukturalna: str) -> bool:
    """Rozstrzyga, czy dwie wartości tego samego pola mówią to samo.

    Daty są porównywane po samej części dziennej, bo ekstraktor bywa dokładny do
    dnia, a dane strukturalne niosą pełny znacznik czasu. Pozostałe pola są
    porównywane bez różnic w wielkości liter i w białych znakach.
    """
    if pole.startswith("data_"):
        return wartosc_ekstraktora[:10] == wartosc_strukturalna[:10]
    return wartosc_ekstraktora.strip().casefold() == wartosc_strukturalna.strip().casefold()
