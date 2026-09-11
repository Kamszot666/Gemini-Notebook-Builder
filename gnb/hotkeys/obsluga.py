"""Spina rejestrację skrótu, rozpoznanie źródła, kolejkę i przetwarzanie w potoku.

Ten moduł jest jedynym miejscem w pakiecie ``gnb.hotkeys``, które łączy warstwę
Win32 (``_win32.py``), UI Automation (``_automatyzacja.py``), Eksplorator
(``_eksplorator.py``) i dźwięki (``_dzwieki.py``) z resztą aplikacji: kolejką
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

    from gnb.core.konfiguracja import Konfiguracja
    from gnb.core.postep import WywolanieZwrotnePostepu
    from gnb.hotkeys import _automatyzacja, _dzwieki, _eksplorator, _win32
    from gnb.hotkeys.kolejka import KolejkaSkrotu
    from gnb.hotkeys.model import TypDodania
    from gnb.hotkeys.rozpoznanie import PorazkaRozpoznania, rozpoznaj
    from gnb.ingestion.wejscie import przyjmij_plik, przyjmij_url
    from gnb.potok import WynikPrzetwarzania, przetworz_projekt
    from gnb.ui.stan_skrotu import AktywnyProjektSkrotu, OstatniKomunikatSkrotu
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
        ) -> None:
            self._konfiguracja = konfiguracja
            self._aktywny_projekt = aktywny_projekt
            self._rejestr = rejestr
            self._ostatni_komunikat = ostatni_komunikat
            self._kolejka = KolejkaSkrotu()
            self._watek = _win32.WatekSkrotu(self._obsluz_nacisniecie)
            rejestr.dodaj_nasluch_zakonczenia(self._sprobuj_oproznic_kolejke)

        def uruchom(self) -> bool:
            """Rejestruje skrót. Zwraca prawdę przy powodzeniu, zawsze loguje wynik.

            Nieudana rejestracja nigdy nie zatrzymuje aplikacji, zgodnie
            z decyzją czwartą sekcji dwunastej CLAUDE.md.
            """
            udalo_sie = self._watek.uruchom()
            if udalo_sie:
                _LOG.info("Globalny skrót Control plus Shift plus F12 zarejestrowany.")
            elif self._watek.kod_bledu_rejestracji == _win32.ERROR_HOTKEY_ALREADY_REGISTERED:
                _LOG.warning(
                    "Nie udało się zarejestrować globalnego skrótu Control plus Shift "
                    "plus F12: kombinacja jest już zajęta przez inny program. Jeżeli "
                    "korzystasz z NVDA w układzie laptopowym albo przypisałeś własny "
                    "gest do tej kombinacji, sprawdź to w oknie NVDA: Preferencje, "
                    "Gesty wejściowe — programowo nie da się zajrzeć do gestów innego "
                    "procesu."
                )
            else:
                _LOG.warning(
                    "Nie udało się zarejestrować globalnego skrótu Control plus Shift "
                    "plus F12. Kod błędu Windows: %s.",
                    self._watek.kod_bledu_rejestracji,
                )
            return udalo_sie

        def zatrzymaj(self) -> None:
            self._watek.zatrzymaj()

        def _obsluz_nacisniecie(self) -> None:
            nazwa_projektu = self._aktywny_projekt.aktualny()
            if nazwa_projektu is None:
                self._zglos_porazke(
                    "Brak aktywnego projektu skrótu. Wybierz projekt na jego stronie."
                )
                return

            okno = _win32.informacje_o_aktywnym_oknie()
            if okno is None:
                self._zglos_porazke("Nie udało się ustalić aktywnego okna. Nic nie dodano.")
                return

            adres_paska: str | None = None
            pliki_zaznaczone: tuple[Path, ...] = ()
            if okno.nazwa_procesu in _PRZEGLADARKI:
                adres_paska = _automatyzacja.odczytaj_pasek_adresu(okno.uchwyt)
            elif okno.nazwa_klasy == _KLASA_OKNA_EKSPLORATORA:
                pliki_zaznaczone = _eksplorator.odczytaj_zaznaczenie(okno.uchwyt)

            wynik = rozpoznaj(okno, adres_paska, pliki_zaznaczone)
            if isinstance(wynik, PorazkaRozpoznania):
                self._zglos_porazke(wynik.powod)
                return

            moment = datetime.now(UTC)
            if wynik.typ is TypDodania.ADRES:
                assert wynik.adres is not None, "rozpoznanie.py zawsze ustawia adres dla TypDodania.ADRES"
                pozycja = przyjmij_url(
                    wynik.adres, moment, self._konfiguracja.dodatkowe_parametry_sledzace
                )
                komunikat = f"Dodano adres strony: {wynik.opis}"
                self._kolejka.dodaj(nazwa_projektu, pozycja)
            else:
                for sciezka in wynik.pliki:
                    self._kolejka.dodaj(nazwa_projektu, przyjmij_plik(sciezka, moment))
                komunikat = f"Dodano plik: {wynik.opis}"

            _dzwieki.zagraj_sukces()
            self._ostatni_komunikat.ustaw(komunikat, sukces=True)
            _LOG.info("%s (projekt „%s”).", komunikat, nazwa_projektu)
            self._sprobuj_oproznic_kolejke()

        def _zglos_porazke(self, powod: str) -> None:
            _dzwieki.zagraj_porazke()
            self._ostatni_komunikat.ustaw(powod, sukces=False)
            _LOG.info(powod)

        def _sprobuj_oproznic_kolejke(self) -> None:
            """Rozpoczyna kolejny przebieg dla oczekującego projektu, jeżeli rejestr jest wolny.

            Wołane od razu po dodaniu do kolejki oraz jako nasłuch zakończenia
            zadania w rejestrze — to razem daje automatyczną kontynuację
            z decyzji pierwszej etapu jedenastego: źródło zapisane od razu,
            przetworzone w tym samym przebiegu, jeśli rejestr jest wolny, albo
            w następnym, gdy nie jest.
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
                self._rejestr.uruchom(nazwa_projektu, praca)
            except ZadanieJuzTrwa:
                # Rejestr zdążył się zająć między odczytem a próbą uruchomienia —
                # wrzucamy z powrotem, następny nasłuch zakończenia spróbuje znowu.
                for pozycja in pozycje:
                    self._kolejka.dodaj(nazwa_projektu, pozycja)
