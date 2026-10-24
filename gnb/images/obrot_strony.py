"""Wykrywanie obrotu strony o 90, 180 albo 270 stopni przed rozpoznaniem tekstu.

Kartka położona pod statywem bywa obrócona, a znacznik EXIF telefonu tego nie
pokazuje, bo telefon stał prosto. Przygotowanie obrazu prostuje tylko przechył do
kilku stopni, więc odczyt obróconej strony jest bełkotem o pewności około 40.

Ten moduł pyta o orientację strony Tesseracta w trybie wykrywania orientacji
(``--psm 0``, dane ``osd.traineddata``) i obraca obraz o wskazany kąt. Nie decyduje,
czy obrót poprawił odczyt: wołający porównuje pewność odczytów, bo podpowiedź
orientacji bywa błędna na stronach z małą ilością tekstu.
"""

from __future__ import annotations

import re
import subprocess
from functools import lru_cache

from PIL import Image

from gnb.core.wyjatki import BrakNarzedzia
from gnb.images.tesseract import UstawieniaOcr, dostepne_jezyki, znajdz_tesseract

# Kąty obrotu, które Tesseract może wskazać. Zero oznacza stronę prostą.
KATY_OBROTU_STOPNIE = (90, 180, 270)

# Górny limit czasu jednego wywołania wykrywania orientacji. Wykrycie działa na
# całej stronie, ale jest wielokrotnie szybsze od rozpoznania tekstu.
_LIMIT_CZASU_OSD_SEKUNDY = 60

_WZORZEC_OBROTU = re.compile(r"^Rotate:\s*(\d+)\s*$", re.MULTILINE)

NAZWA_DANYCH_ORIENTACJI = "osd"

OSTRZEZENIE_BRAK_DANYCH_ORIENTACJI = (
    "Tesseract nie ma pliku danych orientacji osd.traineddata, więc nie wykrywa obrotu "
    "strony. Odczyt słabej strony sprawdza obroty o 90, 180 i 270 stopni po kolei, co "
    "jest wolniejsze. Dograj plik osd.traineddata obok pol.traineddata."
)


def obroc_zgodnie_z_zegarem(obraz: Image.Image, stopnie: int) -> Image.Image:
    """Obraca obraz o podany kąt zgodnie z ruchem wskazówek zegara, powiększając płótno.

    Pillow liczy kąty przeciwnie do ruchu wskazówek zegara, dlatego kąt ma znak
    minus. Pomylony kierunek daje bełkot zamiast odczytu, więc ten znak pilnuje test.
    """
    return obraz.rotate(-stopnie, expand=True, fillcolor=(255, 255, 255))


@lru_cache(maxsize=8)
def dane_orientacji_dostepne(sciezka_tesseract: str, sciezka_tessdata: str) -> bool:
    """Prawda, gdy Tesseract ma dane orientacji ``osd``. Wynik jest pamiętany."""
    return NAZWA_DANYCH_ORIENTACJI in dostepne_jezyki(sciezka_tesseract, sciezka_tessdata)


def wykryj_obrot_osd(obraz_png: bytes, ustawienia: UstawieniaOcr) -> int | None:
    """Zwraca kąt, o jaki trzeba obrócić obraz zgodnie z zegarem, albo nic bez wyniku.

    Zwraca 0, 90, 180 albo 270. Brak wyniku oznacza: za mało znaków na stronie, kod
    błędu Tesseracta, przekroczenie limitu czasu albo brak programu. Brak pliku danych
    orientacji sprawdza osobno `dane_orientacji_dostepne`.
    """
    try:
        program = znajdz_tesseract(ustawienia.sciezka_tesseract)
    except BrakNarzedzia:
        return None
    polecenie = [str(program), "stdin", "stdout", "--psm", "0", "-l", NAZWA_DANYCH_ORIENTACJI]
    if ustawienia.sciezka_tessdata:
        polecenie.extend(["--tessdata-dir", ustawienia.sciezka_tessdata])
    try:
        wynik = subprocess.run(
            polecenie,
            input=obraz_png,
            capture_output=True,
            timeout=_LIMIT_CZASU_OSD_SEKUNDY,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if wynik.returncode != 0:
        return None
    dopasowanie = _WZORZEC_OBROTU.search(wynik.stdout.decode("utf-8", errors="replace"))
    if dopasowanie is None:
        return None
    kat = int(dopasowanie.group(1))
    return kat if kat in (0, *KATY_OBROTU_STOPNIE) else None
