"""Adapter ekstrakcji dla zapisu nutowego w postaci obrazu albo pliku PDF.

Rozpoznawanie notacji robi zewnętrzny program Audiveris, uruchamiany w trybie
wsadowym, bez interfejsu graficznego. Audiveris eksportuje MusicXML, który jest
dalej odczytywany tym samym parserem co formaty natywne, `gnb.music.musicxml`
— granica między częścią A a częścią B etapu dziesiątego wypada dokładnie na
tym pliku, a nie na parserze MusicXML, który obie części dzielą.

Audiveris nie zwraca żadnej publicznej wartości pewności rozpoznania — ani przez
wiersz poleceń, ani w wyeksportowanym MusicXML. Zamiast zbiorczej oceny ten
adapter dokłada do opisu: jawne oznaczenie pochodzenia (rozpoznanie optyczne,
nie odczyt pliku notacji), oraz policzalne sygnały kontrolne wyprowadzone z
wyniku — brak tonacji, brak metrum, brak taktów, takty bez żadnej rozpoznanej
treści. Każde źródło przetworzone tą drogą dostaje też stałe ostrzeżenie, które
bezwarunkowo kieruje je do sekcji raportu „Materiały do sprawdzenia”, niezależnie
od tego, czy powyższe sygnały coś wykryły.

Limit czasu liczony jest na stronę, nie na cały plik: wielostronicowy skan miałby
inaczej przerywaną w połowie legalną pracę. Audiveris przetwarza wielostronicowy
plik jednym wywołaniem i sam łączy strony w jedną ciągłą partyturę — zweryfikowane
uruchomieniem na prawdziwym dwustronicowym pliku PDF, więc ten adapter nie dzieli
źródła i zwraca jeden opis dla całego pliku. Postęp jest raportowany strona po
stronie przez odczyt rosnącego pliku dziennika Audiverisa w trakcie jego pracy.
"""

from __future__ import annotations

import io
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BladPrzejsciowy, BladTrwaly, PominietoZrodlo
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.plik_obraz import FORMATY_OBRAZOW
from gnb.music.audiveris import znajdz_audiveris
from gnb.music.model import OpisPartytury, zbuduj_dokument_wyekstrahowany
from gnb.music.musicxml import przeczytaj_musicxml

METODA_EKSTRAKCJI = "nuty-skanowane-audiveris"
FORMATY_NUTY_SKANOWANE = frozenset({"pdf"}) | FORMATY_OBRAZOW

# Górny limit czasu rozpoznawania JEDNEJ strony albo arkusza. Zmierzone naprawdę
# na tym komputerze: syntetyczny obrazek 1400x700 px dał wynik w 13,7 s, ten sam
# materiał w rozdzielczości realnego skanu (5833x2916 px) zajął 2 minuty 9,7 s.
# Wartość jest wielokrotnie wyższa, żeby gęściej zapisana prawdziwa partytura na
# wolniejszym sprzęcie nie została ucięta w połowie pracy. Limit dla całego pliku
# to ta wartość razy liczba stron, nie stała — patrz `_limit_czasu_sekundy`.
LIMIT_CZASU_NA_STRONE_SEKUNDY = 1800

# Odstęp między kolejnymi odczytami rosnącego pliku dziennika Audiverisa.
_ODSTEP_SPRAWDZANIA_POSTEPU_SEKUNDY = 2.0

# Koniec wiersza dziennika Audiverisa oznaczający ukończenie ostatniego kroku
# jednego arkusza — sprawdzone uruchomieniem programu, ten sam wiersz pojawia
# się raz na stronę niezależnie od tego, czy plik ma jedną stronę, czy wiele.
_ZNACZNIK_KONCA_STRONY = "| PAGE"

# Nazwa pliku wykonywalnego jest odnajdywana przez `gnb.music.audiveris`, a nie
# tu — ten moduł zna tylko sposób wywołania.
_ARGUMENTY_WSADOWE = ("-batch", "-transcribe", "-export", "-output")

SUFIKS_PLIKU_POSREDNIEGO = "audiveris.mxl"

