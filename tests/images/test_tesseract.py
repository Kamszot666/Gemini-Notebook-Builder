"""Testy wołania Tesseracta: odnajdywanie narzędzia i rozpoznawanie tekstu.

Testy rozpoznawania po polsku pomijają się z czytelnym komunikatem, gdy nie da
się wykonać OCR polskiego tekstu: albo brakuje samego Tesseracta, albo jest on
zainstalowany bez pliku danych językowych ``pol.traineddata``. Rozróżnienie tych
dwóch braków niesie fikstura ``wymaga_ocr_pol``. Na komputerze użytkownika oba
warunki są spełnione, więc testy realnie się wykonują.
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
    brakujace_dane_jezykowe,
    czy_dostepny,
    rozpoznaj_tekst,
    rozpoznaj_wiele,
    znajdz_tesseract,
)

_TESSERACT_JEST = czy_dostepny()


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


def test_rozpoznaj_tekst_odczytuje_wyrazne_wielkie_litery(
    wymaga_ocr_pol: None,
    obraz_z_tekstem: Callable[..., bytes],
) -> None:
    obraz = obraz_z_tekstem(["GEMINI NOTEBOOK", "BUILDER 2026"])

    tekst = rozpoznaj_tekst(obraz, UstawieniaOcr(jezyk="pol"))

    assert "GEMINI" in tekst.upper()
    assert "\r" not in tekst


def test_rozpoznaj_wiele_zachowuje_kolejnosc_i_zglasza_postep(
    wymaga_ocr_pol: None,
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


def test_efektywna_liczba_procesow_zostawia_jeden_rdzen_wolny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Domyślny dobór procesów OCR nie zajmuje wszystkich rdzeni.

    Powód jest dostępnościowy: przy pełnym obciążeniu wszystkich rdzeni synteza
    mowy czytnika ekranu się zacina, a użytkownik właśnie wtedy słucha komunikatów
    o postępie OCR. Test czerwieni się, gdyby ktoś „zoptymalizował” dobór z powrotem
    do pełnej liczby rdzeni.
    """
    monkeypatch.setattr(tesseract.os, "cpu_count", lambda: 8)
    assert UstawieniaOcr(liczba_procesow=0).efektywna_liczba_procesow == 4

    monkeypatch.setattr(tesseract.os, "cpu_count", lambda: 3)
    assert UstawieniaOcr(liczba_procesow=0).efektywna_liczba_procesow == 2

    monkeypatch.setattr(tesseract.os, "cpu_count", lambda: 1)
    assert UstawieniaOcr(liczba_procesow=0).efektywna_liczba_procesow == 1

    monkeypatch.setattr(tesseract.os, "cpu_count", lambda: None)
    assert UstawieniaOcr(liczba_procesow=0).efektywna_liczba_procesow == 1

    monkeypatch.setattr(tesseract.os, "cpu_count", lambda: 20)
    assert UstawieniaOcr(liczba_procesow=7).efektywna_liczba_procesow == 7


def test_brakujace_dane_jezykowe_wskazuje_brakujacy_czlon(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strażnik pomijania testów OCR rozpoznaje brak konkretnego pliku danych językowych."""
    monkeypatch.setattr(tesseract, "dostepne_jezyki", lambda _sciezka="": ("eng", "osd"))

    assert brakujace_dane_jezykowe("pol") == ("pol",)
    assert brakujace_dane_jezykowe("pol+eng") == ("pol",)
    assert brakujace_dane_jezykowe("eng") == ()


def test_brakujace_dane_jezykowe_puste_gdy_wszystkie_dane_sa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tesseract, "dostepne_jezyki", lambda _sciezka="": ("eng", "pol"))

    assert brakujace_dane_jezykowe("pol+eng") == ()


def test_brakujace_dane_jezykowe_zglasza_wszystko_gdy_lista_jest_pusta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pusta lista języków — brak programu albo pusty katalog danych — to brak wszystkiego.

    Rozróżnienie braku programu od braku pliku danych językowych należy do
    strażnika w conftest, który najpierw sprawdza ``czy_dostepny``.
    """
    monkeypatch.setattr(tesseract, "dostepne_jezyki", lambda _sciezka="": ())

    assert brakujace_dane_jezykowe("pol+eng") == ("pol", "eng")


def test_ustawienia_ocr_z_konfiguracji(tmp_path: Path) -> None:
    konfiguracja = wczytaj_konfiguracje(
        tmp_path / "nie_ma.toml", srodowisko={"GNB_OCR_JEZYK": "pol+eng", "GNB_OCR_PSM": "6"}
    )

    ustawienia = UstawieniaOcr.z_konfiguracji(konfiguracja)

    assert ustawienia.jezyk == "pol+eng"
    assert ustawienia.tryb_segmentacji == 6
