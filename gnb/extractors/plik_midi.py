"""Adapter ekstrakcji dla plików MIDI.

Adapter jest cienką warstwą: bramkuje się na typie źródła i formacie, sprawdza
dostępność biblioteki mido, a właściwy odczyt zleca `gnb.music.midi`. Wspólną
zamianę opisu partytury na `DokumentWyekstrahowany` wykonuje pomocnik
`gnb.music.model.zbuduj_dokument_wyekstrahowany`.
"""

from __future__ import annotations

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import BladGnb, BrakNarzedzia
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.music.midi import (
    KOMUNIKAT_BRAK_BIBLIOTEKI,
    czy_dostepna_biblioteka,
    przeczytaj_midi,
)
from gnb.music.model import zbuduj_dokument_wyekstrahowany

METODA_EKSTRAKCJI = "nuty-midi"
FORMATY_MIDI = frozenset({"mid", "midi"})


class EkstraktorMidi:
    """Ekstraktor opisu partytury z plików MIDI."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_NUTY and format_zrodla in FORMATY_MIDI

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Buduje opis partytury z pliku MIDI.

        Odczyt MIDI nie ma etapu długotrwałego, więc argument `postep` jest
        przyjmowany dla zgodności z kontraktem i nie jest używany.
        """
        if not czy_dostepna_biblioteka():
            raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI, identyfikator_zrodla)
        try:
            opis = przeczytaj_midi(bajty)
        except BladGnb as blad:
            if blad.identyfikator_zrodla is None:
                blad.identyfikator_zrodla = identyfikator_zrodla
            raise
        return zbuduj_dokument_wyekstrahowany(
            identyfikator_zrodla, opis, metoda_ekstrakcji=METODA_EKSTRAKCJI
        )
