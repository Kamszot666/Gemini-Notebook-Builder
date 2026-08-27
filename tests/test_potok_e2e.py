"""Test end-to-end potoku etapu pierwszego, w tym wznowienia z checkpointu."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_plik, przyjmij_tekst
from gnb.potok import przetworz_projekt

KATALOG_DANYCH = Path(__file__).resolve().parent / "dane"


# Strefa czasu lokalnego użyta w testach, odpowiadająca polskiemu czasowi
# letniemu. Pozwala sprawdzić, że log ważny jest prowadzony w czasie lokalnym,
# a nie w czasie UTC używanym przez pozostałe zapisy.
_STREFA_LOKALNA = timezone(timedelta(hours=2))


def _zegar_lokalny_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 8, 26, 22, 30, tzinfo=_STREFA_LOKALNA)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 8, 26, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _pozycje() -> list[PozycjaWejsciowa]:
    moment = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
    return [
        przyjmij_plik(KATALOG_DANYCH / "dokument_strukturalny.md", moment),
        przyjmij_plik(KATALOG_DANYCH / "tekst_plaski.txt", moment),
        przyjmij_plik(KATALOG_DANYCH / "tekst_windows1250.txt", moment),
        przyjmij_tekst("Krótki tekst wklejony do testu end-to-end.", moment),
    ]


def test_potok_przetwarza_rozne_zrodla_i_stosuje_regule_md(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test etapu 1", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_przetworzonych == 4
    assert wynik.liczba_bledow == 0

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    pliki = {p.name for p in katalog_wynikow.iterdir()}

    trzon = "jak_przygotować_bazę_wiedzy_dla_asystenta_ai"
    assert len(list(katalog_wynikow.glob(f"{trzon}_*.txt"))) == 1
    assert len(list(katalog_wynikow.glob(f"{trzon}_*.md"))) == 1

    liczba_md = sum(1 for nazwa in pliki if nazwa.endswith(".md"))
    assert liczba_md == 1, "wersję MD dostaje tylko dokument_strukturalny.md"


def test_wersja_txt_zrodla_markdown_nie_jest_kopia_wersji_md(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test wersji TXT", zegar=_zegar_krokowy()
    )

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    trzon = "jak_przygotować_bazę_wiedzy_dla_asystenta_ai"
    (plik_txt,) = katalog_wynikow.glob(f"{trzon}_*.txt")
    (plik_md,) = katalog_wynikow.glob(f"{trzon}_*.md")

    tresc_txt = plik_txt.read_text(encoding="utf-8")
    tresc_md = plik_md.read_text(encoding="utf-8")

    assert tresc_txt != tresc_md
    assert tresc_md.startswith("# Jak przygotować bazę wiedzy dla asystenta AI")
    assert tresc_txt.startswith("Jak przygotować bazę wiedzy dla asystenta AI")
    assert "#" not in tresc_txt
    assert "|" not in tresc_txt
    assert "Metoda: MinHash" in tresc_txt


def test_nazwa_pliku_wynikowego_wiaze_plik_ze_zrodlem_z_manifestu(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test nazw", zegar=_zegar_krokowy()
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    for zrodlo in manifest["zrodla"]:
        skrot = zrodlo["identyfikator"].rsplit("-", 1)[-1][:8]
        for sciezka_wzgledna in zrodlo["pliki_wynikowe"]:
            nazwa = Path(sciezka_wzgledna).stem
            assert nazwa.endswith(f"_{skrot}"), nazwa
            assert " " not in nazwa
            assert nazwa == nazwa.lower()


def test_plik_windows1250_jest_odczytany_bez_utraty_polskich_znakow(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test kodowania", zegar=_zegar_krokowy()
    )

    pasujace = list((wynik.katalog_projektu / "pliki_wynikowe").glob("zażółć_gęślą_jaźń_*.txt"))
    assert len(pasujace) == 1, "polskie znaki mają zostać zachowane także w nazwie pliku"
    assert "Zażółć gęślą jaźń." in pasujace[0].read_text(encoding="utf-8")


def test_manifest_i_checkpoint_powstaja_i_sa_spojne(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(),
        konfiguracja,
        nazwa_projektu="Test spójności",
        zegar=_zegar_krokowy(),
        zegar_lokalny=_zegar_lokalny_krokowy(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert len(manifest["zrodla"]) == 4
    assert wynik.sciezka_raportu.exists()

    log_wazny = (wynik.katalog_projektu / "logi" / "log_wazne.txt").read_text(encoding="utf-8")
    assert log_wazny.startswith("--- 2026-08-26 (czas lokalny) ---")
    assert "Projekt zakończony|" in log_wazny


def test_log_wazny_jest_prowadzony_w_czasie_lokalnym(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(),
        konfiguracja,
        nazwa_projektu="Test stref czasowych",
        zegar=_zegar_krokowy(),
        zegar_lokalny=_zegar_lokalny_krokowy(),
    )

    katalog_logow = wynik.katalog_projektu / "logi"
    log_wazny = (katalog_logow / "log_wazne.txt").read_text(encoding="utf-8")
    log_szczegolowy = (katalog_logow / "log_szczegolowy.txt").read_text(encoding="utf-8")

    # Zegar lokalny testu startuje o 22:30, więc taką godzinę ma pierwszy wpis.
    assert log_wazny.startswith("--- 2026-08-26 (czas lokalny) ---")
    assert "Projekt utworzony|22:30" in log_wazny

    # Log szczegółowy nie korzysta z podstawionych zegarów, tylko z zegara
    # systemowego, dlatego sprawdzany jest jego rozjazd wobec bieżącego czasu
    # UTC. Zapis w czasie lokalnym dałby tu przesunięcie o pełną strefę.
    pierwszy_znacznik = log_szczegolowy.split("|", 1)[0].split(",", 1)[0]
    zapisany = datetime.strptime(pierwszy_znacznik, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    assert abs((datetime.now(UTC) - zapisany).total_seconds()) < 300


def test_wznowienie_nie_duplikuje_ani_nie_gubi_zrodel(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pierwsze = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test wznowienia", zegar=_zegar_krokowy()
    )
    pliki_po_pierwszym = sorted(
        p.name for p in (pierwsze.katalog_projektu / "pliki_wynikowe").iterdir()
    )
    manifest_pierwszy = json.loads(pierwsze.sciezka_manifestu.read_text(encoding="utf-8"))

    drugie = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test wznowienia", zegar=_zegar_krokowy()
    )
    pliki_po_drugim = sorted(p.name for p in (drugie.katalog_projektu / "pliki_wynikowe").iterdir())
    manifest_drugi = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))

    assert drugie.wznowiono is True
    assert pliki_po_drugim == pliki_po_pierwszym
    assert len(manifest_drugi["zrodla"]) == len(manifest_pierwszy["zrodla"]) == 4
    assert len(manifest_drugi["wyniki"]) == len(manifest_pierwszy["wyniki"])

    identyfikatory = [zrodlo["identyfikator"] for zrodlo in manifest_drugi["zrodla"]]
    assert len(identyfikatory) == len(set(identyfikatory))


def test_bledne_wejscie_nie_zatrzymuje_potoku(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pozycje = [
        *_pozycje(),
        przyjmij_plik(
            KATALOG_DANYCH / "nie_ma_takiego_pliku.txt", datetime(2026, 8, 26, tzinfo=UTC)
        ),
    ]
    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test odporności", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_przetworzonych == 4
    assert wynik.liczba_bledow == 1

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    statusy = [zrodlo["status"] for zrodlo in manifest["zrodla"]]
    assert statusy.count("blad") == 1


def test_zrodlo_ponad_limit_slow_jest_pominiete_a_nie_bledne(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path, bezpieczny_limit_slow=5)
    moment = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
    pozycje = [
        przyjmij_tekst("Ten tekst ma zdecydowanie więcej niż pięć słów w swojej treści.", moment),
        przyjmij_tekst("Krótki tekst.", moment),
    ]

    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test limitu słów", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0
    assert wynik.liczba_przetworzonych == 1

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    pominiete = [zrodlo for zrodlo in manifest["zrodla"] if zrodlo["status"] == "pominiete"]
    assert len(pominiete) == 1
    assert "etapu szóstego" in (pominiete[0]["komunikat_bledu"] or "")

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba źródeł pominiętych: 1" in raport
    assert "Liczba źródeł z błędem: 0" in raport

    log_szczegolowy = (wynik.katalog_projektu / "logi" / "log_szczegolowy.txt").read_text(
        encoding="utf-8"
    )
    assert "Pominięto źródło" in log_szczegolowy


def test_plik_ponad_bezpieczny_limit_rozmiaru_jest_pominiety(tmp_path: Path) -> None:
    katalog_zrodel = tmp_path / "zrodla"
    katalog_zrodel.mkdir()
    duzy_plik = katalog_zrodel / "duzy.txt"
    duzy_plik.write_text("słowo " * 200_000, encoding="utf-8")

    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", bezpieczny_limit_mb=1)
    pozycje = [przyjmij_plik(duzy_plik, datetime(2026, 8, 26, 9, 0, tzinfo=UTC))]

    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test limitu rozmiaru", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert [zrodlo["status"] for zrodlo in manifest["zrodla"]] == ["pominiete"]


def test_wylaczone_zachowywanie_oryginalow_nie_tworzy_podkatalogu(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path, zachowuj_oryginaly=False)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test bez oryginałów", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_przetworzonych == 4
    assert not (wynik.katalog_projektu / "materialy_zrodlowe").exists()
    assert list((wynik.katalog_projektu / "pliki_wynikowe").iterdir())


def test_wlaczone_zachowywanie_oryginalow_zapisuje_materialy_zrodlowe(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        _pozycje(), konfiguracja, nazwa_projektu="Test z oryginałami", zegar=_zegar_krokowy()
    )

    materialy = wynik.katalog_projektu / "materialy_zrodlowe"
    assert len(list(materialy.iterdir())) == 4
