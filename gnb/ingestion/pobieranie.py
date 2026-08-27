"""Asynchroniczne pobieranie stron internetowych z ponowieniami i kulturą wobec serwera.

Moduł realizuje wymagania sekcji siódmej i piętnastej CLAUDE.md: każde żądanie
ma limit czasu, ograniczoną liczbę ponowień i rosnący odstęp między próbami,
współbieżność jest ograniczona do kilku połączeń na domenę, a między żądaniami
do tej samej domeny zachowywany jest odstęp. Klient przedstawia się nazwą
wskazującą projekt i domyślnie respektuje plik ``robots.txt``.

Podział błędów jest zgodny z taksonomią z sekcji siódmej. Przekroczony limit
czasu, zerwane połączenie, odpowiedzi z rodziny 5xx oraz odpowiedź 429 to
`BladPrzejsciowy` i podlegają ponowieniu. Pozostałe odpowiedzi z rodziny 4xx to
`BladTrwaly` i nie są ponawiane, bo powtórzenie żądania niczego nie zmieni.

Osobno traktowany jest błąd certyfikatu TLS. Jest to `BladTrwaly`, ponieważ
niezaufany certyfikat nie naprawi się przy kolejnej próbie, a ponawianie tylko
wydłuża pracę. Komunikat podpowiada realne przyczyny: podsłuchiwanie ruchu przez
program antywirusowy albo serwer pośredniczący, przeterminowany certyfikat
serwisu oraz błędnie ustawiony zegar systemowy.

Trzy sytuacje nie są błędami, tylko świadomym pominięciem źródła i są zwracane
jako `PominietePobranie`: zakaz w pliku ``robots.txt``, zasób, który nie jest
stroną HTML, oraz zasób przekraczający bezpieczny limit rozmiaru.

Pamięć podręczna jest opcjonalna. Gdy jest podana, świeży wpis jest używany bez
sięgania do sieci, a wpis nieświeży służy do zapytania warunkowego z nagłówkami
``If-None-Match`` oraz ``If-Modified-Since``. Odpowiedź 304 oznacza, że zapisana
treść jest nadal aktualna.

Treść pobranej strony jest danymi, nigdy instrukcją. Moduł nie interpretuje
zawartości i nie wykonuje niczego, co w niej znajdzie.
"""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from urllib.parse import urlsplit

import httpx

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.wyjatki import BladGnb, BladPrzejsciowy, BladTrwaly
from gnb.ingestion.robots import KontrolerRobots
from gnb.persistence.cache import PamiecPodreczna, WpisCache, teraz_utc

TYPY_ZAWARTOSCI_HTML = ("text/html", "application/xhtml+xml")
BAJTOW_W_MEGABAJCIE = 1024 * 1024
_ROZMIAR_FRAGMENTU = 65536
_KOD_NIEZMIENIONE = 304
_KOD_ZA_DUZO_ZADAN = 429


class BladZaDuzoZadan(BladPrzejsciowy):
    """Serwer prosi o zwolnienie tempa. Niesie odstęp podany w nagłówku Retry-After.

    Jest to zwykły błąd przejściowy, więc reszta aplikacji nie musi go
    rozróżniać. Osobna klasa istnieje tylko po to, żeby przekazać do mechanizmu
    ponowień odstęp żądany przez serwer, bez zmiany wspólnej taksonomii wyjątków
    z sekcji siódmej CLAUDE.md.
    """

    def __init__(
        self,
        komunikat: str,
        identyfikator_zrodla: str | None = None,
        *,
        odstep_sekundy: float | None = None,
    ) -> None:
        super().__init__(komunikat, identyfikator_zrodla)
        self.odstep_sekundy = odstep_sekundy


