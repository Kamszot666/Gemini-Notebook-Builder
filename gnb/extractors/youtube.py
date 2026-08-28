"""Zamiana napisów filmu na tekst nadający się do notatnika.

Sklejanie segmentów napisów w akapity jest logiką wspólną z plikami napisów
SRT i VTT, więc mieszka w `gnb.extractors.napisy_wspolne`. Ten moduł dodaje to,
co jest specyficzne dla YouTube: rozpoznanie i wycięcie stopki tłumaczy oraz
zebranie metadanych filmu.

Napisy tworzone ręcznie bywają zakończone albo poprzedzone stopką tłumaczy
społecznościowych, na przykład „Tłumaczenie: imię i nazwisko”. To nie jest
wypowiedź prelegenta, tylko informacja o pochodzeniu napisów, a doklejona do
pierwszego zdania zanieczyszcza materiał: model czytający bazę wiedzy uzna
nazwiska za treść wykładu. Stopka jest więc wycinana ze strumienia tekstu, ale
nie jest kasowana — trafia do metadanych źródła jako `atrybucja_napisow`,
ponieważ identyfikowalność źródeł stoi w hierarchii priorytetów wyżej niż wygoda.

Moduł nie interpretuje treści napisów. Tekst z serwisu jest danymi, nigdy
instrukcją.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury
from gnb.extractors.napisy_wspolne import zapisz_akapity, zbuduj_akapity
from gnb.ingestion.youtube import TYP_NAPISOW_AUTOMATYCZNE, SegmentNapisow, WynikYouTube

METODA_EKSTRAKCJI = "napisy_youtube"

# Liczba segmentów sprawdzanych na początku i na końcu transkrypcji pod kątem
# stopki tłumaczy. Stopka pojawia się na brzegach materiału, nigdy w środku,
# więc przeszukiwanie całości tylko mnożyłoby fałszywe trafienia.
LICZBA_SEGMENTOW_ATRYBUCJI = 4

KOMUNIKAT_NAPISY_BEZ_TRESCI = (
    "Napisy tego filmu nie zawierają mowy, a jedynie oznaczenia dźwięków albo puste "
    "wiersze, więc nie ma z czego zbudować tekstu. Źródło zostało pominięte."
)

# Wzorce stopki tłumaczy. Warianty polskie wymagają dwukropka, ponieważ samo
# słowo „tłumaczenie” bywa treścią wypowiedzi. Warianty angielskie są całymi
# zwrotami, więc dwukropek nie jest potrzebny.
_WZORCE_ATRYBUCJI = re.compile(
    r"^\s*(?:"
    r"tłumaczenie\s*:|"
    r"korekta\s*:|"
    r"napisy\s*:|"
    r"opracowanie\s*:|"
    r"translated\s+by|"
    r"reviewed\s+by|"
    r"subtitles\s+by|"
    r"captions\s+by"
    r")",
    re.IGNORECASE,
)


def zbuduj_dokument(
    wynik: WynikYouTube, *, znaczniki_czasu: bool = False
) -> DokumentWyekstrahowany:
    """Buduje dokument wyekstrahowany z napisów jednego filmu.

    Poziom pewności struktury jest niski, ponieważ transkrypcja mowy nie ma
    struktury dokumentu: nie ma w niej nagłówków, list ani tabel. Dzięki temu
    reguła z sekcji ósmej CLAUDE.md nigdy nie wygeneruje dla filmu wersji MD.
    """
    segmenty, atrybucja = usun_atrybucje(wynik.napisy.segmenty, wynik.napisy.typ)
    akapity = zbuduj_akapity(segmenty)
    tekst = zapisz_akapity(
        akapity,
        znaczniki_czasu=znaczniki_czasu,
        dlugosc_filmu_sekundy=wynik.metadane.dlugosc_sekundy,
    )
    metadane = _metadane_tekstowe(wynik)
    if atrybucja:
        metadane["atrybucja_napisow"] = atrybucja
    return DokumentWyekstrahowany(
        identyfikator_zrodla=wynik.identyfikator,
        tekst=tekst,
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
        metoda_ekstrakcji=METODA_EKSTRAKCJI,
        tytul=wynik.metadane.tytul,
        metadane=metadane,
    )


def usun_atrybucje(
    segmenty: Sequence[SegmentNapisow], typ_napisow: str
) -> tuple[tuple[SegmentNapisow, ...], str]:
    """Wycina stopkę tłumaczy z brzegów transkrypcji i zwraca ją osobno.

    Sprawdzane są wyłącznie skrajne segmenty, po kilka z każdej strony, ponieważ
    stopka pojawia się na początku albo na końcu materiału. Napisy automatyczne
    są pomijane, bo takich stopek nie zawierają, a ryzyko fałszywego trafienia
    byłoby w nich niepotrzebne.

    Segment, z którego po usunięciu stopki nic nie zostaje, znika, żeby nie
    tworzyć pustego akapitu. Zwracany napis zawiera pełny usunięty tekst, bez
    prób wydzielania z niego nazwisk, bo takie parsowanie byłoby zgadywaniem.
    """
    if typ_napisow == TYP_NAPISOW_AUTOMATYCZNE or not segmenty:
        return tuple(segmenty), ""

    do_sprawdzenia = _indeksy_brzegowe(len(segmenty))
    zachowane: list[SegmentNapisow] = []
    usuniete: list[str] = []

    for indeks, segment in enumerate(segmenty):
        if indeks not in do_sprawdzenia:
            zachowane.append(segment)
            continue

        pozostale_wiersze: list[str] = []
        for wiersz in segment.tekst.splitlines() or [segment.tekst]:
            if _WZORCE_ATRYBUCJI.match(wiersz):
                usuniete.append(wiersz.strip())
            else:
                pozostale_wiersze.append(wiersz)

        pozostalo = "\n".join(pozostale_wiersze).strip()
        if pozostalo:
            zachowane.append(
                SegmentNapisow(poczatek_sekundy=segment.poczatek_sekundy, tekst=pozostalo)
            )

    return tuple(zachowane), " ".join(usuniete)


def _indeksy_brzegowe(liczba_segmentow: int) -> set[int]:
    """Zwraca indeksy segmentów z początku i z końca transkrypcji."""
    zasieg = min(LICZBA_SEGMENTOW_ATRYBUCJI, liczba_segmentow)
    poczatek = set(range(zasieg))
    koniec = set(range(max(0, liczba_segmentow - zasieg), liczba_segmentow))
    return poczatek | koniec


def _metadane_tekstowe(wynik: WynikYouTube) -> dict[str, str]:
    """Zbiera metadane filmu w postaci nadającej się do zapisu w manifeście."""
    metadane: dict[str, str] = {
        "identyfikator_filmu": wynik.identyfikator,
        "adres_kanoniczny": wynik.adres_kanoniczny,
        "jezyk_napisow": wynik.napisy.jezyk,
        "typ_napisow": wynik.napisy.typ,
    }
    if wynik.napisy.metoda:
        metadane["metoda_pobrania_napisow"] = wynik.napisy.metoda
    if wynik.napisy.awaryjny_jezyk:
        metadane["jezyk_awaryjny"] = "tak"
    if wynik.metadane.tytul:
        metadane["tytul"] = wynik.metadane.tytul
    if wynik.metadane.kanal:
        metadane["kanal"] = wynik.metadane.kanal
    if wynik.metadane.dlugosc_sekundy is not None:
        metadane["dlugosc_sekundy"] = str(wynik.metadane.dlugosc_sekundy)
    if wynik.metadane.data_publikacji:
        metadane["data_publikacji"] = wynik.metadane.data_publikacji
    return metadane
