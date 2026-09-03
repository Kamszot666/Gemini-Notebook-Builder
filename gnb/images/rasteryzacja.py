"""Rasteryzacja stron pliku PDF do obrazów na potrzeby OCR.

Narzędziem jest pypdfium2: licencja zgodna z publicznym repozytorium na
Apache-2.0, gotowe koła dla Windows z dołączonymi binariami PDFium, brak
zewnętrznego programu do zainstalowania. Decyzja czwarta etapu ósmego. Odrzucone
zostały PyMuPDF z powodu licencji AGPL oraz pdf2image z powodu zależności od
zewnętrznego programu poppler.

Ten moduł zamienia każdą stronę PDF na obraz PNG. Sam nie rozpoznaje tekstu ani
nie rozstrzyga, czy PDF wymaga OCR — tym zajmuje się ekstraktor PDF. Strony są
renderowane po kolei, ponieważ biblioteka PDFium nie jest bezpieczna wątkowo;
równoległy jest dopiero sam OCR, który działa na gotowych obrazach.

Rozdzielczość rasteryzacji jest głównym regulatorem kompromisu między jakością
rozpoznania a czasem pracy i pochodzi z konfiguracji, a nie jest wpisana na
sztywno.
"""

from __future__ import annotations

import io
from collections.abc import Callable

import pypdfium2 as pdfium

from gnb.core.wyjatki import BladTrwaly

# Liczba punktów na cal w jednostce użytej wewnętrznie przez PDF. Skala
# renderowania to iloraz żądanej rozdzielczości i tej wartości.
_PUNKTOW_NA_CAL_W_PDF = 72

KOMUNIKAT_USZKODZONY_PDF = (
    "Pliku PDF nie dało się otworzyć do rasteryzacji: jest uszkodzony albo ma "
    "nieprawidłową strukturę."
)


def liczba_stron(bajty_pdf: bytes, *, identyfikator_zrodla: str | None = None) -> int:
    """Zwraca liczbę stron pliku PDF, otwierając go tylko do odczytu tej liczby."""
    dokument = _otworz(bajty_pdf, identyfikator_zrodla)
    try:
        return len(dokument)
    finally:
        dokument.close()


def rasteryzuj_strony(
    bajty_pdf: bytes,
    *,
    rozdzielczosc_dpi: int,
    identyfikator_zrodla: str | None = None,
    przy_postepie: Callable[[int, int], None] | None = None,
) -> list[bytes]:
    """Renderuje każdą stronę PDF do obrazu PNG i zwraca listę bajtów w kolejności stron.

    Argument `przy_postepie` jest wołany po każdej wyrenderowanej stronie z parą
    liczb: ile stron gotowych i ile wszystkich. Rasteryzacja jest krótsza od
    OCR, ale przy grubym skanie i tak trwa, więc postęp jest zgłaszany.
    """
    dokument = _otworz(bajty_pdf, identyfikator_zrodla)
    skala = rozdzielczosc_dpi / _PUNKTOW_NA_CAL_W_PDF
    strony_png: list[bytes] = []
    try:
        wszystkich = len(dokument)
        for numer in range(wszystkich):
            strona = dokument[numer]
            try:
                mapa_bitowa = strona.render(scale=skala)
                obraz = mapa_bitowa.to_pil()
                bufor = io.BytesIO()
                obraz.convert("RGB").save(bufor, format="PNG")
                strony_png.append(bufor.getvalue())
            finally:
                strona.close()
            if przy_postepie is not None:
                przy_postepie(numer + 1, wszystkich)
    except pdfium.PdfiumError as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY_PDF, identyfikator_zrodla) from blad
    finally:
        dokument.close()
    return strony_png


def _otworz(bajty_pdf: bytes, identyfikator_zrodla: str | None) -> pdfium.PdfDocument:
    """Otwiera dokument PDF z bajtów, zamieniając błąd biblioteki na błąd trwały."""
    try:
        return pdfium.PdfDocument(bajty_pdf)
    except pdfium.PdfiumError as blad:
        raise BladTrwaly(KOMUNIKAT_USZKODZONY_PDF, identyfikator_zrodla) from blad
