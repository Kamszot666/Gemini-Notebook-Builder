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
    from datetime import UTC, datetime

    from gnb.core.konfiguracja import Konfiguracja
    from gnb.hotkeys import obsluga
    from gnb.hotkeys.model import InformacjeOOknie, RodzajWynikuKopiowania, WynikKopiowania
    from gnb.hotkeys.obsluga import ObslugaSkrotu
    from gnb.ingestion.wejscie import przyjmij_tekst
    from gnb.persistence.projekt import ustal_uklad
    from gnb.ui.stan_skrotu import AktywnyProjektSkrotu, OstatniKomunikatSkrotu
    from gnb.ui.zadania import ZadanieJuzTrwa


_KATALOG_WYNIKOW_TESTU: list[Path] = []


@pytest.fixture(autouse=True)
def _katalog_wynikow_testu(tmp_path: Path) -> object:
    """Katalog wyników na czas testu; skrót sprawdza przy naciśnięciu, czy projekt istnieje."""
    _KATALOG_WYNIKOW_TESTU[:] = [tmp_path / "wyniki"]
    yield tmp_path / "wyniki"
    _KATALOG_WYNIKOW_TESTU.clear()


def _utworz_checkpoint(katalog_wynikow: Path, nazwa: str) -> Path:
    katalog = ustal_uklad(katalog_wynikow, nazwa).katalog_projektu
    katalog.mkdir(parents=True, exist_ok=True)
    plik = katalog / "checkpoint.json"
    plik.write_text("{}", encoding="utf-8")
    return plik


class _AktywnyZProjektemNaDysku(AktywnyProjektSkrotu if sys.platform == "win32" else object):  # type: ignore[misc]
    """Wybór projektu, który od razu tworzy checkpoint, jak projekt wybrany w interfejsie."""

    def __init__(self, katalog_wynikow: Path) -> None:
        super().__init__()
        self._katalog_testu = katalog_wynikow

    def ustaw(self, nazwa: str) -> None:
        _utworz_checkpoint(self._katalog_testu, nazwa)
        super().ustaw(nazwa)


class _FalszywyRejestr:
    """Podstawa `RejestrZadan`: zapamiętuje żądania uruchomienia, nic nie wykonuje.

    Argument ``przy_pierwszym_wywolaniu`` symuluje zbieg zdarzeń: coś, co ma się
    wydarzyć dokładnie w chwili, gdy skrót próbuje uruchomić przetwarzanie po
    raz pierwszy, na przykład zakończenie się innego zadania i jego własny
    nasłuch trafiający akurat na pustą kolejkę.
    """

    def __init__(
        self,
        *,
        rzuc_juz_trwa_razy: int = 0,
        przy_pierwszym_wywolaniu: object | None = None,
    ) -> None:
        self.uruchomienia: list[str] = []
        self._rzuc_juz_trwa_razy = rzuc_juz_trwa_razy
        self._przy_pierwszym_wywolaniu = przy_pierwszym_wywolaniu
        self._nasluchy: list[object] = []

    def dodaj_nasluch_zakonczenia(self, wywolanie: object) -> None:
        self._nasluchy.append(wywolanie)

    def uruchom(self, nazwa_projektu: str, _praca: object, *, liczba_pozycji: int = 0) -> None:
        if self._przy_pierwszym_wywolaniu is not None:
            wywolanie, self._przy_pierwszym_wywolaniu = self._przy_pierwszym_wywolaniu, None
            wywolanie()  # type: ignore[operator]
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
    konfiguracja: Konfiguracja | None = None,
    wynik_kopiowania: WynikKopiowania | None = None,
    wywolania_schowka: list[str] | None = None,
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
    nic_nie_zaznaczono = WynikKopiowania(RodzajWynikuKopiowania.NIC_NIE_ZAZNACZONO)

    def falszywe_kopiowanie() -> WynikKopiowania:
        if wywolania_schowka is not None:
            wywolania_schowka.append("kopiowanie")
        return wynik_kopiowania or nic_nie_zaznaczono

    monkeypatch.setattr(obsluga._schowek, "skopiuj_zaznaczenie", falszywe_kopiowanie)
    dzwieki: list[str] = []
    monkeypatch.setattr(obsluga._dzwieki, "zagraj_sukces", lambda: dzwieki.append("sukces"))
    monkeypatch.setattr(obsluga._dzwieki, "zagraj_porazke", lambda: dzwieki.append("porazka"))

    konfiguracja = konfiguracja or Konfiguracja(katalog_wynikow=_KATALOG_WYNIKOW_TESTU[0])
    aktywny_projekt = _AktywnyZProjektemNaDysku(konfiguracja.katalog_wynikow)
    ostatni_komunikat = OstatniKomunikatSkrotu()
    fikcyjny_rejestr = rejestr if rejestr is not None else _FalszywyRejestr()
    instancja = ObslugaSkrotu(konfiguracja, aktywny_projekt, fikcyjny_rejestr, ostatni_komunikat)  # type: ignore[arg-type]
    return instancja, dzwieki, ostatni_komunikat, fikcyjny_rejestr, aktywny_projekt


