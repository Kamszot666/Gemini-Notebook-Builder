"""Wspólny kontrakt ekstraktorów oraz rejestr dobierający ekstraktor do źródła.

Ekstraktor zamienia rozkodowany, jeszcze nieznormalizowany tekst źródła na
`DokumentWyekstrahowany`: tekst, opcjonalny tytuł, listę bloków strukturalnych
oraz poziom pewności rozpoznania struktury. Deklaruje też, czy zwracany tekst
zawiera znaczniki formatowania. Nowy format tekstowy dodaje się jako nową
implementację protokołu `Ekstraktor` i wpis w rejestrze, bez zmian w pozostałych
modułach potoku.

PDF, DOCX i EPUB są kontenerami binarnymi, więc nie da się ich rozkodować jako
tekst: próba wykrycia kodowania znakowego na bajtach takiego pliku dałaby
bezużyteczny wynik. Dla nich obowiązuje osobny protokół `EkstraktorBinarny`,
pracujący wprost na bajtach pliku, oraz osobny rejestr `RejestrEkstraktorowBinarnych`.
Potok rozstrzyga po formacie pliku, z którego rejestru skorzystać, zanim
w ogóle spróbuje rozkodować zawartość jako tekst.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import FormatNieobslugiwany

# Wywołanie zwrotne postępu długiej ekstrakcji, na przykład OCR skanu strona po
# stronie. Argumenty to liczba jednostek już gotowych i liczba wszystkich.
# Ekstraktory bez etapu długotrwałego po prostu go nie wołają.
PostepEkstrakcji = Callable[[int, int], None]


class Ekstraktor(Protocol):
    """Kontrakt pojedynczego adaptera ekstrakcji."""

    metoda: str

    # Prawda oznacza, że zwracany tekst zachowuje znaczniki formatowania, jak
    # w Markdown. Potok buduje wtedy dodatkowo wersję TXT bez znaczników, żeby
    # plik TXT nie był kopią pliku MD. Fałsz oznacza tekst już czysty.
    tekst_zawiera_znaczniki: bool

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        """Zwraca prawdę, jeżeli ten ekstraktor potrafi przetworzyć dane źródło.

        Argument `format_zrodla` to małą literą zapisane rozszerzenie pliku bez
        kropki albo zadeklarowany format tekstu wklejonego, na przykład ``txt``
        lub ``md``. Pusty napis oznacza brak wskazówki formatu.
        """
        ...

    def wyekstrahuj(self, identyfikator_zrodla: str, tekst: str) -> DokumentWyekstrahowany:
        """Buduje `DokumentWyekstrahowany` z rozkodowanego tekstu źródła."""
        ...


class RejestrEkstraktorow:
    """Uporządkowana lista ekstraktorów z wyborem pierwszego pasującego."""

    def __init__(self, ekstraktory: Sequence[Ekstraktor]) -> None:
        self._ekstraktory: tuple[Ekstraktor, ...] = tuple(ekstraktory)

    def dobierz(self, typ_zrodla: TypZrodla, format_zrodla: str) -> Ekstraktor:
        """Zwraca pierwszy ekstraktor obsługujący dane źródło.

        Gdy żaden ekstraktor nie pasuje, zgłasza `FormatNieobslugiwany`
        z komunikatem po polsku gotowym do pokazania użytkownikowi.
        """
        for ekstraktor in self._ekstraktory:
            if ekstraktor.obsluguje(typ_zrodla, format_zrodla):
                return ekstraktor
        raise FormatNieobslugiwany(
            f"Brak ekstraktora dla źródła typu „{typ_zrodla.value}” "
            f"w formacie „{format_zrodla or 'nieokreślony'}”."
        )


class EkstraktorBinarny(Protocol):
    """Kontrakt adaptera ekstrakcji dla formatów binarnych: PDF, DOCX i EPUB.

    W przeciwieństwie do `Ekstraktor` pracuje wprost na bajtach pliku, a nie na
    tekście już rozkodowanym.
    """

    metoda: str
    tekst_zawiera_znaczniki: bool

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        """Zwraca prawdę, jeżeli ten ekstraktor potrafi przetworzyć dane źródło."""
        ...

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Buduje `DokumentWyekstrahowany` wprost z bajtów pliku.

        Argument `postep` jest opcjonalnym wywołaniem zwrotnym do raportowania
        postępu długiego etapu, na przykład OCR skanu PDF strona po stronie.
        Ekstraktory bez takiego etapu go pomijają.
        """
        ...


