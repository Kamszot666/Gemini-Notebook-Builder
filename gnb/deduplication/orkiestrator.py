"""Wieloetapowa deduplikacja zbioru źródeł i audytowalne decyzje o duplikatach.

Etapy są uruchamiane w kolejności z sekcji szesnastej CLAUDE.md: hash treści po
normalizacji, porównanie po usunięciu różnic kosmetycznych, podobieństwo
klasyczne SimHash lub porównanie sekwencyjne krótkich tekstów. Każdy etap można
wyłączyć w ustawieniach. Etap embeddingów lokalnych nie jest tutaj realizowany —
jest domyślnie wyłączony i pozostaje poza zakresem etapu piątego.

Źródła są porównywane w stałej kolejności rosnących identyfikatorów, więc wynik
deduplikacji jest powtarzalny między uruchomieniami. Pierwsze źródło z grupy
podobnych zostaje reprezentantem, a kolejne są z nim zestawiane.

Pewny duplikat, czyli identyczna treść albo podobieństwo powyżej progu, nie
wchodzi do wyników i dostaje status „duplikat”. Podobieństwo w paśmie niższym
niczego nie usuwa: oba źródła zostają, a para jest oznaczana do rozstrzygnięcia
przez człowieka. Pole zachowanych fragmentów unikalnych pozostaje w tym zakresie
etapu zawsze puste, ponieważ pełne oznaczenie duplikatu zachodzi tylko przy
wyniku skrajnym, przy którym z założenia nie ma treści unikalnej do ocalenia.
Szersze omówienie jest w sekcji osiemnastej e CLAUDE.md.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from gnb.core.model import DecyzjaDeduplikacji
from gnb.core.stale import WynikDeduplikacji
from gnb.deduplication.hasze import hash_tresci, klucz_kosmetyczny
from gnb.deduplication.simhash import (
    DOMYSLNY_ROZMIAR_SHINGLA,
    podobienstwo_sekwencyjne,
    podobienstwo_simhash,
    simhash_tekstu,
)

DOMYSLNY_PROG_DUPLIKATU = 0.90
DOMYSLNY_PROG_DO_PRZEGLADU = 0.75
DOMYSLNY_PROG_SLOW_KROTKIEGO_TEKSTU = 60

METODA_HASH = "hash treści"
METODA_KOSMETYCZNA = "porównanie kosmetyczne"
METODA_SIMHASH = "SimHash"
METODA_SEKWENCYJNA = "porównanie sekwencyjne"

_UZASADNIENIE_HASH = "Znormalizowany tekst obu źródeł jest identyczny."
_UZASADNIENIE_KOSMETYCZNA = (
    "Teksty różnią się wyłącznie interpunkcją, odstępami albo wielkością liter."
)


@dataclass(frozen=True, slots=True)
class ZrodloDoDeduplikacji:
    """Znormalizowane źródło zgłoszone do porównania z pozostałymi."""

    identyfikator: str
    tekst: str
    liczba_slow: int


@dataclass(frozen=True, slots=True)
class UstawieniaDeduplikacji:
    """Włączenie i progi kolejnych etapów deduplikacji."""

    etap_hash: bool = True
    etap_kosmetyczny: bool = True
    etap_podobienstwa: bool = True
    prog_duplikatu: float = DOMYSLNY_PROG_DUPLIKATU
    prog_do_przegladu: float = DOMYSLNY_PROG_DO_PRZEGLADU
    rozmiar_shingla: int = DOMYSLNY_ROZMIAR_SHINGLA
    prog_slow_krotkiego_tekstu: int = DOMYSLNY_PROG_SLOW_KROTKIEGO_TEKSTU


@dataclass(frozen=True, slots=True)
class WynikDeduplikacjiZbioru:
    """Zbiór decyzji deduplikacji wraz z podziałem źródeł na kategorie.

    `identyfikatory_duplikatow` to źródła do usunięcia z wyników, ze statusem
    „duplikat”. `identyfikatory_do_przegladu` to źródła zachowane, ale oznaczone
    do rozstrzygnięcia przez człowieka.
    """

    decyzje: tuple[DecyzjaDeduplikacji, ...] = ()
    identyfikatory_duplikatow: frozenset[str] = field(default_factory=frozenset)
    identyfikatory_do_przegladu: frozenset[str] = field(default_factory=frozenset)


@dataclass(slots=True)
class _Profil:
    """Odcisk jednego źródła policzony raz i wykorzystywany przy każdym porównaniu."""

    identyfikator: str
    tekst: str
    liczba_slow: int
    hash_tresci: str
    klucz_kosmetyczny: str
    simhash: int


def deduplikuj(
    zrodla: Sequence[ZrodloDoDeduplikacji],
    ustawienia: UstawieniaDeduplikacji | None = None,
) -> WynikDeduplikacjiZbioru:
    """Porównuje wszystkie źródła i zwraca komplet decyzji deduplikacji.

    Wynik jest deterministyczny: źródła są przetwarzane w kolejności rosnących
    identyfikatorów, a pierwsze źródło z grupy podobnych zostaje reprezentantem.
    """
    ustawienia = ustawienia or UstawieniaDeduplikacji()
    uporzadkowane = sorted(zrodla, key=lambda zrodlo: zrodlo.identyfikator)

    reprezentanci: list[_Profil] = []
    decyzje: list[DecyzjaDeduplikacji] = []
    duplikaty: set[str] = set()
    do_przegladu: set[str] = set()

    for zrodlo in uporzadkowane:
        profil = _zbuduj_profil(zrodlo, ustawienia)
        trafienie = _najlepsze_trafienie(reprezentanci, profil, ustawienia)
        if trafienie is None:
            reprezentanci.append(profil)
            continue

        decyzja, czy_pewny = trafienie
        decyzje.append(decyzja)
        if czy_pewny:
            duplikaty.add(zrodlo.identyfikator)
        else:
            do_przegladu.add(zrodlo.identyfikator)
            reprezentanci.append(profil)

    return WynikDeduplikacjiZbioru(
        decyzje=tuple(decyzje),
        identyfikatory_duplikatow=frozenset(duplikaty),
        identyfikatory_do_przegladu=frozenset(do_przegladu),
    )


def _zbuduj_profil(zrodlo: ZrodloDoDeduplikacji, ustawienia: UstawieniaDeduplikacji) -> _Profil:
    return _Profil(
        identyfikator=zrodlo.identyfikator,
        tekst=zrodlo.tekst,
        liczba_slow=zrodlo.liczba_slow,
        hash_tresci=hash_tresci(zrodlo.tekst),
        klucz_kosmetyczny=klucz_kosmetyczny(zrodlo.tekst),
        simhash=(
            simhash_tekstu(zrodlo.tekst, rozmiar_shingla=ustawienia.rozmiar_shingla)
            if ustawienia.etap_podobienstwa
            else 0
        ),
    )


def _najlepsze_trafienie(
    reprezentanci: Sequence[_Profil],
    profil: _Profil,
    ustawienia: UstawieniaDeduplikacji,
) -> tuple[DecyzjaDeduplikacji, bool] | None:
    """Zwraca decyzję dla najlepszego dopasowania profilu do reprezentantów.

    Pewne trafienie kończy szukanie od razu. Trafienie słabsze, czyli para do
    ręcznego rozstrzygnięcia, jest zapamiętywane, a szukanie trwa dalej, na
    wypadek gdyby dalszy reprezentant okazał się pewnym duplikatem. Drugi
    element krotki mówi, czy trafienie jest pewne.
    """
    slabe: DecyzjaDeduplikacji | None = None
    for reprezentant in reprezentanci:
        decyzja = _porownaj(reprezentant, profil, ustawienia)
        if decyzja is None:
            continue
        if decyzja.decyzja is WynikDeduplikacji.DUPLIKAT:
            return decyzja, True
        if slabe is None or decyzja.wynik_podobienstwa > slabe.wynik_podobienstwa:
            slabe = decyzja
    if slabe is None:
        return None
    return slabe, False


def _porownaj(
    reprezentant: _Profil,
    profil: _Profil,
    ustawienia: UstawieniaDeduplikacji,
) -> DecyzjaDeduplikacji | None:
    """Zestawia dwa profile kolejnymi włączonymi etapami deduplikacji."""
    if ustawienia.etap_hash and reprezentant.hash_tresci == profil.hash_tresci:
        return _decyzja(
            reprezentant, profil, WynikDeduplikacji.DUPLIKAT, 1.0, METODA_HASH, _UZASADNIENIE_HASH
        )

    if ustawienia.etap_kosmetyczny and reprezentant.klucz_kosmetyczny == profil.klucz_kosmetyczny:
        return _decyzja(
            reprezentant,
            profil,
            WynikDeduplikacji.DUPLIKAT,
            1.0,
            METODA_KOSMETYCZNA,
            _UZASADNIENIE_KOSMETYCZNA,
        )

    if not ustawienia.etap_podobienstwa:
        return None

    wynik, metoda = _podobienstwo_klasyczne(reprezentant, profil, ustawienia)
    if wynik >= ustawienia.prog_duplikatu:
        return _decyzja(
            reprezentant,
            profil,
            WynikDeduplikacji.DUPLIKAT,
            wynik,
            metoda,
            f"Podobieństwo {wynik:.2f} osiągnęło próg pewnego duplikatu "
            f"{ustawienia.prog_duplikatu:.2f}.",
        )
    if wynik >= ustawienia.prog_do_przegladu:
        return _decyzja(
            reprezentant,
            profil,
            WynikDeduplikacji.WYMAGA_DECYZJI_UZYTKOWNIKA,
            wynik,
            metoda,
            f"Podobieństwo {wynik:.2f} mieści się między progiem do ręcznego "
            f"rozstrzygnięcia {ustawienia.prog_do_przegladu:.2f} a progiem pewnego "
            f"duplikatu {ustawienia.prog_duplikatu:.2f}. Oba źródła zostają w wynikach.",
        )
    return None


def _podobienstwo_klasyczne(
    reprezentant: _Profil,
    profil: _Profil,
    ustawienia: UstawieniaDeduplikacji,
) -> tuple[float, str]:
    """Liczy podobieństwo dwóch tekstów, wybierając metodę po długości krótszego.

    Tekst krótszy niż próg słów krótkiego tekstu jest porównywany sekwencyjnie,
    ponieważ SimHash na kilku shinglach ma zbyt duży rozrzut. Dłuższe teksty
    porównuje SimHash, znacznie tańszy obliczeniowo od dopasowania sekwencyjnego.
    """
    krotszy = min(reprezentant.liczba_slow, profil.liczba_slow)
    if krotszy < ustawienia.prog_slow_krotkiego_tekstu:
        return podobienstwo_sekwencyjne(reprezentant.tekst, profil.tekst), METODA_SEKWENCYJNA
    return podobienstwo_simhash(reprezentant.simhash, profil.simhash), METODA_SIMHASH


def _decyzja(
    reprezentant: _Profil,
    profil: _Profil,
    wynik: WynikDeduplikacji,
    podobienstwo: float,
    metoda: str,
    uzasadnienie: str,
) -> DecyzjaDeduplikacji:
    return DecyzjaDeduplikacji(
        identyfikator_zrodla_glownego=reprezentant.identyfikator,
        identyfikator_duplikatu=profil.identyfikator,
        metoda=metoda,
        wynik_podobienstwa=round(podobienstwo, 4),
        decyzja=wynik,
        uzasadnienie=uzasadnienie,
        zachowane_fragmenty_unikalne=[],
    )
