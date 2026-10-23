"""Test end-to-end: Markdown jako domyślny format wynikowy (etap siedemnasty, część B).

Sprawdza w pełnym potoku, że domyślnie powstaje wyłącznie MD dla każdego źródła,
że plik grupy ma nagłówek drugiego poziomu przed każdym źródłem, że tekst bez
struktury nie tworzy fałszywych nagłówków i że liczba słów nie zależy od formatu.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.extractors.markdown import utworz_parser
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_tekst
from gnb.potok import przetworz_projekt

_MOMENT = datetime(2026, 10, 23, 9, 0, tzinfo=UTC)

_TEKST_Z_PODEJRZANA_SKLADNIA = (
    "# To tylko linia tekstu\n\n- i to tylko linia\n\n1. oraz ta\n\nwzór 2*3*4 daje 24"
)
_MARKDOWN_ZE_STRUKTURA = "# Dokument\n\n## Sekcja pierwsza\n\nTreść sekcji.\n\n- a\n- b\n- c\n"


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 10, 23, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _przetworz(tmp_path: Path, pozycje: list[PozycjaWejsciowa], **ustawienia: object):  # type: ignore[no-untyped-def]
    return przetworz_projekt(
        pozycje,
        Konfiguracja(
            katalog_wynikow=tmp_path / "wyniki",
            deduplikacja_hash_wlaczona=False,
            deduplikacja_kosmetyczna_wlaczona=False,
            deduplikacja_podobienstwo_wlaczone=False,
            **ustawienia,  # type: ignore[arg-type]
        ),
        nazwa_projektu="Test Markdown",
        zegar=_zegar_krokowy(),
    )


def _naglowki(tekst: str) -> list[tuple[int, str]]:
    tokeny = utworz_parser().parse(tekst)
    return [
        (int(token.tag[1:]), tokeny[indeks + 1].content)
        for indeks, token in enumerate(tokeny)
        if token.type == "heading_open"
    ]


def test_tekst_bez_struktury_daje_plik_md_bez_falszywych_naglowkow_i_list(tmp_path: Path) -> None:
    wynik = _przetworz(tmp_path, [przyjmij_tekst(_TEKST_Z_PODEJRZANA_SKLADNIA, _MOMENT)])

    katalog = wynik.katalog_projektu / "pliki_wynikowe"
    (plik,) = katalog.iterdir()
    assert plik.suffix == ".md"
    tokeny = utworz_parser().parse(plik.read_text(encoding="utf-8"))
    typy = {token.type for token in tokeny}
    assert typy <= {"paragraph_open", "inline", "paragraph_close"}, typy
    tresc = plik.read_text(encoding="utf-8")
    assert "\\# To tylko linia tekstu" in tresc


def test_zrodlo_markdown_zachowuje_swoja_strukture_w_pliku_md(tmp_path: Path) -> None:
    wynik = _przetworz(
        tmp_path, [przyjmij_tekst(_MARKDOWN_ZE_STRUKTURA, _MOMENT, format_tekstu="md")]
    )

    (plik,) = (wynik.katalog_projektu / "pliki_wynikowe").iterdir()

    assert _naglowki(plik.read_text(encoding="utf-8")) == [
        (1, "Dokument"),
        (2, "Sekcja pierwsza"),
    ]


def test_plik_grupy_ma_naglowek_drugiego_poziomu_przed_kazdym_zrodlem(tmp_path: Path) -> None:
    pozycje = [
        przyjmij_tekst(_MARKDOWN_ZE_STRUKTURA, _MOMENT, format_tekstu="md", grupa="Temat"),
        przyjmij_tekst(_TEKST_Z_PODEJRZANA_SKLADNIA, _MOMENT, grupa="Temat"),
        przyjmij_tekst("Zwykła notatka bez struktury.", _MOMENT, grupa="Temat"),
    ]

    wynik = _przetworz(tmp_path, pozycje)

    (plik,) = (wynik.katalog_projektu / "pliki_wynikowe").iterdir()
    assert plik.suffix == ".md"
    naglowki = _naglowki(plik.read_text(encoding="utf-8"))
    poziomy = [poziom for poziom, _ in naglowki]
    assert naglowki[0] == (1, "Grupa „Temat”")
    assert poziomy.count(1) == 1
    assert poziomy.count(2) == 3, "po jednym nagłówku drugiego poziomu na źródło"
    # Nagłówki źródła ze strukturą leżą pod jego nagłówkiem drugiego poziomu.
    assert (3, "Dokument") in naglowki
    assert (4, "Sekcja pierwsza") in naglowki
    # Tekst z podejrzaną składnią nie dodał żadnego nagłówka ponad trzy źródła i strukturę.
    assert len(naglowki) == 1 + 3 + 2


def test_liczba_slow_pliku_md_i_txt_tej_samej_tresci_jest_taka_sama(tmp_path: Path) -> None:
    pozycje = [
        przyjmij_tekst(_TEKST_Z_PODEJRZANA_SKLADNIA, _MOMENT),
        przyjmij_tekst(_MARKDOWN_ZE_STRUKTURA, _MOMENT, format_tekstu="md"),
    ]

    wynik = _przetworz(tmp_path, pozycje, formaty_wynikowe=("md", "txt"))

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    po_trzonie: dict[str, dict[str, int]] = {}
    for plik in manifest["wyniki"]:
        sciezka = Path(plik["sciezka"])
        po_trzonie.setdefault(sciezka.stem, {})[sciezka.suffix] = plik["liczba_slow"]
    assert len(po_trzonie) == 2
    for trzon, slowa in po_trzonie.items():
        assert slowa[".md"] == slowa[".txt"], trzon


def test_podzial_zrodla_na_czesci_daje_czesci_md_z_oznaczeniem_czesci(tmp_path: Path) -> None:
    akapity = [
        f"Akapit numer {numer} opowiada o rzeczach wartych zapamiętania." for numer in range(30)
    ]
    wynik = _przetworz(
        tmp_path,
        [przyjmij_tekst("\n\n".join(akapity), _MOMENT)],
        bezpieczny_limit_slow=120,
    )

    pliki = sorted((wynik.katalog_projektu / "pliki_wynikowe").iterdir())

    assert len(pliki) >= 2
    assert all(plik.suffix == ".md" for plik in pliki)
    for numer, plik in enumerate(pliki, start=1):
        assert f"Część: {numer} z {len(pliki)}" in plik.read_text(encoding="utf-8")


def test_plik_md_obok_txt_nie_zajmuje_drugiego_slotu_limitu_zrodel(tmp_path: Path) -> None:
    pozycje = [
        przyjmij_tekst("Pierwsza notatka o podatkach.", _MOMENT),
        przyjmij_tekst("Druga notatka o ubezpieczeniach.", _MOMENT),
    ]

    wynik = _przetworz(tmp_path, pozycje, formaty_wynikowe=("md", "txt"), limit_zrodel=2)

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert [zrodlo["status"] for zrodlo in manifest["zrodla"]] == ["spakowane", "spakowane"]
    assert len(manifest["wyniki"]) == 4


def test_podzial_zrodla_mieszczacy_sie_w_limicie_nie_jest_pomijany_przez_pliki_md(
    tmp_path: Path,
) -> None:
    """Pierwsze źródło ma dwa pliki (MD i TXT), ale zajmuje jeden slot.

    Limit trzech źródeł mieści jedno małe źródło i drugie podzielone na dwie
    części. Gdyby plik MD obok TXT liczył się osobno, drugiemu zabrakłoby slotu
    i całe źródło zostałoby pominięte.
    """
    male = "Mała notatka o jednym temacie."
    akapit = "Ten akapit ma dokładnie dziesięć słów, czyli tyle, ile trzeba."
    duze = "\n\n".join([akapit] * 7)

    wynik = _przetworz(
        tmp_path,
        [przyjmij_tekst(male, _MOMENT), przyjmij_tekst(duze, _MOMENT)],
        formaty_wynikowe=("md", "txt"),
        limit_zrodel=3,
        bezpieczny_limit_slow=40,
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert sorted(zrodlo["status"] for zrodlo in manifest["zrodla"]) == ["spakowane", "spakowane"]
    # Małe źródło: MD i TXT. Duże: dwie części, każda w MD i w TXT.
    assert len(manifest["wyniki"]) == 2 + 4


def _wiersz_raportu(raport: str, poczatek: str) -> str:
    return next(wiersz for wiersz in raport.splitlines() if wiersz.startswith(poczatek))


def test_raport_samego_md_liczy_slowa_i_sloty_a_oba_formaty_daja_te_same_liczby(
    tmp_path: Path,
) -> None:
    pozycje = [
        przyjmij_tekst(_TEKST_Z_PODEJRZANA_SKLADNIA, _MOMENT),
        przyjmij_tekst(_MARKDOWN_ZE_STRUKTURA, _MOMENT, format_tekstu="md"),
    ]

    tylko_md = _przetworz(tmp_path / "a", pozycje)
    oba = _przetworz(tmp_path / "b", pozycje, formaty_wynikowe=("md", "txt"))

    raport_md = tylko_md.sciezka_raportu.read_text(encoding="utf-8")
    raport_oba = oba.sciezka_raportu.read_text(encoding="utf-8")
    assert _wiersz_raportu(raport_md, "Liczba plików MD:") == "Liczba plików MD: 2"
    assert _wiersz_raportu(raport_md, "Liczba plików TXT:") == "Liczba plików TXT: 0"
    assert not _wiersz_raportu(raport_md, "Łączna liczba słów w plikach wynikowych:").endswith(" 0")
    for poczatek in ("Łączna liczba słów w plikach wynikowych:", "Wykorzystanie limitu źródeł:"):
        assert _wiersz_raportu(raport_md, poczatek) == _wiersz_raportu(raport_oba, poczatek)
    assert _wiersz_raportu(raport_oba, "Liczba plików TXT:") == "Liczba plików TXT: 2"
