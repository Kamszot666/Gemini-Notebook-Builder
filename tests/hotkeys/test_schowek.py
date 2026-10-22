"""Testy odczytu zaznaczenia przez schowek Windows.

Testy używają prawdziwego schowka systemowego, więc uruchamiają się tylko na
Windows (sekcja piąta, punkt piąty CLAUDE.md). Przed każdym testem zawartość
schowka użytkownika jest zapamiętywana, a po nim przywracana. Wysłanie
Control plus C do aktywnego okna jest podmieniane, żeby test nigdy nie wciskał
klawiszy w programie, który akurat ma fokus; sprawdzana jest cała reszta
przebiegu: numer sekwencji, odczyt tekstu i przywrócenie poprzedniej zawartości.
Prawdziwe wciskanie klawiszy w Chrome i Firefoksie sprawdza człowiek.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Schowek Windows działa wyłącznie na Windows."
)

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wintypes

    from gnb.hotkeys import _schowek
    from gnb.hotkeys.model import RodzajWynikuKopiowania

    _user32 = ctypes.WinDLL("user32")
    _kernel32 = ctypes.WinDLL("kernel32")
    _user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    _user32.RegisterClipboardFormatW.restype = wintypes.UINT
    _FORMAT_TESTOWY = int(_user32.RegisterClipboardFormatW("GNB testowy format schowka"))
    _BAJTY_TESTOWE = b"\x00\x01\x02 dane testowe \xff\xfe"


def _ustaw_schowek(*, tekst: str | None, bajty_testowe: bytes | None = None) -> None:
    """Ustawia schowek niezależnie od kodu testowanego modułu: własne wywołania ctypes."""
    with _schowek._otwarty_schowek():
        _user32.EmptyClipboard()
        if tekst is not None:
            _wstaw(_schowek.CF_UNICODETEXT, (tekst + "\0").encode("utf-16-le"))
        if bajty_testowe is not None:
            _wstaw(_FORMAT_TESTOWY, bajty_testowe)


def _wstaw(format_schowka: int, bajty: bytes) -> None:
    _kernel32.GlobalAlloc.restype = ctypes.c_void_p
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    uchwyt = _kernel32.GlobalAlloc(0x0002, len(bajty))
    wskaznik = _kernel32.GlobalLock(uchwyt)
    ctypes.memmove(wskaznik, bajty, len(bajty))
    _kernel32.GlobalUnlock(uchwyt)
    assert _user32.SetClipboardData(format_schowka, uchwyt)


def _bajty_w_schowku(format_schowka: int) -> bytes | None:
    with _schowek._otwarty_schowek():
        return _schowek._bajty_formatu(format_schowka)


def _formaty_w_schowku() -> list[int]:
    with _schowek._otwarty_schowek():
        return _schowek._wypisz_formaty()


@pytest.fixture(autouse=True)
def chroniony_schowek(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Zapamiętuje schowek użytkownika przed testem i przywraca go po teście."""
    migawka = _schowek.zrob_migawke()
    monkeypatch.setattr(_schowek, "poczekaj_na_puszczenie_klawiszy", lambda _limit: True)
    try:
        yield
    finally:
        if migawka is not None:
            _schowek.przywroc_migawke(migawka)


def test_numer_sekwencji_zmienia_sie_po_zmianie_schowka() -> None:
    przed = _schowek.numer_sekwencji()

    _ustaw_schowek(tekst="cokolwiek")

    assert _schowek.numer_sekwencji() != przed


def test_migawka_zachowuje_tekst_i_inny_format_i_przywraca_oba() -> None:
    _ustaw_schowek(tekst="Zażółć gęślą jaźń", bajty_testowe=_BAJTY_TESTOWE)
    migawka = _schowek.zrob_migawke()
    assert migawka is not None

    _ustaw_schowek(tekst="Zupełnie inny tekst")
    assert _bajty_w_schowku(_FORMAT_TESTOWY) is None
    assert _schowek.przywroc_migawke(migawka) is True

    assert _schowek.odczytaj_tekst_schowka() == "Zażółć gęślą jaźń"
    assert _bajty_w_schowku(_FORMAT_TESTOWY) == _BAJTY_TESTOWE


def test_migawka_pustego_schowka_przywraca_pusty_schowek() -> None:
    _ustaw_schowek(tekst=None)
    migawka = _schowek.zrob_migawke()
    assert migawka is not None
    assert migawka.formaty == ()

    _ustaw_schowek(tekst="coś innego")
    assert _schowek.przywroc_migawke(migawka) is True

    assert _formaty_w_schowku() == []


