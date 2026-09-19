"""Odczyt pliku Guitar Pro i zbudowanie z niego opisu partytury.

Silnikiem odczytu jest biblioteka PyGuitarPro. Obsługiwane są wersje formatu
gp3, gp4 i gp5. Nowsze formaty gpx i gp, czyli wersje szósta i siódma programu
Guitar Pro, nie są obsługiwane; ich odrzucenie z czytelnym komunikatem
następuje wcześniej, w warstwie przyjmowania wejścia, zgodnie z sekcją
piętnastą CLAUDE.md.

PyGuitarPro sam wykrywa wersję pliku z jego nagłówka, więc ten moduł nie musi
rozpoznawać wersji po rozszerzeniu. Liczba taktów jest dokładna, bo pochodzi
z nagłówków taktów. Zmiana metrum między nagłówkami taktów kończy się
ostrzeżeniem.

Od etapu trzynastego moduł opisuje też same dźwięki: dla każdej ścieżki
strunowej, czyli takiej, która ma niepuste `track.strings` i nie jest ścieżką
perkusyjną, buduje takt po takcie zapis w postaci struna, próg, nazwa dźwięku
i wartość rytmiczna. Sekcja piętnasta CLAUDE.md zabrania zgadywania, która
ścieżka jest „tą basową” — ani nazwa ścieżki, ani numer instrumentu General
MIDI nie są tu wiarygodne — więc opisywane są wszystkie ścieżki strunowe, bez
wyboru jednej.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia
from gnb.music.instrumenty_gm import nazwa_instrumentu
from gnb.music.model import OpisPartytury, ZapisDzwiekowSciezki
from gnb.music.nuty_teoria import (
    litera_dzwieku_z_midi,
    nazwa_dzwieku_z_midi,
    nazwa_wartosci_rytmicznej,
)
from gnb.music.tonacje import nazwa_tonacji_z_kwint

METODA_ODCZYTU = "pyguitarpro"

KOMUNIKAT_BRAK_TONACJI = (
    "Plik nie zawiera oznaczenia tonacji. Wartość domyślna formatu Guitar Pro "
    "(zero krzyżyków, tryb durowy) jest nierozróżnialna od jej braku, więc "
    "zamiast zgadywać, czy utwór naprawdę jest w C-dur, wiersz tonacji został "
    "pominięty."
)

KOMUNIKAT_BRAK_BIBLIOTEKI = (
    "Nie znaleziono biblioteki PyGuitarPro, która czyta pliki Guitar Pro. "
    "Zainstaluj ją poleceniem „pip install gnb[nuty]”. Bez niej pliki gp3, gp4 "
    "i gp5 nie zostaną odczytane, a pozostałe formaty źródeł działają normalnie."
)
KOMUNIKAT_USZKODZONY = (
    "Pliku Guitar Pro nie dało się odczytać: jest uszkodzony albo zapisany "
    "w nieobsługiwanej odmianie formatu."
)


def czy_dostepna_biblioteka() -> bool:
    """Zwraca prawdę, gdy bibliotekę PyGuitarPro da się zaimportować."""
    try:
        import guitarpro  # noqa: F401
    except ImportError:
        return False
    return True


def przeczytaj_guitarpro(bajty: bytes, *, zapis_dzwiekow_wlaczony: bool = True) -> OpisPartytury:
    """Buduje `OpisPartytury` z bajtów pliku Guitar Pro w wersji gp3, gp4 albo gp5.

    Zgłasza `BrakNarzedzia`, gdy biblioteki PyGuitarPro nie ma, oraz `BladTrwaly`
    dla pliku uszkodzonego albo w nieobsługiwanej odmianie. Nie dokłada
    identyfikatora źródła — robi to adapter.

    Argument `zapis_dzwiekow_wlaczony` odpowiada kluczowi konfiguracji
    `nuty_zapis_dzwiekow_wlaczony`. Przy wartości fałsz opis wraca do zakresu
    sprzed etapu trzynastego: same metadane, bez dźwięków.
    """
    try:
        import guitarpro
    except ImportError as blad:
        raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI) from blad

    try:
        utwor = guitarpro.parse(io.BytesIO(bajty))
    except (guitarpro.GPException, OSError, EOFError, ValueError, IndexError) as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY) from blad

    tytul = (utwor.title or "").strip() or None
    tempo_bpm = int(utwor.tempo) if utwor.tempo else None

    naglowki = list(utwor.measureHeaders)
    liczba_taktow = len(naglowki) or None
    metrum = _metrum_naglowka(naglowki[0]) if naglowki else None

    tonacja, uwaga_tonacji = _tonacja_i_uwaga(utwor, naglowki)

    instrumenty: list[str] = []
    struktura_czesci: list[str] = []
    for numer, sciezka in enumerate(utwor.tracks, start=1):
        nazwa_sciezki = (sciezka.name or "").strip() or f"ścieżka {numer}"
        struktura_czesci.append(f"Ścieżka {numer}: {nazwa_sciezki}")
        nazwa_instrumentu_sciezki = nazwa_instrumentu(
            sciezka.channel.instrument, perkusja=sciezka.isPercussionTrack
        )
        if nazwa_instrumentu_sciezki not in instrumenty:
            instrumenty.append(nazwa_instrumentu_sciezki)

    ostrzezenia_zmian = _ostrzezenia_zmian(naglowki, metrum)

    zapis_dzwiekow: list[ZapisDzwiekowSciezki] = []
    if zapis_dzwiekow_wlaczony:
        zapis_dzwiekow, ostrzezenia_glosow = _zapisz_dzwieki_sciezek(utwor.tracks)
        ostrzezenia_zmian.extend(ostrzezenia_glosow)

    uwagi_odczytu: list[str] = []
    if getattr(utwor, "version", None):
        uwagi_odczytu.append(f"Wersja zapisu podana w pliku: {utwor.version}.")
    uwagi_odczytu.extend(uwaga_tonacji)

    return OpisPartytury(
        format_zrodlowy=_kod_formatu(utwor),
        metoda_odczytu=METODA_ODCZYTU,
        tytul=tytul,
        tonacja=tonacja,
        metrum=metrum,
        tempo_bpm=tempo_bpm,
        liczba_taktow=liczba_taktow,
        liczba_taktow_przyblizona=False,
        instrumenty=instrumenty,
        struktura_czesci=struktura_czesci,
        ostrzezenia_zmian=ostrzezenia_zmian,
        uwagi_odczytu=uwagi_odczytu,
        zapis_dzwiekow=zapis_dzwiekow,
    )


def _kod_formatu(utwor: object) -> str:
    """Zwraca kod formatu źródłowego w postaci „gp3”, „gp4” albo „gp5”."""
    krotka_wersji = getattr(utwor, "versionTuple", None)
    if krotka_wersji:
        return f"gp{krotka_wersji[0]}"
    return "gp5"


def _tonacja_i_uwaga(utwor: object, naglowki: list[object]) -> tuple[str | None, list[str]]:
    """Ustala tonację utworu i, gdy trzeba, uwagę tłumaczącą jej brak.

    Pole `Song.key` biblioteki PyGuitarPro jest dla każdej z trzech wersji
    formatu budowane z trybem wpisanym na sztywno jako durowy: sam plik Guitar
    Pro nie zapisuje trybu na poziomie całego utworu, tylko liczbę krzyżyków
    albo bemoli. Prawdziwy tryb, gdy plik go zapisuje, jest w nagłówku
    pierwszego taktu, więc stamtąd bierzemy tonację w pierwszej kolejności,
    a do `Song.key` sięgamy tylko wtedy, gdy w pliku nie ma żadnego taktu.
    `Song.key` i tak nigdy nie może dać trybu molowego — to jest znana,
    słabsza wartość, nie równorzędna alternatywa.

    Wartość domyślna, czyli zero krzyżyków i tryb durowy, jest nierozróżnialna
    od braku jakiegokolwiek oznaczenia tonacji w pliku — biblioteka zwraca tę
    samą wartość w obu przypadkach. Zamiast przedstawić to przypuszczenie jako
    fakt, funkcja zwraca `None` razem z uwagą wyjaśniającą dlaczego, zgodnie
    z sekcją dziesiątą CLAUDE.md o niedeklarowaniu stuprocentowej poprawności.
    """
    zrodlo = getattr(naglowki[0], "keySignature", None) if naglowki else getattr(utwor, "key", None)
    wartosc = getattr(zrodlo, "value", None)
    if not isinstance(wartosc, tuple) or len(wartosc) != 2:
        return None, []
    liczba_kwint, tryb = int(wartosc[0]), int(wartosc[1])
    if liczba_kwint == 0 and tryb == 0:
        return None, [KOMUNIKAT_BRAK_TONACJI]
    return nazwa_tonacji_z_kwint(liczba_kwint, moll=tryb == 1), []


def _metrum_naglowka(naglowek: object) -> str | None:
    """Zwraca metrum nagłówka taktu jako napis „licznik/mianownik” albo ``None``."""
    metrum = getattr(naglowek, "timeSignature", None)
    if metrum is None:
        return None
    licznik = getattr(metrum, "numerator", None)
    mianownik = getattr(getattr(metrum, "denominator", None), "value", None)
    if licznik is None or mianownik is None:
        return None
    return f"{licznik}/{mianownik}"


def _ostrzezenia_zmian(naglowki: list[object], pierwsze_metrum: str | None) -> list[str]:
    """Buduje ostrzeżenie, gdy metrum zmienia się między nagłówkami taktów."""
    metra = {metrum for naglowek in naglowki if (metrum := _metrum_naglowka(naglowek)) is not None}
    if len(metra) > 1:
        return [
            f"W tabulaturze zmienia się metrum ({len(metra)} różne wartości); "
            f"opis podaje metrum początkowe ({pierwsze_metrum})."
        ]
    return []


def _zapisz_dzwieki_sciezek(
    sciezki: Sequence[Any],
) -> tuple[list[ZapisDzwiekowSciezki], list[str]]:
    """Buduje zapis dźwięków każdej ścieżki strunowej pliku.

    Ścieżka kwalifikuje się, gdy ma niepustą listę strun i nie jest ścieżką
    perkusyjną. Żadna nie jest wybierana jako „ta basowa” — sekcja piętnasta
    CLAUDE.md zabrania zgadywania, a ani nazwa ścieżki, ani numer instrumentu
    General MIDI nie wskazują tego wiarygodnie, co potwierdziło zgłoszenie na
    pliku rzeczywistego repertuaru. Zwraca też ostrzeżenia dla ścieżek, których
    drugi głos (`voice`) niesie własne nuty pominięte w tym zapisie.

    Struktury PyGuitarPro nie mają opublikowanych adnotacji typów, więc
    elementy pochodzące z nich są tu typowane jako `Any` — dokładnie tak samo,
    jak zrobiono to już w `gnb/audio/transkrypcja.py` dla segmentów
    faster-whisper.
    """
    wyniki: list[ZapisDzwiekowSciezki] = []
    ostrzezenia: list[str] = []
    for numer, sciezka in enumerate(sciezki, start=1):
        struny = list(sciezka.strings)
        if not struny or sciezka.isPercussionTrack:
            continue
        nazwa_sciezki = (sciezka.name or "").strip() or f"ścieżka {numer}"
        wysokosci_strun = {struna.number: struna.value for struna in struny}
        etykiety = _etykiety_strun(struny)

        takty_surowe: list[str] = []
        ma_dodatkowy_glos = False
        for takt in sciezka.measures:
            takty_surowe.append(_takt_jako_tekst(takt, wysokosci_strun, etykiety))
            if _glos_drugi_ma_nuty(takt):
                ma_dodatkowy_glos = True
        if ma_dodatkowy_glos:
            ostrzezenia.append(
                f"Ścieżka „{nazwa_sciezki}” ma dodatkowy, niezależny głos z własnymi "
                "nutami, który nie jest opisany w zapisie dźwięków."
            )

        strojenie = tuple(
            nazwa_dzwieku_z_midi(struna.value) for struna in sorted(struny, key=lambda s: s.value)
        )
        wyniki.append(
            ZapisDzwiekowSciezki(
                nazwa_sciezki=nazwa_sciezki,
                strojenie=strojenie,
                takty=tuple(_zwin_powtorzenia(takty_surowe)),
            )
        )
    return wyniki, ostrzezenia


def _etykiety_strun(struny: Sequence[Any]) -> dict[int, str]:
    """Nazywa struny ścieżki samą literą, a oktawę dopisuje tylko przy kolizji liter.

    Kolizja jest sprawdzana w obrębie jednej ścieżki: gdy dwie struny tej samej
    ścieżki mają tę samą literę (na przykład strój obniżony), wszystkie struny
    tej ścieżki dostają oktawę, dla jednej, spójnej konwencji w obrębie całego
    jej zapisu — nie tylko struny, które akurat kolidują.
    """
    litery = {struna.number: litera_dzwieku_z_midi(struna.value) for struna in struny}
    if len(set(litery.values())) < len(litery):
        return {struna.number: nazwa_dzwieku_z_midi(struna.value) for struna in struny}
    return litery


def _takt_jako_tekst(takt: Any, wysokosci_strun: dict[int, int], etykiety: dict[int, str]) -> str:
    """Buduje treść jednego taktu: struna, próg, nazwa dźwięku, wartość rytmiczna."""
    glosy = takt.voices
    if not glosy:
        return ""
    fragmenty: list[str] = []
    for uderzenie in glosy[0].beats:
        rytm = _rytm_uderzenia(uderzenie)
        nuty = list(uderzenie.notes)
        if not nuty:
            fragmenty.append(f"pauza {rytm}")
            continue
        for nuta in sorted(nuty, key=lambda n: n.string):
            etykieta = etykiety[nuta.string]
            prog_opis = "pusta struna" if nuta.value == 0 else f"próg {nuta.value}"
            dzwiek = nazwa_dzwieku_z_midi(wysokosci_strun[nuta.string] + nuta.value)
            fragmenty.append(f"struna {etykieta}, {prog_opis}, {dzwiek}, {rytm}")
    return "; ".join(fragmenty)


def _rytm_uderzenia(uderzenie: Any) -> str:
    """Zwraca nazwę wartości rytmicznej jednego uderzenia, z kropką i podziałem nietypowym."""
    czas_trwania = uderzenie.duration
    nazwa = nazwa_wartosci_rytmicznej(czas_trwania.value, kropka=bool(czas_trwania.isDotted))
    tercola = czas_trwania.tuplet
    if tercola is not None and tercola.enters != tercola.times:
        nazwa = f"{nazwa} (podział {tercola.enters}:{tercola.times})"
    return nazwa


def _glos_drugi_ma_nuty(takt: Any) -> bool:
    """Zwraca prawdę, gdy drugi głos taktu (voice o indeksie 1) ma choć jedną nutę."""
    glosy = takt.voices
    if len(glosy) < 2:
        return False
    return any(uderzenie.notes for uderzenie in glosy[1].beats)


def _zwin_powtorzenia(tresc_taktow: Sequence[str]) -> list[str]:
    """Zwija bezpośrednio sąsiadujące, identyczne takty w jeden wiersz zbiorczy.

    Dwa takty są identyczne, gdy ich zbudowana treść tekstowa jest identyczna —
    ta sama sekwencja par struna-próg w tej samej kolejności oraz ta sama
    wartość rytmiczna każdego zdarzenia, łącznie z kropką i nietypowym
    podziałem. Takt o tej samej sekwencji strun i progów, ale innym rytmie,
    identyczny nie jest, bo różni się jego treść tekstowa. Zwijane są tylko
    takty bezpośrednio sąsiadujące — odległe powtórzenie w innym miejscu
    utworu zmuszałoby słuchacza czytnika ekranu do skoku pamięciowego wstecz,
    więc zostaje wypisane w całości ponownie.
    """
    wyniki: list[str] = []
    liczba = len(tresc_taktow)
    indeks = 0
    while indeks < liczba:
        start = indeks
        while indeks + 1 < liczba and tresc_taktow[indeks + 1] == tresc_taktow[start]:
            indeks += 1
        koniec = indeks
        wyniki.append(f"Takt {start + 1}: {tresc_taktow[start]}")
        if koniec == start + 1:
            wyniki.append(f"Takt {koniec + 1}: jak takt {start + 1}.")
        elif koniec > start + 1:
            wyniki.append(f"Takty {start + 2}-{koniec + 1}: jak takt {start + 1}.")
        indeks += 1
    return wyniki
