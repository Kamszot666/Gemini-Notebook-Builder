"""Checkpoint projektu z zapisem atomowym.

Jeden plik ``checkpoint.json`` na projekt, z numerem wersji schematu. Zapis
odbywa się do pliku tymczasowego w tym samym katalogu, a potem przez
``os.replace``, dzięki czemu plik docelowy nigdy nie jest częściowo zapisany.
Przed zastąpieniem poprzednia zawartość jest kopiowana do pliku z rozszerzeniem
``.bak`` — zachowywana jest jedna kopia zapasowa.

Checkpoint przechowuje stan każdego źródła, więc po restarcie da się wznowić
pracę bez powtarzania ukończonych etapów.

Odczyt rozgałęzia się po numerze wersji schematu. Plik zapisany starszą wersją
aplikacji jest migrowany do postaci bieżącej, zanim powstaną z niego obiekty,
więc katalog projektu założony poprzednią wersją nadal daje się wznowić. Plik
w wersji nowszej niż obsługiwana kończy się błędem trwałym z komunikatem po
polsku, ponieważ starsza aplikacja nie ma jak odgadnąć znaczenia pól, których
jeszcze nie zna.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gnb.core.wyjatki import BladTrwaly

WERSJA_SCHEMATU = 4
NAJSTARSZA_OBSLUGIWANA_WERSJA = 1
_SUFIKS_TYMCZASOWY = ".tmp"
_SUFIKS_KOPII = ".bak"

KOMUNIKAT_NOWSZA_WERSJA = (
    "Plik checkpointu pochodzi z nowszej wersji aplikacji: zapisano go w wersji "
    "schematu {znaleziona}, a ta wersja aplikacji obsługuje najwyżej {obslugiwana}. "
    "Zaktualizuj aplikację albo utwórz nowy projekt pod inną nazwą."
)


@dataclass
class StanWyniku:
    """Zapisany w checkpoincie opis jednego pliku wynikowego źródła.

    Pole `liczba_znakow_pliku` liczy zawartość zapisanego pliku, więc obejmuje
    też końcowy znak nowej linii. Liczba znaków źródła, zapisana przy wpisie
    źródła, liczy sam tekst dokumentu i jest zawsze o ten jeden znak mniejsza.
    Dwie różne miary noszą różne nazwy, żeby nie dało się ich pomylić.
    """

    sciezka_wzgledna: str
    format: str
    liczba_slow: int
    liczba_znakow_pliku: int
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
    """Zapisany w checkpoincie stan pojedynczego źródła.

    Pole `naglowek_metadanych` niesie gotowy nagłówek pliku wynikowego zbudowany
    na etapie normalizacji. Jest zapisywany, bo zawiera datę importu w czasie
    lokalnym i po wznowieniu pracy nie dałoby się go odtworzyć identycznie. Pole
    `duplikat_glowny` jest ustawiane dla źródła uznanego za duplikat innego i
    wskazuje identyfikator źródła zachowanego.
    """

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
    metadane: dict[str, str] = field(default_factory=dict)
    ocena_jakosci: str | None = None
    powody_oceny: list[str] = field(default_factory=list)
    ostrzezenia: list[str] = field(default_factory=list)
    naglowek_metadanych: str | None = None
    duplikat_glowny: str | None = None


@dataclass
class DecyzjaDeduplikacjiZapis:
    """Audytowalna decyzja deduplikacji zapisana w checkpoincie.

    Odpowiada kontraktowi `gnb.core.model.DecyzjaDeduplikacji`. Pole zachowanych
    fragmentów unikalnych jest przewidziane w schemacie, ale w zakresie etapu
    piątego pozostaje puste, co wyjaśnia sekcja osiemnasta e CLAUDE.md.
    """

    identyfikator_zrodla_glownego: str
    identyfikator_duplikatu: str
    metoda: str
    wynik_podobienstwa: float
    decyzja: str
    uzasadnienie: str
    zachowane_fragmenty_unikalne: list[str] = field(default_factory=list)


@dataclass
class StanDeduplikacji:
    """Stan etapu deduplikacji projektu.

    `wykonana` pozwala pominąć powtórne porównanie po wznowieniu pracy, gdy
    przerwanie nastąpiło już po deduplikacji, a przed zapisem plików wynikowych.
    """

    wykonana: bool = False
    decyzje: list[DecyzjaDeduplikacjiZapis] = field(default_factory=list)


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
    deduplikacja: StanDeduplikacji = field(default_factory=StanDeduplikacji)


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

    Plik zapisany starszą wersją schematu jest migrowany przed budową obiektów,
    więc wznawia się normalnie. Brak spodziewanego pola po migracji oznacza plik
    naprawdę uszkodzony i również kończy się błędem trwałym, nigdy surowym
    śladem stosu. Plik w wersji nowszej niż obsługiwana daje błąd trwały od razu,
    bez sięgania po kopię zapasową, ponieważ kopia jest z tej samej wersji.
    """
    if not sciezka.exists():
        return None
    try:
        return _checkpoint_ze_slownika(_wczytaj_json(sciezka))
    except _BLEDY_ODCZYTU as blad_glowny:
        kopia = sciezka.with_name(sciezka.name + _SUFIKS_KOPII)
        if not kopia.exists():
            raise BladTrwaly(
                f"Plik checkpointu {sciezka} jest uszkodzony i nie ma kopii zapasowej. "
                f"Przyczyna: {_opis_przyczyny(blad_glowny)}"
            ) from blad_glowny
        try:
            return _checkpoint_ze_slownika(_wczytaj_json(kopia))
        except _BLEDY_ODCZYTU as blad_kopii:
            raise BladTrwaly(
                f"Plik checkpointu {sciezka} oraz jego kopia zapasowa są uszkodzone. "
                f"Przyczyna: {_opis_przyczyny(blad_kopii)}"
            ) from blad_kopii


