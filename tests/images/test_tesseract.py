"""Testy wołania Tesseracta: odnajdywanie narzędzia i rozpoznawanie tekstu.

Testy rozpoznawania pomijają się z czytelnym komunikatem, gdy Tesseract nie jest
zainstalowany, tak samo jak testy kanaryjne serwisu wideo pomijają się przy
braku sieci. Na komputerze użytkownika Tesseract jest, więc realnie się
wykonują.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from gnb.core.konfiguracja import wczytaj_konfiguracje
from gnb.core.wyjatki import BrakNarzedzia
from gnb.images import tesseract
from gnb.images.tesseract import (
    UstawieniaOcr,
    czy_dostepny,
    rozpoznaj_tekst,
    rozpoznaj_wiele,
    znajdz_tesseract,
)

_TESSERACT_JEST = czy_dostepny()
_wymaga_tesseracta = pytest.mark.skipif(
    not _TESSERACT_JEST, reason="Tesseract nie jest zainstalowany w tym środowisku."
)


def test_znajdz_tesseract_zwraca_istniejacy_plik_gdy_jest_w_path() -> None:
    if not _TESSERACT_JEST:
        pytest.skip("Tesseract nie jest zainstalowany w tym środowisku.")
    sciezka = znajdz_tesseract()
    assert sciezka.is_file()


def test_znajdz_tesseract_zglasza_brak_narzedzia_dla_blednej_sciezki(tmp_path: Path) -> None:
    """Wskazanie nieistniejącego pliku kończy się czytelnym `BrakNarzedzia`."""
    with pytest.raises(BrakNarzedzia):
        znajdz_tesseract(str(tmp_path / "nie_ma_tesseracta.exe"))


def test_czy_dostepny_jest_falszem_dla_blednej_sciezki(tmp_path: Path) -> None:
    assert czy_dostepny(str(tmp_path / "nie_ma.exe")) is False


def test_znajdz_tesseract_zglasza_brak_gdy_nigdzie_go_nie_ma(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Brak narzędzia w PATH i w znanych katalogach kończy się `BrakNarzedzia`.

    Test czerwieni się, gdyby odnajdywanie zaczęło po cichu zwracać dowolną
    ścieżkę zamiast zgłaszać brak.
    """
    monkeypatch.setattr(tesseract.shutil, "which", lambda _nazwa: None)
    monkeypatch.setattr(tesseract, "_ZNANE_PODKATALOGI_WINDOWS", ())
    monkeypatch.setattr(tesseract, "_DOMYSLNE_SCIEZKI_WINDOWS", ())

    with pytest.raises(BrakNarzedzia, match="Tesseract"):
        znajdz_tesseract()


@_wymaga_tesseracta
def test_rozpoznaj_tekst_odczytuje_wyrazne_wielkie_litery(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obraz = obraz_z_tekstem(["GEMINI NOTEBOOK", "BUILDER 2026"])

    tekst = rozpoznaj_tekst(obraz, UstawieniaOcr(jezyk="pol"))

    assert "GEMINI" in tekst.upper()
    assert "\r" not in tekst


@_wymaga_tesseracta
def test_rozpoznaj_wiele_zachowuje_kolejnosc_i_zglasza_postep(
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obrazy = [
        obraz_z_tekstem(["STRONA PIERWSZA"]),
        obraz_z_tekstem(["STRONA DRUGA"]),
        obraz_z_tekstem(["STRONA TRZECIA"]),
    ]
    postep: list[tuple[int, int]] = []

    wyniki = rozpoznaj_wiele(
        obrazy, UstawieniaOcr(jezyk="pol"), przy_postepie=lambda a, b: postep.append((a, b))
    )

    assert len(wyniki) == 3
    assert "PIERWSZA" in wyniki[0].upper()
    assert "DRUGA" in wyniki[1].upper()
    assert "TRZECIA" in wyniki[2].upper()
    assert postep[-1] == (3, 3)
    assert len(postep) == 3


def test_rozpoznaj_wiele_dla_pustej_listy_nie_wola_tesseracta() -> None:
    assert rozpoznaj_wiele([], UstawieniaOcr()) == []


def test_efektywna_liczba_procesow_zamienia_zero_na_wartosc_dobrana() -> None:
    assert UstawieniaOcr(liczba_procesow=2).efektywna_liczba_procesow == 2
    assert UstawieniaOcr(liczba_procesow=0).efektywna_liczba_procesow >= 1


def test_ustawienia_ocr_z_konfiguracji(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml", srodowisko={"GNB_OCR_JEZYK": "pol+eng", "GNB_OCR_PSM": "6"}
    )

    ustawienia = UstawieniaOcr.z_konfiguracji(konfiguracja)

    assert ustawienia.jezyk == "pol+eng"
    assert ustawienia.tryb_segmentacji == 6
