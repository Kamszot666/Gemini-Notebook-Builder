"""Adapter ekstrakcji dla plików Guitar Pro w wersjach gp3, gp4 i gp5.

Adapter bramkuje się na typie źródła i formacie, sprawdza dostępność biblioteki
PyGuitarPro, a właściwy odczyt zleca `gnb.music.guitarpro`. Nowsze formaty gpx
i gp są odrzucane wcześniej, w warstwie przyjmowania wejścia, więc tu nie
docierają.
"""

from __future__ import annotations

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BladGnb, BrakNarzedzia
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.music.guitarpro import (
    KOMUNIKAT_BRAK_BIBLIOTEKI,
    czy_dostepna_biblioteka,
    przeczytaj_guitarpro,
)
from gnb.music.model import zbuduj_dokument_wyekstrahowany

METODA_EKSTRAKCJI = "nuty-guitarpro"
FORMATY_GUITARPRO = frozenset({"gp3", "gp4", "gp5"})


class EkstraktorGuitarPro:
    """Ekstraktor opisu partytury z plików Guitar Pro gp3, gp4 i gp5."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_NUTY and format_zrodla in FORMATY_GUITARPRO

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Buduje opis partytury z pliku Guitar Pro.

        Odczyt nie ma etapu długotrwałego, więc argument `postep` jest
        przyjmowany dla zgodności z kontraktem i nie jest używany.
        """
        if not czy_dostepna_biblioteka():
            raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI, identyfikator_zrodla)
        try:
            opis = przeczytaj_guitarpro(bajty)
        except BladGnb as blad:
            if blad.identyfikator_zrodla is None:
                blad.identyfikator_zrodla = identyfikator_zrodla
            raise
        return zbuduj_dokument_wyekstrahowany(
            identyfikator_zrodla, opis, metoda_ekstrakcji=METODA_EKSTRAKCJI
        )
