"""Transkrypcja nagrań mowy silnikiem faster-whisper na rdzeniu CTranslate2.

Ten moduł opakowuje bibliotekę faster-whisper wąskim adapterem z własnymi
typami, tak samo jak `gnb.images.tesseract` opakowuje program Tesseract. Do
biblioteki trafia gotowa fala dźwiękowa jako tablica NumPy, nigdy ścieżka pliku,
więc wbudowany w faster-whisper dekoder audio (PyAV) nie jest w ogóle wołany.
Rozkodowanie nagrania robi `gnb.audio.dekodowanie` przez FFmpega.

Strażnik atrapy modułu ``av``. Biblioteka faster-whisper importuje PyAV
bezwarunkowo w pierwszej linii swojego pliku ``__init__``. Na komputerze
deweloperskim Inteligentne sterowanie aplikacjami Windows blokuje niepodpisane
biblioteki natywne PyAV, więc ta jedna linia wywraca cały import faster-whisper,
mimo że rdzeń CTranslate2 i wykrywanie mowy przez ONNX Runtime działają bez
zarzutu. Dlatego przed importem faster-whisper próbujemy zaimportować ``av``
i tylko wtedy, gdy to zawiedzie, wstawiamy do ``sys.modules`` puste atrapy
modułów ``av``, ``av.audio`` i ``av.error``. Na maszynie bez blokady ładuje się
prawdziwy PyAV i nic się nie zmienia.

To nie jest omijanie zabezpieczenia w rozumieniu sekcji trzeciej CLAUDE.md.
Nie ładujemy zablokowanego pliku, nie wyłączamy żadnej ochrony — rezygnujemy
z zależności, której i tak nie używamy, bo dekodujemy własnym narzędziem.
Rozumowanie jest identyczne jak przy regule uruchamiania narzędzi przez
``python -m`` z sekcji piątej.

Transkrypcja działa wyłącznie na procesorze. Ustawienie karty graficznej kończy
się jawnym błędem konfiguracji, bez cichego przełączania z powrotem na procesor,
zgodnie z decyzją trzecią etapu dziewiątego.

Brak biblioteki faster-whisper nie wywraca aplikacji: kończy się wyjątkiem
`BrakNarzedzia`, a potok zamienia go na kontrolowane pominięcie źródła.
"""

from __future__ import annotations

import functools
import importlib
import logging
import os
import sys
import types
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from gnb.audio.dekodowanie import CZESTOTLIWOSC_PROBKOWANIA, Fala
from gnb.core.konfiguracja import (
    KOMUNIKAT_URZADZENIE_NIEOBSLUGIWANE,
    URZADZENIA_PROCESORA,
    Konfiguracja,
)
from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia

_log = logging.getLogger(__name__)

# Nazwy atrap modułów wstawianych awaryjnie zamiast zablokowanego PyAV.
_ATRAPY_AV = ("av", "av.audio", "av.error")

# Powód wstawienia atrapy modułu ``av``. Pusty, dopóki import PyAV się udaje albo
# nie był jeszcze próbowany. Potok odczytuje tę wartość i zapisuje ją do
# ``log_szczegolowy.txt`` przez rejestrator projektu, bo rejestrator tego modułu
# nie trafia do pliku logu projektu.
_powod_atrapy_av: str | None = None

KOMUNIKAT_BRAK_BIBLIOTEKI = (
    "Nie znaleziono biblioteki faster-whisper, która przepisuje mowę z nagrań na "
    "tekst. Zainstaluj ją poleceniem „pip install gnb[audio]”. Bez niej nagrania "
    "mowy nie zostaną przepisane, a pozostałe formaty źródeł działają normalnie."
)
KOMUNIKAT_MODEL_NIEDOSTEPNY = (
    "Nie udało się wczytać modelu transkrypcji „{model}”. Przy pierwszym "
    "uruchomieniu model pobiera się z sieci — sprawdź połączenie i nie przerywaj "
    "pierwszego pobrania. Szczegóły: {powod}."
)
KOMUNIKAT_BLAD_TRANSKRYPCJI = "Transkrypcja nagrania nie powiodła się. Szczegóły: {powod}."

