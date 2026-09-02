"""Lokalny serwer HTTP interfejsu WWW.

Serwer nasłuchuje wyłącznie na adresie z konfiguracji, który musi być pętlą
zwrotną, zgodnie z sekcją jedenastą CLAUDE.md. Routing jest prostą tablicą tras.
Treść stron budują funkcje z ``gnb.ui.widoki``; ten moduł spina je z żądaniem,
konfiguracją, rejestrem zadań w tle i plikiem pól notatnika.

Operacje zmieniające stan wymagają metody POST i zgodnego tokenu CSRF. Po
udanym POST serwer przekierowuje na stronę wynikową, żeby odświeżenie strony nie
powtarzało operacji. Nieudana walidacja formularza zwraca stronę z listą błędów,
bez przekierowania.
"""

from __future__ import annotations

import json
import logging
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlsplit

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.nazwy import sanityzuj_nazwe_projektu
from gnb.core.postep import WywolanieZwrotnePostepu
from gnb.core.wyjatki import BladGnb
from gnb.ingestion.wejscie import (
    PozycjaWejsciowa,
    przyjmij_plik,
    przyjmij_tekst,
    przyjmij_url,
)
from gnb.persistence import pola_notatnika
from gnb.persistence.checkpoint import wczytaj
from gnb.persistence.pola_notatnika import PolaNotatnika, PrzekroczonoLimitZnakow
from gnb.persistence.projekt import ustal_uklad, utworz_katalogi
from gnb.potok import WynikPrzetwarzania, odtworz_wejscia, przetworz_projekt
from gnb.ui import csrf, formularze, widoki
from gnb.ui.projekty import niedokonczone
from gnb.ui.widoki import BladPola, DaneFormularzaProjektu, PodsumowanieWyniku, sciezka_projektu
from gnb.ui.zadania import RejestrZadan, StanZadania, ZadanieJuzTrwa

_LOG = logging.getLogger("gnb.ui")
_TYP_HTML = "text/html; charset=utf-8"
_TYP_JSON = "application/json; charset=utf-8"
_NADWYZKA_LIMITU_BAJTOW = 1_048_576
_BAJTOW_W_MEGABAJCIE = 1024 * 1024