@dataclass(frozen=True, slots=True)
class UstawieniaPobierania:
    """Ustawienia sieciowe wyjęte z konfiguracji, żeby moduł nie zależał od jej kształtu."""

    nazwa_klienta: str
    limit_czasu_sekundy: float
    liczba_ponowien: int
    podstawa_odstepu_sekundy: float
    maksymalny_odstep_sekundy: float
    odstep_miedzy_zadaniami_sekundy: float
    polaczenia_na_domene: int
    respektuj_robots: bool
    maksymalny_rozmiar_pobrania_mb: int
    uzywaj_cache: bool
    maksymalny_wiek_cache_dni: int

    @classmethod
    def z_konfiguracji(cls, konfiguracja: Konfiguracja) -> UstawieniaPobierania:
        """Buduje ustawienia pobierania z pełnej konfiguracji aplikacji."""
        return cls(
            nazwa_klienta=konfiguracja.nazwa_klienta,
            limit_czasu_sekundy=konfiguracja.limit_czasu_sekundy,
            liczba_ponowien=konfiguracja.liczba_ponowien,
            podstawa_odstepu_sekundy=konfiguracja.podstawa_odstepu_sekundy,
            maksymalny_odstep_sekundy=konfiguracja.maksymalny_odstep_sekundy,
            odstep_miedzy_zadaniami_sekundy=konfiguracja.odstep_miedzy_zadaniami_sekundy,
            polaczenia_na_domene=konfiguracja.polaczenia_na_domene,
            respektuj_robots=konfiguracja.respektuj_robots,
            maksymalny_rozmiar_pobrania_mb=konfiguracja.maksymalny_rozmiar_pobrania_mb,
            uzywaj_cache=konfiguracja.uzywaj_cache,
            maksymalny_wiek_cache_dni=konfiguracja.maksymalny_wiek_cache_dni,
        )


@dataclass(frozen=True, slots=True)
class OdpowiedzPobrania:
    """Pobrany zasób wraz z danymi potrzebnymi do ponownej ekstrakcji i do manifestu."""

    adres_zadany: str
    adres_koncowy: str
    kod_odpowiedzi: int
    tresc: bytes
    typ_zawartosci: str
    deklarowane_kodowanie: str
    etag: str | None = None
    last_modified: str | None = None
    z_pamieci_podrecznej: bool = False


@dataclass(frozen=True, slots=True)
class PominietePobranie:
    """Zasób świadomie pominięty, z powodem gotowym do pokazania użytkownikowi."""

    adres: str
    powod: str


@dataclass(frozen=True, slots=True)
class Zadanie:
    """Jeden adres do pobrania: postać wysyłana do serwera i klucz tożsamości."""

    adres_pobierania: str
    klucz_kanoniczny: str


WynikPobrania = OdpowiedzPobrania | PominietePobranie


@dataclass(slots=True)
class _StanDomeny:
    """Stan kolejki jednej domeny: dopuszczalna współbieżność i moment następnego żądania."""

    semafor: asyncio.Semaphore
    blokada: asyncio.Lock = field(default_factory=asyncio.Lock)
    nastepny_dozwolony: float = 0.0


