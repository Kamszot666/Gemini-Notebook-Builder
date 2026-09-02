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
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from gnb.core.postep import FazaPotoku, ZdarzeniePostepu

DOMYSLNY_MINIMALNY_ODSTEP_SEKUND = 4.0


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