KOMUNIKAT_USZKODZONY_PLIK = (
    "Pliku ze skanem nut nie dało się otworzyć: jest uszkodzony albo nie jest "
    "poprawnym plikiem PDF ani obrazem."
)
KOMUNIKAT_BRAK_ROZPOZNANIA = "Audiveris nie rozpoznał w tym pliku żadnej notacji muzycznej."

_ZDANIE_POCHODZENIA = (
    "Ten opis powstał z rozpoznania optycznego obrazu lub skanu programem "
    "Audiveris, a nie z odczytu pliku notacji muzycznej."
)
_OSTRZEZENIE_DO_SPRAWDZENIA = (
    "Materiał rozpoznany optycznie programem Audiveris — automatyczne "
    "rozpoznanie zapisu nutowego bywa niedokładne, sprawdź treść przed użyciem."
)


class EkstraktorNutSkanowanych:
    """Adapter zapisu nutowego z obrazu i PDF przez rozpoznawanie optyczne Audiverisem."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def __init__(self, sciezka_audiveris: str = "") -> None:
        self._sciezka_audiveris = sciezka_audiveris

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_NUTY and format_zrodla in FORMATY_NUTY_SKANOWANE

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Rozpoznaje zapis nutowy programem Audiveris i buduje z niego opis partytury.

        Kolejność: sprawdź i przygotuj plik wejściowy i policz strony, dopiero
        potem znajdź program — uszkodzony plik ma się ujawnić bez wymagania
        obecności zewnętrznego narzędzia — uruchom Audiverisa w katalogu
        tymczasowym, odczytaj wyeksportowany MusicXML istniejącym parserem,
        dołóż oznaczenie pochodzenia i sygnały kontrolne. Katalog tymczasowy,
        wraz z plikiem projektu Audiverisa (`.omr`) i dziennikiem, znika w
        całości po wyjściu z bloku — jedyne, co z niego przeżywa, to bajty
        MusicXML wczytane do pamięci wcześniej.
        """
        surowe_wejscie, rozszerzenie, liczba_stron, opis_pochodzenia = _przygotuj_wejscie(
            bajty, identyfikator_zrodla
        )
        program = znajdz_audiveris(self._sciezka_audiveris)
        limit_czasu_sekundy = _limit_czasu_sekundy(liczba_stron)

        with tempfile.TemporaryDirectory(prefix="gnb-audiveris-") as nazwa_katalogu:
            katalog = Path(nazwa_katalogu)
            plik_wejsciowy = katalog / f"wejscie.{rozszerzenie}"
            plik_wejsciowy.write_bytes(surowe_wejscie)
            katalog_wyjsciowy = katalog / "wynik"
            katalog_wyjsciowy.mkdir()
            plik_dziennika = katalog / "dziennik.txt"

            polecenie = [
                str(program),
                *_ARGUMENTY_WSADOWE,
                str(katalog_wyjsciowy),
                str(plik_wejsciowy),
            ]
            kod_wyjscia = _uruchom_audiveris(
                polecenie,
                plik_dziennika,
                limit_czasu_sekundy,
                liczba_stron,
                postep,
                identyfikator_zrodla,
            )
            if kod_wyjscia != 0:
                raise BladTrwaly(
                    f"Audiveris nie rozpoznał zapisu nutowego (kod {kod_wyjscia}). "
                    f"Ostatnie wiersze dziennika: {_ostatnie_wiersze_dziennika(plik_dziennika)}",
                    identyfikator_zrodla,
                )

            pliki_mxl = sorted(katalog_wyjsciowy.glob("*.mxl"))
            if not pliki_mxl:
                raise PominietoZrodlo(KOMUNIKAT_BRAK_ROZPOZNANIA, identyfikator_zrodla)
            mxl_bajty = pliki_mxl[0].read_bytes()

        opis = przeczytaj_musicxml(mxl_bajty)
        opis.format_zrodlowy = opis_pochodzenia
        opis.metoda_odczytu = "Audiveris (rozpoznanie optyczne) + xml.etree"
        opis.uwagi_odczytu.append(_ZDANIE_POCHODZENIA)
        opis.ostrzezenia_zmian.append(_OSTRZEZENIE_DO_SPRAWDZENIA)
        opis.ostrzezenia_zmian.extend(_sygnaly_kontrolne(opis, mxl_bajty))

        dokument = zbuduj_dokument_wyekstrahowany(
            identyfikator_zrodla, opis, metoda_ekstrakcji=METODA_EKSTRAKCJI
        )
        dokument.plik_posredni = (SUFIKS_PLIKU_POSREDNIEGO, mxl_bajty)
        return dokument