# Ile rdzeni domyślny dobór wątków transkrypcji zostawia wolnych. Powód jest
# dostępnościowy, nie wydajnościowy: gdy transkrypcja obciąża wszystkie rdzenie,
# synteza mowy czytnika ekranu zaczyna się zacinać, a użytkownik właśnie wtedy
# słucha komunikatów o postępie długiej operacji. Jeden wolny rdzeń wystarcza,
# żeby mowa była płynna. Tak samo dobierana jest liczba procesów OCR
# w gnb/images/tesseract.py; nie „poprawiaj” tego na pełną liczbę rdzeni jako
# rzekomo nieoptymalne — ustawienie „transkrypcja_liczba_watkow” nadal pozwala
# podnieść wartość ręcznie. Opisane też w docs/CONFIGURATION.md.
_RDZENIE_ZOSTAWIONE_WOLNE = 1

# Progi obrony przed halucynacjami Whispera na poziomie samej transkrypcji.
# Segment o prawdopodobieństwie logarytmicznym poniżej tej wartości albo
# o wysokim prawdopodobieństwie braku mowy jest oznaczany jako niepewny.
PROG_PRAWDOPODOBIENSTWA_LOGARYTMICZNEGO = -1.0
PROG_PRAWDOPODOBIENSTWA_BRAKU_MOWY = 0.6


@dataclass(frozen=True, slots=True)
class UstawieniaTranskrypcji:
    """Zestaw ustawień jednego przebiegu transkrypcji, wyprowadzony z konfiguracji."""

    model: str = "medium"
    jezyk: str = "pl"
    urzadzenie: str = "procesor"
    typ_obliczen: str = "int8"
    liczba_watkow: int = 0
    prog_vad: float = 0.5

    @classmethod
    def z_konfiguracji(cls, konfiguracja: Konfiguracja) -> UstawieniaTranskrypcji:
        """Buduje ustawienia transkrypcji z pól konfiguracji aplikacji.

        Wartość urządzenia inna niż procesor kończy się tutaj jawnym błędem
        trwałym, nawet gdy konfigurację zbudowano z pominięciem `wczytaj_konfiguracje`.
        Decyzja trzecia etapu dziewiątego: cicha podmiana na procesor jest gorsza
        niż jawna odmowa.
        """
        urzadzenie = konfiguracja.transkrypcja_urzadzenie.strip().lower()
        if urzadzenie not in URZADZENIA_PROCESORA:
            raise BladTrwaly(KOMUNIKAT_URZADZENIE_NIEOBSLUGIWANE.format(wartosc=urzadzenie))
        return cls(
            model=konfiguracja.transkrypcja_model,
            jezyk=konfiguracja.transkrypcja_jezyk,
            urzadzenie="procesor",
            typ_obliczen=konfiguracja.transkrypcja_typ_obliczen,
            liczba_watkow=konfiguracja.transkrypcja_liczba_watkow,
            prog_vad=konfiguracja.transkrypcja_prog_vad,
        )

    @property
    def efektywna_liczba_watkow(self) -> int:
        """Zwraca liczbę wątków procesora, zamieniając zero na wartość dobraną."""
        if self.liczba_watkow > 0:
            return self.liczba_watkow
        rdzenie = os.cpu_count() or 1
        return max(1, rdzenie - _RDZENIE_ZOSTAWIONE_WOLNE)


@dataclass(frozen=True, slots=True)
class SegmentTranskrypcji:
    """Jeden odcinek rozpoznanej mowy wraz z miarami pewności."""

    poczatek_sekundy: float
    koniec_sekundy: float
    tekst: str
    prawdopodobienstwo_logarytmiczne: float
    prawdopodobienstwo_braku_mowy: float

    @property
    def czy_niepewny(self) -> bool:
        """Prawda, gdy segment wygląda na halucynację modelu albo słaby odczyt."""
        return (
            self.prawdopodobienstwo_logarytmiczne < PROG_PRAWDOPODOBIENSTWA_LOGARYTMICZNEGO
            or self.prawdopodobienstwo_braku_mowy > PROG_PRAWDOPODOBIENSTWA_BRAKU_MOWY
        )