def test_brak_aktywnego_projektu_gra_porazke_i_nic_nie_zapisuje(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Przykładowa strona")
    wywolania: list[str] = []
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl/artykul", wywolania_schowka=wywolania
    )

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    assert aktywny.aktualny() is None
    assert rejestr.uruchomienia == []
    assert instancja._kolejka.liczba_oczekujacych() == 0
    # Bez projektu nie ma po co dotykać schowka użytkownika.
    assert wywolania == []
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is False
    assert "Ustaw aktywny projekt skrótu na stronie projektu" in komunikat.tekst


def test_usuniety_katalog_aktywnego_projektu_gra_porazke_czysci_wybor_i_nie_tworzy_katalogu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Przykładowa strona")
    wywolania: list[str] = []
    plik_stanu = tmp_path / "stan.json"
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl/artykul", wywolania_schowka=wywolania
    )
    aktywny._plik_stanu = plik_stanu
    aktywny.ustaw("Projekt A")
    assert plik_stanu.is_file()
    katalog = ustal_uklad(_KATALOG_WYNIKOW_TESTU[0], "Projekt A").katalog_projektu
    (katalog / "checkpoint.json").unlink()

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    assert aktywny.aktualny() is None
    assert not plik_stanu.exists()
    assert rejestr.uruchomienia == []
    assert instancja._kolejka.liczba_oczekujacych() == 0
    assert wywolania == []
    assert not (katalog / "checkpoint.json").exists()
    assert not (katalog / "materialy_zrodlowe").exists()
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is False
    assert "Projekt A" in komunikat.tekst
    assert "już nie ma na dysku" in komunikat.tekst


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


def test_gdy_rejestr_jest_chwilowo_zajety_ponowienie_od_razu_konczy_przetwarzanie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Jedno ponowienie w `_sprobuj_oproznic_kolejke` domyślnie stara się jeszcze raz.

    Rejestr jest zajęty tylko przy pierwszej próbie, więc wbudowane ponowienie
    powinno od razu odebrać pozycje z powrotem z kolejki i uruchomić
    przetwarzanie — bez czekania na osobny nasłuch zakończenia.
    """
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    rejestr = _FalszywyRejestr(rzuc_juz_trwa_razy=1)
    instancja, dzwieki, _ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl", rejestr=rejestr
    )
    aktywny.ustaw("Projekt C")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    assert rejestr.uruchomienia == ["Projekt C"]
    assert instancja._kolejka.liczba_oczekujacych() == 0


def test_gdy_rejestr_pozostaje_zajety_ponowienie_jest_ograniczone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ponowienie nie zamienia się w pętlę zajętą czekaniem, gdy rejestr wciąż jest zajęty."""
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    rejestr = _FalszywyRejestr(rzuc_juz_trwa_razy=99)
    instancja, dzwieki, _ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl", rejestr=rejestr
    )
    aktywny.ustaw("Projekt C")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    assert rejestr.uruchomienia == []
    assert instancja._kolejka.liczba_oczekujacych() == 1

    # Prawdziwy nasłuch zakończenia zadania, wołany później, wciąż odbierze pozycje.
    rejestr._rzuc_juz_trwa_razy = 0
    instancja._sprobuj_oproznic_kolejke()
    assert rejestr.uruchomienia == ["Projekt C"]
    assert instancja._kolejka.liczba_oczekujacych() == 0


