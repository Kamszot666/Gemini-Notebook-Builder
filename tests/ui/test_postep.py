"""Testy dławienia komunikatów postępu dla regionu role="status"."""

from __future__ import annotations

from gnb.core.postep import FazaPotoku, ZdarzeniePostepu
from gnb.ui.postep import DlawikPostepu, KalkulatorProcentu


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


def _zd(faza: FazaPotoku, wykonano: int, wszystkich: int, opis: str = "opis") -> ZdarzeniePostepu:
    return ZdarzeniePostepu(faza=faza, wykonano=wykonano, wszystkich=wszystkich, opis=opis)


def test_kalkulator_procentu_liczy_proporcjonalnie_do_zgloszonych_krokow() -> None:
    """Jedenaście źródeł ekstrakcji plus po jednym kroku dedup i pakowania daje budżet 13.

    Trzy przetworzone źródła to trzy z trzynastu, zaokrąglone w dół do pełnej
    dziesiątki: 300 // 13 = 23, w dół do 20.
    """
    kalkulator = KalkulatorProcentu(liczba_pozycji=11)
    wynik = kalkulator.opatrz_procentem(
        _zd(FazaPotoku.EKSTRAKCJA, 3, 11, "Przetworzono 3 z 11 źródeł")
    )
    assert wynik.opis == "Postęp: 20 procent, Przetworzono 3 z 11 źródeł"


def test_kalkulator_procentu_nie_cofa_sie_gdy_pobieranie_konczy_sie_przed_ekstrakcja() -> None:
    """Budżet ekstrakcji jest wpisany z góry, więc szybkie pobranie stron nie zawyża procentu.

    Bez wpisania budżetu ekstrakcji z góry zakończenie samego pobierania trzech
    stron (przy nieznanym jeszcze budżecie eksrakcji) dawałoby chwilowo 60
    procent, które trzeba by potem cofnąć do 20 — to właśnie ten test chroni.
    """
    kalkulator = KalkulatorProcentu(liczba_pozycji=11)

    kalkulator.opatrz_procentem(_zd(FazaPotoku.POBIERANIE_STRON, 0, 3))
    po_pobraniu = kalkulator.opatrz_procentem(_zd(FazaPotoku.POBIERANIE_STRON, 3, 3))
    assert po_pobraniu.opis.startswith("Postęp: 10 procent")

    po_pierwszym_zrodle = kalkulator.opatrz_procentem(_zd(FazaPotoku.EKSTRAKCJA, 1, 11))
    assert po_pierwszym_zrodle.opis.startswith("Postęp: 20 procent")


def test_kalkulator_procentu_nie_cofa_sie_gdy_dochodzi_dedup_i_pakowanie() -> None:
    """Cała sekwencja jednego przebiegu: procent nigdy nie maleje między zdarzeniami."""
    kalkulator = KalkulatorProcentu(liczba_pozycji=11)
    sekwencja = [
        _zd(FazaPotoku.POBIERANIE_STRON, 0, 3),
        _zd(FazaPotoku.POBIERANIE_STRON, 3, 3),
        _zd(FazaPotoku.EKSTRAKCJA, 1, 11),
        _zd(FazaPotoku.EKSTRAKCJA, 6, 11),
        _zd(FazaPotoku.EKSTRAKCJA, 11, 11),
        _zd(FazaPotoku.DEDUPLIKACJA, 0, 1),
        _zd(FazaPotoku.DEDUPLIKACJA, 1, 1),
        _zd(FazaPotoku.PAKOWANIE, 0, 1),
        _zd(FazaPotoku.PAKOWANIE, 1, 1),
        _zd(FazaPotoku.ZAKONCZENIE, 1, 1, "Projekt zakończony"),
    ]

    procenty = []
    for zdarzenie in sekwencja:
        opis = kalkulator.opatrz_procentem(zdarzenie).opis
        procenty.append(int(opis.split(" ")[1]))

    assert procenty == sorted(procenty)
    assert procenty[-1] == 100


def test_kalkulator_procentu_nie_zmienia_opisu_fazy_ocr() -> None:
    """OCR mówi o postępie jednego źródła, nie całego przebiegu — bez prefiksu procentu."""
    kalkulator = KalkulatorProcentu(liczba_pozycji=1)
    wynik = kalkulator.opatrz_procentem(
        _zd(FazaPotoku.OCR, 3, 40, "Rozpoznawanie tekstu ze skanu, strona 3 z 40")
    )
    assert wynik.opis == "Rozpoznawanie tekstu ze skanu, strona 3 z 40"