@dataclass(frozen=True, slots=True)
class WynikTranskrypcji:
    """Wynik transkrypcji jednego nagrania."""

    segmenty: tuple[SegmentTranskrypcji, ...]
    jezyk: str
    dlugosc_nagrania_sekundy: float


def powod_atrapy_av() -> str | None:
    """Zwraca powód wstawienia atrapy modułu ``av`` albo ``None``, gdy PyAV działa.

    Wartość jest ustalana przy pierwszym imporcie warstwy faster-whisper. Potok
    odczytuje ją i zapisuje do ``log_szczegolowy.txt``, ponieważ rejestrator tego
    modułu nie trafia do pliku logu projektu.
    """
    return _powod_atrapy_av


def _wstaw_atrapy_av(powod: str) -> None:
    """Wstawia do ``sys.modules`` puste atrapy modułów ``av`` i zapisuje powód."""
    global _powod_atrapy_av
    atrapy: dict[str, types.ModuleType] = {}
    for nazwa in _ATRAPY_AV:
        modul = types.ModuleType(nazwa)
        modul.__doc__ = (
            "Atrapa modułu wstawiona przez gnb.audio.transkrypcja, bo prawdziwy "
            "PyAV nie zaimportował się. Dekodowanie audio i tak idzie przez FFmpeg."
        )
        atrapy[nazwa] = modul
        sys.modules.setdefault(nazwa, modul)
    atrapy["av"].__dict__["audio"] = sys.modules["av.audio"]
    atrapy["av"].__dict__["error"] = sys.modules["av.error"]
    _powod_atrapy_av = powod
    _log.warning(
        "Nie udało się zaimportować PyAV (%s). Wstawiono atrapę modułu „av”; "
        "dekodowanie dźwięku i tak idzie przez FFmpeg.",
        powod,
    )


@functools.lru_cache(maxsize=1)
def _faster_whisper() -> types.ModuleType:
    """Importuje bibliotekę faster-whisper, w razie potrzeby z atrapą PyAV.

    Wynik jest zapamiętywany, więc próba importu i ewentualne wstawienie atrapy
    dzieją się raz na proces. Brak samej biblioteki kończy się `BrakNarzedzia`.
    """
    try:
        importlib.import_module("av")
    except Exception as blad:  # noqa: BLE001 — każdy błąd importu PyAV ma ten sam skutek
        _wstaw_atrapy_av(f"{type(blad).__name__}: {blad}")
    try:
        return importlib.import_module("faster_whisper")
    except ImportError as blad:
        raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI) from blad


def zaladuj_vad() -> types.ModuleType:
    """Zwraca moduł ``faster_whisper.vad`` z filtrem wykrywania aktywności mowy.

    Import przechodzi przez ten sam strażnik atrapy PyAV co reszta biblioteki,
    więc wykrywanie mowy działa nawet tam, gdzie PyAV jest zablokowany. Brak
    biblioteki kończy się `BrakNarzedzia`.
    """
    _faster_whisper()
    try:
        return importlib.import_module("faster_whisper.vad")
    except ImportError as blad:
        raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI) from blad


def czy_dostepna_biblioteka() -> bool:
    """Zwraca prawdę, gdy bibliotekę faster-whisper da się zaimportować."""
    try:
        _faster_whisper()
    except BrakNarzedzia:
        return False
    return True


def model_dostepny_lokalnie(model: str, typ_obliczen: str = "int8") -> bool:
    """Zwraca prawdę, gdy model transkrypcji jest już pobrany na dysk.

    Używane przez strażnik pomijania testów zależnych od modelu: bez pobranego
    modelu i bez sieci test ma się pominąć z czytelnym powodem, a nie zaczerwienić.
    Wzoruje się na fiksturze ``wymaga_ocr_pol`` z tests/conftest.py.
    """
    try:
        biblioteka = _faster_whisper()
    except BrakNarzedzia:
        return False
    try:
        biblioteka.WhisperModel(
            model, device="cpu", compute_type=typ_obliczen, local_files_only=True
        )
    except Exception:  # noqa: BLE001 — dowolny błąd oznacza „modelu nie ma lokalnie”
        return False
    return True


