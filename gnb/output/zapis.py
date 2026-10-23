"""Zapis plików wynikowych źródła: MD domyślnie, TXT opcjonalnie, PDF dla grup obrazów.

Pliki są zapisywane w UTF-8 bez znaku kolejności bajtów, z końcami wierszy LF,
i zawsze kończą się pojedynczym znakiem nowej linii. Format wynikowy wybiera
konfiguracja: domyślnie powstaje wyłącznie MD, a TXT można włączyć obok niego.
Przy obu formatach każda treść leży w dwóch plikach, z których do notatnika
wgrywa się tylko jeden.

Plik MD powstaje dla każdego źródła, gdy format jest włączony. Struktura w nim
pochodzi wyłącznie z bloków zgłoszonych przez ekstraktor. Tekst bez struktury,
na przykład z OCR, transkrypcji albo płaskiego pliku TXT, staje się akapitami,
a znaki, które Markdown odczytałby jako składnię, są escapowane. Dla źródła ze
strukturą plik TXT dostaje tę samą treść przepisaną bez znaczników,
przygotowaną przez `gnb.output.tekst_bez_znacznikow`.

Na początku każdego pliku pojedynczego źródła, w wersji TXT i w wersji MD,
zapisywany jest nagłówek metadanych w identycznej postaci zwykłego tekstu.
Buduje go moduł `gnb.output.naglowek_metadanych`. Plik grupy w wersji MD ma
nagłówek każdego źródła w postaci listy pod nagłówkiem drugiego poziomu
(`gnb.output.markdown_pliku`).

Moduł zwraca opis `PlikWynikowy` dla każdego zapisanego pliku, z policzonymi
słowami i znakami, rozmiarem w bajtach oraz sumą kontrolną. Liczby te dotyczą
zawartości pliku, więc obejmują nagłówek. Słowa pliku MD są liczone po usunięciu
znaczników składni, tą samą funkcją co dla TXT, żeby limit nie zależał od
formatu. Limity notatnika są sprawdzane osobno, na samej treści dokumentu,
ponieważ nagłówek jest informacją o źródle, a nie jego treścią.
"""

from __future__ import annotations

from pathlib import Path

from gnb.core.identyfikatory import suma_kontrolna_pliku
from gnb.core.liczenie_slow import policz_slowa, policz_znaki
from gnb.core.model import DokumentZnormalizowany, PlikWynikowy
from gnb.core.stale import FormatWynikowy
from gnb.extractors.escapowanie_markdown import escapuj_tekst_plaski
from gnb.output.markdown_pliku import policz_slowa_markdown
from gnb.output.naglowek_metadanych import polacz_z_trescia

FORMAT_MD = "md"
FORMAT_TXT = "txt"

_ROZSZERZENIA = {FormatWynikowy.MD: "md", FormatWynikowy.TXT: "txt"}


def tresc_markdown_zrodla(tekst: str, *, ma_struktura: bool) -> str:
    """Zwraca treść źródła w zapisie Markdown.

    Gdy ekstraktor zwrócił tekst ze znacznikami, jest on już Markdownem. Inaczej
    tekst staje się akapitami, a znaki składni są escapowane, żeby przypadkowy
    krzyżyk albo myślnik na początku wiersza nie stał się fałszywym nagłówkiem
    albo listą.
    """
    return tekst if ma_struktura else escapuj_tekst_plaski(tekst)


def zapisz_wyniki(
    katalog_wynikow: Path,
    nazwa_bazowa: str,
    identyfikator_zrodla: str,
    dokument: DokumentZnormalizowany,
    *,
    formaty_wlaczone: tuple[str, ...] = (FORMAT_MD,),
    tekst_txt: str | None = None,
    naglowek: str = "",
) -> list[PlikWynikowy]:
    """Zapisuje pliki MD i TXT źródła według włączonych formatów.

    Treścią pliku MD jest znormalizowany tekst dokumentu, a gdy `tekst_txt` nie
    został podany (źródło bez struktury), tekst ten jest escapowany jak zwykły
    akapit. Treścią pliku TXT jest `tekst_txt`, jeżeli został podany, a w
    przeciwnym razie ten sam znormalizowany tekst. Wywołujący podaje `tekst_txt`
    wtedy, gdy tekst źródła zawiera znaczniki formatowania i wersja TXT ma być
    ich pozbawiona.

    Nagłówek metadanych, jeżeli został podany, trafia na początek obu wersji
    w identycznej postaci i jest oddzielony od treści jednym pustym wierszem.
    """
    katalog_wynikow.mkdir(parents=True, exist_ok=True)
    wyniki: list[PlikWynikowy] = []

    if FORMAT_MD in formaty_wlaczone:
        tresc_md = tresc_markdown_zrodla(dokument.tekst, ma_struktura=tekst_txt is not None)
        sciezka_md = katalog_wynikow / f"{nazwa_bazowa}.md"
        _zapisz_tekst(
            sciezka_md, _z_koncowym_znakiem_nowej_linii(polacz_z_trescia(naglowek, tresc_md))
        )
        wyniki.append(_opis_pliku(sciezka_md, FormatWynikowy.MD, identyfikator_zrodla))

    if FORMAT_TXT in formaty_wlaczone:
        tresc_txt = _z_koncowym_znakiem_nowej_linii(
            polacz_z_trescia(naglowek, dokument.tekst if tekst_txt is None else tekst_txt)
        )
        sciezka_txt = katalog_wynikow / f"{nazwa_bazowa}.txt"
        _zapisz_tekst(sciezka_txt, tresc_txt)
        wyniki.append(_opis_pliku(sciezka_txt, FormatWynikowy.TXT, identyfikator_zrodla))

    return wyniki


