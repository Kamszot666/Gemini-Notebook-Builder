"""Ekstrakcja tekstu z plików RTF biblioteką striprtf.

RTF jest formatem tekstowym z poleceniami sterującymi, ale jego treść trzeba
z nich wydobyć, więc plik jest traktowany jak format binarny: bajty trafiają
wprost do biblioteki, bez wykrywania kodowania znakowego. Kodowanie polskich
znaków wynika z polecenia strony kodowej zapisanego w samym pliku, na przykład
`\\ansicpg1250`, i biblioteka je uwzględnia, więc „ą” i „ż” nie zamieniają się
w inne znaki.

Biblioteka zwraca sam tekst, bez struktury: nie rozpoznaje nagłówków, a tabelę
spłaszcza do wierszy z komórkami rozdzielonymi kreską pionową. Dlatego
ekstraktor zgłasza niski poziom pewności struktury i nie tworzy bloków, a plik RTF
z tabelą dostaje ostrzeżenie, że jej struktura została uproszczona. To samo
dotyczy obrazów i obiektów osadzonych, których biblioteka nie odczytuje.

Znak zastępczy w wyniku oznacza bajt, którego nie dało się odczytać w podanym
kodowaniu, więc jego obecność też trafia do ostrzeżeń.
"""

from __future__ import annotations

import re

from striprtf.striprtf import rtf_to_text

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.bazowy import PostepEkstrakcji

METODA_EKSTRAKCJI = "rtf"
FORMATY_RTF = frozenset({"rtf"})

KOMUNIKAT_NIEPOPRAWNY = (
    "Plik nie jest poprawnym dokumentem RTF: nie zaczyna się od znacznika „{\\rtf”. "
    "Plik jest uszkodzony albo ma inny format niż wskazuje rozszerzenie."
)

_ZNAK_ZASTEPCZY = "\ufffd"
_MAKSYMALNA_DLUGOSC_TYTULU = 80
_WZORZEC_TABELI = re.compile(rb"\\trowd")
_WZORZEC_OBRAZU = re.compile(rb"\\pict\b")
_WZORZEC_OBIEKTU = re.compile(rb"\\object\b")


class EkstraktorRtf:
    """Ekstraktor plików RTF zwracający sam tekst, bez struktury."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_RTF

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Zamienia RTF na tekst akapitami rozdzielonymi pustym wierszem.

        Biblioteka rozdziela akapity pojedynczym znakiem nowej linii, a reszta
        potoku oczekuje pustego wiersza między akapitami, więc ekstraktor
        zamienia jedno na drugie. Argument `postep` nie jest używany.
        """
        if not bajty.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"{\\rtf"):
            raise BladTrwaly(KOMUNIKAT_NIEPOPRAWNY, identyfikator_zrodla)
        try:
            tekst = rtf_to_text(  # type: ignore[no-untyped-call]
                bajty.decode("latin-1"), errors="replace"
            )
        except (ValueError, KeyError, IndexError, RecursionError) as blad:
            raise BladTrwaly(
                "Nie udało się odczytać pliku RTF: plik jest uszkodzony.", identyfikator_zrodla
            ) from blad

        akapity = [wiersz.strip() for wiersz in tekst.splitlines() if wiersz.strip()]
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst="\n\n".join(akapity),
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=akapity[0][:_MAKSYMALNA_DLUGOSC_TYTULU] if akapity else None,
            ostrzezenia=_ostrzezenia(bajty, tekst),
        )


def _ostrzezenia(bajty: bytes, tekst: str) -> list[str]:
    ostrzezenia: list[str] = []
    if _WZORZEC_TABELI.search(bajty):
        ostrzezenia.append(
            "Plik RTF zawiera tabele. Biblioteka odczytu nie zachowuje ich struktury: tabele "
            "zapisano jako wiersze z komórkami rozdzielonymi kreską pionową, więc układ "
            "kolumn mógł zostać uproszczony."
        )
    obrazy = len(_WZORZEC_OBRAZU.findall(bajty))
    if obrazy:
        ostrzezenia.append(
            f"Plik RTF zawiera obrazy ({obrazy}), których treść nie została odczytana."
        )
    obiekty = len(_WZORZEC_OBIEKTU.findall(bajty))
    if obiekty:
        ostrzezenia.append(
            f"Plik RTF zawiera obiekty osadzone ({obiekty}), których treść nie została odczytana."
        )
    if _ZNAK_ZASTEPCZY in tekst:
        ostrzezenia.append(
            "W tekście są znaki zastępcze: część bajtów nie dała się odczytać w kodowaniu "
            "zapisanym w pliku."
        )
    return ostrzezenia
