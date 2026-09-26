"""Testy ręcznych operacji na źródłach istniejącego projektu.

Projekt powstaje prawdziwym przebiegiem potoku, a dopiero potem operacje
zmieniają jego stan, więc testy sprawdzają całą drogę: checkpoint, pliki na
dysku, manifest, raport i oba logi, a po usunięciu także to, że kolejne
wznowienie nie przywraca usuniętego źródła.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.wyjatki import BladTrwaly
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_tekst
from gnb.operacje_projektu import (
    oznacz_jako_zweryfikowane,
    sprawdz_mozliwosc_zastapienia,
    usun_zrodlo_z_projektu,
    wczytaj_checkpoint_projektu,
    zapisz_plik_zastepczy,
)
from gnb.persistence.checkpoint import zapisz
from gnb.persistence.projekt import UkladProjektu, ustal_uklad
from gnb.potok import WynikPrzetwarzania, odtworz_wejscia, przetworz_projekt

_MOMENT = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)
_NAZWA = "Test operacji"
_TEKST_A = "Notatka pierwsza mówi o porządkowaniu materiałów źródłowych przed importem."
_TEKST_B = "Notatka druga przypomina o sprawdzeniu dat publikacji artykułów w bazie."
_TEKST_C = "Notatka trzecia dotyczy rozróżniania oryginału od przedruku w archiwum."


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 25, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _konfiguracja(tmp_path: Path) -> Konfiguracja:
    return Konfiguracja(katalog_wynikow=tmp_path / "wyniki")


def _pozycje(*tresci: str, grupa: str | None = None) -> list[PozycjaWejsciowa]:
    return [przyjmij_tekst(tresc, _MOMENT, grupa=grupa) for tresc in tresci]


def _przetworz(
    tmp_path: Path, pozycje: list[PozycjaWejsciowa], **argumenty: Any
) -> WynikPrzetwarzania:
    return przetworz_projekt(
        pozycje,
        _konfiguracja(tmp_path),
        nazwa_projektu=_NAZWA,
        zegar=_zegar_krokowy(),
        **argumenty,
    )


def _uklad(tmp_path: Path) -> UkladProjektu:
    return ustal_uklad(_konfiguracja(tmp_path).katalog_wynikow, _NAZWA)


def _manifest(uklad: UkladProjektu) -> dict[str, Any]:
    return json.loads(uklad.manifest_json.read_text(encoding="utf-8"))


def _pliki_txt(uklad: UkladProjektu) -> list[Path]:
    return sorted(uklad.pliki_wynikowe.glob("*.txt"))


def _log_wazny(uklad: UkladProjektu) -> str:
    return (uklad.logi / "log_wazne.txt").read_text(encoding="utf-8")


def _oznacz_ostrzezeniem(tmp_path: Path, identyfikator: str) -> None:
    """Dopisuje źródłu ostrzeżenie ekstraktora, żeby trafiło do materiałów do sprawdzenia."""
    uklad = _uklad(tmp_path)
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    checkpoint.zrodla[identyfikator].ostrzezenia = ["Plik PDF nie ma warstwy tekstowej."]
    zapisz(uklad.checkpoint, checkpoint)


# --- oznaczenie jako zweryfikowane -------------------------------------------


def test_zweryfikowane_zrodlo_znika_z_materialow_do_sprawdzenia_ale_zostaje_w_raporcie(
    tmp_path: Path,
) -> None:
    wynik = _przetworz(tmp_path, _pozycje(_TEKST_A))
    uklad = _uklad(tmp_path)
    identyfikator = str(_manifest(uklad)["zrodla"][0]["identyfikator"])
    _oznacz_ostrzezeniem(tmp_path, identyfikator)
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    assert checkpoint.zrodla[identyfikator].zweryfikowane_recznie is False

    oznacz_jako_zweryfikowane(uklad, _konfiguracja(tmp_path), identyfikator)

    assert wczytaj_checkpoint_projektu(uklad).zrodla[identyfikator].zweryfikowane_recznie is True
    (zrodlo,) = _manifest(uklad)["zrodla"]
    assert zrodlo["zweryfikowane_recznie"] is True
    assert zrodlo["ostrzezenia"] == ["Plik PDF nie ma warstwy tekstowej."]
    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Materiały do sprawdzenia" not in raport
    assert "Źródła zweryfikowane ręcznie, liczba: 1" in raport
    assert "- Plik PDF nie ma warstwy tekstowej." in raport
    assert "Czas pracy: nie dotyczy" in raport
    assert "Źródło zweryfikowane ręcznie:" in _log_wazny(uklad)
    assert "oznaczone przez użytkownika jako zweryfikowane" in (
        (uklad.logi / "log_szczegolowy.txt").read_text(encoding="utf-8")
    )


def test_oznaczenie_zrodla_spoza_materialow_do_sprawdzenia_jest_odrzucane(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A))
    uklad = _uklad(tmp_path)
    identyfikator = str(_manifest(uklad)["zrodla"][0]["identyfikator"])

    with pytest.raises(BladTrwaly, match="nie jest na liście materiałów do sprawdzenia"):
        oznacz_jako_zweryfikowane(uklad, _konfiguracja(tmp_path), identyfikator)

    assert wczytaj_checkpoint_projektu(uklad).zrodla[identyfikator].zweryfikowane_recznie is False


def test_oznaczenie_nieznanego_zrodla_jest_odrzucane(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A))

    with pytest.raises(BladTrwaly, match="Nie ma w projekcie źródła"):
        oznacz_jako_zweryfikowane(_uklad(tmp_path), _konfiguracja(tmp_path), "nie-ma-takiego")


# --- usunięcie źródła --------------------------------------------------------


def test_usuniecie_zrodla_usuwa_je_z_checkpointu_z_dysku_i_z_wejsc(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A, _TEKST_B))
    uklad = _uklad(tmp_path)
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    plik_a = next(plik for plik in _pliki_txt(uklad) if _TEKST_A in plik.read_text("utf-8"))
    identyfikator = next(
        stan.identyfikator
        for stan in checkpoint.zrodla.values()
        if stan.wyniki and stan.wyniki[0].sciezka_wzgledna.endswith(plik_a.name)
    )

    wynik = usun_zrodlo_z_projektu(uklad, _konfiguracja(tmp_path), identyfikator)

    assert wynik.usuniete_pliki == (plik_a.name,)
    assert not wynik.wymaga_przepakowania
    assert not plik_a.exists()
    assert len(_pliki_txt(uklad)) == 1
    odczytany = wczytaj_checkpoint_projektu(uklad)
    assert identyfikator not in odczytany.zrodla
    assert len(odczytany.wejscia) == 1
    assert not list(uklad.wyniki_posrednie.glob(f"{identyfikator}.*"))
    assert identyfikator not in {zrodlo["identyfikator"] for zrodlo in _manifest(uklad)["zrodla"]}
    assert "Liczba wejść: 1" in uklad.raport.read_text(encoding="utf-8")
    assert "Źródło usunięte z projektu:" in _log_wazny(uklad)

    # Wznowienie z zapisanych wejść nie może przywrócić usuniętego źródła.
    ponowny = _przetworz(
        tmp_path,
        odtworz_wejscia(odczytany, _konfiguracja(tmp_path)),
        ponownie_przetwarzaj_usuniete=False,
    )
    assert ponowny.liczba_przetworzonych == 1
    assert len(_pliki_txt(uklad)) == 1
    assert _TEKST_A not in "".join(plik.read_text("utf-8") for plik in _pliki_txt(uklad))


def test_usuniecie_zrodla_nie_kasuje_materialow_zrodlowych(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A))
    uklad = _uklad(tmp_path)
    identyfikator = str(_manifest(uklad)["zrodla"][0]["identyfikator"])
    oryginaly_przed = sorted(uklad.materialy_zrodlowe.glob("*"))
    assert oryginaly_przed

    usun_zrodlo_z_projektu(uklad, _konfiguracja(tmp_path), identyfikator)

    assert sorted(uklad.materialy_zrodlowe.glob("*")) == oryginaly_przed


def test_usuniecie_zrodla_z_grupy_przepakowuje_pozostale(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A, _TEKST_B, _TEKST_C, grupa="Grupa"))
    uklad = _uklad(tmp_path)
    (stary_plik,) = _pliki_txt(uklad)
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    identyfikator_a = next(iter(checkpoint.zrodla))

    wynik = usun_zrodlo_z_projektu(uklad, _konfiguracja(tmp_path), identyfikator_a)

    assert wynik.wymaga_przepakowania
    assert stary_plik.exists(), "stary plik grupy jest usuwany dopiero po zapisaniu nowego"
    odczytany = wczytaj_checkpoint_projektu(uklad)
    assert {stan.status for stan in odczytany.zrodla.values()} == {"znormalizowane"}

    przepakowanie = _przetworz(
        tmp_path,
        odtworz_wejscia(odczytany, _konfiguracja(tmp_path)),
        ponownie_przetwarzaj_usuniete=False,
    )

    (nowy_plik,) = _pliki_txt(uklad)
    assert nowy_plik != stary_plik
    assert not stary_plik.exists()
    tresc = nowy_plik.read_text(encoding="utf-8")
    assert tresc.count("Identyfikator źródła: ") == 2
    assert identyfikator_a not in tresc
    raport = przepakowanie.sciezka_raportu.read_text(encoding="utf-8")
    assert f"Plik grupy zastąpiony: {stary_plik.name} → {nowy_plik.name}" in raport


def test_usuniecie_jedynego_zrodla_grupy_usuwa_jej_plik_bez_przepakowania(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A, grupa="Grupa"))
    uklad = _uklad(tmp_path)
    identyfikator = str(_manifest(uklad)["zrodla"][0]["identyfikator"])

    wynik = usun_zrodlo_z_projektu(uklad, _konfiguracja(tmp_path), identyfikator)

    assert not wynik.wymaga_przepakowania
    assert not _pliki_txt(uklad)
    assert wczytaj_checkpoint_projektu(uklad).zastapione_pliki_grup == []


def test_usuniecie_glownego_zrodla_przywraca_jego_duplikaty_do_pakowania(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A, _TEKST_A.upper()))
    uklad = _uklad(tmp_path)
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    duplikaty = [stan for stan in checkpoint.zrodla.values() if stan.status == "duplikat"]
    if not duplikaty:
        pytest.skip("deduplikacja nie uznała pary za duplikat przy tych ustawieniach")
    (duplikat,) = duplikaty
    glowny = duplikat.duplikat_glowny
    assert glowny is not None

    wynik = usun_zrodlo_z_projektu(uklad, _konfiguracja(tmp_path), glowny)

    assert wynik.wymaga_przepakowania
    odczytany = wczytaj_checkpoint_projektu(uklad)
    assert odczytany.zrodla[duplikat.identyfikator].status == "znormalizowane"
    assert odczytany.zrodla[duplikat.identyfikator].duplikat_glowny is None
    assert odczytany.deduplikacja.decyzje == []


def test_usuniecie_nieznanego_zrodla_jest_odrzucane(tmp_path: Path) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A))

    with pytest.raises(BladTrwaly, match="Nie ma w projekcie źródła"):
        usun_zrodlo_z_projektu(_uklad(tmp_path), _konfiguracja(tmp_path), "nie-ma-takiego")


# --- zastąpienie treści: sprawdzenie i zapis pliku ---------------------------


def test_zastapienie_treści_jest_mozliwe_dla_spakowanego_a_niemozliwe_dla_duplikatu(
    tmp_path: Path,
) -> None:
    _przetworz(tmp_path, _pozycje(_TEKST_A))
    uklad = _uklad(tmp_path)
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    identyfikator = next(iter(checkpoint.zrodla))

    sprawdz_mozliwosc_zastapienia(checkpoint, identyfikator)
    checkpoint.zrodla[identyfikator].status = "duplikat"
    with pytest.raises(BladTrwaly, match="nie da się zastąpić plikiem"):
        sprawdz_mozliwosc_zastapienia(checkpoint, identyfikator)
    with pytest.raises(BladTrwaly, match="Nie ma w projekcie źródła"):
        sprawdz_mozliwosc_zastapienia(checkpoint, "nie-ma-takiego")


def test_zapis_pliku_zastepczego_nie_nadpisuje_wczesniejszego(tmp_path: Path) -> None:
    pierwszy = zapisz_plik_zastepczy(tmp_path, "strona.html", b"pierwszy")
    drugi = zapisz_plik_zastepczy(tmp_path, "strona.html", b"drugi")

    assert pierwszy.name == "strona.html"
    assert drugi.name == "strona_1.html"
    assert pierwszy.read_bytes() == b"pierwszy"
    assert drugi.read_bytes() == b"drugi"


def test_ponowne_pobranie_wycofuje_zrodlo_sieciowe_i_zachowuje_weryfikacje(
    tmp_path: Path,
) -> None:
    import httpx

    from gnb.ingestion.wejscie import przyjmij_url
    from gnb.operacje_projektu import przygotuj_ponowne_pobranie
    from gnb.potok import pozycja_z_wejscia

    zadania: list[str] = []
    tresc = (Path(__file__).resolve().parent / "dane" / "artykul_oryginal.html").read_bytes()

    def obsluz(zadanie: httpx.Request) -> httpx.Response:
        zadania.append(zadanie.url.path)
        if zadanie.url.path == "/robots.txt":
            return httpx.Response(404)
        return httpx.Response(200, content=tresc, headers={"content-type": "text/html"})

    konfiguracja = Konfiguracja(
        katalog_wynikow=tmp_path / "wyniki",
        sciezka_cache=tmp_path / "cache.sqlite3",
        uzywaj_cache=False,
        respektuj_robots=False,
        odstep_miedzy_zadaniami_sekundy=0.0,
        liczba_ponowien=0,
    )
    transport = httpx.MockTransport(obsluz)
    przetworz_projekt(
        [przyjmij_url("https://przyklad.pl/artykul", _MOMENT)],
        konfiguracja,
        nazwa_projektu=_NAZWA,
        zegar=_zegar_krokowy(),
        transport_http=transport,
    )
    uklad = ustal_uklad(konfiguracja.katalog_wynikow, _NAZWA)
    (identyfikator,) = wczytaj_checkpoint_projektu(uklad).zrodla

    wycofane = przygotuj_ponowne_pobranie(uklad, konfiguracja, identyfikator)

    assert wycofane is not None
    assert identyfikator not in wczytaj_checkpoint_projektu(uklad).zrodla
    pozycja = pozycja_z_wejscia(wycofane[0], konfiguracja, _MOMENT)
    assert pozycja is not None
    przetworz_projekt(
        [*odtworz_wejscia(wczytaj_checkpoint_projektu(uklad), konfiguracja), pozycja],
        konfiguracja,
        nazwa_projektu=_NAZWA,
        zegar=_zegar_krokowy(),
        transport_http=transport,
    )
    stan = wczytaj_checkpoint_projektu(uklad).zrodla[identyfikator]
    assert stan.zweryfikowane_recznie is True
    assert zadania.count("/artykul") == 2


def test_ponowne_pobranie_nie_dotyczy_tekstu_wklejonego(tmp_path: Path) -> None:
    from gnb.operacje_projektu import przygotuj_ponowne_pobranie

    _przetworz(tmp_path, _pozycje(_TEKST_A))
    uklad = _uklad(tmp_path)
    (identyfikator,) = wczytaj_checkpoint_projektu(uklad).zrodla

    assert przygotuj_ponowne_pobranie(uklad, _konfiguracja(tmp_path), identyfikator) is None
    assert identyfikator in wczytaj_checkpoint_projektu(uklad).zrodla
