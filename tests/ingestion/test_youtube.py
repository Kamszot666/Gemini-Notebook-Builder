"""Testy pobierania napisów i metadanych filmu, prowadzone na danych sztucznych.

Żaden test w tym pliku nie korzysta z sieci. Warstwy pobierania są podstawiane
atrapami, a formaty napisów sprawdzane na przygotowanych fragmentach treści.
"""

from __future__ import annotations

import pytest

from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly
from gnb.ingestion.youtube import (
    TYP_NAPISOW_AUTOMATYCZNE,
    TYP_NAPISOW_RECZNE,
    MetadaneFilmu,
    Napisy,
    PobieraczYouTube,
    PominietyFilm,
    PreferencjeNapisow,
    SegmentNapisow,
    WynikYouTube,
    _segmenty_z_formatu,
    _wybierz_sciezke_yt_dlp,
)

_IDENTYFIKATOR = "iG9CE55wbtY"


def _napisy(jezyk: str = "pl", typ: str = TYP_NAPISOW_RECZNE) -> Napisy:
    return Napisy(
        jezyk=jezyk,
        typ=typ,
        segmenty=(
            SegmentNapisow(0.0, "Pierwsze zdanie."),
            SegmentNapisow(3.5, "Drugie zdanie."),
        ),
        metoda="atrapa",
    )


class _WarstwaNapisowAtrapa:
    """Atrapa warstwy napisów: zwraca przygotowany wynik albo zgłasza błąd."""

    def __init__(
        self, wynik: Napisy | None = None, blad: Exception | None = None, nazwa: str = "atrapa"
    ) -> None:
        self.nazwa = nazwa
        self.wywolania: list[str] = []
        self._wynik = wynik
        self._blad = blad

    def pobierz_napisy(
        self, identyfikator_filmu: str, preferencje: PreferencjeNapisow
    ) -> Napisy | None:
        self.wywolania.append(identyfikator_filmu)
        if self._blad is not None:
            raise self._blad
        return self._wynik


class _WarstwaMetadanychAtrapa:
    """Atrapa warstwy metadanych."""

    def __init__(
        self, metadane: MetadaneFilmu | None = None, blad: Exception | None = None
    ) -> None:
        self.nazwa = "atrapa-metadanych"
        self._metadane = metadane
        self._blad = blad

    def pobierz_metadane(self, identyfikator_filmu: str) -> MetadaneFilmu:
        if self._blad is not None:
            raise self._blad
        return self._metadane or MetadaneFilmu(identyfikator=identyfikator_filmu)


def _pobieracz(
    warstwy: tuple[_WarstwaNapisowAtrapa, ...],
    metadane: _WarstwaMetadanychAtrapa | None = None,
    preferencje: PreferencjeNapisow | None = None,
) -> PobieraczYouTube:
    return PobieraczYouTube(
        preferencje,
        warstwy_napisow=warstwy,  # type: ignore[arg-type]
        warstwa_metadanych=metadane or _WarstwaMetadanychAtrapa(),  # type: ignore[arg-type]
    )


def test_napisy_reczne_daja_pelny_wynik() -> None:
    metadane = MetadaneFilmu(
        identyfikator=_IDENTYFIKATOR,
        tytul="Wykład o bazach wiedzy",
        kanal="Kanał testowy",
        dlugosc_sekundy=930,
        data_publikacji="2026-03-01",
    )
    pobieracz = _pobieracz((_WarstwaNapisowAtrapa(_napisy()),), _WarstwaMetadanychAtrapa(metadane))

    wynik = pobieracz.pobierz(_IDENTYFIKATOR)

    assert isinstance(wynik, WynikYouTube)
    assert wynik.adres_kanoniczny == "https://www.youtube.com/watch?v=iG9CE55wbtY"
    assert wynik.metadane.tytul == "Wykład o bazach wiedzy"
    assert wynik.napisy.typ == TYP_NAPISOW_RECZNE
    assert wynik.napisy.jezyk == "pl"


