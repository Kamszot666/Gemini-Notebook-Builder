"""Testy end-to-end potoku dla zdjęć kartek akt pakowanych jako sekcje skanów.

Wszystkie obrazy są syntetyczne: tekst narysowany krojem z repozytorium albo
bazgroły imitujące pismo odręczne. Żadne zdjęcie ani tekst z prawdziwych akt nie
może trafić do repozytorium, testów ani logów (sekcja „Część E” polecenia).

Testy zależne od OCR pomijają się z komunikatem, gdy nie da się rozpoznać
polskiego tekstu (fikstura ``wymaga_ocr_pol``).
"""

from __future__ import annotations

import json
import random
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from gnb.core.konfiguracja import Konfiguracja
from gnb.extractors import plik_obraz
from gnb.ingestion.wejscie import przyjmij_plik
from gnb.potok import przetworz_projekt

KROJ = Path(__file__).resolve().parent.parent / "gnb" / "images" / "czcionki" / "DejaVuSans.ttf"
_MOMENT = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
_SLOWA = (
    "sąd wyrok wniosek pozwany powód świadek rozprawa zarządzenie odpis termin "
    "postanowienie pełnomocnik dowód protokół zażalenie doręczenie uzasadnienie "
    "koszty strona kwota zobowiązanie umowa pismo załącznik odroczenie biegły"
).split()
ZDANIE_NIECZYTELNE = (
    "Prawdopodobnie pismo odręczne albo zdjęcie nieczytelne dla OCR. Treść nie została odczytana."
)


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": _MOMENT}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _tekst_strony(numer: int, wierszy: int = 4) -> list[str]:
    """Zwraca unikalny tekst strony: wiersze ze słów losowanych od numeru strony."""
    losowy = random.Random(numer)
    return [
        f"Strona {numer} wiersz {wiersz}: " + " ".join(losowy.choices(_SLOWA, k=6))
        for wiersz in range(1, wierszy + 1)
    ]


def _zapisz_druk(sciezka: Path, numer: int, *, wierszy: int = 4, rozmiar=(1100, 420)) -> list[str]:
    obraz = Image.new("RGB", rozmiar, "white")
    rysunek = ImageDraw.Draw(obraz)
    czcionka = ImageFont.truetype(str(KROJ), 34)
    wiersze = _tekst_strony(numer, wierszy)
    for indeks, wiersz in enumerate(wiersze):
        rysunek.text((40, 30 + indeks * 62), wiersz, font=czcionka, fill="black")
    obraz.save(sciezka)
    return wiersze


def _zapisz_bazgroly(sciezka: Path, ziarno: int = 1) -> None:
    """Rysuje poziome, poszarpane kreski imitujące pismo odręczne, bez żadnego druku."""
    losowy = random.Random(ziarno)
    obraz = Image.new("RGB", (1100, 700), "white")
    rysunek = ImageDraw.Draw(obraz)
    y = 60
    for _ in range(9):
        x = 40
        while x < 1000:
            dlugosc = losowy.randint(30, 150)
            punkty = [(x + i, y + losowy.randint(-14, 14)) for i in range(0, dlugosc, 8)]
            rysunek.line(punkty, fill="black", width=3)
            x += dlugosc + losowy.randint(15, 40)
        y += 70
    obraz.save(sciezka)


def _wejscia(sciezki: list[Path], grupa: str = "akta"):
    return [przyjmij_plik(sciezka, _MOMENT, grupa=grupa) for sciezka in sciezki]


def _konfiguracja(katalog: Path, **zmiany) -> Konfiguracja:
    return Konfiguracja(katalog_wynikow=katalog, grupy_obrazow_jako_skany=True, **zmiany)


def _naglowki_skanow(tresc: str) -> list[str]:
    return re.findall(r"^## (.+)$", tresc, flags=re.MULTILINE)


