"""Testy rozpoznawania adresów serwisu YouTube.

Testy nie korzystają z sieci. Pracują wyłącznie na napisach adresów.
"""

from __future__ import annotations

import pytest

from gnb.core.youtube import (
    AdresYouTube,
    RodzajAdresuYouTube,
    adres_kanoniczny_filmu,
    czy_adres_youtube,
    rozpoznaj,
)

_IDENTYFIKATOR = "iG9CE55wbtY"
_KANONICZNY = "https://www.youtube.com/watch?v=iG9CE55wbtY"


@pytest.mark.parametrize(
    "adres",
    [
        "https://www.youtube.com/watch?v=iG9CE55wbtY",
        "https://youtube.com/watch?v=iG9CE55wbtY",
        "https://m.youtube.com/watch?v=iG9CE55wbtY",
        "https://music.youtube.com/watch?v=iG9CE55wbtY",
        "https://youtu.be/iG9CE55wbtY",
        "https://www.youtube.com/shorts/iG9CE55wbtY",
        "https://www.youtube.com/live/iG9CE55wbtY",
        "https://www.youtube.com/embed/iG9CE55wbtY",
        "https://www.youtube-nocookie.com/embed/iG9CE55wbtY",
        "https://www.youtube.com/v/iG9CE55wbtY",
    ],
)
def test_wszystkie_postacie_adresu_daja_ten_sam_adres_kanoniczny(adres: str) -> None:
    wynik = rozpoznaj(adres)

    assert wynik.czy_film is True
    assert wynik.identyfikator_filmu == _IDENTYFIKATOR
    assert wynik.adres_kanoniczny == _KANONICZNY


def test_adres_filmu_z_numerem_playlisty_jest_zwyklym_filmem() -> None:
    wynik = rozpoznaj("https://www.youtube.com/watch?v=iG9CE55wbtY&list=PL1234567890abcdef")

    assert wynik.czy_film is True
    assert wynik.adres_kanoniczny == _KANONICZNY


def test_parametry_towarzyszace_nie_wchodza_do_postaci_kanonicznej() -> None:
    wynik = rozpoznaj("https://www.youtube.com/watch?v=iG9CE55wbtY&t=142s&index=3&utm_source=x")

    assert wynik.adres_kanoniczny == _KANONICZNY


def test_adres_skrocony_z_momentem_startu_jest_filmem() -> None:
    wynik = rozpoznaj("https://youtu.be/iG9CE55wbtY?t=90")

    assert wynik.czy_film is True
    assert wynik.adres_kanoniczny == _KANONICZNY


def test_playlista_jest_odrzucana_z_konkretnym_powodem() -> None:
    wynik = rozpoznaj("https://www.youtube.com/playlist?list=PL1234567890abcdef")

    assert wynik.rodzaj is RodzajAdresuYouTube.PLAYLISTA
    assert wynik.identyfikator_filmu is None
    assert "playlistę" in (wynik.powod_odrzucenia or "")
    assert "adresy poszczególnych filmów" in (wynik.powod_odrzucenia or "")


@pytest.mark.parametrize(
    "adres",
    [
        "https://www.youtube.com/@nazwakanalu",
        "https://www.youtube.com/@nazwakanalu/videos",
        "https://www.youtube.com/@nazwakanalu/streams",
        "https://www.youtube.com/@nazwakanalu/shorts",
        "https://www.youtube.com/c/nazwakanalu",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv",
        "https://www.youtube.com/channel/UCabcdefghijklmnopqrstuv/videos",
        "https://www.youtube.com/user/nazwauzytkownika",
    ],
)
def test_kanal_jest_odrzucany_z_konkretnym_powodem(adres: str) -> None:
    wynik = rozpoznaj(adres)

    assert wynik.rodzaj is RodzajAdresuYouTube.KANAL
    assert "kanał" in (wynik.powod_odrzucenia or "")
    assert "adresy poszczególnych filmów" in (wynik.powod_odrzucenia or "")


def test_zakladka_kanalu_nie_jest_mylona_z_filmem_krotkim() -> None:
    kanal = rozpoznaj("https://www.youtube.com/@nazwakanalu/shorts")
    film = rozpoznaj("https://www.youtube.com/shorts/iG9CE55wbtY")

    assert kanal.rodzaj is RodzajAdresuYouTube.KANAL
    assert film.czy_film is True


@pytest.mark.parametrize(
    "adres",
    [
        "https://www.youtube.com/",
        "https://www.youtube.com/feed/subscriptions",
        "https://www.youtube.com/watch?v=zakrotki",
        "https://www.youtube.com/watch",
        "https://youtu.be/",
        "https://www.youtube.com/shorts/",
    ],
)
def test_adres_bez_identyfikatora_filmu_jest_nierozpoznany(adres: str) -> None:
    wynik = rozpoznaj(adres)

    assert wynik.rodzaj is RodzajAdresuYouTube.NIEROZPOZNANY
    assert wynik.identyfikator_filmu is None
    assert "IDENTYFIKATOR" in (wynik.powod_odrzucenia or "")


def test_adres_spoza_serwisu_jest_nierozpoznany() -> None:
    assert rozpoznaj("https://przyklad.pl/watch?v=iG9CE55wbtY").rodzaj is (
        RodzajAdresuYouTube.NIEROZPOZNANY
    )


@pytest.mark.parametrize(
    ("adres", "oczekiwane"),
    [
        ("https://www.youtube.com/watch?v=iG9CE55wbtY", True),
        ("https://youtu.be/iG9CE55wbtY", True),
        ("https://www.youtube.com/@nazwakanalu", True),
        ("https://przyklad.pl/artykul", False),
        ("https://niby-youtube.com/watch?v=iG9CE55wbtY", False),
    ],
)
def test_rozpoznanie_przynaleznosci_do_serwisu(adres: str, oczekiwane: bool) -> None:
    assert czy_adres_youtube(adres) is oczekiwane


def test_adres_kanoniczny_powstaje_z_samego_identyfikatora() -> None:
    assert adres_kanoniczny_filmu(_IDENTYFIKATOR) == _KANONICZNY


def test_wynik_rozpoznania_jest_niezmienny() -> None:
    wynik = rozpoznaj("https://youtu.be/iG9CE55wbtY")
    assert isinstance(wynik, AdresYouTube)
    with pytest.raises(AttributeError):
        wynik.identyfikator_filmu = "inny"  # type: ignore[misc]