def test_brak_napisow_konczy_sie_pominieciem_z_odeslaniem_do_etapu_dziewiatego() -> None:
    wynik = _pobieracz((_WarstwaNapisowAtrapa(None),)).pobierz(_IDENTYFIKATOR)

    assert isinstance(wynik, PominietyFilm)
    assert "etapie dziewiątym" in wynik.powod


def test_awaria_pierwszej_warstwy_przenosi_prace_na_druga() -> None:
    pierwsza = _WarstwaNapisowAtrapa(
        blad=BladPrzejsciowy("warstwa nie odpowiada"), nazwa="pierwsza"
    )
    druga = _WarstwaNapisowAtrapa(_napisy(typ=TYP_NAPISOW_AUTOMATYCZNE), nazwa="druga")

    wynik = _pobieracz((pierwsza, druga)).pobierz(_IDENTYFIKATOR)

    assert isinstance(wynik, WynikYouTube)
    assert wynik.napisy.typ == TYP_NAPISOW_AUTOMATYCZNE
    assert pierwsza.wywolania == [_IDENTYFIKATOR]
    assert druga.wywolania == [_IDENTYFIKATOR]


def test_brak_napisow_stwierdzony_przez_pierwsza_warstwe_konczy_poszukiwanie() -> None:
    pierwsza = _WarstwaNapisowAtrapa(None, nazwa="pierwsza")
    druga = _WarstwaNapisowAtrapa(_napisy(), nazwa="druga")

    wynik = _pobieracz((pierwsza, druga)).pobierz(_IDENTYFIKATOR)

    assert isinstance(wynik, PominietyFilm)
    assert druga.wywolania == []


def test_awaria_wszystkich_warstw_jest_bledem_przejsciowym() -> None:
    warstwy = (
        _WarstwaNapisowAtrapa(blad=BladPrzejsciowy("pierwsza padła"), nazwa="pierwsza"),
        _WarstwaNapisowAtrapa(blad=BladPrzejsciowy("druga padła"), nazwa="druga"),
    )

    with pytest.raises(BladPrzejsciowy, match="druga padła"):
        _pobieracz(warstwy).pobierz(_IDENTYFIKATOR)


def test_film_prywatny_jest_bledem_trwalym_i_nie_uruchamia_kolejnej_warstwy() -> None:
    pierwsza = _WarstwaNapisowAtrapa(blad=BladTrwaly("Film jest prywatny."), nazwa="pierwsza")
    druga = _WarstwaNapisowAtrapa(_napisy(), nazwa="druga")

    with pytest.raises(BladTrwaly, match="prywatny"):
        _pobieracz((pierwsza, druga)).pobierz(_IDENTYFIKATOR)
    assert druga.wywolania == []


def test_awaria_metadanych_nie_przekresla_napisow() -> None:
    pobieracz = _pobieracz(
        (_WarstwaNapisowAtrapa(_napisy()),),
        _WarstwaMetadanychAtrapa(blad=BladPrzejsciowy("brak danych filmu")),
    )

    wynik = pobieracz.pobierz(_IDENTYFIKATOR)

    assert isinstance(wynik, WynikYouTube)
    assert wynik.metadane.tytul is None
    assert wynik.metadane.identyfikator == _IDENTYFIKATOR


def test_film_niedostepny_wykryty_przy_metadanych_jest_bledem_trwalym() -> None:
    pobieracz = _pobieracz(
        (_WarstwaNapisowAtrapa(_napisy()),),
        _WarstwaMetadanychAtrapa(blad=BladTrwaly("Film jest niedostępny.")),
    )

    with pytest.raises(BladTrwaly, match="niedostępny"):
        pobieracz.pobierz(_IDENTYFIKATOR)


_JSON3 = """
{"events": [
  {"tStartMs": 0, "dDurationMs": 2000, "segs": [{"utf8": "Pierwsze "}, {"utf8": "zdanie."}]},
  {"tStartMs": 2500, "dDurationMs": 100, "segs": [{"utf8": "\\n"}]},
  {"tStartMs": 3500, "dDurationMs": 2000, "segs": [{"utf8": "Drugie zdanie."}]}
]}
"""

