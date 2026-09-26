"""Ekstrakcja plików DOC i PPT przez konwersję programem LibreOffice.

Stare formaty binarne Office nie mają dobrej biblioteki w czystym Pythonie, więc
LibreOffice zamienia DOC na DOCX, a PPT na PPTX, i dalej pracują zwykłe
ekstraktory tych formatów. Wynik niesie ostrzeżenie, że treść przeszła przez
konwersję, bo konwersja jest przybliżeniem: układ bardzo złożonego dokumentu mógł
się zmienić, choć tekst zostaje.

Brak LibreOffice nie zatrzymuje aplikacji. Zgłaszany jest `BrakNarzedzia`, który
potok zamienia na pominięcie źródła z komunikatem mówiącym, czego zabrakło, tak
samo jak przy braku FFmpega albo Audiverisa.
"""

from __future__ import annotations

from dataclasses import replace

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.libreoffice import konwertuj, znajdz_libreoffice
from gnb.extractors.plik_docx import EkstraktorDocx
from gnb.extractors.plik_pptx import EkstraktorPptx

METODA_EKSTRAKCJI = "libreoffice"
FORMATY_LIBREOFFICE = frozenset({"doc", "ppt"})


class _EkstraktorLibreOffice:
    """Wspólny szkielet ekstraktorów DOC i PPT, korzystających z konwersji LibreOffice."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True
    _format_zrodla = ""
    _format_docelowy = ""

    def __init__(self, sciezka_libreoffice: str = "") -> None:
        self._sciezka_libreoffice = sciezka_libreoffice

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla == self._format_zrodla

    def _ekstraktor_wyniku(self) -> EkstraktorDocx | EkstraktorPptx:
        raise NotImplementedError

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Konwertuje plik i odczytuje wynik ekstraktorem DOCX albo PPTX.

        Ostrzeżenie o konwersji dołącza się do ostrzeżeń ekstraktora wyniku, więc
        trafia do logów, manifestu i raportu tą samą drogą co każde inne.
        """
        program = znajdz_libreoffice(self._sciezka_libreoffice)
        przekonwertowane = konwertuj(
            program, bajty, self._format_zrodla, self._format_docelowy, identyfikator_zrodla
        )
        dokument = self._ekstraktor_wyniku().wyekstrahuj(
            identyfikator_zrodla, przekonwertowane, postep=postep
        )
        return replace(
            dokument,
            metoda_ekstrakcji=f"{METODA_EKSTRAKCJI}+{dokument.metoda_ekstrakcji}",
            ostrzezenia=[
                *dokument.ostrzezenia,
                f"Plik {self._format_zrodla.upper()} został odczytany po konwersji programem "
                f"LibreOffice na {self._format_docelowy.upper()}. Konwersja jest przybliżeniem: "
                "tekst zostaje, ale układ złożonego dokumentu mógł się zmienić.",
            ],
        )


class EkstraktorDoc(_EkstraktorLibreOffice):
    """Ekstraktor starych dokumentów DOC: konwersja na DOCX programem LibreOffice."""

    _format_zrodla = "doc"
    _format_docelowy = "docx"

    def _ekstraktor_wyniku(self) -> EkstraktorDocx:
        return EkstraktorDocx()


class EkstraktorPpt(_EkstraktorLibreOffice):
    """Ekstraktor starych prezentacji PPT: konwersja na PPTX programem LibreOffice."""

    _format_zrodla = "ppt"
    _format_docelowy = "pptx"

    def _ekstraktor_wyniku(self) -> EkstraktorPptx:
        return EkstraktorPptx()
