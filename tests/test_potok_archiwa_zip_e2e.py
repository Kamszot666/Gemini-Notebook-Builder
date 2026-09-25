"""Test end-to-end potoku dla archiwów ZIP: pliki z archiwum jako zwykłe źródła.

Sprawdza, że pliki z archiwum przechodzą te same adaptery co pliki podane wprost,
że pochodzenie z archiwum jest w manifeście, nagłówku i raporcie, że każdy
pominięty element jest widoczny we wszystkich miejscach, że brak automatycznego
łączenia w grupę jest zachowany oraz że wznowienie i usunięcie źródła działają.
"""

from __future__ import annotations

import json
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik
from gnb.operacje_projektu import usun_zrodlo_z_projektu
from gnb.persistence.checkpoint import wczytaj
from gnb.persistence.projekt import ustal_uklad
from gnb.potok import WynikPrzetwarzania, odtworz_wejscia, przetworz_projekt

DANE = Path(__file__).resolve().parent / "dane" / "formaty"
_MOMENT = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
_NAZWA = "Archiwa"


def _zegar() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 26, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _konfiguracja(tmp_path: Path, **nadpisania: Any) -> Konfiguracja:
    ustawienia: dict[str, Any] = {
        "katalog_wynikow": tmp_path / "wyniki",
        "deduplikacja_hash_wlaczona": False,
        "deduplikacja_kosmetyczna_wlaczona": False,
        "deduplikacja_podobienstwo_wlaczone": False,
    }
    ustawienia.update(nadpisania)
    return Konfiguracja(**ustawienia)


def _zip(tmp_path: Path, wpisy: dict[str, bytes | str], nazwa: str = "materialy.zip") -> Path:
    sciezka = tmp_path / nazwa
    with zipfile.ZipFile(sciezka, "w", zipfile.ZIP_DEFLATED) as archiwum:
        for wpis, dane in wpisy.items():
            archiwum.writestr(wpis, dane)
    return sciezka


def _przetworz(
    tmp_path: Path,
    pozycje: list[PozycjaWejsciowa],
    *,
    ponownie_przetwarzaj_usuniete: bool = True,
    **konfiguracja: Any,
) -> WynikPrzetwarzania:
    return przetworz_projekt(
        pozycje,
        _konfiguracja(tmp_path, **konfiguracja),
        nazwa_projektu=_NAZWA,
        zegar=_zegar(),
        ponownie_przetwarzaj_usuniete=ponownie_przetwarzaj_usuniete,
    )


def _pozycje(*sciezki: Path, grupa: str | None = None) -> list[PozycjaWejsciowa]:
    return [przyjmij_plik(sciezka, _MOMENT, grupa=grupa) for sciezka in sciezki]


def _manifest(wynik: WynikPrzetwarzania) -> dict[str, Any]:
    return json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))


def _zrodla(wynik: WynikPrzetwarzania) -> dict[str, dict[str, Any]]:
    return {zrodlo["pochodzenie"]: zrodlo for zrodlo in _manifest(wynik)["zrodla"]}


def _pliki_wynikowe(wynik: WynikPrzetwarzania) -> list[Path]:
    return sorted((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))


def _tresc(wynik: WynikPrzetwarzania) -> str:
    return "\n".join(plik.read_text(encoding="utf-8") for plik in _pliki_wynikowe(wynik))


def _raport(wynik: WynikPrzetwarzania) -> str:
    return wynik.sciezka_raportu.read_text(encoding="utf-8")


def _log_wazny(wynik: WynikPrzetwarzania) -> str:
    return (wynik.katalog_projektu / "logi" / "log_wazne.txt").read_text(encoding="utf-8")


def _log_szczegolowy(wynik: WynikPrzetwarzania) -> str:
    return (wynik.katalog_projektu / "logi" / "log_szczegolowy.txt").read_text(encoding="utf-8")


