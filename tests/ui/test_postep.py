"""Testy dławienia komunikatów postępu dla regionu role="status"."""

from __future__ import annotations

from gnb.core.postep import FazaPotoku, ZdarzeniePostepu
from gnb.ui.postep import DlawikPostepu


class _ZegarKrokowy:
    """Zegar sterowany ręcznie: czas rośnie tylko po jawnym przesunięciu."""

    def __init__(self) -> None:
        self.teraz = 0.0

    def __call__(self) -> float:
        return self.teraz


def _zdarzenie(opis: str, faza: FazaPotoku = FazaPotoku.EKSTRAKCJA) -> ZdarzeniePostepu:
    return ZdarzeniePostepu(faza=faza, wykonano=1, wszystkich=10, opis=opis)


def test_dwa_zdarzenia_w_tej_samej_sekundzie_daja_jeden_komunikat() -> None:
    zegar = _ZegarKrokowy()
    dlawik = DlawikPostepu(minimalny_odstep_sekund=4.0, zegar=zegar)

    dlawik.przyjmij(_zdarzenie("Przetworzono 1 z 10 źródeł"))
    dlawik.przyjmij(_zdarzenie("Przetworzono 2 z 10 źródeł"))
    dlawik.przyjmij(_zdarzenie("Przetworzono 3 z 10 źródeł"))

    assert dlawik.komunikat() == "Przetworzono 1 z 10 źródeł"


def test_zdarzenie_fazy_ocr_dociera_do_regionu_postepu() -> None:
    """Postęp OCR skanu jest zwykłym zdarzeniem: jego opis trafia do regionu status.

    Test czerwieni się, gdyby faza OCR zaczęła być traktowana szczególnie i jej
    komunikat gdzieś przepadał — użytkownik nie może zostać przy niemym oknie
    przez kilkanaście minut rozpoznawania skanu.
    """
    zegar = _ZegarKrokowy()
    dlawik = DlawikPostepu(minimalny_odstep_sekund=4.0, zegar=zegar)

    dlawik.przyjmij(
        _zdarzenie("Rozpoznawanie tekstu ze skanu „skan.pdf”, strona 3 z 40", FazaPotoku.OCR)
    )

    assert dlawik.komunikat() == "Rozpoznawanie tekstu ze skanu „skan.pdf”, strona 3 z 40"


def test_po_uplynieciu_odstepu_pokazywany_jest_najnowszy_opis() -> None:
    zegar = _ZegarKrokowy()
    dlawik = DlawikPostepu(minimalny_odstep_sekund=4.0, zegar=zegar)

    dlawik.przyjmij(_zdarzenie("Przetworzono 1 z 10 źródeł"))
    dlawik.przyjmij(_zdarzenie("Przetworzono 5 z 10 źródeł"))
    assert dlawik.komunikat() == "Przetworzono 1 z 10 źródeł"

    zegar.teraz = 5.0
    assert dlawik.komunikat() == "Przetworzono 5 z 10 źródeł"


def test_ten_sam_tekst_nie_jest_wydawany_dwa_razy() -> None:
    zegar = _ZegarKrokowy()
    dlawik = DlawikPostepu(minimalny_odstep_sekund=1.0, zegar=zegar)

    dlawik.przyjmij(_zdarzenie("Deduplikacja źródeł", faza=FazaPotoku.DEDUPLIKACJA))
    zegar.teraz = 10.0
    dlawik.przyjmij(_zdarzenie("Deduplikacja źródeł", faza=FazaPotoku.DEDUPLIKACJA))

    # Brak zmiany tekstu oznacza brak nowego czasu widocznego komunikatu, więc
    # kolejny inny opis wciąż musi poczekać na pełny odstęp od pierwszego wpisu.
    assert dlawik.komunikat() == "Deduplikacja źródeł"


def test_zdarzenie_zakonczenia_przechodzi_mimo_dlawienia() -> None:
    zegar = _ZegarKrokowy()
    dlawik = DlawikPostepu(minimalny_odstep_sekund=100.0, zegar=zegar)

    dlawik.przyjmij(_zdarzenie("Przetworzono 1 z 10 źródeł"))
    dlawik.przyjmij(_zdarzenie("Projekt zakończony", faza=FazaPotoku.ZAKONCZENIE))

    assert dlawik.komunikat() == "Projekt zakończony"
