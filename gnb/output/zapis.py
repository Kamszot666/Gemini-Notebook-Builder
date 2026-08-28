"""Zapis plików wynikowych źródła: TXT zawsze, MD warunkowo.

Pliki są zapisywane w UTF-8 bez znaku kolejności bajtów, z końcami wierszy LF,
i zawsze kończą się pojedynczym znakiem nowej linii. W etapie pierwszym każde
źródło daje własny plik i nie ma łączenia źródeł — to zadanie etapu szóstego.

Wersja TXT i wersja MD mogą mieć różną treść. Dla źródła Markdown plik MD
zachowuje znaczniki, a plik TXT dostaje tę samą treść przepisaną bez znaczników,
przygotowaną przez `gnb.output.tekst_bez_znacznikow`. Dzięki temu dwa pliki
wynikowe tego samego źródła nie są swoimi kopiami i nie zajmują dwóch slotów
notatnika na identyczną treść.

Na początku każdego pliku, w wersji TXT i w wersji MD, zapisywany jest nagłówek
metadanych źródła, w identycznej postaci zwykłego tekstu. Buduje go moduł
`gnb.output.naglowek_metadanych`.

Moduł zwraca opis `PlikWynikowy` dla każdego zapisanego pliku, z policzonymi
słowami i znakami, rozmiarem w bajtach oraz sumą kontrolną. Liczby te dotyczą
zawartości pliku, więc obejmują nagłówek. Limity notatnika są sprawdzane osobno,
na samej treści dokumentu, ponieważ nagłówek jest informacją o źródle, a nie jego
treścią.
"""

from __future__ import annotations

from pathlib import Path

from gnb.core.identyfikatory import suma_kontrolna_pliku
from gnb.core.liczenie_slow import policz_slowa, policz_znaki
from gnb.core.model import DokumentZnormalizowany, PlikWynikowy
from gnb.core.stale import FormatWynikowy
from gnb.output.naglowek_metadanych import polacz_z_trescia
from gnb.output.regula_md import DecyzjaFormatu

FORMAT_MD = "md"


def zapisz_wyniki(
    katalog_wynikow: Path,
    nazwa_bazowa: str,
    identyfikator_zrodla: str,
    dokument: DokumentZnormalizowany,
    decyzja: DecyzjaFormatu,
    *,
    formaty_wlaczone: tuple[str, ...] = ("txt", "md"),
    tekst_txt: str | None = None,
    naglowek: str = "",
) -> list[PlikWynikowy]:
    """Zapisuje plik TXT zawsze, a plik MD tylko gdy pozwala reguła i konfiguracja.

    Plik MD powstaje, gdy `decyzja.generuj_md` jest prawdą oraz format ``md``
    jest obecny w `formaty_wlaczone`. Treścią pliku MD jest znormalizowany tekst
    dokumentu. Treścią pliku TXT jest `tekst_txt`, jeżeli został podany, a w
    przeciwnym razie ten sam znormalizowany tekst. Wywołujący podaje `tekst_txt`
    wtedy, gdy tekst źródła zawiera znaczniki formatowania i wersja TXT ma być
    ich pozbawiona.

    Nagłówek metadanych, jeżeli został podany, trafia na początek obu wersji
    w identycznej postaci i jest oddzielony od treści jednym pustym wierszem.
    """
    katalog_wynikow.mkdir(parents=True, exist_ok=True)
    tresc_md = _z_koncowym_znakiem_nowej_linii(polacz_z_trescia(naglowek, dokument.tekst))
    tresc_txt = _z_koncowym_znakiem_nowej_linii(
        polacz_z_trescia(naglowek, dokument.tekst if tekst_txt is None else tekst_txt)
    )

    wyniki: list[PlikWynikowy] = []
    sciezka_txt = katalog_wynikow / f"{nazwa_bazowa}.txt"
    _zapisz_tekst(sciezka_txt, tresc_txt)
    wyniki.append(_opis_pliku(sciezka_txt, FormatWynikowy.TXT, identyfikator_zrodla))

    if decyzja.generuj_md and FORMAT_MD in formaty_wlaczone:
        sciezka_md = katalog_wynikow / f"{nazwa_bazowa}.md"
        _zapisz_tekst(sciezka_md, tresc_md)
        wyniki.append(_opis_pliku(sciezka_md, FormatWynikowy.MD, identyfikator_zrodla))

    return wyniki


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
    sciezka: Path, format_pliku: FormatWynikowy, identyfikator_zrodla: str
) -> PlikWynikowy:
    """Buduje `PlikWynikowy` z rzeczywistej zawartości zapisanego pliku."""
    dane = sciezka.read_bytes()
    tekst = dane.decode("utf-8")
    return PlikWynikowy(
        sciezka=sciezka,
        format=format_pliku,
        identyfikatory_zrodel=[identyfikator_zrodla],
        liczba_slow=policz_slowa(tekst),
        liczba_znakow=policz_znaki(tekst),
        rozmiar_bajtow=len(dane),
        checksum=suma_kontrolna_pliku(sciezka),
    )