# Wyjątki odczytu, po których warto sięgnąć po kopię zapasową. Brak klucza oraz
# niewłaściwy typ pola są tu razem z błędem składni JSON, ponieważ wszystkie
# trzy znaczą to samo: zawartość pliku nie odpowiada schematowi. Bez nich
# uszkodzony plik kończył się surowym śladem stosu zamiast polskiego komunikatu.
_BLEDY_ODCZYTU = (OSError, ValueError, KeyError, TypeError)


def _opis_przyczyny(blad: Exception) -> str:
    """Opisuje po polsku, co było nie tak z zawartością pliku checkpointu."""
    if isinstance(blad, KeyError):
        return f"brak spodziewanego pola {blad.args[0]!r}."
    if isinstance(blad, OSError):
        return "pliku nie dało się odczytać z dysku."
    return f"{blad}"


def _wczytaj_json(sciezka: Path) -> dict[str, Any]:
    dane = json.loads(sciezka.read_text(encoding="utf-8"))
    if not isinstance(dane, dict):
        raise ValueError("Zawartość pliku checkpointu nie jest obiektem JSON.")
    return dane


def _zmigruj(dane: dict[str, Any]) -> dict[str, Any]:
    """Doprowadza dane wczytane z pliku do postaci bieżącej wersji schematu.

    Migracja jest wykonywana krok po kroku, po jednym przejściu na wersję, i
    zawsze przed budową obiektów. Dzięki temu odczyt starszego pliku kończy się
    wznowieniem projektu, a nie błędem braku pola.
    """
    wersja = _wersja_schematu(dane)
    if wersja > WERSJA_SCHEMATU:
        raise BladTrwaly(
            KOMUNIKAT_NOWSZA_WERSJA.format(znaleziona=wersja, obslugiwana=WERSJA_SCHEMATU)
        )
    if wersja < NAJSTARSZA_OBSLUGIWANA_WERSJA:
        raise ValueError(f"Numer wersji schematu checkpointu jest nieprawidłowy: {wersja}.")

    while wersja < WERSJA_SCHEMATU:
        dane = _MIGRACJE[wersja](dane)
        wersja += 1
        dane["wersja_schematu"] = wersja
    return dane


def _wersja_schematu(dane: dict[str, Any]) -> int:
    """Zwraca numer wersji schematu zapisany w pliku.

    Brak numeru albo numer, który nie jest liczbą, oznacza plik uszkodzony, a nie
    plik starszej wersji, więc kończy się błędem wartości. Dzięki temu odczyt
    sięgnie po kopię zapasową, zamiast zgadywać, jaką postać ma zawartość.
    """
    surowa = dane.get("wersja_schematu")
    if isinstance(surowa, bool) or not isinstance(surowa, int | str):
        raise ValueError("Plik checkpointu nie zawiera numeru wersji schematu.")
    try:
        return int(surowa)
    except ValueError as blad:
        raise ValueError(
            f"Numer wersji schematu checkpointu nie jest liczbą: {surowa!r}."
        ) from blad


