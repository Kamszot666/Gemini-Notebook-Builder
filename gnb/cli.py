"""Wiersz poleceń aplikacji Gemini Notebook Builder.

Udostępnia trzy polecenia. Polecenie ``diagnostyka`` sprawdza dostępność
narzędzi zewnętrznych wymienionych w sekcji piątej CLAUDE.md. Polecenie
``przetworz`` uruchamia potok przetwarzania dla tekstu wklejonego, plików
lokalnych w formacie TXT, MD, HTML, CSV, SRT, VTT, PDF, DOCX, EPUB, obrazów,
nagrań mowy, adresów stron internetowych oraz adresów filmów z serwisu YouTube,
dla których pobierane są napisy. Polecenie ``pamiec`` pokazuje stan wspólnej
pamięci podręcznej pobranych stron i pozwala ją wyczyścić.

Przed pobraniem czegokolwiek polecenie ``przetworz`` wypisuje podsumowanie listy
adresów: ile jest poprawnych, ile duplikatów i ile wpisów odrzucono wraz
z powodem. Opcja ``--sprawdz-liste`` kończy pracę zaraz po tym podsumowaniu,
bez pobierania.

Wyjście jest czytelne liniowo dla czytnika ekranu, bez pasków postępu i bez
znaków sterujących przerysowujących wiersz.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja, wczytaj_konfiguracje
from gnb.core.postep import FazaPotoku, WywolanieZwrotnePostepu, ZdarzeniePostepu
from gnb.core.wyjatki import BladGnb
from gnb.ingestion.lista_url import (
    PodsumowanieListyUrl,
    opis_podsumowania,
    wczytaj_liste_z_pliku,
    zbierz_adresy,
)
from gnb.ingestion.wejscie import (
    PozycjaWejsciowa,
    przyjmij_plik,
    przyjmij_tekst,
    przyjmij_url,
)
from gnb.persistence.cache import otworz, wyczysc_pamiec_podreczna
from gnb.potok import przetworz_projekt

KOD_BRAK_ZRODEL = 2
KOD_BLAD = 1

# Najkrótszy odstęp między wierszami postępu w wierszu poleceń. Dławienie
# istnieje z tego samego powodu co w interfejsie WWW: potok zgłasza postęp po
# każdej stronie skanu i po każdym segmencie transkrypcji, a wypisanie każdego
# z nich zalałoby wyjście.
_ODSTEP_POSTEPU_CLI_SEKUNDY = 3.0

# Fazy potoku, których postęp jest wypisywany w wierszu poleceń: OCR skanu oraz
# transkrypcja nagrania. To jedyne etapy, które potrafią trwać kilkanaście minut
# albo dłużej bez żadnego znaku życia.
_FAZY_POSTEPU_CLI = frozenset({FazaPotoku.OCR, FazaPotoku.TRANSKRYPCJA})


def _postep_wiersza_polecen() -> WywolanieZwrotnePostepu:
    """Buduje dławione wypisywanie postępu długich etapów dla wiersza poleceń.

    Wypisywane są wyłącznie zdarzenia faz OCR i transkrypcji, bo to jedyne etapy,
    które potrafią trwać kilkanaście minut albo dłużej bez żadnego znaku życia.
    Wiersze są zwykłym tekstem, bez pasków postępu i bez znaków sterujących
    przerysowujących wiersz, zgodnie z sekcją piątą CLAUDE.md.
    """
    stan = {"czas": 0.0}

    def zglos(zdarzenie: ZdarzeniePostepu) -> None:
        if zdarzenie.faza not in _FAZY_POSTEPU_CLI:
            return
        teraz = time.monotonic()
        ostatni = zdarzenie.wykonano == zdarzenie.wszystkich
        if ostatni or teraz - stan["czas"] >= _ODSTEP_POSTEPU_CLI_SEKUNDY:
            print(zdarzenie.opis)
            stan["czas"] = teraz

    return zglos


@dataclass(frozen=True, slots=True)
class Narzedzie:
    """Opis jednego narzędzia zewnętrznego sprawdzanego przez diagnostykę.

    Pole `polecenia` przyjmuje więcej niż jedną nazwę pliku wykonywalnego,
    bo na przykład MuseScore na Windows nie nazywa się `mscore`, tylko
    `MuseScore4.exe` albo `MuseScore3.exe`, zgodnie z pułapką opisaną
    w sekcji piętnastej CLAUDE.md.
    """

    nazwa: str
    polecenia: tuple[str, ...]
    argument_wersji: str
    do_czego_sluzy: str
    co_przestanie_dzialac: str


NARZEDZIA: tuple[Narzedzie, ...] = (
    Narzedzie(
        nazwa="FFmpeg",
        polecenia=("ffmpeg",),
        argument_wersji="-version",
        do_czego_sluzy=(
            "rozkodowanie każdego nagrania audio do fali dźwiękowej przed transkrypcją; "
            "ścieżka audio używa wyłącznie FFmpega, nie dekodera wbudowanego w faster-whisper"
        ),
        co_przestanie_dzialac="całe przetwarzanie i transkrypcja nagrań mowy",
    ),
    Narzedzie(
        nazwa="Tesseract",
        polecenia=("tesseract",),
        argument_wersji="--version",
        do_czego_sluzy="rozpoznawanie tekstu na skanach i obrazach",
        co_przestanie_dzialac="OCR obrazów i skanowanych plików PDF",
    ),
    Narzedzie(
        nazwa="LibreOffice",
        polecenia=("soffice",),
        argument_wersji="--version",
        do_czego_sluzy="konwersja plików ODT oraz część obsługi PPTX",
        co_przestanie_dzialac="import plików w formacie ODT",
    ),
    Narzedzie(
        nazwa="MuseScore",
        polecenia=("mscore", "MuseScore4.exe", "MuseScore3.exe"),
        argument_wersji="--version",
        do_czego_sluzy="konwersja plików MIDI i MusicXML na PDF oraz odczyt tonacji i metrum",
        co_przestanie_dzialac="konwersja materiałów nutowych przez wiersz poleceń",
    ),
    Narzedzie(
        nazwa="Java",
        polecenia=("java",),
        argument_wersji="-version",
        do_czego_sluzy="uruchamianie Audiveris, czyli rozpoznawania nut ze skanów i zdjęć",
        co_przestanie_dzialac="rozpoznawanie notacji muzycznej z obrazów i plików PDF",
    ),
)


def _znajdz_wersje(sciezka_programu: str, argument: str) -> str | None:
    """Zwraca pierwszy wiersz wyjścia polecenia sprawdzającego wersję, jeżeli się uda.

    Przyjmuje pełną ścieżkę znalezioną wcześniej przez `shutil.which`, a nie
    samą nazwę polecenia. Windows potrafi mieć w tym samym katalogu zarówno
    wariant konsolowy, jak i graficzny tego samego programu — tak jest
    w przypadku LibreOffice, gdzie `soffice.com` zwraca się natychmiast,
    a `soffice.exe` otwiera okno i blokuje proces aż do przekroczenia
    limitu czasu. Podanie gołej nazwy `soffice` bez rozszerzenia pozostawia
    Windows wybór, który z nich uruchomić, i bywa to wybór graficzny, dlatego
    używana jest tu dokładnie ta ścieżka, którą wcześniej znalazł
    `shutil.which`.

    Niektóre narzędzia, na przykład Java, wypisują wersję na standardowe
    wyjście błędu zamiast na standardowe wyjście, dlatego sprawdzane jest
    jedno i drugie.
    """

    try:
        wynik = subprocess.run(
            [sciezka_programu, argument],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    tekst = (wynik.stdout or wynik.stderr).strip()
    if not tekst:
        return None
    return tekst.splitlines()[0]


def _sprawdz_narzedzie(narzedzie: Narzedzie) -> str:
    """Buduje jeden czytelny wiersz raportu diagnostyki dla podanego narzędzia."""

    for polecenie in narzedzie.polecenia:
        sciezka = shutil.which(polecenie)
        if sciezka is not None:
            wersja = _znajdz_wersje(sciezka, narzedzie.argument_wersji)
            opis_wersji = wersja if wersja is not None else "nieznana"
            return (
                f"{narzedzie.nazwa}: JEST ({polecenie}). Wersja: {opis_wersji}. Ścieżka: {sciezka}."
            )

    return (
        f"{narzedzie.nazwa}: BRAK. Służy do: {narzedzie.do_czego_sluzy}. "
        f"Bez niego przestanie działać: {narzedzie.co_przestanie_dzialac}."
    )


def _wiersz_jezykow_ocr() -> str:
    """Buduje wiersz raportu o zainstalowanych danych językowych Tesseracta.

    Instalator Tesseracta domyślnie dokłada tylko angielski. Bez pliku
    ``pol.traineddata`` OCR polskiego tekstu daje wynik systematycznie błędny,
    więc brak polskiego jest tu wypisany wprost jako ostrzeżenie.
    """
    from gnb.core.konfiguracja import wczytaj_konfiguracje
    from gnb.core.wyjatki import BladGnb
    from gnb.images.tesseract import czy_dostepny, dostepne_jezyki

    try:
        sciezka = wczytaj_konfiguracje().sciezka_tesseract
    except BladGnb:
        sciezka = ""
    if not czy_dostepny(sciezka):
        return "Dane językowe OCR: nie sprawdzono, bo nie znaleziono Tesseracta."

    jezyki = dostepne_jezyki(sciezka)
    if not jezyki:
        return "Dane językowe OCR: Tesseract nie zwrócił listy języków."
    wykaz = ", ".join(jezyki)
    if "pol" not in jezyki:
        return (
            f"Dane językowe OCR: {wykaz}. UWAGA: brak języka „pol”. OCR polskiego "
            "tekstu będzie systematycznie błędny — dograj plik pol.traineddata."
        )
    return f"Dane językowe OCR: {wykaz}. Polski („pol”) jest zainstalowany."


def zbuduj_raport_diagnostyki() -> str:
    """Buduje pełną treść raportu diagnostyki jako jeden tekst z końcami wierszy LF."""

    wiersze = [
        "Raport diagnostyczny narzędzi zewnętrznych Gemini Notebook Builder.",
        "",
    ]
    wiersze.extend(_sprawdz_narzedzie(narzedzie) for narzedzie in NARZEDZIA)
    wiersze.append(_wiersz_jezykow_ocr())
    wiersze.append("")
    wiersze.append(
        "Koniec raportu. Brak narzędzia opcjonalnego nie zatrzymuje działania aplikacji."
    )
    return "\n".join(wiersze) + "\n"


def uruchom_diagnostyke(sciezka_pliku: str | None = None) -> int:
    """Wypisuje czytelny tekstowo raport dostępności narzędzi zewnętrznych.

    Bez opcji `sciezka_pliku` raport trafia na standardowe wyjście. Z tą opcją
    jest zapisywany wprost do wskazanego pliku w kodowaniu UTF-8 ze znacznikiem
    kolejności bajtów. Zapis wprost jest potrzebny, ponieważ przekierowanie
    standardowego wyjścia operatorem ``>`` w programie PowerShell w wersji piątej
    przekodowuje wyjście programu według strony kodowej konsoli i psuje polskie
    znaki diakrytyczne niezależnie od tego, w jakim kodowaniu program pisze.
    Raport diagnostyki jest przeznaczony do odczytu syntezatorem mowy, więc musi
    dać się zapisać do czytelnego pliku bez tej pułapki.

    Zwraca zawsze kod zero, ponieważ brak opcjonalnego narzędzia zewnętrznego
    nie jest błędem aplikacji, zgodnie z sekcją piątą CLAUDE.md. Kod jeden
    oznacza wyłącznie to, że wskazanego pliku nie dało się zapisać.
    """

    raport = zbuduj_raport_diagnostyki()
    if sciezka_pliku is None:
        print(raport, end="")
        return 0
    try:
        zapisz_tekst_utf8(Path(sciezka_pliku), raport)
    except OSError as blad:
        print(f"Nie udało się zapisać raportu do pliku {sciezka_pliku}: {blad.strerror}.")
        return KOD_BLAD
    print(f"Raport diagnostyczny zapisano w pliku: {sciezka_pliku}")
    return 0


def uruchom_pamiec(wyczysc: bool) -> int:
    """Pokazuje stan wspólnej pamięci podręcznej, a na życzenie ją czyści.

    Pamięć podręczna jest wspólna dla wszystkich projektów i leży poza katalogiem
    projektu, dlatego jej ścieżka jest wypisywana wprost. Dzięki temu nie trzeba
    szukać pliku po dysku.
    """
    try:
        konfiguracja = wczytaj_konfiguracje()
    except BladGnb as blad:
        print(f"Nie udało się wczytać konfiguracji: {blad.komunikat}")
        return KOD_BLAD

    sciezka = konfiguracja.sciezka_cache
    print(f"Plik pamięci podręcznej: {sciezka}")
    print(f"Pamięć podręczna włączona: {'tak' if konfiguracja.uzywaj_cache else 'nie'}")
    print(f"Maksymalny wiek wpisu w dniach: {konfiguracja.maksymalny_wiek_cache_dni}")

    try:
        if wyczysc:
            usuniete = wyczysc_pamiec_podreczna(sciezka)
            print(f"Usunięto wpisów: {usuniete}.")
            return 0
        if not sciezka.exists():
            print("Plik jeszcze nie istnieje. Powstanie przy pierwszym pobraniu strony.")
            return 0
        with otworz(sciezka) as pamiec:
            print(f"Zapamiętane zasoby: {pamiec.liczba_wpisow()}.")
    except BladGnb as blad:
        print(f"Nie udało się otworzyć pamięci podręcznej: {blad.komunikat}")
        return KOD_BLAD
    return 0


def _zbierz_adresy_wejsciowe(
    adresy: list[str], listy: list[str], konfiguracja: Konfiguracja
) -> PodsumowanieListyUrl:
    """Łączy adresy podane wprost oraz z plików list w jedno podsumowanie.

    Duplikaty są wykrywane po postaci kanonicznej w obrębie całego zestawu, więc
    ten sam adres podany raz wprost i raz w pliku listy jest jednym źródłem.
    """
    fragmenty = list(adresy)
    for sciezka in listy:
        podsumowanie_pliku = wczytaj_liste_z_pliku(
            Path(sciezka), konfiguracja.dodatkowe_parametry_sledzace
        )
        fragmenty.extend(adres.podany for adres in podsumowanie_pliku.adresy)
        fragmenty.extend(podsumowanie_pliku.duplikaty)
        fragmenty.extend(wpis.wartosc for wpis in podsumowanie_pliku.odrzucone)
    return zbierz_adresy("\n".join(fragmenty), konfiguracja.dodatkowe_parametry_sledzace)


def uruchom_przetwarzanie(
    nazwa_projektu: str | None,
    pliki: list[str],
    teksty_plaskie: list[str],
    teksty_markdown: list[str],
    katalog_projektu: str | None,
    adresy: list[str] | None = None,
    listy_adresow: list[str] | None = None,
    tylko_sprawdz_liste: bool = False,
    grupa: str | None = None,
    wymus_transkrypcje: bool = False,
) -> int:
    """Buduje pozycje wejściowe, uruchamia potok i wypisuje raport dla użytkownika.

    Zwraca kod zero, gdy potok się wykona, oraz kod dwa, gdy nie podano żadnego
    źródła. Pojedyncze błędne źródło nie zmienia kodu wyjścia — jest opisane
    w raporcie, w manifeście i w logu.

    Argument `grupa` przypisuje wszystkie źródła tego wywołania do jednej grupy
    tematycznej pakowania. Źródła jednej grupy są w etapie szóstym łączone
    w możliwie najmniej plików wynikowych. Wiele grup w jednym projekcie
    uzyskuje się przez kilkukrotne uruchomienie polecenia: checkpoint kumuluje
    źródła między uruchomieniami.

    Argument `wymus_transkrypcje` przełamuje odrzucenie nagrania rozpoznanego
    jako niemowne: audio jest wtedy przepisywane nawet przy niskim udziale mowy.
    Służy do nadpisania tej decyzji dla konkretnego nagrania mowy z głośnym tłem.

    Przy opcji `tylko_sprawdz_liste` polecenie kończy się po wypisaniu
    podsumowania listy adresów, z kodem zero także wtedy, gdy część wpisów jest
    błędna. Wykrycie błędnych wpisów jest bowiem zamierzonym wynikiem tego
    sprawdzenia, a nie awarią. Kod niezerowy pojawia się tylko wtedy, gdy pliku
    listy nie da się odczytać.
    """
    moment = datetime.now(UTC)
    try:
        konfiguracja = wczytaj_konfiguracje()
        podsumowanie_adresow = _zbierz_adresy_wejsciowe(
            list(adresy or []), list(listy_adresow or []), konfiguracja
        )
    except BladGnb as blad:
        print(f"Nie udało się przygotować listy adresów: {blad.komunikat}")
        return KOD_BLAD

    if podsumowanie_adresow.liczba_wykrytych:
        print("Podsumowanie listy adresów przed pobraniem:")
        print(opis_podsumowania(podsumowanie_adresow))
        print("")

    if tylko_sprawdz_liste:
        print("Sprawdzenie listy zakończone. Nie pobrano żadnego adresu.")
        return 0

    pozycje: list[PozycjaWejsciowa] = []
    for sciezka in pliki:
        pozycje.append(przyjmij_plik(Path(sciezka), moment, grupa=grupa))
    for tresc in teksty_plaskie:
        pozycje.append(przyjmij_tekst(tresc, moment, format_tekstu="txt", grupa=grupa))
    for tresc in teksty_markdown:
        pozycje.append(przyjmij_tekst(tresc, moment, format_tekstu="md", grupa=grupa))
    for adres in podsumowanie_adresow.adresy:
        pozycje.append(
            przyjmij_url(
                adres.podany,
                moment,
                konfiguracja.dodatkowe_parametry_sledzace,
                grupa=grupa,
            )
        )

    if not pozycje:
        print(
            "Nie podano żadnego źródła. Użyj opcji --plik, --tekst, --tekst-md, "
            "--url albo --lista-url."
        )
        return KOD_BRAK_ZRODEL

    try:
        wynik = przetworz_projekt(
            pozycje,
            konfiguracja,
            nazwa_projektu=nazwa_projektu,
            wlasny_katalog_projektu=Path(katalog_projektu) if katalog_projektu else None,
            postep=_postep_wiersza_polecen(),
            wymus_transkrypcje=wymus_transkrypcje,
        )
    except BladGnb as blad:
        print(f"Przetwarzanie przerwane błędem: {blad.komunikat}")
        return KOD_BLAD

    print(f"Projekt: {wynik.nazwa_projektu}")
    print(f"Katalog projektu: {wynik.katalog_projektu}")
    print(f"Wznowiono istniejący projekt: {'tak' if wynik.wznowiono else 'nie'}")
    print(f"Źródła przetworzone: {wynik.liczba_przetworzonych}")
    print(f"Źródła pominięte: {wynik.liczba_pominietych}")
    print(f"Źródła z błędem: {wynik.liczba_bledow}")
    print(f"Manifest: {wynik.sciezka_manifestu}")
    print(f"Raport końcowy: {wynik.sciezka_raportu}")
    print("")
    print(
        f"Przetworzono {wynik.liczba_przetworzonych} źródeł, "
        f"pominięto {wynik.liczba_pominietych + wynik.liczba_bledow}. "
        f"Wyniki są w katalogu: {wynik.katalog_projektu}."
    )
    return 0


def zapisz_tekst_utf8(sciezka: Path, tresc: str) -> None:
    """Zapisuje tekst do pliku w kodowaniu UTF-8 ze znacznikiem kolejności bajtów.

    Znacznik kolejności bajtów sprawia, że edytor tekstu i czytnik ekranu
    otwierający plik rozpoznają kodowanie UTF-8, zamiast zakładać systemową
    stronę kodową, w której polskie znaki diakrytyczne są nieczytelne. Końce
    wierszy są ujednolicone do znaku nowej linii.
    """

    sciezka.parent.mkdir(parents=True, exist_ok=True)
    with sciezka.open("w", encoding="utf-8-sig", newline="\n") as plik:
        plik.write(tresc)


def _wymus_kodowanie_utf8() -> None:
    """Ustawia standardowe wyjście i wyjście błędów na UTF-8.

    Domyślne kodowanie konsoli Windows oraz wyjścia przekierowanego do pliku
    bywa stroną kodową taką jak cp1250, w której polskie znaki diakrytyczne
    wypisują się jako nieczytelne znaki zapytania albo inne krzaki. Ponieważ
    komunikaty aplikacji muszą być czytelne dla czytnika ekranu, wyjście jest
    jawnie przełączane na UTF-8 niezależnie od strony kodowej odziedziczonej
    z systemu.

    Sprawdzana jest sama obecność metody ``reconfigure``, a nie konkretny typ
    strumienia. Dzięki temu przełączenie działa także wtedy, gdy standardowe
    wyjście zostało zastąpione własną klasą, na przykład przez narzędzie
    przechwytujące wyjście testów. Strumień, którego nie da się przełączyć,
    jest pomijany, ponieważ nieudane przełączenie kodowania nie jest błędem
    zatrzymującym aplikację.
    """

    for strumien in (sys.stdout, sys.stderr):
        rekonfiguruj = getattr(strumien, "reconfigure", None)
        if not callable(rekonfiguruj):
            continue
        try:
            rekonfiguruj(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def main(argumenty: list[str] | None = None) -> int:
    """Punkt wejścia wiersza poleceń aplikacji."""

    _wymus_kodowanie_utf8()

    parser = argparse.ArgumentParser(
        prog="gnb", description="Gemini Notebook Builder — wiersz poleceń."
    )
    podpolecenia = parser.add_subparsers(dest="polecenie", required=True)
    parser_diagnostyka = podpolecenia.add_parser(
        "diagnostyka", help="Sprawdź dostępność narzędzi zewnętrznych."
    )
    parser_diagnostyka.add_argument(
        "--plik",
        metavar="SCIEZKA",
        default=None,
        help=(
            "Zapisz raport wprost do wskazanego pliku w UTF-8 zamiast na standardowe "
            "wyjście. Zapis wprost pomija pułapkę przekierowania operatorem „>” "
            "w programie PowerShell, które psuje polskie znaki."
        ),
    )

    parser_pamiec = podpolecenia.add_parser(
        "pamiec",
        help="Pokaż stan wspólnej pamięci podręcznej pobranych stron albo ją wyczyść.",
    )
    parser_pamiec.add_argument(
        "--wyczysc",
        action="store_true",
        help="Usuń całą zawartość pamięci podręcznej.",
    )

    parser_przetworz = podpolecenia.add_parser(
        "przetworz",
        help=(
            "Przetwórz tekst wklejony, pliki TXT i MD oraz adresy stron w ramach jednego projektu."
        ),
    )
    parser_przetworz.add_argument(
        "--projekt", metavar="NAZWA", default=None, help="Nazwa projektu. Domyślnie generowana."
    )
    parser_przetworz.add_argument(
        "--plik",
        action="append",
        default=[],
        metavar="SCIEZKA",
        help=(
            "Ścieżka pliku lokalnego: tekst, dokument, obraz albo nagranie mowy. "
            "Opcję można podać wielokrotnie."
        ),
    )
    parser_przetworz.add_argument(
        "--tekst",
        action="append",
        default=[],
        metavar="TRESC",
        help="Tekst wklejony traktowany jako tekst płaski. Opcję można podać wielokrotnie.",
    )
    parser_przetworz.add_argument(
        "--tekst-md",
        action="append",
        default=[],
        metavar="TRESC",
        dest="tekst_md",
        help="Tekst wklejony traktowany jako Markdown. Opcję można podać wielokrotnie.",
    )
    parser_przetworz.add_argument(
        "--url",
        action="append",
        default=[],
        metavar="ADRES",
        help=(
            "Adres strony internetowej albo filmu z serwisu YouTube. Opcję można podać "
            "wielokrotnie, a w jednej wartości zmieścić kilka adresów rozdzielonych spacjami."
        ),
    )
    parser_przetworz.add_argument(
        "--lista-url",
        action="append",
        default=[],
        metavar="SCIEZKA",
        dest="lista_url",
        help="Plik TXT z adresami. Opcję można podać wielokrotnie.",
    )
    parser_przetworz.add_argument(
        "--sprawdz-liste",
        action="store_true",
        dest="sprawdz_liste",
        help="Wypisz podsumowanie listy adresów i zakończ, bez pobierania czegokolwiek.",
    )
    parser_przetworz.add_argument(
        "--grupa",
        metavar="NAZWA",
        default=None,
        help=(
            "Nazwa grupy tematycznej dla wszystkich źródeł tego wywołania. Źródła jednej "
            "grupy są łączone w możliwie najmniej plików wynikowych. Kolejną grupę dodaje "
            "się osobnym wywołaniem polecenia w tym samym projekcie."
        ),
    )
    parser_przetworz.add_argument(
        "--wymus-transkrypcje",
        action="store_true",
        dest="wymus_transkrypcje",
        help=(
            "Przepisz nagranie mowy nawet wtedy, gdy zostało rozpoznane jako niemowne. "
            "Przydatne dla nagrania mowy z głośną muzyką albo szumem w tle."
        ),
    )
    parser_przetworz.add_argument(
        "--katalog",
        metavar="SCIEZKA",
        default=None,
        help="Własny katalog projektu. Domyślnie katalog wyników z konfiguracji.",
    )

    ustalone = parser.parse_args(argumenty)

    if ustalone.polecenie == "diagnostyka":
        return uruchom_diagnostyke(ustalone.plik)

    if ustalone.polecenie == "pamiec":
        return uruchom_pamiec(bool(ustalone.wyczysc))

    if ustalone.polecenie == "przetworz":
        return uruchom_przetwarzanie(
            ustalone.projekt,
            list(ustalone.plik),
            list(ustalone.tekst),
            list(ustalone.tekst_md),
            ustalone.katalog,
            list(ustalone.url),
            list(ustalone.lista_url),
            bool(ustalone.sprawdz_liste),
            ustalone.grupa,
            bool(ustalone.wymus_transkrypcje),
        )

    parser.error(f"Nieznane polecenie: {ustalone.polecenie}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
