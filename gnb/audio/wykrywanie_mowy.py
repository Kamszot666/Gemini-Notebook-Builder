"""Odrzucanie materiału niemownego na podstawie udziału mowy w nagraniu.

Moduł audio obsługuje wyłącznie nagrania mowy. Rozróżnianie mowy od muzyki jest
tu heurystyką dwustopniową, a nie klasyfikacją muzyki. Pierwszy stopień jest
w tym module: filtr wykrywania aktywności mowy Silero, wbudowany w faster-whisper,
podaje, jaki udział długości nagrania stanowi mowa; nagranie o udziale poniżej
konfigurowalnego progu jest odrzucane jako niemowne, z czytelnym komunikatem
i bez transkrypcji. Drugi stopień, obrona przed halucynacjami już przepisanego
tekstu, jest w `gnb.audio.ocena`.

To jest heurystyka. Utwór ze śpiewem może częściowo zarejestrować się jako mowa,
a nagranie mowy z głośną muzyką w tle może zejść poniżej progu. Dlatego sekcja
piętnasta CLAUDE.md wymaga, żeby użytkownik mógł nadpisać tę decyzję dla
konkretnego pliku — służy do tego opcja wiersza poleceń ``--wymus-transkrypcje``
oraz globalny klucz konfiguracji ``transkrypcja_prog_udzialu_mowy``.

Osobny klasyfikator muzyki został odrzucony w decyzji siódmej etapu dziewiątego:
oznaczałby kolejny model i setki megabajtów za przypadek, o którym sekcja
pierwsza a CLAUDE.md mówi, że nie wystąpi, bo użytkownik nagrań muzycznych nie
dodaje.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnb.audio.dekodowanie import CZESTOTLIWOSC_PROBKOWANIA, Fala
from gnb.audio.transkrypcja import zaladuj_vad

OCENA_MOWA = "mowa"
OCENA_NIEMOWNE = "niemowne"

KOMUNIKAT_NIEMOWNE = (
    "Nagranie zostało rozpoznane jako materiał niemowny: mowa stanowi około "
    "{udzial} procent jego długości, poniżej progu {prog} procent. Moduł audio "
    "obsługuje wyłącznie nagrania mowy, więc plik pominięto bez transkrypcji. "
    "Jeżeli to jednak nagranie mowy z głośnym tłem, wymuś transkrypcję opcją "
    "„--wymus-transkrypcje” albo obniż próg „transkrypcja_prog_udzialu_mowy” "
    "w konfiguracji."
)


@dataclass(frozen=True, slots=True)
class OcenaMowy:
    """Wynik pierwszego stopnia heurystyki: czy nagranie jest mową."""

    ocena: str
    udzial_mowy: float
    prog: float

    @property
    def czy_mowa(self) -> bool:
        """Prawda, gdy udział mowy sięga progu i nagranie nadaje się do transkrypcji."""
        return self.ocena == OCENA_MOWA

    @property
    def udzial_procent(self) -> int:
        """Udział mowy zaokrąglony do pełnych procent, do komunikatu dla użytkownika."""
        return round(self.udzial_mowy * 100)

    @property
    def prog_procent(self) -> int:
        """Próg udziału mowy zaokrąglony do pełnych procent."""
        return round(self.prog * 100)


def dlugosc_mowy_sekundy(fala: Fala, prog_vad: float) -> float:
    """Zwraca łączną długość odcinków mowy w nagraniu, w sekundach.

    Wykrywanie aktywności mowy realizuje wbudowany w faster-whisper filtr Silero,
    ten sam, którego transkrypcja używa jako ``vad_filter``. Nie dokładamy
    osobnej zależności ani osobnego modelu, zgodnie z decyzją szóstą etapu
    dziewiątego.
    """
    vad = zaladuj_vad()
    odcinki = vad.get_speech_timestamps(fala, vad.VadOptions(threshold=prog_vad))
    probki_mowy = sum(int(odcinek["end"]) - int(odcinek["start"]) for odcinek in odcinki)
    return probki_mowy / CZESTOTLIWOSC_PROBKOWANIA


def ocen_mowe(dlugosc_mowy: float, dlugosc_nagrania: float, prog_udzialu: float) -> OcenaMowy:
    """Rozstrzyga, czy nagranie jest mową, porównując udział mowy z progiem.

    Próg udziału równy zeru oznacza „nigdy nie odrzucaj”, czyli globalny
    odpowiednik wymuszenia transkrypcji. Nagranie bez próbek dźwięku dostaje
    udział zero i jest odrzucane, chyba że próg też wynosi zero.
    """
    if dlugosc_nagrania <= 0:
        udzial = 0.0
    else:
        udzial = min(dlugosc_mowy / dlugosc_nagrania, 1.0)
    ocena = OCENA_MOWA if udzial >= prog_udzialu else OCENA_NIEMOWNE
    return OcenaMowy(ocena=ocena, udzial_mowy=udzial, prog=prog_udzialu)