def test_skany_w_jednym_pliku_md_w_kolejnosci_naturalnej_z_dopiskami_i_nieczytelnym(
    wymaga_ocr_pol: None, tmp_path: Path
) -> None:
    folder = tmp_path / "zdjecia"
    folder.mkdir()
    nazwy = ["skan_10.png", "skan_2.png", "skan_1.png"]
    for numer, nazwa in zip((10, 2, 1), nazwy, strict=True):
        _zapisz_druk(folder / nazwa, numer)
    _zapisz_bazgroly(folder / "skan_3.png")
    (folder / "skan_2_dopiski.txt").write_bytes(
        "Dopisek ołówkiem przy marginesie: sprawa pilna.".encode("utf-8-sig")
    )
    (folder / "obcy_dopiski.txt").write_text("Dopisek bez zdjęcia.", encoding="utf-8")

    sciezki = [
        folder / "skan_10.png",
        folder / "skan_2.png",
        folder / "skan_2_dopiski.txt",
        folder / "skan_3.png",
        folder / "obcy_dopiski.txt",
        folder / "skan_1.png",
    ]
    wynik = przetworz_projekt(
        _wejscia(sciezki),
        _konfiguracja(tmp_path / "wyniki"),
        nazwa_projektu="Akta test",
        zegar=_zegar_krokowy(),
    )

    # Pliki dopisków nie są źródłami.
    assert wynik.liczba_przetworzonych == 4
    pliki = sorted((wynik.katalog_projektu / "pliki_wynikowe").glob("*"))
    assert [plik.suffix for plik in pliki] == [".md"]
    tresc = pliki[0].read_text(encoding="utf-8")

    assert _naglowki_skanow(tresc) == ["skan_1.png", "skan_2.png", "skan_3.png", "skan_10.png"]
    assert "- Numer skanu w grupie: 1" in tresc
    assert "- Numer skanu w grupie: 4" in tresc
    assert "- Ocena OCR: poprawna" in tresc
    assert re.search(r"- Średnia pewność słów: \d+\.\d", tresc)
    # Druk jest odczytany, a dopiski leżą w osobnej sekcji tylko przy właściwym skanie.
    assert "Strona 1 wiersz 1" in tresc
    assert tresc.count("### Dopiski odręczne przepisane przez osobę widzącą") == 1
    sekcja_2 = tresc.split("## skan_2.png")[1].split("## skan_3.png")[0]
    assert "### Dopiski odręczne przepisane przez osobę widzącą" in sekcja_2
    assert "Dopisek ołówkiem przy marginesie" in sekcja_2
    assert "- Dopiski odręczne: tak" in sekcja_2
    assert tresc.count("- Dopiski odręczne: nie") == 3

    # Skan nieczytelny ma tylko zdanie o braku odczytu.
    sekcja_3 = tresc.split("## skan_3.png")[1].split("## skan_10.png")[0]
    assert ZDANIE_NIECZYTELNE in sekcja_3
    assert "Ocena OCR:" in sekcja_3

    # Manifest, raport i wyniki pośrednie.
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    po_pliku = {
        zrodlo["metadane"].get("dopiski_odreczne"): zrodlo
        for zrodlo in manifest["zrodla"]
        if zrodlo["metadane"].get("nieczytelne_dla_ocr") == "nie"
    }
    assert set(po_pliku) == {"tak", "nie"}
    nieczytelne = [
        zrodlo
        for zrodlo in manifest["zrodla"]
        if zrodlo["metadane"].get("nieczytelne_dla_ocr") == "tak"
    ]
    assert len(nieczytelne) == 1
    assert float(nieczytelne[0]["metadane"]["srednia_pewnosc_ocr"]) < 50
    odczyty_posrednie = list(
        (wynik.katalog_projektu / "wyniki_posrednie").glob("*.ocr_nieczytelny.txt")
    )
    assert len(odczyty_posrednie) <= 1

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Skany z niską pewnością odczytu, liczba: 1" in raport
    assert "Plik: skan_3.png" in raport
    assert ZDANIE_NIECZYTELNE in raport
    assert "Dopiski bez pasującego skanu, liczba: 1" in raport
    assert "Plik: obcy_dopiski.txt" in raport


