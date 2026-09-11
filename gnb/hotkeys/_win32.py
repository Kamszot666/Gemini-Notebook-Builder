"""Warstwa Win32 przez ctypes: rejestracja skrótu, pętla komunikatów, aktywne okno.

Moduł jest importowalny na każdym systemie, ale cała jego zawartość leży za
sprawdzeniem ``sys.platform == "win32"``, zgodnie z sekcją piątą CLAUDE.md:
dzięki temu ``python -m mypy gnb --platform linux`` pomija tę gałąź zamiast
zgłaszać błąd o nieistniejącym na Linuksie ``ctypes.windll``. Na Linuksie ten
moduł po prostu nic nie definiuje — nic w resztę pakietu go bezwarunkowo nie
importuje, patrz ``gnb/hotkeys/obsluga.py``.

Rejestracja i wyrejestrowanie skrótu muszą zajść w tym samym wątku Win32,
dlatego cały cykl życia — rejestracja, pętla komunikatów ``GetMessage``,
wyrejestrowanie — jest zamknięty w jednym wątku zarządzanym przez klasę
``WatekSkrotu``.
"""

from __future__ import annotations

import sys

from gnb.hotkeys.model import InformacjeOOknie
from gnb.hotkeys.stale import IDENTYFIKATOR_SKROTU, KOD_KLAWISZA_SKROTU, MODYFIKATORY_SKROTU

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wintypes
    import logging
    import threading
    from collections.abc import Callable

    _LOG = logging.getLogger("gnb.hotkeys")

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    WM_HOTKEY = 0x0312
    WM_QUIT = 0x0012
    ERROR_HOTKEY_ALREADY_REGISTERED = 1409

    _DLUGOSC_BUFORA_KLASY = 256
    _DLUGOSC_BUFORA_SCIEZKI = 1024
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    class _MSG(ctypes.Structure):
        _fields_ = (
            ("hwnd", wintypes.HWND),
            ("message", wintypes.UINT),
            ("wParam", wintypes.WPARAM),
            ("lParam", wintypes.LPARAM),
            ("time", wintypes.DWORD),
            ("pt", wintypes.POINT),
        )

    def informacje_o_aktywnym_oknie() -> InformacjeOOknie | None:
        """Zwraca migawkę aktywnego okna albo ``None``, gdy żadne okno nie jest aktywne."""
        uchwyt = _user32.GetForegroundWindow()
        if not uchwyt:
            return None
        return InformacjeOOknie(
            uchwyt=uchwyt,
            tytul=_tytul_okna(uchwyt),
            nazwa_klasy=_nazwa_klasy(uchwyt),
            nazwa_procesu=_nazwa_procesu(uchwyt),
        )

    def _tytul_okna(uchwyt: int) -> str:
        dlugosc = _user32.GetWindowTextLengthW(uchwyt)
        if dlugosc == 0:
            return ""
        bufor = ctypes.create_unicode_buffer(dlugosc + 1)
        _user32.GetWindowTextW(uchwyt, bufor, dlugosc + 1)
        return str(bufor.value)

    def _nazwa_klasy(uchwyt: int) -> str:
        bufor = ctypes.create_unicode_buffer(_DLUGOSC_BUFORA_KLASY)
        _user32.GetClassNameW(uchwyt, bufor, _DLUGOSC_BUFORA_KLASY)
        return str(bufor.value)

    def _nazwa_procesu(uchwyt: int) -> str:
        """Zwraca nazwę pliku wykonywalnego procesu właściciela okna, bez rozszerzenia.

        Rozpoznanie po nazwie procesu, a nie po położeniu okna na ekranie, jest
        wymagane sekcją drugą CLAUDE.md: komunikaty muszą nazywać program przez
        jego rzeczywistą nazwę.
        """
        pid = wintypes.DWORD()
        _user32.GetWindowThreadProcessId(uchwyt, ctypes.byref(pid))
        if not pid.value:
            return ""
        uchwyt_procesu = _kernel32.OpenProcess(
            _PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value
        )
        if not uchwyt_procesu:
            return ""
        try:
            bufor = ctypes.create_unicode_buffer(_DLUGOSC_BUFORA_SCIEZKI)
            rozmiar = wintypes.DWORD(_DLUGOSC_BUFORA_SCIEZKI)
            udalo_sie = _kernel32.QueryFullProcessImageNameW(
                uchwyt_procesu, 0, bufor, ctypes.byref(rozmiar)
            )
            if not udalo_sie:
                return ""
            sciezka = str(bufor.value)
        finally:
            _kernel32.CloseHandle(uchwyt_procesu)
        nazwa_pliku = sciezka.rsplit("\\", 1)[-1]
        if nazwa_pliku.lower().endswith(".exe"):
            nazwa_pliku = nazwa_pliku[:-4]
        return nazwa_pliku.lower()

    class WatekSkrotu:
        """Rejestruje globalny skrót i prowadzi jego pętlę komunikatów w osobnym wątku.

        Wątek startuje razem z serwerem interfejsu, tylko gdy funkcja jest
        włączona w konfiguracji, i kończy się przy jego zamknięciu — żaden
        osobny proces w tle, żaden autostart, zgodnie z decyzją pierwszą
        sekcji dwunastej CLAUDE.md.

        Naciśnięcie skrótu jest obsługiwane w nowym, osobnym wątku roboczym, nie
        w tym wątku: odczyt stanu pulpitu i dalsze przetwarzanie nie mogą zająć
        pętli komunikatów, bo wtedy kolejne naciśnięcia skrótu i komunikat
        kończący pracę czekałyby w kolejce.
        """

        def __init__(self, przy_nacisnieciu: Callable[[], None]) -> None:
            self._przy_nacisnieciu = przy_nacisnieciu
            self._watek: threading.Thread | None = None
            self._id_watku: int | None = None
            self._zdarzenie_gotowosci = threading.Event()
            self._zarejestrowano = False
            self._kod_bledu_rejestracji: int | None = None

        @property
        def zarejestrowano(self) -> bool:
            return self._zarejestrowano

        @property
        def kod_bledu_rejestracji(self) -> int | None:
            return self._kod_bledu_rejestracji

        def uruchom(self, limit_czasu_sekundy: float = 5.0) -> bool:
            """Startuje wątek, rejestruje skrót i czeka na wynik rejestracji.

            Zwraca prawdę, gdy rejestracja się powiodła. Nieudana rejestracja —
            na przykład skrót zajęty przez inny program — nie jest wyjątkiem
            i nie zatrzymuje aplikacji, zgodnie z decyzją czwartą sekcji
            dwunastej CLAUDE.md; wywołujący loguje wynik i pracuje dalej.
            """
            self._watek = threading.Thread(
                target=self._petla, name="gnb-globalny-skrot", daemon=True
            )
            self._watek.start()
            self._zdarzenie_gotowosci.wait(timeout=limit_czasu_sekundy)
            return self._zarejestrowano

        def zatrzymaj(self, limit_czasu_sekundy: float = 2.0) -> None:
            """Wysyła komunikat kończący pracę do wątku pętli i czeka na jej zakończenie."""
            if self._watek is None or not self._watek.is_alive():
                return
            if self._id_watku is not None:
                _user32.PostThreadMessageW(self._id_watku, WM_QUIT, 0, 0)
            self._watek.join(timeout=limit_czasu_sekundy)

        def _petla(self) -> None:
            self._id_watku = _kernel32.GetCurrentThreadId()
            udalo_sie = _user32.RegisterHotKey(
                None, IDENTYFIKATOR_SKROTU, MODYFIKATORY_SKROTU, KOD_KLAWISZA_SKROTU
            )
            self._zarejestrowano = bool(udalo_sie)
            if not udalo_sie:
                self._kod_bledu_rejestracji = ctypes.GetLastError()
            self._zdarzenie_gotowosci.set()
            if not udalo_sie:
                return
            try:
                self._pompuj_komunikaty()
            finally:
                _user32.UnregisterHotKey(None, IDENTYFIKATOR_SKROTU)

        def _pompuj_komunikaty(self) -> None:
            komunikat = _MSG()
            while True:
                wynik = _user32.GetMessageW(ctypes.byref(komunikat), None, 0, 0)
                if wynik <= 0:
                    return
                if komunikat.message == WM_HOTKEY:
                    self._obsluz_nacisniecie()
                _user32.TranslateMessage(ctypes.byref(komunikat))
                _user32.DispatchMessageW(ctypes.byref(komunikat))

        def _obsluz_nacisniecie(self) -> None:
            threading.Thread(
                target=self._bezpiecznie_obsluz, name="gnb-obsluga-skrotu", daemon=True
            ).start()

        def _bezpiecznie_obsluz(self) -> None:
            try:
                self._przy_nacisnieciu()
            except Exception:
                _LOG.exception("Nieobsłużony błąd w obsłudze naciśnięcia globalnego skrótu.")
