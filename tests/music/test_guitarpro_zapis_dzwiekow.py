"""Testy zapisu dźwięków ścieżki strunowej i naprawy odczytu tonacji, etap trzynasty.

Plik testowy jest budowany w locie przez `guitarpro.write`, ten sam silnik,
którym go odczytujemy przez `guitarpro.parse` — nie jest to więc niezależna
weryfikacja poprawności samej biblioteki PyGuitarPro, tylko naszej warstwy
opisu przy założeniu, że biblioteka odczytała plik poprawnie. Gdyby obie
strony obiegu miały ten sam błąd, test by go nie wykrył. Alternatywą byłoby
wstawienie do publicznego repozytorium cudzego pliku z prawdziwym repertuarem,
czego unikamy — ten sam kompromis widoczny już w plikach `tabulatura_*`
w `tests/dane`, wziętych z zestawu testowego samej biblioteki.

Fixture ma cztery struny w stroju standardowego basu (E1, A1, D2, G2), nazwę
ścieżki i numer instrumentu General MIDI, które niczego o basie nie mówią —
dokładnie ten przypadek, który uniemożliwił rozpoznanie „to jest bas” po
nazwie albo numerze instrumentu na prawdziwym pliku z repertuaru użytkownika.
"""

from __future__ import annotations

import io

import pytest

from gnb.music.guitarpro import przeczytaj_guitarpro

guitarpro = pytest.importorskip("guitarpro")

pytestmark = pytest.mark.usefixtures("wymaga_pyguitarpro")

_STRUNY_BASU = ((1, 43), (2, 38), (3, 33), (4, 28))  # G2, D2, A1, E1


def _nuta(voice: object, *, string: int, fret: int, wartosc: int, kropka: bool = False) -> object:
    beat = guitarpro.Beat(voice, status=guitarpro.BeatStatus.normal)
    beat.duration = guitarpro.Duration(value=wartosc, isDotted=kropka)
    nuta = guitarpro.Note(beat, value=fret, string=string, type=guitarpro.NoteType.normal)
    beat.notes = [nuta]
    return beat


def _pauza(voice: object, *, wartosc: int) -> object:
    beat = guitarpro.Beat(voice, status=guitarpro.BeatStatus.rest)
    beat.duration = guitarpro.Duration(value=wartosc)
    beat.notes = []
    return beat


def _takt_basu(track: object, naglowek: object, uderzenia_budowniczy: object) -> object:
    """Buduje jeden takt z pojedynczym głosem, drugi głos zostaje pusty."""
    measure = guitarpro.Measure(track, naglowek)
    voice = guitarpro.Voice(measure)
    voice.beats = uderzenia_budowniczy(voice)
    measure.voices = [voice, guitarpro.Voice(measure)]
    return measure


def _zbuduj_bajty_utworu(*, nazwa_sciezki: str = "Track 1", instrument_gm: int = 28) -> bytes:
    """Buduje plik gp5 ze ścieżką basową, którą nazwa i instrument by nie zdradziły.

    Cztery takty: pierwsze trzy identyczne (test zwijania powtórzeń), czwarty
    inny (test, że zwijanie zatrzymuje się na pierwszej różnicy). Pierwszy
    nagłówek taktu niesie jawną tonację e-moll, żeby sprawdzić naprawę odczytu
    tonacji opisaną w sekcji piętnastej CLAUDE.md — pole `Song.key` biblioteki
    PyGuitarPro nigdy nie zwróci trybu molowego, więc bez tej naprawy test by
    nie przeszedł.
    """
    song = guitarpro.Song()
    naglowki = [guitarpro.MeasureHeader(number=numer) for numer in range(1, 5)]
    naglowki[0].keySignature = guitarpro.KeySignature((1, 1))  # e-moll
    song.measureHeaders = naglowki

    track = guitarpro.Track(song, number=1, name=nazwa_sciezki)
    track.strings = [guitarpro.GuitarString(numer, wartosc) for numer, wartosc in _STRUNY_BASU]
    track.channel.instrument = instrument_gm

    def takt_powtarzalny(voice: object) -> list[object]:
        return [
            _nuta(voice, string=4, fret=3, wartosc=4),
            _nuta(voice, string=3, fret=2, wartosc=8),
            _pauza(voice, wartosc=8),
        ]

    measures = [_takt_basu(track, naglowki[i], takt_powtarzalny) for i in range(3)]
    measures.append(
        _takt_basu(track, naglowki[3], lambda voice: [_nuta(voice, string=1, fret=0, wartosc=2)])
    )
    track.measures = measures
    song.tracks = [track]

    bufor = io.BytesIO()
    guitarpro.write(song, bufor, version=(5, 1, 0))
    return bufor.getvalue()


