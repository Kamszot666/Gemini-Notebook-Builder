"""Odczyt jednej strony: surowy obraz, obrót strony i obraz przygotowany.

Pomiar na obrazach syntetycznych pokazał, że przygotowanie obrazu (odszumienie,
wyrównanie kontrastu, wyprostowanie, powiększenie) nie jest bezpieczne dla
każdego druku: drobny, ostry druk po filtrze medianowym bywa rozpoznawany
gorzej niż bez niego, natomiast przechylona strona albo strona o niskim
kontraście bez przygotowania nie daje żadnego tekstu. Dlatego pierwszy odczyt
zawsze idzie z surowego obrazu, a dalsze próby są uruchamiane tylko wtedy, gdy
średnia pewność pierwszej jest niska. Z kandydatów zostaje ten, w którym suma
pewności słów jest największa, czyli taki, który rozpoznał więcej słów
z rozsądną pewnością. Dobre strony nie płacą za nic więcej.

Próby przy słabym pierwszym odczycie, w tej kolejności:

1. Obrót o 90, 180 albo 270 stopni, gdy tak wskazuje wykrywanie orientacji
   Tesseracta. Kartka położona pod statywem bywa obrócona, a znacznik EXIF telefonu
   tego nie pokazuje. Podpowiedzi orientacji się nie ufa: obrócony odczyt jest tylko
   kandydatem i musi wygrać pewnością, więc błędna podpowiedź nie pogorszy wyniku.
2. Gdy po tym najlepszy odczyt nadal jest pusty albo ma pewność poniżej progu bez
   ponowienia (podpowiedź błędna, wskazała 0, nie dała wyniku albo nie ma pliku
   ``osd.traineddata``), sprawdzane są po kolei pozostałe obroty o 90, 180 i 270
   stopni, których jeszcze nie odczytano.
3. Odczyt z obrazu przygotowanego (już obróconego), jeśli przygotowanie jest włączone.

Moduł nie ocenia, czy odczyt jest czytelny dla człowieka: to robi
`gnb.images.ocena_ocr`. Nie zapisuje niczego na dysku.
"""

from __future__ import annotations

import dataclasses
import io

from PIL import Image, ImageOps

from gnb.images.obrot_strony import (
    KATY_OBROTU_STOPNIE,
    OSTRZEZENIE_BRAK_DANYCH_ORIENTACJI,
    dane_orientacji_dostepne,
    obroc_zgodnie_z_zegarem,
    wykryj_obrot_osd,
)
from gnb.images.przygotowanie import przygotuj_do_ocr
from gnb.images.tesseract import UstawieniaOcr, WynikOcrZPewnoscia, rozpoznaj_z_pewnoscia

# Średnia pewność, od której pierwszy odczyt jest uznany za dość dobry, żeby nie
# robić dalszych prób. Czysty druk daje około 95, druk średniej jakości powyżej 80,
# a pismo odręczne i obraz rozmazany poniżej 60.
PROG_PEWNOSCI_BEZ_PONOWIENIA = 85.0


def odczytaj_strone(
    obraz: Image.Image,
    ustawienia: UstawieniaOcr,
    *,
    przygotowanie_wlaczone: bool,
    identyfikator_zrodla: str | None = None,
) -> WynikOcrZPewnoscia:
    """Rozpoznaje tekst obrazu, w razie słabego wyniku próbując obrotu i przygotowania.

    Wynik niesie kąt obrotu zastosowanego przed odczytem oraz ostrzeżenia, które
    wołający ma przekazać dalej do logu, manifestu i raportu.
    """
    # Obrót zapisany w znaczniku EXIF stosowany jest przed każdym odczytem, żeby
    # pierwszy i dalsze odczyty widziały ten sam obraz.
    obraz = ImageOps.exif_transpose(obraz) or obraz

    def odczytaj(do_odczytu: Image.Image, kat: int) -> WynikOcrZPewnoscia:
        wynik = rozpoznaj_z_pewnoscia(
            zapisz_png(do_odczytu), ustawienia, identyfikator_zrodla=identyfikator_zrodla
        )
        return dataclasses.replace(wynik, obrot_stopnie=kat)

    pierwszy = odczytaj(obraz, 0)
    if not _jest_slaby(pierwszy):
        return pierwszy

    ostrzezenia: list[str] = []
    kandydaci: list[tuple[WynikOcrZPewnoscia, Image.Image]] = [(pierwszy, obraz)]

    kat_osd: int | None = None
    if dane_orientacji_dostepne(ustawienia.sciezka_tesseract, ustawienia.sciezka_tessdata):
        kat_osd = wykryj_obrot_osd(zapisz_png(obraz), ustawienia)
    else:
        ostrzezenia.append(OSTRZEZENIE_BRAK_DANYCH_ORIENTACJI)

    sprawdzone_katy = {0}
    if kat_osd in KATY_OBROTU_STOPNIE:
        assert kat_osd is not None
        obrocony = obroc_zgodnie_z_zegarem(obraz, kat_osd)
        kandydaci.append((odczytaj(obrocony, kat_osd), obrocony))
        sprawdzone_katy.add(kat_osd)

    # Podpowiedź orientacji na słabych stronach bywa błędna (zły kąt albo 0 dla
    # strony obróconej), więc gdy najlepszy dotąd odczyt nadal jest słaby, sprawdzane
    # są wszystkie pozostałe obroty. Strona poprawiona obrotem według OSD do progu
    # i wyżej nie płaci za dodatkowe odczyty.
    if _jest_slaby(_najlepszy(kandydaci)[0]):
        for kat in KATY_OBROTU_STOPNIE:
            if kat in sprawdzone_katy:
                continue
            obrocony = obroc_zgodnie_z_zegarem(obraz, kat)
            kandydaci.append((odczytaj(obrocony, kat), obrocony))

    if przygotowanie_wlaczone:
        najlepszy, obraz_najlepszego = _najlepszy(kandydaci)
        kandydaci.append(
            (odczytaj(przygotuj_do_ocr(obraz_najlepszego), najlepszy.obrot_stopnie), obraz)
        )

    wynik, _ = _najlepszy(kandydaci)
    return dataclasses.replace(wynik, ostrzezenia=tuple(ostrzezenia))


def _jest_slaby(wynik: WynikOcrZPewnoscia) -> bool:
    """Mówi, czy odczyt jest pusty albo ma średnią pewność poniżej progu bez ponowienia."""
    return wynik.liczba_slow == 0 or wynik.srednia_pewnosc < PROG_PEWNOSCI_BEZ_PONOWIENIA


def zapisz_png(obraz: Image.Image) -> bytes:
    """Zapisuje obraz jako PNG w pamięci, sprowadzając go do trybu RGB."""
    bufor = io.BytesIO()
    obraz.convert("RGB").save(bufor, format="PNG")
    return bufor.getvalue()


def _najlepszy(
    kandydaci: list[tuple[WynikOcrZPewnoscia, Image.Image]],
) -> tuple[WynikOcrZPewnoscia, Image.Image]:
    """Zwraca kandydata z największą sumą pewności słów; przy remisie wcześniejszego."""
    najlepszy = kandydaci[0]
    for kandydat in kandydaci[1:]:
        if _suma_pewnosci(kandydat[0]) > _suma_pewnosci(najlepszy[0]):
            najlepszy = kandydat
    return najlepszy


def _suma_pewnosci(wynik: WynikOcrZPewnoscia) -> float:
    """Zwraca sumę pewności wszystkich rozpoznanych słów odczytu."""
    return wynik.srednia_pewnosc * wynik.liczba_slow
