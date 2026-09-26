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
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import unquote, urlsplit

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.nazwy import sanityzuj_nazwe_projektu
from gnb.core.postep import WywolanieZwrotnePostepu
from gnb.core.wyjatki import BladGnb
from gnb.ingestion.lista_url import rozpoznaj_liste_adresow_w_pliku
from gnb.ingestion.wejscie import (
    PozycjaWejsciowa,
    przyjmij_plik,
    przyjmij_tekst,
    przyjmij_url,
)
from gnb.operacje_projektu import (
    STATUSY_Z_ZASTAPIENIEM_TRESCI,
    oznacz_jako_zweryfikowane,
    sprawdz_mozliwosc_zastapienia,
    usun_zrodlo_z_projektu,
    wczytaj_checkpoint_projektu,
    zapisz_plik_zastepczy,
)
from gnb.persistence import pola_notatnika
from gnb.persistence.checkpoint import Checkpoint, wczytaj
from gnb.persistence.pliki_wynikowe import znajdz_brakujace_pliki
from gnb.persistence.pola_notatnika import PolaNotatnika, PrzekroczonoLimitZnakow
from gnb.persistence.projekt import UkladProjektu, ustal_uklad, utworz_katalogi
from gnb.potok import (
    WynikPrzetwarzania,
    identyfikatory_materialow_do_sprawdzenia,
    odtworz_wejscia,
    przetworz_projekt,
)
from gnb.ui import csrf, formularze, widoki
from gnb.ui.projekty import niedokonczone
from gnb.ui.stan_skrotu import AktywnyProjektSkrotu, OstatniKomunikatSkrotu
from gnb.ui.widoki import BladPola, DaneFormularzaProjektu, PodsumowanieWyniku, sciezka_projektu
from gnb.ui.widoki_zrodel import (
    BrakujacyPlikDoWidoku,
    ZrodloDoWidoku,
    sekcje_zrodel,
)
from gnb.ui.zadania import RejestrZadan, StanZadania, ZadanieJuzTrwa

_LOG = logging.getLogger("gnb.ui")
_TYP_HTML = "text/html; charset=utf-8"
_TYP_JSON = "application/json; charset=utf-8"
_KATALOG_PLIKOW_ZASTEPCZYCH = "zastepcze"
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
        aktywny_projekt_skrotu: AktywnyProjektSkrotu,
        ostatni_komunikat_skrotu: OstatniKomunikatSkrotu,
    ) -> None:
        if ":" in adres[0]:
            self.address_family = socket.AF_INET6
        super().__init__(adres, _Handler)
        self.konfiguracja = konfiguracja
        self.rejestr = rejestr
        self.aktywny_projekt_skrotu = aktywny_projekt_skrotu
        self.ostatni_komunikat_skrotu = ostatni_komunikat_skrotu


def zbuduj_serwer(
    konfiguracja: Konfiguracja,
    rejestr: RejestrZadan | None = None,
    *,
    aktywny_projekt_skrotu: AktywnyProjektSkrotu | None = None,
    ostatni_komunikat_skrotu: OstatniKomunikatSkrotu | None = None,
) -> ThreadingHTTPServer:
    """Buduje serwer bez uruchamiania go. Wydzielone z ``uruchom_serwer`` na potrzeby testów."""
    return _Serwer(
        (konfiguracja.adres_nasluchu, konfiguracja.port_nasluchu),
        konfiguracja,
        rejestr or RejestrZadan(),
        aktywny_projekt_skrotu or AktywnyProjektSkrotu(),
        ostatni_komunikat_skrotu or OstatniKomunikatSkrotu(),
    )


