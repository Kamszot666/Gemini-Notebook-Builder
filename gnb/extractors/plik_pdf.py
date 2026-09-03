"""Ekstrakcja tekstu z plików PDF: warstwa tekstowa, a przy jej braku OCR skanu.

Ekstraktor najpierw czyta tekst już obecny w pliku PDF. Gdy pliku nie da się tak
odczytać — bo jest to skan złożony z obrazów stron — i OCR jest włączony w
konfiguracji, każda strona jest rasteryzowana przez pypdfium2 i rozpoznawana
przez Tesseract, a wynik składany w jeden tekst z zachowaniem numerów stron.
Tekst z OCR zawsze dostaje ostrzeżenie kierujące go do sekcji „Materiały do
sprawdzenia”, bo rozpoznanie skanu bywa niedokładne.

Gdy OCR jest wyłączony albo nie ma Tesseracta, ze skanu nie powstaje żadna
treść, a ocena jakości ekstrakcji z `gnb.potok` to wychwyci i oznaczy źródło
jako podejrzane, zamiast milcząco stracić treść.

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
from gnb.core.wyjatki import BladTrwaly, BrakNarzedzia
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.images.ocena_ocr import ocen_ocr
from gnb.images.rasteryzacja import rasteryzuj_strony
from gnb.images.tesseract import UstawieniaOcr, czy_dostepny, rozpoznaj_wiele

METODA_EKSTRAKCJI = "pdf"
METODA_EKSTRAKCJI_OCR = "pdf-ocr"
FORMATY_PDF = frozenset({"pdf"})

# Najmniejsza liczba znaków warstwy tekstowej, przy której plik jest uznawany za
# dokument z tekstem, a nie za skan. Kilka znaków to zwykle sam artefakt, na
# przykład numer strony wstawiony jako tekst na skan.
_PROG_WARSTWY_TEKSTOWEJ_ZNAKI = 20

NAGLOWEK_STRONY_OCR = "Strona {numer}:"
OSTRZEZENIE_TEKST_Z_OCR = (
    "Tekst tego pliku PDF pochodzi z OCR skanu, więc może zawierać błędy "
    "rozpoznania. Warto porównać go z oryginałem przed wgraniem do notatnika."
)
OSTRZEZENIE_OCR_BEZ_TESSERACTA = (
    "Plik PDF nie ma warstwy tekstowej, a OCR jest włączony, ale nie znaleziono "
    "programu Tesseract. Skan zapisano bez rozpoznanego tekstu."
)

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
    "z obrazów stron. Włącz OCR w konfiguracji i zainstaluj Tesseract, żeby "
    "rozpoznać tekst ze skanu."
)


class EkstraktorPdf:
    """Ekstraktor tekstu z plików PDF: warstwa tekstowa, a przy jej braku OCR skanu."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def __init__(
        self,
        ustawienia_ocr: UstawieniaOcr | None = None,
        *,
        ocr_wlaczony: bool = False,
    ) -> None:
        self._ustawienia_ocr = ustawienia_ocr or UstawieniaOcr()
        self._ocr_wlaczony = ocr_wlaczony

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_PDF

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Odczytuje tekst PDF z warstwy tekstowej, a przy jej braku z OCR skanu."""
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

        if len(tekst.strip()) >= _PROG_WARSTWY_TEKSTOWEJ_ZNAKI:
            return DokumentWyekstrahowany(
                identyfikator_zrodla=identyfikator_zrodla,
                tekst=tekst,
                poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
                metoda_ekstrakcji=METODA_EKSTRAKCJI,
                tytul=tytul,
                metadane=metadane,
                ostrzezenia=[],
            )

        return self._wyekstrahuj_skan(identyfikator_zrodla, bajty, metadane, tytul, postep)

    def _wyekstrahuj_skan(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        metadane: dict[str, str],
        tytul: str | None,
        postep: PostepEkstrakcji | None,
    ) -> DokumentWyekstrahowany:
        """Rasteryzuje strony skanu i rozpoznaje z nich tekst, gdy OCR jest włączony."""

        def pusty(ostrzezenie: str) -> DokumentWyekstrahowany:
            return _pusty_skan(identyfikator_zrodla, metadane, tytul, ostrzezenie)

        if not self._ocr_wlaczony:
            return pusty(KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ)
        if not czy_dostepny(self._ustawienia_ocr.sciezka_tesseract):
            return pusty(OSTRZEZENIE_OCR_BEZ_TESSERACTA)

        strony_png = rasteryzuj_strony(
            bajty,
            rozdzielczosc_dpi=self._ustawienia_ocr.rozdzielczosc_pdf_dpi,
            identyfikator_zrodla=identyfikator_zrodla,
        )
        try:
            teksty_stron = rozpoznaj_wiele(
                strony_png,
                self._ustawienia_ocr,
                przy_postepie=postep,
                identyfikator_zrodla=identyfikator_zrodla,
            )
        except BrakNarzedzia:
            return pusty(OSTRZEZENIE_OCR_BEZ_TESSERACTA)

        tekst = _zloz_strony_skanu(teksty_stron)
        if not tekst.strip():
            return pusty(KOMUNIKAT_BEZ_WARSTWY_TEKSTOWEJ)

        ostrzezenia = [OSTRZEZENIE_TEKST_Z_OCR]
        ocena = ocen_ocr(tekst)
        if ocena.czy_wymaga_sprawdzenia:
            ostrzezenia.extend(ocena.powody)

        metadane_skanu = {
            **metadane,
            "ocr_wykonany": "tak",
            "liczba_stron_skanu": str(len(strony_png)),
        }
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI_OCR,
            tytul=tytul,
            metadane=metadane_skanu,
            ostrzezenia=ostrzezenia,
        )


def _pusty_skan(
    identyfikator_zrodla: str,
    metadane: dict[str, str],
    tytul: str | None,
    ostrzezenie: str,
) -> DokumentWyekstrahowany:
    """Buduje wynik dla skanu, z którego nie powstał żaden tekst."""
    return DokumentWyekstrahowany(
        identyfikator_zrodla=identyfikator_zrodla,
        tekst="",
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
        metoda_ekstrakcji=METODA_EKSTRAKCJI,
        tytul=tytul,
        metadane={**metadane, "ocr_wykonany": "nie"},
        ostrzezenia=[ostrzezenie],
    )


def _zloz_strony_skanu(teksty_stron: list[str]) -> str:
    """Skleja rozpoznane strony w jeden tekst z nagłówkiem numeru strony przed każdą."""
    czesci: list[str] = []
    for numer, tekst_strony in enumerate(teksty_stron, start=1):
        oczyszczony = tekst_strony.strip()
        if not oczyszczony:
            continue
        czesci.append(f"{NAGLOWEK_STRONY_OCR.format(numer=numer)}\n{oczyszczony}")
    return "\n\n".join(czesci)


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
