"""Planowanie plików wynikowych: podział źródeł zbyt dużych i łączenie małych.

Ten moduł działa zawsze po deduplikacji, zgodnie z sekcją ósmą CLAUDE.md. Nie
dotyka dysku i nie buduje nagłówków metadanych — decyduje wyłącznie, które źródła
trafią do którego pliku wynikowego i w jakiej postaci treści.

Dwie sytuacje z sekcji dziesiątej CLAUDE.md:

1. Pojedyncze źródło przekraczające limit jest dzielone na części na granicy
   jednostki strukturalnej. Każda część zachowuje ten sam identyfikator źródła
   i dostaje numer wraz z liczbą wszystkich części.
2. Małe źródła jednej grupy tematycznej są łączone w jeden plik, żeby oszczędzać
   sloty notatnika. Łączenie następuje wyłącznie w obrębie grupy nadanej przez
   użytkownika, nigdy przypadkowo. Gdy dokładane źródło przekroczyłoby limit
   słów albo limit rozmiaru, bieżący plik grupy jest zamykany, a źródło zaczyna
   kolejny plik tej samej grupy, numerowany jak część.

Źródło należące do grupy, ale samo przekraczające limit, jest dzielone na własne
pliki-części i nie jest łączone z pozostałymi. Łączenie dotyczy z definicji
źródeł małych.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gnb.packing.limity import LimityPakowania, miesci_sie
from gnb.packing.podzial import podziel_na_czesci

# Łącznik treści dwóch źródeł w jednym pliku grupy. Pusty wiersz między
# fragmentami odpowiada odstępowi między akapitami w znormalizowanym tekście,
# a nagłówek metadanych każdego fragmentu i tak jest wyraźną granicą.
_LACZNIK_FRAGMENTOW = "\n\n"


@dataclass(frozen=True, slots=True)
class ZrodloDoPakowania:
    """Znormalizowane źródło zgłoszone do pakowania.

    Pole `tekst` to znormalizowana treść bez nagłówka metadanych. Pole
    `grupa` jest nazwą grupy tematycznej nadaną przez użytkownika albo wartością
    pustą, gdy źródło ma trafić do osobnego pliku.
    """

    identyfikator: str
    tekst: str
    grupa: str | None = None


@dataclass(frozen=True, slots=True)
class FragmentPliku:
    """Jeden fragment pliku wynikowego: identyfikator źródła i przypadająca nań treść.

    Dla źródła niepodzielonego treść jest całą treścią źródła. Dla części źródła
    podzielonego treść jest treścią tej jednej części.
    """

    identyfikator: str
    tekst: str


@dataclass(frozen=True, slots=True)
class PlanPliku:
    """Opis jednego pliku wynikowego do zapisania.

    `numer_czesci` i `liczba_czesci` mówią, którą z ilu części dla tej samej
    podstawy nazwy jest ten plik. Dla pliku, który jest jedyny dla swojej
    podstawy, oba pola mają wartość jeden, a `czy_wieloczesciowy` jest fałszem.
    `czy_grupa` mówi, czy nazwa pliku ma powstać z nazwy grupy, czy z nazwy
    pojedynczego źródła.
    """

    fragmenty: tuple[FragmentPliku, ...]
    czy_grupa: bool
    grupa: str | None = None
    numer_czesci: int = 1
    liczba_czesci: int = 1
    ostrzezenia: tuple[str, ...] = ()

    @property
    def czy_wieloczesciowy(self) -> bool:
        """Prawda, gdy dla tej podstawy nazwy powstaje więcej niż jeden plik."""
        return self.liczba_czesci > 1


def rozplanuj_pojedyncze_zrodlo(
    identyfikator: str, tekst: str, limity: LimityPakowania
) -> list[PlanPliku]:
    """Planuje pliki dla źródła spoza grupy: jeden plik albo kilka części."""
    wynik = podziel_na_czesci(tekst, limity)
    if len(wynik.czesci) == 1:
        return [
            PlanPliku(
                fragmenty=(FragmentPliku(identyfikator, wynik.czesci[0]),),
                czy_grupa=False,
            )
        ]
    return _plany_czesci(identyfikator, wynik.czesci, tuple(wynik.ostrzezenia), czy_grupa=False)


def rozplanuj_grupe(
    nazwa_grupy: str,
    zrodla: Sequence[ZrodloDoPakowania],
    limity: LimityPakowania,
) -> list[PlanPliku]:
    """Planuje pliki dla jednej grupy: części źródeł zbyt dużych plus łączenie małych.

    Źródła są przetwarzane w stałej kolejności rosnących identyfikatorów, więc
    wynik jest powtarzalny między uruchomieniami. Źródło samo przekraczające
    limit trafia do własnych plików-części. Pozostałe źródła są dokładane po
    kolei do bieżącego pliku grupy, a przekroczenie któregokolwiek limitu
    zamyka plik i otwiera następny.
    """
    uporzadkowane = sorted(zrodla, key=lambda zrodlo: zrodlo.identyfikator)
    plany: list[PlanPliku] = []
    male: list[ZrodloDoPakowania] = []

    for zrodlo in uporzadkowane:
        wynik = podziel_na_czesci(zrodlo.tekst, limity)
        if len(wynik.czesci) == 1:
            male.append(zrodlo)
            continue
        plany.extend(
            _plany_czesci(
                zrodlo.identyfikator, wynik.czesci, tuple(wynik.ostrzezenia), czy_grupa=False
            )
        )

    plany.extend(_polacz_male(nazwa_grupy, male, limity))
    return plany


def _polacz_male(
    nazwa_grupy: str,
    zrodla: Sequence[ZrodloDoPakowania],
    limity: LimityPakowania,
) -> list[PlanPliku]:
    """Rozkłada małe źródła grupy na jak najmniejszą liczbę wspólnych plików."""
    if not zrodla:
        return []

    kosze: list[list[ZrodloDoPakowania]] = []
    biezacy: list[ZrodloDoPakowania] = []
    for zrodlo in zrodla:
        proba = [*biezacy, zrodlo]
        if biezacy and not _kosz_sie_miesci(proba, limity):
            kosze.append(biezacy)
            biezacy = [zrodlo]
        else:
            biezacy = proba
    if biezacy:
        kosze.append(biezacy)

    liczba_koszy = len(kosze)
    return [
        PlanPliku(
            fragmenty=tuple(FragmentPliku(z.identyfikator, z.tekst) for z in kosz),
            czy_grupa=True,
            grupa=nazwa_grupy,
            numer_czesci=numer,
            liczba_czesci=liczba_koszy,
        )
        for numer, kosz in enumerate(kosze, start=1)
    ]


def _kosz_sie_miesci(zrodla: Sequence[ZrodloDoPakowania], limity: LimityPakowania) -> bool:
    """Prawda, gdy złączona treść koszyka mieści się w limicie słów i rozmiaru.

    Limity sprawdzane są na samej treści, bez nagłówków metadanych, zgodnie
    z regułą z modułu `gnb.output.naglowek_metadanych`. Treść koszyka to treści
    źródeł złączone tym samym łącznikiem, którym powstaje plik grupy.
    """
    zlaczona = _LACZNIK_FRAGMENTOW.join(zrodlo.tekst for zrodlo in zrodla)
    return miesci_sie(zlaczona, limity)


def _plany_czesci(
    identyfikator: str,
    czesci: Sequence[str],
    ostrzezenia: tuple[str, ...],
    *,
    czy_grupa: bool,
) -> list[PlanPliku]:
    """Buduje po jednym planie pliku na każdą część podzielonego źródła."""
    liczba = len(czesci)
    return [
        PlanPliku(
            fragmenty=(FragmentPliku(identyfikator, czesc),),
            czy_grupa=czy_grupa,
            numer_czesci=numer,
            liczba_czesci=liczba,
            ostrzezenia=ostrzezenia if numer == 1 else (),
        )
        for numer, czesc in enumerate(czesci, start=1)
    ]
