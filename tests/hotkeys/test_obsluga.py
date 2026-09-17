"""Testy `ObslugaSkrotu` — spięcia rejestracji, rozpoznania, kolejki, dźwięków i komunikatów.

Testy podstawiają warstwę Win32, UI Automation, Eksplorator i dźwięki fałszywymi
funkcjami: sprawdzają logikę spinającą (`obsluga.py`), nie prawdziwe wywołania
systemowe, które mają własne testy w `test_win32.py` i wymagają uruchomienia na
Windows z konkretnym stanem pulpitu. `_obsluz_nacisniecie` jest wołane wprost,
z pominięciem prawdziwego naciśnięcia klawiszy i prawdziwej pętli komunikatów —
to jest właśnie ta funkcja, którą `WatekSkrotu` wywołuje po naciśnięciu skrótu.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Obsługa globalnego skrótu działa wyłącznie na Windows."
)

if sys.platform == "win32":
    from gnb.core.konfiguracja import Konfiguracja
    from gnb.hotkeys import obsluga
    from gnb.hotkeys.model import InformacjeOOknie
    from gnb.hotkeys.obsluga import ObslugaSkrotu
    from gnb.ui.stan_skrotu import AktywnyProjektSkrotu, OstatniKomunikatSkrotu
    from gnb.ui.zadania import ZadanieJuzTrwa


class _FalszywyRejestr:
    """Podstawa `RejestrZadan`: zapamiętuje żądania uruchomienia, nic nie wykonuje."""

    def __init__(self, *, rzuc_juz_trwa_razy: int = 0) -> None:
        self.uruchomienia: list[str] = []
        self._rzuc_juz_trwa_razy = rzuc_juz_trwa_razy
        self._nasluchy: list[object] = []

    def dodaj_nasluch_zakonczenia(self, wywolanie: object) -> None:
        self._nasluchy.append(wywolanie)

    def uruchom(self, nazwa_projektu: str, _praca: object) -> None:
        if self._rzuc_juz_trwa_razy > 0:
            self._rzuc_juz_trwa_razy -= 1
            raise ZadanieJuzTrwa("Zajęty.")
        self.uruchomienia.append(nazwa_projektu)


def _okno(**nadpisania: object) -> InformacjeOOknie:
    domyslne = {"uchwyt": 1, "tytul": "Okno", "nazwa_klasy": "", "nazwa_procesu": ""}
    domyslne.update(nadpisania)
    return InformacjeOOknie(**domyslne)  # type: ignore[arg-type]


def _obsluga(
    monkeypatch: pytest.MonkeyPatch,
    *,
    okno: InformacjeOOknie | None,
    adres_paska: str | None = None,
    pliki_zaznaczone: tuple[Path, ...] = (),
    rejestr: _FalszywyRejestr | None = None,
) -> tuple[
    ObslugaSkrotu, list[str], OstatniKomunikatSkrotu, _FalszywyRejestr, AktywnyProjektSkrotu
]:
    monkeypatch.setattr(obsluga._win32, "informacje_o_aktywnym_oknie", lambda: okno)
    monkeypatch.setattr(
        obsluga._automatyzacja, "odczytaj_pasek_adresu", lambda _uchwyt: adres_paska
    )
    monkeypatch.setattr(
        obsluga._eksplorator, "odczytaj_zaznaczenie", lambda _uchwyt: pliki_zaznaczone
    )
    dzwieki: list[str] = []
    monkeypatch.setattr(obsluga._dzwieki, "zagraj_sukces", lambda: dzwieki.append("sukces"))
    monkeypatch.setattr(obsluga._dzwieki, "zagraj_porazke", lambda: dzwieki.append("porazka"))

    aktywny_projekt = AktywnyProjektSkrotu()
    ostatni_komunikat = OstatniKomunikatSkrotu()
    fikcyjny_rejestr = rejestr if rejestr is not None else _FalszywyRejestr()
    instancja = ObslugaSkrotu(Konfiguracja(), aktywny_projekt, fikcyjny_rejestr, ostatni_komunikat)  # type: ignore[arg-type]
    return instancja, dzwieki, ostatni_komunikat, fikcyjny_rejestr, aktywny_projekt


def test_brak_aktywnego_projektu_gra_porazke_i_nie_dotyka_rozpoznania(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instancja, dzwieki, ostatni_komunikat, _rejestr, _aktywny = _obsluga(monkeypatch, okno=_okno())
    # Aktywny projekt nie jest ustawiony.

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is False
    assert "Brak aktywnego projektu skrótu" in komunikat.tekst


def test_adres_z_przegladarki_trafia_do_kolejki_i_gra_sukces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Przykładowa strona")
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl/artykul"
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is True
    assert "Dodano adres strony: Przykładowa strona" in komunikat.tekst
    # Kolejka opróżniła się od razu, bo fikcyjny rejestr nie jest zajęty.
    assert rejestr.uruchomienia == ["Projekt A"]


def test_brak_odczytu_paska_adresu_gra_porazke(monkeypatch: pytest.MonkeyPatch) -> None:
    okno = _okno(nazwa_procesu="firefox", tytul="Strona")
    instancja, dzwieki, ostatni_komunikat, _rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska=None
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "nie udało się odczytać" in komunikat.tekst.lower()


def test_pliki_z_eksploratora_traf_do_kolejki(monkeypatch: pytest.MonkeyPatch) -> None:
    okno = _okno(nazwa_klasy="CabinetWClass")
    pliki = (Path("a.txt"), Path("b.txt"))
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, pliki_zaznaczone=pliki
    )
    aktywny.ustaw("Projekt B")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "Dodano plik: a.txt i 1 więcej" in komunikat.tekst
    assert rejestr.uruchomienia == ["Projekt B"]


def test_gdy_rejestr_jest_zajety_pozycja_wraca_do_kolejki(monkeypatch: pytest.MonkeyPatch) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    rejestr = _FalszywyRejestr(rzuc_juz_trwa_razy=1)
    instancja, dzwieki, _ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl", rejestr=rejestr
    )
    aktywny.ustaw("Projekt C")

    instancja._obsluz_nacisniecie()

    # Rejestr zgłosił zajętość: dźwięk sukcesu i komunikat i tak są wysłane
    # (źródło zostało zapisane), ale przetwarzanie nie wystartowało jeszcze.
    assert dzwieki == ["sukces"]
    assert rejestr.uruchomienia == []
    assert instancja._kolejka.liczba_oczekujacych() == 1

    # Nasłuch zakończenia (symulowany ręcznie) opróżnia kolejkę, gdy rejestr jest już wolny.
    instancja._sprobuj_oproznic_kolejke()
    assert rejestr.uruchomienia == ["Projekt C"]
    assert instancja._kolejka.liczba_oczekujacych() == 0


def test_nierozpoznany_program_gra_porazke_z_nazwa_programu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="notepad", nazwa_klasy="Notepad")
    instancja, dzwieki, ostatni_komunikat, _rejestr, aktywny = _obsluga(monkeypatch, okno=okno)
    aktywny.ustaw("Projekt D")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "notepad" in komunikat.tekst
