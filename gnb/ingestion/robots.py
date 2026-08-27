"""Odczyt pliku ``robots.txt`` i decyzja, czy wolno pobrać dany adres.

Sekcja szósta CLAUDE.md zabrania omijania zabezpieczeń technicznych i każe
domyślnie respektować ``robots.txt``. Ten moduł pobiera plik raz na każde
źródło, czyli na parę schematu i nazwy hosta, i przechowuje wynik przez czas
jednego uruchomienia.

Przyjęta polityka wobec odpowiedzi serwera:

1. Odpowiedź 200 oznacza wczytanie reguł i stosowanie się do nich.
2. Odpowiedź 401 albo 403 oznacza zakaz pobierania czegokolwiek z tej witryny.
   Serwis wprost odmawia dostępu do reguł, więc zgadywanie ich byłoby obchodzeniem
   zabezpieczenia.
3. Odpowiedź 404 i pozostałe odpowiedzi z rodziny 4xx oznaczają brak reguł, czyli
   zgodę na pobieranie. Tak działa powszechnie przyjęta interpretacja tego pliku.
4. Błąd sieci oraz odpowiedź 5xx również oznaczają zgodę. Chwilowa awaria serwera
   nie może zablokować pracy użytkownika na materiale, do którego ma prawo.

Moduł czyta też deklarację ``Crawl-delay``, jeżeli witryna ją podaje. Odstęp
z konfiguracji jest wtedy zwiększany do wartości żądanej przez serwis.
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx

NAZWA_PLIKU_ROBOTS = "/robots.txt"
_KODY_PELNEGO_ZAKAZU = (401, 403)


class KontrolerRobots:
    """Pyta plik ``robots.txt`` o zgodę na pobranie adresu, z pamięcią na czas pracy."""

    def __init__(self, klient: httpx.AsyncClient, nazwa_klienta: str) -> None:
        self._klient = klient
        self._nazwa_klienta = nazwa_klienta
        self._reguly: dict[str, RobotFileParser | None] = {}

    async def czy_wolno(self, adres: str) -> bool:
        """Zwraca prawdę, gdy reguły witryny pozwalają pobrać podany adres."""
        parser = await self._parser(adres)
        if parser is None:
            return True
        return parser.can_fetch(self._nazwa_klienta, adres)

    async def zadany_odstep(self, adres: str) -> float | None:
        """Zwraca odstęp między żądaniami żądany przez witrynę albo wartość pustą."""
        parser = await self._parser(adres)
        if parser is None:
            return None
        opoznienie = parser.crawl_delay(self._nazwa_klienta)
        return float(opoznienie) if opoznienie is not None else None

    async def _parser(self, adres: str) -> RobotFileParser | None:
        """Zwraca reguły dla źródła adresu, pobierając plik przy pierwszym pytaniu."""
        zrodlo = _zrodlo_adresu(adres)
        if zrodlo not in self._reguly:
            self._reguly[zrodlo] = await self._pobierz_reguly(zrodlo)
        return self._reguly[zrodlo]

    async def _pobierz_reguly(self, zrodlo: str) -> RobotFileParser | None:
        """Pobiera i interpretuje plik reguł dla podanego źródła."""
        parser = RobotFileParser()
        try:
            odpowiedz = await self._klient.get(zrodlo + NAZWA_PLIKU_ROBOTS)
        except httpx.HTTPError:
            return None

        if odpowiedz.status_code in _KODY_PELNEGO_ZAKAZU:
            parser.parse(["User-agent: *", "Disallow: /"])
            return parser
        if odpowiedz.status_code != httpx.codes.OK:
            return None

        parser.parse(odpowiedz.text.splitlines())
        return parser


def _zrodlo_adresu(adres: str) -> str:
    """Zwraca schemat i autorytet adresu, czyli miejsce, w którym leży plik reguł."""
    czesci = urlsplit(adres)
    return urlunsplit((czesci.scheme, czesci.netloc, "", "", ""))