def zapisz_plik_pakietu(
    katalog_wynikow: Path,
    nazwa_bazowa: str,
    tresc: str,
    identyfikatory_zrodel: list[str],
    *,
    format_pliku: FormatWynikowy = FormatWynikowy.TXT,
) -> PlikWynikowy:
    """Zapisuje jeden gotowy plik pakietu (TXT albo MD) i zwraca jego opis.

    Używane do plików, które powstają w fazie pakowania: części podzielonego
    źródła oraz plików grupy łączących kilka małych źródeł. Treść jest już złożona
    razem z nagłówkami metadanych przez `gnb.output.skladanie` albo
    `gnb.output.markdown_pliku`, więc ta funkcja tylko dopisuje końcowy znak nowej
    linii, zapisuje plik w UTF-8 bez znaku kolejności bajtów i liczy jego
    zawartość.
    """
    katalog_wynikow.mkdir(parents=True, exist_ok=True)
    sciezka = katalog_wynikow / f"{nazwa_bazowa}.{_ROZSZERZENIA[format_pliku]}"
    _zapisz_tekst(sciezka, _z_koncowym_znakiem_nowej_linii(tresc))
    return _opis_pliku(sciezka, format_pliku, None, identyfikatory_zrodel)


def zapisz_plik_pdf(
    katalog_wynikow: Path,
    nazwa_bazowa: str,
    pdf_bajty: bytes,
    identyfikatory_zrodel: list[str],
    *,
    liczba_slow: int,
    liczba_znakow: int,
) -> PlikWynikowy:
    """Zapisuje gotowy tematyczny plik PDF i zwraca jego opis.

    Bajty pliku PDF powstają w `gnb.images.pdf_tematyczny` i są tu zapisywane
    bez zmian. Liczba słów i znaków dotyczy treści tekstowej obrazów grupy, a nie
    binarnej zawartości pliku PDF, bo to treść jest porównywana z limitem
    notatnika, a rozmiar pliku jest osobnym, trzecim ograniczeniem.
    """
    katalog_wynikow.mkdir(parents=True, exist_ok=True)
    sciezka = katalog_wynikow / f"{nazwa_bazowa}.pdf"
    sciezka.write_bytes(pdf_bajty)
    return PlikWynikowy(
        sciezka=sciezka,
        format=FormatWynikowy.PDF,
        identyfikatory_zrodel=list(identyfikatory_zrodel),
        liczba_slow=liczba_slow,
        liczba_znakow=liczba_znakow,
        rozmiar_bajtow=len(pdf_bajty),
        checksum=suma_kontrolna_pliku(sciezka),
    )


def _z_koncowym_znakiem_nowej_linii(tekst: str) -> str:
    """Zapewnia, że niepusty tekst kończy się dokładnie jednym znakiem nowej linii."""
    if not tekst:
        return ""
    return tekst if tekst.endswith("\n") else tekst + "\n"


def _zapisz_tekst(sciezka: Path, tresc: str) -> None:
    """Zapisuje tekst w UTF-8 bez BOM, wymuszając końce wierszy LF także na Windows."""
    with sciezka.open("w", encoding="utf-8", newline="\n") as plik:
        plik.write(tresc)


def _opis_pliku(
    sciezka: Path,
    format_pliku: FormatWynikowy,
    identyfikator_zrodla: str | None,
    identyfikatory_zrodel: list[str] | None = None,
) -> PlikWynikowy:
    """Buduje `PlikWynikowy` z rzeczywistej zawartości zapisanego pliku."""
    dane = sciezka.read_bytes()
    tekst = dane.decode("utf-8")
    liczba_slow = (
        policz_slowa_markdown(tekst) if format_pliku is FormatWynikowy.MD else policz_slowa(tekst)
    )
    identyfikatory = (
        list(identyfikatory_zrodel)
        if identyfikatory_zrodel is not None
        else [identyfikator_zrodla or ""]
    )
    return PlikWynikowy(
        sciezka=sciezka,
        format=format_pliku,
        identyfikatory_zrodel=identyfikatory,
        liczba_slow=liczba_slow,
        liczba_znakow=policz_znaki(tekst),
        rozmiar_bajtow=len(dane),
        checksum=suma_kontrolna_pliku(sciezka),
    )
