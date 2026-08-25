"""Testy kontraktów danych z gnb.core.model i gnb.core.stale."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from gnb.core.model import (
    BlokTresci,
    DecyzjaDeduplikacji,
    DokumentWyekstrahowany,
    DokumentZnormalizowany,
    PlikWynikowy,
    WejscieSurowe,
    Zrodlo,
)
from gnb.core.stale import (
    FormatWynikowy,
    PoziomPewnosciStruktury,
    RodzajBloku,
    StatusZrodla,
    TypWejscia,
    TypZrodla,
    WynikDeduplikacji,
)


def test_status_zrodla_ma_dokladnie_wartosci_z_claude_md() -> None:
    """Statusy źródła muszą odpowiadać dokładnie liście z sekcji siódmej CLAUDE.md."""

    oczekiwane = {
        "oczekuje",
        "pobrane",
        "wyekstrahowane",
        "znormalizowane",
        "duplikat",
        "spakowane",
        "pominiete",
        "blad",
    }
    assert {status.value for status in StatusZrodla} == oczekiwane


def test_wejscie_surowe_tworzy_sie_z_wymaganymi_polami() -> None:
    wejscie = WejscieSurowe(
        identyfikator_wejscia="w-1",
        typ_wejscia=TypWejscia.URL,
        wartosc="https://example.invalid/artykul",
        moment_dodania=datetime.now(UTC),
    )

    assert wejscie.typ_wejscia is TypWejscia.URL


def test_zrodlo_tworzy_sie_z_wymaganymi_polami() -> None:
    teraz = datetime.now(UTC)
    zrodlo = Zrodlo(
        identyfikator_zrodla="abc123",
        typ_zrodla=TypZrodla.STRONA_WWW,
        pochodzenie="https://example.invalid/artykul",
        checksum=None,
        status=StatusZrodla.OCZEKUJE,
        utworzono=teraz,
        zaktualizowano=teraz,
    )

    assert zrodlo.status is StatusZrodla.OCZEKUJE


def test_dokument_wyekstrahowany_domyslne_listy_sa_niezalezne_miedzy_instancjami() -> None:
    """Pole z field(default_factory=list) nie może być współdzielone między instancjami."""

    dokument_a = DokumentWyekstrahowany(
        identyfikator_zrodla="abc123",
        tekst="Treść dokumentu.",
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.SREDNI,
        metoda_ekstrakcji="trafilatura",
    )
    dokument_b = DokumentWyekstrahowany(
        identyfikator_zrodla="def456",
        tekst="Inna treść.",
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
        metoda_ekstrakcji="heurystyka",
    )

    dokument_a.bloki.append(BlokTresci(rodzaj=RodzajBloku.AKAPIT, poziom=0, tresc="Akapit."))

    assert len(dokument_a.bloki) == 1
    assert dokument_b.bloki == []


def test_dokument_znormalizowany_przechowuje_liczniki() -> None:
    dokument = DokumentZnormalizowany(
        identyfikator_zrodla="abc123",
        tekst="Krotki tekst.",
        liczba_slow=2,
        liczba_znakow=13,
    )

    assert dokument.liczba_slow == 2
    assert dokument.liczba_znakow == 13


def test_decyzja_deduplikacji_przechowuje_uzasadnienie_i_fragmenty_unikalne() -> None:
    decyzja = DecyzjaDeduplikacji(
        identyfikator_zrodla_glownego="abc123",
        identyfikator_duplikatu="def456",
        metoda="rapidfuzz",
        wynik_podobienstwa=0.94,
        decyzja=WynikDeduplikacji.CZESCIOWY_DUPLIKAT,
        uzasadnienie="Wspólny trzon tekstu, jeden akapit unikalny w duplikacie.",
        zachowane_fragmenty_unikalne=["Akapit widoczny tylko w przedruku."],
    )

    assert decyzja.decyzja is WynikDeduplikacji.CZESCIOWY_DUPLIKAT
    assert len(decyzja.zachowane_fragmenty_unikalne) == 1


def test_plik_wynikowy_przechowuje_sciezke_i_liste_zrodel() -> None:
    plik = PlikWynikowy(
        sciezka=Path("wyniki") / "temat.txt",
        format=FormatWynikowy.TXT,
        identyfikatory_zrodel=["abc123", "def456"],
        liczba_slow=100,
        liczba_znakow=600,
        rozmiar_bajtow=612,
        checksum="deadbeef",
    )

    assert plik.format is FormatWynikowy.TXT
    assert plik.identyfikatory_zrodel == ["abc123", "def456"]