def _archiwum_z_roznymi_plikami(tmp_path: Path) -> Path:
    return _zip(
        tmp_path,
        {
            "notatka.txt": "Notatka z archiwum o żółwiach i ich pancerzach.",
            "raport/dokument.docx": (DANE / "dokument.docx").read_bytes(),
            "raport/arkusz.xlsx": (DANE / "arkusz.xlsx").read_bytes(),
            "program.exe": b"MZ",
            "__MACOSX/._notatka.txt": b"x",
        },
    )


def test_pliki_z_archiwum_sa_zrodlami_z_pochodzeniem_i_bez_automatycznej_grupy(
    tmp_path: Path,
) -> None:
    wynik = _przetworz(tmp_path, _pozycje(_archiwum_z_roznymi_plikami(tmp_path)))

    assert wynik.liczba_bledow == 0
    assert wynik.liczba_przetworzonych == 3
    zrodla = _zrodla(wynik)
    assert set(zrodla) == {
        "materialy.zip » notatka.txt",
        "materialy.zip » raport/dokument.docx",
        "materialy.zip » raport/arkusz.xlsx",
    }
    assert all(zrodlo["archiwum"] == "materialy.zip" for zrodlo in zrodla.values())
    assert all(zrodlo["status"] == "spakowane" for zrodlo in zrodla.values())
    # Brak grupy: każde źródło ma własny plik wynikowy.
    assert len(_pliki_wynikowe(wynik)) == 3
    tresc = _tresc(wynik)
    assert "Notatka z archiwum o żółwiach" in tresc
    assert "Wstęp do żółwi" in tresc  # DOCX przez zwykły adapter DOCX
    assert "Żółta ścierka" in tresc  # XLSX przez zwykły adapter XLSX
    assert "Archiwum: materialy.zip" in tresc
    assert "Plik: raport/dokument.docx" in tresc


def test_nazwa_grupy_laczy_pliki_z_archiwum_w_jeden_plik(tmp_path: Path) -> None:
    archiwum = _zip(tmp_path, {"a.txt": "Pierwsza treść.", "b.txt": "Druga treść."})

    wynik = _przetworz(tmp_path, _pozycje(archiwum, grupa="Moja grupa"))

    assert wynik.liczba_przetworzonych == 2
    (plik,) = _pliki_wynikowe(wynik)
    tresc = plik.read_text(encoding="utf-8")
    assert "Pierwsza treść." in tresc and "Druga treść." in tresc


def test_manifest_ma_wpis_archiwum_z_lista_zawartosci_i_powiazaniem_ze_zrodlami(
    tmp_path: Path,
) -> None:
    wynik = _przetworz(tmp_path, _pozycje(_archiwum_z_roznymi_plikami(tmp_path)))

    (archiwum,) = _manifest(wynik)["archiwa"]
    assert archiwum["nazwa"] == "materialy.zip"
    assert archiwum["status"] == "rozwiniete"
    assert archiwum["suma_kontrolna"]
    pliki = {plik["sciezka"]: plik for plik in archiwum["pliki"]}
    assert set(pliki) == {
        "notatka.txt",
        "raport/dokument.docx",
        "raport/arkusz.xlsx",
        "program.exe",
        "__MACOSX/._notatka.txt",
    }
    zrodla = _zrodla(wynik)
    przyjety = pliki["notatka.txt"]
    assert przyjety["status"] == "przyjety"
    assert (
        przyjety["identyfikator_zrodla"] == zrodla["materialy.zip » notatka.txt"]["identyfikator"]
    )
    assert pliki["program.exe"]["status"] == "pominiety"
    assert "Nieobsługiwany format" in pliki["program.exe"]["komunikat"]
    manifest_txt = (wynik.katalog_projektu / "manifest.txt").read_text(encoding="utf-8")
    assert "Archiwum: materialy.zip" in manifest_txt
    assert "Plik w archiwum: program.exe" in manifest_txt