def uruchom_serwer(konfiguracja: Konfiguracja, *, rejestr: RejestrZadan | None = None) -> None:
    """Uruchamia serwer i blokuje do przerwania klawiszem.

    Adres i port pochodzą z konfiguracji. Adres jest tam już zweryfikowany jako
    pętla zwrotna, więc serwer nie może przypadkiem wystawić się do sieci.

    Globalny skrót klawiszowy z etapu jedenastego rejestruje się tutaj, razem
    ze startem serwera, i wyrejestrowuje się przy jego zamknięciu — zgodnie
    z decyzją pierwszą sekcji dwunastej CLAUDE.md nie ma dla niego żadnej innej
    ścieżki uruchomienia. Dzieje się to wyłącznie na Windows i wyłącznie, gdy
    ustawienie ``globalny_skrot_wlaczony`` jest włączone; nieudana rejestracja
    jest tylko logowana i nie przerywa startu serwera.
    """
    serwer = cast("_Serwer", zbuduj_serwer(konfiguracja, rejestr))
    adres = f"http://{konfiguracja.adres_nasluchu}:{serwer.server_address[1]}/"
    print(f"Interfejs Gemini Notebook Builder działa pod adresem {adres}", flush=True)
    print(
        "Otwórz ten adres w przeglądarce. Serwer zatrzymasz klawiszami Control plus C.",
        flush=True,
    )
    obsluga_skrotu = _uruchom_globalny_skrot(serwer)
    try:
        serwer.serve_forever()
    except KeyboardInterrupt:
        print("")
        print("Zatrzymywanie serwera.")
    finally:
        if obsluga_skrotu is not None:
            obsluga_skrotu.zatrzymaj()
        serwer.shutdown()
        serwer.server_close()


class _ObslugaSkrotuLike(Protocol):
    """Tylko to, czego ten moduł potrzebuje od ``gnb.hotkeys.ObslugaSkrotu``.

    Protokół strukturalny, a nie import konkretnej klasy, żeby ten plik dało
    się sprawdzić także poleceniem ``python -m mypy gnb --platform linux`` —
    ``gnb.hotkeys`` na Linuksie nic nie eksportuje, patrz sekcja szósta
    CLAUDE.md.
    """

    def zatrzymaj(self) -> None: ...


