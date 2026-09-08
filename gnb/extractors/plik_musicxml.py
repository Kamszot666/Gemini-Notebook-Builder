"""Adapter ekstrakcji dla plików MusicXML oraz skompresowanego kontenera MXL.

Adapter bramkuje się na typie źródła i formacie, a właściwy odczyt zleca
`gnb.music.musicxml`. Rozpoznanie, czy plik jest gołym XML, czy archiwum MXL,
robi sam parser na podstawie zawartości — adapter go nie dotyczy. MusicXML
czyta biblioteka standardowa, więc nie ma tu sprawdzania dostępności zależności.
"""

from __future__ import annotations

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BladGnb
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.music.model import zbuduj_dokument_wyekstrahowany
from gnb.music.musicxml import przeczytaj_musicxml

METODA_EKSTRAKCJI = "nuty-musicxml"
FORMATY_MUSICXML = frozenset({"musicxml", "mxl"})


class EkstraktorMusicXml:
    """Ekstraktor opisu partytury z plików MusicXML i kontenera MXL."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_NUTY and format_zrodla in FORMATY_MUSICXML

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Buduje opis partytury z pliku MusicXML albo kontenera MXL.

        Odczyt nie ma etapu długotrwałego, więc argument `postep` jest
        przyjmowany dla zgodności z kontraktem i nie jest używany.
        """
        try:
            opis = przeczytaj_musicxml(bajty)
        except BladGnb as blad:
            if blad.identyfikator_zrodla is None:
                blad.identyfikator_zrodla = identyfikator_zrodla
            raise
        return zbuduj_dokument_wyekstrahowany(
            identyfikator_zrodla, opis, metoda_ekstrakcji=METODA_EKSTRAKCJI
        )
