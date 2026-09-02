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


def _tresc_po_naglowku(tresc_pliku: str) -> str:
    """Zwraca treść pliku wynikowego bez nagłówka metadanych.

    Nagłówek jest oddzielony od treści jednym pustym wierszem, więc wystarczy
    odciąć wszystko do pierwszego pustego wiersza.
    """
    _, _, tresc = tresc_pliku.partition("\n\n")
    return tresc


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
    assert _tresc_po_naglowku(tresc_md).startswith("# Jak przygotować bazę wiedzy")
    assert _tresc_po_naglowku(tresc_txt).startswith("Jak przygotować bazę wiedzy")
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


def _tresc_bez_naglowka(sciezka: Path) -> str:
    """Zwraca treść pliku wynikowego po odcięciu nagłówka metadanych."""
    return sciezka.read_text(encoding="utf-8").partition("\n\n")[2]


def test_zrodlo_ponad_limit_slow_jest_dzielone_na_czesci_bez_utraty_tresci(
    tmp_path: Path,
) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path, bezpieczny_limit_slow=5)
    moment = datetime(2026, 8, 26, 9, 0, tzinfo=UTC)
    akapit = "Pierwsze zdanie jest krótkie. Drugie zdanie też jest krótkie. Trzecie kończy akapit."
    duzy_tekst = f"{akapit}\n\n{akapit}\n\n{akapit}"
    pozycje = [
        przyjmij_tekst(duzy_tekst, moment),
        przyjmij_tekst("Krótki tekst.", moment),
    ]

    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test limitu słów", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_pominietych == 0
    assert wynik.liczba_bledow == 0
    assert wynik.liczba_przetworzonych == 2

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    czesci = sorted(p for p in katalog_wynikow.glob("*.txt") if "_czesc_" in p.name)
    assert len(czesci) >= 2

    for plik_czesci in czesci:
        assert "Część: " in plik_czesci.read_text(encoding="utf-8").partition("\n\n")[0]

    slowa_czesci = [slowo for plik in czesci for slowo in _tresc_bez_naglowka(plik).split()]
    assert slowa_czesci == duzy_tekst.split()

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    duze = next(z for z in manifest["zrodla"] if len(z["pliki_wynikowe"]) > 1)
    assert duze["status"] == "spakowane"
    wyniki_z_czesciami = [w for w in manifest["wyniki"] if w["liczba_czesci"]]
    assert {w["liczba_czesci"] for w in wyniki_z_czesciami} == {len(czesci)}
    assert {w["numer_czesci"] for w in wyniki_z_czesciami} == set(range(1, len(czesci) + 1))

    raport = wynik.sciezka_raportu.read_text(encoding="utf-8")
    assert "Liczba źródeł pominiętych: 0" in raport
    assert f"Liczba plików TXT: {len(czesci) + 1}" in raport


def test_plik_binarny_ponad_bezpieczny_limit_rozmiaru_jest_pominiety(tmp_path: Path) -> None:
    katalog_zrodel = tmp_path / "zrodla"
    katalog_zrodel.mkdir()
    duzy_plik = katalog_zrodel / "duzy.pdf"
    duzy_plik.write_bytes(b"%PDF-1.4\n" + b"0" * 1_200_000)

    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", bezpieczny_limit_mb=1)
    pozycje = [przyjmij_plik(duzy_plik, datetime(2026, 8, 26, 9, 0, tzinfo=UTC))]

    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test limitu rozmiaru", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_pominietych == 1
    assert wynik.liczba_bledow == 0

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))
    assert [zrodlo["status"] for zrodlo in manifest["zrodla"]] == ["pominiete"]


