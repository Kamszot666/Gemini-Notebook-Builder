"""Raport końcowy projektu w postaci czytelnego liniowo tekstu.

Raport podsumowuje przebieg przetwarzania: liczbę wejść, liczbę źródeł
poprawnych, pominiętych i błędnych, liczbę wykrytych duplikatów, liczbę źródeł
po deduplikacji, liczbę plików wynikowych w podziale na formaty, procent
wykorzystania limitu źródeł, największy plik wynikowy, łączną liczbę słów oraz
czas pracy.

Po liczbach raport wymienia z nazwy każde źródło pominięte oraz każde źródło
zakończone błędem, razem z powodem. Sama liczba pominięć nie mówi użytkownikowi,
czego zabrakło, a odszukiwanie tego w manifeście jest niewygodne przy odsłuchu
czytnikiem ekranu.

Dopóki nie ma deduplikacji ani plików PDF, odpowiednie liczby są zerowe. Raport
zawsze wypisuje wszystkie pozycje, żeby jego układ był przewidywalny.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ZrodloNieprzetworzone:
    """Źródło pominięte albo zakończone błędem, wraz z powodem do pokazania."""

    identyfikator: str
    pochodzenie: str
    status: str
    powod: str


@dataclass(frozen=True, slots=True)
class PodsumowanieProjektu:
    """Zestaw liczb i wykaz źródeł nieprzetworzonych, potrzebne do raportu końcowego."""

    liczba_wejsc: int
    liczba_zrodel_poprawnych: int
    liczba_zrodel_pominietych: int
    liczba_zrodel_blednych: int
    liczba_duplikatow: int
    liczba_zrodel_po_deduplikacji: int
    liczba_plikow_txt: int
    liczba_plikow_md: int
    liczba_plikow_pdf: int
    limit_zrodel: int
    najwiekszy_plik_nazwa: str | None
    najwiekszy_plik_bajtow: int
    laczna_liczba_slow: int
    czas_pracy_sekundy: float
    zrodla_nieprzetworzone: tuple[ZrodloNieprzetworzone, ...] = ()


def zbuduj_raport(nazwa_projektu: str, podsumowanie: PodsumowanieProjektu) -> str:
    """Buduje treść raportu końcowego jako zwykły tekst, bez tabel i ozdobników."""
    procent_limitu = _procent_wykorzystania_limitu(
        podsumowanie.liczba_zrodel_po_deduplikacji, podsumowanie.limit_zrodel
    )
    najwiekszy_plik = (
        f"{podsumowanie.najwiekszy_plik_nazwa}, {podsumowanie.najwiekszy_plik_bajtow} bajtów"
        if podsumowanie.najwiekszy_plik_nazwa is not None
        else "brak"
    )
    wiersze = [
        f"Raport końcowy projektu: {nazwa_projektu}",
        "",
        f"Liczba wejść: {podsumowanie.liczba_wejsc}",
        f"Liczba źródeł poprawnych: {podsumowanie.liczba_zrodel_poprawnych}",
        f"Liczba źródeł pominiętych: {podsumowanie.liczba_zrodel_pominietych}",
        f"Liczba źródeł z błędem: {podsumowanie.liczba_zrodel_blednych}",
        f"Liczba wykrytych duplikatów: {podsumowanie.liczba_duplikatow}",
        f"Liczba źródeł po deduplikacji: {podsumowanie.liczba_zrodel_po_deduplikacji}",
        f"Liczba plików TXT: {podsumowanie.liczba_plikow_txt}",
        f"Liczba plików MD: {podsumowanie.liczba_plikow_md}",
        f"Liczba plików PDF: {podsumowanie.liczba_plikow_pdf}",
        f"Wykorzystanie limitu źródeł: {procent_limitu} procent "
        f"(limit {podsumowanie.limit_zrodel})",
        f"Największy plik wynikowy: {najwiekszy_plik}",
        f"Łączna liczba słów w plikach wynikowych: {podsumowanie.laczna_liczba_slow}",
        f"Czas pracy: {_opis_czasu(podsumowanie.czas_pracy_sekundy)}",
    ]
    wiersze.extend(_wiersze_zrodel_nieprzetworzonych(podsumowanie.zrodla_nieprzetworzone))
    return "\n".join(wiersze) + "\n"


def _wiersze_zrodel_nieprzetworzonych(
    zrodla: tuple[ZrodloNieprzetworzone, ...],
) -> list[str]:
    """Buduje wykaz źródeł pominiętych i błędnych wraz z powodem, po jednym na akapit."""
    if not zrodla:
        return []
    wiersze = ["", "Źródła nieprzetworzone, liczba: " + str(len(zrodla)), ""]
    for zrodlo in zrodla:
        wiersze.append(f"Źródło: {zrodlo.pochodzenie}")
        wiersze.append(f"  Identyfikator: {zrodlo.identyfikator}")
        wiersze.append(f"  Status: {zrodlo.status}")
        wiersze.append(f"  Powód: {zrodlo.powod}")
        wiersze.append("")
    return wiersze[:-1]


def zapisz_raport(sciezka: Path, tresc: str) -> None:
    """Zapisuje raport obok manifestu, w UTF-8 z końcami wierszy LF."""
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    with sciezka.open("w", encoding="utf-8", newline="\n") as plik:
        plik.write(tresc)


def _procent_wykorzystania_limitu(liczba_zrodel: int, limit: int) -> int:
    if limit <= 0:
        return 0
    return round(liczba_zrodel * 100 / limit)


def _opis_czasu(sekundy: float) -> str:
    zaokraglone = round(sekundy)
    if zaokraglone < 60:
        return f"{zaokraglone} s"
    minuty, reszta = divmod(zaokraglone, 60)
    return f"{minuty} min {reszta} s"
