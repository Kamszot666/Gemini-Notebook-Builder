"""Ocena jakości transkrypcji: obrona przed halucynacjami modelu Whisper.

Modele Whisper na fragmentach bez mowy generują halucynacje w postaci
powtarzanych fraz, a na nagraniach słabej jakości zwracają segmenty o niskiej
pewności. Taki wynik w pliku wynikowym wygląda tak samo jak poprawny: ma tekst,
ma wpis w manifeście. To jest cicha korupcja materiału źródłowego, czyli
naruszenie pierwszego priorytetu z sekcji czwartej CLAUDE.md. Ten moduł
odpowiada za to samo co ocena jakości OCR z etapu ósmego, tylko dla mowy:
pozwala taki przypadek zauważyć bez odsłuchiwania każdego nagrania.

Ocena jest jedną z dwóch: transkrypcja poprawna albo transkrypcja podejrzana.
Źródło z oceną podejrzaną jest zapisywane normalnie i nigdy nie jest kasowane —
trafia dodatkowo do sekcji „Materiały do sprawdzenia” w raporcie końcowym, tą
samą drogą co ostrzeżenie ekstraktora.

Heurystyki są zachowawcze. Fałszywe podejrzenie kosztuje jedno odsłuchanie
nagrania, a przeoczona halucynacja kosztuje wiarygodność całej bazy wiedzy.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gnb.audio.transkrypcja import SegmentTranskrypcji

OCENA_TRANSKRYPCJI_POPRAWNA = "poprawna"
OCENA_TRANSKRYPCJI_PODEJRZANA = "podejrzana"

# Najmniejsza liczba powtórzeń tej samej frazy, przy której uznajemy ją za
# halucynację. Dwa powtórzenia bywają naturalne w mowie („tak, tak”), trzy to
# już sygnał, że model utknął na pętli.
MINIMALNA_LICZBA_POWTORZEN_FRAZY = 3

# Najmniejsza liczba segmentów, przy której w ogóle liczymy udział segmentów
# niepewnych. Na jednym czy dwóch segmentach ten wskaźnik jest zbyt czuły.
MINIMALNA_LICZBA_SEGMENTOW_DO_OCENY_PEWNOSCI = 3

# Największy dopuszczalny udział segmentów niepewnych. Powyżej tego progu
# transkrypcja jako całość wygląda na przekłamaną.
PROG_UDZIALU_SEGMENTOW_NIEPEWNYCH = 0.3

POWOD_POWTORZONA_FRAZA = (
    "fraza „{fraza}” powtarza się {liczba} razy, co jest typowe dla halucynacji "
    "modelu na fragmencie bez mowy"
)
POWOD_SEGMENTY_NIEPEWNE = (
    "{liczba} z {wszystkich} segmentów ma niską pewność rozpoznania — warto "
    "porównać te fragmenty z nagraniem"
)


@dataclass(frozen=True, slots=True)
class OcenaTranskrypcji:
    """Wynik oceny jakości jednej transkrypcji."""

    ocena: str
    powody: tuple[str, ...] = ()

    @property
    def czy_podejrzana(self) -> bool:
        """Prawda, gdy transkrypcja ma trafić do sekcji „Materiały do sprawdzenia”."""
        return self.ocena == OCENA_TRANSKRYPCJI_PODEJRZANA


def ocen_transkrypcje(segmenty: Sequence[SegmentTranskrypcji]) -> OcenaTranskrypcji:
    """Ocenia transkrypcję zestawem heurystyk i zwraca ocenę wraz z powodami."""
    powody: list[str] = []

    fraza, liczba_powtorzen = _najczestsza_powtorzona_fraza(segmenty)
    if liczba_powtorzen >= MINIMALNA_LICZBA_POWTORZEN_FRAZY:
        powody.append(POWOD_POWTORZONA_FRAZA.format(fraza=_skroc(fraza), liczba=liczba_powtorzen))

    if len(segmenty) >= MINIMALNA_LICZBA_SEGMENTOW_DO_OCENY_PEWNOSCI:
        niepewne = sum(1 for segment in segmenty if segment.czy_niepewny)
        if niepewne / len(segmenty) > PROG_UDZIALU_SEGMENTOW_NIEPEWNYCH:
            powody.append(POWOD_SEGMENTY_NIEPEWNE.format(liczba=niepewne, wszystkich=len(segmenty)))

    if powody:
        return OcenaTranskrypcji(ocena=OCENA_TRANSKRYPCJI_PODEJRZANA, powody=tuple(powody))
    return OcenaTranskrypcji(ocena=OCENA_TRANSKRYPCJI_POPRAWNA)


def _najczestsza_powtorzona_fraza(
    segmenty: Sequence[SegmentTranskrypcji],
) -> tuple[str, int]:
    """Zwraca najczęściej powtórzony tekst segmentu i liczbę jego wystąpień.

    Porównywane są całe teksty segmentów po sprowadzeniu do małych liter i
    ściągnięciu białych znaków. Model utknięty na pętli zwraca dokładnie ten sam
    segment wiele razy, więc porównanie dosłowne wystarcza i nie generuje
    fałszywych trafień na naturalnie podobnych zdaniach.
    """
    liczniki: dict[str, int] = {}
    reprezentacja: dict[str, str] = {}
    for segment in segmenty:
        klucz = " ".join(segment.tekst.lower().split())
        if not klucz:
            continue
        liczniki[klucz] = liczniki.get(klucz, 0) + 1
        reprezentacja.setdefault(klucz, segment.tekst.strip())
    if not liczniki:
        return "", 0
    klucz_najczestszy = max(liczniki, key=lambda k: liczniki[k])
    return reprezentacja[klucz_najczestszy], liczniki[klucz_najczestszy]


def _skroc(tekst: str, maksimum: int = 60) -> str:
    """Skraca frazę do komunikatu, żeby długi segment nie zalał raportu."""
    tekst = " ".join(tekst.split())
    return tekst if len(tekst) <= maksimum else tekst[: maksimum - 1] + "…"
