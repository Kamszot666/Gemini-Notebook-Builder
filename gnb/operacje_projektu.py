"""Ręczne operacje użytkownika na źródłach istniejącego projektu.

Trzy operacje z etapu czternastego: oznaczenie źródła jako zweryfikowanego
ręcznie, usunięcie źródła z projektu oraz przygotowanie zastąpienia jego treści
plikiem. Wspólne jest to, że działają na już zapisanym projekcie, na żądanie
człowieka, i że każda zmiana trafia jednocześnie do checkpointu, do obu logów,
do manifestu i do raportu, zgodnie z sekcją siódmą CLAUDE.md: zmiana bez śladu
jest gorsza niż błąd.

Moduł nie przetwarza treści. Zastąpienie treści plikiem wymaga ekstrakcji, więc
wykonuje je potok (`przetworz_projekt` z argumentem `zastepcze_tresci`); tutaj
jest tylko sprawdzenie, czy zastąpienie jest możliwe. Usunięcie źródła z grupy
zostawia pozostałe źródła grupy do przepakowania, którego też dokonuje potok.

Operacje zapisują checkpoint, więc wywołujący musi zagwarantować, że w tej
chwili nie trwa żaden przebieg przetwarzania tego projektu: zapis checkpointu
ma jednego właściciela naraz, zgodnie z sekcją piętnastą CLAUDE.md.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.core.stale import StatusZrodla, TypZrodla
from gnb.core.wyjatki import BladGnb, BladTrwaly
from gnb.ingestion.wejscie import identyfikator_awaryjny, waliduj_i_utworz_zrodlo
from gnb.logging_pl.dziennik import (
    NAZWA_LOGU_SZCZEGOLOWEGO,
    NAZWA_LOGU_WAZNEGO,
    ZDARZENIE_ZRODLO_USUNIETE,
    ZDARZENIE_ZRODLO_ZWERYFIKOWANE,
    DziennikSzczegolowy,
    DziennikWazny,
    teraz_lokalny,
)
from gnb.persistence.checkpoint import Checkpoint, StanZrodla, WejscieZapis, wczytaj, zapisz
from gnb.persistence.pliki_wynikowe import (
    czlonkowie_grupy,
    usun_pliki_zrodla,
    wycofaj_grupe,
)
from gnb.persistence.projekt import UkladProjektu
from gnb.potok import (
    identyfikatory_materialow_do_sprawdzenia,
    odbuduj_manifest_i_raport,
    pozycja_z_wejscia,
)

# Statusy, przy których zastąpienie treści ma sens: źródło ma jakąś treść do
# podmiany albo jej brak, który użytkownik chce uzupełnić ręcznie. Duplikat
# innego źródła i źródło jeszcze nieprzetworzone są poza tym zakresem.
STATUSY_Z_ZASTAPIENIEM_TRESCI = frozenset(
    {
        StatusZrodla.SPAKOWANE.value,
        StatusZrodla.ZNORMALIZOWANE.value,
        StatusZrodla.POMINIETE.value,
        StatusZrodla.BLAD.value,
    }
)


@dataclass(frozen=True, slots=True)
class WynikUsuniecia:
    """Skutki usunięcia źródła z projektu, potrzebne do komunikatu i dalszych kroków."""

    pochodzenie: str
    usuniete_pliki: tuple[str, ...]
    wymaga_przepakowania: bool


def wczytaj_checkpoint_projektu(uklad: UkladProjektu) -> Checkpoint:
    """Wczytuje checkpoint projektu albo zgłasza czytelny błąd trwały, gdy go nie ma."""
    checkpoint = wczytaj(uklad.checkpoint) if uklad.checkpoint.is_file() else None
    if checkpoint is None:
        raise BladTrwaly(f"Projekt „{uklad.nazwa_projektu}” nie ma checkpointu.")
    return checkpoint


def sprawdz_mozliwosc_zastapienia(checkpoint: Checkpoint, identyfikator: str) -> None:
    """Zgłasza błąd trwały, gdy treści tego źródła nie da się zastąpić plikiem."""
    stan = checkpoint.zrodla.get(identyfikator)
    if stan is None:
        raise BladTrwaly("Nie ma w projekcie źródła o tym identyfikatorze.", identyfikator)
    if stan.status not in STATUSY_Z_ZASTAPIENIEM_TRESCI:
        raise BladTrwaly(
            f"Treści źródła w stanie „{stan.status}” nie da się zastąpić plikiem. "
            "Zastąpić można treść źródła spakowanego, znormalizowanego, pominiętego "
            "albo z błędem.",
            identyfikator,
        )


def oznacz_jako_zweryfikowane(
    uklad: UkladProjektu,
    konfiguracja: Konfiguracja,
    identyfikator: str,
    *,
    zegar_lokalny: Callable[[], datetime] = teraz_lokalny,
) -> None:
    """Oznacza źródło z materiałów do sprawdzenia jako obejrzane i uznane za dobre.

    Oznaczenie nie zmienia oceny jakości ani ostrzeżeń zapisanych w manifeście:
    odnotowuje wyłącznie, że człowiek je widział i się z nimi zgodził. Źródło
    przestaje być wymieniane w sekcji „Materiały do sprawdzenia”, a raport
    wymienia je osobno jako zweryfikowane ręcznie, wraz z dawnymi powodami.
    Odmawia dla źródła, które nie jest materiałem do sprawdzenia, bo nie ma
    czego weryfikować, i dla źródła już oznaczonego.
    """
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    stan = checkpoint.zrodla.get(identyfikator)
    if stan is None:
        raise BladTrwaly("Nie ma w projekcie źródła o tym identyfikatorze.", identyfikator)
    if identyfikator not in identyfikatory_materialow_do_sprawdzenia(checkpoint):
        raise BladTrwaly(
            "To źródło nie jest na liście materiałów do sprawdzenia, więc nie ma czego "
            "oznaczać jako zweryfikowane.",
            identyfikator,
        )

    stan.zweryfikowane_recznie = True
    zapisz(uklad.checkpoint, checkpoint)
    odbuduj_manifest_i_raport(uklad, konfiguracja, checkpoint)
    _zapisz_w_dziennikach(
        uklad,
        zegar_lokalny,
        ZDARZENIE_ZRODLO_ZWERYFIKOWANE,
        stan,
        f"Źródło {identyfikator} oznaczone przez użytkownika jako zweryfikowane ręcznie.",
    )


def usun_zrodlo_z_projektu(
    uklad: UkladProjektu,
    konfiguracja: Konfiguracja,
    identyfikator: str,
    *,
    zegar_lokalny: Callable[[], datetime] = teraz_lokalny,
) -> WynikUsuniecia:
    """Usuwa źródło z projektu: z checkpointu, z wejść, z decyzji deduplikacji i z dysku.

    Usuwane są pliki wynikowe źródła i jego wyniki pośrednie. Materiały
    źródłowe, czyli zachowane oryginały i wysłane pliki wejściowe, zostają
    na dysku: usunięcie źródła z projektu nie jest kasowaniem materiału, który
    użytkownik przyniósł, a ich zachowanie nic nie kosztuje w limicie notatnika.

    Źródło z grupy tematycznej, w której zostają inne źródła, nie może po
    prostu zabrać swojego fragmentu z pliku grupy, więc cała grupa jest
    cofana do przepakowania, a stary plik zostaje usunięty po zapisaniu nowego.
    Źródła oznaczone dotąd jako duplikaty usuwanego źródła wracają do puli
    pakowania, bo były duplikatami tylko wobec niego. Wynik mówi, czy potrzebny
    jest kolejny przebieg przetwarzania.
    """
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    stan = checkpoint.zrodla.get(identyfikator)
    if stan is None:
        raise BladTrwaly("Nie ma w projekcie źródła o tym identyfikatorze.", identyfikator)

    stare_sciezki = [wynik.sciezka_wzgledna for wynik in stan.wyniki]
    del checkpoint.zrodla[identyfikator]
    _usun_wejscia_zrodla(checkpoint, konfiguracja, identyfikator)
    _rozwiaz_duplikaty_usuwanego_zrodla(checkpoint, identyfikator)

    usuniete: list[str] = []
    if (
        stan.grupa_pakowania
        and stan.typ != TypZrodla.PLIK_NUTY.value
        and czlonkowie_grupy(checkpoint, stan.grupa_pakowania)
    ):
        wycofaj_grupe(checkpoint, stan.grupa_pakowania, dodatkowe_sciezki=stare_sciezki)
    else:
        # Źródło spoza grupy albo jedyny członek grupy: nikt inny nie korzysta
        # z jego plików, więc nie ma czego przepakowywać.
        usuniete = usun_pliki_zrodla(uklad, stan)
    _usun_wyniki_posrednie(uklad, identyfikator)

    wymaga_przepakowania = any(
        pozostaly.status == StatusZrodla.ZNORMALIZOWANE.value
        for pozostaly in checkpoint.zrodla.values()
    )
    zapisz(uklad.checkpoint, checkpoint)
    odbuduj_manifest_i_raport(uklad, konfiguracja, checkpoint)
    _zapisz_w_dziennikach(
        uklad,
        zegar_lokalny,
        ZDARZENIE_ZRODLO_USUNIETE,
        stan,
        f"Źródło {identyfikator} usunięte z projektu przez użytkownika. Usunięte pliki: "
        f"{', '.join(usuniete) or 'brak'}. Wymaga przepakowania: "
        f"{'tak' if wymaga_przepakowania else 'nie'}.",
    )
    return WynikUsuniecia(
        pochodzenie=stan.pochodzenie,
        usuniete_pliki=tuple(usuniete),
        wymaga_przepakowania=wymaga_przepakowania,
    )


TYPY_ZRODEL_SIECIOWYCH = frozenset({TypZrodla.STRONA_WWW.value, TypZrodla.YOUTUBE.value})


def przygotuj_ponowne_pobranie(
    uklad: UkladProjektu,
    konfiguracja: Konfiguracja,
    identyfikator: str,
    *,
    zegar_lokalny: Callable[[], datetime] = teraz_lokalny,
) -> tuple[WejscieZapis, WynikUsuniecia] | None:
    """Wycofuje zweryfikowane źródło sieciowe tak, by kolejny przebieg pobrał je od nowa.

    Źródło jest usuwane z projektu tą samą drogą co przy ręcznym usunięciu, a jego
    zapisane wejście wraca do wywołującego, który dodaje je do kolejnego przebiegu
    jako ponownie podany adres. Identyfikator trafia do listy
    `zweryfikowane_wstepnie`, więc nowo utworzone źródło od razu nosi znacznik
    ręcznej weryfikacji i nie wraca do materiałów do sprawdzenia. Źródło, które
    nie pochodzi z sieci, albo bez zapisanego wejścia daje ``None`` i nic nie
    zmienia: jego treść nie ma skąd być pobrana ponownie.
    """
    checkpoint = wczytaj_checkpoint_projektu(uklad)
    stan = checkpoint.zrodla.get(identyfikator)
    if stan is None or stan.typ not in TYPY_ZRODEL_SIECIOWYCH:
        return None
    wejscie = _wejscie_zrodla(checkpoint, konfiguracja, identyfikator)
    if wejscie is None:
        return None
    if identyfikator not in checkpoint.zweryfikowane_wstepnie:
        checkpoint.zweryfikowane_wstepnie.append(identyfikator)
    zapisz(uklad.checkpoint, checkpoint)
    wynik = usun_zrodlo_z_projektu(uklad, konfiguracja, identyfikator, zegar_lokalny=zegar_lokalny)
    return wejscie, wynik


def _wejscie_zrodla(
    checkpoint: Checkpoint, konfiguracja: Konfiguracja, identyfikator: str
) -> WejscieZapis | None:
    """Zwraca zapisane wejście, które prowadzi do źródła o podanym identyfikatorze."""
    moment = datetime.now(UTC)
    for wejscie in checkpoint.wejscia:
        pozycja = pozycja_z_wejscia(wejscie, konfiguracja, moment)
        if pozycja is None:
            continue
        try:
            id_wejscia = waliduj_i_utworz_zrodlo(pozycja, konfiguracja, moment).identyfikator_zrodla
        except BladGnb:
            continue
        if id_wejscia == identyfikator:
            return wejscie
    return None


def _usun_wejscia_zrodla(
    checkpoint: Checkpoint, konfiguracja: Konfiguracja, identyfikator: str
) -> None:
    """Usuwa z listy wejść wszystkie wpisy, które prowadzą do danego źródła.

    Bez tego wznowienie projektu odtworzyłoby usunięte źródło z zapisanych
    wejść. Identyfikator wejścia ustala się tą samą drogą co w potoku: przez
    walidację, a dla wejścia, którego nie da się zwalidować, przez identyfikator
    awaryjny.
    """
    moment = datetime.now(UTC)
    pozostale = []
    for wejscie in checkpoint.wejscia:
        pozycja = pozycja_z_wejscia(wejscie, konfiguracja, moment)
        if pozycja is None:
            pozostale.append(wejscie)
            continue
        try:
            id_wejscia = waliduj_i_utworz_zrodlo(pozycja, konfiguracja, moment).identyfikator_zrodla
        except BladGnb:
            id_wejscia = identyfikator_awaryjny(pozycja)
        if id_wejscia != identyfikator:
            pozostale.append(wejscie)
    checkpoint.wejscia = pozostale


def _rozwiaz_duplikaty_usuwanego_zrodla(checkpoint: Checkpoint, identyfikator: str) -> None:
    """Usuwa decyzje deduplikacji z udziałem źródła i przywraca jego duplikaty do pakowania."""
    for stan in checkpoint.zrodla.values():
        if stan.status == StatusZrodla.DUPLIKAT.value and stan.duplikat_glowny == identyfikator:
            stan.status = StatusZrodla.ZNORMALIZOWANE.value
            stan.duplikat_glowny = None
            stan.komunikat_bledu = None
    checkpoint.deduplikacja.decyzje = [
        decyzja
        for decyzja in checkpoint.deduplikacja.decyzje
        if identyfikator
        not in (decyzja.identyfikator_zrodla_glownego, decyzja.identyfikator_duplikatu)
    ]


def _usun_wyniki_posrednie(uklad: UkladProjektu, identyfikator: str) -> None:
    """Usuwa wyniki pośrednie źródła: znormalizowany tekst, wersję TXT i oryginał obrazu."""
    if not uklad.wyniki_posrednie.is_dir():
        return
    for plik in uklad.wyniki_posrednie.glob(f"{identyfikator}.*"):
        if plik.is_file():
            plik.unlink()


def _zapisz_w_dziennikach(
    uklad: UkladProjektu,
    zegar_lokalny: Callable[[], datetime],
    zdarzenie: str,
    stan: StanZrodla,
    komunikat: str,
) -> None:
    """Dopisuje zdarzenie do log_wazne.txt i komunikat do log_szczegolowy.txt."""
    dziennik_wazny = DziennikWazny(uklad.logi / NAZWA_LOGU_WAZNEGO, zegar_lokalny)
    dziennik_wazny.zapisz(f"{zdarzenie}: {stan.pochodzenie}".replace("|", "/"))
    with DziennikSzczegolowy(
        uklad.logi / NAZWA_LOGU_SZCZEGOLOWEGO, uklad.identyfikator_projektu
    ) as log:
        log.log(
            logging.INFO,
            komunikat,
            extra={"identyfikator_zrodla": stan.identyfikator},
        )


def zapisz_plik_zastepczy(katalog: Path, nazwa_pliku: str, zawartosc: bytes) -> Path:
    """Zapisuje przesłany plik zastępczy w katalogu projektu pod niekolidującą nazwą.

    Nazwa pliku musi być już oczyszczona przez wywołującego. Istniejący plik nie
    jest nadpisywany: kolejne zastąpienie tego samego źródła dostaje kolejny
    numer, więc wcześniej zapisane pliki zostają jako ślad tego, co podstawiono.
    """
    katalog.mkdir(parents=True, exist_ok=True)
    cel = katalog / nazwa_pliku
    licznik = 1
    while cel.exists():
        cel = katalog / f"{Path(nazwa_pliku).stem}_{licznik}{Path(nazwa_pliku).suffix}"
        licznik += 1
    cel.write_bytes(zawartosc)
    return cel
