"""Budowanie opisu merytorycznego obrazu z materiału, który już jest dostępny.

Opis powstaje wyłącznie z rzeczy, które aplikacja już ma: tekstu alternatywnego,
podpisu figury, otaczającego akapitu, opisowej nazwy pliku, metadanych obrazu
oraz informacji o rozpoznanym tekście OCR. Nigdy nie jest zmyślany i nigdy nie
powstaje przez wysłanie obrazu do zewnętrznej usługi — zakazuje tego sekcja
trzecia CLAUDE.md, a decyzja siódma etapu ósmego rozstrzyga to wprost.

Gdy nie ma z czego zbudować opisu, zwracany jest jawny komunikat o jego braku,
a nie pusty ciąg. Pusty ciąg w pliku wynikowym wyglądałby jak przeoczenie,
a jawny brak mówi użytkownikowi, że to obraz bez żadnego materiału opisowego
i że sam musi zdecydować, czy taki obraz wnosi coś do notatnika.

Sam tekst OCR nie jest tutaj wklejany w całości: trafia do pliku wynikowego jako
osobna, oznaczona sekcja. Opis jedynie odnotowuje, że rozpoznano tekst i ile go
jest, żeby te same zdania nie stały w pliku dwa razy.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from gnb.core.liczenie_slow import policz_slowa

BRAK_OPISU = (
    "Brak opisu. Nie było z czego go zbudować: obraz nie ma tekstu alternatywnego, "
    "podpisu, otaczającego tekstu, opisowej nazwy pliku, metadanych ani rozpoznanego "
    "tekstu. Zdecyduj sam, czy taki obraz wnosi coś do notatnika."
)

# Człony nazw plików typowe dla aparatu i zrzutów ekranu. Nazwa złożona wyłącznie
# z takich członów i liczb nie jest opisowa.
_CZLONY_NIEOPISOWE = frozenset(
    {"img", "image", "dsc", "dscn", "photo", "foto", "obraz", "scan", "skan", "screenshot", "zrzut"}
)
_MINIMALNA_DLUGOSC_CZLONU_OPISOWEGO = 3
_ROZDZIELACZE_NAZWY = re.compile(r"[\s_\-.]+")

ETYKIETA_NAZWA_PLIKU = "Nazwa pliku"
ETYKIETA_FORMAT_WYMIARY = "Format i wymiary"
ETYKIETA_TEKST_ALTERNATYWNY = "Tekst alternatywny"
ETYKIETA_PODPIS = "Podpis"
ETYKIETA_OTACZAJACY_TEKST = "Fragment otaczającego tekstu"
ETYKIETA_METADANE = "Opis z metadanych obrazu"
ETYKIETA_OCR = "Rozpoznany tekst"

_WSTEP = (
    "Opis obrazu zbudowany z dostępnego materiału tekstowego, bez interpretacji treści wizualnej."
)
_MAKSYMALNA_DLUGOSC_OTACZAJACEGO_TEKSTU = 400


@dataclass(frozen=True, slots=True)
class MaterialDoOpisu:
    """Zebrany materiał, z którego buduje się opis obrazu.

    Pola tekstu alternatywnego, podpisu i otaczającego tekstu są wypełniane tylko
    dla obrazu wyjętego z treści strony. Dla obrazu wskazanego jako plik
    dostępne są zwykle sama nazwa pliku, metadane i tekst OCR.
    """

    nazwa_pliku: str | None = None
    format_obrazu: str | None = None
    wymiary: tuple[int, int] | None = None
    tekst_alternatywny: str | None = None
    podpis: str | None = None
    otaczajacy_tekst: str | None = None
    metadane_obrazu: Mapping[str, str] = field(default_factory=dict)
    tekst_ocr: str | None = None


def zbuduj_opis(material: MaterialDoOpisu) -> str:
    """Buduje opis obrazu jako czytelny tekst albo zwraca komunikat o braku opisu.

    Informacja o formacie i wymiarach obrazu jest tylko uzupełnieniem: sama, bez
    żadnego materiału opisowego, nie wystarcza na opis merytoryczny i wtedy
    zwracany jest jawny komunikat o braku opisu.
    """
    wiersze: list[str] = []
    ma_material_tresciowy = False

    nazwa_opisowa = _nazwa_opisowa(material.nazwa_pliku)
    if nazwa_opisowa is not None:
        wiersze.append(f"{ETYKIETA_NAZWA_PLIKU}: {nazwa_opisowa}")
        ma_material_tresciowy = True

    format_wymiary = _format_i_wymiary(material.format_obrazu, material.wymiary)
    if format_wymiary is not None:
        wiersze.append(f"{ETYKIETA_FORMAT_WYMIARY}: {format_wymiary}")

    for etykieta, wartosc in (
        (ETYKIETA_TEKST_ALTERNATYWNY, material.tekst_alternatywny),
        (ETYKIETA_PODPIS, material.podpis),
    ):
        oczyszczona = _oczysc(wartosc)
        if oczyszczona:
            wiersze.append(f"{etykieta}: {oczyszczona}")
            ma_material_tresciowy = True

    otaczajacy = _oczysc(material.otaczajacy_tekst)
    if otaczajacy:
        wiersze.append(f"{ETYKIETA_OTACZAJACY_TEKST}: {_skroc(otaczajacy)}")
        ma_material_tresciowy = True

    opis_z_metadanych = _opis_z_metadanych(material.metadane_obrazu)
    if opis_z_metadanych:
        wiersze.append(f"{ETYKIETA_METADANE}: {opis_z_metadanych}")
        ma_material_tresciowy = True

    podsumowanie_ocr = _podsumowanie_ocr(material.tekst_ocr)
    if podsumowanie_ocr is not None:
        wiersze.append(f"{ETYKIETA_OCR}: {podsumowanie_ocr}")
        ma_material_tresciowy = True

    if not ma_material_tresciowy:
        return BRAK_OPISU
    return _WSTEP + "\n\n" + "\n".join(wiersze)


def _nazwa_opisowa(nazwa_pliku: str | None) -> str | None:
    """Zwraca nazwę pliku bez rozszerzenia, o ile niesie treść opisową.

    Nazwa złożona wyłącznie z członów typowych dla aparatu i z liczb, na przykład
    „IMG_20240101_1200”, nie jest opisowa i jest pomijana. Nazwa z choć jednym
    znaczącym słowem, na przykład „raport wykres kwartalny”, jest zachowana.
    """
    if not nazwa_pliku:
        return None
    trzon = nazwa_pliku.rsplit(".", 1)[0] if "." in nazwa_pliku else nazwa_pliku
    czlony = [czlon for czlon in _ROZDZIELACZE_NAZWY.split(trzon) if czlon]
    znaczace = [
        czlon
        for czlon in czlony
        if czlon.isalpha()
        and len(czlon) >= _MINIMALNA_DLUGOSC_CZLONU_OPISOWEGO
        and czlon.lower() not in _CZLONY_NIEOPISOWE
    ]
    if not znaczace:
        return None
    return " ".join(czlony)


def _format_i_wymiary(format_obrazu: str | None, wymiary: tuple[int, int] | None) -> str | None:
    """Składa krótką informację o formacie i wymiarach obrazu w pikselach."""
    czesci: list[str] = []
    if format_obrazu:
        czesci.append(format_obrazu.upper())
    if wymiary is not None:
        czesci.append(f"{wymiary[0]} na {wymiary[1]} pikseli")
    return ", ".join(czesci) if czesci else None


def _opis_z_metadanych(metadane: Mapping[str, str]) -> str | None:
    """Wybiera z metadanych obrazu pole opisowe, jeżeli jest.

    Kolejność preferencji: jawny opis, tytuł, komentarz, słowa kluczowe. Bierze
    pierwszą niepustą wartość, bo łączenie kilku dawałoby zlepek bez sensu.
    """
    for klucz in ("opis", "tytul", "komentarz", "slowa_kluczowe"):
        wartosc = _oczysc(metadane.get(klucz))
        if wartosc:
            return wartosc
    return None


def _podsumowanie_ocr(tekst_ocr: str | None) -> str | None:
    """Zwraca krótkie zdanie o rozpoznanym tekście OCR albo nic, gdy go nie ma.

    Pełny tekst OCR jest w pliku wynikowym osobną sekcją, więc tu jest tylko
    informacja, że powstał, wraz z jego pierwszym wierszem jako próbką.
    """
    if not tekst_ocr or not tekst_ocr.strip():
        return None
    liczba_slow = policz_slowa(tekst_ocr)
    pierwszy_wiersz = next(
        (wiersz.strip() for wiersz in tekst_ocr.splitlines() if wiersz.strip()), ""
    )
    return (
        f"rozpoznano {liczba_slow} słów, patrz osobna sekcja niżej. "
        f"Początek: {_skroc(pierwszy_wiersz, 120)}"
    )


def _oczysc(wartosc: str | None) -> str:
    """Sprowadza wartość do jednego wiersza bez nadmiarowych białych znaków."""
    if not wartosc:
        return ""
    return " ".join(wartosc.split())


def _skroc(tekst: str, limit: int = _MAKSYMALNA_DLUGOSC_OTACZAJACEGO_TEKSTU) -> str:
    """Skraca tekst do limitu znaków, dopisując wielokropek, gdy coś odcięto."""
    if len(tekst) <= limit:
        return tekst
    return tekst[: limit - 1].rstrip() + "…"