class RejestrEkstraktorowBinarnych:
    """Uporządkowana lista ekstraktorów binarnych z wyborem pierwszego pasującego."""

    def __init__(self, ekstraktory: Sequence[EkstraktorBinarny]) -> None:
        self._ekstraktory: tuple[EkstraktorBinarny, ...] = tuple(ekstraktory)

    def dobierz(self, typ_zrodla: TypZrodla, format_zrodla: str) -> EkstraktorBinarny:
        """Zwraca pierwszy ekstraktor binarny obsługujący dane źródło.

        Gdy żaden ekstraktor nie pasuje, zgłasza `FormatNieobslugiwany`
        z komunikatem po polsku gotowym do pokazania użytkownikowi.
        """
        for ekstraktor in self._ekstraktory:
            if ekstraktor.obsluguje(typ_zrodla, format_zrodla):
                return ekstraktor
        raise FormatNieobslugiwany(
            f"Brak ekstraktora binarnego dla źródła typu „{typ_zrodla.value}” "
            f"w formacie „{format_zrodla or 'nieokreślony'}”."
        )


def domyslny_rejestr_binarny(
    ustawienia_ocr: object | None = None,
    *,
    ocr_wlaczony: bool = False,
    ustawienia_transkrypcji: object | None = None,
    transkrypcja_wlaczona: bool = False,
    prog_udzialu_mowy: float = 0.5,
    wymus_transkrypcje: bool = False,
) -> RejestrEkstraktorowBinarnych:
    """Buduje rejestr ekstraktorów formatów binarnych: PDF, DOCX, EPUB, obrazów i audio.

    Ekstraktor obrazów oraz ekstraktor PDF potrzebują ustawień OCR i informacji,
    czy OCR jest w ogóle włączony. Ekstraktor audio potrzebuje ustawień
    transkrypcji, informacji, czy transkrypcja jest włączona, progu udziału mowy
    oraz flagi wymuszenia transkrypcji dla materiału niemownego. Wszystkie te
    wartości pochodzą z konfiguracji projektu i z opcji wiersza poleceń. Gdy nie
    podano ustawień, OCR i transkrypcja są wyłączone.
    """
    from gnb.audio.transkrypcja import UstawieniaTranskrypcji
    from gnb.extractors.plik_audio import EkstraktorAudio
    from gnb.extractors.plik_docx import EkstraktorDocx
    from gnb.extractors.plik_epub import EkstraktorEpub
    from gnb.extractors.plik_obraz import EkstraktorObrazu
    from gnb.extractors.plik_pdf import EkstraktorPdf
    from gnb.images.tesseract import UstawieniaOcr

    ustawienia = ustawienia_ocr if isinstance(ustawienia_ocr, UstawieniaOcr) else UstawieniaOcr()
    ustawienia_audio = (
        ustawienia_transkrypcji
        if isinstance(ustawienia_transkrypcji, UstawieniaTranskrypcji)
        else UstawieniaTranskrypcji()
    )
    return RejestrEkstraktorowBinarnych(
        (
            EkstraktorPdf(ustawienia, ocr_wlaczony=ocr_wlaczony),
            EkstraktorDocx(),
            EkstraktorEpub(),
            EkstraktorObrazu(ustawienia, ocr_wlaczony=ocr_wlaczony),
            EkstraktorAudio(
                ustawienia_audio,
                transkrypcja_wlaczona=transkrypcja_wlaczona,
                prog_udzialu_mowy=prog_udzialu_mowy,
                wymus_transkrypcje=wymus_transkrypcje,
            ),
        )
    )


def domyslny_rejestr(zachowuj_odnosniki: bool = True) -> RejestrEkstraktorow:
    """Buduje rejestr ekstraktorów tekstowych: tekstu, Markdown, CSV, napisów
    plikowych oraz stron internetowych i plików HTML.

    Ekstraktor Markdown jest przed ekstraktorem tekstu płaskiego, żeby źródło
    z formatem ``md`` trafiło do właściwego adaptera także wtedy, gdy jest
    tekstem wklejonym. Ekstraktor stron internetowych rozpoznaje własny typ
    źródła, więc jego miejsce w kolejności nie ma znaczenia. To samo dotyczy
    ekstraktorów CSV i napisów, bo rozpoznają swój format po rozszerzeniu.

    Argument `zachowuj_odnosniki` pochodzi z konfiguracji i decyduje o tym, czy
    na końcu treści artykułu powstaje wykaz odnośników.
    """
    from gnb.extractors.markdown import EkstraktorMarkdown
    from gnb.extractors.napisy import EkstraktorNapisow
    from gnb.extractors.plik_csv import EkstraktorCsv
    from gnb.extractors.strona_www import EkstraktorStronyWww
    from gnb.extractors.tekst import EkstraktorTekstu

    return RejestrEkstraktorow(
        (
            EkstraktorStronyWww(zachowuj_odnosniki=zachowuj_odnosniki),
            EkstraktorMarkdown(),
            EkstraktorCsv(),
            EkstraktorNapisow(),
            EkstraktorTekstu(),
        )
    )
