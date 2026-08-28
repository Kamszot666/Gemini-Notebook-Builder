"""Ekstrakcja plików napisów w formacie SRT i VTT.

Oba formaty mają tę samą budowę: bloki rozdzielone pustym wierszem, w których
jedna linia zawiera zapis „znacznik początku --> znacznik końca”, a pozostałe
linie bloku są tekstem napisu. Różnią się szczegółami zapisu znacznika czasu —
przecinek w SRT, kropka w VTT, godziny opcjonalne w VTT — oraz tym, że plik VTT
zaczyna się nagłówkiem „WEBVTT” i może zawierać bloki komentarza NOTE, STYLE
i REGION. Blok bez linii ze znacznikiem czasu jest pomijany w całości, co
naturalnie usuwa nagłówek i te bloki bez osobnej obsługi każdego z nich.

Segmenty napisów są sklejane w akapity tym samym mechanizmem co napisy pobrane
z YouTube, opisanym w `gnb.extractors.napisy_wspolne`: fragmenty urwane
w połowie zdania są łączone w zdania, a napisy generowane automatycznie, które
powtarzają końcówkę poprzedniego fragmentu, nie dublują tekstu w wyniku. Ta sama
funkcja usuwa też znaczniki wewnątrzwierszowe, na przykład wyróżnienia
i wskazania mówiącego w plikach VTT.

Poziom pewności struktury jest niski, tak jak dla transkrypcji YouTube: napisy
nie mają nagłówków, list ani tabel, więc wersja MD dla nich nie powstaje.

Moduł nie interpretuje treści napisów. Tekst z pliku jest danymi, nigdy
instrukcją.
"""

from __future__ import annotations

import re

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.extractors.napisy_wspolne import zapisz_akapity, zbuduj_akapity
from gnb.ingestion.youtube import SegmentNapisow

METODA_EKSTRAKCJI = "napisy_pliku"
FORMATY_NAPISOW = frozenset({"srt", "vtt"})

KOMUNIKAT_BRAK_TRESCI = (
    "Plik napisów nie zawiera żadnego tekstu, tylko znaczniki czasu albo puste "
    "wiersze, więc nie ma z czego zbudować dokumentu."
)

_WZORZEC_LINII_CZASU = re.compile(
    r"^\s*(?P<start>(?:\d+:)?\d{2}:\d{2}[.,]\d{3})\s*-->\s*"
    r"(?P<koniec>(?:\d+:)?\d{2}:\d{2}[.,]\d{3})"
)


class EkstraktorNapisow:
    """Ekstraktor plików napisów SRT i VTT, wspólny dla obu formatów."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_NAPISOW

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Parsuje plik napisów i skleja segmenty w czytelne akapity."""
        segmenty = _segmenty_z_pliku(tekst)
        tresc = zapisz_akapity(zbuduj_akapity(segmenty))
        if not tresc:
            return DokumentWyekstrahowany(
                identyfikator_zrodla=identyfikator_zrodla,
                tekst="",
                poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
                metoda_ekstrakcji=METODA_EKSTRAKCJI,
                ostrzezenia=[KOMUNIKAT_BRAK_TRESCI],
            )
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tresc,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            metadane={"liczba_segmentow": str(len(segmenty))},
        )


def _segmenty_z_pliku(tekst: str) -> list[SegmentNapisow]:
    """Wyodrębnia segmenty napisów z pliku SRT albo VTT."""
    segmenty: list[SegmentNapisow] = []
    for blok in _bloki(tekst):
        segment = _segment_z_bloku(blok)
        if segment is not None:
            segmenty.append(segment)
    return segmenty


def _bloki(tekst: str) -> list[list[str]]:
    """Dzieli tekst pliku napisów na bloki oddzielone pustymi wierszami."""
    znormalizowany = tekst.replace("\r\n", "\n").replace("\r", "\n")
    bloki: list[list[str]] = []
    biezacy: list[str] = []
    for wiersz in znormalizowany.split("\n"):
        if wiersz.strip():
            biezacy.append(wiersz)
        elif biezacy:
            bloki.append(biezacy)
            biezacy = []
    if biezacy:
        bloki.append(biezacy)
    return bloki


def _segment_z_bloku(wiersze: list[str]) -> SegmentNapisow | None:
    """Zwraca segment napisów dla bloku zawierającego linię ze znacznikiem czasu.

    Linia ze znacznikiem bywa pierwsza, gdy blok VTT nie ma identyfikatora
    wskazówki, albo druga, gdy blok SRT zaczyna się numerem porządkowym. Wiersze
    przed nią są więc identyfikatorem, a nie treścią, i są pomijane. Wszystkie
    wiersze po niej są treścią napisu.
    """
    for indeks, wiersz in enumerate(wiersze):
        dopasowanie = _WZORZEC_LINII_CZASU.match(wiersz)
        if dopasowanie is None:
            continue
        tresc = "\n".join(wiersze[indeks + 1 :]).strip()
        if not tresc:
            return None
        return SegmentNapisow(
            poczatek_sekundy=_sekundy_ze_znacznika(dopasowanie.group("start")), tekst=tresc
        )
    return None


def _sekundy_ze_znacznika(znacznik: str) -> float:
    """Zamienia znacznik czasu SRT albo VTT na liczbę sekund od początku."""
    znormalizowany = znacznik.replace(",", ".")
    czesc_calkowita, _, milisekundy = znormalizowany.partition(".")
    skladniki = czesc_calkowita.split(":")
    if len(skladniki) == 3:
        godziny, minuty, sekundy = (int(skladnik) for skladnik in skladniki)
    else:
        godziny = 0
        minuty, sekundy = (int(skladnik) for skladnik in skladniki)
    return godziny * 3600 + minuty * 60 + sekundy + int(milisekundy or "0") / 1000