class Pobieracz:
    """Klient pobierający strony, z ponowieniami, limitami na domenę i pamięcią podręczną.

    Obiekt jest asynchronicznym menedżerem kontekstu. Wejście w blok ``async
    with`` otwiera połączenie HTTP, a wyjście je zamyka.

    Argumenty `transport`, `usypiacz`, `zegar_monotoniczny` i `zegar_utc` służą
    testom. Pozwalają sprawdzić ponowienia, odstępy i zapytania warunkowe bez
    sieci i bez rzeczywistego czekania.
    """

    def __init__(
        self,
        ustawienia: UstawieniaPobierania,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        pamiec: PamiecPodreczna | None = None,
        usypiacz: Callable[[float], Awaitable[None]] | None = None,
        zegar_monotoniczny: Callable[[], float] | None = None,
        zegar_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._ustawienia = ustawienia
        self._transport = transport
        self._pamiec = pamiec if ustawienia.uzywaj_cache else None
        self._usypiacz = usypiacz if usypiacz is not None else asyncio.sleep
        self._zegar = zegar_monotoniczny if zegar_monotoniczny is not None else time.monotonic
        self._zegar_utc = zegar_utc if zegar_utc is not None else teraz_utc
        self._klient: httpx.AsyncClient | None = None
        self._robots: KontrolerRobots | None = None
        self._domeny: dict[str, _StanDomeny] = {}

    async def __aenter__(self) -> Pobieracz:
        self._klient = httpx.AsyncClient(
            headers={"User-Agent": self._ustawienia.nazwa_klienta},
            timeout=self._ustawienia.limit_czasu_sekundy,
            follow_redirects=True,
            transport=self._transport,
        )
        self._robots = KontrolerRobots(self._klient, self._ustawienia.nazwa_klienta)
        return self

    async def __aexit__(
        self,
        typ_wyjatku: type[BaseException] | None,
        wartosc_wyjatku: BaseException | None,
        slad: TracebackType | None,
    ) -> None:
        if self._klient is not None:
            await self._klient.aclose()
            self._klient = None
        self._robots = None

    async def pobierz_wiele(self, zadania: Sequence[Zadanie]) -> list[WynikPobrania | BladGnb]:
        """Pobiera wiele adresów równolegle, z zachowaniem limitów na domenę.

        Wynik ma tę samą kolejność co lista zadań. Błąd jednego adresu jest
        zwracany jako wartość, a nie zgłaszany, ponieważ jedno niedziałające
        źródło nie może zatrzymać całej pracy.
        """
        wyniki = await asyncio.gather(*(self._pobierz_bez_wyjatku(zadanie) for zadanie in zadania))
        return list(wyniki)

    async def pobierz(self, zadanie: Zadanie) -> WynikPobrania:
        """Pobiera jeden adres, korzystając z pamięci podręcznej i ponowień."""
        wpis = self._pamiec.odczytaj(zadanie.klucz_kanoniczny) if self._pamiec else None
        teraz = self._zegar_utc()
        if wpis is not None and wpis.czy_swiezy(self._ustawienia.maksymalny_wiek_cache_dni, teraz):
            return _z_pamieci(zadanie, wpis)

        if self._ustawienia.respektuj_robots:
            pominiecie = await self._sprawdz_robots(zadanie.adres_pobierania)
            if pominiecie is not None:
                return pominiecie

        return await self._pobierz_z_ponowieniami(zadanie, wpis)

    async def _pobierz_bez_wyjatku(self, zadanie: Zadanie) -> WynikPobrania | BladGnb:
        """Zwraca wynik pobrania albo błąd projektu jako wartość."""
        try:
            return await self.pobierz(zadanie)
        except BladGnb as blad:
            return blad

    async def _sprawdz_robots(self, adres: str) -> PominietePobranie | None:
        """Zwraca pominięcie, gdy reguły witryny zabraniają pobrania adresu."""
        robots = self._wymagany_kontroler_robots()
        if await robots.czy_wolno(adres):
            return None
        return PominietePobranie(
            adres=adres,
            powod=(
                "Plik robots.txt tej witryny nie pozwala pobrać tego adresu. "
                "Źródło zostało pominięte, ponieważ nie omijamy zabezpieczeń."
            ),
        )

    async def _pobierz_z_ponowieniami(
        self, zadanie: Zadanie, wpis: WpisCache | None
    ) -> WynikPobrania:
        """Wykonuje żądanie, ponawiając je przy błędach przejściowych."""
        ostatni_blad: BladPrzejsciowy | None = None
        for numer_proby in range(self._ustawienia.liczba_ponowien + 1):
            try:
                return await self._jedno_zadanie(zadanie, wpis)
            except BladPrzejsciowy as blad:
                ostatni_blad = blad
                if numer_proby == self._ustawienia.liczba_ponowien:
                    break
                zadany_odstep = getattr(blad, "odstep_sekundy", None)
                await self._usypiacz(self._odstep_ponowienia(numer_proby, zadany_odstep))
        raise (
            ostatni_blad
            if ostatni_blad is not None
            else BladPrzejsciowy(f"Nie udało się pobrać adresu {zadanie.adres_pobierania}.")
        )

    async def _jedno_zadanie(self, zadanie: Zadanie, wpis: WpisCache | None) -> WynikPobrania:
        """Wykonuje pojedyncze żądanie HTTP i zamienia odpowiedź na wynik pobrania."""
        klient = self._wymagany_klient()
        naglowki = _naglowki_warunkowe(wpis)

        async with self._dostep_do_domeny(zadanie.adres_pobierania):
            try:
                async with klient.stream(
                    "GET", zadanie.adres_pobierania, headers=naglowki
                ) as odpowiedz:
                    if odpowiedz.status_code == _KOD_NIEZMIENIONE and wpis is not None:
                        return self._odswiez_wpis(zadanie, wpis)
                    _sprawdz_kod_odpowiedzi(odpowiedz, zadanie.adres_pobierania)
                    pominiecie = _pominiecie_z_typu_zawartosci(odpowiedz, zadanie.adres_pobierania)
                    if pominiecie is not None:
                        return pominiecie
                    tresc = await self._wczytaj_tresc(odpowiedz, zadanie.adres_pobierania)
                    if isinstance(tresc, PominietePobranie):
                        return tresc
                    return self._zapamietaj(zadanie, odpowiedz, tresc)
            except httpx.TimeoutException as blad:
                raise BladPrzejsciowy(
                    f"Przekroczono limit czasu przy pobieraniu {zadanie.adres_pobierania}."
                ) from blad
            except httpx.ConnectError as blad:
                if _czy_blad_certyfikatu(blad):
                    raise BladTrwaly(
                        f"Nie udało się zweryfikować certyfikatu witryny przy adresie "
                        f"{zadanie.adres_pobierania}. Sprawdź, czy ruch nie jest "
                        "przechwytywany przez program antywirusowy albo serwer "
                        "pośredniczący, czy certyfikat witryny nie wygasł oraz czy zegar "
                        "systemowy jest ustawiony poprawnie."
                    ) from blad
                raise BladPrzejsciowy(
                    f"Błąd połączenia przy pobieraniu {zadanie.adres_pobierania}: {blad}"
                ) from blad
            except httpx.HTTPError as blad:
                raise BladPrzejsciowy(
                    f"Błąd połączenia przy pobieraniu {zadanie.adres_pobierania}: {blad}"
                ) from blad

    async def _wczytaj_tresc(
        self, odpowiedz: httpx.Response, adres: str
    ) -> bytes | PominietePobranie:
        """Wczytuje treść fragmentami, pilnując bezpiecznego limitu rozmiaru."""
        limit = self._ustawienia.maksymalny_rozmiar_pobrania_mb * BAJTOW_W_MEGABAJCIE
        fragmenty: list[bytes] = []
        rozmiar = 0
        async for fragment in odpowiedz.aiter_bytes(_ROZMIAR_FRAGMENTU):
            rozmiar += len(fragment)
            if rozmiar > limit:
                return PominietePobranie(
                    adres=adres,
                    powod=(
                        f"Zasób przekracza bezpieczny limit pobrania "
                        f"{self._ustawienia.maksymalny_rozmiar_pobrania_mb} MB. "
                        "Źródło zostało pominięte."
                    ),
                )
            fragmenty.append(fragment)
        return b"".join(fragmenty)

    def _zapamietaj(
        self, zadanie: Zadanie, odpowiedz: httpx.Response, tresc: bytes
    ) -> OdpowiedzPobrania:
        """Buduje wynik pobrania i zapisuje go w pamięci podręcznej."""
        wynik = OdpowiedzPobrania(
            adres_zadany=zadanie.adres_pobierania,
            adres_koncowy=str(odpowiedz.url),
            kod_odpowiedzi=odpowiedz.status_code,
            tresc=tresc,
            typ_zawartosci=_typ_zawartosci(odpowiedz),
            deklarowane_kodowanie=(odpowiedz.charset_encoding or ""),
            etag=odpowiedz.headers.get("etag"),
            last_modified=odpowiedz.headers.get("last-modified"),
        )
        if self._pamiec is not None:
            self._pamiec.zapisz(
                WpisCache(
                    klucz=zadanie.klucz_kanoniczny,
                    adres_koncowy=wynik.adres_koncowy,
                    kod_odpowiedzi=wynik.kod_odpowiedzi,
                    typ_zawartosci=wynik.typ_zawartosci,
                    deklarowane_kodowanie=wynik.deklarowane_kodowanie,
                    etag=wynik.etag,
                    last_modified=wynik.last_modified,
                    tresc=wynik.tresc,
                    pobrano=self._zegar_utc(),
                )
            )
        return wynik

    def _odswiez_wpis(self, zadanie: Zadanie, wpis: WpisCache) -> OdpowiedzPobrania:
        """Obsługuje odpowiedź 304, czyli potwierdzenie aktualności zapisanej treści."""
        if self._pamiec is not None:
            self._pamiec.odswiez_czas_pobrania(zadanie.klucz_kanoniczny, self._zegar_utc())
        return _z_pamieci(zadanie, wpis)

    def _odstep_ponowienia(self, numer_proby: int, odstep_z_naglowka: float | None) -> float:
        """Wyznacza odstęp przed kolejną próbą, z rosnącym opóźnieniem i sufitem.

        Odstęp podany przez serwer w nagłówku ``Retry-After`` ma pierwszeństwo,
        ale nadal podlega górnemu ograniczeniu z konfiguracji, żeby jedno źródło
        nie zatrzymało pracy na godziny.
        """
        maksimum = self._ustawienia.maksymalny_odstep_sekundy
        if odstep_z_naglowka is not None:
            return float(min(odstep_z_naglowka, maksimum))
        rosnacy = self._ustawienia.podstawa_odstepu_sekundy * (2**numer_proby)
        return float(min(rosnacy, maksimum))

    @asynccontextmanager
    async def _dostep_do_domeny(self, adres: str) -> AsyncIterator[None]:
        """Wpuszcza żądanie do domeny z zachowaniem limitu połączeń i odstępu.

        Odstęp jest liczony od momentu wpuszczenia poprzedniego żądania do tej
        samej domeny. Dzięki temu równoległe pobieranie wielu adresów z jednego
        serwisu nadal zachowuje kulturę wobec serwera.
        """
        stan = self._stan_domeny(_domena(adres))
        odstep = self._ustawienia.odstep_miedzy_zadaniami_sekundy
        async with stan.semafor:
            async with stan.blokada:
                teraz = self._zegar()
                do_odczekania = stan.nastepny_dozwolony - teraz
                if do_odczekania > 0:
                    await self._usypiacz(do_odczekania)
                    teraz += do_odczekania
                stan.nastepny_dozwolony = teraz + odstep
            yield

    def _stan_domeny(self, domena: str) -> _StanDomeny:
        """Zwraca stan kolejki dla domeny, tworząc go przy pierwszym użyciu."""
        stan = self._domeny.get(domena)
        if stan is None:
            stan = _StanDomeny(semafor=asyncio.Semaphore(self._ustawienia.polaczenia_na_domene))
            self._domeny[domena] = stan
        return stan

    def _wymagany_klient(self) -> httpx.AsyncClient:
        """Zwraca otwartego klienta albo zgłasza błąd użycia poza blokiem ``async with``."""
        if self._klient is None:
            raise BladTrwaly("Pobieracz jest używany poza blokiem async with.")
        return self._klient

    def _wymagany_kontroler_robots(self) -> KontrolerRobots:
        """Zwraca kontroler reguł witryn albo zgłasza błąd użycia poza kontekstem."""
        if self._robots is None:
            raise BladTrwaly("Pobieracz jest używany poza blokiem async with.")
        return self._robots


def _z_pamieci(zadanie: Zadanie, wpis: WpisCache) -> OdpowiedzPobrania:
    """Buduje wynik pobrania z zapisanego wpisu pamięci podręcznej."""
    return OdpowiedzPobrania(
        adres_zadany=zadanie.adres_pobierania,
        adres_koncowy=wpis.adres_koncowy,
        kod_odpowiedzi=wpis.kod_odpowiedzi,
        tresc=wpis.tresc,
        typ_zawartosci=wpis.typ_zawartosci,
        deklarowane_kodowanie=wpis.deklarowane_kodowanie,
        etag=wpis.etag,
        last_modified=wpis.last_modified,
        z_pamieci_podrecznej=True,
    )


def _naglowki_warunkowe(wpis: WpisCache | None) -> dict[str, str]:
    """Buduje nagłówki zapytania warunkowego na podstawie zapisanego wpisu."""
    if wpis is None:
        return {}
    naglowki: dict[str, str] = {}
    if wpis.etag:
        naglowki["If-None-Match"] = wpis.etag
    if wpis.last_modified:
        naglowki["If-Modified-Since"] = wpis.last_modified
    return naglowki


def _sprawdz_kod_odpowiedzi(odpowiedz: httpx.Response, adres: str) -> None:
    """Zamienia kod odpowiedzi na wyjątek przejściowy albo trwały, zgodnie z taksonomią."""
    kod = odpowiedz.status_code
    if kod == _KOD_ZA_DUZO_ZADAN:
        raise BladZaDuzoZadan(
            f"Serwer prosi o zwolnienie tempa przy adresie {adres}. Ponawiam za chwilę.",
            odstep_sekundy=_odstep_z_naglowka(odpowiedz),
        )
    if kod >= 500:
        raise BladPrzejsciowy(f"Serwer odpowiedział błędem {kod} dla adresu {adres}.")
    if kod >= 400:
        raise BladTrwaly(f"Serwer odpowiedział kodem {kod} dla adresu {adres}.")


def _odstep_z_naglowka(odpowiedz: httpx.Response) -> float | None:
    """Odczytuje nagłówek ``Retry-After`` wyrażony w sekundach."""
    wartosc = odpowiedz.headers.get("retry-after")
    if not wartosc:
        return None
    try:
        return max(0.0, float(wartosc.strip()))
    except ValueError:
        return None


def _pominiecie_z_typu_zawartosci(
    odpowiedz: httpx.Response, adres: str
) -> PominietePobranie | None:
    """Zwraca pominięcie, gdy zasób nie jest stroną HTML."""
    typ = _typ_zawartosci(odpowiedz)
    if not typ or typ in TYPY_ZAWARTOSCI_HTML:
        return None
    return PominietePobranie(
        adres=adres,
        powod=(
            f"Zasób ma typ „{typ}”, a nie stronę HTML. Obsługa tego formatu przyjdzie "
            "w kolejnych etapach, na razie źródło zostało pominięte."
        ),
    )


def _typ_zawartosci(odpowiedz: httpx.Response) -> str:
    """Zwraca sam typ zawartości, bez parametrów takich jak kodowanie."""
    naglowek = str(odpowiedz.headers.get("content-type", ""))
    return naglowek.split(";", 1)[0].strip().lower()


def _czy_blad_certyfikatu(blad: BaseException) -> bool:
    """Rozstrzyga, czy błąd połączenia wynika z niezaufanego certyfikatu TLS.

    Biblioteka HTTP opakowuje błąd biblioteki SSL, więc sprawdzany jest cały
    łańcuch przyczyn, a nie tylko sam wyjątek wierzchni.
    """
    biezacy: BaseException | None = blad
    odwiedzone: set[int] = set()
    while biezacy is not None and id(biezacy) not in odwiedzone:
        if isinstance(biezacy, ssl.SSLError):
            return True
        odwiedzone.add(id(biezacy))
        biezacy = biezacy.__cause__ or biezacy.__context__
    return False


def _domena(adres: str) -> str:
    """Zwraca nazwę hosta adresu, używaną jako klucz kolejki żądań."""
    return (urlsplit(adres).hostname or "").lower()