_VTT = """WEBVTT
Kind: captions
Language: pl

00:00:00.000 --> 00:00:02.000 align:start position:0%
Pierwsze zdanie.

00:00:03.500 --> 00:00:05.500
Drugie zdanie.
"""


def test_odczyt_segmentow_z_formatu_json3() -> None:
    segmenty = _segmenty_z_formatu("json3", _JSON3)

    assert [segment.tekst for segment in segmenty] == ["Pierwsze zdanie.", "Drugie zdanie."]
    assert segmenty[1].poczatek_sekundy == pytest.approx(3.5)


def test_odczyt_segmentow_z_formatu_vtt() -> None:
    segmenty = _segmenty_z_formatu("vtt", _VTT)

    assert [segment.tekst for segment in segmenty] == ["Pierwsze zdanie.", "Drugie zdanie."]
    assert segmenty[1].poczatek_sekundy == pytest.approx(3.5)


def test_segmenty_bez_tekstu_sa_pomijane_przy_odczycie() -> None:
    assert len(_segmenty_z_formatu("json3", _JSON3)) == 2


def test_uszkodzony_json3_daje_pusty_zestaw_segmentow() -> None:
    assert _segmenty_z_formatu("json3", "to nie jest JSON") == ()


def test_wybor_sciezki_yt_dlp_preferuje_reczne_przed_automatycznymi() -> None:
    informacje = {
        "subtitles": {"en": [{"ext": "json3", "url": "https://przyklad.pl/en.json3"}]},
        "automatic_captions": {"pl": [{"ext": "json3", "url": "https://przyklad.pl/pl.json3"}]},
    }

    wybor = _wybierz_sciezke_yt_dlp(informacje, PreferencjeNapisow(jezyki=("pl", "en")))

    assert wybor is not None
    jezyk, typ, _ = wybor
    assert (jezyk, typ) == ("en", TYP_NAPISOW_RECZNE)


def test_wybor_sciezki_yt_dlp_bierze_automatyczne_gdy_brak_recznych() -> None:
    informacje = {
        "subtitles": {},
        "automatic_captions": {"pl": [{"ext": "json3", "url": "https://przyklad.pl/pl.json3"}]},
    }

    wybor = _wybierz_sciezke_yt_dlp(informacje, PreferencjeNapisow(jezyki=("pl",)))

    assert wybor is not None
    jezyk, typ, _ = wybor
    assert (jezyk, typ) == ("pl", TYP_NAPISOW_AUTOMATYCZNE)


def test_wylaczone_napisy_automatyczne_daja_brak_wyboru() -> None:
    informacje = {
        "subtitles": {},
        "automatic_captions": {"pl": [{"ext": "json3", "url": "https://przyklad.pl/pl.json3"}]},
    }

    preferencje = PreferencjeNapisow(jezyki=("pl",), dopuszczaj_automatyczne=False)
    assert _wybierz_sciezke_yt_dlp(informacje, preferencje) is None


def test_wybor_sciezki_yt_dlp_woli_format_json3() -> None:
    informacje = {
        "subtitles": {
            "pl": [
                {"ext": "vtt", "url": "https://przyklad.pl/pl.vtt"},
                {"ext": "json3", "url": "https://przyklad.pl/pl.json3"},
            ]
        },
        "automatic_captions": {},
    }

    wybor = _wybierz_sciezke_yt_dlp(informacje, PreferencjeNapisow(jezyki=("pl",)))

    assert wybor is not None
    assert wybor[2]["ext"] == "json3"


def test_kolejnosc_jezykow_decyduje_o_wyborze() -> None:
    informacje = {
        "subtitles": {
            "en": [{"ext": "json3", "url": "https://przyklad.pl/en.json3"}],
            "pl": [{"ext": "json3", "url": "https://przyklad.pl/pl.json3"}],
        },
        "automatic_captions": {},
    }

    wybor = _wybierz_sciezke_yt_dlp(informacje, PreferencjeNapisow(jezyki=("pl", "en")))
    assert wybor is not None and wybor[0] == "pl"

    wybor = _wybierz_sciezke_yt_dlp(informacje, PreferencjeNapisow(jezyki=("en", "pl")))
    assert wybor is not None and wybor[0] == "en"
