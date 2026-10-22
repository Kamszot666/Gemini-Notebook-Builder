"""Odczyt zaznaczonego tekstu przeglądarki przez schowek Windows.

Odczyt zaznaczenia treści strony przez UI Automation w Chrome i Firefoksie nie
działa (pomiary opisane w ``gnb/hotkeys/CLAUDE.md``), więc schowek jest jedyną
znaną drogą. Moduł nie czyta schowka sam z siebie: robi to wyłącznie na
polecenie ``skopiuj_zaznaczenie``, wołane po naciśnięciu skrótu, gdy aktywnym
oknem jest przeglądarka.

Przebieg jednego odczytu: migawka dotychczasowej zawartości schowka, czekanie
na puszczenie klawiszy skrótu, wysłanie Control plus C, czekanie na zmianę
numeru sekwencji schowka, odczyt tekstu i przywrócenie migawki. Numer sekwencji,
a nie porównanie treści, wykrywa zmianę, bo ten sam tekst skopiowany drugi raz
też jest zmianą.

Klawisze skrótu trzeba puścić przed wysłaniem kopiowania: w chwili naciśnięcia
skrótu użytkownik trzyma Control i Shift, a Control plus Shift plus C w Chrome
otwiera narzędzia deweloperskie. Po puszczeniu klawiszy do przeglądarki dociera
wyłącznie syntetyczne Control plus C.

Migawka obejmuje wszystkie formaty schowka oparte na pamięci globalnej, więc
pliki skopiowane w Eksploratorze i obraz nie giną. Jeżeli schowek zawiera format,
którego nie da się bezpiecznie zapamiętać i przywrócić (metaplik, format
rysowany przez właściciela, uchwyt GDI), nic nie jest kopiowane.

Cała zawartość leży za sprawdzeniem ``sys.platform == "win32"`` z tego samego
powodu co w ``_win32.py``.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import contextlib
    import ctypes
    import ctypes.wintypes as wintypes
    import logging
    import time
    from collections.abc import Iterator
    from dataclasses import dataclass

    from gnb.core.skrot import KombinacjaSkrotu
    from gnb.hotkeys.model import RodzajWynikuKopiowania, WynikKopiowania

    _LOG = logging.getLogger("gnb.hotkeys")

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    _user32.OpenClipboard.restype = wintypes.BOOL
    _user32.CloseClipboard.restype = wintypes.BOOL
    _user32.EmptyClipboard.restype = wintypes.BOOL
    _user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    _user32.EnumClipboardFormats.restype = wintypes.UINT
    _user32.GetClipboardData.argtypes = [wintypes.UINT]
    _user32.GetClipboardData.restype = ctypes.c_void_p
    _user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    _user32.SetClipboardData.restype = ctypes.c_void_p
    _user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _user32.CreateWindowExW.restype = ctypes.c_void_p
    _user32.DestroyWindow.argtypes = [ctypes.c_void_p]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    _kernel32.GlobalAlloc.restype = ctypes.c_void_p
    _kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalFree.restype = ctypes.c_void_p
    _kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalLock.restype = ctypes.c_void_p
    _kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalUnlock.restype = wintypes.BOOL
    _kernel32.GlobalSize.argtypes = [ctypes.c_void_p]
    _kernel32.GlobalSize.restype = ctypes.c_size_t

    _GMEM_MOVEABLE = 0x0002

    CF_TEXT = 1
    CF_BITMAP = 2
    CF_METAFILEPICT = 3
    CF_DIB = 8
    CF_PALETTE = 9
    CF_ENHMETAFILE = 14
    CF_UNICODETEXT = 13
    CF_DIBV5 = 17
    _CF_WLASCICIEL_RYSUJE = 0x0080
    _CF_PRYWATNE_OD = 0x0200
    _CF_GDI_DO = 0x03FF

    _VK_SHIFT = 0x10
    _VK_CONTROL = 0x11
    _VK_ALT = 0x12
    _VK_LEWY_WINDOWS = 0x5B
    _VK_PRAWY_WINDOWS = 0x5C
    _VK_C = 0x43

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002

    _LIMIT_ROZMIARU_MIGAWKI_BAJTOW = 64 * 1024 * 1024
    _ODSTEP_SPRAWDZANIA_S = 0.015
    _PROBY_OTWARCIA_SCHOWKA = 10
    _PRZERWA_MIEDZY_PROBAMI_S = 0.02

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = (
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        )

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = (
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.c_size_t),
        )

    class _UNIA_WEJSCIA(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT))

    class _INPUT(ctypes.Structure):
        _fields_ = (("type", wintypes.DWORD), ("u", _UNIA_WEJSCIA))

    _user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int]
    _user32.SendInput.restype = wintypes.UINT

    class SchowekNiedostepny(Exception):
        """Schowek jest zajęty przez inny program albo nie dało się utworzyć okna właściciela."""

    @dataclass(frozen=True, slots=True)
    class _Migawka:
        """Dotychczasowa zawartość schowka: formaty i ich surowe bajty."""

        formaty: tuple[tuple[int, bytes], ...]

    def numer_sekwencji() -> int:
        """Zwraca numer sekwencji schowka, który zmienia się przy każdej zmianie zawartości."""
        return int(_user32.GetClipboardSequenceNumber())

    @contextlib.contextmanager
    def _otwarty_schowek() -> Iterator[None]:
        """Otwiera schowek na czas bloku, z własnym oknem właściciela.

        Okno jest potrzebne, bo po ``OpenClipboard(NULL)`` funkcja
        ``EmptyClipboard`` ustawia właściciela na NULL, a wtedy
        ``SetClipboardData`` kończy się błędem. Schowek bywa chwilowo zajęty
        przez inny program, więc otwarcie jest ponawiane kilka razy.
        """
        okno = _user32.CreateWindowExW(0, "STATIC", None, 0, 0, 0, 0, 0, None, None, None, None)
        if not okno:
            raise SchowekNiedostepny("Nie udało się utworzyć okna właściciela schowka.")
        try:
            for _ in range(_PROBY_OTWARCIA_SCHOWKA):
                if _user32.OpenClipboard(okno):
                    break
                time.sleep(_PRZERWA_MIEDZY_PROBAMI_S)
            else:
                raise SchowekNiedostepny("Schowek jest zajęty przez inny program.")
            try:
                yield
            finally:
                _user32.CloseClipboard()
        finally:
            _user32.DestroyWindow(okno)

    def _wypisz_formaty() -> list[int]:
        formaty: list[int] = []
        format_biezacy = 0
        while True:
            format_biezacy = int(_user32.EnumClipboardFormats(format_biezacy))
            if format_biezacy == 0:
                return formaty
            formaty.append(format_biezacy)

    def _czy_format_do_pominiecia(format_schowka: int, wszystkie: list[int]) -> bool:
        """Formaty rysowane z innych, które Windows składa sam po przywróceniu."""
        if format_schowka in (CF_BITMAP, CF_PALETTE):
            return CF_DIB in wszystkie or CF_DIBV5 in wszystkie
        return False

    def _czy_format_niebezpieczny(format_schowka: int) -> bool:
        return (
            format_schowka in (CF_METAFILEPICT, CF_ENHMETAFILE)
            or _CF_WLASCICIEL_RYSUJE <= format_schowka < 0x0100
            or _CF_PRYWATNE_OD <= format_schowka <= _CF_GDI_DO
        )

    def _bajty_formatu(format_schowka: int) -> bytes | None:
        """Kopiuje bajty formatu opartego na pamięci globalnej albo zwraca ``None``."""
        uchwyt = _user32.GetClipboardData(format_schowka)
        if not uchwyt:
            return None
        rozmiar = int(_kernel32.GlobalSize(uchwyt))
        if rozmiar == 0:
            return None
        wskaznik = _kernel32.GlobalLock(uchwyt)
        if not wskaznik:
            return None
        try:
            return ctypes.string_at(wskaznik, rozmiar)
        finally:
            _kernel32.GlobalUnlock(uchwyt)

    def zrob_migawke() -> _Migawka | None:
        """Zapamiętuje schowek albo zwraca ``None``, gdy nie da się go bezpiecznie przywrócić.

        Pusty schowek jest poprawną migawką. Zgłasza ``SchowekNiedostepny``,
        gdy schowka nie dało się otworzyć.
        """
        with _otwarty_schowek():
            wszystkie = _wypisz_formaty()
            zapamietane: list[tuple[int, bytes]] = []
            suma_bajtow = 0
            for format_schowka in wszystkie:
                if _czy_format_do_pominiecia(format_schowka, wszystkie):
                    continue
                if _czy_format_niebezpieczny(format_schowka):
                    return None
                bajty = _bajty_formatu(format_schowka)
                if bajty is None:
                    return None
                suma_bajtow += len(bajty)
                if suma_bajtow > _LIMIT_ROZMIARU_MIGAWKI_BAJTOW:
                    return None
                zapamietane.append((format_schowka, bajty))
            return _Migawka(tuple(zapamietane))

    def przywroc_migawke(migawka: _Migawka) -> bool:
        """Przywraca zapamiętaną zawartość schowka. Zwraca fałsz, gdy się nie udało."""
        try:
            with _otwarty_schowek():
                _user32.EmptyClipboard()
                for format_schowka, bajty in migawka.formaty:
                    uchwyt = _kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(bajty))
                    if not uchwyt:
                        return False
                    wskaznik = _kernel32.GlobalLock(uchwyt)
                    if not wskaznik:
                        _kernel32.GlobalFree(uchwyt)
                        return False
                    ctypes.memmove(wskaznik, bajty, len(bajty))
                    _kernel32.GlobalUnlock(uchwyt)
                    if not _user32.SetClipboardData(format_schowka, uchwyt):
                        _kernel32.GlobalFree(uchwyt)
                        return False
        except SchowekNiedostepny:
            return False
        return True

    def odczytaj_tekst_schowka() -> str | None:
        """Zwraca tekst Unicode ze schowka albo ``None``, gdy go tam nie ma."""
        with _otwarty_schowek():
            uchwyt = _user32.GetClipboardData(CF_UNICODETEXT)
            if not uchwyt:
                return None
            wskaznik = _kernel32.GlobalLock(uchwyt)
            if not wskaznik:
                return None
            try:
                return ctypes.wstring_at(wskaznik)
            finally:
                _kernel32.GlobalUnlock(uchwyt)

    def klawisze_kombinacji(kombinacja: KombinacjaSkrotu) -> tuple[int, ...]:
        """Kody klawiszy wirtualnych, które trzeba puścić po naciśnięciu tej kombinacji."""
        klawisze: list[int] = []
        if kombinacja.control:
            klawisze.append(_VK_CONTROL)
        if kombinacja.alt:
            klawisze.append(_VK_ALT)
        if kombinacja.shift:
            klawisze.append(_VK_SHIFT)
        if kombinacja.windows:
            klawisze.extend((_VK_LEWY_WINDOWS, _VK_PRAWY_WINDOWS))
        klawisze.append(kombinacja.kod_klawisza_win32())
        return tuple(klawisze)

    def poczekaj_na_puszczenie_klawiszy(kombinacja: KombinacjaSkrotu, limit_s: float) -> bool:
        """Czeka, aż modyfikatory i klawisz tej kombinacji zostaną puszczone.

        Zwraca fałsz po limicie. Sprawdzane są wyłącznie klawisze wybranej
        kombinacji, a nie stałe Control, Shift i F12.
        """
        klawisze = klawisze_kombinacji(kombinacja)
        koniec = time.monotonic() + limit_s
        while time.monotonic() < koniec:
            if not any(_user32.GetAsyncKeyState(klawisz) & 0x8000 for klawisz in klawisze):
                return True
            time.sleep(_ODSTEP_SPRAWDZANIA_S)
        return False

    def _zdarzenie_klawisza(kod: int, *, puszczony: bool) -> _INPUT:
        wejscie = _INPUT()
        wejscie.type = _INPUT_KEYBOARD
        wejscie.u.ki = _KEYBDINPUT(kod, 0, _KEYEVENTF_KEYUP if puszczony else 0, 0, 0)
        return wejscie

    def wyslij_control_c() -> bool:
        """Wysyła do aktywnego okna wyłącznie Control plus C. Zwraca fałsz, gdy się nie udało."""
        zdarzenia = (_INPUT * 4)(
            _zdarzenie_klawisza(_VK_CONTROL, puszczony=False),
            _zdarzenie_klawisza(_VK_C, puszczony=False),
            _zdarzenie_klawisza(_VK_C, puszczony=True),
            _zdarzenie_klawisza(_VK_CONTROL, puszczony=True),
        )
        return int(_user32.SendInput(4, zdarzenia, ctypes.sizeof(_INPUT))) == 4

    def skopiuj_zaznaczenie(
        kombinacja: KombinacjaSkrotu,
        limit_puszczenia_klawiszy_s: float = 2.0,
        limit_zmiany_schowka_s: float = 1.0,
    ) -> WynikKopiowania:
        """Kopiuje zaznaczenie aktywnej przeglądarki przez schowek i przywraca schowek.

        Gdy schowek zawiera coś, czego nie da się bezpiecznie przywrócić,
        niczego nie kopiuje. Gdy numer sekwencji schowka się nie zmienił albo
        w schowku po kopiowaniu nie ma tekstu, uznaje, że nic nie zaznaczono.
        """
        try:
            migawka = zrob_migawke()
        except SchowekNiedostepny as blad:
            return WynikKopiowania(RodzajWynikuKopiowania.BLAD, uwaga=str(blad))
        if migawka is None:
            return WynikKopiowania(
                RodzajWynikuKopiowania.SCHOWEK_NIE_DO_PRZYWROCENIA,
                uwaga=(
                    "Schowek zawiera dane, których nie da się bezpiecznie przywrócić, "
                    "więc nie sprawdzono zaznaczonego tekstu."
                ),
            )
        if not poczekaj_na_puszczenie_klawiszy(kombinacja, limit_puszczenia_klawiszy_s):
            return WynikKopiowania(
                RodzajWynikuKopiowania.BLAD,
                uwaga="Nie puszczono klawiszy skrótu, więc nie sprawdzono zaznaczonego tekstu.",
            )

        numer_przed = numer_sekwencji()
        if not wyslij_control_c():
            return WynikKopiowania(
                RodzajWynikuKopiowania.BLAD,
                uwaga="Windows odrzucił wysłanie kopiowania do przeglądarki.",
            )
        koniec = time.monotonic() + limit_zmiany_schowka_s
        while numer_sekwencji() == numer_przed and time.monotonic() < koniec:
            time.sleep(_ODSTEP_SPRAWDZANIA_S)
        if numer_sekwencji() == numer_przed:
            return WynikKopiowania(RodzajWynikuKopiowania.NIC_NIE_ZAZNACZONO)

        # Przeglądarka potrafi zapisać schowek kilka razy z rzędu, więc chwila
        # na ustabilizowanie się numeru sekwencji przed odczytem.
        time.sleep(0.05)
        try:
            tekst = odczytaj_tekst_schowka()
            uwaga = ""
        except SchowekNiedostepny:
            tekst = None
            uwaga = "Nie udało się odczytać schowka po kopiowaniu."
        if not przywroc_migawke(migawka):
            uwaga = (
                uwaga + " " if uwaga else ""
            ) + "Nie udało się przywrócić poprzedniej zawartości schowka."
            _LOG.warning(uwaga)
        if tekst is None or not tekst.strip():
            rodzaj = RodzajWynikuKopiowania.NIC_NIE_ZAZNACZONO
            return WynikKopiowania(rodzaj, uwaga=uwaga)
        return WynikKopiowania(RodzajWynikuKopiowania.ZAZNACZONO, tekst=tekst, uwaga=uwaga)