def _z_wersji_1_na_2(dane: dict[str, Any]) -> dict[str, Any]:
    """Przechodzi z wersji 1 na 2. Wersja 2 dodała pole ``pobranie`` przy źródle.

    Pole zostało dodane z bezpieczną wartością domyślną i jest odczytywane przez
    ``get``, więc plik wersji 1 wczytuje się poprawnie bez przenoszenia danych.
    Krok istnieje po to, żeby ciąg wersji był pełny i widoczny wprost w kodzie.
    """
    return dane


def _z_wersji_2_na_3(dane: dict[str, Any]) -> dict[str, Any]:
    """Przechodzi z wersji 2 na 3. Wersja 3 dodała pole ``metadane`` przy źródle.

    Tak samo jak przy poprzednim kroku, jest to zmiana wyłącznie dodająca pole
    z bezpieczną wartością domyślną, więc dane nie wymagają przekształcenia.
    """
    return dane


def _z_wersji_3_na_4(dane: dict[str, Any]) -> dict[str, Any]:
    """Przechodzi z wersji 3 na 4, zmieniając nazwę pola liczby znaków pliku wynikowego.

    W wersji 3 pole opisujące plik wynikowy nosiło nazwę ``liczba_znakow``, taką
    samą jak pole opisujące dokument źródłowy, mimo że obie miary liczą co innego.
    W wersji 4 pole pliku nazywa się ``liczba_znakow_pliku``.

    Migracja jest wyłącznie przeniesieniem klucza wewnątrz wpisu wyniku, bez
    żadnego przeliczania. Wartości nie wolno wyprowadzać z pola ``liczba_znakow``
    zapisanego przy źródle, ponieważ tamto pole liczy tekst dokumentu, a nie plik,
    a przy źródle z wersją TXT i wersją MD naraz obydwa pliki dostałyby tę samą
    błędną liczbę.
    """
    for stan in _wpisy_zrodel(dane):
        wyniki = stan.get("wyniki")
        if not isinstance(wyniki, list):
            continue
        for wynik in wyniki:
            if not isinstance(wynik, dict):
                continue
            if "liczba_znakow" in wynik and "liczba_znakow_pliku" not in wynik:
                wynik["liczba_znakow_pliku"] = wynik.pop("liczba_znakow")
    return dane


def _wpisy_zrodel(dane: dict[str, Any]) -> list[dict[str, Any]]:
    """Zwraca wpisy źródeł nadające się do przekształcenia przez migrację.

    Wpisy o nieoczekiwanym kształcie są pomijane, ponieważ ich sprawdzeniem
    zajmuje się właściwy odczyt, który zgłosi czytelny błąd. Migracja nie jest
    miejscem na walidację.
    """
    zrodla = dane.get("zrodla")
    if not isinstance(zrodla, dict):
        return []
    return [stan for stan in zrodla.values() if isinstance(stan, dict)]


# Kolejne przejścia między wersjami schematu. Klucz to wersja, z której krok
# wychodzi. Rozgałęzienie po numerze wersji jest tu jedynym powodem, dla którego
# numer w pliku ma znaczenie: numer wczytany i z niczym nieporównany byłby ozdobą.
_MIGRACJE: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _z_wersji_1_na_2,
    2: _z_wersji_2_na_3,
    3: _z_wersji_3_na_4,
}


def _checkpoint_do_slownika(checkpoint: Checkpoint) -> dict[str, Any]:
    return {
        "wersja_schematu": checkpoint.wersja_schematu,
        "identyfikator_projektu": checkpoint.identyfikator_projektu,
        "nazwa_projektu": checkpoint.nazwa_projektu,
        "katalog_projektu": checkpoint.katalog_projektu,
        "konfiguracja": dict(checkpoint.konfiguracja),
        "czas_ostatniej_zmiany": checkpoint.czas_ostatniej_zmiany,
        "zakonczony": checkpoint.zakonczony,
        "deduplikacja": _deduplikacja_do_slownika(checkpoint.deduplikacja),
        "zrodla": {klucz: _stan_do_slownika(stan) for klucz, stan in checkpoint.zrodla.items()},
    }


