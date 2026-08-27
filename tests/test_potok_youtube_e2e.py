"""Test end-to-end potoku dla filmów z serwisu YouTube, bez sieci.

Warstwy pobierania napisów są podstawione danymi sztucznymi, a transport HTTP
sztucznym transportem. Dzięki temu cały przebieg — rozpoznanie adresu, pobranie
napisów, ekstrakcja, zapis, manifest, checkpoint i raport — jest sprawdzany
deterministycznie i bez połączenia z internetem.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.wyjatki import BladTrwaly
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_url
from gnb.ingestion.youtube import (
    TYP_NAPISOW_AUTOMATYCZNE,
    TYP_NAPISOW_RECZNE,
    MetadaneFilmu,
    Napisy,
    PobieraczYouTube,
    PreferencjeNapisow,
    SegmentNapisow,
)
from gnb.potok import przetworz_projekt

_IDENTYFIKATOR = "iG9CE55wbtY"
_ADRES = "https://www.youtube.com/watch?v=iG9CE55wbtY"
_ADRES_SKROCONY = "https://youtu.be/iG9CE55wbtY"
_ADRES_PLAYLISTY = "https://www.youtube.com/playlist?list=PL1234567890abcdef"
_ADRES_KANALU = "https://www.youtube.com/@nazwakanalu"
_MOMENT = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 8, 26, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _konfiguracja(tmp_path: Path, **nadpisania: object) -> Konfiguracja:
    domyslne: dict[str, object] = {
        "katalog_wynikow": tmp_path / "wyniki",
        "sciezka_cache": tmp_path / "cache.sqlite3",
        "uzywaj_cache": False,
        "respektuj_robots": False,
        "odstep_miedzy_zadaniami_sekundy": 0.0,
        "liczba_ponowien": 0,
    }
    domyslne.update(nadpisania)
    return Konfiguracja(**domyslne)  # type: ignore[arg-type]


def _transport_bez_regul() -> httpx.MockTransport:
    """Transport odpowiadający brakiem reguł na pytanie o plik robots.txt."""

    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    return httpx.MockTransport(obsluga)


def _transport_z_zakazem() -> httpx.MockTransport:
    def obsluga(zadanie: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /")

    return httpx.MockTransport(obsluga)


_SEGMENTY = (
    SegmentNapisow(0.0, "Baza wiedzy dla asystenta jest tym lepsza,"),
    SegmentNapisow(4.0, "im mniej zawiera powtórzeń."),
    SegmentNapisow(75.0, "Drugi wątek wykładu dotyczy pochodzenia materiałów."),
)


class _WarstwaNapisowAtrapa:
    """Atrapa warstwy napisów, sterowana słownikiem identyfikator filmu na wynik."""

    nazwa = "atrapa-napisow"

    def __init__(self, wyniki: dict[str, Napisy | None | Exception]) -> None:
        self.wywolania: list[str] = []
        self._wyniki = wyniki

    def pobierz_napisy(
        self, identyfikator_filmu: str, preferencje: PreferencjeNapisow
    ) -> Napisy | None:
        self.wywolania.append(identyfikator_filmu)
        wynik = self._wyniki.get(identyfikator_filmu)
        if isinstance(wynik, Exception):
            raise wynik
        return wynik


class _WarstwaMetadanychAtrapa:
    """Atrapa warstwy metadanych, sterowana słownikiem identyfikator filmu na wynik."""

    nazwa = "atrapa-metadanych"

    def __init__(self, wyniki: dict[str, MetadaneFilmu | Exception]) -> None:
        self._wyniki = wyniki

    def pobierz_metadane(self, identyfikator_filmu: str) -> MetadaneFilmu:
        wynik = self._wyniki.get(identyfikator_filmu)
        if isinstance(wynik, Exception):
            raise wynik
        return wynik or MetadaneFilmu(identyfikator=identyfikator_filmu)


def _metadane() -> MetadaneFilmu:
    return MetadaneFilmu(
        identyfikator=_IDENTYFIKATOR,
        tytul="Jak przygotować bazę wiedzy",
        kanal="Kanał testowy",
        dlugosc_sekundy=930,
        data_publikacji="2026-03-01",
    )


def _pobieracz(
    napisy: Napisy | Exception | None = None,
    metadane: MetadaneFilmu | Exception | None = None,
    *,
    bez_napisow: bool = False,
) -> tuple[PobieraczYouTube, _WarstwaNapisowAtrapa]:
    """Buduje pobieracz z podstawionymi warstwami.

    Wartość pusta w argumencie `napisy` oznacza użycie napisów domyślnych.
    Film bez napisów wskazuje osobny argument `bez_napisow`, żeby nie mylić tych
    dwóch przypadków.
    """
    wybrane: Napisy | Exception | None = None if bez_napisow else (napisy or _napisy_reczne())
    warstwa = _WarstwaNapisowAtrapa({_IDENTYFIKATOR: wybrane})
    return (
        PobieraczYouTube(
            warstwy_napisow=(warstwa,),  # type: ignore[arg-type]
            warstwa_metadanych=_WarstwaMetadanychAtrapa(  # type: ignore[arg-type]
                {_IDENTYFIKATOR: metadane if metadane is not None else _metadane()}
            ),
        ),
        warstwa,
    )


def _napisy_reczne() -> Napisy:
    return Napisy(jezyk="pl", typ=TYP_NAPISOW_RECZNE, segmenty=_SEGMENTY, metoda="atrapa")


def _pozycje(*adresy: str) -> list[PozycjaWejsciowa]:
    return [przyjmij_url(adres, _MOMENT) for adres in adresy]


def _uruchom(
    tmp_path: Path,
    adresy: tuple[str, ...] = (_ADRES,),
    *,
    pobieracz: PobieraczYouTube | None = None,
    nazwa: str = "Test YouTube",
    transport: httpx.MockTransport | None = None,
    **konfiguracja: object,
) -> object:
    return przetworz_projekt(
        _pozycje(*adresy),
        _konfiguracja(tmp_path, **konfiguracja),
        nazwa_projektu=nazwa,
        zegar=_zegar_krokowy(),
        transport_http=transport or _transport_bez_regul(),
        pobieracz_youtube=pobieracz or _pobieracz()[0],
    )


def test_film_z_napisami_przechodzi_caly_potok(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path)

    assert wynik.liczba_przetworzonych == 1  # type: ignore[attr-defined]
    assert wynik.liczba_bledow == 0  # type: ignore[attr-defined]

    katalog = wynik.katalog_projektu / "pliki_wynikowe"  # type: ignore[attr-defined]
    pliki = sorted(plik.name for plik in katalog.iterdir())
    assert len(pliki) == 1, "transkrypcja nie dostaje wersji MD"
    assert pliki[0].endswith(".txt")

    tresc = (katalog / pliki[0]).read_text(encoding="utf-8")
    assert "Baza wiedzy dla asystenta jest tym lepsza, im mniej zawiera powtórzeń." in tresc
    assert "[" not in tresc


def test_metadane_filmu_trafiaja_do_manifestu(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path)

    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    metadane = zrodlo["metadane"]

    assert zrodlo["typ"] == "youtube"
    assert zrodlo["pochodzenie"] == _ADRES
    assert metadane["tytul"] == "Jak przygotować bazę wiedzy"
    assert metadane["kanal"] == "Kanał testowy"
    assert metadane["jezyk_napisow"] == "pl"
    assert metadane["typ_napisow"] == TYP_NAPISOW_RECZNE
    assert metadane["identyfikator_filmu"] == _IDENTYFIKATOR
    assert metadane["dlugosc_sekundy"] == "930"
    assert metadane["adres_kanoniczny"] == _ADRES


def test_tytul_filmu_staje_sie_nazwa_pliku(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path)

    katalog = wynik.katalog_projektu / "pliki_wynikowe"  # type: ignore[attr-defined]
    (plik,) = katalog.iterdir()
    assert plik.name.startswith("jak_przygotować_bazę_wiedzy__")


def test_oryginal_napisow_jest_zachowany_jako_plik_json(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path)

    materialy = list(
        (wynik.katalog_projektu / "materialy_zrodlowe").iterdir()  # type: ignore[attr-defined]
    )
    assert len(materialy) == 1
    assert materialy[0].suffix == ".json"
    zapisane = json.loads(materialy[0].read_text(encoding="utf-8"))
    assert zapisane["napisy"]["jezyk"] == "pl"
    assert len(zapisane["napisy"]["segmenty"]) == 3


def test_wlaczone_znaczniki_czasu_pojawiaja_sie_w_pliku(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path, znaczniki_czasu=True)

    katalog = wynik.katalog_projektu / "pliki_wynikowe"  # type: ignore[attr-defined]
    (plik,) = katalog.iterdir()
    tresc = plik.read_text(encoding="utf-8")

    assert tresc.startswith("[00:00] ")


def test_film_bez_napisow_jest_pomijany_z_odeslaniem_do_etapu_dziewiatego(
    tmp_path: Path,
) -> None:
    pobieracz, _ = _pobieracz(bez_napisow=True)
    wynik = _uruchom(tmp_path, pobieracz=pobieracz, nazwa="Test bez napisów")

    assert wynik.liczba_pominietych == 1  # type: ignore[attr-defined]
    assert wynik.liczba_bledow == 0  # type: ignore[attr-defined]

    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert zrodlo["status"] == "pominiete"
    assert "etapie dziewiątym" in zrodlo["komunikat_bledu"]


def test_film_prywatny_konczy_sie_statusem_blad(tmp_path: Path) -> None:
    pobieracz, _ = _pobieracz(napisy=BladTrwaly("Film jest prywatny."))
    wynik = _uruchom(tmp_path, pobieracz=pobieracz, nazwa="Test filmu prywatnego")

    assert wynik.liczba_bledow == 1  # type: ignore[attr-defined]
    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert zrodlo["status"] == "blad"
    assert "prywatny" in zrodlo["komunikat_bledu"]


def test_playlista_jest_pomijana_a_film_przetworzony(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path, (_ADRES, _ADRES_PLAYLISTY), nazwa="Test playlisty")

    assert wynik.liczba_przetworzonych == 1  # type: ignore[attr-defined]
    assert wynik.liczba_pominietych == 1  # type: ignore[attr-defined]

    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    pominiete = [zrodlo for zrodlo in manifest["zrodla"] if zrodlo["status"] == "pominiete"]
    assert len(pominiete) == 1
    assert "playlistę" in pominiete[0]["komunikat_bledu"]
    assert "adresy poszczególnych filmów" in pominiete[0]["komunikat_bledu"]


def test_kanal_jest_pomijany_z_wlasnym_powodem(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path, (_ADRES_KANALU,), nazwa="Test kanału")

    assert wynik.liczba_pominietych == 1  # type: ignore[attr-defined]
    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert "kanał" in zrodlo["komunikat_bledu"]


def test_powod_pominiecia_playlisty_trafia_do_raportu(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path, (_ADRES_PLAYLISTY,), nazwa="Test raportu playlisty")

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert "Źródła nieprzetworzone, liczba: 1" in raport
    assert "playlistę" in raport


def test_dwie_postacie_adresu_daja_jedno_zrodlo_i_jedno_pobranie(tmp_path: Path) -> None:
    pobieracz, warstwa = _pobieracz()
    wynik = _uruchom(
        tmp_path, (_ADRES, _ADRES_SKROCONY), pobieracz=pobieracz, nazwa="Test duplikatu filmu"
    )

    assert wynik.liczba_przetworzonych == 1  # type: ignore[attr-defined]
    assert warstwa.wywolania == [_IDENTYFIKATOR]


def test_wznowienie_nie_pobiera_napisow_ponownie(tmp_path: Path) -> None:
    pobieracz, warstwa = _pobieracz()
    konfiguracja = _konfiguracja(tmp_path)

    for _ in range(2):
        wynik = przetworz_projekt(
            _pozycje(_ADRES),
            konfiguracja,
            nazwa_projektu="Test wznowienia filmu",
            zegar=_zegar_krokowy(),
            transport_http=_transport_bez_regul(),
            pobieracz_youtube=pobieracz,
        )

    assert wynik.wznowiono is True
    assert warstwa.wywolania == [_IDENTYFIKATOR]


def test_pamiec_podreczna_oszczedza_pobranie_w_drugim_projekcie(tmp_path: Path) -> None:
    pobieracz, warstwa = _pobieracz()
    konfiguracja = _konfiguracja(tmp_path, uzywaj_cache=True)

    for nazwa in ("Pierwszy projekt", "Drugi projekt"):
        przetworz_projekt(
            _pozycje(_ADRES),
            konfiguracja,
            nazwa_projektu=nazwa,
            zegar=_zegar_krokowy(),
            transport_http=_transport_bez_regul(),
            pobieracz_youtube=pobieracz,
        )

    assert warstwa.wywolania == [_IDENTYFIKATOR]


def test_wylaczony_wyjatek_robots_pomija_film_zgodnie_z_regulami_witryny(
    tmp_path: Path,
) -> None:
    wynik = _uruchom(
        tmp_path,
        nazwa="Test robots dla filmu",
        transport=_transport_z_zakazem(),
        respektuj_robots=True,
        wyjatek_robots_dla_zrodel_jawnych=False,
    )

    assert wynik.liczba_pominietych == 1  # type: ignore[attr-defined]
    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert "robots.txt" in zrodlo["komunikat_bledu"]


def test_wyjatek_robots_pozwala_pobrac_film(tmp_path: Path) -> None:
    wynik = _uruchom(
        tmp_path,
        nazwa="Test wyjątku dla filmu",
        transport=_transport_z_zakazem(),
        respektuj_robots=True,
    )

    assert wynik.liczba_przetworzonych == 1  # type: ignore[attr-defined]


def test_napisy_automatyczne_sa_odnotowane_w_manifescie(tmp_path: Path) -> None:
    napisy = Napisy(jezyk="en", typ=TYP_NAPISOW_AUTOMATYCZNE, segmenty=_SEGMENTY, metoda="atrapa")
    pobieracz, _ = _pobieracz(napisy=napisy)

    wynik = _uruchom(tmp_path, pobieracz=pobieracz, nazwa="Test napisów automatycznych")

    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert zrodlo["metadane"]["typ_napisow"] == TYP_NAPISOW_AUTOMATYCZNE
    assert zrodlo["metadane"]["jezyk_napisow"] == "en"


def _log_wazny(wynik: object) -> str:
    """Zwraca treść pliku log_wazne.txt projektu."""
    katalog = wynik.katalog_projektu  # type: ignore[attr-defined]
    return (katalog / "logi" / "log_wazne.txt").read_text(encoding="utf-8")


def test_log_wazny_mowi_jakie_napisy_pobrano(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path, nazwa="Test logu napisów")

    log = _log_wazny(wynik)
    assert "Napisy wybrane: język pl, tworzone ręcznie" in log


def test_log_wazny_odnotowuje_napisy_automatyczne(tmp_path: Path) -> None:
    napisy = Napisy(jezyk="en", typ=TYP_NAPISOW_AUTOMATYCZNE, segmenty=_SEGMENTY, metoda="atrapa")
    pobieracz, _ = _pobieracz(napisy=napisy)

    wynik = _uruchom(tmp_path, pobieracz=pobieracz, nazwa="Test logu automatycznych")

    assert "Napisy wybrane: język en, automatyczne" in _log_wazny(wynik)


def test_napisy_w_innym_jezyku_sa_uzyte_i_zglaszane_w_logu(tmp_path: Path) -> None:
    napisy = Napisy(
        jezyk="de",
        typ=TYP_NAPISOW_RECZNE,
        segmenty=_SEGMENTY,
        metoda="atrapa",
        awaryjny_jezyk=True,
    )
    pobieracz, _ = _pobieracz(napisy=napisy)

    wynik = _uruchom(tmp_path, pobieracz=pobieracz, nazwa="Test języka awaryjnego")

    assert wynik.liczba_przetworzonych == 1  # type: ignore[attr-defined]

    log = _log_wazny(wynik)
    assert "Napisy wybrane: język de, tworzone ręcznie" in log
    assert "Uwaga, napisy w innym języku niż preferowane" in log
    assert "oczekiwano pl, en, pobrano de" in log
    assert "Jak przygotować bazę wiedzy" in log

    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert zrodlo["metadane"]["jezyk_napisow"] == "de"
    assert zrodlo["metadane"]["jezyk_awaryjny"] == "tak"


def test_napisy_w_preferowanym_jezyku_nie_daja_ostrzezenia(tmp_path: Path) -> None:
    wynik = _uruchom(tmp_path, nazwa="Test bez ostrzeżenia")

    assert "Uwaga, napisy w innym języku" not in _log_wazny(wynik)
    manifest = json.loads(
        wynik.sciezka_manifestu.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    )
    (zrodlo,) = manifest["zrodla"]
    assert "jezyk_awaryjny" not in zrodlo["metadane"]
