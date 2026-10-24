"""Przygotowanie zdjęcia strony do rozpoznania tekstu.

Zdjęcie kartki z telefonu bywa przechylone, ma słaby kontrast albo jest zbyt
małe, żeby Tesseract rozpoznał drobny druk. Ten moduł wykonuje cztery proste
kroki na samym obrazie: odcienie szarości, wyrównanie kontrastu, wyprostowanie
przechylonej strony i powiększenie zbyt małego obrazu. Używa wyłącznie Pillow
i NumPy, czyli bibliotek, które projekt już zawiera, bez nowych komponentów
natywnych (reguła z sekcji 18d CLAUDE.md).

Moduł nie decyduje, czy przygotowanie jest potrzebne, i nie ocenia wyniku
rozpoznania: to należy do wołającego, który porównuje pewność odczytu. Nie
zmienia też obrazu źródłowego zapisanego w wynikach, pracuje na kopii.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter, ImageOps

# Obraz, którego dłuższy bok jest krótszy, jest powiększany do tej wartości.
# Dla strony A4 odpowiada to mniej więcej 200 punktom na cal, co jest dolną
# granicą, od której drobny druk przestaje być rozpoznawany niepewnie.
DOLNY_DLUGOSC_BOKU_PX = 2000
NAJWIEKSZE_POWIEKSZENIE = 2.5

# Zakres i krok poszukiwania kąta przechylenia, w stopniach. Zdjęcia z trybu
# skanowania dokumentów są już wyprostowane, więc większy kąt oznaczałby raczej
# błąd wykrycia niż rzeczywiste przechylenie.
NAJWIEKSZY_KAT_STOPNIE = 5.0
KROK_KATA_STOPNIE = 0.5
# Najmniejszy kąt, o który obraz jest obracany. Mniejszy nie poprawia odczytu,
# a obrót zawsze wygładza krawędzie liter.
NAJMNIEJSZY_OBRACANY_KAT_STOPNIE = 1.0
_SZEROKOSC_DO_WYKRYCIA_KATA_PX = 900


def przygotuj_do_ocr(obraz: Image.Image) -> Image.Image:
    """Zwraca kopię obrazu przygotowaną do rozpoznania tekstu."""
    szary = ImageOps.exif_transpose(obraz) or obraz
    # Filtr medianowy usuwa szum ziarna z matrycy telefonu, który bez niego
    # rozciągałby zakres jasności przy wyrównaniu kontrastu i zalewał tekst.
    szary = szary.convert("L").filter(ImageFilter.MedianFilter(3))
    szary = ImageOps.autocontrast(szary, cutoff=1)
    kat = wykryj_kat_przechylenia(szary)
    if abs(kat) >= NAJMNIEJSZY_OBRACANY_KAT_STOPNIE:
        szary = szary.rotate(kat, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=255)
    return powieksz_jesli_maly(szary)


def powieksz_jesli_maly(obraz: Image.Image) -> Image.Image:
    """Powiększa obraz, którego dłuższy bok jest krótszy niż `DOLNY_DLUGOSC_BOKU_PX`."""
    dluzszy_bok = max(obraz.size)
    if dluzszy_bok >= DOLNY_DLUGOSC_BOKU_PX:
        return obraz
    skala = min(NAJWIEKSZE_POWIEKSZENIE, DOLNY_DLUGOSC_BOKU_PX / dluzszy_bok)
    nowy_rozmiar = (round(obraz.width * skala), round(obraz.height * skala))
    return obraz.resize(nowy_rozmiar, resample=Image.Resampling.LANCZOS)


def wykryj_kat_przechylenia(szary: Image.Image) -> float:
    """Szuka kąta w stopniach, o który trzeba obrócić obraz, żeby wiersze były poziome.

    Metoda profilu rzutu: dla kolejnych kątów liczona jest suma ciemnych
    punktów w każdym wierszu, a właściwy kąt daje najostrzejszy profil, czyli
    największą wariancję sum. Zwraca zero, gdy obraz nie ma wyraźnego tekstu.
    """
    if szary.width > _SZEROKOSC_DO_WYKRYCIA_KATA_PX:
        wysokosc = round(szary.height * _SZEROKOSC_DO_WYKRYCIA_KATA_PX / szary.width)
        szary = szary.resize((_SZEROKOSC_DO_WYKRYCIA_KATA_PX, max(1, wysokosc)))
    piksele = np.asarray(szary, dtype=np.uint8)
    prog = float(piksele.mean()) - 0.5 * float(piksele.std())
    if piksele.std() < 8:
        return 0.0
    ciemne = Image.fromarray(((piksele < prog) * 255).astype(np.uint8))

    liczba_krokow = round(NAJWIEKSZY_KAT_STOPNIE / KROK_KATA_STOPNIE)
    najlepszy_kat = 0.0
    najlepszy_wynik = -1.0
    wynik_dla_zera = 0.0
    for numer in range(-liczba_krokow, liczba_krokow + 1):
        kat = numer * KROK_KATA_STOPNIE
        obrocony = ciemne.rotate(kat, resample=Image.Resampling.NEAREST, fillcolor=0)
        profil = np.asarray(obrocony, dtype=np.float32).sum(axis=1)
        wynik = float(profil.var())
        if numer == 0:
            wynik_dla_zera = wynik
        if wynik > najlepszy_wynik:
            najlepszy_wynik = wynik
            najlepszy_kat = kat
    # Obrót jest uzasadniony tylko wtedy, gdy wyraźnie poprawia ostrość profilu
    # w stosunku do obrazu nieobróconego.
    if najlepszy_wynik < wynik_dla_zera * 1.05:
        return 0.0
    return najlepszy_kat
