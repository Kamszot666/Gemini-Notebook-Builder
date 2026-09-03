"""Testy oceny jakości transkrypcji: obrona przed halucynacjami Whispera.

Wszystkie testy są czyste: operują na sztucznych segmentach, nie wołają modelu.
"""

from __future__ import annotations

from gnb.audio.ocena import (
    OCENA_TRANSKRYPCJI_PODEJRZANA,
    OCENA_TRANSKRYPCJI_POPRAWNA,
    ocen_transkrypcje,
)
from gnb.audio.transkrypcja import SegmentTranskrypcji


def _segment(
    tekst: str,
    *,
    poczatek: float = 0.0,
    logprob: float = -0.2,
    brak_mowy: float = 0.05,
) -> SegmentTranskrypcji:
    return SegmentTranskrypcji(
        poczatek_sekundy=poczatek,
        koniec_sekundy=poczatek + 3.0,
        tekst=tekst,
        prawdopodobienstwo_logarytmiczne=logprob,
        prawdopodobienstwo_braku_mowy=brak_mowy,
    )


def test_zwykla_transkrypcja_jest_poprawna() -> None:
    segmenty = [
        _segment("Dzień dobry, zaczynamy wykład."),
        _segment("Dziś porozmawiamy o architekturze potoku.", poczatek=3.0),
        _segment("Pierwszy etap to walidacja wejścia.", poczatek=6.0),
    ]

    ocena = ocen_transkrypcje(segmenty)

    assert ocena.ocena == OCENA_TRANSKRYPCJI_POPRAWNA
    assert ocena.czy_podejrzana is False


def test_powtorzona_fraza_daje_ocene_podejrzana() -> None:
    """Model utknięty na pętli zwraca ten sam segment wiele razy — to halucynacja."""
    segmenty = [_segment("Dziękuję za uwagę.", poczatek=float(i)) for i in range(4)]

    ocena = ocen_transkrypcje(segmenty)

    assert ocena.ocena == OCENA_TRANSKRYPCJI_PODEJRZANA
    assert any("powtarza się" in powod for powod in ocena.powody)


def test_dwa_powtorzenia_nie_wystarczaja() -> None:
    """Dwa identyczne segmenty bywają naturalne, więc nie są jeszcze sygnałem.

    Test czerwieni się, gdyby próg powtórzeń spadł do dwóch i zaczął fałszywie
    oznaczać naturalne powtórzenia w mowie.
    """
    segmenty = [
        _segment("Tak."),
        _segment("Tak.", poczatek=3.0),
        _segment("Przejdźmy dalej do kolejnego punktu.", poczatek=6.0),
    ]

    assert ocen_transkrypcje(segmenty).ocena == OCENA_TRANSKRYPCJI_POPRAWNA


def test_duzo_segmentow_niskiej_pewnosci_daje_ocene_podejrzana() -> None:
    segmenty = [
        _segment("fragment pierwszy", logprob=-2.5),
        _segment("fragment drugi", poczatek=3.0, brak_mowy=0.9),
        _segment("fragment trzeci", poczatek=6.0, logprob=-3.0),
        _segment("fragment czwarty wyraźny", poczatek=9.0),
    ]

    ocena = ocen_transkrypcje(segmenty)

    assert ocena.ocena == OCENA_TRANSKRYPCJI_PODEJRZANA
    assert any("niską pewność" in powod for powod in ocena.powody)


def test_pojedynczy_slaby_segment_nie_przechyla_oceny() -> None:
    segmenty = [
        _segment("fragment słaby", logprob=-2.5),
        _segment("fragment wyraźny drugi", poczatek=3.0),
        _segment("fragment wyraźny trzeci", poczatek=6.0),
        _segment("fragment wyraźny czwarty", poczatek=9.0),
    ]

    assert ocen_transkrypcje(segmenty).ocena == OCENA_TRANSKRYPCJI_POPRAWNA


def test_pusta_lista_segmentow_jest_poprawna() -> None:
    assert ocen_transkrypcje([]).ocena == OCENA_TRANSKRYPCJI_POPRAWNA