def _uruchom_globalny_skrot(serwer: _Serwer) -> _ObslugaSkrotuLike | None:
    """Uruchamia obsługę globalnego skrótu, gdy system i konfiguracja na to pozwalają.

    Import ``gnb.hotkeys`` jest tu celowo lokalny i warunkowy: reszta pakietu
    nie zakłada obecności tego modułu, zgodnie z sekcją szóstą CLAUDE.md, więc
    serwer interfejsu musi działać bez niego na systemie innym niż Windows.
    """
    if sys.platform == "win32" and serwer.konfiguracja.globalny_skrot_wlaczony:
        from gnb.hotkeys import ObslugaSkrotu

        obsluga = ObslugaSkrotu(
            serwer.konfiguracja,
            serwer.aktywny_projekt_skrotu,
            serwer.rejestr,
            serwer.ostatni_komunikat_skrotu,
        )
        obsluga.uruchom()
        return obsluga
    return None


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
        elif (adres_zrodla := self._rozbij_adres_zrodla(sciezka)) is not None:
            self._obsluz_dzialanie_na_zrodle(*adres_zrodla)
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/wznow"):
            self._wznow_projekt(self._nazwa_z_url(sciezka[len("/projekt/") : -len("/wznow")]))
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/pola"):
            self._zapisz_pola(self._nazwa_z_url(sciezka[len("/projekt/") : -len("/pola")]))
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/aktywny-skrot"):
            self._ustaw_aktywny_projekt_skrotu(
                self._nazwa_z_url(sciezka[len("/projekt/") : -len("/aktywny-skrot")])
            )
        elif sciezka.startswith("/projekt/") and sciezka.endswith("/dosylanie"):
            self._dosylanie_zrodel(
                self._nazwa_z_url(sciezka[len("/projekt/") : -len("/dosylanie")])
            )
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
            aktywny_projekt_skrotu=self._serwer.aktywny_projekt_skrotu.aktualny(),
            ostatni_komunikat_skrotu=self._serwer.ostatni_komunikat_skrotu.aktualny(),
        )
        self._wyslij_html(kod, html, token=token)

    def _pokaz_projekt(
        self,
        nazwa: str,
        *,
        kod: int = 200,
        bledy: list[BladPola] | None = None,
        dane_dosylania: DaneFormularzaProjektu | None = None,
        bledy_dosylania: list[BladPola] | None = None,
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
            aktywny_projekt_skrotu=self._serwer.aktywny_projekt_skrotu.aktualny(),
            ostatni_komunikat_skrotu=self._serwer.ostatni_komunikat_skrotu.aktualny(),
            grupy_projektu=self._grupy_projektu(uklad),
            dane_dosylania=dane_dosylania,
            bledy_dosylania=bledy_dosylania,
            zrodla_html=self._zrodla_html(uklad, token),
        )
        self._wyslij_html(kod, html, token=token)

    def _grupy_projektu(self, uklad: UkladProjektu) -> list[str]:
        """Nazwy grup tematycznych znanych projektowi, w kolejności pierwszego użycia.

        Trafiają na listę podpowiedzi pola grupy w formularzu dosyłania, a ostatnia
        z nich jest wartością domyślną tego pola, żeby kolejne źródła trafiały do
        tego samego pliku grupy bez przepisywania nazwy.
        """
        if not uklad.checkpoint.is_file():
            return []
        checkpoint = wczytaj(uklad.checkpoint)
        if checkpoint is None:
            return []
        grupy: list[str] = []
        for wejscie in checkpoint.wejscia:
            if wejscie.grupa and wejscie.grupa not in grupy:
                grupy.append(wejscie.grupa)
        return grupy

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
        """Zwraca stan bieżącego zadania jako JSON, odpytywane przez skrypt strony projektu.

        Odpowiedź niesie tylko krótkie zdania stanu. Strona niczego przy tym nie
        przebudowuje, żeby nie przenosić fokusu czytnika ekranu; po zakończeniu
        dodaje jedynie odnośnik do ponownego wczytania strony z wynikami.
        """
        informacja = self._serwer.rejestr.informacja()
        if informacja is None:
            dane: dict[str, str] = {"komunikat": "", "stan": "brak"}
            self._wyslij(200, json.dumps(dane, ensure_ascii=False).encode("utf-8"), _TYP_JSON)
            return

        dane = {"komunikat": informacja.komunikat_postepu, "stan": informacja.stan.value}
        if informacja.stan is StanZadania.ZAKONCZONE and informacja.wynik is not None:
            uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, informacja.nazwa_projektu)
            if _odczytaj_tekst(uklad.raport) is not None:
                dane["naglowek"] = "Stan przetwarzania: zakończone"
                dane["komunikat"] = (
                    "Przetwarzanie zakończone. Aktywuj odnośnik „Pokaż wyniki przetwarzania”."
                )
        elif informacja.stan is StanZadania.BLAD:
            dane["naglowek"] = "Stan przetwarzania: zakończone błędem"
            powod = informacja.komunikat_bledu or "Powód nie został zapisany."
            dane["komunikat"] = f"Przetwarzanie zakończone błędem. Powód: {powod}"

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
        if not dane.grupa:
            bledy.append(BladPola("grupa", "Nazwa grupy tematycznej jest wymagana."))

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

        try:
            self._uruchom_nowy_projekt(nazwa_bezpieczna, dane, adresy, pliki, dane.grupa)
        except ZadanieJuzTrwa as blad:
            self._pokaz_strone_glowna(
                kod=409, dane=dane, bledy=[BladPola("nazwa_projektu", str(blad))]
            )
            return
        except BladGnb as blad:
            self._pokaz_strone_glowna(
                kod=400, dane=dane, bledy=[BladPola("adresy", blad.komunikat)]
            )
            return
        self._przekieruj(sciezka_projektu(nazwa_bezpieczna))

    def _uruchom_nowy_projekt(
        self,
        nazwa: str,
        dane: DaneFormularzaProjektu,
        adresy: list[str],
        pliki: list[formularze.PlikFormularza],
        grupa: str,
    ) -> None:
        """Przyjmuje wejścia i uruchamia przebieg; błędny adres kończy się przed katalogiem."""
        konfiguracja = self._konfiguracja
        moment = datetime.now(UTC)
        pozycje: list[PozycjaWejsciowa] = []
        if dane.tekst.strip():
            pozycje.append(przyjmij_tekst(dane.tekst, moment, grupa=grupa))
        for adres in adresy:
            pozycje.append(
                przyjmij_url(adres, moment, konfiguracja.dodatkowe_parametry_sledzace, grupa=grupa)
            )
        uklad = ustal_uklad(konfiguracja.katalog_wynikow, nazwa)
        utworz_katalogi(uklad, z_materialami_zrodlowymi=konfiguracja.zachowuj_oryginaly)
        for plik in pliki:
            sciezka = self._zapisz_plik_wejsciowy(uklad.pliki_wejsciowe, plik)
            lista = rozpoznaj_liste_adresow_w_pliku(
                sciezka, konfiguracja.dodatkowe_parametry_sledzace
            )
            if lista is None:
                pozycje.append(przyjmij_plik(sciezka, moment, grupa=grupa))
                continue
            # Plik złożony wyłącznie z adresów jest listą źródeł: pobieramy strony,
            # a sama lista nie trafia do notatnika jako treść.
            for wpis in lista.adresy:
                pozycje.append(
                    przyjmij_url(
                        wpis.podany,
                        moment,
                        konfiguracja.dodatkowe_parametry_sledzace,
                        grupa=grupa,
                    )
                )

        def praca(postep: WywolanieZwrotnePostepu) -> WynikPrzetwarzania:
            return przetworz_projekt(pozycje, konfiguracja, nazwa_projektu=nazwa, postep=postep)

        self._serwer.rejestr.uruchom(nazwa, praca, liczba_pozycji=len(pozycje))

    def _dosylanie_zrodel(self, nazwa: str) -> None:
        """Dodaje kolejne źródła do już istniejącego projektu, z formularza pod raportem.

        Idzie tą samą ścieżką przetwarzania co formularz nowego projektu
        z nazwą już istniejącego projektu — `_uruchom_nowy_projekt` wznawia
        checkpoint zamiast zaczynać od zera, dokładnie tak samo jak przy
        wysłaniu formularza strony głównej z istniejącą nazwą. Różni się tylko
        tym, gdzie wracają błędy walidacji: tu na stronę projektu, z której
        przyszło żądanie, nie na stronę główną — pozycja czwarta listy zmian
        etapu czternastego.
        """
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return

        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        if not uklad.katalog_projektu.is_dir():
            self._blad(404, "Nie znaleziono projektu", f"Nie ma projektu o nazwie „{nazwa}”.")
            return

        dane = DaneFormularzaProjektu(
            tekst=wynik_formularza.pole("tekst"),
            adresy=wynik_formularza.pole("adresy"),
            grupa=wynik_formularza.pole("grupa").strip(),
        )
        adresy = [wiersz.strip() for wiersz in dane.adresy.splitlines() if wiersz.strip()]
        pliki = [plik for plik in wynik_formularza.pliki if plik.zawartosc]
        bledy: list[BladPola] = []
        if not dane.tekst.strip() and not adresy and not pliki:
            bledy.append(
                BladPola(
                    "dosylanie-tekst", "Podaj przynajmniej jedno źródło: tekst, adres albo plik."
                )
            )
        if not dane.grupa:
            bledy.append(BladPola("dosylanie-grupa", "Nazwa grupy tematycznej jest wymagana."))
        if bledy:
            self._pokaz_projekt(
                uklad.nazwa_projektu, kod=400, dane_dosylania=dane, bledy_dosylania=bledy
            )
            return

        try:
            self._uruchom_nowy_projekt(uklad.nazwa_projektu, dane, adresy, pliki, dane.grupa)
        except ZadanieJuzTrwa as blad:
            self._pokaz_projekt(
                uklad.nazwa_projektu,
                kod=409,
                dane_dosylania=dane,
                bledy_dosylania=[BladPola("dosylanie-tekst", str(blad))],
            )
            return
        except BladGnb as blad:
            self._pokaz_projekt(
                uklad.nazwa_projektu,
                kod=400,
                dane_dosylania=dane,
                bledy_dosylania=[BladPola("dosylanie-adresy", blad.komunikat)],
            )
            return
        self._przekieruj(sciezka_projektu(uklad.nazwa_projektu))

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
                pozycje,
                konfiguracja,
                nazwa_projektu=nazwa_projektu,
                postep=postep,
                ponownie_przetwarzaj_usuniete=False,
            )

        try:
            self._serwer.rejestr.uruchom(nazwa_projektu, praca, liczba_pozycji=len(pozycje))
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

    def _ustaw_aktywny_projekt_skrotu(self, nazwa: str) -> None:
        """Ustawia jawnie wybrany projekt jako cel globalnego skrótu klawiszowego.

        Wybór jest jawny, nie „ostatnio otwarty”, zgodnie z decyzją drugą sekcji
        dwunastej CLAUDE.md — patrz docstring ``AktywnyProjektSkrotu``.
        """
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return

        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        if not uklad.katalog_projektu.is_dir():
            self._blad(404, "Nie znaleziono projektu", f"Nie ma projektu o nazwie „{nazwa}”.")
            return

        self._serwer.aktywny_projekt_skrotu.ustaw(uklad.nazwa_projektu)
        self._przekieruj(sciezka_projektu(uklad.nazwa_projektu))

    # --- ręczne działania na źródłach ---------------------------------

    def _rozbij_adres_zrodla(self, sciezka: str) -> tuple[str, str, str] | None:
        """Rozpoznaje adres ``/projekt/NAZWA/zrodlo/IDENTYFIKATOR/DZIALANIE``.

        Zwraca nazwę projektu, identyfikator źródła i nazwę działania albo nic,
        gdy ścieżka ma inny kształt.
        """
        czesci = sciezka.split("/")
        if len(czesci) == 6 and czesci[1] == "projekt" and czesci[3] == "zrodlo":
            return self._nazwa_z_url(czesci[2]), unquote(czesci[4]), czesci[5]
        return None

    def _obsluz_dzialanie_na_zrodle(self, nazwa: str, identyfikator: str, akcja: str) -> None:
        if akcja == "zweryfikowane":
            self._oznacz_zrodlo_jako_zweryfikowane(nazwa, identyfikator)
        elif akcja == "usun":
            self._usun_zrodlo(nazwa, identyfikator)
        elif akcja == "zastap":
            self._zastap_tresc_zrodla(nazwa, identyfikator)
        else:
            self._blad(404, "Nie znaleziono", "Pod tym adresem nie ma żadnej operacji.")

    def _uklad_istniejacego_projektu(self, nazwa: str) -> UkladProjektu | None:
        uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa)
        if not uklad.katalog_projektu.is_dir():
            self._blad(404, "Nie znaleziono projektu", f"Nie ma projektu o nazwie „{nazwa}”.")
            return None
        return uklad

    def _zrodlo_do_widoku_lub_blad(
        self, uklad: UkladProjektu, identyfikator: str
    ) -> ZrodloDoWidoku | None:
        checkpoint = self._wczytaj_checkpoint_do_widoku(uklad)
        zrodla = self._zrodla_do_widoku(checkpoint) if checkpoint is not None else []
        for zrodlo in zrodla:
            if zrodlo.identyfikator == identyfikator:
                return zrodlo
        self._blad(404, "Nie znaleziono źródła", "Nie ma w projekcie źródła o tym identyfikatorze.")
        return None

    def _oznacz_zrodlo_jako_zweryfikowane(self, nazwa: str, identyfikator: str) -> None:
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return
        uklad = self._uklad_istniejacego_projektu(nazwa)
        if uklad is None:
            return
        try:
            with self._serwer.rejestr.wylacznie():
                oznacz_jako_zweryfikowane(uklad, self._konfiguracja, identyfikator)
        except ZadanieJuzTrwa as blad:
            self._blad(409, "Inne przetwarzanie w toku", str(blad))
            return
        except BladGnb as blad:
            self._blad(400, "Nie można oznaczyć źródła", blad.komunikat)
            return
        self._przekieruj(sciezka_projektu(uklad.nazwa_projektu))

    def _usun_zrodlo(self, nazwa: str, identyfikator: str) -> None:
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return
        uklad = self._uklad_istniejacego_projektu(nazwa)
        if uklad is None:
            return
        try:
            with self._serwer.rejestr.wylacznie():
                wynik = usun_zrodlo_z_projektu(uklad, self._konfiguracja, identyfikator)
        except ZadanieJuzTrwa as blad:
            self._blad(409, "Inne przetwarzanie w toku", str(blad))
            return
        except BladGnb as blad:
            self._blad(400, "Nie można usunąć źródła", blad.komunikat)
            return
        if wynik.wymaga_przepakowania and not self._uruchom_zapisane_wejscia(uklad, {}):
            return
        self._przekieruj(sciezka_projektu(uklad.nazwa_projektu))

    def _zastap_tresc_zrodla(self, nazwa: str, identyfikator: str) -> None:
        wynik_formularza = self._parsuj_formularz()
        if wynik_formularza is None:
            return
        if not self._csrf_ok(wynik_formularza.pole(csrf.NAZWA_POLA_FORMULARZA)):
            return
        uklad = self._uklad_istniejacego_projektu(nazwa)
        if uklad is None:
            return
        pliki = [plik for plik in wynik_formularza.pliki if plik.zawartosc]
        if not pliki:
            self._blad(
                400,
                "Nie wybrano pliku",
                "Wybierz plik z ręcznie zapisaną treścią źródła i spróbuj ponownie.",
            )
            return
        try:
            sprawdz_mozliwosc_zastapienia(wczytaj_checkpoint_projektu(uklad), identyfikator)
        except BladGnb as blad:
            self._blad(400, "Nie można zastąpić treści", blad.komunikat)
            return
        sciezka = zapisz_plik_zastepczy(
            uklad.pliki_wejsciowe / _KATALOG_PLIKOW_ZASTEPCZYCH,
            formularze.bezpieczna_nazwa_wysylki(pliki[0].nazwa_pliku),
            pliki[0].zawartosc,
        )
        if not self._uruchom_zapisane_wejscia(uklad, {identyfikator: sciezka}):
            return
        self._przekieruj(sciezka_projektu(uklad.nazwa_projektu))

    def _uruchom_zapisane_wejscia(
        self, uklad: UkladProjektu, zastepcze_tresci: dict[str, Path]
    ) -> bool:
        """Uruchamia przebieg z zapisanych wejść projektu; zwraca fałsz po wysłaniu strony błędu.

        Służy przepakowaniu po usunięciu źródła z grupy oraz zastąpieniu treści
        źródła plikiem. Zapisane wejścia nie są ponownym podaniem źródeł przez
        użytkownika, więc źródła pominięte z powodu ręcznie usuniętego pliku
        wynikowego zostają pominięte.
        """
        konfiguracja = self._konfiguracja
        pozycje = odtworz_wejscia(wczytaj_checkpoint_projektu(uklad), konfiguracja)
        nazwa_projektu = uklad.nazwa_projektu

        def praca(postep: WywolanieZwrotnePostepu) -> WynikPrzetwarzania:
            return przetworz_projekt(
                pozycje,
                konfiguracja,
                nazwa_projektu=nazwa_projektu,
                postep=postep,
                zastepcze_tresci=zastepcze_tresci,
                ponownie_przetwarzaj_usuniete=False,
            )

        try:
            self._serwer.rejestr.uruchom(nazwa_projektu, praca, liczba_pozycji=len(pozycje))
        except ZadanieJuzTrwa as blad:
            self._blad(
                409,
                "Inne przetwarzanie w toku",
                f"{blad} Zmiana została zapisana, a przetwarzanie dokończysz przyciskiem "
                "wznowienia projektu na stronie głównej, gdy poprzednie się skończy.",
            )
            return False
        return True

    def _wczytaj_checkpoint_do_widoku(self, uklad: UkladProjektu) -> Checkpoint | None:
        """Wczytuje checkpoint do wyświetlenia. Uszkodzony albo brakujący daje ``None``."""
        if not uklad.checkpoint.is_file():
            return None
        try:
            return wczytaj(uklad.checkpoint)
        except BladGnb:
            return None

    def _zrodla_do_widoku(self, checkpoint: Checkpoint) -> list[ZrodloDoWidoku]:
        materialy = identyfikatory_materialow_do_sprawdzenia(checkpoint)
        zrodla: list[ZrodloDoWidoku] = []
        for stan in checkpoint.zrodla.values():
            nazwy_plikow = tuple(
                dict.fromkeys(Path(wynik.sciezka_wzgledna).name for wynik in stan.wyniki)
            )
            zrodla.append(
                ZrodloDoWidoku(
                    identyfikator=stan.identyfikator,
                    pochodzenie=stan.pochodzenie,
                    status=stan.status,
                    grupa=stan.grupa_pakowania,
                    pliki_wynikowe=nazwy_plikow,
                    komunikat=stan.komunikat_bledu,
                    powody_do_sprawdzenia=(
                        *stan.powody_oceny,
                        *stan.ostrzezenia,
                        *stan.ostrzezenia_pakowania,
                    ),
                    czy_material_do_sprawdzenia=stan.identyfikator in materialy,
                    zweryfikowane_recznie=stan.zweryfikowane_recznie,
                    tresc_zastapiona_plikiem=stan.tresc_zastapiona_plikiem,
                    czy_mozna_zastapic_tresc=stan.status in STATUSY_Z_ZASTAPIENIEM_TRESCI,
                )
            )
        return zrodla

    def _zrodla_html(self, uklad: UkladProjektu, token_csrf: str) -> str:
        """Buduje fragment strony projektu z wykazem źródeł i brakującymi plikami.

        Sprawdzenie brakujących plików jest tu wyłącznie odczytem: wyświetlenie
        strony nigdy nie zmienia stanu projektu, status źródeł zmienia dopiero
        początek następnego przebiegu przetwarzania.
        """
        checkpoint = self._wczytaj_checkpoint_do_widoku(uklad)
        if checkpoint is None:
            return ""
        brakujace = [
            BrakujacyPlikDoWidoku(
                nazwa=brak.nazwa,
                pochodzenie_zrodel=tuple(
                    checkpoint.zrodla[identyfikator].pochodzenie
                    for identyfikator in brak.identyfikatory_zrodel
                    if identyfikator in checkpoint.zrodla
                ),
                czy_zajmuje_slot=brak.czy_zajmuje_slot,
            )
            for brak in znajdz_brakujace_pliki(uklad, checkpoint)
        ]
        return sekcje_zrodel(
            uklad.nazwa_projektu, self._zrodla_do_widoku(checkpoint), brakujace, token_csrf
        )

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