def test_pominiete_pliki_z_archiwum_sa_w_raporcie_i_w_obu_logach(tmp_path: Path) -> None:
    wynik = _przetworz(tmp_path, _pozycje(_archiwum_z_roznymi_plikami(tmp_path)))

    assert wynik.liczba_pominietych_z_archiwow == 2
    raport = _raport(wynik)
    assert "Archiwa ZIP, liczba: 1" in raport
    assert "Przyjęte pliki: 3" in raport
    assert "Pominięte pliki: 2" in raport
    assert "Pominięto: program.exe. Powód: Nieobsługiwany format pliku: „exe”." in raport
    assert "metadanych systemu" in raport
    assert "Archiwum ZIP rozwinięte:" in _log_wazny(wynik)
    assert "przyjęto 3, pominięto 2" in _log_wazny(wynik)
    assert "pominięto plik program.exe" in _log_szczegolowy(wynik)


def test_archiwum_ponad_limit_jest_pominiete_w_calosci_i_widoczne_wszedzie(
    tmp_path: Path,
) -> None:
    archiwum = _zip(tmp_path, {f"{n}.txt": f"treść {n}" for n in range(5)})

    wynik = _przetworz(tmp_path, _pozycje(archiwum), zip_maks_plikow=3)

    assert wynik.liczba_przetworzonych == 0
    assert wynik.liczba_pominietych_z_archiwow == 1
    assert _manifest(wynik)["zrodla"] == []
    (wpis,) = _manifest(wynik)["archiwa"]
    assert wpis["status"] == "pominiete"
    assert "więcej niż 3 plików" in wpis["komunikat"]
    raport = _raport(wynik)
    assert "Całe archiwum zostało pominięte." in raport
    assert "więcej niż 3 plików" in raport
    assert "Uwaga, archiwum ZIP pominięte:" in _log_wazny(wynik)
    assert "pominięte" in _log_szczegolowy(wynik)
    assert not _pliki_wynikowe(wynik)


def test_ostrzezenie_przed_przetwarzaniem_gdy_archiwum_nie_miesci_sie_w_slotach(
    tmp_path: Path,
) -> None:
    archiwum = _zip(tmp_path, {f"{n}.txt": f"Osobna treść numer {n}." for n in range(4)})

    wynik = _przetworz(tmp_path, _pozycje(archiwum), limit_zrodel=2)

    (wpis,) = _manifest(wynik)["archiwa"]
    assert any("potrzebuje 4 slotów" in o and "wolnych jest 2" in o for o in wpis["ostrzezenia"])
    assert "Uwaga: Archiwum ma 4 plików" in _raport(wynik)
    assert "Uwaga, archiwum ZIP może nie zmieścić się w limicie źródeł" in _log_wazny(wynik)
    assert wynik.liczba_przetworzonych == 2
    assert wynik.liczba_pominietych == 2


def test_z_nazwa_grupy_archiwum_mieści_sie_w_jednym_slocie_bez_ostrzezenia(
    tmp_path: Path,
) -> None:
    archiwum = _zip(tmp_path, {f"{n}.txt": f"Osobna treść numer {n}." for n in range(4)})

    wynik = _przetworz(tmp_path, _pozycje(archiwum, grupa="Razem"), limit_zrodel=2)

    (wpis,) = _manifest(wynik)["archiwa"]
    assert wpis["ostrzezenia"] == []
    assert wynik.liczba_przetworzonych == 4


def test_wznowienie_odtwarza_pliki_z_archiwum_a_nie_samo_archiwum(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_archiwum_z_roznymi_plikami(tmp_path)))
    uklad = ustal_uklad(_konfiguracja(tmp_path).katalog_wynikow, _NAZWA)
    checkpoint = wczytaj(uklad.checkpoint)
    assert checkpoint is not None

    wejscia = odtworz_wejscia(checkpoint, _konfiguracja(tmp_path))
    drugi = _przetworz(tmp_path, wejscia, ponownie_przetwarzaj_usuniete=False)

    assert len(wejscia) == 3
    assert all(pozycja.format_zrodla != "zip" for pozycja in wejscia)
    assert all(pozycja.archiwum == "materialy.zip" for pozycja in wejscia)
    assert drugi.liczba_przetworzonych == pierwszy.liczba_przetworzonych == 3
    assert len(_manifest(drugi)["zrodla"]) == 3
    assert len(_pliki_wynikowe(drugi)) == 3