def test_dopiski_przechodza_przez_zdanie_nieczytelne_bez_deduplikacji(
    wymaga_ocr_pol: None, tmp_path: Path
) -> None:
    """Dwa różne skany nieczytelne dla OCR nie mogą się zdeduplikować w jeden."""
    folder = tmp_path / "zdjecia"
    folder.mkdir()
    _zapisz_bazgroly(folder / "a_1.png", ziarno=1)
    _zapisz_bazgroly(folder / "a_2.png", ziarno=2)
    _zapisz_druk(folder / "a_3.png", 3)
    wynik = przetworz_projekt(
        _wejscia([folder / "a_1.png", folder / "a_2.png", folder / "a_3.png"]),
        _konfiguracja(tmp_path / "wyniki"),
        nazwa_projektu="Akta dedup",
        zegar=_zegar_krokowy(),
    )
    assert wynik.liczba_przetworzonych == 3
    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert all(zrodlo["status"] == "spakowane" for zrodlo in manifest["zrodla"])
    tresc = next((wynik.katalog_projektu / "pliki_wynikowe").glob("*.md")).read_text(
        encoding="utf-8"
    )
    assert tresc.count(ZDANIE_NIECZYTELNE) == 2


def test_przerwanie_i_wznowienie_nie_powtarza_ocr_przetworzonych_zdjec(
    wymaga_ocr_pol: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "zdjecia"
    folder.mkdir()
    sciezki = []
    for numer in range(1, 7):
        sciezka = folder / f"k_{numer}.png"
        _zapisz_druk(sciezka, numer, wierszy=2, rozmiar=(1100, 200))
        sciezki.append(sciezka)
    konfiguracja = _konfiguracja(tmp_path / "wyniki")

    prawdziwa = plik_obraz.odczytaj_strone
    wywolania: list[int] = []

    def przerywajaca(*argumenty, **nazwane):
        wywolania.append(1)
        if len(wywolania) == 4:
            raise KeyboardInterrupt
        return prawdziwa(*argumenty, **nazwane)

    monkeypatch.setattr(plik_obraz, "odczytaj_strone", przerywajaca)
    with pytest.raises(KeyboardInterrupt):
        przetworz_projekt(
            _wejscia(sciezki), konfiguracja, nazwa_projektu="Akta wznow", zegar=_zegar_krokowy()
        )
    assert len(wywolania) == 4

    wywolania.clear()
    monkeypatch.setattr(
        plik_obraz,
        "odczytaj_strone",
        lambda *argumenty, **nazwane: wywolania.append(1) or prawdziwa(*argumenty, **nazwane),
    )
    wynik = przetworz_projekt(
        _wejscia(sciezki), konfiguracja, nazwa_projektu="Akta wznow", zegar=_zegar_krokowy()
    )
    # Trzy zdjęcia były gotowe przed przerwaniem, więc OCR dotyczy tylko pozostałych trzech.
    assert len(wywolania) == 3
    assert wynik.wznowiono is True
    assert wynik.liczba_przetworzonych == 6
    tresc = next((wynik.katalog_projektu / "pliki_wynikowe").glob("*.md")).read_text(
        encoding="utf-8"
    )
    assert _naglowki_skanow(tresc) == [f"k_{numer}.png" for numer in range(1, 7)]


@pytest.mark.wolne
def test_trzysta_skanow_daje_kilka_plikow_w_kolejnosci_nazw(
    wymaga_ocr_pol: None, tmp_path: Path
) -> None:
    folder = tmp_path / "zdjecia"
    folder.mkdir()
    sciezki = []
    for numer in range(1, 301):
        sciezka = folder / f"IMG_{numer}.png"
        _zapisz_druk(sciezka, numer, wierszy=1, rozmiar=(1100, 110))
        sciezki.append(sciezka)
    # Kolejność wejść jest celowo odwrócona: o porządku decydują nazwy plików.
    sciezki.reverse()

    poczatek = time.perf_counter()
    wynik = przetworz_projekt(
        _wejscia(sciezki),
        _konfiguracja(tmp_path / "wyniki"),
        nazwa_projektu="Akta trzysta",
        zegar=_zegar_krokowy(),
    )
    czas_na_zdjecie = (time.perf_counter() - poczatek) / 300
    print(f"Czas przetwarzania jednego syntetycznego zdjęcia: {czas_na_zdjecie:.2f} s")

    assert wynik.liczba_przetworzonych == 300
    pliki = sorted((wynik.katalog_projektu / "pliki_wynikowe").glob("*.md"))
    assert 1 <= len(pliki) <= 5
    nazwy = [nazwa for plik in pliki for nazwa in _naglowki_skanow(plik.read_text("utf-8"))]
    assert nazwy == [f"IMG_{numer}.png" for numer in range(1, 301)]
    assert all(plik.stat().st_size < 30 * 1024 * 1024 for plik in pliki)
