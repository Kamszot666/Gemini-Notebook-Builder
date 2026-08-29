"""Budowa i zapis manifestu projektu: ``manifest.json`` i ``manifest.txt``.

``manifest.json`` jest źródłem prawdy, ``manifest.txt`` jest z niego generowanym
widokiem czytelnym liniowo dla użytkownika, bez tabel i bez znaków ozdobnych.
Manifest zawiera po jednym wpisie na źródło i po jednym na plik wynikowy, wraz
z decyzją o wygenerowaniu wersji MD i jej uzasadnieniem. Wpis źródła niesie też
ostrzeżenia zgłoszone przez ekstraktor, na przykład informację o pliku PDF bez
warstwy tekstowej. Ostrzeżenie, które nie dociera do użytkownika, jest gorsze
niż jego brak, bo daje fałszywe poczucie, że utrata treści zostałaby zauważona.

Manifest jest budowany z pełnego stanu checkpointu, więc po wznowieniu pracy
opisuje wszystkie źródła projektu, a nie tylko te przetworzone w ostatnim
uruchomieniu.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WERSJA_SCHEMATU = 4


@dataclass(frozen=True, slots=True)
class WpisPobrania:
    """Dane odpowiedzi HTTP zapisywane w manifeście dla źródła pobranego ze strony."""

    adres_koncowy: str
    kod_odpowiedzi: int
    deklarowane_kodowanie: str
    etag: str | None
    last_modified: str | None
    z_pamieci_podrecznej: bool


@dataclass(frozen=True, slots=True)
class WpisZrodla:
    """Wiersz manifestu opisujący jedno źródło."""

    identyfikator: str
    typ: str
    pochodzenie: str
    checksum: str
    status: str
    duplikat: str | None
    decyzja_md: bool | None
    uzasadnienie_md: tuple[str, ...]
    pliki_wynikowe: tuple[str, ...]
    komunikat_bledu: str | None
    pobranie: WpisPobrania | None = None
    metadane: dict[str, str] = field(default_factory=dict)
    ocena_jakosci: str | None = None
    powody_oceny: tuple[str, ...] = ()
    ostrzezenia: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WpisDeduplikacji:
    """Audytowalna decyzja deduplikacji zapisana w manifeście.

    Odpowiada kontraktowi `gnb.core.model.DecyzjaDeduplikacji`. Pole zachowanych
    fragmentów unikalnych jest w schemacie, ale w zakresie etapu piątego zostaje
    puste, co wyjaśnia sekcja osiemnasta e CLAUDE.md.
    """

    identyfikator_zrodla_glownego: str
    identyfikator_duplikatu: str
    metoda: str
    wynik_podobienstwa: float
    decyzja: str
    uzasadnienie: str
    zachowane_fragmenty_unikalne: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WpisWyniku:
    """Wiersz manifestu opisujący jeden plik wynikowy.

    Pole `liczba_znakow_pliku` liczy zawartość pliku razem z końcowym znakiem
    nowej linii, w odróżnieniu od liczby znaków źródła, która liczy sam tekst
    dokumentu. Obie miary mają różne nazwy, bo mierzą co innego.
    """

    sciezka: str
    format: str
    liczba_zrodel: int
    liczba_slow: int
    liczba_znakow_pliku: int
    rozmiar_bajtow: int
    checksum: str
    status: str


@dataclass(frozen=True, slots=True)
class Manifest:
    """Pełny manifest projektu."""

    wersja_schematu: int
    identyfikator_projektu: str
    nazwa_projektu: str
    zrodla: tuple[WpisZrodla, ...]
    wyniki: tuple[WpisWyniku, ...]
    deduplikacja: tuple[WpisDeduplikacji, ...] = ()


def zapisz_manifest(sciezka_json: Path, sciezka_txt: Path, manifest: Manifest) -> None:
    """Zapisuje manifest w postaci JSON oraz w postaci tekstowej dla użytkownika."""
    sciezka_json.parent.mkdir(parents=True, exist_ok=True)
    with sciezka_json.open("w", encoding="utf-8", newline="\n") as plik:
        json.dump(_do_slownika(manifest), plik, ensure_ascii=False, indent=2)
        plik.write("\n")
    with sciezka_txt.open("w", encoding="utf-8", newline="\n") as plik:
        plik.write(zbuduj_widok_tekstowy(manifest))


def _do_slownika(manifest: Manifest) -> dict[str, Any]:
    return {
        "wersja_schematu": manifest.wersja_schematu,
        "identyfikator_projektu": manifest.identyfikator_projektu,
        "nazwa_projektu": manifest.nazwa_projektu,
        "zrodla": [
            {
                "identyfikator": wpis.identyfikator,
                "typ": wpis.typ,
                "pochodzenie": wpis.pochodzenie,
                "checksum": wpis.checksum,
                "status": wpis.status,
                "duplikat": wpis.duplikat,
                "decyzja_md": wpis.decyzja_md,
                "uzasadnienie_md": list(wpis.uzasadnienie_md),
                "pliki_wynikowe": list(wpis.pliki_wynikowe),
                "komunikat_bledu": wpis.komunikat_bledu,
                "pobranie": _pobranie_do_slownika(wpis.pobranie),
                "metadane": dict(wpis.metadane),
                "ocena_jakosci": wpis.ocena_jakosci,
                "powody_oceny": list(wpis.powody_oceny),
                "ostrzezenia": list(wpis.ostrzezenia),
            }
            for wpis in manifest.zrodla
        ],
        "wyniki": [
            {
                "sciezka": wpis.sciezka,
                "format": wpis.format,
                "liczba_zrodel": wpis.liczba_zrodel,
                "liczba_slow": wpis.liczba_slow,
                "liczba_znakow_pliku": wpis.liczba_znakow_pliku,
                "rozmiar_bajtow": wpis.rozmiar_bajtow,
                "checksum": wpis.checksum,
                "status": wpis.status,
            }
            for wpis in manifest.wyniki
        ],
        "deduplikacja": [
            {
                "identyfikator_zrodla_glownego": wpis.identyfikator_zrodla_glownego,
                "identyfikator_duplikatu": wpis.identyfikator_duplikatu,
                "metoda": wpis.metoda,
                "wynik_podobienstwa": wpis.wynik_podobienstwa,
                "decyzja": wpis.decyzja,
                "uzasadnienie": wpis.uzasadnienie,
                "zachowane_fragmenty_unikalne": list(wpis.zachowane_fragmenty_unikalne),
            }
            for wpis in manifest.deduplikacja
        ],
    }


def _pobranie_do_slownika(pobranie: WpisPobrania | None) -> dict[str, Any] | None:
    """Zamienia dane pobrania na słownik. Brak danych jest poprawny dla źródeł lokalnych."""
    if pobranie is None:
        return None
    return {
        "adres_koncowy": pobranie.adres_koncowy,
        "kod_odpowiedzi": pobranie.kod_odpowiedzi,
        "deklarowane_kodowanie": pobranie.deklarowane_kodowanie,
        "etag": pobranie.etag,
        "last_modified": pobranie.last_modified,
        "z_pamieci_podrecznej": pobranie.z_pamieci_podrecznej,
    }


def zbuduj_widok_tekstowy(manifest: Manifest) -> str:
    """Buduje czytelny liniowo tekst manifestu, bez tabel i znaków ozdobnych."""
    wiersze: list[str] = [
        f"Manifest projektu: {manifest.nazwa_projektu}",
        f"Identyfikator projektu: {manifest.identyfikator_projektu}",
        f"Wersja schematu manifestu: {manifest.wersja_schematu}",
        "Pełne sumy kontrolne są w pliku manifest.json.",
        "",
        f"Źródła, liczba: {len(manifest.zrodla)}",
        "",
    ]
    for wpis_zrodla in manifest.zrodla:
        wiersze.append(f"Źródło: {wpis_zrodla.identyfikator}")
        wiersze.append(f"  Typ: {wpis_zrodla.typ}")
        wiersze.append(f"  Pochodzenie: {wpis_zrodla.pochodzenie}")
        wiersze.append(f"  Suma kontrolna, skrót: {_skrocona_suma(wpis_zrodla.checksum)}")
        wiersze.append(f"  Status: {wpis_zrodla.status}")
        wiersze.append(f"  Duplikat: {wpis_zrodla.duplikat if wpis_zrodla.duplikat else 'nie'}")
        wiersze.append(f"  Wygenerowano wersję MD: {_opis_decyzji_md(wpis_zrodla.decyzja_md)}")
        if wpis_zrodla.uzasadnienie_md:
            wiersze.append("  Spełnione warunki reguły MD:")
            wiersze.extend(f"    - {warunek}" for warunek in wpis_zrodla.uzasadnienie_md)
        if wpis_zrodla.pliki_wynikowe:
            wiersze.append("  Pliki wynikowe:")
            wiersze.extend(f"    - {plik}" for plik in wpis_zrodla.pliki_wynikowe)
        if wpis_zrodla.pobranie is not None:
            wiersze.extend(_wiersze_pobrania(wpis_zrodla.pobranie))
        if wpis_zrodla.metadane:
            wiersze.append("  Metadane źródła:")
            wiersze.extend(
                f"    {nazwa}: {wartosc}" for nazwa, wartosc in sorted(wpis_zrodla.metadane.items())
            )
        if wpis_zrodla.ocena_jakosci:
            wiersze.append(f"  Ocena jakości ekstrakcji: {wpis_zrodla.ocena_jakosci}")
        if wpis_zrodla.powody_oceny:
            wiersze.append("  Powody oceny:")
            wiersze.extend(f"    - {powod}" for powod in wpis_zrodla.powody_oceny)
        if wpis_zrodla.ostrzezenia:
            wiersze.append("  Ostrzeżenia ekstrakcji:")
            wiersze.extend(f"    - {ostrzezenie}" for ostrzezenie in wpis_zrodla.ostrzezenia)
        if wpis_zrodla.komunikat_bledu:
            wiersze.append(f"  Komunikat błędu: {wpis_zrodla.komunikat_bledu}")
        wiersze.append("")

    wiersze.append(f"Pliki wynikowe, liczba: {len(manifest.wyniki)}")
    wiersze.append("")
    for wpis_wyniku in manifest.wyniki:
        wiersze.append(f"Plik wynikowy: {wpis_wyniku.sciezka}")
        wiersze.append(f"  Format: {wpis_wyniku.format}")
        wiersze.append(f"  Liczba źródeł: {wpis_wyniku.liczba_zrodel}")
        wiersze.append(f"  Liczba słów: {wpis_wyniku.liczba_slow}")
        wiersze.append(f"  Liczba znaków pliku: {wpis_wyniku.liczba_znakow_pliku}")
        wiersze.append(f"  Rozmiar w bajtach: {wpis_wyniku.rozmiar_bajtow}")
        wiersze.append(f"  Suma kontrolna, skrót: {_skrocona_suma(wpis_wyniku.checksum)}")
        wiersze.append(f"  Status: {wpis_wyniku.status}")
        wiersze.append("")

    wiersze.append(f"Decyzje deduplikacji, liczba: {len(manifest.deduplikacja)}")
    wiersze.append("")
    for wpis_dedup in manifest.deduplikacja:
        wiersze.append(f"Duplikat: {wpis_dedup.identyfikator_duplikatu}")
        wiersze.append(f"  Źródło główne: {wpis_dedup.identyfikator_zrodla_glownego}")
        wiersze.append(f"  Metoda: {wpis_dedup.metoda}")
        wiersze.append(f"  Podobieństwo: {wpis_dedup.wynik_podobienstwa:.2f}")
        wiersze.append(f"  Decyzja: {wpis_dedup.decyzja}")
        wiersze.append(f"  Uzasadnienie: {wpis_dedup.uzasadnienie}")
        if wpis_dedup.zachowane_fragmenty_unikalne:
            wiersze.append("  Zachowane fragmenty unikalne:")
            wiersze.extend(
                f"    - {fragment}" for fragment in wpis_dedup.zachowane_fragmenty_unikalne
            )
        wiersze.append("")

    return "\n".join(wiersze).rstrip("\n") + "\n"


def _wiersze_pobrania(pobranie: WpisPobrania) -> list[str]:
    """Buduje wiersze widoku tekstowego opisujące pobranie strony internetowej."""
    wiersze = [
        f"  Adres końcowy po przekierowaniach: {pobranie.adres_koncowy}",
        f"  Kod odpowiedzi HTTP: {pobranie.kod_odpowiedzi}",
        f"  Deklarowane kodowanie: {pobranie.deklarowane_kodowanie or 'nie podano'}",
        f"  Wzięte z pamięci podręcznej: {'tak' if pobranie.z_pamieci_podrecznej else 'nie'}",
    ]
    if pobranie.etag:
        wiersze.append(f"  ETag: {pobranie.etag}")
    if pobranie.last_modified:
        wiersze.append(f"  Last-Modified: {pobranie.last_modified}")
    return wiersze


def _opis_decyzji_md(decyzja: bool | None) -> str:
    if decyzja is None:
        return "nie dotyczy"
    return "tak" if decyzja else "nie"


def _skrocona_suma(suma: str) -> str:
    """Zwraca pierwsze szesnaście znaków sumy kontrolnej albo napis o jej braku.

    Pełny skrót jest nieczytelny przy odsłuchu syntezatorem mowy, więc widok
    tekstowy manifestu pokazuje tylko jego początek. Pełną wartość zawiera
    manifest.json.
    """
    return suma[:16] if suma else "brak"