def test_to_samo_archiwum_dodane_ponownie_nie_dubluje_wpisu_ani_zrodel(tmp_path: Path) -> None:
    archiwum = _archiwum_z_roznymi_plikami(tmp_path)
    _przetworz(tmp_path, _pozycje(archiwum))

    drugi = _przetworz(tmp_path, _pozycje(archiwum))

    assert len(_manifest(drugi)["archiwa"]) == 1
    assert len(_manifest(drugi)["zrodla"]) == 3
    assert "Źródła już obecne w projekcie, liczba: 3" in _raport(drugi)


def test_usuniecie_zrodla_z_archiwum_dziala_i_wznowienie_go_nie_przywraca(
    tmp_path: Path,
) -> None:
    wynik = _przetworz(tmp_path, _pozycje(_archiwum_z_roznymi_plikami(tmp_path)))
    uklad = ustal_uklad(_konfiguracja(tmp_path).katalog_wynikow, _NAZWA)
    identyfikator = _zrodla(wynik)["materialy.zip » notatka.txt"]["identyfikator"]

    usun_zrodlo_z_projektu(uklad, _konfiguracja(tmp_path), identyfikator)

    checkpoint = wczytaj(uklad.checkpoint)
    assert checkpoint is not None
    assert len(checkpoint.wejscia) == 2
    ponowny = _przetworz(
        tmp_path,
        odtworz_wejscia(checkpoint, _konfiguracja(tmp_path)),
        ponownie_przetwarzaj_usuniete=False,
    )
    assert "materialy.zip » notatka.txt" not in _zrodla(ponowny)
    assert len(_manifest(ponowny)["zrodla"]) == 2


def test_uszkodzone_archiwum_nie_zatrzymuje_pozostalych_zrodel(tmp_path: Path) -> None:
    zepsute = tmp_path / "zepsute.zip"
    zepsute.write_bytes(b"to nie jest archiwum")
    zwykly = tmp_path / "zwykly.txt"
    zwykly.write_text("Zwykły plik obok archiwum.", encoding="utf-8")

    wynik = _przetworz(tmp_path, _pozycje(zepsute, zwykly))

    assert wynik.liczba_przetworzonych == 1
    (wpis,) = _manifest(wynik)["archiwa"]
    assert wpis["status"] == "pominiete"
    assert "nie jest poprawnym archiwum ZIP" in wpis["komunikat"]
    assert _zrodla(wynik)["zwykly.txt"]["status"] == "spakowane"


def test_obrazy_z_archiwum_trafiaja_do_wspolnego_tematycznego_pliku_pdf(tmp_path: Path) -> None:
    """Obraz z archiwum dostaje domyślną grupę obrazów jak każdy obraz podany bez grupy."""
    katalog_danych = Path(__file__).resolve().parent / "dane"
    archiwum = _zip(
        tmp_path,
        {
            "wykres.png": (katalog_danych / "obraz_wykres.png").read_bytes(),
            "zdjecie.jpg": (katalog_danych / "obraz_zdjecie.jpg").read_bytes(),
        },
    )

    wynik = _przetworz(tmp_path, _pozycje(archiwum))

    assert wynik.liczba_bledow == 0
    pliki_pdf = list((wynik.katalog_projektu / "pliki_wynikowe").glob("*.pdf"))
    assert len(pliki_pdf) == 1
    zrodla = _zrodla(wynik)
    assert set(zrodla) == {"materialy.zip » wykres.png", "materialy.zip » zdjecie.jpg"}
    assert all(zrodlo["archiwum"] == "materialy.zip" for zrodlo in zrodla.values())
