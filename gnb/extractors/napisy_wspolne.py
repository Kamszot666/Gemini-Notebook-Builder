"""Sklejanie segmentów napisów w czytelne akapity, wspólne dla kilku źródeł.

Napisy, niezależnie od tego, czy pochodzą z serwisu YouTube, czy z pliku SRT
albo VTT dostarczonego przez użytkownika, mają tę samą wadę jako materiał
źródłowy: przychodzą jako dziesiątki albo setki krótkich fragmentów, często
urwanych w połowie zdania. Taki zapis jest bezużyteczny wprost jako materiał
w notatniku i wyjątkowo męczący przy odsłuchu czytnikiem ekranu, dlatego
fragmenty są sklejane w zdania, a zdania w akapity.

Napisy generowane automatycznie mają dodatkową właściwość: kolejne segmenty
powtarzają końcówkę poprzedniego, ponieważ tekst przewija się na ekranie.
Powtórzenia są wykrywane i usuwane, żeby to samo zdanie nie pojawiło się
w wyniku dwa razy. Ten sam mechanizm broni też przed nakładającymi się
fragmentami w plikach SRT i VTT wyeksportowanych z automatycznego rozpoznawania
mowy.

Znaczniki czasu są opcjonalne. Znacznik przy każdym segmencie rozbijałby tekst
na strzępy, więc gdy są włączone, pojawiają się wyłącznie na początku akapitu.

Logika ta była wcześniej częścią ekstraktora YouTube. Wydzielenie jej do
osobnego modułu pozwala użyć jej też dla plików napisów SRT i VTT, bez
duplikowania nietrywialnego algorytmu sklejania w dwóch miejscach.

Moduł nie interpretuje treści napisów. Tekst źródłowy jest danymi, nigdy
instrukcją.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from gnb.ingestion.youtube import SegmentNapisow

# Progi podziału na akapity. Akapit jest zamykany na końcu zdania, gdy ma już
# sensowną długość, a najpóźniej po przekroczeniu długości maksymalnej, żeby
# materiał bez interpunkcji nie zamienił się w jeden nieskończony blok.
MINIMALNA_DLUGOSC_AKAPITU = 350
MAKSYMALNA_DLUGOSC_AKAPITU = 1200
SEKUND_W_GODZINIE = 3600

_ZNAKI_KONCA_ZDANIA = (".", "!", "?", "…", ":")

# Nawias okrągły albo kwadratowy wraz z zawartością. Sam nawias nie przesądza
# jeszcze, że to oznaczenie dźwięku — rozstrzyga o tym `_czy_oznaczenie_dzwieku`.
_NAWIAS = re.compile(r"\[[^\]]*\]|\([^)]*\)")
_ZNACZNIKI_WEWNETRZNE = re.compile(r"<[^>]*>")
_NUTY = re.compile(r"[♪♫]")
_BIALE_ZNAKI = re.compile(r"\s+")
_CYFRA = re.compile(r"\d")

# Najdłuższe oznaczenie dźwięku, jakie usuwamy z treści segmentu. Typowe
# oznaczenie to jedno słowo, na przykład „[muzyka]” albo „(śmiech)”, rzadziej
# krótka fraza w rodzaju „[muzyka w tle]”. Dłuższy nawias to już zdanie
# poboczne wypowiedzi, więc zostaje.
MAKSYMALNA_LICZBA_SLOW_OZNACZENIA_DZWIEKU = 3

# Znaki, których obecność w nawiasie świadczy o wypowiedzi, a nie o etykiecie
# dźwięku. Dwukropka tu nie ma, bo bywa częścią wskazania mówiącego.
_ZNAKI_ZDANIA_W_NAWIASIE = (".", "!", "?", "…")


class Akapit:
    """Jeden akapit transkrypcji wraz z momentem jego rozpoczęcia."""

    __slots__ = ("poczatek_sekundy", "tekst")

    def __init__(self, poczatek_sekundy: float, tekst: str) -> None:
        self.poczatek_sekundy = poczatek_sekundy
        self.tekst = tekst

    def __eq__(self, inny: object) -> bool:
        if not isinstance(inny, Akapit):
            return NotImplemented
        return (self.poczatek_sekundy, self.tekst) == (inny.poczatek_sekundy, inny.tekst)

    def __repr__(self) -> str:
        return f"Akapit({self.poczatek_sekundy!r}, {self.tekst!r})"


def zbuduj_akapity(segmenty: Sequence[SegmentNapisow]) -> list[Akapit]:
    """Skleja segmenty napisów w akapity, usuwając powtórzenia i puste fragmenty.

    Podział jest deterministyczny i nie zależy od tego, czy znaczniki czasu są
    włączone. Akapit kończy się na granicy zdania, gdy osiągnął już minimalną
    długość, albo po przekroczeniu długości maksymalnej.
    """
    akapity: list[Akapit] = []
    biezacy: list[str] = []
    poczatek: float = 0.0

    for segment in segmenty:
        tekst = _oczysc_segment(segment.tekst)
        if not tekst:
            continue

        dolaczany = _bez_powtorzenia(" ".join(biezacy), tekst)
        if not dolaczany:
            continue

        if not biezacy:
            poczatek = segment.poczatek_sekundy
        biezacy.append(dolaczany)

        polaczony = " ".join(biezacy)
        if _czy_zamknac_akapit(polaczony):
            akapity.append(Akapit(poczatek, polaczony))
            biezacy = []

    if biezacy:
        akapity.append(Akapit(poczatek, " ".join(biezacy)))
    return akapity


def zapisz_akapity(
    akapity: Sequence[Akapit],
    *,
    znaczniki_czasu: bool = False,
    dlugosc_filmu_sekundy: int | None = None,
) -> str:
    """Zapisuje akapity jako tekst, opcjonalnie ze znacznikiem czasu na początku.

    Format znacznika jest jednolity w obrębie całego pliku i zależy od łącznej
    długości materiału, a nie od momentu danego akapitu. Dzięki temu w jednym
    materiale nie mieszają się zapisy dwu- i trzyczłonowe.
    """
    if not akapity:
        return ""
    if not znaczniki_czasu:
        return "\n\n".join(akapit.tekst for akapit in akapity)

    z_godzinami = _czy_zapis_z_godzinami(akapity, dlugosc_filmu_sekundy)
    return "\n\n".join(
        f"{_znacznik_czasu(akapit.poczatek_sekundy, z_godzinami)} {akapit.tekst}"
        for akapit in akapity
    )


def _czy_zapis_z_godzinami(
    akapity: Sequence[Akapit], dlugosc_materialu_sekundy: int | None
) -> bool:
    """Rozstrzyga, czy znacznik ma zawierać godziny.

    Podstawą jest znana długość materiału. Gdy nie jest znana, decyduje moment
    ostatniego akapitu, bo to najlepsze dostępne przybliżenie długości całości.
    """
    if dlugosc_materialu_sekundy is not None:
        return dlugosc_materialu_sekundy >= SEKUND_W_GODZINIE
    return bool(akapity) and akapity[-1].poczatek_sekundy >= SEKUND_W_GODZINIE


def _znacznik_czasu(sekundy: float, z_godzinami: bool) -> str:
    """Buduje znacznik czasu w postaci ``[mm:ss]`` albo ``[h:mm:ss]``."""
    calkowite = int(sekundy)
    godziny, reszta = divmod(calkowite, SEKUND_W_GODZINIE)
    minuty, sekundy_reszty = divmod(reszta, 60)
    if z_godzinami:
        return f"[{godziny}:{minuty:02d}:{sekundy_reszty:02d}]"
    return f"[{minuty + godziny * 60:02d}:{sekundy_reszty:02d}]"


def _oczysc_segment(tekst: str) -> str:
    """Usuwa z segmentu oznaczenia dźwięków, znaczniki i nadmiarowe białe znaki."""
    bez_znacznikow = _ZNACZNIKI_WEWNETRZNE.sub(" ", tekst)
    bez_dzwiekow = _usun_oznaczenia_dzwiekow(bez_znacznikow)
    bez_nut = _NUTY.sub(" ", bez_dzwiekow)
    return _BIALE_ZNAKI.sub(" ", bez_nut).strip()


def _usun_oznaczenia_dzwiekow(tekst: str) -> str:
    """Usuwa z segmentu wyłącznie nawiasy będące oznaczeniem dźwięku.

    Wcześniej usuwana była zawartość każdego nawiasu, co kasowało treść
    merytoryczną: zdanie „Wojna trwała (1939-1945) i objęła cały kontynent”
    traciło daty. Nawias jest więc oceniany, a nie usuwany z góry, i przy
    wątpliwości zostaje, bo utrata treści kosztuje więcej niż zostawiona
    etykieta dźwięku.
    """
    caly_segment = tekst.strip()

    def zamien(dopasowanie: re.Match[str]) -> str:
        fragment = dopasowanie.group(0)
        return " " if _czy_oznaczenie_dzwieku(fragment, caly_segment) else fragment

    return _NAWIAS.sub(zamien, tekst)


def _czy_oznaczenie_dzwieku(fragment: str, caly_segment: str) -> bool:
    """Rozstrzyga, czy nawias jest etykietą dźwięku, czy częścią wypowiedzi.

    Kryterium ma dwie ścieżki. Nawias obejmujący cały segment jest etykietą,
    ponieważ segment napisów złożony wyłącznie z nawiasu nie jest wypowiedzią —
    tak zapisuje się „[muzyka rockowa gra w tle]”. Nawias wewnątrz zdania jest
    etykietą tylko wtedy, gdy jest krótki i nie zawiera znaku końca zdania.

    Zawartość z cyfrą zostaje zawsze i ta reguła wyprzedza obie ścieżki. Daty,
    zakresy lat, wyniki i numery w nawiasie nigdy nie są oznaczeniami dźwięków,
    a to właśnie one były dotąd tracone.
    """
    wnetrze = fragment[1:-1].strip()
    if _CYFRA.search(wnetrze):
        return False
    if fragment == caly_segment:
        return True
    if any(znak in wnetrze for znak in _ZNAKI_ZDANIA_W_NAWIASIE):
        return False
    return len(wnetrze.split()) <= MAKSYMALNA_LICZBA_SLOW_OZNACZENIA_DZWIEKU


def _bez_powtorzenia(dotychczasowy: str, nowy: str) -> str:
    """Zwraca tę część nowego segmentu, której nie ma jeszcze w akapicie.

    Usuwane jest wyłącznie rzeczywiste nakładanie się, czyli sytuacja, w której
    koniec dotychczasowego akapitu jest dosłownie początkiem nowego segmentu.
    Tak wygląda przewijanie tekstu na ekranie w napisach automatycznych i tylko
    to zjawisko miało być tu obsłużone.

    Wcześniej kasowany był każdy segment, którego tekst występował gdziekolwiek
    w bieżącym akapicie, przez co sekwencja „Tak.”, zdanie, „Tak.” traciła drugie
    „Tak.”. Porównanie idzie po słowach, a nie po znakach, więc końcówka
    poprzedniego wyrazu nie może przypadkiem dopasować się do całego wyrazu.
    """
    if not dotychczasowy:
        return nowy
    slowa_dotychczasowe = dotychczasowy.split()
    slowa_nowe = nowy.split()
    najdluzsze_nakladanie = min(len(slowa_dotychczasowe), len(slowa_nowe))
    for dlugosc in range(najdluzsze_nakladanie, 0, -1):
        if slowa_dotychczasowe[-dlugosc:] == slowa_nowe[:dlugosc]:
            return " ".join(slowa_nowe[dlugosc:])
    return nowy


def _czy_zamknac_akapit(tekst: str) -> bool:
    """Rozstrzyga, czy akapit jest już gotowy do zamknięcia."""
    if len(tekst) >= MAKSYMALNA_DLUGOSC_AKAPITU:
        return True
    return len(tekst) >= MINIMALNA_DLUGOSC_AKAPITU and tekst.endswith(_ZNAKI_KONCA_ZDANIA)
