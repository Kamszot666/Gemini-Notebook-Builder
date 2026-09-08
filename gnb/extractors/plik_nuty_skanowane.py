"""Adapter ekstrakcji dla zapisu nutowego w postaci obrazu albo pliku PDF.

W części A etapu dziesiątego ten adapter nie rozpoznaje notacji — zawsze kończy
się kontrolowanym pominięciem z komunikatem, że rozpoznawanie zapisu nutowego
z obrazu wymaga programu Audiveris i zostanie dodane w drugiej części etapu.
Oryginał pliku jest wcześniej zachowywany przez potok w materiałach źródłowych
projektu, więc nic nie przepada.

Granica między częścią A i częścią B wypada dokładnie na tym pliku: w części B
staje się on adapterem Audiverisa.
"""

from __future__ import annotations

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import TypZrodla
from gnb.core.wyjatki import PominietoZrodlo
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.plik_obraz import FORMATY_OBRAZOW

METODA_EKSTRAKCJI = "nuty-skanowane"
FORMATY_NUTY_SKANOWANE = frozenset({"pdf"}) | FORMATY_OBRAZOW

KOMUNIKAT_AUDIVERIS = (
    "Ten plik to zapis nutowy w postaci obrazu albo dokumentu PDF. Rozpoznawanie "
    "notacji z obrazu wymaga programu Audiveris i zostanie dodane w drugiej "
    "części etapu dziesiątego. Na razie plik został pominięty; jego oryginał "
    "zachowano w materiałach źródłowych projektu."
)


class EkstraktorNutSkanowanych:
    """Adapter zapisu nutowego z obrazu i PDF. W części A zawsze pomija źródło."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_NUTY and format_zrodla in FORMATY_NUTY_SKANOWANE

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Zawsze zgłasza `PominietoZrodlo` z komunikatem o Audiverisie."""
        raise PominietoZrodlo(KOMUNIKAT_AUDIVERIS, identyfikator_zrodla)