def test_zapis_dzwiekow_ma_wlasciwe_struny_progi_dzwieki_i_rytm() -> None:
    opis = przeczytaj_guitarpro(_zbuduj_bajty_utworu())

    assert len(opis.zapis_dzwiekow) == 1
    sciezka = opis.zapis_dzwiekow[0]
    assert sciezka.nazwa_sciezki == "Track 1"
    assert sciezka.strojenie == ("E1", "A1", "D2", "G2")
    assert sciezka.takty[0] == (
        "Takt 1: struna E, próg 3, G1, ćwierćnuta; struna A, próg 2, H1, ósemka; pauza ósemka"
    )


def test_zapis_dzwiekow_zwija_bezposrednio_sasiadujace_identyczne_takty() -> None:
    opis = przeczytaj_guitarpro(_zbuduj_bajty_utworu())
    takty = opis.zapis_dzwiekow[0].takty

    assert takty[1] == "Takty 2-3: jak takt 1."
    assert takty[2] == "Takt 4: struna G, pusta struna, G2, półnuta"
    assert len(takty) == 3, "trzy identyczne takty i jeden różny mają dać trzy wiersze, nie cztery"


def test_tonacja_z_naglowka_pierwszego_taktu_daje_prawdziwy_tryb_molowy() -> None:
    """Naprawa usterki: `Song.key` nigdy nie zwraca molu, nagłówek taktu — owszem.

    Bez odczytu z `measureHeaders[0].keySignature` ten test dostałby `None`
    (bo `Song.key` biblioteki PyGuitarPro dla żadnej wersji formatu nie może
    zwrócić trybu molowego — sprawdzone bezpośrednio w źródle biblioteki), nie
    „e-moll”, mimo że plik jawnie zapisuje e-moll w nagłówku pierwszego taktu.
    """
    opis = przeczytaj_guitarpro(_zbuduj_bajty_utworu())
    assert opis.tonacja == "e-moll"


def test_brak_kolizji_liter_daje_nazwy_strun_bez_oktawy() -> None:
    """Cztery struny basu standardowego mają różne litery, więc nazwa jest bez oktawy."""
    opis = przeczytaj_guitarpro(_zbuduj_bajty_utworu())
    assert "struna E," in opis.zapis_dzwiekow[0].takty[0]
    assert "struna E1," not in opis.zapis_dzwiekow[0].takty[0]


def test_kolizja_liter_dodaje_oktawe_do_wszystkich_strun_sciezki() -> None:
    """Dwie struny tej samej litery (na przykład strój obniżony) wymuszają oktawę.

    Bez tego dwie różne struny nazywałyby się identycznie „struna E” i nie dałoby
    się z tekstu ustalić, którą z nich naprawdę zagrano — cichy błąd poprawności
    danych, którego dotyczy decyzja piąta ze zgłoszenia etapu trzynastego.
    """
    song = guitarpro.Song()
    naglowek = guitarpro.MeasureHeader(number=1)
    song.measureHeaders = [naglowek]
    track = guitarpro.Track(song, number=1, name="Kolizja")
    # Dwie struny E w różnych oktawach: E1 (28) i E2 (40).
    track.strings = [guitarpro.GuitarString(1, 40), guitarpro.GuitarString(2, 28)]
    measure = guitarpro.Measure(track, naglowek)
    voice = guitarpro.Voice(measure)
    voice.beats = [
        _nuta(voice, string=1, fret=0, wartosc=4),
        _nuta(voice, string=2, fret=0, wartosc=4),
    ]
    measure.voices = [voice, guitarpro.Voice(measure)]
    track.measures = [measure]
    song.tracks = [track]

    bufor = io.BytesIO()
    guitarpro.write(song, bufor, version=(5, 1, 0))

    opis = przeczytaj_guitarpro(bufor.getvalue())
    takt = opis.zapis_dzwiekow[0].takty[0]
    assert "struna E2, pusta struna, E2, ćwierćnuta" in takt
    assert "struna E1, pusta struna, E1, ćwierćnuta" in takt


def test_zapis_dzwiekow_wylaczony_daje_pusta_liste() -> None:
    opis = przeczytaj_guitarpro(_zbuduj_bajty_utworu(), zapis_dzwiekow_wlaczony=False)
    assert opis.zapis_dzwiekow == []
