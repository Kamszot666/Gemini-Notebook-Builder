"""Ocena jakości tekstu rozpoznanego przez OCR.

Wynik OCR pusty albo złożony ze śmieci wygląda w plikach wynikowych tak samo jak
poprawny: obraz ma opis, ma wpis w manifeście. To jest cicha utrata treści, czyli
naruszenie drugiego priorytetu z sekcji czwartej CLAUDE.md. Ten moduł odpowiada
za to samo co ocena jakości ekstrakcji z etapu czwartego A, tylko dla tekstu
z obrazu: pozwala taki przypadek zauważyć bez oglądania każdego pliku.

Ocena jest jedną z trzech. „poprawna” oznacza tekst nadający się do notatnika.
„pusta” oznacza brak jakiegokolwiek rozpoznanego tekstu — to nie zawsze błąd,
bo zdjęcie może po prostu nie zawierać napisów, ale użytkownik ma o tym wiedzieć.
„podejrzana” oznacza tekst rozpoznany, ale wyglądający na przekłamany: dużo
znaków nietekstowych albo dużo słów bez samogłosek, typowych dla OCR obrazu
o niskiej jakości albo obrazu, który wcale nie zawiera tekstu.

Heurystyki są zachowawcze. Fałszywe podejrzenie kosztuje jedno zajrzenie do
pliku, a przeoczony bełkot w bazie wiedzy kosztuje jej wiarygodność.
"""

from __future__ import annotations

from dataclasses import dataclass

from gnb.core.liczenie_slow import policz_slowa

OCENA_OCR_POPRAWNA = "poprawna"
OCENA_OCR_PUSTA = "pusta"
OCENA_OCR_PODEJRZANA = "podejrzana"

# Minimalna liczba słów zawierających literę, przy której w ogóle sprawdzany jest
# udział słów bez samogłoski. Na krótszym tekście ten wskaźnik jest zbyt czuły:
# pojedynczy skrót albo symbol fałszywie przechyliłby ocenę.
_MINIMALNA_LICZBA_SLOW_DO_OCENY_SAMOGLOSEK = 6

# Największy dopuszczalny udział znaków spoza zbioru znaków tekstowych, liczony
# na tekście bez spacji. Powyżej tego progu tekst uznajemy za przekłamany.
_PROG_UDZIALU_ZNAKOW_NIETEKSTOWYCH = 0.25

# Najmniejszy dopuszczalny udział słów z samogłoską wśród słów zawierających
# literę. Poniżej tego progu tekst wygląda na błędny odczyt kształtów zamiast
# liter.
_PROG_UDZIALU_SLOW_Z_SAMOGLOSKA = 0.6

_SAMOGLOSKI = set("aeiouyąęó")
_ZNAKI_TEKSTOWE_DODATKOWE = set(" \n\t.,;:!?()[]{}-–—…„”\"'«»/%°№#&@+=*")

POWOD_PUSTY = "OCR nie rozpoznał żadnego tekstu na obrazie"
POWOD_ZNAKI_NIETEKSTOWE = (
    "rozpoznany tekst ma wysoki udział znaków nietekstowych ({udzial} procent), "
    "co jest typowe dla obrazu bez czytelnego pisma"
)
POWOD_SLOWA_BEZ_SAMOGLOSEK = (
    "wśród rozpoznanych słów mało jest słów z samogłoską ({udzial} procent), "
    "co jest typowe dla błędnego odczytu kształtów zamiast liter"
)


@dataclass(frozen=True, slots=True)
class OcenaOcr:
    """Wynik oceny jakości jednego przebiegu OCR."""

    ocena: str
    powody: tuple[str, ...] = ()

    @property
    def czy_wymaga_sprawdzenia(self) -> bool:
        """Prawda, gdy wynik OCR ma trafić do sekcji „Materiały do sprawdzenia”."""
        return self.ocena in (OCENA_OCR_PUSTA, OCENA_OCR_PODEJRZANA)


def ocen_ocr(tekst: str) -> OcenaOcr:
    """Ocenia jakość rozpoznanego tekstu i zwraca ocenę wraz z powodami."""
    if policz_slowa(tekst) == 0:
        return OcenaOcr(ocena=OCENA_OCR_PUSTA, powody=(POWOD_PUSTY,))

    powody: list[str] = []

    udzial_nietekstowych = _udzial_znakow_nietekstowych(tekst)
    if udzial_nietekstowych > _PROG_UDZIALU_ZNAKOW_NIETEKSTOWYCH:
        powody.append(POWOD_ZNAKI_NIETEKSTOWE.format(udzial=round(udzial_nietekstowych * 100)))

    slowa_z_litera = [slowo for slowo in tekst.split() if any(znak.isalpha() for znak in slowo)]
    if len(slowa_z_litera) >= _MINIMALNA_LICZBA_SLOW_DO_OCENY_SAMOGLOSEK:
        z_samogloska = sum(1 for slowo in slowa_z_litera if _ma_samogloske(slowo))
        udzial = z_samogloska / len(slowa_z_litera)
        if udzial < _PROG_UDZIALU_SLOW_Z_SAMOGLOSKA:
            powody.append(POWOD_SLOWA_BEZ_SAMOGLOSEK.format(udzial=round(udzial * 100)))

    if powody:
        return OcenaOcr(ocena=OCENA_OCR_PODEJRZANA, powody=tuple(powody))
    return OcenaOcr(ocena=OCENA_OCR_POPRAWNA)


def _udzial_znakow_nietekstowych(tekst: str) -> float:
    """Zwraca udział znaków spoza zbioru znaków tekstowych, licząc bez spacji."""
    znaczace = [znak for znak in tekst if not znak.isspace()]
    if not znaczace:
        return 1.0
    nietekstowe = sum(
        1 for znak in znaczace if not (znak.isalnum() or znak in _ZNAKI_TEKSTOWE_DODATKOWE)
    )
    return nietekstowe / len(znaczace)


def _ma_samogloske(slowo: str) -> bool:
    """Zwraca prawdę, gdy słowo zawiera choć jedną samogłoskę alfabetu polskiego."""
    return any(znak.lower() in _SAMOGLOSKI for znak in slowo)
