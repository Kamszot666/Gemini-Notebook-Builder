"""Testy checkpointu projektu z zapisem atomowym."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gnb.core.wyjatki import BladTrwaly
from gnb.persistence.checkpoint import (
    WERSJA_SCHEMATU,
    Checkpoint,
    StanWyniku,
    StanZrodla,
    wczytaj,
    zapisz,
)


def _przykladowy_checkpoint() -> Checkpoint:
    return Checkpoint(
        wersja_schematu=WERSJA_SCHEMATU,
        identyfikator_projektu="proj-abc",
        nazwa_projektu="Projekt",
        katalog_projektu="/tmp/projekt",
        konfiguracja={"limit_zrodel": "100"},
        czas_ostatniej_zmiany="2026-08-26T10:00:00+00:00",
        zrodla={
            "plik_tekstowy-1": StanZrodla(
                identyfikator="plik_tekstowy-1",
                typ="plik_tekstowy",
                pochodzenie="a.md",
                checksum="a" * 64,
                format_zrodla="md",
                status="spakowane",
                nazwa_bazowa_wyniku="a",
                wyniki=[
                    StanWyniku(
                        sciezka_wzgledna="pliki_wynikowe/a.txt",
                        format="txt",
                        liczba_slow=10,
                        liczba_znakow_pliku=60,
                        rozmiar_bajtow=61,
                        checksum="b" * 64,
                    )
                ],
                liczba_slow=10,
                liczba_znakow=60,
                decyzja_md=False,
            )
        },
    )


# Zawartość pliku checkpointu zapisanego wersją schematu 3. Tekst jest wpisany
# wprost, a nie wygenerowany bieżącym kodem, ponieważ test zgodności wstecznej
# zbudowany z bieżącego zapisu sprawdzałby wyłącznie to, co sam ustawił, i nie
# mógłby nie przejść. Liczba znaków dokumentu i liczba znaków pliku wynikowego
# mają tu celowo różne wartości, żeby migracja wyprowadzająca jedną z drugiej
# dała wynik odróżnialny od poprawnego.
_CHECKPOINT_W_WERSJI_TRZECIEJ = """{
  "wersja_schematu": 3,
  "identyfikator_projektu": "proj-abc",
  "nazwa_projektu": "Projekt",
  "katalog_projektu": "/tmp/projekt",
  "konfiguracja": {"limit_zrodel": "100"},
  "czas_ostatniej_zmiany": "2026-08-26T10:00:00+00:00",
  "zakonczony": false,
  "zrodla": {
    "plik_tekstowy-1": {
      "identyfikator": "plik_tekstowy-1",
      "typ": "plik_tekstowy",
      "pochodzenie": "a.md",
      "checksum": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "format_zrodla": "md",
      "status": "spakowane",
      "nazwa_bazowa_wyniku": "a",
      "wyniki": [
        {
          "sciezka_wzgledna": "pliki_wynikowe/a.txt",
          "format": "txt",
          "liczba_slow": 10,
          "liczba_znakow": 999,
          "rozmiar_bajtow": 1000,
          "checksum": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        }
      ],
      "liczba_slow": 10,
      "liczba_znakow": 60,
      "decyzja_md": false,
      "uzasadnienie_md": [],
      "komunikat_bledu": null,
      "pobranie": null,
      "metadane": {}
    }
  }
}"""


def test_zapis_i_odczyt_zwraca_ten_sam_stan(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    oryginal = _przykladowy_checkpoint()
    zapisz(sciezka, oryginal)

    wczytany = wczytaj(sciezka)
    assert wczytany == oryginal


def test_brak_pliku_checkpointu_daje_none(tmp_path: Path) -> None:
    assert wczytaj(tmp_path / "nie_ma.json") is None


def test_drugi_zapis_zostawia_kopie_zapasowa(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    zapisz(sciezka, _przykladowy_checkpoint())
    zmieniony = _przykladowy_checkpoint()
    zmieniony.zakonczony = True
    zapisz(sciezka, zmieniony)

    kopia = tmp_path / "checkpoint.json.bak"
    assert kopia.is_file()
    assert not (tmp_path / "checkpoint.json.tmp").exists()


def test_uszkodzony_plik_bez_kopii_daje_blad_trwaly(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    sciezka.write_text("to nie jest json", encoding="utf-8")
    with pytest.raises(BladTrwaly):
        wczytaj(sciezka)


def test_uszkodzony_plik_glowny_wczytuje_sie_z_kopii(tmp_path: Path) -> None:
    sciezka = tmp_path / "checkpoint.json"
    zapisz(sciezka, _przykladowy_checkpoint())
    zmieniony = _przykladowy_checkpoint()
    zmieniony.zakonczony = True
    zapisz(sciezka, zmieniony)

    sciezka.write_text("uszkodzone", encoding="utf-8")
    wczytany = wczytaj(sciezka)
    assert wczytany is not None
    assert wczytany.zakonczony is False


def test_ocena_jakosci_przezywa_zapis_i_odczyt(tmp_path: Path) -> None:
    checkpoint = _przykladowy_checkpoint()
    stan = checkpoint.zrodla["plik_tekstowy-1"]
    stan.ocena_jakosci = "podejrzana"
    stan.powody_oceny = ["źródło nie ma tytułu"]

    sciezka = tmp_path / "checkpoint.json"
    zapisz(sciezka, checkpoint)
    odczytany = wczytaj(sciezka)

    assert odczytany is not None
    odczytany_stan = odczytany.zrodla["plik_tekstowy-1"]
    assert odczytany_stan.ocena_jakosci == "podejrzana"
    assert odczytany_stan.powody_oceny == ["źródło nie ma tytułu"]


def test_ostrzezenia_przezywaja_zapis_i_odczyt(tmp_path: Path) -> None:
    checkpoint = _przykladowy_checkpoint()
    checkpoint.zrodla["plik_tekstowy-1"].ostrzezenia = ["Plik CSV nie zawiera danych."]

    sciezka = tmp_path / "checkpoint.json"
    zapisz(sciezka, checkpoint)
    odczytany = wczytaj(sciezka)

    assert odczytany is not None
    assert odczytany.zrodla["plik_tekstowy-1"].ostrzezenia == ["Plik CSV nie zawiera danych."]


def test_checkpoint_w_wersji_trzeciej_migruje_sie_i_wznawia(tmp_path: Path) -> None:
    """Plik zapisany wersją schematu 3 wczytuje się po migracji, bez błędu.

    Nazwa pola opisującego liczbę znaków pliku wynikowego zmieniła się w wersji
    czwartej z ``liczba_znakow`` na ``liczba_znakow_pliku``. Bez migracji odczyt
    kończył się surowym ``KeyError``, przez co każdy starszy katalog projektu był
    niewznawialny.
    """
    sciezka = tmp_path / "checkpoint.json"
    sciezka.write_text(_CHECKPOINT_W_WERSJI_TRZECIEJ, encoding="utf-8")

    odczytany = wczytaj(sciezka)

    assert odczytany is not None
    assert odczytany.wersja_schematu == WERSJA_SCHEMATU
    assert odczytany.zakonczony is False
    stan = odczytany.zrodla["plik_tekstowy-1"]
    assert stan.status == "spakowane"
    # Wartości pól dokumentu i pliku są celowo różne, więc migracja wyprowadzona
    # z liczby znaków dokumentu, zamiast przeniesienia klucza wyniku, dałaby tu 60.
    assert stan.liczba_znakow == 60
    assert stan.wyniki[0].liczba_znakow_pliku == 999
    assert stan.wyniki[0].liczba_slow == 10


def test_migracja_wersji_trzeciej_nie_gubi_pol_dodanych_pozniej(tmp_path: Path) -> None:
    """Pola dodane w wersji czwartej dostają po migracji bezpieczne wartości domyślne."""
    sciezka = tmp_path / "checkpoint.json"
    sciezka.write_text(_CHECKPOINT_W_WERSJI_TRZECIEJ, encoding="utf-8")

    odczytany = wczytaj(sciezka)

    assert odczytany is not None
    stan = odczytany.zrodla["plik_tekstowy-1"]
    assert stan.ocena_jakosci is None
    assert stan.powody_oceny == []
    assert stan.ostrzezenia == []


def test_zmigrowany_checkpoint_zapisuje_sie_w_biezacej_wersji(tmp_path: Path) -> None:
    """Po migracji i ponownym zapisie plik na dysku jest już w wersji bieżącej."""
    sciezka = tmp_path / "checkpoint.json"
    sciezka.write_text(_CHECKPOINT_W_WERSJI_TRZECIEJ, encoding="utf-8")

    odczytany = wczytaj(sciezka)
    assert odczytany is not None
    zapisz(sciezka, odczytany)

    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    assert dane["wersja_schematu"] == WERSJA_SCHEMATU
    wynik = dane["zrodla"]["plik_tekstowy-1"]["wyniki"][0]
    assert wynik["liczba_znakow_pliku"] == 999
    assert "liczba_znakow" not in wynik


def test_checkpoint_z_nowszej_wersji_daje_blad_trwaly(tmp_path: Path) -> None:
    """Plik nowszej wersji kończy się polskim komunikatem, a nie śladem stosu."""
    sciezka = tmp_path / "checkpoint.json"
    dane = json.loads(_CHECKPOINT_W_WERSJI_TRZECIEJ)
    dane["wersja_schematu"] = WERSJA_SCHEMATU + 1
    sciezka.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(BladTrwaly) as informacja:
        wczytaj(sciezka)
    assert "nowszej wersji aplikacji" in informacja.value.komunikat


def test_brak_spodziewanego_pola_daje_blad_trwaly_a_nie_slad_stosu(tmp_path: Path) -> None:
    """Wpis źródła bez wymaganego pola kończy się błędem trwałym z komunikatem po polsku."""
    sciezka = tmp_path / "checkpoint.json"
    dane = json.loads(_CHECKPOINT_W_WERSJI_TRZECIEJ)
    dane["wersja_schematu"] = WERSJA_SCHEMATU
    del dane["zrodla"]["plik_tekstowy-1"]["status"]
    sciezka.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(BladTrwaly) as informacja:
        wczytaj(sciezka)
    assert "status" in informacja.value.komunikat


def test_checkpoint_bez_numeru_wersji_jest_traktowany_jak_uszkodzony(tmp_path: Path) -> None:
    """Brak numeru wersji to plik uszkodzony, a nie plik starszej wersji."""
    sciezka = tmp_path / "checkpoint.json"
    dane = json.loads(_CHECKPOINT_W_WERSJI_TRZECIEJ)
    del dane["wersja_schematu"]
    sciezka.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(BladTrwaly):
        wczytaj(sciezka)


def test_starszy_checkpoint_wczytuje_sie_takze_z_kopii_zapasowej(tmp_path: Path) -> None:
    """Uszkodzony plik główny i kopia zapasowa w wersji 3 dają wznowienie po migracji."""
    sciezka = tmp_path / "checkpoint.json"
    sciezka.write_text("uszkodzone", encoding="utf-8")
    (tmp_path / "checkpoint.json.bak").write_text(_CHECKPOINT_W_WERSJI_TRZECIEJ, encoding="utf-8")

    odczytany = wczytaj(sciezka)

    assert odczytany is not None
    assert odczytany.zrodla["plik_tekstowy-1"].wyniki[0].liczba_znakow_pliku == 999
