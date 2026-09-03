"""Generowanie tematycznego pliku PDF z obrazami, ich opisami i tekstem OCR.

Narzędziem jest reportlab: licencja BSD-3-Clause, dojrzałość, brak wymaganego
komponentu natywnego. Decyzja piąta etapu ósmego. Odrzucone zostało fpdf2 z
powodu licencji LGPL-3.0.

Do pliku PDF osadzana jest czcionka TrueType DejaVuSans, dołączona do repozytorium
wraz z plikiem licencji w katalogu ``czcionki``. Czcionka systemu Windows nie jest
używana, żeby testy przechodziły także poza Windows.

Uwaga o dostępności, zgodnie z sekcją piętnastą i decyzją ósmą etapu ósmego:
reportlab w trybie ``SimpleDocTemplate`` nie tworzy rzeczywistej struktury
dostępności PDF. Opis obrazu jest tu więc zwykłym tekstem akapitu umieszczonym
pod obrazem, a nie tagiem alternatywnym. Nie nazywamy go tagiem alt, bo nim nie
jest.

Jeden plik PDF odpowiada jednej grupie tematycznej i zajmuje jeden slot źródła
notatnika. Podział grupy zbyt dużej na kilka plików PDF jest po stronie pakowania,
a nie tego modułu: tutaj powstaje dokładnie taki plik, jaki opisano na wejściu.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as ObrazPlatypus,
)
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)

NAZWA_CZCIONKI = "DejaVuSans"
_SCIEZKA_CZCIONKI = Path(__file__).resolve().parent / "czcionki" / "DejaVuSans.ttf"

_MARGINES = 2 * cm
_SZEROKOSC_RAMKI = A4[0] - 2 * _MARGINES
_WYSOKOSC_RAMKI = A4[1] - 2 * _MARGINES

NAGLOWEK_SEKCJI_OBRAZ = "Obraz"
KOMUNIKAT_BRAK_OBRAZU = "Obrazu nie udało się osadzić w pliku PDF."


@dataclass(frozen=True, slots=True)
class ObrazDoPdf:
    """Jeden obraz grupy wraz z materiałem tekstowym do umieszczenia w PDF.

    Pole `naglowek` to gotowy nagłówek metadanych źródła, ten sam, który trafia
    na początek pliku TXT. Pole `tresc` to opis merytoryczny wraz z sekcją tekstu
    OCR. Pole `obraz_png` to bajty obrazu do osadzenia; wartość pusta oznacza, że
    obrazu nie udało się odczytać i w PDF pojawi się o tym informacja.
    """

    naglowek: str
    tresc: str
    obraz_png: bytes | None


@dataclass(frozen=True, slots=True)
class UstawieniaPdf:
    """Ustawienia generowania PDF pochodzące z konfiguracji aplikacji."""

    jakosc_grafik: int = 85
    maksymalny_wymiar_px: int = 2600


_czcionka_zarejestrowana = False


def _zarejestruj_czcionke() -> None:
    """Rejestruje w reportlab czcionkę DejaVuSans, dokładnie raz na proces."""
    global _czcionka_zarejestrowana
    if _czcionka_zarejestrowana:
        return
    pdfmetrics.registerFont(TTFont(NAZWA_CZCIONKI, str(_SCIEZKA_CZCIONKI)))
    _czcionka_zarejestrowana = True


def zbuduj_pdf(
    tytul_dokumentu: str,
    obrazy: Sequence[ObrazDoPdf],
    ustawienia: UstawieniaPdf | None = None,
) -> bytes:
    """Buduje tematyczny plik PDF i zwraca jego bajty.

    Każdy obraz dostaje osobną stronę: nagłówek metadanych, osadzony obraz oraz
    opis merytoryczny wraz z tekstem OCR. Kolejność obrazów jest zachowana.
    """
    ustawienia = ustawienia or UstawieniaPdf()
    _zarejestruj_czcionke()

    styl_naglowka = ParagraphStyle(
        "NaglowekMetadanych",
        fontName=NAZWA_CZCIONKI,
        fontSize=8,
        leading=11,
        alignment=TA_LEFT,
    )
    styl_tytulu_sekcji = ParagraphStyle(
        "TytulSekcji",
        fontName=NAZWA_CZCIONKI,
        fontSize=12,
        leading=16,
        spaceBefore=6,
        spaceAfter=6,
    )
    styl_tresci = ParagraphStyle(
        "TrescOpisu",
        fontName=NAZWA_CZCIONKI,
        fontSize=9,
        leading=13,
        alignment=TA_LEFT,
    )

    elementy: list[object] = []
    for numer, obraz in enumerate(obrazy):
        if numer > 0:
            elementy.append(PageBreak())
        elementy.append(Preformatted(obraz.naglowek.rstrip(), styl_naglowka))
        elementy.append(Spacer(1, 0.4 * cm))
        elementy.append(Paragraph(NAGLOWEK_SEKCJI_OBRAZ, styl_tytulu_sekcji))
        elementy.append(_element_obrazu(obraz.obraz_png, ustawienia, styl_tresci))
        elementy.append(Spacer(1, 0.4 * cm))
        elementy.extend(_elementy_tresci(obraz.tresc, styl_tresci))

    bufor = io.BytesIO()
    dokument = SimpleDocTemplate(
        bufor,
        pagesize=A4,
        leftMargin=_MARGINES,
        rightMargin=_MARGINES,
        topMargin=_MARGINES,
        bottomMargin=_MARGINES,
        title=tytul_dokumentu,
    )
    dokument.build(elementy)
    return bufor.getvalue()


def _element_obrazu(
    obraz_png: bytes | None, ustawienia: UstawieniaPdf, styl_tekstu: ParagraphStyle
) -> object:
    """Buduje element osadzonego obrazu przeskalowanego do ramki strony.

    Gdy bajtów obrazu nie ma albo nie da się ich odczytać, zwracany jest akapit
    z informacją o tym, zamiast przerywać budowanie całego pliku.
    """
    if not obraz_png:
        return Paragraph(KOMUNIKAT_BRAK_OBRAZU, styl_tekstu)
    try:
        przygotowany, szerokosc, wysokosc = _przygotuj_obraz(obraz_png, ustawienia)
    except OSError:
        return Paragraph(KOMUNIKAT_BRAK_OBRAZU, styl_tekstu)

    dostepna_wysokosc = _WYSOKOSC_RAMKI * 0.7
    skala = min(_SZEROKOSC_RAMKI / szerokosc, dostepna_wysokosc / wysokosc, 1.0)
    return ObrazPlatypus(io.BytesIO(przygotowany), width=szerokosc * skala, height=wysokosc * skala)


def _przygotuj_obraz(obraz_png: bytes, ustawienia: UstawieniaPdf) -> tuple[bytes, int, int]:
    """Sprowadza obraz do RGB, ogranicza jego wymiar i zapisuje jako JPEG.

    Zapis jako JPEG z konfigurowalną jakością trzyma rozmiar tematycznego PDF
    poniżej limitu źródła notatnika. Ograniczenie dłuższego boku do
    `maksymalny_wymiar_px` robi to samo dla bardzo dużych skanów.
    """
    otwarty = Image.open(io.BytesIO(obraz_png))
    otwarty.load()
    obraz = otwarty.convert("RGB")

    dluzszy_bok = max(obraz.width, obraz.height)
    if dluzszy_bok > ustawienia.maksymalny_wymiar_px:
        wspolczynnik = ustawienia.maksymalny_wymiar_px / dluzszy_bok
        nowe = (round(obraz.width * wspolczynnik), round(obraz.height * wspolczynnik))
        obraz = obraz.resize(nowe, Image.Resampling.LANCZOS)

    bufor = io.BytesIO()
    obraz.save(bufor, format="JPEG", quality=ustawienia.jakosc_grafik, optimize=True)
    return bufor.getvalue(), obraz.width, obraz.height


def _elementy_tresci(tresc: str, styl: ParagraphStyle) -> list[object]:
    """Zamienia opis merytoryczny i tekst OCR na kolejne akapity PDF.

    Puste wiersze rozdzielają akapity. Znak nowej linii wewnątrz akapitu jest
    zamieniany na złamanie wiersza, żeby nagłówki pól opisu nie zlewały się
    w jeden ciąg.
    """
    elementy: list[object] = []
    for akapit in tresc.split("\n\n"):
        oczyszczony = akapit.strip()
        if not oczyszczony:
            continue
        bezpieczny = _escapuj(oczyszczony).replace("\n", "<br/>")
        elementy.append(Paragraph(bezpieczny, styl))
        elementy.append(Spacer(1, 0.2 * cm))
    return elementy


def _escapuj(tekst: str) -> str:
    """Escapuje znaki, które reportlab traktuje jako znaczniki wewnątrz akapitu."""
    return tekst.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