@functools.lru_cache(maxsize=2)
def _wczytaj_model(model: str, typ_obliczen: str, liczba_watkow: int) -> Any:
    """Wczytuje model transkrypcji i zapamiętuje go między wywołaniami."""
    biblioteka = _faster_whisper()
    try:
        return biblioteka.WhisperModel(
            model,
            device="cpu",
            compute_type=typ_obliczen,
            cpu_threads=liczba_watkow,
        )
    except Exception as blad:  # noqa: BLE001 — pobranie modelu zawodzi na wiele sposobów
        raise BrakNarzedzia(KOMUNIKAT_MODEL_NIEDOSTEPNY.format(model=model, powod=blad)) from blad


def transkrybuj(
    fala: Fala,
    ustawienia: UstawieniaTranskrypcji,
    *,
    przy_postepie: Callable[[int, int], None] | None = None,
    identyfikator_zrodla: str | None = None,
) -> WynikTranskrypcji:
    """Przepisuje falę dźwiękową na tekst, segment po segmencie.

    Filtr wykrywania aktywności mowy jest włączony, bo modele Whisper na
    fragmentach bez mowy generują halucynacje w postaci powtarzanych fraz.
    Argument `przy_postepie` jest wołany po każdym gotowym segmencie z parą liczb
    w sekundach: ile sekund nagrania już przepisano i ile trwa całe nagranie.
    Potok zamienia to na komunikat wyrażony w minutach.
    """
    model = _wczytaj_model(
        ustawienia.model, ustawienia.typ_obliczen, ustawienia.efektywna_liczba_watkow
    )
    opcje_vad = zaladuj_vad().VadOptions(threshold=ustawienia.prog_vad)
    try:
        segmenty_surowe, informacje = model.transcribe(
            fala,
            language=ustawienia.jezyk,
            vad_filter=True,
            vad_parameters=opcje_vad,
        )
        dlugosc = float(getattr(informacje, "duration", 0.0)) or (
            len(fala) / CZESTOTLIWOSC_PROBKOWANIA
        )
        segmenty = tuple(_zbierz_segmenty(segmenty_surowe, dlugosc, przy_postepie))
    except BrakNarzedzia:
        raise
    except Exception as blad:  # noqa: BLE001 — błąd rdzenia CTranslate2 zamieniamy na czytelny
        raise BladTrwaly(
            KOMUNIKAT_BLAD_TRANSKRYPCJI.format(powod=blad), identyfikator_zrodla
        ) from blad

    return WynikTranskrypcji(
        segmenty=segmenty,
        jezyk=str(getattr(informacje, "language", ustawienia.jezyk) or ustawienia.jezyk),
        dlugosc_nagrania_sekundy=dlugosc,
    )


def _zbierz_segmenty(
    segmenty_surowe: Any,
    dlugosc_nagrania: float,
    przy_postepie: Callable[[int, int], None] | None,
) -> Iterator[SegmentTranskrypcji]:
    """Zamienia leniwy strumień segmentów faster-whisper na nasze segmenty.

    Strumień jest leniwy, więc dopiero jego przejście uruchamia właściwe
    rozpoznawanie. Postęp jest zgłaszany po każdym segmencie, na podstawie jego
    końca, żeby użytkownik nie został przy niemym oknie przez godzinę.
    """
    calkowite_sekundy = max(int(round(dlugosc_nagrania)), 1)
    for segment in segmenty_surowe:
        yield SegmentTranskrypcji(
            poczatek_sekundy=float(segment.start),
            koniec_sekundy=float(segment.end),
            tekst=str(segment.text).strip(),
            prawdopodobienstwo_logarytmiczne=float(segment.avg_logprob),
            prawdopodobienstwo_braku_mowy=float(segment.no_speech_prob),
        )
        if przy_postepie is not None:
            przy_postepie(min(int(segment.end), calkowite_sekundy), calkowite_sekundy)
