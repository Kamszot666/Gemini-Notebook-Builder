"""Opis pól konfiguracji pokazywanych na stronie ustawień i odczyt wartości z formularza.

Moduł jest tablicą: dla każdego pola klasy ``Konfiguracja`` mówi, w której
zakładce leży, jak się nazywa dla użytkownika, jaką ma kontrolkę, jaki ma opis
i czy zmiana działa dopiero po ponownym uruchomieniu serwera. Zamienia też
wartości wpisane w formularz na wartości do zapisu w pliku konfiguracji.

Moduł nie buduje HTML i nie zapisuje pliku. Reguły poprawności wartości są
w ``gnb.core.konfiguracja`` i obowiązują przy zapisie; tutaj sprawdza się tylko
to, czy tekst z formularza da się zamienić na liczbę albo wartość logiczną.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from gnb.core.konfiguracja import (
    KROJE_PISMA,
    STOPNIE_CZCIONKI,
    Konfiguracja,
    pola_konfiguracji,
)
from gnb.ui.wyglad import NAZWY_KROJOW, nazwy_schematow


class Rodzaj(StrEnum):
    """Rodzaj kontrolki, jaką pole dostaje na stronie ustawień."""

    LOGICZNE = "logiczne"
    LICZBA = "liczba"
    LICZBA_RZECZYWISTA = "liczba_rzeczywista"
    WYBOR = "wybor"
    WYBOR_LICZBY = "wybor_liczby"
    TEKST = "tekst"
    LISTA = "lista"
    FORMATY = "formaty"
    TYLKO_ODCZYT = "tylko_odczyt"


@dataclass(frozen=True, slots=True)
class PoleUstawien:
    """Jedno pole konfiguracji widoczne na stronie ustawień."""

    nazwa: str
    etykieta: str
    opis: str
    rodzaj: Rodzaj
    minimum: float | None = None
    maksimum: float | None = None
    opcje: tuple[str, ...] = ()
    restart: bool = False
    # Nazwy opcji pokazywane użytkownikowi, gdy różnią się od wartości zapisywanych w pliku.
    nazwy_opcji: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Zakladka:
    """Zakładka tematyczna ze swoimi polami."""

    identyfikator: str
    tytul: str
    wstep: str
    pola: tuple[PoleUstawien, ...]


class BladWartosciUstawienia(Exception):
    """Wartość z formularza nie daje się zamienić na typ pola."""

    def __init__(self, pole: str, komunikat: str) -> None:
        super().__init__(komunikat)
        self.pole = pole
        self.komunikat = komunikat


# Modele Whisper przyjmowane przez bibliotekę faster-whisper w wersji 1.2.x
# (funkcja ``faster_whisper.available_models``), bez wariantów wyłącznie
# angielskich, bo nagrania użytkownika są po polsku. Kolejność od najmniejszego
# do największego, z modelami „turbo” obok pełnych.
MODELE_TRANSKRYPCJI = ("tiny", "base", "small", "medium", "large-v3-turbo", "large-v2", "large-v3")
TYPY_OBLICZEN_PROCESORA = ("int8", "int8_float32", "float32")
URZADZENIA_TRANSKRYPCJI = ("procesor",)

_NASTEPNY_PRZEBIEG = "Zmiana działa od następnego przebiegu."
_PO_RESTARCIE = "Zmiana działa dopiero po ponownym uruchomieniu serwera."


def _logiczne(nazwa: str, etykieta: str, opis: str, *, restart: bool = False) -> PoleUstawien:
    return PoleUstawien(nazwa, etykieta, opis, Rodzaj.LOGICZNE, restart=restart)


def _liczba(
    nazwa: str,
    etykieta: str,
    opis: str,
    *,
    minimum: float = 1,
    maksimum: float | None = None,
    restart: bool = False,
) -> PoleUstawien:
    return PoleUstawien(
        nazwa, etykieta, opis, Rodzaj.LICZBA, minimum=minimum, maksimum=maksimum, restart=restart
    )


def _rzeczywista(
    nazwa: str,
    etykieta: str,
    opis: str,
    *,
    minimum: float = 0,
    maksimum: float | None = None,
) -> PoleUstawien:
    return PoleUstawien(
        nazwa, etykieta, opis, Rodzaj.LICZBA_RZECZYWISTA, minimum=minimum, maksimum=maksimum
    )


def _tekst(nazwa: str, etykieta: str, opis: str, *, restart: bool = False) -> PoleUstawien:
    return PoleUstawien(nazwa, etykieta, opis, Rodzaj.TEKST, restart=restart)


def _lista(nazwa: str, etykieta: str, opis: str) -> PoleUstawien:
    return PoleUstawien(nazwa, etykieta, opis, Rodzaj.LISTA)


def _wybor(nazwa: str, etykieta: str, opis: str, opcje: tuple[str, ...]) -> PoleUstawien:
    return PoleUstawien(nazwa, etykieta, opis, Rodzaj.WYBOR, opcje=opcje)


def _kolor(nazwa: str, etykieta: str, rola: str) -> PoleUstawien:
    return PoleUstawien(
        nazwa,
        etykieta,
        f"Kolor {rola} przy schemacie Kolory własne. Wpisz kod w postaci #RRGGBB, na przykład "
        "#1a2b3c. Przy innym schemacie to pole nie ma skutku.",
        Rodzaj.TEKST,
    )


_NAZWY_SCHEMATOW = nazwy_schematow()


ZAKLADKI: tuple[Zakladka, ...] = (
    Zakladka(
        "limity",
        "Limity notatnika",
        "Limity liczby źródeł i wielkości plików, dopasowane do planu Gemini Notebook.",
        (
            _liczba(
                "limit_zrodel",
                "Limit liczby źródeł w notatniku",
                "Ile źródeł mieści jeden notatnik w Twoim planie. Plan Plus to 100, Standard 50, "
                "Pro 300.",
            ),
            _liczba(
                "limit_adresow_z_pliku",
                "Limit adresów z jednego pliku",
                "Ile adresów wolno dodać jako osobne źródła z jednego pliku z adresami.",
            ),
            _liczba(
                "bezpieczny_limit_slow",
                "Bezpieczny limit słów w pliku",
                "Powyżej tej liczby słów źródło jest dzielone na części. Limit notatnika to "
                "500 000 słów, margines chroni przed różnicą w liczeniu.",
            ),
            _liczba(
                "bezpieczny_limit_mb",
                "Bezpieczny limit rozmiaru pliku w megabajtach",
                "Powyżej tego rozmiaru plik wynikowy jest dzielony. Limit notatnika to 200 MB.",
            ),
        ),
    ),
    Zakladka(
        "pobieranie",
        "Pobieranie stron",
        "Sieć, plik robots.txt, pamięć podręczna i certyfikaty. Dotyczy adresów stron www.",
        (
            _tekst(
                "nazwa_klienta",
                "Nazwa klienta wysyłana do serwisów",
                "Rozpoznawalna nazwa programu w nagłówku User-Agent. Nie zmieniaj jej bez "
                "powodu, bo wskazuje autora ruchu.",
            ),
            _rzeczywista(
                "limit_czasu_sekundy",
                "Limit czasu jednego żądania w sekundach",
                "Po tylu sekundach bez odpowiedzi próba pobrania kończy się niepowodzeniem.",
                minimum=0.1,
            ),
            _liczba(
                "liczba_ponowien",
                "Liczba ponowień po błędzie przejściowym",
                "Ile razy ponowić pobranie po chwilowym błędzie sieci. Zero oznacza brak ponowień.",
                minimum=0,
            ),
            _rzeczywista(
                "podstawa_odstepu_sekundy",
                "Podstawowy odstęp między ponowieniami w sekundach",
                "Odstęp rośnie z każdą próbą, zaczynając od tej wartości.",
                minimum=0.1,
            ),
            _rzeczywista(
                "maksymalny_odstep_sekundy",
                "Największy odstęp między ponowieniami w sekundach",
                "Górna granica rosnącego odstępu.",
                minimum=0.1,
            ),
            _rzeczywista(
                "odstep_miedzy_zadaniami_sekundy",
                "Odstęp między żądaniami do tej samej domeny w sekundach",
                "Przerwa między kolejnymi pobraniami z jednego serwisu. Zero wyłącza przerwę.",
            ),
            _liczba(
                "polaczenia_na_domene",
                "Liczba równoległych połączeń na domenę",
                "Ile stron z jednego serwisu może być pobieranych naraz. Zalecane są trzy.",
            ),
            _logiczne(
                "respektuj_robots",
                "Przestrzegaj pliku robots.txt",
                "Gdy włączone, strony zablokowane w robots.txt nie są pobierane.",
            ),
            _logiczne(
                "wyjatek_robots_dla_zrodel_jawnych",
                "Pobieraj adresy wskazane jawnie mimo robots.txt",
                "Gdy włączone, adres, który sam podajesz, jest pobierany także wtedy, gdy "
                "robots.txt go blokuje. Nie dotyczy adresów znalezionych w treści.",
            ),
            _liczba(
                "maksymalny_rozmiar_pobrania_mb",
                "Największy pobierany plik w megabajtach",
                "Większe odpowiedzi serwisu są odrzucane.",
            ),
            _tekst(
                "sciezka_certyfikatow",
                "Własny plik certyfikatów PEM",
                "Pełna ścieżka pliku. Potrzebna tylko wtedy, gdy ruch przechodzi przez firmowy "
                "serwer pośredniczący albo program antywirusowy. Puste oznacza wbudowany magazyn. "
                "Weryfikacji certyfikatu nie da się wyłączyć.",
            ),
            _logiczne(
                "uzywaj_cache",
                "Używaj pamięci podręcznej pobranych stron",
                "Niezmieniona strona nie jest pobierana drugi raz.",
            ),
            _liczba(
                "maksymalny_wiek_cache_dni",
                "Najdłuższe przechowywanie strony w pamięci podręcznej w dniach",
                "Starsze wpisy są pobierane ponownie.",
            ),
            _tekst(
                "sciezka_cache",
                "Plik pamięci podręcznej",
                "Pełna ścieżka pliku bazy SQLite wspólnej dla wszystkich projektów.",
                restart=True,
            ),
            _lista(
                "dodatkowe_parametry_sledzace",
                "Dodatkowe parametry śledzące do usunięcia z adresów",
                "Nazwy parametrów adresu oddzielone przecinkami, które mają być usuwane przed "
                "porównaniem adresów. Wbudowana lista zostaje, to są dodatkowe nazwy.",
            ),
        ),
    ),
    Zakladka(
        "youtube",
        "YouTube i napisy",
        "Pobieranie napisów filmów z serwisu YouTube.",
        (
            _lista(
                "jezyki_napisow",
                "Języki napisów w kolejności preferencji",
                "Kody języków oddzielone przecinkami, na przykład pl, en.",
            ),
            _logiczne(
                "napisy_automatyczne",
                "Dopuszczaj napisy generowane automatycznie",
                "Gdy film nie ma napisów od autora, użyj napisów utworzonych automatycznie.",
            ),
            _logiczne(
                "napisy_tlumaczone",
                "Dopuszczaj napisy tłumaczone automatycznie",
                "Gdy nie ma napisów w wybranych językach, użyj tłumaczenia automatycznego.",
            ),
            _logiczne(
                "awaryjny_dowolny_jezyk",
                "Gdy brak wybranego języka, weź napisy w dowolnym języku",
                "Awaryjnie dopuszcza napisy w języku spoza listy preferencji.",
            ),
            _logiczne(
                "znaczniki_czasu",
                "Zapisuj znaczniki czasu napisów",
                "Dodaje do tekstu napisów znaczniki czasu, co zwiększa jego długość.",
            ),
        ),
    ),
    Zakladka(
        "deduplikacja",
        "Deduplikacja",
        "Wykrywanie powtórzonych źródeł. Kolejność etapów jest stała.",
        (
            _logiczne(
                "deduplikacja_hash_wlaczona",
                "Etap pierwszy: identyczna treść",
                "Wykrywa źródła o dokładnie takiej samej treści.",
            ),
            _logiczne(
                "deduplikacja_kosmetyczna_wlaczona",
                "Etap drugi: różnice kosmetyczne",
                "Pomija różnice w interpunkcji, białych znakach i wielkości liter.",
            ),
            _logiczne(
                "deduplikacja_podobienstwo_wlaczone",
                "Etap trzeci: podobieństwo tekstów",
                "Porównuje podobieństwo treści. Pewny duplikat jest usuwany z wyników.",
            ),
            _logiczne(
                "deduplikacja_embeddingi_wlaczone",
                "Etap czwarty: podobieństwo semantyczne",
                "Opcjonalne porównanie znaczeniowe. Nigdy nie usuwa źródła, tylko je oznacza "
                "do Twojej decyzji.",
            ),
            _rzeczywista(
                "deduplikacja_prog_duplikatu",
                "Próg pewnego duplikatu",
                "Liczba od 0 do 1. Podobieństwo od tej wartości w górę uznaje źródło za duplikat.",
                minimum=0.01,
                maksimum=1,
            ),
            _rzeczywista(
                "deduplikacja_prog_do_przegladu",
                "Próg pary do ręcznego rozstrzygnięcia",
                "Liczba od 0 do 1, nie wyższa niż próg duplikatu. Para o podobieństwie od tej "
                "wartości, ale poniżej progu duplikatu, zostaje w wynikach i jest oznaczona.",
                minimum=0.01,
                maksimum=1,
            ),
        ),
    ),
    Zakladka(
        "ocr",
        "OCR i obrazy",
        "Rozpoznawanie tekstu z obrazów i skanów programem Tesseract.",
        (
            _logiczne(
                "ocr_wlaczony",
                "Rozpoznawaj tekst z obrazów i skanów",
                "Gdy wyłączone, obrazy i skany PDF bez warstwy tekstu są pomijane.",
            ),
            _tekst(
                "ocr_jezyk",
                "Język rozpoznawania",
                "Kod języka Tesseracta, na przykład pol. Kilka języków łączy się znakiem plus, "
                "na przykład pol+eng.",
            ),
            _liczba(
                "ocr_psm",
                "Tryb segmentacji strony",
                "Liczba od 0 do 13 według Tesseracta. Trzy to automatyczna segmentacja.",
                minimum=0,
                maksimum=13,
            ),
            _liczba(
                "ocr_rozdzielczosc_pdf_dpi",
                "Rozdzielczość stron PDF w punktach na cal",
                "Wyższa daje lepsze rozpoznanie, ale wolniejszą pracę.",
            ),
            _liczba(
                "ocr_liczba_procesow",
                "Liczba równoległych procesów rozpoznawania",
                "Zero oznacza dobór automatyczny.",
                minimum=0,
            ),
            _tekst(
                "sciezka_tesseract",
                "Plik programu Tesseract",
                "Pełna ścieżka pliku wykonywalnego. Puste oznacza wyszukanie automatyczne.",
            ),
            _tekst(
                "sciezka_tessdata",
                "Katalog danych językowych Tesseracta",
                "Pełna ścieżka katalogu. Puste oznacza miejsce domyślne.",
            ),
        ),
    ),
    Zakladka(
        "transkrypcja",
        "Transkrypcja mowy",
        "Zamiana nagrań mowy na tekst biblioteką faster-whisper. Działa na procesorze.",
        (
            _logiczne(
                "transkrypcja_wlaczona",
                "Przepisuj nagrania mowy",
                "Gdy wyłączone, pliki audio i wideo są pomijane.",
            ),
            _wybor(
                "transkrypcja_model",
                "Model transkrypcji",
                "Wartość domyślna jest dobrana do zwykłego komputera. Model większy od domyślnego "
                "wymaga mocniejszego komputera i więcej pamięci oraz działa dużo wolniej na "
                "procesorze. Model mniejszy jest szybszy, ale mniej dokładny.",
                MODELE_TRANSKRYPCJI,
            ),
            _tekst(
                "transkrypcja_jezyk",
                "Język nagrań",
                "Kod języka, na przykład pl.",
            ),
            _wybor(
                "transkrypcja_urzadzenie",
                "Urządzenie obliczeń",
                "W tej wersji transkrypcja działa wyłącznie na procesorze.",
                URZADZENIA_TRANSKRYPCJI,
            ),
            _wybor(
                "transkrypcja_typ_obliczen",
                "Typ obliczeń",
                "Osiem bitów całkowitych jest najszybsze na procesorze. Pełna precyzja jest "
                "wolniejsza i zajmuje więcej pamięci.",
                TYPY_OBLICZEN_PROCESORA,
            ),
            _liczba(
                "transkrypcja_liczba_watkow",
                "Liczba wątków procesora",
                "Zero oznacza liczbę rdzeni minus jeden.",
                minimum=0,
            ),
            _rzeczywista(
                "transkrypcja_prog_vad",
                "Próg wykrywania mowy",
                "Liczba od 0 do 1. Wyższa wartość jest bardziej wymagająca przy wykrywaniu mowy.",
                minimum=0.01,
                maksimum=1,
            ),
            _rzeczywista(
                "transkrypcja_prog_udzialu_mowy",
                "Próg udziału mowy w nagraniu",
                "Liczba od 0 do 1. Nagranie z mniejszym udziałem mowy jest uznawane za niemowne "
                "i pomijane. Zero wyłącza to pomijanie.",
                minimum=0,
                maksimum=1,
            ),
        ),
    ),
    Zakladka(
        "nuty",
        "Nuty",
        "Materiały nutowe: zapis dźwięków oraz programy do rozpoznawania nut.",
        (
            _logiczne(
                "nuty_zapis_dzwiekow_wlaczony",
                "Zapisuj dźwięki ścieżek strunowych w opisie utworu",
                "Dotyczy plików Guitar Pro. Wyłącz dla utworu, którego opis wychodzi zbyt długi "
                "do odsłuchu.",
            ),
            _tekst(
                "sciezka_audiveris",
                "Plik programu Audiveris",
                "Pełna ścieżka. Rozpoznaje nuty z obrazów i PDF. Puste oznacza wyszukanie "
                "automatyczne.",
            ),
            _tekst(
                "sciezka_musescore",
                "Plik programu MuseScore",
                "Pełna ścieżka. Program jest tylko wykrywany przez diagnostykę, nie jest "
                "uruchamiany. Puste oznacza wyszukanie automatyczne.",
            ),
        ),
    ),
    Zakladka(
        "biurowe",
        "Formaty biurowe i archiwa ZIP",
        "Konwersja dokumentów biurowych i zabezpieczenia przy rozpakowywaniu archiwów ZIP.",
        (
            _tekst(
                "sciezka_libreoffice",
                "Plik programu LibreOffice",
                "Pełna ścieżka pliku soffice. Służy do konwersji starych formatów biurowych. "
                "Puste oznacza wyszukanie automatyczne.",
            ),
            _liczba(
                "zip_maks_plikow",
                "Największa liczba plików w archiwum ZIP",
                "Archiwum z większą liczbą plików jest pomijane.",
            ),
            _liczba(
                "zip_maks_rozmiar_mb",
                "Największy rozmiar rozpakowanego archiwum w megabajtach",
                "Zabezpieczenie przed archiwum, które po rozpakowaniu zajęłoby zbyt wiele miejsca.",
            ),
            _liczba(
                "zip_maks_stosunek_kompresji",
                "Największy stosunek kompresji w archiwum",
                "Zabezpieczenie przed tak zwaną bombą kompresyjną.",
            ),
            _liczba(
                "zip_maks_zaglebienie",
                "Największe zagłębienie archiwów w archiwach",
                "Ile poziomów archiwów zagnieżdżonych w sobie zostanie rozpakowanych.",
            ),
        ),
    ),
    Zakladka(
        "wyniki",
        "Pliki wynikowe",
        "Formaty plików dla notatnika, oryginały i ustawienia grafik oraz plików PDF.",
        (
            _tekst(
                "katalog_wynikow",
                "Katalog wyników",
                "Pełna ścieżka katalogu nadrzędnego projektów. Projekty z poprzedniego katalogu "
                "nie są przenoszone.",
                restart=True,
            ),
            PoleUstawien(
                "formaty_wynikowe",
                "Twórz także pliki Markdown",
                "Plik TXT powstaje zawsze. Gdy włączone, dokument o wyraźnej strukturze dostaje "
                "dodatkowo plik Markdown.",
                Rodzaj.FORMATY,
            ),
            _logiczne(
                "zachowuj_oryginaly",
                "Zachowuj oryginały źródeł",
                "Kopiuje pliki źródłowe do katalogu materiałów źródłowych projektu.",
            ),
            _logiczne(
                "zachowuj_odnosniki",
                "Dołącz na końcu tekstu wykaz odnośników",
                "Gdy włączone, na końcu tekstu pobranej strony powstaje sekcja z wykazem "
                "odnośników znalezionych w artykule, razem z ich adresami. Adresy w samej "
                "treści artykułu nie zależą od tego ustawienia.",
            ),
            _liczba(
                "jakosc_grafik",
                "Jakość grafik w plikach PDF",
                "Liczba od 1 do 100. Wyższa daje lepszy obraz i większy plik.",
                maksimum=100,
            ),
            _liczba(
                "maksymalny_wymiar_grafiki_px",
                "Największy bok grafiki w pikselach",
                "Większe grafiki są pomniejszane, żeby plik PDF nie przekroczył limitu.",
            ),
            _liczba(
                "maksymalny_rozmiar_pdf_mb",
                "Największy rozmiar pliku PDF w megabajtach",
                "Powyżej tej wartości plik PDF jest dzielony na części.",
            ),
        ),
    ),
    Zakladka(
        "skrot",
        "Skrót klawiszowy",
        "Globalny skrót Control plus Shift plus F12. Działa wyłącznie na Windows.",
        (
            _logiczne(
                "globalny_skrot_wlaczony",
                "Włącz globalny skrót klawiszowy",
                "Na innym systemie niż Windows to ustawienie nie ma skutku. Aktywny projekt "
                "skrótu wybierasz na stronie projektu albo na liście Projekt na stronie głównej.",
                restart=True,
            ),
        ),
    ),
    Zakladka(
        "serwer",
        "Serwer",
        "Ustawienia lokalnego serwera interfejsu.",
        (
            PoleUstawien(
                "adres_nasluchu",
                "Adres nasłuchu",
                "Tylko do odczytu. Serwer nasłuchuje wyłącznie na pętli zwrotnej, bo interfejs "
                "nie ma uwierzytelniania.",
                Rodzaj.TYLKO_ODCZYT,
                restart=True,
            ),
            _liczba(
                "port_nasluchu",
                "Port serwera",
                "Numer od 1 do 65535.",
                maksimum=65535,
                restart=True,
            ),
            _liczba(
                "limit_znakow_instrukcji_systemowej",
                "Limit znaków instrukcji systemowej notatnika",
                "Największa długość pola instrukcji systemowej na stronie projektu.",
            ),
            _liczba(
                "maksymalny_rozmiar_wysylki_mb",
                "Największy rozmiar wysyłanych plików w megabajtach",
                "Większa wysyłka z formularza jest odrzucana.",
            ),
        ),
    ),
    Zakladka(
        "wyglad",
        "Wygląd",
        "Schemat kolorów, rozmiar i krój pisma oraz własne kolory interfejsu. Zmiany działają "
        "na wszystkich stronach od następnego otwarcia strony.",
        (
            PoleUstawien(
                "wyglad_schemat",
                "Schemat kolorów",
                "Gotowy zestaw kolorów albo Kolory własne, ustawiane niżej. Każdy gotowy schemat "
                "ma kontrast tekstu co najmniej 7 do 1.",
                Rodzaj.WYBOR,
                opcje=tuple(_NAZWY_SCHEMATOW),
                nazwy_opcji=tuple(_NAZWY_SCHEMATOW.values()),
            ),
            PoleUstawien(
                "wyglad_rozmiar_czcionki",
                "Rozmiar czcionki",
                "Procent rozmiaru domyślnego. Rozmiar domyślny to 20 pikseli przy zwykłym "
                "ustawieniu przeglądarki; powiększenie strony w przeglądarce działa dodatkowo.",
                Rodzaj.WYBOR_LICZBY,
                opcje=tuple(str(stopien) for stopien in STOPNIE_CZCIONKI),
                nazwy_opcji=tuple(f"{stopien} procent" for stopien in STOPNIE_CZCIONKI),
            ),
            PoleUstawien(
                "wyglad_kroj_pisma",
                "Krój pisma",
                "Krój bez szeryfów. Jeśli wybranego kroju nie ma w systemie, strona użyje "
                "kroju systemowego.",
                Rodzaj.WYBOR,
                opcje=KROJE_PISMA,
                nazwy_opcji=tuple(NAZWY_KROJOW[kroj] for kroj in KROJE_PISMA),
            ),
            _kolor("wyglad_kolor_tla", "Kolor tła", "tła strony"),
            _kolor("wyglad_kolor_tekstu", "Kolor tekstu", "tekstu"),
            _kolor("wyglad_kolor_odnosnikow", "Kolor odnośników", "odnośników"),
            _kolor("wyglad_kolor_przycisku_tla", "Kolor tła przycisków", "tła przycisków"),
            _kolor(
                "wyglad_kolor_przycisku_tekstu", "Kolor tekstu przycisków", "tekstu na przyciskach"
            ),
            _kolor("wyglad_kolor_obramowania", "Kolor obramowań", "obramowań pól i przycisków"),
            _kolor("wyglad_kolor_fokusu", "Kolor wskaźnika fokusu", "wskaźnika fokusu"),
            _kolor("wyglad_kolor_bledu", "Kolor komunikatów o błędach", "komunikatów o błędach"),
        ),
    ),
)


def pole_ustawien(nazwa: str) -> PoleUstawien:
    """Zwraca opis pola o danej nazwie albo zgłasza ``KeyError``."""
    for zakladka in ZAKLADKI:
        for pole in zakladka.pola:
            if pole.nazwa == nazwa:
                return pole
    raise KeyError(nazwa)


def zakladka_o_identyfikatorze(identyfikator: str) -> Zakladka | None:
    for zakladka in ZAKLADKI:
        if zakladka.identyfikator == identyfikator:
            return zakladka
    return None


def pola_bez_zakladki() -> tuple[str, ...]:
    """Pola konfiguracji, które nie trafiły do żadnej zakładki (powinno być pusto)."""
    umieszczone = {pole.nazwa for zakladka in ZAKLADKI for pole in zakladka.pola}
    return tuple(nazwa for nazwa in pola_konfiguracji() if nazwa not in umieszczone)


def opis_zmiany(pole: PoleUstawien) -> str:
    """Zdanie o tym, od kiedy działa zmiana tego pola."""
    return _PO_RESTARCIE if pole.restart else _NASTEPNY_PRZEBIEG


def wartosc_domyslna_slowami(pole: PoleUstawien) -> str:
    """Wartość domyślna pola zapisana tak, żeby dało się ją przeczytać na głos."""
    return wartosc_slowami(pole, getattr(Konfiguracja(), pole.nazwa))


def wartosc_slowami(pole: PoleUstawien, wartosc: object) -> str:
    if isinstance(wartosc, bool):
        return "tak" if wartosc else "nie"
    if pole.nazwy_opcji and str(wartosc) in pole.opcje:
        return pole.nazwy_opcji[pole.opcje.index(str(wartosc))]
    if pole.rodzaj is Rodzaj.FORMATY:
        return "tak" if "md" in _jako_krotka(wartosc) else "nie"
    if isinstance(wartosc, (tuple, list)):
        return ", ".join(str(element) for element in wartosc) if wartosc else "puste"
    napis = str(wartosc)
    return napis if napis else "puste"


def wartosc_do_pola_formularza(pole: PoleUstawien, wartosc: object) -> str:
    """Wartość pola jako napis do wpisania w kontrolkę (bez kontrolek logicznych)."""
    if isinstance(wartosc, (tuple, list)):
        return ", ".join(str(element) for element in wartosc)
    return str(wartosc)


def _jako_krotka(wartosc: object) -> tuple[str, ...]:
    if isinstance(wartosc, (tuple, list)):
        return tuple(str(element) for element in wartosc)
    return (str(wartosc),)


def odczytaj_zakladke(
    zakladka: Zakladka,
    formularz: Mapping[str, str],
    zablokowane: frozenset[str],
) -> tuple[dict[str, object], list[BladWartosciUstawienia]]:
    """Zamienia wartości formularza jednej zakładki na wartości do zapisu.

    Pola zablokowane zmienną środowiskową i pola tylko do odczytu są pomijane.
    Pole logiczne nieobecne w formularzu oznacza odznaczone pole wyboru. Błędy
    zbiera na liście, żeby pokazać wszystkie naraz.
    """
    wartosci: dict[str, object] = {}
    bledy: list[BladWartosciUstawienia] = []
    for pole in zakladka.pola:
        if pole.rodzaj is Rodzaj.TYLKO_ODCZYT or pole.nazwa in zablokowane:
            continue
        try:
            wartosci[pole.nazwa] = _odczytaj_pole(pole, formularz)
        except BladWartosciUstawienia as blad:
            bledy.append(blad)
    return wartosci, bledy


def _odczytaj_pole(pole: PoleUstawien, formularz: Mapping[str, str]) -> object:
    surowa = formularz.get(pole.nazwa, "")
    if pole.rodzaj is Rodzaj.LOGICZNE:
        return pole.nazwa in formularz
    if pole.rodzaj is Rodzaj.FORMATY:
        return ("txt", "md") if pole.nazwa in formularz else ("txt",)
    if pole.rodzaj is Rodzaj.LICZBA:
        try:
            return int(surowa.strip())
        except ValueError as blad:
            raise BladWartosciUstawienia(
                pole.nazwa, f"Pole „{pole.etykieta}” musi być liczbą całkowitą."
            ) from blad
    if pole.rodzaj is Rodzaj.LICZBA_RZECZYWISTA:
        try:
            return float(surowa.strip().replace(",", "."))
        except ValueError as blad:
            raise BladWartosciUstawienia(
                pole.nazwa, f"Pole „{pole.etykieta}” musi być liczbą."
            ) from blad
    if pole.rodzaj in (Rodzaj.WYBOR, Rodzaj.WYBOR_LICZBY):
        wybrana = surowa.strip()
        if not wybrana:
            raise BladWartosciUstawienia(pole.nazwa, f"Wybierz wartość w polu „{pole.etykieta}”.")
        if pole.rodzaj is Rodzaj.WYBOR_LICZBY:
            try:
                return int(wybrana)
            except ValueError as blad:
                raise BladWartosciUstawienia(
                    pole.nazwa, f"Wybierz wartość z listy w polu „{pole.etykieta}”."
                ) from blad
        return wybrana
    if pole.rodzaj is Rodzaj.LISTA:
        elementy = [czesc.strip() for czesc in surowa.split(",")]
        return [element for element in elementy if element]
    return surowa.strip()