def test_plik_tekstowy_ponad_bezpieczny_limit_rozmiaru_jest_dzielony_a_nie_pomijany(
    tmp_path: Path,
) -> None:
    """Duży plik tekstowy nie jest odrzucany przy wejściu: dzieli go faza pakowania."""
    katalog_zrodel = tmp_path / "zrodla"
    katalog_zrodel.mkdir()
    duzy_plik = katalog_zrodel / "duzy.txt"
    akapit = "Zdanie pierwsze akapitu. Zdanie drugie akapitu. Zdanie trzecie akapitu."
    duzy_plik.write_text("\n\n".join([akapit] * 40), encoding="utf-8")

    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path / "wyniki", bezpieczny_limit_slow=25)
    pozycje = [przyjmij_plik(duzy_plik, datetime(2026, 8, 26, 9, 0, tzinfo=UTC))]

    wynik = przetworz_projekt(
        pozycje, konfiguracja, nazwa_projektu="Test dużego tekstu", zegar=_zegar_krokowy()
    )

    assert wynik.liczba_pominietych == 0
    assert wynik.liczba_bledow == 0
    assert wynik.liczba_przetworzonych == 1

    katalog_wynikow = wynik.katalog_projektu / "pliki_wynikowe"
    czesci = sorted(katalog_wynikow.glob("*_czesc_*.txt"))
    assert len(czesci) >= 2
    slowa = [slowo for plik in czesci for slowo in _tresc_bez_naglowka(plik).split()]
    assert slowa == "\n\n".join([akapit] * 40).split()


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


def _naglowek_pliku(sciezka: Path) -> str:
    """Zwraca sam nagłówek metadanych z pliku wynikowego."""
    naglowek, _, _ = sciezka.read_text(encoding="utf-8").partition("\n\n")
    return naglowek


def test_naglowek_metadanych_jest_na_poczatku_pliku_zrodla_plikowego(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        [
            przyjmij_plik(
                KATALOG_DANYCH / "dokument_strukturalny.md", datetime(2026, 8, 26, tzinfo=UTC)
            )
        ],
        konfiguracja,
        nazwa_projektu="Test nagłówka",
        zegar=_zegar_krokowy(),
    )

    (plik_txt,) = (wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt")
    naglowek = _naglowek_pliku(plik_txt)

    assert "Tytuł: Jak przygotować bazę wiedzy dla asystenta AI" in naglowek
    assert "Typ źródła: plik tekstowy" in naglowek
    assert "Plik: dokument_strukturalny.md" in naglowek
    assert "Identyfikator źródła: plik_tekstowy-" in naglowek
    assert "Adres:" not in naglowek


def test_naglowek_jest_identyczny_w_wersji_txt_i_md(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        [
            przyjmij_plik(
                KATALOG_DANYCH / "dokument_strukturalny.md", datetime(2026, 8, 26, tzinfo=UTC)
            )
        ],
        konfiguracja,
        nazwa_projektu="Test zgodności nagłówka",
        zegar=_zegar_krokowy(),
    )

    katalog = wynik.katalog_projektu / "pliki_wynikowe"
    (plik_txt,) = katalog.glob("*.txt")
    (plik_md,) = katalog.glob("*.md")

    assert _naglowek_pliku(plik_txt) == _naglowek_pliku(plik_md)
    assert not _naglowek_pliku(plik_md).startswith("#")


def test_tekst_wklejony_nie_ma_ani_adresu_ani_pliku_w_naglowku(tmp_path: Path) -> None:
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    wynik = przetworz_projekt(
        [
            przyjmij_tekst(
                "Krótka notatka do sprawdzenia nagłówka.", datetime(2026, 8, 26, tzinfo=UTC)
            )
        ],
        konfiguracja,
        nazwa_projektu="Test tekstu wklejonego",
        zegar=_zegar_krokowy(),
    )

    (plik_txt,) = (wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt")
    naglowek = _naglowek_pliku(plik_txt)

    assert "Typ źródła: tekst wklejony" in naglowek
    assert "Adres:" not in naglowek
    assert "Plik:" not in naglowek


def test_limit_slow_jest_liczony_bez_naglowka_metadanych(tmp_path: Path) -> None:
    """Nagłówek jest informacją o źródle, nie jego treścią, więc nie wchodzi do limitu."""
    tresc = "Zdanie z dokładnie dziesięcioma słowami, policzonymi bez nagłówka metadanych."
    liczba_slow = len(tresc.split())
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path, bezpieczny_limit_slow=liczba_slow)

    wynik = przetworz_projekt(
        [przyjmij_tekst(tresc, datetime(2026, 8, 26, tzinfo=UTC))],
        konfiguracja,
        nazwa_projektu="Test limitu bez nagłówka",
        zegar=_zegar_krokowy(),
    )

    assert wynik.liczba_przetworzonych == 1
    assert wynik.liczba_pominietych == 0

    (plik_txt,) = (wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt")
    slowa_w_pliku = len(plik_txt.read_text(encoding="utf-8").split())
    assert slowa_w_pliku > liczba_slow, "plik z nagłówkiem ma więcej słów niż sama treść"


def test_zrodla_bez_ekstrakcji_nie_dostaja_oceny_jakosci(tmp_path: Path) -> None:
    """Tekst wklejony i pliki tekstowe nie podlegają ocenie jakości ekstrakcji.

    Ich treść jest dokładnie tym, co podał użytkownik, więc nie ma czego oceniać.
    Krótki tekst wklejony nie może z tego powodu trafiać do materiałów do
    sprawdzenia.
    """
    wynik = przetworz_projekt(
        _pozycje(),
        Konfiguracja(katalog_wynikow=tmp_path / "wyniki"),
        nazwa_projektu="Test bez oceny",
        zegar=_zegar_krokowy(),
        zegar_lokalny=_zegar_lokalny_krokowy(),
    )

    manifest = json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))

    assert all(zrodlo["ocena_jakosci"] is None for zrodlo in manifest["zrodla"])
    assert all(zrodlo["powody_oceny"] == [] for zrodlo in manifest["zrodla"])
    assert "Materiały do sprawdzenia" not in wynik.sciezka_raportu.read_text(encoding="utf-8")


