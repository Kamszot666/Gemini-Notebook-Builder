"""Odczyt jednej strony: rozpoznanie z surowego obrazu i, przy słabym wyniku, z przygotowanego.

Pomiar na obrazach syntetycznych pokazał, że przygotowanie obrazu (odszumienie,
wyrównanie kontrastu, wyprostowanie, powiększenie) nie jest bezpieczne dla
każdego druku: drobny, ostry druk po filtrze medianowym bywa rozpoznawany
gorzej niż bez niego, natomiast przechylona strona albo strona o niskim
kontraście bez przygotowania nie daje żadnego tekstu. Dlatego pierwszy odczyt
zawsze idzie z surowego obrazu, a przygotowany obraz jest drugą próbą, uruchamianą
tylko wtedy, gdy średnia pewność pierwszej jest niska. Z dwóch odczytów
zostaje ten, w którym suma pewności słów jest większa, czyli taki, który
rozpoznał więcej słów z rozsądną pewnością.

Moduł nie ocenia, czy odczyt jest czytelny dla człowieka: to robi
`gnb.images.ocena_ocr`. Nie zapisuje niczego na dysku.
"""

from __future__ import annotations

import io

from PIL import Image

from gnb.images.przygotowanie import przygotuj_do_ocr
from gnb.images.tesseract import UstawieniaOcr, WynikOcrZPewnoscia, rozpoznaj_z_pewnoscia

# Średnia pewność, od której pierwszy odczyt jest uznany za dość dobry, żeby nie
# robić drugiej próby. Czysty druk daje około 95, druk średniej jakości powyżej 80,
# a pismo odręczne i obraz rozmazany poniżej 60.
PROG_PEWNOSCI_BEZ_PONOWIENIA = 85.0


def odczytaj_strone(
    obraz: Image.Image,
    ustawienia: UstawieniaOcr,
    *,
    przygotowanie_wlaczone: bool,
    identyfikator_zrodla: str | None = None,
) -> WynikOcrZPewnoscia:
    """Rozpoznaje tekst obrazu, w razie słabego wyniku ponawiając z obrazem przygotowanym."""
    pierwszy = rozpoznaj_z_pewnoscia(
        zapisz_png(obraz), ustawienia, identyfikator_zrodla=identyfikator_zrodla
    )
    if not przygotowanie_wlaczone:
        return pierwszy
    if pierwszy.liczba_slow > 0 and pierwszy.srednia_pewnosc >= PROG_PEWNOSCI_BEZ_PONOWIENIA:
        return pierwszy

    drugi = rozpoznaj_z_pewnoscia(
        zapisz_png(przygotuj_do_ocr(obraz)), ustawienia, identyfikator_zrodla=identyfikator_zrodla
    )
    return drugi if _suma_pewnosci(drugi) > _suma_pewnosci(pierwszy) else pierwszy


def zapisz_png(obraz: Image.Image) -> bytes:
    """Zapisuje obraz jako PNG w pamięci, sprowadzając go do trybu RGB."""
    bufor = io.BytesIO()
    obraz.convert("RGB").save(bufor, format="PNG")
    return bufor.getvalue()


def _suma_pewnosci(wynik: WynikOcrZPewnoscia) -> float:
    """Zwraca sumę pewności wszystkich rozpoznanych słów odczytu."""
    return wynik.srednia_pewnosc * wynik.liczba_slow
