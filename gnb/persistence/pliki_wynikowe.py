"""Zgodność checkpointu z plikami wynikowymi na dysku oraz przepakowanie grup.

Moduł odpowiada za trzy rzeczy, które łączy jedno: plik wynikowy jest zapisany
zarówno na dysku, jak i w checkpoincie, a ręczna zmiana jednego z nich bez
drugiego nie może zostać przemilczana. Po pierwsze, wykrywa pliki wynikowe,
które checkpoint zna, a których nie ma już na dysku. Po drugie, wycofuje grupę
tematyczną do przepakowania, gdy jej skład się zmienia: dochodzi nowe źródło,
źródło znika albo jego treść zostaje zastąpiona. Po trzecie, po przepakowaniu
usuwa stare pliki grupy i zapisuje, czym zostały zastąpione.

Moduł nie zapisuje checkpointu, nie pisze do dzienników i nie przetwarza treści
źródeł. Zapis checkpointu oraz wpisy do logów należą do wywołującego, żeby zapis
checkpointu pozostał w jednym miejscu, zgodnie z sekcją piętnastą CLAUDE.md.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from gnb.core.stale import FormatWynikowy, StatusZrodla, TypZrodla
from gnb.persistence.checkpoint import Checkpoint, StanZrodla, ZastapionyPlikGrupy
from gnb.persistence.projekt import UkladProjektu

# Opis nowego pliku w zapisie o zastąpieniu, gdy po przepakowaniu grupa nie ma
# już żadnego pliku, na przykład dlatego, że jej źródła zostały pominięte.
NOWA_NAZWA_BRAK = "brak nowego pliku, źródła grupy zostały pominięte"

POWOD_PLIK_USUNIETY_RECZNIE = "plik wynikowy usunięty ręcznie z dysku"


@dataclass(frozen=True, slots=True)
class BrakujacyPlik:
    """Plik wynikowy znany checkpointowi, którego nie ma na dysku.

    Plik wersji MD jest dodatkiem do pliku TXT i nie zajmuje slotu notatnika.
    Jego brak jest zgłaszany, ale nie zmienia statusu źródła, bo treść źródła
    jest nadal w pliku TXT.
    """

    sciezka_wzgledna: str
    format: str
    identyfikatory_zrodel: tuple[str, ...]

    @property
    def czy_zajmuje_slot(self) -> bool:
        """Prawda dla plików, których brak oznacza brak treści źródła w wynikach."""
        return self.format != FormatWynikowy.MD.value

    @property
    def nazwa(self) -> str:
        """Sama nazwa pliku, czytelna przy odsłuchu w odróżnieniu od pełnej ścieżki."""
        return PurePosixPath(self.sciezka_wzgledna).name


def znajdz_brakujace_pliki(uklad: UkladProjektu, checkpoint: Checkpoint) -> list[BrakujacyPlik]:
    """Zwraca pliki wynikowe źródeł spakowanych, których nie ma na dysku.

    Sprawdza wyłącznie istnienie plików, niczego nie zmienia. Ten sam plik grupy
    jest zapisany przy każdym ze swoich źródeł, więc jest zwracany raz, ze
    wszystkimi źródłami.
    """
    po_sciezce: dict[str, tuple[str, list[str]]] = {}
    for stan in checkpoint.zrodla.values():
        if stan.status != StatusZrodla.SPAKOWANE.value:
            continue
        for wynik in stan.wyniki:
            identyfikatory = po_sciezce.setdefault(wynik.sciezka_wzgledna, (wynik.format, []))[1]
            if stan.identyfikator not in identyfikatory:
                identyfikatory.append(stan.identyfikator)
    return [
        BrakujacyPlik(sciezka, format_pliku, tuple(identyfikatory))
        for sciezka, (format_pliku, identyfikatory) in po_sciezce.items()
        if not _sciezka_w_projekcie(uklad, sciezka).is_file()
    ]


def usun_plik_wynikowy(uklad: UkladProjektu, sciezka_wzgledna: str) -> bool:
    """Usuwa jeden plik wynikowy z dysku i zwraca prawdę, gdy plik istniał.

    Odmawia usunięcia czegokolwiek spoza katalogu projektu: ścieżka pochodzi
    z checkpointu, który da się edytować ręcznie, a ta funkcja kasuje pliki.
    """
    sciezka = _sciezka_w_projekcie(uklad, sciezka_wzgledna)
    if not sciezka.resolve().is_relative_to(uklad.katalog_projektu.resolve()):
        return False
    try:
        sciezka.unlink()
    except FileNotFoundError:
        return False
    return True


def czlonkowie_grupy(checkpoint: Checkpoint, nazwa_grupy: str) -> list[StanZrodla]:
    """Zwraca źródła spakowane, które należą do grupy i podlegają grupowaniu.

    Materiał nutowy nie podlega grupowaniu tematycznemu niezależnie od nazwy
    grupy, którą mu nadano, więc nigdy nie jest członkiem grupy.
    """
    return [
        stan
        for stan in checkpoint.zrodla.values()
        if stan.grupa_pakowania == nazwa_grupy
        and stan.typ != TypZrodla.PLIK_NUTY.value
        and stan.status == StatusZrodla.SPAKOWANE.value
    ]


def wycofaj_grupe(
    checkpoint: Checkpoint,
    nazwa_grupy: str,
    *,
    dodatkowe_sciezki: Iterable[str] = (),
) -> list[str]:
    """Cofa spakowane źródła grupy do stanu „znormalizowane”, żeby spakować ją od nowa.

    Źródła wracają do puli pakowania, a ich stare pliki są zapisywane jako
    oczekujące na zastąpienie: usuwa je dopiero `domknij_zastapione_pliki`,
    po zapisaniu nowych. Dzięki temu przerwanie pracy w środku nie zostawia
    grupy bez żadnego pliku. Argument `dodatkowe_sciezki` to pliki, które
    należały do grupy, a których właściciela nie ma już w checkpoincie albo
    wyszedł z grupy, na przykład źródło usuwane z projektu.

    Zwraca identyfikatory źródeł cofniętych do przepakowania.
    """
    czlonkowie = czlonkowie_grupy(checkpoint, nazwa_grupy)
    stare: list[str] = []
    for sciezka in [
        *dodatkowe_sciezki,
        *(wynik.sciezka_wzgledna for stan in czlonkowie for wynik in stan.wyniki),
    ]:
        if sciezka not in stare:
            stare.append(sciezka)

    for stan in czlonkowie:
        stan.wyniki = []
        stan.ostrzezenia_pakowania = []
        stan.status = StatusZrodla.ZNORMALIZOWANE.value

    oczekujace = {
        wpis.stara_nazwa for wpis in checkpoint.zastapione_pliki_grup if not wpis.nowa_nazwa
    }
    for sciezka in stare:
        if sciezka not in oczekujace:
            checkpoint.zastapione_pliki_grup.append(
                ZastapionyPlikGrupy(stara_nazwa=sciezka, nowa_nazwa="", grupa=nazwa_grupy)
            )
    return [stan.identyfikator for stan in czlonkowie]


def domknij_zastapione_pliki(
    uklad: UkladProjektu, checkpoint: Checkpoint
) -> list[ZastapionyPlikGrupy]:
    """Usuwa stare pliki grup i uzupełnia zapis o tym, czym zostały zastąpione.

    Wywoływana po fazie pakowania. Stary plik, który po przepakowaniu dostał tę
    samą nazwę co nowy, został po prostu nadpisany, więc nie jest zastąpieniem
    i jego wpis znika. Zwraca wpisy domknięte w tym wywołaniu, żeby wywołujący
    mógł je zapisać w dzienniku.
    """
    domkniete: list[ZastapionyPlikGrupy] = []
    zachowane: list[ZastapionyPlikGrupy] = []
    for wpis in checkpoint.zastapione_pliki_grup:
        if wpis.nowa_nazwa:
            zachowane.append(wpis)
            continue
        nowe = _aktualne_pliki_grupy(checkpoint, wpis.grupa)
        if wpis.stara_nazwa in nowe:
            continue
        usun_plik_wynikowy(uklad, wpis.stara_nazwa)
        wpis.nowa_nazwa = ", ".join(PurePosixPath(sciezka).name for sciezka in nowe) or (
            NOWA_NAZWA_BRAK
        )
        zachowane.append(wpis)
        domkniete.append(wpis)
    checkpoint.zastapione_pliki_grup = zachowane
    return domkniete


def usun_pliki_zrodla(uklad: UkladProjektu, stan: StanZrodla) -> list[str]:
    """Usuwa z dysku wszystkie pliki wynikowe jednego źródła i zwraca ich nazwy.

    Dotyczy źródła spoza grupy albo jedynego członka grupy: jego pliki nie
    zawierają treści żadnego innego źródła.
    """
    usuniete: list[str] = []
    for sciezka in dict.fromkeys(wynik.sciezka_wzgledna for wynik in stan.wyniki):
        if usun_plik_wynikowy(uklad, sciezka):
            usuniete.append(PurePosixPath(sciezka).name)
    return usuniete


def pozostale_pliki_zrodla(
    uklad: UkladProjektu, stan: StanZrodla, wykluczone: Sequence[str]
) -> list[str]:
    """Zwraca nazwy plików źródła, które nadal istnieją na dysku, poza wymienionymi."""
    return [
        PurePosixPath(sciezka).name
        for sciezka in dict.fromkeys(wynik.sciezka_wzgledna for wynik in stan.wyniki)
        if sciezka not in wykluczone and _sciezka_w_projekcie(uklad, sciezka).is_file()
    ]


def _aktualne_pliki_grupy(checkpoint: Checkpoint, nazwa_grupy: str | None) -> list[str]:
    """Zwraca posortowane ścieżki plików, które grupa ma po przepakowaniu."""
    return sorted(
        {
            wynik.sciezka_wzgledna
            for stan in checkpoint.zrodla.values()
            if stan.grupa_pakowania == nazwa_grupy
            and stan.typ != TypZrodla.PLIK_NUTY.value
            and stan.status == StatusZrodla.SPAKOWANE.value
            for wynik in stan.wyniki
        }
    )


def _sciezka_w_projekcie(uklad: UkladProjektu, sciezka_wzgledna: str) -> Path:
    return uklad.katalog_projektu / Path(*PurePosixPath(sciezka_wzgledna).parts)
