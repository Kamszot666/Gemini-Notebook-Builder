"""Wykrywanie kodowania znaków i dekodowanie bajtów źródła do tekstu.

Najpierw sprawdzany jest znak kolejności bajtów na początku danych. Jeżeli go
nie ma, kodowanie jest wykrywane biblioteką ``charset-normalizer``. Znak
kolejności bajtów jest zawsze usuwany z wyniku.

Moduł zwraca tekst oraz nazwę wykrytego kodowania. Nie zmienia końców wierszy
ani postaci znaków Unicode — to należy do modułu normalizacji tekstu.
"""

from __future__ import annotations

from charset_normalizer import from_bytes

from gnb.core.wyjatki import BladTrwaly

_ZNAK_BOM = "\ufeff"

# Kolejność ma znaczenie: znacznik UTF-32 little endian zaczyna się tymi samymi
# dwoma bajtami co znacznik UTF-16 little endian, więc dłuższy musi być pierwszy.
_ZNACZNIKI_KOLEJNOSCI_BAJTOW: tuple[tuple[bytes, str], ...] = (
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)


def zdekoduj(dane: bytes) -> tuple[str, str]:
    """Dekoduje bajty źródła do tekstu i zwraca tekst oraz nazwę wykrytego kodowania.

    Puste wejście daje pusty tekst i kodowanie ``utf-8``. Gdy nie uda się ustalić
    kodowania, zgłaszany jest błąd trwały, bo dalsze przetwarzanie takich danych
    nie ma sensu.
    """
    if not dane:
        return "", "utf-8"

    for znacznik, kodowanie in _ZNACZNIKI_KOLEJNOSCI_BAJTOW:
        if dane.startswith(znacznik):
            # Kodeki utf-8-sig, utf-16 i utf-32 same usuwają znak kolejności bajtów.
            return dane.decode(kodowanie), kodowanie

    najlepsze_dopasowanie = from_bytes(dane).best()
    if najlepsze_dopasowanie is None:
        raise BladTrwaly("Nie udało się wykryć kodowania tekstu źródła.")
    tekst = str(najlepsze_dopasowanie)
    if tekst.startswith(_ZNAK_BOM):
        tekst = tekst[len(_ZNAK_BOM) :]
    return tekst, najlepsze_dopasowanie.encoding