def _przygotuj_wejscie(bajty: bytes, identyfikator_zrodla: str) -> tuple[bytes, str, int, str]:
    """Zwraca bajty pliku wejściowego, jego rozszerzenie, liczbę stron i opis pochodzenia.

    PDF trafia do Audiverisa bez zmian — Audiveris czyta PDF własnym dekoderem
    (biblioteka PDFBox), więc nie ma potrzeby rasteryzować stron samodzielnie.
    Obraz jest otwierany i od nowa zapisywany jako PNG biblioteką Pillow, nie
    dlatego, że Audiveris wymaga akurat tego rozszerzenia — sam Audiveris i tak
    sprowadza obraz do skali szarości, sprawdzone uruchomieniem — tylko żeby
    uszkodzony plik ujawnił się tu, kontrolowanym błędem trwałym, zamiast dopiero
    wewnątrz Audiverisa nieczytelnym komunikatem po angielsku.
    """
    if bajty[:4] == b"%PDF":
        try:
            czytnik = PdfReader(io.BytesIO(bajty))
            liczba_stron = len(czytnik.pages)
        except (PdfReadError, ValueError) as blad:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY_PLIK, identyfikator_zrodla) from blad
        if liczba_stron < 1:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY_PLIK, identyfikator_zrodla)
        opis_pochodzenia = (
            "PDF ze skanem nut (rozpoznanie optyczne, Audiveris)"
            if liczba_stron == 1
            else f"PDF ze skanem nut, {liczba_stron} stron (rozpoznanie optyczne, Audiveris)"
        )
        return bajty, "pdf", liczba_stron, opis_pochodzenia

    try:
        obraz = Image.open(io.BytesIO(bajty))
        obraz.load()
    except (UnidentifiedImageError, OSError) as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY_PLIK, identyfikator_zrodla) from blad
    bufor = io.BytesIO()
    obraz.convert("RGB").save(bufor, format="PNG")
    return (
        bufor.getvalue(),
        "png",
        1,
        "obraz ze skanem nut (rozpoznanie optyczne, Audiveris)",
    )


def _limit_czasu_sekundy(liczba_stron: int) -> float:
    """Liczy limit czasu całego wywołania z limitu na stronę, nie ze stałej."""
    return liczba_stron * LIMIT_CZASU_NA_STRONE_SEKUNDY


def _uruchom_audiveris(
    polecenie: list[str],
    plik_dziennika: Path,
    limit_czasu_sekundy: float,
    liczba_stron: int,
    postep: PostepEkstrakcji | None,
    identyfikator_zrodla: str,
) -> int:
    """Uruchamia Audiverisa, zgłaszając postęp strona po stronie i pilnując limitu czasu.

    Wyjście podprocesu trafia do pliku, a nie do potoku, żeby dało się je czytać
    w trakcie pracy procesu, zanim się zakończy — zachowanie zweryfikowane wprost
    przy projektowaniu tego adaptera. Ukończenie kolejnej strony poznaje się po
    wierszu dziennika kończącym się krokiem PAGE, ostatnim krokiem rozpoznawania
    jednego arkusza. Odczyt pliku dziennika jest odporny na chwilowy błąd dostępu
    ze strony systemu — pomija wtedy tę próbę i sprawdza ponownie przy następnym
    obiegu pętli, zamiast przerywać całe rozpoznawanie z powodu samego odczytu
    dziennika.
    """
    with plik_dziennika.open("wb") as uchwyt_zapisu:
        proces = subprocess.Popen(polecenie, stdout=uchwyt_zapisu, stderr=subprocess.STDOUT)

    poczatek = time.monotonic()
    stron_ukonczonych = 0
    pozycja_odczytu = 0
    while True:
        kod_wyjscia = proces.poll()
        try:
            with plik_dziennika.open("rb") as uchwyt_odczytu:
                uchwyt_odczytu.seek(pozycja_odczytu)
                nowe_bajty = uchwyt_odczytu.read()
                pozycja_odczytu = uchwyt_odczytu.tell()
        except OSError:
            nowe_bajty = b""

        if nowe_bajty and postep is not None:
            for wiersz in nowe_bajty.decode("utf-8", errors="replace").splitlines():
                if wiersz.rstrip().endswith(_ZNACZNIK_KONCA_STRONY) and (
                    stron_ukonczonych < liczba_stron
                ):
                    stron_ukonczonych += 1
                    postep(stron_ukonczonych, liczba_stron)

        if kod_wyjscia is not None:
            return kod_wyjscia

        if time.monotonic() - poczatek > limit_czasu_sekundy:
            proces.kill()
            proces.wait()
            raise BladPrzejsciowy(
                "Rozpoznawanie zapisu nutowego przez Audiveris przekroczyło limit "
                f"czasu {int(limit_czasu_sekundy)} sekund.",
                identyfikator_zrodla,
            )

        time.sleep(_ODSTEP_SPRAWDZANIA_POSTEPU_SEKUNDY)