def test_wznowienie_ze_starszego_checkpointu_dziala(tmp_path: Path) -> None:
    """Katalog projektu założony poprzednią wersją aplikacji nadal daje się wznowić.

    Checkpoint jest tu celowo cofnięty do postaci wersji schematu 3: numer wersji
    wraca do trzech, a pole opisujące liczbę znaków pliku wynikowego odzyskuje
    starą nazwę. Bez migracji odczyt kończył się surowym ``KeyError``, więc każdy
    starszy katalog projektu wywracał program zamiast się wznowić.
    """
    konfiguracja = Konfiguracja(katalog_wynikow=tmp_path)
    pierwsze = przetworz_projekt(
        _pozycje(),
        konfiguracja,
        nazwa_projektu="Test starszego checkpointu",
        zegar=_zegar_krokowy(),
    )
    sciezka_checkpointu = pierwsze.katalog_projektu / "checkpoint.json"
    dane = json.loads(sciezka_checkpointu.read_text(encoding="utf-8"))
    dane["wersja_schematu"] = 3
    for stan in dane["zrodla"].values():
        stan.pop("ocena_jakosci", None)
        stan.pop("powody_oceny", None)
        stan.pop("ostrzezenia", None)
        for wynik in stan["wyniki"]:
            wynik["liczba_znakow"] = wynik.pop("liczba_znakow_pliku")
    sciezka_checkpointu.write_text(json.dumps(dane, ensure_ascii=False), encoding="utf-8")
    sciezka_checkpointu.with_suffix(".json.bak").write_text(
        json.dumps(dane, ensure_ascii=False), encoding="utf-8"
    )

    drugie = przetworz_projekt(
        _pozycje(),
        konfiguracja,
        nazwa_projektu="Test starszego checkpointu",
        zegar=_zegar_krokowy(),
    )

    assert drugie.wznowiono is True
    assert drugie.liczba_przetworzonych == pierwsze.liczba_przetworzonych
    manifest = json.loads(drugie.sciezka_manifestu.read_text(encoding="utf-8"))
    assert len(manifest["zrodla"]) == 4
    assert all(wynik["liczba_znakow_pliku"] > 0 for wynik in manifest["wyniki"])