class _Serwer(ThreadingHTTPServer):
    """Serwer wątkowy przechowujący konfigurację i rejestr zadań dla obsługi żądań."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        adres: tuple[str, int],
        konfiguracja: Konfiguracja,
        rejestr: RejestrZadan,
    ) -> None:
        if ":" in adres[0]:
            self.address_family = socket.AF_INET6
        super().__init__(adres, _Handler)
        self.konfiguracja = konfiguracja
        self.rejestr = rejestr


def zbuduj_serwer(
    konfiguracja: Konfiguracja, rejestr: RejestrZadan | None = None
) -> ThreadingHTTPServer:
    """Buduje serwer bez uruchamiania go. Wydzielone z ``uruchom_serwer`` na potrzeby testów."""
    return _Serwer(
        (konfiguracja.adres_nasluchu, konfiguracja.port_nasluchu),
        konfiguracja,
        rejestr or RejestrZadan(),
    )


def uruchom_serwer(konfiguracja: Konfiguracja, *, rejestr: RejestrZadan | None = None) -> None:
    """Uruchamia serwer i blokuje do przerwania klawiszem.

    Adres i port pochodzą z konfiguracji. Adres jest tam już zweryfikowany jako
    pętla zwrotna, więc serwer nie może przypadkiem wystawić się do sieci.
    """
    serwer = zbuduj_serwer(konfiguracja, rejestr)
    adres = f"http://{konfiguracja.adres_nasluchu}:{serwer.server_address[1]}/"
    print(f"Interfejs Gemini Notebook Builder działa pod adresem {adres}", flush=True)
    print(
        "Otwórz ten adres w przeglądarce. Serwer zatrzymasz klawiszami Control plus C.",
        flush=True,
    )
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Zatrzymywanie serwera.")
    finally:
        serwer.shutdown()
        serwer.server_close()


class _Handler(BaseHTTPRequestHandler):
    """Obsługa pojedynczego żądania HTTP interfejsu."""

    server_version = "GeminiNotebookBuilder"
    protocol_version = "HTTP/1.1"

    # Domyślne logowanie BaseHTTPRequestHandler pisze wprost na standardowe
    # wyjście błędów. Kierujemy je do rejestratora zamiast zaśmiecać konsolę,
    # z której użytkownik czyta komunikaty startowe.
    def log_message(self, fmt: str, *args: object) -> None:
        _LOG.info("%s - %s", self.address_string(), fmt % args)

    @property
    def _serwer(self) -> _Serwer:
        return cast("_Serwer", self.server)

    @property
    def _konfiguracja(self) -> Konfiguracja:
        return self._serwer.konfiguracja

    # --- routing ---------------------------------------------------------

    def do_GET(self) -> None:
        self._bezpiecznie(self._trasuj_get)

    def do_POST(self) -> None:
        self._bezpiecznie(self._trasuj_post)

    def _bezpiecznie(self, akcja: Callable[[], None]) -> None:
        """Wykonuje obsługę żądania, zamieniając nieobsłużony wyjątek na stronę 500."""
        try:
            akcja()
        except Exception:
            _LOG.exception("Nieobsłużony błąd przy %s %s", self.command, self.path)
            try:
                self._blad(500, "Błąd wewnętrzny", "Coś poszło nie tak po stronie serwera.")
            except OSError:
                pass

    def _trasuj_get(self) -> None:
        sciezka = urlsplit(self.path).path
        if sciezka == "/":
            self._pokaz_strone_glowna()
        elif sciezka == widoki.SCIEZKA_POSTEPU:
            self._pokaz_postep()
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/prompt"):
            self._pokaz_prompt(self._nazwa_z_url(sciezka[len("/projekt/") : -len("/prompt")]))
        elif sciezka.startswith("/projekt/"):
            self._pokaz_projekt(self._nazwa_z_url(sciezka[len("/projekt/") :]))
        else:
            self._blad(404, "Nie znaleziono", "Pod tym adresem nie ma żadnej strony.")

    def _trasuj_post(self) -> None:
        sciezka = urlsplit(self.path).path
        if sciezka == "/projekt/nowy":
            self._utworz_projekt()
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/wznow"):
            self._wznow_projekt(self._nazwa_z_url(sciezka[len("/projekt/") : -len("/wznow")]))
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/pola"):
            self._zapisz_pola(self._nazwa_z_url(sciezka[len("/projekt/") : -len("/pola")]))
        else:
            self._blad(404, "Nie znaleziono", "Pod tym adresem nie ma żadnej operacji.")

    # --- widoki ---------------------------------------------------------

    def _pokaz_strone_glowna(
        self,
        *,
        kod: int = 200,
        dane: DaneFormularzaProjektu | None = None,
        bledy: list[BladPola] | None = None,
    ) -> None:
        token = self._token_sesji()
        html = widoki.strona_glowna(
            projekty=niedokonczone(self._konfiguracja.katalog_wynikow),
            token_csrf=token,
            dane=dane,
            bledy=bledy,
        )
        self._wyslij_html(kod, html, token=token)

    def _pokaz_projekt(
        self,
        nazwa: str,
        *,
        kod: int = 200,
        bledy: list[BladPola] | None = None,
    ) -> None:
        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        if not uklad.katalog_projektu.is_dir():
            self._blad(404, "Nie znaleziono projektu", f"Nie ma projektu o nazwie „{nazwa}”.")
            return

        informacja = self._serwer.rejestr.informacja()
        if informacja is not None and informacja.nazwa_projektu != uklad.nazwa_projektu:
            informacja = None

        podsumowanie: PodsumowanieWyniku | None = None
        raport: str | None = None
        zakonczone = informacja is not None and informacja.stan is StanZadania.ZAKONCZONE
        wynik = informacja.wynik if informacja is not None else None
        if zakonczone and wynik is not None:
            podsumowanie = PodsumowanieWyniku(
                liczba_przetworzonych=wynik.liczba_przetworzonych,
                liczba_pominietych=wynik.liczba_pominietych,
                liczba_bledow=wynik.liczba_bledow,
                katalog_projektu=str(wynik.katalog_projektu),
                wznowiono=wynik.wznowiono,
            )
            raport = _odczytaj_tekst(uklad.raport)
        elif informacja is None and uklad.raport.is_file():
            raport = _odczytaj_tekst(uklad.raport)

        token = self._token_sesji()
        html = widoki.strona_projektu(
            nazwa=uklad.nazwa_projektu,
            informacja=informacja,
            pola=pola_notatnika.wczytaj(uklad.pola_notatnika),
            limit_znakow_instrukcji=self._konfiguracja.limit_znakow_instrukcji_systemowej,
            token_csrf=token,
            podsumowanie=podsumowanie,
            raport=raport,
            bledy=bledy,
        )
        self._wyslij_html(kod, html, token=token)

    def _pokaz_prompt(self, nazwa: str) -> None:
        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        if not uklad.katalog_projektu.is_dir():
            self._blad(404, "Nie znaleziono projektu", f"Nie ma projektu o nazwie „{nazwa}”.")
            return
        pola = pola_notatnika.wczytaj(uklad.pola_notatnika)
        self._wyslij_html(
            200, widoki.strona_promptu(nazwa=uklad.nazwa_projektu, prompt=pola.prompt_wyszukiwania)
        )

    def _pokaz_postep(self) -> None:
        informacja = self._serwer.rejestr.informacja()
        if informacja is None:
            dane = {"komunikat": "", "stan": "brak"}
        else:
            dane = {"komunikat": informacja.komunikat_postepu, "stan": informacja.stan.value}
        self._wyslij(200, json.dumps(dane, ensure_ascii=False).encode("utf-8"), _TYP_JSON)

    # --- operacje ------------------------------------------------------

    def _utworz_projekt(self) -> None:
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return

        dane = DaneFormularzaProjektu(
            nazwa_projektu=wynik_formularza.pole("nazwa_projektu").strip(),
            tekst=wynik_formularza.pole("tekst"),
            adresy=wynik_formularza.pole("adresy"),
            grupa=wynik_formularza.pole("grupa").strip(),
        )
        bledy: list[BladPola] = []
        if not dane.nazwa_projektu:
            bledy.append(BladPola("nazwa_projektu", "Nazwa projektu jest wymagana."))

        adresy = [wiersz.strip() for wiersz in dane.adresy.splitlines() if wiersz.strip()]
        pliki = [plik for plik in wynik_formularza.pliki if plik.zawartosc]
        if not dane.tekst.strip() and not adresy and not pliki:
            bledy.append(
                BladPola("tekst", "Podaj przynajmniej jedno źródło: tekst, adres albo plik.")
            )

        nazwa_bezpieczna = ""
        if dane.nazwa_projektu:
            try:
                nazwa_bezpieczna = sanityzuj_nazwe_projektu(dane.nazwa_projektu)
            except BladGnb as blad:
                bledy.append(BladPola("nazwa_projektu", blad.komunikat))

        if bledy:
            self._pokaz_strone_glowna(kod=400, dane=dane, bledy=bledy)
            return

        grupa = dane.grupa or None
        try:
            self._uruchom_nowy_projekt(nazwa_bezpieczna, dane, adresy, pliki, grupa)
        except ZadanieJuzTrwa as blad:
            self._pokaz_strone_glowna(
                kod=409, dane=dane, bledy=[BladPola("nazwa_projektu", str(blad))]
            )
            return
        self._przekieruj(sciezka_projektu(nazwa_bezpieczna))

    def _uruchom_nowy_projekt(
        self,
        nazwa: str,
        dane: DaneFormularzaProjektu,
        adresy: list[str],
        pliki: list[formularze.PlikFormularza],
        grupa: str | None,
    ) -> None:
        konfiguracja = self._konfiguracja
        uklad = ustal_uklad(konfiguracja.katalog_wynikow, nazwa)
        utworz_katalogi(uklad, z_materialami_zrodlowymi=konfiguracja.zachowuj_oryginaly)

        moment = datetime.now(UTC)
        pozycje: list[PozycjaWejsciowa] = []
        if dane.tekst.strip():
            pozycje.append(przyjmij_tekst(dane.tekst, moment, grupa=grupa))
        for adres in adresy:
            pozycje.append(
                przyjmij_url(adres, moment, konfiguracja.dodatkowe_parametry_sledzace, grupa=grupa)
            )
        for plik in pliki:
            sciezka = self._zapisz_plik_wejsciowy(uklad.pliki_wejsciowe, plik)
            pozycje.append(przyjmij_plik(sciezka, moment, grupa=grupa))

        def praca(postep: WywolanieZwrotnePostepu) -> WynikPrzetwarzania:
            return przetworz_projekt(pozycje, konfiguracja, nazwa_projektu=nazwa, postep=postep)

        self._serwer.rejestr.uruchom(nazwa, praca)

    def _wznow_projekt(self, nazwa: str) -> None:
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return

        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        checkpoint = wczytaj(uklad.checkpoint) if uklad.checkpoint.is_file() else None
        if checkpoint is None:
            self._blad(
                404,
                "Nie znaleziono projektu",
                f"Nie ma checkpointu projektu „{nazwa}”, więc nie da się go wznowić.",
            )
            return

        konfiguracja = self._konfiguracja
        pozycje = odtworz_wejscia(checkpoint, konfiguracja)
        nazwa_projektu = uklad.nazwa_projektu

        def praca(postep: WywolanieZwrotnePostepu) -> WynikPrzetwarzania:
            return przetworz_projekt(
                pozycje, konfiguracja, nazwa_projektu=nazwa_projektu, postep=postep
            )

        try:
            self._serwer.rejestr.uruchom(nazwa_projektu, praca)
        except ZadanieJuzTrwa as blad:
            self._blad(409, "Inne przetwarzanie w toku", str(blad))
            return
        self._przekieruj(sciezka_projektu(nazwa_projektu))

    def _zapisz_pola(self, nazwa: str) -> None:
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return

        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        if not uklad.katalog_projektu.is_dir():
            self._blad(404, "Nie znaleziono projektu", f"Nie ma projektu o nazwie „{nazwa}”.")
            return

        pola = PolaNotatnika(
            instrukcja_systemowa=wynik_formularza.pole("instrukcja_systemowa"),
            prompt_wyszukiwania=wynik_formularza.pole("prompt_wyszukiwania"),
        )
        try:
            pola_notatnika.zapisz(
                uklad.pola_notatnika,
                pola,
                limit_znakow_instrukcji=self._konfiguracja.limit_znakow_instrukcji_systemowej,
            )
        except PrzekroczonoLimitZnakow as blad:
            self._pokaz_projekt(
                uklad.nazwa_projektu,
                kod=400,
                bledy=[BladPola("instrukcja_systemowa", blad.komunikat)],
            )
            return
        self._przekieruj(sciezka_projektu(uklad.nazwa_projektu))

    # --- pomocnicze ---------------------------------------------------

    def _nazwa_z_url(self, fragment: str) -> str:
        return unquote(fragment).strip().strip("/")

    def _zapisz_plik_wejsciowy(self, katalog: Path, plik: formularze.PlikFormularza) -> Path:
        katalog.mkdir(parents=True, exist_ok=True)
        nazwa = formularze.bezpieczna_nazwa_wysylki(plik.nazwa_pliku)
        cel = katalog / nazwa
        licznik = 1
        while cel.exists():
            cel = katalog / f"{cel.stem}_{licznik}{cel.suffix}"
            licznik += 1
        cel.write_bytes(plik.zawartosc)
        return cel

    def _parsuj_formularz(self) -> formularze.WynikFormularza | None:
        typ = self.headers.get("Content-Type", "")
        cialo = self._czytaj_cialo()
        if cialo is None:
            return None
        limit = (
            self._konfiguracja.maksymalny_rozmiar_wysylki_mb * _BAJTOW_W_MEGABAJCIE
            + _NADWYZKA_LIMITU_BAJTOW
        )
        try:
            return formularze.parsuj(
                cialo,
                typ,
                maksymalny_rozmiar_bajtow=limit,
                maksymalna_liczba_plikow=self._konfiguracja.limit_zrodel,
            )
        except formularze.BladFormularza as blad:
            self._blad(400, "Błędny formularz", str(blad))
            return None

    def _czytaj_cialo(self) -> bytes | None:
        surowa_dlugosc = self.headers.get("Content-Length")
        if surowa_dlugosc is None or not surowa_dlugosc.isdigit():
            self._blad(400, "Błędne żądanie", "Żądanie POST nie podało długości treści.")
            return None
        dlugosc = int(surowa_dlugosc)
        twardy_limit = (
            self._konfiguracja.maksymalny_rozmiar_wysylki_mb * _BAJTOW_W_MEGABAJCIE
            + _NADWYZKA_LIMITU_BAJTOW
        )
        if dlugosc > twardy_limit:
            self._blad(413, "Zbyt duże żądanie", "Treść żądania przekracza dozwolony rozmiar.")
            return None
        return self.rfile.read(dlugosc)

    def _token_sesji(self) -> str:
        istniejacy = csrf.token_z_ciasteczka(self.headers.get("Cookie"))
        return istniejacy or csrf.nowy_token()

    def _csrf_ok(self, token_formularza: str) -> bool:
        token_ciasteczka = csrf.token_z_ciasteczka(self.headers.get("Cookie"))
        if csrf.zgodny(token_ciasteczka, token_formularza):
            return True
        self._blad(
            403,
            "Brak uprawnień",
            "Token formularza jest nieprawidłowy. Wróć na stronę, odśwież ją i spróbuj ponownie.",
        )
        return False

    def _blad(self, kod: int, tytul: str, komunikat: str) -> None:
        self._wyslij_html(kod, widoki.strona_bledu(kod=kod, tytul=tytul, komunikat=komunikat))

    def _wyslij_html(self, kod: int, html: str, *, token: str | None = None) -> None:
        dodatkowe = [("Set-Cookie", csrf.naglowek_ustawienia_ciasteczka(token))] if token else None
        self._wyslij(kod, html.encode("utf-8"), _TYP_HTML, dodatkowe)

    def _przekieruj(self, lokalizacja: str) -> None:
        self.send_response(303)
        self.send_header("Location", lokalizacja)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _wyslij(
        self,
        kod: int,
        cialo: bytes,
        typ: str,
        dodatkowe_naglowki: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(kod)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(cialo)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for nazwa, wartosc in dodatkowe_naglowki or []:
            self.send_header(nazwa, wartosc)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cialo)


def _odczytaj_tekst(sciezka: Path) -> str | None:
    try:
        return sciezka.read_text(encoding="utf-8")
    except OSError:
        return None