def _ostatnie_wiersze_dziennika(plik_dziennika: Path, ile: int = 5) -> str:
    """Zwraca ostatnich kilka wierszy dziennika Audiverisa do wklejenia w komunikat błędu."""
    try:
        wiersze = plik_dziennika.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "brak dziennika."
    return " | ".join(wiersze[-ile:]) if wiersze else "dziennik jest pusty."


def _sygnaly_kontrolne(opis: OpisPartytury, mxl_bajty: bytes) -> list[str]:
    """Wyprowadza policzalne sygnały nieudanego rozpoznania z wyniku Audiverisa.

    W przeciwieństwie do zbiorczej oceny pewności każdy sygnał jest sprawdzalnym
    faktem: obecnością albo brakiem konkretnego elementu w wyniku, nie naszą
    opinią o jego jakości.
    """
    sygnaly: list[str] = []
    if not opis.tonacja:
        sygnaly.append("Audiveris nie rozpoznał oznaczenia tonacji.")
    if not opis.metrum:
        sygnaly.append("Audiveris nie rozpoznał oznaczenia metrum.")
    if not opis.liczba_taktow:
        sygnaly.append("Audiveris nie rozpoznał żadnego taktu.")

    puste_takty = _numery_pustych_taktow(mxl_bajty)
    if puste_takty:
        sygnaly.append(
            "Takt(y) bez żadnej rozpoznanej treści po rozpoznaniu optycznym: "
            + ", ".join(puste_takty)
            + "."
        )
    return sygnaly


def _numery_pustych_taktow(mxl_bajty: bytes) -> list[str]:
    """Zwraca numery taktów bez nuty, pauzy ani wypełnienia w wyeksportowanym MusicXML.

    Niezależne od `gnb.music.musicxml.przeczytaj_musicxml`, który zwraca już
    zbudowany opis, a nie drzewo XML do dalszego przeszukania — stąd własny,
    celowo mały odczyt ograniczony do tego jednego sygnału.
    """
    if zipfile.is_zipfile(io.BytesIO(mxl_bajty)):
        with zipfile.ZipFile(io.BytesIO(mxl_bajty)) as archiwum:
            nazwa_partytury = next(
                (
                    nazwa
                    for nazwa in archiwum.namelist()
                    if nazwa.lower().endswith(".xml") and "meta-inf" not in nazwa.lower()
                ),
                None,
            )
            tresc = archiwum.read(nazwa_partytury) if nazwa_partytury else mxl_bajty
    else:
        tresc = mxl_bajty

    try:
        korzen = ET.fromstring(tresc)
    except ET.ParseError:
        return []

    puste: list[str] = []
    for takt in korzen.iter():
        if _lokalny_tag(takt.tag) != "measure":
            continue
        ma_tresc = any(
            _lokalny_tag(dziecko.tag) in ("note", "forward", "backup") for dziecko in takt
        )
        if not ma_tresc:
            puste.append(takt.get("number") or "?")
    return puste


def _lokalny_tag(tag: str) -> str:
    """Zwraca nazwę znacznika bez przestrzeni nazw — MusicXML jej zwykle nie ma."""
    return tag.rsplit("}", 1)[-1]
