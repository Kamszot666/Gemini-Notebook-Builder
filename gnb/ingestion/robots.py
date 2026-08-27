"""Odczyt pliku ``robots.txt`` i decyzja, czy wolno pobrać dany adres.

Sekcja szósta CLAUDE.md zabrania omijania zabezpieczeń technicznych i każe
domyślnie respektować ``robots.txt``. Ten moduł pobiera plik raz na każde
źródło, czyli na parę schematu i nazwy hosta, i przechowuje wynik przez czas
jednego uruchomienia.

Polityka wobec odpowiedzi serwera jest zgodna z RFC 9309, sekcja 2.3.1:

1. Odpowiedź z rodziny 2xx oznacza wczytanie reguł i stosowanie się do nich.
2. Odpowiedź z rodziny 4xx, w tym 401 i 403, oznacza, że plik reguł jest
   niedostępny, a więc wolno sięgać po zasoby serwera. Ma to również praktyczne
   znaczenie: witryny za zaporą aplikacyjną często odpowiadają kodem 403 na sam
   plik ``robots.txt`` przy nietypowym kliencie, mimo że artykuł jest publicznie
   dostępny w przeglądarce.
3. Odpowiedź z rodziny 5xx oraz błąd sieci oznaczają, że plik reguł jest
   nieokreślony, a wtedy obowiązuje pełny zakaz. Taka sytuacja jest najpierw
   traktowana jako błąd przejściowy i ponawiana, a dopiero po wyczerpaniu prób
   źródło zostaje pominięte z czytelnym komunikatem.

Moduł czyta też deklarację ``Crawl-delay``, jeżeli witryna ją podaje. Odstęp
z konfiguracji jest wtedy zwiększany do wartości żądanej przez serwis.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

from gnb.core.wyjatki import BladPrzejsciowy

NAZWA_PLIKU_ROBOTS = "/robots.txt"

KOMUNIKAT_REGULY_NIEDOSTEPNE = (
    "Nie udało się pobrać pliku robots.txt tej witryny, więc jej reguły są "
    "nieokreślone. Zgodnie z RFC 9309 obowiązuje wtedy pełny zakaz pobierania "
    "i źródło zostało pominięte. Spróbuj ponownie, gdy serwis zacznie odpowiadać."
)
KOMUNIKAT_ZAKAZ_REGUL = (
    "Plik robots.txt tej witryny nie pozwala pobrać tego adresu. "
    "Źródło zostało pominięte, ponieważ nie omijamy zabezpieczeń."
)


class DecyzjaRobots(Enum):
    """Rozstrzygnięcie reguł witryny dla jednego adresu."""

    DOZWOLONE = auto()
    ZABRONIONE = auto()
    NIEDOSTEPNE = auto()


@dataclass(slots=True)
class _StanZrodla:
    """Zapamiętany wynik odczytu reguł dla jednego schematu i hosta."""

    parser: RobotFileParser | None = None
    niedostepne: bool = False


class KontrolerRobots:
    """Pyta plik ``robots.txt`` o zgodę na pobranie adresu, z pamięcią na czas pracy."""

    def __init__(self, klient: httpx.AsyncClient, nazwa_klienta: str) -> None:
        self._klient = klient
        self._nazwa_klienta = nazwa_klienta
        self._stany: dict[str, _StanZrodla] = {}
        self._blokady: dict[str, asyncio.Lock] = {}

    async def decyzja(self, adres: str) -> DecyzjaRobots:
        """Zwraca rozstrzygnięcie reguł witryny dla podanego adresu.

        Zgłasza `BladPrzejsciowy`, gdy pliku reguł nie da się w tej chwili
        pobrać, żeby wywołujący mógł ponowić próbę zgodnie z własną polityką
        odstępów. Po wyczerpaniu prób wywołujący zapisuje ten stan metodą
        `oznacz_niedostepne`, a kolejne adresy z tej samej witryny dostają
        rozstrzygnięcie `NIEDOSTEPNE` bez ponownego pytania serwera.
        """
        stan = await self._stan(adres)
        if stan.niedostepne:
            return DecyzjaRobots.NIEDOSTEPNE
        if stan.parser is None:
            return DecyzjaRobots.DOZWOLONE
        if stan.parser.can_fetch(self._nazwa_klienta, adres):
            return DecyzjaRobots.DOZWOLONE
        return DecyzjaRobots.ZABRONIONE

    def oznacz_niedostepne(self, adres: str) -> None:
        """Zapamiętuje, że reguł witryny nie udało się pobrać mimo ponowień."""
        self._stany[_zrodlo_adresu(adres)] = _StanZrodla(niedostepne=True)

    async def zadany_odstep(self, adres: str) -> float | None:
        """Zwraca odstęp między żądaniami żądany przez witrynę albo wartość pustą."""
        stan = self._stany.get(_zrodlo_adresu(adres))
        if stan is None or stan.parser is None:
            return None
        opoznienie = stan.parser.crawl_delay(self._nazwa_klienta)
        return float(opoznienie) if opoznienie is not None else None

    async def _stan(self, adres: str) -> _StanZrodla:
        """Zwraca zapamiętany stan reguł, pobierając plik przy pierwszym pytaniu.

        Odczyt jest chroniony blokadą na źródło, więc równoległe pobieranie wielu
        adresów z jednego serwisu pyta o plik reguł tylko raz. Bez tej blokady
        każdy adres wysyłałby własne żądanie, zanim pierwsza odpowiedź zdążyłaby
        trafić do pamięci.
        """
        zrodlo = _zrodlo_adresu(adres)
        stan = self._stany.get(zrodlo)
        if stan is not None:
            return stan

        async with self._blokada(zrodlo):
            stan = self._stany.get(zrodlo)
            if stan is None:
                stan = await self._pobierz_reguly(zrodlo)
                self._stany[zrodlo] = stan
            return stan

    def _blokada(self, zrodlo: str) -> asyncio.Lock:
        """Zwraca blokadę odczytu reguł dla danego źródła, tworząc ją przy pierwszym użyciu."""
        blokada = self._blokady.get(zrodlo)
        if blokada is None:
            blokada = asyncio.Lock()
            self._blokady[zrodlo] = blokada
        return blokada

    async def _pobierz_reguly(self, zrodlo: str) -> _StanZrodla:
        """Pobiera i interpretuje plik reguł dla podanego źródła."""
        try:
            odpowiedz = await self._klient.get(zrodlo + NAZWA_PLIKU_ROBOTS)
        except httpx.HTTPError as blad:
            raise BladPrzejsciowy(
                f"Nie udało się pobrać pliku robots.txt witryny {zrodlo}: {blad}"
            ) from blad

        if odpowiedz.status_code >= 500:
            raise BladPrzejsciowy(
                f"Witryna {zrodlo} odpowiedziała błędem {odpowiedz.status_code} "
                "przy pobieraniu pliku robots.txt."
            )
        if odpowiedz.status_code >= 400:
            return _StanZrodla()

        parser = RobotFileParser()
        parser.parse(odpowiedz.text.splitlines())
        return _StanZrodla(parser=parser)


def _zrodlo_adresu(adres: str) -> str:
    """Zwraca schemat i autorytet adresu, czyli miejsce, w którym leży plik reguł."""
    czesci = urlsplit(adres)
    return urlunsplit((czesci.scheme, czesci.netloc, "", "", ""))
