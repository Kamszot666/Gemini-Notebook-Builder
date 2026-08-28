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

Plik PDF zaszyfrowany albo zabezpieczony przed kopiowaniem kończy się błędem
trwałym z czytelnym komunikatem: taki plik nie zaimportuje się także wprost do
notatnika, niezależnie od planu, więc próba odczytania go przez tę aplikację
i tak nie prowadziłaby do użytecznego wyniku.
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly

METODA_EKSTRAKCJI = "pdf"
FORMATY_PDF = frozenset({"pdf"})

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