def _deduplikacja_do_slownika(stan: StanDeduplikacji) -> dict[str, Any]:
    return {
        "wykonana": stan.wykonana,
        "decyzje": [
            {
                "identyfikator_zrodla_glownego": decyzja.identyfikator_zrodla_glownego,
                "identyfikator_duplikatu": decyzja.identyfikator_duplikatu,
                "metoda": decyzja.metoda,
                "wynik_podobienstwa": decyzja.wynik_podobienstwa,
                "decyzja": decyzja.decyzja,
                "uzasadnienie": decyzja.uzasadnienie,
                "zachowane_fragmenty_unikalne": list(decyzja.zachowane_fragmenty_unikalne),
            }
            for decyzja in stan.decyzje
        ],
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
        "metadane": dict(stan.metadane),
        "ocena_jakosci": stan.ocena_jakosci,
        "powody_oceny": list(stan.powody_oceny),
        "ostrzezenia": list(stan.ostrzezenia),
        "naglowek_metadanych": stan.naglowek_metadanych,
        "duplikat_glowny": stan.duplikat_glowny,
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
        "liczba_znakow_pliku": wynik.liczba_znakow_pliku,
        "rozmiar_bajtow": wynik.rozmiar_bajtow,
        "checksum": wynik.checksum,
    }


def _checkpoint_ze_slownika(dane: dict[str, Any]) -> Checkpoint:
    # Migracja wykonuje się przed jakąkolwiek budową obiektu, żeby wpis zapisany
    # starszą wersją aplikacji miał już komplet pól, gdy dojdzie do jego odczytu.
    dane = _zmigruj(dane)
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
        deduplikacja=_deduplikacja_ze_slownika(dane.get("deduplikacja")),
    )


def _deduplikacja_ze_slownika(dane: Any) -> StanDeduplikacji:
    """Odczytuje stan deduplikacji. Jego brak jest poprawny dla starszych plików.

    Pole zostało dodane w etapie piątym z pustą wartością domyślną, więc plik
    zapisany wcześniejszą wersją aplikacji wczytuje się bez zmian w schemacie.
    """
    if not isinstance(dane, dict):
        return StanDeduplikacji()
    surowe_decyzje = dane.get("decyzje", [])
    decyzje = [
        _decyzja_deduplikacji_ze_slownika(element)
        for element in surowe_decyzje
        if isinstance(element, dict)
    ]
    return StanDeduplikacji(wykonana=bool(dane.get("wykonana", False)), decyzje=decyzje)


def _decyzja_deduplikacji_ze_slownika(dane: dict[str, Any]) -> DecyzjaDeduplikacjiZapis:
    return DecyzjaDeduplikacjiZapis(
        identyfikator_zrodla_glownego=str(dane["identyfikator_zrodla_glownego"]),
        identyfikator_duplikatu=str(dane["identyfikator_duplikatu"]),
        metoda=str(dane["metoda"]),
        wynik_podobienstwa=float(dane["wynik_podobienstwa"]),
        decyzja=str(dane["decyzja"]),
        uzasadnienie=str(dane["uzasadnienie"]),
        zachowane_fragmenty_unikalne=[
            str(element) for element in dane.get("zachowane_fragmenty_unikalne", [])
        ],
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
        metadane=_metadane_ze_slownika(dane.get("metadane")),
        ocena_jakosci=_opcjonalny_tekst(dane.get("ocena_jakosci")),
        powody_oceny=[str(element) for element in dane.get("powody_oceny", [])],
        ostrzezenia=[str(element) for element in dane.get("ostrzezenia", [])],
        naglowek_metadanych=_opcjonalny_tekst(dane.get("naglowek_metadanych")),
        duplikat_glowny=_opcjonalny_tekst(dane.get("duplikat_glowny")),
    )


def _metadane_ze_slownika(dane: Any) -> dict[str, str]:
    """Odczytuje metadane źródła. Ich brak jest poprawny dla źródeł bez metadanych."""
    if not isinstance(dane, dict):
        return {}
    return {str(klucz): str(wartosc) for klucz, wartosc in dane.items()}


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
        liczba_znakow_pliku=int(dane["liczba_znakow_pliku"]),
        rozmiar_bajtow=int(dane["rozmiar_bajtow"]),
        checksum=str(dane["checksum"]),
    )


def _opcjonalny_tekst(wartosc: Any) -> str | None:
    return None if wartosc is None else str(wartosc)


def _opcjonalna_liczba(wartosc: Any) -> int | None:
    return None if wartosc is None else int(wartosc)


def _opcjonalna_wartosc_logiczna(wartosc: Any) -> bool | None:
    return None if wartosc is None else bool(wartosc)
