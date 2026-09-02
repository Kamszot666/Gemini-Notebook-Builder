"""Testy parsowania ciała formularzy interfejsu, w tym integralności binarnej."""

from __future__ import annotations

import pytest

from gnb.ui.formularze import (
    BladFormularza,
    bezpieczna_nazwa_wysylki,
    parsuj,
)

_GRANICA = "----TestGranicaFormularza1234"


def _czesc_pola(nazwa: str, wartosc: str) -> bytes:
    return (
        f'--{_GRANICA}\r\nContent-Disposition: form-data; name="{nazwa}"\r\n\r\n{wartosc}\r\n'
    ).encode()


def _czesc_pliku(nazwa: str, nazwa_pliku: str, zawartosc: bytes) -> bytes:
    naglowek = (
        f"--{_GRANICA}\r\n"
        f'Content-Disposition: form-data; name="{nazwa}"; filename="{nazwa_pliku}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode()
    return naglowek + zawartosc + b"\r\n"


def _zloz(*czesci: bytes) -> bytes:
    return b"".join(czesci) + f"--{_GRANICA}--\r\n".encode()


def _parsuj(cialo: bytes) -> object:
    return parsuj(
        cialo,
        f"multipart/form-data; boundary={_GRANICA}",
        maksymalny_rozmiar_bajtow=10_000_000,
        maksymalna_liczba_plikow=10,
    )


def test_multipart_z_polami_i_plikiem() -> None:
    cialo = _zloz(
        _czesc_pola("nazwa_projektu", "Mój projekt"),
        _czesc_pola("grupa", "Wiedza"),
        _czesc_pliku("pliki", "notatka.txt", b"tresc pliku"),
    )
    wynik = _parsuj(cialo)

    assert wynik.pole("nazwa_projektu") == "Mój projekt"
    assert wynik.pole("grupa") == "Wiedza"
    assert len(wynik.pliki) == 1
    assert wynik.pliki[0].nazwa_pliku == "notatka.txt"
    assert wynik.pliki[0].zawartosc == b"tresc pliku"


def test_wysylany_plik_binarny_jest_odtworzony_bajt_w_bajt() -> None:
    """Plik binarny z bajtami spoza ASCII i sekwencjami CR, LF oraz CRLF w treści.

    Test celuje w ryzyko normalizacji końców wierszy przez parser. Gdyby parser
    zmieniał choćby jeden bajt, wysłany PDF, DOCX czy EPUB byłby uszkodzony, co
    narusza priorytet pierwszy z sekcji czwartej CLAUDE.md.
    """
    oryginalne_bajty = (
        b"%PDF-1.4\r\n1 0 obj\r\n<< /Type /Catalog >>\r\nstream\r"
        + bytes(range(256))
        + b"\rendstream\r\n%%EOF\n"
        + b"\r\n\r\n"
        + bytes(range(255, -1, -1))
    )
    cialo = _zloz(
        _czesc_pola("nazwa_projektu", "Test binarny"),
        _czesc_pliku("pliki", "dokument.pdf", oryginalne_bajty),
    )

    wynik = _parsuj(cialo)

    assert len(wynik.pliki) == 1
    assert wynik.pliki[0].zawartosc == oryginalne_bajty
    assert len(wynik.pliki[0].zawartosc) == len(oryginalne_bajty)


def test_wiele_plikow_pod_ta_sama_nazwa_pola() -> None:
    cialo = _zloz(
        _czesc_pliku("pliki", "a.txt", b"aaa"),
        _czesc_pliku("pliki", "b.txt", b"bbb"),
    )
    wynik = _parsuj(cialo)
    assert [plik.nazwa_pliku for plik in wynik.pliki] == ["a.txt", "b.txt"]


def test_urlencoded_bez_plikow() -> None:
    wynik = parsuj(
        b"nazwa_projektu=Notatki&adresy=https%3A%2F%2Fexample.com%2Fa&grupa=",
        "application/x-www-form-urlencoded",
        maksymalny_rozmiar_bajtow=10_000,
        maksymalna_liczba_plikow=0,
    )
    assert wynik.pole("nazwa_projektu") == "Notatki"
    assert wynik.pole("adresy") == "https://example.com/a"
    assert wynik.pole("grupa") == ""
    assert wynik.pliki == []


def test_przekroczenie_limitu_rozmiaru_konczy_sie_bledem() -> None:
    with pytest.raises(BladFormularza, match="ponad limit"):
        parsuj(
            b"x" * 100,
            "application/x-www-form-urlencoded",
            maksymalny_rozmiar_bajtow=10,
            maksymalna_liczba_plikow=0,
        )


def test_przekroczenie_liczby_plikow_konczy_sie_bledem() -> None:
    cialo = _zloz(
        _czesc_pliku("pliki", "a.txt", b"a"),
        _czesc_pliku("pliki", "b.txt", b"b"),
    )
    with pytest.raises(BladFormularza, match="ponad limit"):
        parsuj(
            cialo,
            f"multipart/form-data; boundary={_GRANICA}",
            maksymalny_rozmiar_bajtow=10_000,
            maksymalna_liczba_plikow=1,
        )


def test_multipart_bez_granicy_konczy_sie_bledem() -> None:
    with pytest.raises(BladFormularza, match="boundary"):
        parsuj(
            b"cokolwiek",
            "multipart/form-data",
            maksymalny_rozmiar_bajtow=10_000,
            maksymalna_liczba_plikow=1,
        )


def test_bezpieczna_nazwa_wysylki_odcina_sciezke_i_zachowuje_rozszerzenie() -> None:
    assert bezpieczna_nazwa_wysylki("../../etc/raport.pdf") == "raport.pdf"
    assert bezpieczna_nazwa_wysylki("C:\\Users\\ktos\\notatka.docx") == "notatka.docx"
    assert bezpieczna_nazwa_wysylki("dobra_nazwa.txt") == "dobra_nazwa.txt"


def test_pusty_wybor_pliku_nie_daje_pustego_pliku() -> None:
    """Formularz z polem pliku, ale bez wybranego pliku, ma pustą nazwę pliku.

    Przeglądarka wysyła wtedy część z ``filename=""`` i bez treści. Taka część
    nie może stać się plikiem o zerowej zawartości.
    """
    cialo = _zloz(
        _czesc_pola("nazwa_projektu", "Bez pliku"),
        _czesc_pliku("pliki", "", b""),
    )
    wynik = _parsuj(cialo)
    assert wynik.pliki == []
