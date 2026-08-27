"""Przyjmowanie adresów pojedynczo i listami oraz podsumowanie przed pobraniem.

Pole adresu w interfejsie oraz importowany plik TXT muszą przyjmować pojedynczy
adres, wiele adresów rozdzielonych spacjami i wiele adresów w osobnych
wierszach. Ten moduł zamienia taki tekst na listę adresów gotowych do
przetworzenia i buduje podsumowanie, które użytkownik ma zobaczyć, zanim
cokolwiek zostanie pobrane. To jest najtańszy moment na wychwycenie pomyłki.

Duplikaty są wykrywane po postaci kanonicznej adresu, więc dwa zapisy tego
samego artykułu różniące się parametrem śledzącym albo kolejnością parametrów
są rozpoznane jako jedno źródło. Zachowywane jest pierwsze wystąpienie, razem
z jego oryginalnym zapisem, bo to jego użyjemy do pobrania.

Wiersz zaczynający się od krzyżyka jest komentarzem i nie jest liczony jako
wpis. Pozwala to opisać listę adresów bez zaśmiecania podsumowania.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from gnb.core.url import adres_kanoniczny, czy_wyglada_na_adres, waliduj_adres
from gnb.core.wyjatki import BladTrwaly
from gnb.normalization.kodowanie import zdekoduj

ZNAK_KOMENTARZA = "#"


@dataclass(frozen=True, slots=True)
class AdresWejsciowy:
    """Jeden przyjęty adres w dwóch postaciach: podanej przez użytkownika i kanonicznej."""

    podany: str
    kanoniczny: str


@dataclass(frozen=True, slots=True)
class OdrzuconyWpis:
    """Wpis, którego nie dało się uznać za adres, wraz z powodem odrzucenia."""

    wartosc: str
    powod: str


@dataclass(frozen=True, slots=True)
class PodsumowanieListyUrl:
    """Wynik analizy listy adresów, pokazywany przed rozpoczęciem pobierania."""

    adresy: tuple[AdresWejsciowy, ...] = ()
    duplikaty: tuple[str, ...] = ()
    odrzucone: tuple[OdrzuconyWpis, ...] = field(default=())

    @property
    def liczba_wykrytych(self) -> int:
        """Liczba wszystkich wpisów, łącznie z duplikatami i odrzuconymi."""
        return len(self.adresy) + len(self.duplikaty) + len(self.odrzucone)

    @property
    def liczba_poprawnych(self) -> int:
        """Liczba adresów, które trafią do przetwarzania."""
        return len(self.adresy)

    @property
    def liczba_duplikatow(self) -> int:
        """Liczba wpisów pominiętych jako powtórzenie wcześniejszego adresu."""
        return len(self.duplikaty)

    @property
    def liczba_odrzuconych(self) -> int:
        """Liczba wpisów, których nie dało się uznać za adres."""
        return len(self.odrzucone)


def zbierz_adresy(
    tekst: str, dodatkowe_parametry_sledzace: Iterable[str] = ()
) -> PodsumowanieListyUrl:
    """Zamienia tekst z adresami na podsumowanie gotowe do pokazania użytkownikowi.

    Wpisy są rozdzielane dowolnymi białymi znakami, więc jeden adres, kilka
    adresów w wierszu i kilka adresów w osobnych wierszach dają ten sam wynik.
    """
    dodatkowe = tuple(dodatkowe_parametry_sledzace)
    adresy: list[AdresWejsciowy] = []
    duplikaty: list[str] = []
    odrzucone: list[OdrzuconyWpis] = []
    widziane: set[str] = set()

    for wpis in _wpisy(tekst):
        try:
            podany = waliduj_adres(wpis)
            kanoniczny = adres_kanoniczny(podany, dodatkowe)
        except BladTrwaly as blad:
            odrzucone.append(OdrzuconyWpis(wartosc=wpis, powod=blad.komunikat))
            continue
        if kanoniczny in widziane:
            duplikaty.append(podany)
            continue
        widziane.add(kanoniczny)
        adresy.append(AdresWejsciowy(podany=podany, kanoniczny=kanoniczny))

    return PodsumowanieListyUrl(
        adresy=tuple(adresy), duplikaty=tuple(duplikaty), odrzucone=tuple(odrzucone)
    )


def wczytaj_liste_z_pliku(
    sciezka: Path, dodatkowe_parametry_sledzace: Iterable[str] = ()
) -> PodsumowanieListyUrl:
    """Wczytuje plik TXT z adresami i zwraca podsumowanie jego zawartości.

    Kodowanie pliku jest wykrywane tak samo jak dla zwykłych plików tekstowych.
    Brak pliku, katalog zamiast pliku oraz błąd odczytu kończą się błędem
    trwałym, ponieważ w tym wypadku nie ma czego podsumowywać.
    """
    if not sciezka.exists():
        raise BladTrwaly(f"Plik z listą adresów nie istnieje: {sciezka}.")
    if not sciezka.is_file():
        raise BladTrwaly(f"Ścieżka listy adresów nie wskazuje zwykłego pliku: {sciezka}.")
    try:
        dane = sciezka.read_bytes()
    except OSError as blad:
        raise BladTrwaly(f"Nie udało się odczytać listy adresów {sciezka}: {blad}") from blad
    tekst, _ = zdekoduj(dane)
    return zbierz_adresy(tekst, dodatkowe_parametry_sledzace)


def opis_podsumowania(podsumowanie: PodsumowanieListyUrl) -> str:
    """Buduje opis podsumowania czytelny liniowo, bez tabel i znaków sterujących.

    Opis jest wspólny dla wiersza poleceń i dla przyszłego interfejsu WWW, żeby
    użytkownik widział w obu miejscach dokładnie tę samą treść.
    """
    wiersze = [
        f"Wykryte adresy: {podsumowanie.liczba_wykrytych}",
        f"Adresy poprawne: {podsumowanie.liczba_poprawnych}",
        f"Duplikaty pominięte: {podsumowanie.liczba_duplikatow}",
        f"Wpisy odrzucone: {podsumowanie.liczba_odrzuconych}",
    ]
    if podsumowanie.duplikaty:
        wiersze.append("")
        wiersze.append("Pominięte jako duplikat wcześniejszego adresu:")
        wiersze.extend(f"  {adres}" for adres in podsumowanie.duplikaty)
    if podsumowanie.odrzucone:
        wiersze.append("")
        wiersze.append("Odrzucone wpisy wraz z powodem:")
        wiersze.extend(f"  {wpis.wartosc} — {wpis.powod}" for wpis in podsumowanie.odrzucone)
    return "\n".join(wiersze)


def _wpisy(tekst: str) -> list[str]:
    """Rozdziela tekst na wpisy, pomijając komentarze i puste fragmenty.

    Wiersz zawierający choć jeden poprawny adres jest dzielony na fragmenty po
    białych znakach, bo użytkownik może wpisać kilka adresów w jednej linii.
    Wiersz bez żadnego adresu jest zwracany w całości jako jeden wpis, dzięki
    czemu zdanie zwykłego tekstu nie zamienia się w tyle odrzuceń, ile ma słów.
    """
    wpisy: list[str] = []
    for wiersz in tekst.splitlines():
        oczyszczony = wiersz.strip()
        if not oczyszczony or oczyszczony.startswith(ZNAK_KOMENTARZA):
            continue
        fragmenty = [fragment for fragment in oczyszczony.split() if fragment]
        if any(czy_wyglada_na_adres(fragment) for fragment in fragmenty):
            wpisy.extend(fragmenty)
            continue
        wpisy.append(_wpis_calego_wiersza(oczyszczony, fragmenty))
    return wpisy


def _wpis_calego_wiersza(wiersz: str, fragmenty: list[str]) -> str:
    """Zwraca wpis reprezentujący wiersz, w którym nie ma żadnego adresu.

    Wiersz prozy rozbity na pojedyncze słowa dałby tyle odrzuconych wpisów, ile
    ma słów, a podsumowanie stałoby się nieczytelne. Dlatego taki wiersz jest
    zgłaszany jako jeden wpis. Wiersz złożony z jednego słowa zachowuje to
    słowo, żeby komunikat o powodzie odrzucenia dotyczył dokładnie jego.
    """
    return fragmenty[0] if len(fragmenty) == 1 else wiersz
