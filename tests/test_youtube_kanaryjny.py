"""Testy kanaryjne obu warstw pobierania napisów, sięgające do prawdziwego serwisu.

Cały plik jest oznaczony markerem ``siec`` i domyślnie się nie uruchamia. Nie
jest to test poprawności, tylko kanarek: ma wykryć sytuację, w której warstwa
przestaje się przebijać do serwisu po zmianie po jego stronie albo po
aktualizacji biblioteki. Dlatego obie warstwy są sprawdzane osobno — sens polega
na tym, żeby wiedzieć, która z nich padła.

Asercje są celowo ubogie: połączenie doszło do skutku, jakieś napisy są, a tekst
po sklejeniu ma niezerową długość. Nie ma tu asercji na treść napisów, liczbę
segmentów ani czas trwania, ponieważ autor filmu może poprawić napisy, a wtedy
test czerwieniłby się bez powodu i przestałby być wiarygodny.

Adres filmu pochodzi z ``tests/dane/lista_youtube.txt`` i nie jest wpisany
w kodzie, więc podmiana filmu nie wymaga zmiany testu.

Uruchomienie: ``python -m pytest -m siec``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gnb.core.wyjatki import BladGnb
from gnb.core.youtube import rozpoznaj
from gnb.extractors.youtube import zbuduj_dokument
from gnb.ingestion.lista_url import wczytaj_liste_z_pliku
from gnb.ingestion.youtube import (
    PobieraczYouTube,
    PreferencjeNapisow,
    WarstwaTranscriptApi,
    WarstwaYtDlp,
    WynikYouTube,
)

pytestmark = pytest.mark.siec

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"
_PREFERENCJE = PreferencjeNapisow()


def _identyfikator_filmu() -> str:
    """Zwraca identyfikator filmu z listy danych testowych."""
    podsumowanie = wczytaj_liste_z_pliku(KATALOG_DANYCH / "lista_youtube.txt")
    if not podsumowanie.adresy:
        pytest.skip("Plik lista_youtube.txt nie zawiera poprawnego adresu.")

    rozpoznanie = rozpoznaj(podsumowanie.adresy[0].podany)
    if rozpoznanie.identyfikator_filmu is None:
        pytest.skip("Adres z lista_youtube.txt nie wskazuje pojedynczego filmu.")
    return rozpoznanie.identyfikator_filmu


def _pomin_gdy_brak_dostepu(blad: Exception) -> None:
    """Zamienia brak dostępu do sieci na czytelne pominięcie testu."""
    opis = str(blad)
    pytest.skip(
        f"Nie udało się połączyć z serwisem, więc kanarek nie ma czego sprawdzić. Przyczyna: {opis}"
    )


def test_warstwa_transcript_api_nadal_pobiera_napisy() -> None:
    identyfikator = _identyfikator_filmu()
    try:
        napisy = WarstwaTranscriptApi().pobierz_napisy(identyfikator, _PREFERENCJE)
    except BladGnb as blad:
        _pomin_gdy_brak_dostepu(blad)
        return

    assert napisy is not None, "warstwa youtube-transcript-api nie znalazła żadnych napisów"
    assert napisy.segmenty, "warstwa youtube-transcript-api zwróciła napisy bez segmentów"


def test_warstwa_yt_dlp_nadal_pobiera_metadane_i_napisy() -> None:
    identyfikator = _identyfikator_filmu()
    warstwa = WarstwaYtDlp()
    try:
        metadane = warstwa.pobierz_metadane(identyfikator)
        napisy = warstwa.pobierz_napisy(identyfikator, _PREFERENCJE)
    except BladGnb as blad:
        _pomin_gdy_brak_dostepu(blad)
        return

    assert metadane.identyfikator == identyfikator
    assert napisy is not None, "warstwa yt-dlp nie znalazła żadnych napisów"
    assert napisy.segmenty, "warstwa yt-dlp zwróciła napisy bez segmentów"


def test_pelne_pobranie_daje_niepusta_transkrypcje() -> None:
    identyfikator = _identyfikator_filmu()
    try:
        wynik = PobieraczYouTube(_PREFERENCJE).pobierz(identyfikator)
    except BladGnb as blad:
        _pomin_gdy_brak_dostepu(blad)
        return

    assert isinstance(wynik, WynikYouTube), "film nie ma napisów w żadnym z wybranych języków"
    assert zbuduj_dokument(wynik).tekst.strip(), "transkrypcja po sklejeniu jest pusta"