def test_schowek_z_formatem_nie_do_przywrocenia_nie_daje_migawki(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ustaw_schowek(tekst="tekst")
    monkeypatch.setattr(_schowek, "_wypisz_formaty", lambda: [_schowek.CF_ENHMETAFILE])

    assert _schowek.zrob_migawke() is None


def test_obraz_ze_skladowa_bitmapy_i_dib_jest_do_przywrocenia() -> None:
    assert _schowek._czy_format_do_pominiecia(_schowek.CF_BITMAP, [2, 8, 17]) is True
    assert _schowek._czy_format_do_pominiecia(_schowek.CF_BITMAP, [2]) is False
    assert _schowek._czy_format_niebezpieczny(_schowek.CF_BITMAP) is False


def test_skopiowane_zaznaczenie_jest_zwrocone_a_schowek_przywrocony(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ustaw_schowek(tekst="Stara zawartość", bajty_testowe=_BAJTY_TESTOWE)

    def udawane_kopiowanie() -> bool:
        _ustaw_schowek(tekst="Zaznaczony fragment strony")
        return True

    monkeypatch.setattr(_schowek, "wyslij_control_c", udawane_kopiowanie)

    wynik = _schowek.skopiuj_zaznaczenie()

    assert wynik.rodzaj is RodzajWynikuKopiowania.ZAZNACZONO
    assert wynik.tekst == "Zaznaczony fragment strony"
    assert wynik.uwaga == ""
    assert _schowek.odczytaj_tekst_schowka() == "Stara zawartość"
    assert _bajty_w_schowku(_FORMAT_TESTOWY) == _BAJTY_TESTOWE


def test_ten_sam_tekst_skopiowany_ponownie_jest_zmiana_schowka(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Zmianę wykrywa numer sekwencji, nie porównanie treści."""
    _ustaw_schowek(tekst="Ten sam tekst")
    monkeypatch.setattr(
        _schowek, "wyslij_control_c", lambda: _ustaw_schowek(tekst="Ten sam tekst") or True
    )

    wynik = _schowek.skopiuj_zaznaczenie()

    assert wynik.rodzaj is RodzajWynikuKopiowania.ZAZNACZONO
    assert wynik.tekst == "Ten sam tekst"


def test_gdy_schowek_sie_nie_zmienil_nic_nie_jest_zaznaczone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ustaw_schowek(tekst="Stara zawartość")
    monkeypatch.setattr(_schowek, "wyslij_control_c", lambda: True)

    wynik = _schowek.skopiuj_zaznaczenie(limit_zmiany_schowka_s=0.1)

    assert wynik.rodzaj is RodzajWynikuKopiowania.NIC_NIE_ZAZNACZONO
    assert _schowek.odczytaj_tekst_schowka() == "Stara zawartość"


def test_skopiowany_tekst_z_samych_bialych_znakow_to_brak_zaznaczenia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ustaw_schowek(tekst="Stara zawartość")
    monkeypatch.setattr(
        _schowek, "wyslij_control_c", lambda: _ustaw_schowek(tekst="  \r\n  ") or True
    )

    wynik = _schowek.skopiuj_zaznaczenie()

    assert wynik.rodzaj is RodzajWynikuKopiowania.NIC_NIE_ZAZNACZONO
    assert _schowek.odczytaj_tekst_schowka() == "Stara zawartość"


def test_zmiana_schowka_bez_tekstu_to_brak_zaznaczenia_i_schowek_wraca(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ustaw_schowek(tekst="Stara zawartość")
    monkeypatch.setattr(
        _schowek,
        "wyslij_control_c",
        lambda: _ustaw_schowek(tekst=None, bajty_testowe=b"obraz") or True,
    )

    wynik = _schowek.skopiuj_zaznaczenie()

    assert wynik.rodzaj is RodzajWynikuKopiowania.NIC_NIE_ZAZNACZONO
    assert _schowek.odczytaj_tekst_schowka() == "Stara zawartość"


def test_schowek_nie_do_przywrocenia_nie_wysyla_kopiowania(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wyslane: list[str] = []
    monkeypatch.setattr(_schowek, "zrob_migawke", lambda: None)
    monkeypatch.setattr(_schowek, "wyslij_control_c", lambda: wyslane.append("c") or True)

    wynik = _schowek.skopiuj_zaznaczenie()

    assert wynik.rodzaj is RodzajWynikuKopiowania.SCHOWEK_NIE_DO_PRZYWROCENIA
    assert "nie da się bezpiecznie przywrócić" in wynik.uwaga
    assert wyslane == []


def test_nieupuszczone_klawisze_skrotu_nie_wysylaja_kopiowania(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kopiowanie przy wciśniętych Control i Shift otworzyłoby narzędzia deweloperskie."""
    wyslane: list[str] = []
    monkeypatch.setattr(_schowek, "poczekaj_na_puszczenie_klawiszy", lambda _limit: False)
    monkeypatch.setattr(_schowek, "wyslij_control_c", lambda: wyslane.append("c") or True)

    wynik = _schowek.skopiuj_zaznaczenie()

    assert wynik.rodzaj is RodzajWynikuKopiowania.BLAD
    assert "klawiszy skrótu" in wynik.uwaga
    assert wyslane == []


def test_kopiowanie_jest_wysylane_dopiero_po_puszczeniu_klawiszy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kolejnosc: list[str] = []
    monkeypatch.setattr(
        _schowek,
        "poczekaj_na_puszczenie_klawiszy",
        lambda _limit: kolejnosc.append("puszczone") or True,
    )
    monkeypatch.setattr(_schowek, "wyslij_control_c", lambda: kolejnosc.append("control_c") or True)

    _schowek.skopiuj_zaznaczenie(limit_zmiany_schowka_s=0.05)

    assert kolejnosc == ["puszczone", "control_c"]