def test_zbieg_zdarzen_dokonczenie_zadania_miedzy_pobraniem_a_odlozeniem_z_powrotem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Odtwarza dokładnie wyścig z uwagi szóstej recenzji pull requesta 33.

    Scenariusz: skrót pobiera pozycje z kolejki (kolejka jest teraz pusta),
    a dokładnie w chwili próby uruchomienia przetwarzania kończy się inne
    zadanie i jego nasłuch zakończenia sam próbuje opróżnić kolejkę — trafia
    na pustą kolejkę (pozycje jeszcze nie wróciły) i nic nie robi. Bez
    ponowienia pozycje utknęłyby w kolejce do następnego naciśnięcia skrótu.
    Symulacja tego konkurencyjnego nasłuchu jest wołana z wnętrza `uruchom`
    fałszywego rejestru, w momencie odpowiadającym rzeczywistemu zbiegowi
    zdarzeń.
    """
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    wywolania_zbiegajace: list[int] = []

    def symuluj_konkurencyjne_zakonczenie() -> None:
        # W tym momencie kolejka jest już pusta (pozycje odebrane przez
        # zewnętrzne wywołanie), więc ten nasłuch "z innego wątku" nic nie
        # znajduje — dokładnie tak jak przy prawdziwym zbiegu zdarzeń.
        assert instancja._kolejka.liczba_oczekujacych() == 0
        instancja._sprobuj_oproznic_kolejke(ponowienia=0)
        wywolania_zbiegajace.append(1)

    rejestr = _FalszywyRejestr(
        rzuc_juz_trwa_razy=1, przy_pierwszym_wywolaniu=symuluj_konkurencyjne_zakonczenie
    )
    instancja, dzwieki, _ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl", rejestr=rejestr
    )
    aktywny.ustaw("Projekt C")

    instancja._obsluz_nacisniecie()

    assert wywolania_zbiegajace == [1], "Konkurencyjny nasłuch musiał się wykonać w środku."
    assert dzwieki == ["sukces"]
    # Mimo że konkurencyjny nasłuch trafił na pustą kolejkę, wbudowane
    # ponowienie po nieudanej próbie uruchomienia i tak odzyskało pozycje.
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


def test_zatrzymaj_bez_oczekujacych_pozycji_nie_zglasza_niczego(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    instancja, _dzwieki, ostatni_komunikat, _rejestr, _aktywny = _obsluga(
        monkeypatch, okno=None, konfiguracja=Konfiguracja(katalog_wynikow=tmp_path)
    )

    instancja.zatrzymaj()

    assert ostatni_komunikat.aktualny() is None


def test_zatrzymaj_z_niepusta_kolejka_ostrzega_w_komunikacie_i_w_logach_projektu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Odtwarza uwagę piątą recenzji pull requesta 33: kolejka ginie przy zamknięciu serwera.

    Sprawdza wariant przyjęty przez użytkownika: ostrzeżenie w ostatnim
    komunikacie skrótu oraz w obu logach projektu, z liczbą utraconych pozycji
    i nazwą projektu, którego dotyczą — sama liczba jest bezużyteczna przy
    odsłuchu czytnikiem ekranu.
    """
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    instancja, _dzwieki, ostatni_komunikat, _rejestr, _aktywny = _obsluga(
        monkeypatch, okno=None, konfiguracja=konfiguracja
    )
    moment = datetime.now(UTC)
    instancja._kolejka.dodaj("Projekt Zamknięty", przyjmij_tekst("pierwsza", moment))
    instancja._kolejka.dodaj("Projekt Zamknięty", przyjmij_tekst("druga", moment))

    instancja.zatrzymaj()

    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert komunikat.sukces is False
    assert "Projekt Zamknięty (2)" in komunikat.tekst

    uklad = ustal_uklad(tmp_path, "Projekt Zamknięty")
    tekst_wazny = (uklad.logi / "log_wazne.txt").read_text(encoding="utf-8")
    assert "kolejki skrótu" in tekst_wazny
    assert "2 pozycji" in tekst_wazny

    tekst_szczegolowy = (uklad.logi / "log_szczegolowy.txt").read_text(encoding="utf-8")
    assert "Projekt Zamknięty (2)" in tekst_szczegolowy


