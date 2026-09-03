"""Taksonomia wyjątków aplikacji Gemini Notebook Builder.

Każdy wyjątek niesie identyfikator źródła, którego dotyczy, jeżeli taki
istnieje, oraz komunikat po polsku gotowy do pokazania użytkownikowi.
Rozróżnienie między błędem przejściowym a trwałym decyduje o tym, czy
operacja podlega ponowieniu z rosnącym odstępem między próbami.
"""

from __future__ import annotations


class BladGnb(Exception):
    """Wspólna podstawa wszystkich wyjątków aplikacji."""

    def __init__(self, komunikat: str, identyfikator_zrodla: str | None = None) -> None:
        super().__init__(komunikat)
        self.komunikat = komunikat
        self.identyfikator_zrodla = identyfikator_zrodla


class BladPrzejsciowy(BladGnb):
    """Błąd chwilowy, na przykład timeout albo błąd sieci 5xx. Podlega ponowieniu."""


class BladTrwaly(BladGnb):
    """Błąd trwały, na przykład 404, uszkodzony plik albo brak uprawnień. Nie podlega ponowieniu."""


class FormatNieobslugiwany(BladGnb):
    """Brak adaptera ekstrakcji dla podanego formatu albo wersji formatu źródła."""


class BrakNarzedzia(BladGnb):
    """Brakuje zewnętrznego programu wymaganego do przetworzenia źródła, na przykład FFmpeg."""


class PrzekroczonoLimit(BladGnb):
    """Przekroczono limit słów w źródle, rozmiaru pliku albo liczby źródeł w notatniku."""


class PominietoZrodlo(BladGnb):
    """Ekstraktor świadomie pomija źródło, bo materiał nie nadaje się do przetworzenia.

    W odróżnieniu od `BladTrwaly` nie oznacza awarii. Jest zgłaszany wtedy, gdy
    ekstraktor rozpoznał, że materiał celowo pozostaje poza jego zakresem, na
    przykład nagranie muzyczne w module obsługującym wyłącznie mowę albo audio
    z wyłączoną w konfiguracji transkrypcją. Potok zamienia go na status
    „pominiete”, tak samo jak przekroczenie limitu, a nie na status „blad”,
    i zapisuje jego komunikat w manifeście oraz w raporcie końcowym.
    """
