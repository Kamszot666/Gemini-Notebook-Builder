"""Checkpoint projektu z zapisem atomowym.

Jeden plik ``checkpoint.json`` na projekt, z numerem wersji schematu. Zapis
odbywa się do pliku tymczasowego w tym samym katalogu, a potem przez
``os.replace``, dzięki czemu plik docelowy nigdy nie jest częściowo zapisany.
Przed zastąpieniem poprzednia zawartość jest kopiowana do pliku z rozszerzeniem
``.bak`` — zachowywana jest jedna kopia zapasowa.

Checkpoint przechowuje stan każdego źródła, więc po restarcie da się wznowić
pracę bez powtarzania ukończonych etapów.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gnb.core.wyjatki import BladTrwaly

WERSJA_SCHEMATU = 2
_SUFIKS_TYMCZASOWY = ".tmp"
_SUFIKS_KOPII = ".bak"


@dataclass
class StanWyniku:
    """Zapisany w checkpoincie opis jednego pliku wynikowego źródła."""

    sciezka_wzgledna: str
    format: str
    liczba_slow: int
    liczba_znakow: int
    rozmiar_bajtow: int
    checksum: str


@dataclass
class StanPobrania:
    """Dane odpowiedzi HTTP zapamiętane dla źródła pobranego ze strony internetowej.

    Deklarowane kodowanie jest zapisywane celowo. Bez niego ponowna ekstrakcja
    z zachowanego pliku HTML dałaby nieczytelne znaki wszędzie tam, gdzie strona
    nie była w UTF-8.
    """

    adres_koncowy: str
    kod_odpowiedzi: int
    deklarowane_kodowanie: str
    etag: str | None = None
    last_modified: str | None = None
    z_pamieci_podrecznej: bool = False


@dataclass
class StanZrodla:
    """Zapisany w checkpoincie stan pojedynczego źródła."""

    identyfikator: str
    typ: str
    pochodzenie: str
    checksum: str
    format_zrodla: str
    status: str
    nazwa_bazowa_wyniku: str | None = None
    wyniki: list[StanWyniku] = field(default_factory=list)
    liczba_slow: int | None = None
    liczba_znakow: int | None = None
    decyzja_md: bool | None = None
    uzasadnienie_md: list[str] = field(default_factory=list)
    komunikat_bledu: str | None = None
    pobranie: StanPobrania | None = None


@dataclass
class Checkpoint:
    """Pełny stan projektu pozwalający wznowić pracę bez powtarzania etapów."""

    wersja_schematu: int
    identyfikator_projektu: str
    nazwa_projektu: str
    katalog_projektu: str
    konfiguracja: dict[str, str]
    czas_ostatniej_zmiany: str
    zrodla: dict[str, StanZrodla] = field(default_factory=dict)
    zakonczony: bool = False


def zapisz(sciezka: Path, checkpoint: Checkpoint) -> None:
    """Zapisuje checkpoint atomowo, zachowując jedną kopię zapasową.

    Dane trafiają najpierw do pliku tymczasowego w tym samym katalogu i są
    wypychane na dysk. Jeżeli plik docelowy już istnieje, jego zawartość jest
    kopiowana do pliku z rozszerzeniem ``.bak``. Dopiero potem plik tymczasowy
    zastępuje docelowy przez ``os.replace``.
    """
    sciezka.parent.mkdir(parents=True, exist_ok=True)
    tymczasowy = sciezka.with_name(sciezka.name + _SUFIKS_TYMCZASOWY)
    tresc = json.dumps(_checkpoint_do_slownika(checkpoint), ensure_ascii=False, indent=2)
    with tymczasowy.open("w", encoding="utf-8", newline="\n") as plik:
        plik.write(tresc)
        plik.flush()
        os.fsync(plik.fileno())
    if sciezka.exists():
        shutil.copy2(sciezka, sciezka.with_name(sciezka.name + _SUFIKS_KOPII))
    os.replace(tymczasowy, sciezka)


def wczytaj(sciezka: Path) -> Checkpoint | None:
    """Wczytuje checkpoint, a gdy plik główny jest uszkodzony, próbuje kopii zapasowej.

    Brak pliku checkpointu zwraca ``None`` i nie jest błędem. Uszkodzony plik
    główny bez sprawnej kopii zapasowej daje błąd trwały z czytelnym komunikatem.
    """
    if not sciezka.exists():
        return None
    try:
        return _checkpoint_ze_slownika(_wczytaj_json(sciezka))
    except (OSError, ValueError) as blad_glowny:
        kopia = sciezka.with_name(sciezka.name + _SUFIKS_KOPII)
        if not kopia.exists():
            raise BladTrwaly(
                f"Plik checkpointu {sciezka} jest uszkodzony i nie ma kopii zapasowej."
            ) from blad_glowny
        try:
            return _checkpoint_ze_slownika(_wczytaj_json(kopia))
        except (OSError, ValueError) as blad_kopii:
            raise BladTrwaly(
                f"Plik checkpointu {sciezka} oraz jego kopia zapasowa są uszkodzone."
            ) from blad_kopii


def _wczytaj_json(sciezka: Path) -> dict[str, Any]:
    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    if not isinstance(dane, dict):
        raise ValueError("Zawartość pliku checkpointu nie jest obiektem JSON.")
    return dane


def _checkpoint_do_slownika(checkpoint: Checkpoint) -> dict[str, Any]:
    return {
        "wersja_schematu": checkpoint.wersja_schematu,
        "identyfikator_projektu": checkpoint.identyfikator_projektu,
        "nazwa_projektu": checkpoint.nazwa_projektu,
        "katalog_projektu": checkpoint.katalog_projektu,
        "konfiguracja": dict(checkpoint.konfiguracja),
        "czas_ostatniej_zmiany": checkpoint.czas_ostatniej_zmiany,
        "zakonczony": checkpoint.zakonczony,
        "zrodla": {klucz: _stan_do_slownika(stan) for klucz, stan in checkpoint.zrodla.items()},
    }


def _stan_do_slownika(stan: StanZrodla) -> dict[str, Any]:
    return {
        "identyfikator": stan.identyfikator,
        "typ": stan.typ,
        "pochodzenie": stan.pochodzenie,
        "checksum": stan.checksum,
        "format_zrodla": stan.format_zrodla,
        "status": stan.status,
        "nazwa_bazowa_wyniku": stan.nazwa_bazowa_wyniku,
        "wyniki": [_wynik_do_slownika(wynik) for wynik in stan.wyniki],
        "liczba_slow": stan.liczba_slow,
        "liczba_znakow": stan.liczba_znakow,
        "decyzja_md": stan.decyzja_md,
        "uzasadnienie_md": list(stan.uzasadnienie_md),
        "komunikat_bledu": stan.komunikat_bledu,
        "pobranie": _pobranie_do_slownika(stan.pobranie),
    }


def _pobranie_do_slownika(pobranie: StanPobrania | None) -> dict[str, Any] | None:
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


def _wynik_do_slownika(wynik: StanWyniku) -> dict[str, Any]:
    return {
        "sciezka_wzgledna": wynik.sciezka_wzgledna,
        "format": wynik.format,
        "liczba_slow": wynik.liczba_slow,
        "liczba_znakow": wynik.liczba_znakow,
        "rozmiar_bajtow": wynik.rozmiar_bajtow,
        "checksum": wynik.checksum,
    }


def _checkpoint_ze_slownika(dane: dict[str, Any]) -> Checkpoint:
    surowe_zrodla = dane.get("zrodla", {})
    if not isinstance(surowe_zrodla, dict):
        raise ValueError("Pole „zrodla” w checkpoincie ma niepoprawny typ.")
    zrodla = {str(klucz): _stan_ze_slownika(wartosc) for klucz, wartosc in surowe_zrodla.items()}
    surowa_konfiguracja = dane.get("konfiguracja", {})
    if not isinstance(surowa_konfiguracja, dict):
        raise ValueError("Pole „konfiguracja” w checkpoincie ma niepoprawny typ.")
    return Checkpoint(
        wersja_schematu=int(dane["wersja_schematu"]),
        identyfikator_projektu=str(dane["identyfikator_projektu"]),
        nazwa_projektu=str(dane["nazwa_projektu"]),
        katalog_projektu=str(dane["katalog_projektu"]),
        konfiguracja={str(k): str(v) for k, v in surowa_konfiguracja.items()},
        czas_ostatniej_zmiany=str(dane["czas_ostatniej_zmiany"]),
        zrodla=zrodla,
        zakonczony=bool(dane.get("zakonczony", False)),
    )


def _stan_ze_slownika(dane: Any) -> StanZrodla:
    if not isinstance(dane, dict):
        raise ValueError("Wpis źródła w checkpoincie nie jest obiektem JSON.")
    return StanZrodla(
        identyfikator=str(dane["identyfikator"]),
        typ=str(dane["typ"]),
        pochodzenie=str(dane["pochodzenie"]),
        checksum=str(dane["checksum"]),
        format_zrodla=str(dane["format_zrodla"]),
        status=str(dane["status"]),
        nazwa_bazowa_wyniku=_opcjonalny_tekst(dane.get("nazwa_bazowa_wyniku")),
        wyniki=[_wynik_ze_slownika(element) for element in dane.get("wyniki", [])],
        liczba_slow=_opcjonalna_liczba(dane.get("liczba_slow")),
        liczba_znakow=_opcjonalna_liczba(dane.get("liczba_znakow")),
        decyzja_md=_opcjonalna_wartosc_logiczna(dane.get("decyzja_md")),
        uzasadnienie_md=[str(element) for element in dane.get("uzasadnienie_md", [])],
        komunikat_bledu=_opcjonalny_tekst(dane.get("komunikat_bledu")),
        pobranie=_pobranie_ze_slownika(dane.get("pobranie")),
    )


def _pobranie_ze_slownika(dane: Any) -> StanPobrania | None:
    """Odczytuje dane pobrania. Ich brak jest poprawny, bo mają je tylko źródła sieciowe."""
    if dane is None:
        return None
    if not isinstance(dane, dict):
        raise ValueError("Wpis pobrania w checkpoincie nie jest obiektem JSON.")
    return StanPobrania(
        adres_koncowy=str(dane["adres_koncowy"]),
        kod_odpowiedzi=int(dane["kod_odpowiedzi"]),
        deklarowane_kodowanie=str(dane.get("deklarowane_kodowanie", "")),
        etag=_opcjonalny_tekst(dane.get("etag")),
        last_modified=_opcjonalny_tekst(dane.get("last_modified")),
        z_pamieci_podrecznej=bool(dane.get("z_pamieci_podrecznej", False)),
    )


def _wynik_ze_slownika(dane: Any) -> StanWyniku:
    if not isinstance(dane, dict):
        raise ValueError("Wpis wyniku w checkpoincie nie jest obiektem JSON.")
    return StanWyniku(
        sciezka_wzgledna=str(dane["sciezka_wzgledna"]),
        format=str(dane["format"]),
        liczba_slow=int(dane["liczba_slow"]),
        liczba_znakow=int(dane["liczba_znakow"]),
        rozmiar_bajtow=int(dane["rozmiar_bajtow"]),
        checksum=str(dane["checksum"]),
    )


def _opcjonalny_tekst(wartosc: Any) -> str | None:
    return None if wartosc is None else str(wartosc)


def _opcjonalna_liczba(wartosc: Any) -> int | None:
    return None if wartosc is None else int(wartosc)


def _opcjonalna_wartosc_logiczna(wartosc: Any) -> bool | None:
    return None if wartosc is None else bool(wartosc)