def test_zatrzymaj_z_kilkoma_projektami_w_kolejce_wymienia_wszystkie(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    instancja, _dzwieki, ostatni_komunikat, _rejestr, _aktywny = _obsluga(
        monkeypatch, okno=None, konfiguracja=konfiguracja
    )
    moment = datetime.now(UTC)
    instancja._kolejka.dodaj("Projekt A", przyjmij_tekst("a", moment))
    instancja._kolejka.dodaj("Projekt B", przyjmij_tekst("b", moment))

    instancja.zatrzymaj()

    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "Projekt A (1)" in komunikat.tekst
    assert "Projekt B (1)" in komunikat.tekst


# --- zaznaczony tekst przez schowek (etap piętnasty, część D2) ---------------


def _zaznaczono(tekst: str, uwaga: str = "") -> WynikKopiowania:
    return WynikKopiowania(RodzajWynikuKopiowania.ZAZNACZONO, tekst=tekst, uwaga=uwaga)


def test_zaznaczony_zwykly_tekst_trafia_do_szkicu_a_nie_do_kolejki(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl", wynik_kopiowania=_zaznaczono("Zdanie.")
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    assert instancja._szkic_tekstu.pobierz("Projekt A").tekst == "Zdanie.\n"
    assert instancja._kolejka.liczba_oczekujacych() == 0
    assert rejestr.uruchomienia == []
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None and komunikat.sukces is True
    # Komunikat mówi, ile znaków i do którego projektu, bez cytowania treści.
    assert "7 znaków" in komunikat.tekst
    assert "Projekt A" in komunikat.tekst
    assert "Zdanie." not in komunikat.tekst


def test_kolejne_zaznaczenia_sa_dopisywane_na_koncu_szkicu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="firefox", tytul="Strona")
    instancja, _dzwieki, _komunikat, _rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, wynik_kopiowania=_zaznaczono("Pierwszy.")
    )
    aktywny.ustaw("Projekt A")
    instancja._obsluz_nacisniecie()
    monkeypatch.setattr(obsluga._schowek, "skopiuj_zaznaczenie", lambda: _zaznaczono("Drugi."))

    instancja._obsluz_nacisniecie()

    assert instancja._szkic_tekstu.pobierz("Projekt A").tekst == "Pierwszy.\nDrugi.\n"


def test_zaznaczone_adresy_trafiaja_do_kolejki_jak_adres_strony(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch,
        okno=okno,
        adres_paska="inna.example",
        wynik_kopiowania=_zaznaczono("https://a.example/x\nhttps://b.example/y"),
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    assert rejestr.uruchomienia == ["Projekt A"]
    assert instancja._szkic_tekstu.pobierz("Projekt A").tekst == ""
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "Dodano adresy z zaznaczenia: 2" in komunikat.tekst


def test_brak_zaznaczenia_dziala_jak_dotad_i_bierze_adres_z_paska(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="przyklad.pl/artykul"
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    assert rejestr.uruchomienia == ["Projekt A"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None and "Dodano adres strony" in komunikat.tekst


def test_schowek_nie_do_przywrocenia_zachowuje_sie_jak_brak_zaznaczenia_i_mowi_o_tym(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    uwaga = "Schowek zawiera dane, których nie da się bezpiecznie przywrócić."
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch,
        okno=okno,
        adres_paska="przyklad.pl/artykul",
        wynik_kopiowania=WynikKopiowania(
            RodzajWynikuKopiowania.SCHOWEK_NIE_DO_PRZYWROCENIA, uwaga=uwaga
        ),
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["sukces"]
    assert rejestr.uruchomienia == ["Projekt A"]
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "Dodano adres strony" in komunikat.tekst
    assert uwaga in komunikat.tekst


def test_adres_interfejsu_w_pasku_adresu_gra_porazke(monkeypatch: pytest.MonkeyPatch) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Gemini Notebook Builder")
    konfiguracja = Konfiguracja(port_nasluchu=8765, katalog_wynikow=_KATALOG_WYNIKOW_TESTU[0])
    instancja, dzwieki, ostatni_komunikat, rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, adres_paska="127.0.0.1:8765", konfiguracja=konfiguracja
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    assert rejestr.uruchomienia == []
    assert instancja._kolejka.liczba_oczekujacych() == 0
    komunikat = ostatni_komunikat.aktualny()
    assert komunikat is not None
    assert "To jest adres interfejsu Gemini Notebook Builder" in komunikat.tekst


def test_zaznaczenie_nie_jest_odczytywane_w_eksploratorze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_klasy="CabinetWClass")
    wywolania: list[str] = []
    instancja, _dzwieki, _komunikat, _rejestr, aktywny = _obsluga(
        monkeypatch,
        okno=okno,
        pliki_zaznaczone=(Path("a.txt"),),
        wywolania_schowka=wywolania,
    )
    aktywny.ustaw("Projekt B")

    instancja._obsluz_nacisniecie()

    assert wywolania == []


def test_zbyt_dlugi_tekst_gra_porazke_i_nie_zmienia_szkicu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    okno = _okno(nazwa_procesu="chrome", tytul="Strona")
    instancja, dzwieki, _komunikat, _rejestr, aktywny = _obsluga(
        monkeypatch, okno=okno, wynik_kopiowania=_zaznaczono("x" * 600_000)
    )
    aktywny.ustaw("Projekt A")

    instancja._obsluz_nacisniecie()

    assert dzwieki == ["porazka"]
    assert instancja._szkic_tekstu.pobierz("Projekt A").tekst == ""
