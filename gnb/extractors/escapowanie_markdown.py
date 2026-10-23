"""Escapowanie składni Markdown w tekście, który nie pochodzi z bloku strukturalnego.

Plik wynikowy MD jest czytany czytnikiem ekranu, więc fałszywy nagłówek albo
fałszywa lista powstała z przypadkowego znaku w treści to błąd poprawności
danych: zmienia strukturę, po której użytkownik nawiguje. Ten moduł poprzedza
odwrotnym ukośnikiem znaki, które parser CommonMark odczytałby jako składnię,
tak aby po ponownym sparsowaniu zostały zwykłym tekstem.

Moduł odpowiada wyłącznie za escapowanie. Nie rozpoznaje struktury, nie dodaje
nagłówków i nie zgaduje list z płaskiego tekstu. Escapowany jest tylko tekst,
który ekstraktor zgłosił jako zwykły akapit, element listy, komórkę, cytat albo
w ogóle nie zgłosił struktury (OCR, transkrypcja, płaski plik TXT).

Zasady:

1. Początek wiersza: wiersz zaczynający się krzyżykami z odstępem, myślnikiem,
   plusem albo gwiazdką z odstępem, liczbą z kropką albo nawiasem, znakiem
   większości, ogrodzeniem kodu, kreską pozioma albo podkreśleniem akapitu
   (same myślniki albo znaki równości), pionową kreską albo definicją odnośnika
   dostaje ukośnik przed pierwszym znakiem składni.
2. Wewnątrz wiersza: gwiazdki, grawisy i podkreślenia niebędące częścią słowa,
   początek znacznika HTML, początek encji, sekwencja zamykająca odnośnik
   ``](`` oraz podwójna tylda.
3. Odwrotny ukośnik jest podwajany tylko wtedy, gdy następuje po nim znak
   interpunkcyjny albo koniec wiersza, bo tylko wtedy parser odczytałby go jako
   znak ucieczki albo twarde złamanie wiersza. Ścieżka w rodzaju ``C:\\Users``
   zostaje bez zmian.
"""

from __future__ import annotations

import re
import string

_POCZATEK_NAGLOWKA = re.compile(r"^(\s{0,3})(#{1,6})(?=\s|$)")
_POCZATEK_PUNKTU = re.compile(r"^(\s{0,3})([-+*])(?=\s|$)")
_POCZATEK_NUMEROWANEJ = re.compile(r"^(\s{0,3}\d{1,9})([.)])(?=\s|$)")
_POCZATEK_CYTATU = re.compile(r"^(\s{0,3})(>)")
_OGRODZENIE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})")
_KRESKA_POZIOMA = re.compile(r"^(\s{0,3})([-_*])(?:[ \t]*\2){2,}[ \t]*$")
_PODKRESLENIE_NAGLOWKA = re.compile(r"^(\s{0,3})(=+|-+)[ \t]*$")
_POCZATEK_TABELI = re.compile(r"^(\s{0,3})(\|)")
_DEFINICJA_ODNOSNIKA = re.compile(r"^(\s{0,3})(\[)(?=[^\]\n]+\]:)")
_ZAMKNIECIE_NAGLOWKA = re.compile(r"(\s)(#+)[ \t]*$")
_ENCJA = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|\w+);")

_INTERPUNKCJA_ASCII = frozenset(string.punctuation)
_POCZATEK_ZNACZNIKA_HTML = frozenset(string.ascii_letters + "/!?")


def escapuj_tekst_plaski(tekst: str) -> str:
    """Escapuje składnię Markdown w tekście wieloliniowym, zachowując podział na wiersze."""
    return "\n".join(_escapuj_wiersz(wiersz) for wiersz in tekst.split("\n"))


def escapuj_naglowek(tekst: str) -> str:
    """Escapuje treść nagłówka: znaki wewnątrzwierszowe i zamykający ciąg krzyżyków."""
    wynik = _escapuj_znaki_wewnatrz_wiersza(tekst)
    return _ZAMKNIECIE_NAGLOWKA.sub(
        lambda dopasowanie: f"{dopasowanie.group(1)}\\{dopasowanie.group(2)}", wynik
    )


def escapuj_komorke_lub_fragment(tekst: str) -> str:
    """Escapuje znaki wewnątrzwierszowe, bez reguł początku wiersza."""
    return _escapuj_znaki_wewnatrz_wiersza(tekst)


def dlugosc_ogrodzenia_kodu(tresc: str) -> int:
    """Zwraca długość ogrodzenia kodu dłuższą niż każdy ciąg grawisów w treści."""
    najdluzszy = 0
    for dopasowanie in re.finditer(r"`+", tresc):
        najdluzszy = max(najdluzszy, len(dopasowanie.group(0)))
    return max(3, najdluzszy + 1)


def _escapuj_wiersz(wiersz: str) -> str:
    wynik = _escapuj_znaki_wewnatrz_wiersza(wiersz)
    for wzorzec in (
        _POCZATEK_NAGLOWKA,
        _POCZATEK_PUNKTU,
        _POCZATEK_CYTATU,
        _OGRODZENIE,
        _KRESKA_POZIOMA,
        _PODKRESLENIE_NAGLOWKA,
        _POCZATEK_TABELI,
        _DEFINICJA_ODNOSNIKA,
    ):
        dopasowanie = wzorzec.match(wynik)
        if dopasowanie:
            koniec_wstepu = dopasowanie.end(1)
            return f"{wynik[:koniec_wstepu]}\\{wynik[koniec_wstepu:]}"
    numerowana = _POCZATEK_NUMEROWANEJ.match(wynik)
    if numerowana:
        pozycja = numerowana.end(1)
        return f"{wynik[:pozycja]}\\{wynik[pozycja:]}"
    return wynik


def _escapuj_znaki_wewnatrz_wiersza(tekst: str) -> str:
    wynik: list[str] = []
    dlugosc = len(tekst)
    for indeks, znak in enumerate(tekst):
        nastepny = tekst[indeks + 1] if indeks + 1 < dlugosc else ""
        poprzedni = tekst[indeks - 1] if indeks > 0 else ""
        if znak == "\\":
            if not nastepny or nastepny in _INTERPUNKCJA_ASCII:
                wynik.append("\\\\")
            else:
                wynik.append(znak)
        elif znak in "*`":
            wynik.append(f"\\{znak}")
        elif znak == "_":
            wewnatrz_slowa = poprzedni.isalnum() and nastepny.isalnum()
            wynik.append(znak if wewnatrz_slowa else "\\_")
        elif znak == "<" and nastepny in _POCZATEK_ZNACZNIKA_HTML and nastepny:
            wynik.append("\\<")
        elif znak == "~" and nastepny == "~":
            wynik.append("\\~")
        elif znak == "]" and nastepny == "(":
            wynik.append("\\]")
        elif znak == "&" and _ENCJA.match(tekst, indeks):
            wynik.append("\\&")
        else:
            wynik.append(znak)
    return "".join(wynik)
