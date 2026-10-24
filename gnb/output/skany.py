"""Składanie plików wynikowych ze skanami kartek: sekcja każdego skanu z nazwą pliku.

Zdjęcia kartek akt są pakowane inaczej niż zwykłe źródła tekstowe. Każdy skan
dostaje własną sekcję, której nagłówkiem jest dokładna nazwa pliku z rozszerzeniem,
żeby asystent czytający plik mógł wskazać konkretny skan. Pod nagłówkiem stoją
metadane: numer skanu w grupie, ocena OCR, średnia pewność słów i informacja
o dopiskach odręcznych. Dalej idzie tekst z OCR, a pod nim, w osobnej sekcji
z własnym nagłówkiem, dopiski przepisane przez osobę widzącą. Dopiski nigdy nie
są mieszane z wynikiem OCR, bo to dwa różne źródła wiarygodności.

Moduł nie wykonuje OCR, nie czyta dopisków z dysku i nie dzieli treści na pliki.
Treść skanu i dopisków dostaje gotową.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gnb.extractors.escapowanie_markdown import escapuj_naglowek, escapuj_tekst_plaski
from gnb.output.markdown_pliku import naglowek_metadanych_jako_liste
from gnb.output.naglowek_metadanych import ETYKIETA_PLIK, polacz_z_trescia
from gnb.output.skladanie import zloz_plik

NAGLOWEK_DOPISKOW = "Dopiski odręczne przepisane przez osobę widzącą"
# Wiersz, który w tekście przekazywanym pakowaniu oddziela wynik OCR od dopisków.
# Pakowanie liczy słowa i rozmiar na tym połączonym tekście, a składanie pliku
# rozdziela go z powrotem.
ZNACZNIK_DOPISKOW = f"{NAGLOWEK_DOPISKOW}:"
_SEPARATOR_DOPISKOW = f"\n\n{ZNACZNIK_DOPISKOW}\n"

ETYKIETA_NUMER_SKANU = "Numer skanu w grupie"
ETYKIETA_OCENA_OCR = "Ocena OCR"
ETYKIETA_PEWNOSC = "Średnia pewność słów"
ETYKIETA_DOPISKI = "Dopiski odręczne"
ETYKIETA_OBROT = "Obrót strony przed odczytem"


@dataclass(frozen=True, slots=True)
class SkanDoPliku:
    """Jeden skan gotowy do wpisania do pliku: metadane oraz teksty."""

    naglowek_metadanych: str
    numer: int
    ocena_ocr: str
    srednia_pewnosc: str
    ma_dopiski: bool
    tresc_ocr: str
    dopiski: str
    # Obrót strony zastosowany przed odczytem, w stopniach, jako napis. Pusty
    # napis (starszy projekt) oznacza brak informacji i brak wiersza w metadanych.
    obrot_stopni: str = ""


def polacz_tresc_skanu(tresc_ocr: str, dopiski: str) -> str:
    """Łączy wynik OCR z dopiskami w jeden tekst do liczenia limitów i pakowania."""
    if not dopiski:
        return tresc_ocr
    return f"{tresc_ocr}{_SEPARATOR_DOPISKOW}{dopiski}"


def rozdziel_tresc_skanu(tekst: str) -> tuple[str, str]:
    """Rozdziela tekst z `polacz_tresc_skanu` na wynik OCR i dopiski."""
    tresc_ocr, separator, dopiski = tekst.partition(_SEPARATOR_DOPISKOW)
    return (tresc_ocr, dopiski) if separator else (tekst, "")


def nazwa_pliku_skanu(naglowek_metadanych: str) -> str:
    """Wyciąga z nagłówka metadanych nazwę pliku skanu, a gdy jej nie ma, pusty napis."""
    for wiersz in naglowek_metadanych.split("\n"):
        etykieta, separator, wartosc = wiersz.partition(": ")
        if separator and etykieta == ETYKIETA_PLIK and wartosc.strip():
            return wartosc.strip()
    return ""


def _metadane_skanu(skan: SkanDoPliku) -> str:
    """Zwraca pełny nagłówek metadanych skanu: dane źródła i pola odczytu."""
    dodatkowe = [f"{ETYKIETA_NUMER_SKANU}: {skan.numer}"]
    if skan.ocena_ocr:
        dodatkowe.append(f"{ETYKIETA_OCENA_OCR}: {skan.ocena_ocr}")
    if skan.srednia_pewnosc:
        dodatkowe.append(f"{ETYKIETA_PEWNOSC}: {skan.srednia_pewnosc}")
    if skan.obrot_stopni:
        dodatkowe.append(f"{ETYKIETA_OBROT}: {skan.obrot_stopni} stopni")
    dodatkowe.append(f"{ETYKIETA_DOPISKI}: {'tak' if skan.ma_dopiski else 'nie'}")
    wiersze = [wiersz for wiersz in (skan.naglowek_metadanych, *dodatkowe) if wiersz]
    return "\n".join(wiersze)


def zloz_skany_txt(skany: Sequence[SkanDoPliku], *, oznaczenie_pliku: str = "") -> str:
    """Składa wersję TXT: nagłówek metadanych i treść każdego skanu po kolei."""
    return zloz_plik(
        [
            (_metadane_skanu(skan), polacz_tresc_skanu(skan.tresc_ocr, skan.dopiski))
            for skan in skany
        ],
        oznaczenie_pliku=oznaczenie_pliku,
    )


def zloz_skany_markdown(skany: Sequence[SkanDoPliku], *, tytul_pliku: str) -> str:
    """Składa wersję MD: nagłówek pliku, a pod nim sekcja drugiego poziomu każdego skanu.

    Nagłówkiem sekcji jest dokładna nazwa pliku skanu. Dopiski dostają nagłówek
    trzeciego poziomu, żeby klawisz poziomu nagłówka w czytniku ekranu odróżniał
    skany od dopisków. Wszystkie teksty są escapowane jako zwykły tekst.
    """
    czesci = [f"# {escapuj_naglowek(tytul_pliku)}"]
    for skan in skany:
        nazwa = nazwa_pliku_skanu(skan.naglowek_metadanych) or f"Skan {skan.numer}"
        sekcja = [f"## {escapuj_naglowek(nazwa)}"]
        lista = naglowek_metadanych_jako_liste(_metadane_skanu(skan))
        sekcja.append(polacz_z_trescia(lista, escapuj_tekst_plaski(skan.tresc_ocr)))
        if skan.dopiski:
            sekcja.append(f"### {NAGLOWEK_DOPISKOW}")
            sekcja.append(escapuj_tekst_plaski(skan.dopiski))
        czesci.append("\n\n".join(czesc for czesc in sekcja if czesc))
    return "\n\n".join(czesci)
