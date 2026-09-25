"""Dławienie komunikatów postępu dla regionu ``role="status"`` interfejsu.

Sekcja jedenasta punkt siódmy CLAUDE.md: maksymalnie jeden komunikat na trzy do
pięciu sekund, w formie podsumowania. Ogłaszanie każdego pojedynczego zdarzenia
czyni interfejs bezużytecznym z czytnikiem ekranu.

Powtórzony ten sam tekst w regionie ``aria-live`` NVDA ogłasza ponownie, więc
dławik odrzuca też komunikat identyczny z aktualnie widocznym, niezależnie od
czasu. Zdarzenie zakończenia projektu przechodzi zawsze, bo jest ostatnią
informacją, jaką użytkownik ma usłyszeć.

Dławik jest zasilany z wątku roboczego, a odczytywany z wątku obsługującego
żądanie HTTP, dlatego jego stan jest chroniony zamkiem.

Moduł zawiera też `KalkulatorProcentu`, który poprzedza dławik i dopisuje do
opisu zdarzenia ogólny procent postępu całego przebiegu, licząc od zera do stu.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import replace

from gnb.core.postep import FazaPotoku, ZdarzeniePostepu

DOMYSLNY_MINIMALNY_ODSTEP_SEKUND = 4.0

# Fazy sekwencji nadrzędnej całego przebiegu, w kolejności ich wystąpienia.
# Fazy OCR, transkrypcji i rozpoznawania nut nie wchodzą tutaj: są zgłaszane
# wewnątrz ekstrakcji pojedynczego źródła i mówią o postępie tego jednego
# źródła, nie całego przebiegu, więc ich opis przechodzi bez zmian.
_FAZY_SEKWENCJI_GLOWNEJ = frozenset(
    {
        FazaPotoku.POBIERANIE_STRON,
        FazaPotoku.POBIERANIE_NAPISOW,
        FazaPotoku.EKSTRAKCJA,
        FazaPotoku.DEDUPLIKACJA,
        FazaPotoku.PAKOWANIE,
    }
)


class KalkulatorProcentu:
    """Liczy ogólny procent postępu przebiegu z kolejnych zdarzeń jednej fazy naraz.

    Budżet ekstrakcji, deduplikacji i pakowania jest znany z góry i wpisany do
    mianownika od razu przy starcie kalkulatora: liczba pozycji do ekstrakcji
    jest znana, zanim jakiekolwiek pobieranie się zacznie, a deduplikacja
    i pakowanie zawsze zgłaszają się jako dokładnie jeden krok każda. Fazy
    pobierania stron i pobierania napisów są inne — ich wielkość ujawnia
    dopiero pierwsze zdarzenie fazy — ale zawsze kończą się, zanim ekstrakcja
    zdąży zgłosić choćby jedno źródło, więc ich spóźnione dojście do
    mianownika nie cofa procentu ogłoszonego wcześniej: nic z ekstrakcji,
    deduplikacji ani pakowania jeszcze się nie liczyło. Gdyby budżet ekstrakcji
    też był nieznany z góry, szybkie zakończenie samego pobierania potrafiłoby
    chwilowo wyglądać na większość całej pracy, a dogonienie przez ekstrakcję
    swojego prawdziwego, dużo większego budżetu cofałoby już ogłoszony procent
    — dokładnie tego ma unikać wpisanie budżetu ekstrakcji z góry.

    Wynikowy procent jest zaokrąglany w dół do pełnej dziesiątki, zgodnie
    z wymaganiem ogłaszania progu co dziesięć procent — jest to więc
    przybliżenie z zamierzenia, nie z niedopatrzenia: deduplikacja i pakowanie
    liczą się jako pojedynczy krok niezależnie od realnego czasu trwania.
    Zakończenie przebiegu zawsze pokazuje sto procent, niezależnie od tego, co
    wyszłoby z samego rachunku, żeby zaokrąglenie w dół nigdy nie zostawiło
    ostatniego komunikatu na dziewięćdziesięciu.
    """

    def __init__(self, liczba_pozycji: int) -> None:
        self._wszystkich: dict[FazaPotoku, int] = {
            FazaPotoku.EKSTRAKCJA: liczba_pozycji,
            FazaPotoku.DEDUPLIKACJA: 1,
            FazaPotoku.PAKOWANIE: 1,
        }
        self._wykonano: dict[FazaPotoku, int] = {}

    def opatrz_procentem(self, zdarzenie: ZdarzeniePostepu) -> ZdarzeniePostepu:
        """Zwraca zdarzenie z opisem poprzedzonym „Postęp: N procent, ”."""
        if zdarzenie.faza is FazaPotoku.ZAKONCZENIE:
            return replace(zdarzenie, opis=f"Postęp: 100 procent, {zdarzenie.opis}")
        if zdarzenie.faza not in _FAZY_SEKWENCJI_GLOWNEJ:
            return zdarzenie

        self._wszystkich[zdarzenie.faza] = zdarzenie.wszystkich
        self._wykonano[zdarzenie.faza] = zdarzenie.wykonano

        wszystkich = sum(self._wszystkich.values())
        wykonano = sum(self._wykonano.get(faza, 0) for faza in self._wszystkich)
        procent = ((wykonano * 100 // wszystkich) // 10) * 10 if wszystkich else 0
        return replace(zdarzenie, opis=f"Postęp: {procent} procent, {zdarzenie.opis}")


class DlawikPostepu:
    """Przechowuje aktualny, dławiony komunikat postępu długiej operacji.

    Metoda `przyjmij` jest wołana przez potok dla każdego zdarzenia. Metoda
    `komunikat` zwraca tekst, który interfejs ma pokazać, i przy okazji promuje
    najnowszy zapamiętany opis, gdy minął już minimalny odstęp. Dzięki temu
    odpytywanie z przeglądarki co kilka sekund w naturalny sposób nadgania
    zdławione wcześniej zdarzenia.
    """

    def __init__(
        self,
        *,
        minimalny_odstep_sekund: float = DOMYSLNY_MINIMALNY_ODSTEP_SEKUND,
        zegar: Callable[[], float] = time.monotonic,
    ) -> None:
        self._minimalny_odstep = minimalny_odstep_sekund
        self._zegar = zegar
        self._zamek = threading.Lock()
        self._widoczny = ""
        self._ostatni_surowy = ""
        # Ujemna nieskończoność sprawia, że pierwsze zdarzenie przechodzi od
        # razu: dławienie dotyczy kolejnych komunikatów, nie pierwszego.
        self._czas_widocznego = float("-inf")

    def przyjmij(self, zdarzenie: ZdarzeniePostepu) -> None:
        """Rejestruje zdarzenie postępu i, jeżeli można, od razu je pokazuje."""
        with self._zamek:
            self._ostatni_surowy = zdarzenie.opis
            wymuszone = zdarzenie.faza is FazaPotoku.ZAKONCZENIE
            self._sprobuj_pokazac(wymuszone=wymuszone)

    def komunikat(self) -> str:
        """Zwraca aktualny dławiony komunikat, promując najnowsze zdarzenie, gdy minął odstęp."""
        with self._zamek:
            self._sprobuj_pokazac(wymuszone=False)
            return self._widoczny

    def _sprobuj_pokazac(self, *, wymuszone: bool) -> None:
        if self._ostatni_surowy == self._widoczny:
            return
        teraz = self._zegar()
        if not wymuszone and (teraz - self._czas_widocznego) < self._minimalny_odstep:
            return
        self._widoczny = self._ostatni_surowy
        self._czas_widocznego = teraz
