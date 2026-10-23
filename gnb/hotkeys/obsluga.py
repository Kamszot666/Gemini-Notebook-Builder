"""Spina rejestrację skrótu, rozpoznanie źródła, kolejkę i przetwarzanie w potoku.

Ten moduł jest jedynym miejscem w pakiecie ``gnb.hotkeys``, które łączy warstwę
Win32 (``_win32.py``), UI Automation (``_automatyzacja.py``), schowek
(``_schowek.py``), Eksplorator (``_eksplorator.py``) i dźwięki (``_dzwieki.py``)
z resztą aplikacji: kolejką
(``kolejka.py``), rozpoznaniem (``rozpoznanie.py``) oraz stanem skrótu i
rejestrem zadań interfejsu z ``gnb.ui``.

Cała zawartość leży za sprawdzeniem ``sys.platform == "win32"`` z tego samego
powodu co w modułach warstwy Win32: żeby ``python -m mypy gnb --platform
linux`` pomijał tę gałąź.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import logging
    from datetime import UTC, datetime
    from pathlib import Path

    import comtypes

    from gnb.core.konfiguracja import Konfiguracja
    from gnb.core.postep import WywolanieZwrotnePostepu
    from gnb.core.skrot import KombinacjaSkrotu, WynikZmianySkrotu, rozbierz_kombinacje
    from gnb.hotkeys import _automatyzacja, _dzwieki, _eksplorator, _schowek, _win32
    from gnb.hotkeys.kolejka import KolejkaSkrotu
    from gnb.hotkeys.model import InformacjeOOknie, RodzajWynikuKopiowania, TypDodania
    from gnb.hotkeys.rozpoznanie import PorazkaRozpoznania, rozpoznaj
    from gnb.ingestion.wejscie import przyjmij_plik, przyjmij_url
    from gnb.logging_pl.dziennik import (
        NAZWA_LOGU_SZCZEGOLOWEGO,
        NAZWA_LOGU_WAZNEGO,
        ZDARZENIE_KOLEJKA_SKROTU_UTRACONA,
        DziennikSzczegolowy,
        DziennikWazny,
    )
    from gnb.persistence.projekt import ustal_uklad
    from gnb.potok import WynikPrzetwarzania, przetworz_projekt
    from gnb.ui.stan_skrotu import (
        AktywnyProjektSkrotu,
        OstatniKomunikatSkrotu,
        SzkicTekstuSkrotu,
    )
    from gnb.ui.zadania import RejestrZadan, ZadanieJuzTrwa

    _LOG = logging.getLogger("gnb.hotkeys")

    # Nazwy procesów i klasa okna rozpoznawane w części A etapu jedenastego.
    # Trzymane tu, nie w ``rozpoznanie.py``, bo dopiero tu decydujemy, którą
    # z dwóch ścieżek odczytu stanu pulpitu w ogóle uruchomić — sam moduł
    # rozpoznania dostaje już gotowe dane i o Win32 nic nie wie.
    _PRZEGLADARKI = frozenset({"chrome", "firefox"})
    _KLASA_OKNA_EKSPLORATORA = "CabinetWClass"

    class ObslugaSkrotu:
        """Cykl życia globalnego skrótu: rejestracja, obsługa naciśnięcia, zatrzymanie."""

        def __init__(
            self,
            konfiguracja: Konfiguracja,
            aktywny_projekt: AktywnyProjektSkrotu,
            rejestr: RejestrZadan,
            ostatni_komunikat: OstatniKomunikatSkrotu,
            szkic_tekstu: SzkicTekstuSkrotu | None = None,
        ) -> None:
            self._konfiguracja = konfiguracja
            self._aktywny_projekt = aktywny_projekt
            self._rejestr = rejestr
            self._ostatni_komunikat = ostatni_komunikat
            self._szkic_tekstu = szkic_tekstu if szkic_tekstu is not None else SzkicTekstuSkrotu()
            self._kolejka = KolejkaSkrotu()
            self._watek = _win32.WatekSkrotu(
                self._obsluz_nacisniecie,
                rozbierz_kombinacje(konfiguracja.globalny_skrot_kombinacja),
            )
            rejestr.dodaj_nasluch_zakonczenia(self._sprobuj_oproznic_kolejke)

        def uruchom(self) -> bool:
            """Rejestruje skrót. Zwraca prawdę przy powodzeniu, zawsze loguje wynik.

            Nieudana rejestracja nigdy nie zatrzymuje aplikacji, zgodnie
            z decyzją czwartą sekcji dwunastej CLAUDE.md.
            """
            udalo_sie = self._watek.uruchom()
            zadana = self._konfiguracja.globalny_skrot_kombinacja
            slowa = rozbierz_kombinacje(zadana).jako_slowa()
            if udalo_sie:
                _LOG.info("Globalny skrót %s zarejestrowany.", slowa)
            elif self._watek.kod_bledu_rejestracji == _win32.ERROR_HOTKEY_ALREADY_REGISTERED:
                _LOG.warning(
                    "Nie udało się zarejestrować globalnego skrótu %s: kombinacja jest już "
                    "zajęta przez inny program. Wybierz inną kombinację na stronie ustawień, "
                    "w zakładce Skrót klawiszowy. Jeżeli korzystasz z NVDA w układzie "
                    "laptopowym albo przypisałeś własny gest do tej kombinacji, sprawdź to "
                    "w oknie NVDA: Preferencje, Gesty wejściowe — programowo nie da się "
                    "zajrzeć do gestów innego procesu.",
                    slowa,
                )
            else:
                _LOG.warning(
                    "Nie udało się zarejestrować globalnego skrótu %s. Kod błędu Windows: %s.",
                    slowa,
                    self._watek.kod_bledu_rejestracji,
                )
            return udalo_sie

        def kombinacja_dzialajaca(self) -> str | None:
            """Napis kombinacji zarejestrowanej teraz albo ``None``, gdy żadna nie jest."""
            aktualna = self._watek.aktualna_kombinacja
            return aktualna.jako_napis() if aktualna is not None else None

        def zmien_kombinacje(self, kombinacja: KombinacjaSkrotu) -> WynikZmianySkrotu:
            """Rejestruje nową kombinację w działającym serwerze; przy odmowie zostaje stara.

            Nowa kombinacja jest rejestrowana, zanim stara zostanie
            wyrejestrowana, więc przy odmowie Windows nic się nie zmienia.
            Komunikat wynikowy jest gotowy do pokazania użytkownikowi.
            """
            wynik = self._watek.zmien_kombinacje(kombinacja)
            dziala = self.kombinacja_dzialajaca()
            if wynik.udalo_sie:
                _LOG.info("Zmieniono globalny skrót na %s.", kombinacja.jako_slowa())
                return WynikZmianySkrotu(
                    True, f"Nowy skrót działa od razu: {kombinacja.jako_slowa()}.", dziala
                )
            if wynik.kod_bledu == _win32.ERROR_HOTKEY_ALREADY_REGISTERED:
                powod = f"Kombinacja {kombinacja.jako_slowa()} jest już zajęta przez inny program."
            elif wynik.kod_bledu is not None:
                powod = (
                    f"Windows odmówił rejestracji kombinacji {kombinacja.jako_slowa()} "
                    f"(kod błędu {wynik.kod_bledu})."
                )
            else:
                powod = f"Nie udało się zarejestrować kombinacji {kombinacja.jako_slowa()}."
            if dziala is not None:
                slowa_dzialajacej = rozbierz_kombinacje(dziala).jako_slowa()
                nadal = f"Nadal działa kombinacja: {slowa_dzialajacej}."
            else:
                nadal = "Obecnie żadna kombinacja nie jest zarejestrowana."
            komunikat = f"Nie zapisano kombinacji. {powod} {nadal}"
            _LOG.warning(komunikat)
            return WynikZmianySkrotu(False, komunikat, dziala)

        def ustaw_konfiguracje(self, konfiguracja: Konfiguracja) -> None:
            """Podmienia konfigurację po zapisie ze strony ustawień (przypisanie jest atomowe)."""
            self._konfiguracja = konfiguracja

        def zatrzymaj(self) -> None:
            self._watek.zatrzymaj()
            self._zglos_utracone_pozycje()

        def _zglos_utracone_pozycje(self) -> None:
            """Ostrzega o źródłach dodanych skrótem, które nie doczekały się przetworzenia.

            ``KolejkaSkrotu`` żyje wyłącznie w pamięci procesu, więc zamknięcie
            serwera z niepustą kolejką traci te pozycje. Milczenie o tym byłoby
            gorsze niż sam fakt utraty: pierwszy priorytet po poprawności danych
            w sekcji czwartej CLAUDE.md to brak nieuzasadnionej utraty treści,
            a utracona treść, o której nikt się nie dowiedział, jest cichą
            korupcją materiału. Trwały zapis kolejki między uruchomieniami
            serwera jest odłożony jako pozycja otwarta w sekcji 18e CLAUDE.md;
            tu tylko ostrzegamy, czytelnie i z nazwą projektu, zamiast dodawać
            nowy plik trwały.
            """
            stan = self._kolejka.stan()
            if not stan:
                return
            opisy = [f"{nazwa} ({liczba})" for nazwa, liczba in stan.items()]
            komunikat = (
                "Serwer zamknięty z nieprzetworzonymi pozycjami dodanymi skrótem: "
                + ", ".join(opisy)
                + ". Dodaj je ponownie po następnym uruchomieniu serwera."
            )
            self._ostatni_komunikat.ustaw(komunikat, sukces=False)
            _LOG.warning(komunikat)
            for nazwa_projektu, liczba in stan.items():
                self._zapisz_ostrzezenie_do_logow_projektu(nazwa_projektu, liczba, komunikat)

        def _zapisz_ostrzezenie_do_logow_projektu(
            self, nazwa_projektu: str, liczba: int, komunikat: str
        ) -> None:
            """Dopisuje ostrzeżenie do log_wazne.txt i log_szczegolowy.txt tego projektu.

            Zapis do logów jednego projektu nie może zablokować zamknięcia
            serwera ani ostrzeżenia dla pozostałych projektów — błąd zapisu jest
            tylko logowany do rejestratora modułu, zgodnie z zasadą piątą
            sekcji trzeciej CLAUDE.md o kontrolowanym pominięciu.
            """
            try:
                uklad = ustal_uklad(self._konfiguracja.katalog_wynikow, nazwa_projektu)
                DziennikWazny(uklad.logi / NAZWA_LOGU_WAZNEGO).zapisz(
                    f"{ZDARZENIE_KOLEJKA_SKROTU_UTRACONA}: {liczba} pozycji"
                )
                with DziennikSzczegolowy(
                    uklad.logi / NAZWA_LOGU_SZCZEGOLOWEGO, uklad.identyfikator_projektu
                ) as logger:
                    logger.warning(komunikat)
            except OSError:
                _LOG.exception(
                    "Nie udało się zapisać do logów projektu „%s” ostrzeżenia "
                    "o utraconej kolejce skrótu.",
                    nazwa_projektu,
                )

        def _obsluz_nacisniecie(self) -> None:
            nazwa_projektu = self._aktywny_projekt.aktualny()
            if nazwa_projektu is None:
                # Decyzja użytkownika z etapu piętnastego, część D: bez projektu
                # zapasowego. Skrót nic nie zapisuje, dopóki użytkownik nie
                # wskaże projektu, bo źródło w przypadkowym projekcie jest błędem
                # poprawności danych.
                self._zglos_porazke(
                    "Brak aktywnego projektu skrótu. Nic nie dodano. Ustaw aktywny projekt "
                    "skrótu na stronie projektu."
                )
                return
            powod_znikniecia = self._aktywny_projekt.sprawdz_istnienie(
                self._konfiguracja.katalog_wynikow
            )
            if powod_znikniecia is not None:
                # Katalog projektu zniknął po wyborze (usunięty ręcznie). Nic nie
                # jest zapisywane ani tworzone od nowa, priorytet poprawności danych.
                self._zglos_porazke(powod_znikniecia)
                return

            okno = _win32.informacje_o_aktywnym_oknie()
            if okno is None:
                self._zglos_porazke("Nie udało się ustalić aktywnego okna. Nic nie dodano.")
                return

            uwagi: list[str] = []
            zaznaczony_tekst: str | None = None
            if okno.nazwa_procesu in _PRZEGLADARKI:
                zaznaczony_tekst = self._odczytaj_zaznaczenie_przegladarki(uwagi)
            adres_paska: str | None
            pliki_zaznaczone: tuple[Path, ...]
            if zaznaczony_tekst is not None and zaznaczony_tekst.strip():
                adres_paska, pliki_zaznaczone = None, ()
            else:
                adres_paska, pliki_zaznaczone = self._odczytaj_stan_okna(okno)

            wynik = rozpoznaj(
                okno,
                adres_paska,
                pliki_zaznaczone,
                zaznaczony_tekst=zaznaczony_tekst,
                adres_nasluchu=self._konfiguracja.adres_nasluchu,
                port_nasluchu=self._konfiguracja.port_nasluchu,
            )
            if isinstance(wynik, PorazkaRozpoznania):
                self._zglos_porazke(" ".join([wynik.powod, *uwagi]))
                return

            moment = datetime.now(UTC)
            if wynik.typ is TypDodania.ADRES:
                assert wynik.adres is not None, "rozpoznanie.py zawsze ustawia adres tu"
                pozycja = przyjmij_url(
                    wynik.adres, moment, self._konfiguracja.dodatkowe_parametry_sledzace
                )
                komunikat = f"Dodano adres strony: {wynik.opis}"
                self._kolejka.dodaj(nazwa_projektu, pozycja)
            elif wynik.typ is TypDodania.ADRESY_Z_ZAZNACZENIA:
                for adres in wynik.adresy:
                    self._kolejka.dodaj(
                        nazwa_projektu,
                        przyjmij_url(
                            adres, moment, self._konfiguracja.dodatkowe_parametry_sledzace
                        ),
                    )
                komunikat = (
                    f"Dodano adres z zaznaczenia: {wynik.opis}"
                    if len(wynik.adresy) == 1
                    else f"Dodano adresy z zaznaczenia: {len(wynik.adresy)}"
                )
                if wynik.liczba_pominietych_adresow_interfejsu:
                    komunikat += (
                        f". Pominięto adresy interfejsu Gemini Notebook Builder: "
                        f"{wynik.liczba_pominietych_adresow_interfejsu}"
                    )
            elif wynik.typ is TypDodania.TEKST:
                if not self._szkic_tekstu.dopisz(nazwa_projektu, wynik.tekst):
                    self._zglos_porazke(
                        "Zaznaczony tekst jest za długi: szkic tekstu tego projektu przekroczyłby "
                        "limit. Nic nie dodano. Wyślij formularz dosyłania, żeby opróżnić szkic."
                    )
                    return
                komunikat = (
                    f"Dopisano {len(wynik.tekst)} znaków zaznaczonego tekstu do pola "
                    f"Tu wklej tekst projektu „{nazwa_projektu}”"
                )
            else:
                for sciezka in wynik.pliki:
                    self._kolejka.dodaj(nazwa_projektu, przyjmij_plik(sciezka, moment))
                komunikat = f"Dodano plik: {wynik.opis}"

            if uwagi:
                komunikat = f"{komunikat}. {' '.join(uwagi)}"
            _dzwieki.zagraj_sukces()
            self._ostatni_komunikat.ustaw(komunikat, sukces=True)
            _LOG.info("%s (projekt „%s”).", komunikat, nazwa_projektu)
            self._sprobuj_oproznic_kolejke()

        def _odczytaj_zaznaczenie_przegladarki(self, uwagi: list[str]) -> str | None:
            """Kopiuje zaznaczenie przeglądarki przez schowek; zwraca tekst albo ``None``.

            ``None`` znaczy, że nic nie zaznaczono albo że zaznaczenia nie dało
            się sprawdzić, i wtedy skrót działa jak dotąd, czyli bierze adres
            strony z paska adresu. Powód niepowodzenia trafia do ``uwagi``.
            """
            biezaca = self._watek.aktualna_kombinacja or rozbierz_kombinacje(
                self._konfiguracja.globalny_skrot_kombinacja
            )
            wynik = _schowek.skopiuj_zaznaczenie(biezaca)
            if wynik.uwaga:
                uwagi.append(wynik.uwaga)
            if wynik.rodzaj is RodzajWynikuKopiowania.ZAZNACZONO:
                return wynik.tekst
            return None

        def _odczytaj_stan_okna(
            self, okno: InformacjeOOknie
        ) -> tuple[str | None, tuple[Path, ...]]:
            """Odczytuje pasek adresu przeglądarki albo zaznaczenie w Eksploratorze.

            Obie ścieżki odczytu używają COM — UI Automation w
            ``_automatyzacja.py`` i Shell.Application w ``_eksplorator.py``. Ten
            kod działa w nowym wątku roboczym, tworzonym przy każdym naciśnięciu
            skrótu (patrz ``_win32.py``), nie w wątku, który zaimportował
            ``gnb.hotkeys`` na starcie serwera. COM wymaga osobnej inicjalizacji
            w każdym wątku, który go używa — wskaźnik interfejsu utworzony
            w jednym wątku nie jest bezpieczny do użycia wprost w innym bez
            marshalingu i grozi błędem RPC_E_WRONG_THREAD. Dlatego CoInitialize
            i CoUninitialize otaczają tu ściśle jedyne miejsce w tej klasie, gdzie
            COM w ogóle jest dotykany; same funkcje odczytu tworzą swoje obiekty
            COM od nowa przy każdym wywołaniu, w tym już zainicjowanym wątku.
            """
            czy_przegladarka = okno.nazwa_procesu in _PRZEGLADARKI
            czy_eksplorator = okno.nazwa_klasy == _KLASA_OKNA_EKSPLORATORA
            if not czy_przegladarka and not czy_eksplorator:
                return None, ()
            comtypes.CoInitialize()
            try:
                if czy_przegladarka:
                    return _automatyzacja.odczytaj_pasek_adresu(okno.uchwyt), ()
                return None, _eksplorator.odczytaj_zaznaczenie(okno.uchwyt)
            finally:
                comtypes.CoUninitialize()

        def _zglos_porazke(self, powod: str) -> None:
            _dzwieki.zagraj_porazke()
            self._ostatni_komunikat.ustaw(powod, sukces=False)
            _LOG.info(powod)

        def _sprobuj_oproznic_kolejke(self, *, ponowienia: int = 1) -> None:
            """Rozpoczyna kolejny przebieg dla oczekującego projektu, jeżeli rejestr jest wolny.

            Wołane od razu po dodaniu do kolejki oraz jako nasłuch zakończenia
            zadania w rejestrze — to razem daje automatyczną kontynuację
            z decyzji pierwszej etapu jedenastego: źródło zapisane od razu,
            przetworzone w tym samym przebiegu, jeśli rejestr jest wolny, albo
            w następnym, gdy nie jest.

            Argument ``ponowienia`` zamyka wąskie okno czasowe: gdy bieżące
            zadanie kończy się dokładnie między pobraniem pozycji z kolejki
            a nieudaną próbą uruchomienia poniżej, jego własny nasłuch
            zakończenia trafia na kolejkę wciąż pustą (pozycje są jeszcze
            w drodze z powrotem) i nic nie robi — bez ponowienia te pozycje
            czekałyby aż do następnego naciśnięcia skrótu. Jedno ponowienie od
            razu po odłożeniu pozycji z powrotem wystarcza: jeżeli rejestr
            zdążył się zwolnić w międzyczasie, ta próba się powiedzie; jeżeli
            wciąż jest zajęty, pozycje zostają w kolejce, a kolejny prawdziwy
            nasłuch zakończenia i tak spróbuje ponownie. Bez limitu ponowień to
            byłaby pętla zajęta czekaniem na zwolnienie rejestru.
            """
            pobrane = self._kolejka.odbierz_jeden_projekt()
            if pobrane is None:
                return
            nazwa_projektu, pozycje = pobrane

            def praca(postep: WywolanieZwrotnePostepu) -> WynikPrzetwarzania:
                return przetworz_projekt(
                    pozycje, self._konfiguracja, nazwa_projektu=nazwa_projektu, postep=postep
                )

            try:
                self._rejestr.uruchom(nazwa_projektu, praca, liczba_pozycji=len(pozycje))
            except ZadanieJuzTrwa:
                # Rejestr zdążył się zająć między odczytem a próbą uruchomienia —
                # wrzucamy z powrotem. Jeżeli zostało ponowienie, próbujemy od
                # razu jeszcze raz; w przeciwnym razie następny nasłuch
                # zakończenia zadania spróbuje znowu.
                for pozycja in pozycje:
                    self._kolejka.dodaj(nazwa_projektu, pozycja)
                if ponowienia > 0:
                    self._sprobuj_oproznic_kolejke(ponowienia=ponowienia - 1)
