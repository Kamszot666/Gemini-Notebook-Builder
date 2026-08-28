"""Ekstrakcja tekstu z plików PDF zawierających warstwę tekstową.

Ten ekstraktor czyta wyłącznie tekst już obecny w pliku PDF. Strona zeskanowana
bez warstwy tekstowej, czyli sam obraz strony, wymaga OCR, a to jest zadanie
etapu ósmego. Z takiej strony ekstraktor nie odczyta nic, a ocena jakości
ekstrakcji z `gnb.potok` to wychwyci i oznaczy źródło jako podejrzane, zamiast
milcząco stracić treść.

PDF nie ma niezawodnie odtwarzalnej struktury dokumentu: format zapisuje tekst
jako pozycjonowane fragmenty na stronie, a nie jako drzewo nagłówków i akapitów.
Zgadywanie nagłówków z wielkości czcionki byłoby heurystyką bez pewności, więc
ekstraktor nie tworzy bloków strukturalnych i zawsze zgłasza niski poziom
pewności — sekcja ósma CLAUDE.md nie pozwala wtedy na wersję MD.

Nagłówek i numer strony powtarzane na każdej stronie zaśmiecałyby wynik,
gdyby trafiały do tekstu tyle razy, ile jest stron. Wykrywanie jest celowo
pozycyjne i ostrożne: sprawdzane są wyłącznie pierwsze dwa wiersze każdej
strony, a wiersz znika ze wszystkich stron tylko wtedy, gdy jego treść jest
identyczna na każdej z nich. Numer strony jest wykrywany wzorcem, bo jego
treść zmienia się na każdej stronie, więc porównanie tekstu by go nie
złapało. Żaden inny wiersz nie jest ruszany, więc treść merytoryczna nie
ginie nawet wtedy, gdy przypadkiem powtarza się między stronami — to zadanie
etapu piątego, deduplikacji, a nie ekstrakcji.

Plik PDF zaszyfrowany albo zabezpieczony przed kopiowaniem kończy się błędem
trwałym z czytelnym komunikatem: taki plik nie zaimportuje się także wprost do
notatnika, niezależnie od planu, więc próba odczytania go przez tę aplikację
i tak nie prowadziłaby do użytecznego wyniku.
"""

from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly

METODA_EKSTRAKCJI = "pdf"
FORMATY_PDF = frozenset({"pdf"})

# Liczba wierszy od początku strony sprawdzanych pod kątem powtarzalnego
# nagłówka. Prawdziwe nagłówki bywają jedno- albo dwuwierszowe (tytuł
# dokumentu i osobny nagłówek sekcji); dalsze wiersze nie są sprawdzane, żeby
# nie wciągnąć w to przypadkowo powtarzającej się treści akapitu.
_LICZBA_WIERSZY_NAGLOWKA_DO_SPRAWDZENIA = 2

# Wzorzec wiersza z samym numerem strony, po polsku i po angielsku, w postaci
# „Strona 3”, „3”, „3 z 10” albo „Page 3 of 10”.
_WZORZEC_NUMERU_STRONY = re.compile(
    r"^(?:strona|page|str\.)?\s*\d{1,4}(?:\s*(?:z|of|/)\s*\d{1,4})?\.?$", re.IGNORECASE
)

KOMUNIKAT_ZASZYFROWANY = (
    "Plik PDF jest zaszyfrowany albo zabezpieczony przed kopiowaniem, więc nie da "
    "się z niego odczytać tekstu. Taki plik nie zaimportuje się także wprost do "
    "notatnika, niezależnie od planu."
)
KOMUNIKAT_USZKODZONY = (
    "Plik PDF jest uszkodzony albo ma nieprawidłową strukturę i nie dał się odczytać."
)
KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ = (
    "Plik PDF nie zawiera warstwy tekstowej, prawdopodobnie jest to skan złożony "
    "z obrazów stron. Rozpoznawanie tekstu ze skanu, czyli OCR, jest zadaniem "
    "etapu ósmego."
)


class EkstraktorPdf:
    """Ekstraktor tekstu z plików PDF z warstwą tekstową."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_PDF

    def wyekstrahuj(self, identyfikator_zrodla: str, bajty: bytes) -> DokumentWyekstrahowany:
        """Odczytuje tekst każdej strony PDF i skleja go w jeden dokument."""
        try:
            czytnik = PdfReader(io.BytesIO(bajty))
            if czytnik.is_encrypted:
                raise BladTrwaly(KOMUNIKAT_ZASZYFROWANY, identyfikator_zrodla)
            strony = [strona.extract_text() or "" for strona in czytnik.pages]
        except PdfReadError as blad:
            raise BladTrwaly(KOMUNIKAT_USZKODZONY, identyfikator_zrodla) from blad

        strony = _usun_powtarzalne_naglowki_i_stopki(strony)
        tekst = "\n\n".join(strona.strip() for strona in strony if strona.strip())
        metadane = _metadane(czytnik)
        tytul = metadane.pop("tytul", None)

        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=tytul,
            metadane=metadane,
            ostrzezenia=[] if tekst.strip() else [KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ],
        )


def _usun_powtarzalne_naglowki_i_stopki(strony: list[str]) -> list[str]:
    """Usuwa z każdej strony powtarzalny nagłówek oraz wiersz numeru strony.

    Nagłówek jest wykrywany pozycyjnie i tylko wtedy, gdy jego treść jest
    identyczna na każdej stronie. Numer strony jest wykrywany wzorcem, bo jego
    treść zmienia się na każdej stronie. Dokument jednostronicowy nie ma
    z czym porównywać, więc wraca bez zmian.
    """
    if len(strony) < 2:
        return strony

    wiersze_stron = [_wiersze_bez_koncowych_pustych(strona) for strona in strony]

    liczba_wierszy_naglowka = 0
    for pozycja in range(_LICZBA_WIERSZY_NAGLOWKA_DO_SPRAWDZENIA):
        if any(len(wiersze) <= pozycja for wiersze in wiersze_stron):
            break
        wzorcowy_wiersz = wiersze_stron[0][pozycja]
        if all(wiersze[pozycja] == wzorcowy_wiersz for wiersze in wiersze_stron):
            liczba_wierszy_naglowka += 1
        else:
            break

    czy_stopka_numerem_strony = all(
        wiersze and _WZORZEC_NUMERU_STRONY.match(wiersze[-1].strip()) for wiersze in wiersze_stron
    )

    wynik: list[str] = []
    for wiersze in wiersze_stron:
        koniec = len(wiersze) - 1 if czy_stopka_numerem_strony and wiersze else len(wiersze)
        wynik.append("\n".join(wiersze[liczba_wierszy_naglowka:koniec]))
    return wynik


def _wiersze_bez_koncowych_pustych(strona: str) -> list[str]:
    """Dzieli tekst strony na wiersze, odcinając puste wiersze z samego końca."""
    wiersze = strona.split("\n")
    while wiersze and not wiersze[-1].strip():
        wiersze.pop()
    return wiersze


def _metadane(czytnik: PdfReader) -> dict[str, str]:
    """Zbiera metadane dokumentu z sekcji informacyjnej pliku PDF, jeżeli są."""
    informacje = czytnik.metadata
    if informacje is None:
        return {}
    metadane: dict[str, str] = {}
    if informacje.title and informacje.title.strip():
        metadane["tytul"] = informacje.title.strip()
    if informacje.author and informacje.author.strip():
        metadane["autor"] = informacje.author.strip()
    if informacje.creation_date is not None:
        metadane["data_publikacji"] = informacje.creation_date.strftime("%Y-%m-%d")
    return metadane
