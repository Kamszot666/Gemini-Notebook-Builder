"""Test end-to-end zmian ręcznych: brakujące pliki, przepakowanie grup, zastąpienie treści.

Trzy sytuacje z etapu czternastego, sprawdzane przez cały potok, a nie tylko
jednostkowo. Po pierwsze, plik wynikowy usunięty ręcznie z dysku: sprawdzenie
i zmiana statusu zachodzą wyłącznie na początku przebiegu i są odwracalne.
Po drugie, dopisanie źródła do istniejącej grupy: grupa jest pakowana od nowa,
a stary plik zastąpiony jest wymieniony w raporcie i w manifeście. Po trzecie,
zastąpienie treści źródła plikiem zapisanym ręcznie, z zachowaniem
identyfikatora i pochodzenia.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from gnb.core.konfiguracja import Konfiguracja
from gnb.ingestion.wejscie import PozycjaWejsciowa, przyjmij_tekst
from gnb.persistence.checkpoint import wczytaj
from gnb.persistence.pliki_wynikowe import znajdz_brakujace_pliki
from gnb.persistence.projekt import ustal_uklad
from gnb.potok import WynikPrzetwarzania, odtworz_wejscia, przetworz_projekt

_MOMENT = datetime(2026, 9, 25, 9, 0, tzinfo=UTC)
_NAZWA = "Test zmian ręcznych"

_TEKST_A = "Notatka pierwsza mówi o porządkowaniu materiałów źródłowych przed importem."
_TEKST_B = "Notatka druga przypomina o sprawdzeniu dat publikacji artykułów w bazie."
_TEKST_C = "Notatka trzecia dotyczy rozróżniania oryginału od przedruku w archiwum."


def _zegar_krokowy() -> Callable[[], datetime]:
    stan = {"teraz": datetime(2026, 9, 25, 10, 0, tzinfo=UTC)}

    def zegar() -> datetime:
        stan["teraz"] = stan["teraz"] + timedelta(seconds=1)
        return stan["teraz"]

    return zegar


def _konfiguracja(tmp_path: Path) -> Konfiguracja:
    return Konfiguracja(katalog_wynikow=tmp_path / "wyniki")


def _pozycje(*tresci: str, grupa: str | None = None) -> list[PozycjaWejsciowa]:
    return [przyjmij_tekst(tresc, _MOMENT, grupa=grupa) for tresc in tresci]


def _przetworz(
    tmp_path: Path,
    pozycje: list[PozycjaWejsciowa],
    **argumenty: Any,
) -> WynikPrzetwarzania:
    return przetworz_projekt(
        pozycje,
        _konfiguracja(tmp_path),
        nazwa_projektu=_NAZWA,
        zegar=_zegar_krokowy(),
        **argumenty,
    )


def _manifest(wynik: WynikPrzetwarzania) -> dict[str, Any]:
    return json.loads(wynik.sciezka_manifestu.read_text(encoding="utf-8"))


def _pierwsze_zrodlo(manifest: dict[str, Any]) -> str:
    return str(manifest["zrodla"][0]["identyfikator"])


def _pliki_txt(wynik: WynikPrzetwarzania) -> list[Path]:
    return sorted((wynik.katalog_projektu / "pliki_wynikowe").glob("*.txt"))


def _log_wazny(wynik: WynikPrzetwarzania) -> str:
    return (wynik.katalog_projektu / "logi" / "log_wazne.txt").read_text(encoding="utf-8")


def _log_szczegolowy(wynik: WynikPrzetwarzania) -> str:
    return (wynik.katalog_projektu / "logi" / "log_szczegolowy.txt").read_text(encoding="utf-8")


def _raport(wynik: WynikPrzetwarzania) -> str:
    return wynik.sciezka_raportu.read_text(encoding="utf-8")


def _statusy(wynik: WynikPrzetwarzania) -> dict[str, str]:
    return {zrodlo["identyfikator"]: zrodlo["status"] for zrodlo in _manifest(wynik)["zrodla"]}


# --- brakujące pliki wynikowe -------------------------------------------------


def test_brakujacy_plik_grupy_pomija_wszystkie_jej_zrodla_na_poczatku_przebiegu(
    tmp_path: Path,
) -> None:
    pozycje = [*_pozycje(_TEKST_A, _TEKST_B, grupa="Grupa"), *_pozycje(_TEKST_C)]
    pierwszy = _przetworz(tmp_path, pozycje)
    assert pierwszy.liczba_przetworzonych == 3
    pliki = _pliki_txt(pierwszy)
    assert len(pliki) == 2
    plik_grupy = next(plik for plik in pliki if _TEKST_A in plik.read_text(encoding="utf-8"))
    plik_grupy.unlink()

    # Samo sprawdzenie zgodności niczego nie zmienia w checkpoincie: to tylko
    # odczyt, z którego korzysta wyświetlanie strony projektu.
    uklad = ustal_uklad(_konfiguracja(tmp_path).katalog_wynikow, _NAZWA)
    checkpoint = wczytaj(uklad.checkpoint)
    assert checkpoint is not None
    brakujace = znajdz_brakujace_pliki(uklad, checkpoint)
    assert [brak.nazwa for brak in brakujace] == [plik_grupy.name]
    assert len(brakujace[0].identyfikatory_zrodel) == 2
    assert set(_statusy(pierwszy).values()) == {"spakowane"}
    ponownie = wczytaj(uklad.checkpoint)
    assert ponownie is not None
    assert {stan.status for stan in ponownie.zrodla.values()} == {"spakowane"}

    # Nowy przebieg z samym trzecim źródłem: wejścia grupy nie są podane ponownie.
    drugi = _przetworz(tmp_path, _pozycje(_TEKST_C))

    statusy = _statusy(drugi)
    assert sorted(statusy.values()) == ["pominiete", "pominiete", "spakowane"]
    assert drugi.liczba_pominietych == 2
    manifest = _manifest(drugi)
    pominiete = [zrodlo for zrodlo in manifest["zrodla"] if zrodlo["status"] == "pominiete"]
    for zrodlo in pominiete:
        assert "plik wynikowy usunięty ręcznie z dysku" in zrodlo["komunikat_bledu"]
        assert plik_grupy.name in zrodlo["komunikat_bledu"]
        assert zrodlo["pliki_wynikowe"] == []

    raport = _raport(drugi)
    assert "Źródła nieprzetworzone, liczba: 2" in raport
    for zrodlo in pominiete:
        assert f"Identyfikator: {zrodlo['identyfikator']}" in raport
    assert "plik wynikowy usunięty ręcznie z dysku" in raport

    assert _log_wazny(drugi).count("Uwaga, plik wynikowy usunięty ręcznie z dysku:") == 2
    assert "plik wynikowy usunięty ręcznie z dysku" in _log_szczegolowy(drugi)


def test_wznowienie_z_zapisanych_wejsc_nie_cofa_pominiecia_po_cichu(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A))
    (plik,) = _pliki_txt(pierwszy)
    plik.unlink()

    drugi = _przetworz(tmp_path, _wejscia_projektu(tmp_path), ponownie_przetwarzaj_usuniete=False)

    assert set(_statusy(drugi).values()) == {"pominiete"}
    assert not _pliki_txt(drugi)
    assert "Źródła nieprzetworzone, liczba: 1" in _raport(drugi)


def test_ponowne_dodanie_zrodla_z_usunietym_plikiem_przetwarza_je_od_nowa(tmp_path: Path) -> None:
    pozycje = _pozycje(_TEKST_A)
    pierwszy = _przetworz(tmp_path, pozycje)
    (plik,) = _pliki_txt(pierwszy)
    plik.unlink()

    drugi = _przetworz(tmp_path, pozycje)

    # W tym samym przebiegu sprawdzenie zamienia źródło w pominięte, a ponowne
    # podanie tego samego wejścia od razu przetwarza je od nowa: pominięcie jest
    # odwracalne i nie może uchodzić za źródło już obecne w projekcie.
    assert set(_statusy(drugi).values()) == {"spakowane"}
    assert len(_pliki_txt(drugi)) == 1
    assert _TEKST_A in _pliki_txt(drugi)[0].read_text(encoding="utf-8")
    assert "Źródła już obecne w projekcie" not in _raport(drugi)
    assert "Źródła nieprzetworzone" not in _raport(drugi)
    assert "Uwaga, plik wynikowy usunięty ręcznie z dysku:" in _log_wazny(drugi)


def test_pominiete_zrodlo_z_usunietym_plikiem_bez_ponownego_dodania_zostaje_pominiete(
    tmp_path: Path,
) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A, _TEKST_B))
    plik_a = next(plik for plik in _pliki_txt(pierwszy) if _TEKST_A in plik.read_text("utf-8"))
    plik_a.unlink()

    drugi = _przetworz(tmp_path, _pozycje(_TEKST_B))

    statusy = list(_statusy(drugi).values())
    assert sorted(statusy) == ["pominiete", "spakowane"]
    assert "Źródła nieprzetworzone, liczba: 1" in _raport(drugi)


def test_brak_pliku_md_nie_zmienia_statusu_zrodla(tmp_path: Path) -> None:
    tresc = (
        "# Tytuł dokumentu\n\n## Pierwsza sekcja\n\nTreść pierwszej sekcji jest dość długa.\n\n"
        "## Druga sekcja\n\n- punkt pierwszy\n- punkt drugi\n- punkt trzeci\n\n"
        "### Podsekcja\n\n```\nkod\n```\n"
    )
    moment = _MOMENT
    pozycje = [przyjmij_tekst(tresc, moment, format_tekstu="md")]
    pierwszy = _przetworz(tmp_path, pozycje)
    pliki_md = list((pierwszy.katalog_projektu / "pliki_wynikowe").glob("*.md"))
    assert pliki_md, "przygotowana treść ma spełniać regułę generowania MD"
    pliki_md[0].unlink()

    drugi = _przetworz(tmp_path, pozycje)

    assert set(_statusy(drugi).values()) == {"spakowane"}
    assert "Uwaga, brak pliku wersji MD na dysku:" in _log_wazny(drugi)


# --- przepakowanie grupy -------------------------------------------------------


def test_dopisanie_zrodla_do_grupy_pakuje_cala_grupe_od_nowa(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A, grupa="Grupa"))
    (stary_plik,) = _pliki_txt(pierwszy)

    drugi = _przetworz(tmp_path, _pozycje(_TEKST_B, grupa="Grupa"))

    (nowy_plik,) = _pliki_txt(drugi)
    assert nowy_plik.name != stary_plik.name
    assert not stary_plik.exists()
    tresc = nowy_plik.read_text(encoding="utf-8")
    assert _TEKST_A in tresc
    assert _TEKST_B in tresc
    assert tresc.count("Identyfikator źródła: ") == 2

    manifest = _manifest(drugi)
    assert set(_statusy(drugi).values()) == {"spakowane"}
    (wpis_wyniku,) = manifest["wyniki"]
    assert wpis_wyniku["liczba_zrodel"] == 2
    (zastapiony,) = manifest["zastapione_pliki_grup"]
    assert zastapiony["stara_nazwa"].endswith(stary_plik.name)
    assert zastapiony["nowa_nazwa"] == nowy_plik.name

    raport = _raport(drugi)
    assert f"Plik grupy zastąpiony: {stary_plik.name} → {nowy_plik.name}" in raport
    assert "Liczba plików TXT: 1" in raport
    assert "Grupa źródeł przepakowana od nowa:" in _log_wazny(drugi)
    assert "Plik grupy zastąpiony:" in _log_wazny(drugi)


def test_zrodlo_bez_grupy_nie_wciaga_do_przepakowania_cudzej_grupy(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A, grupa="Grupa"))
    (plik_grupy,) = _pliki_txt(pierwszy)

    drugi = _przetworz(tmp_path, _pozycje(_TEKST_B))

    assert plik_grupy.exists()
    assert len(_pliki_txt(drugi)) == 2
    assert "Plik grupy zastąpiony" not in _raport(drugi)


def test_przepakowanie_grupy_bez_tekstu_posredniego_zostawia_stary_plik(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A, grupa="Grupa"))
    (stary_plik,) = _pliki_txt(pierwszy)
    for plik in (pierwszy.katalog_projektu / "wyniki_posrednie").glob("*.znormalizowany.txt"):
        plik.unlink()

    drugi = _przetworz(tmp_path, _pozycje(_TEKST_B, grupa="Grupa"))

    assert stary_plik.exists()
    assert len(_pliki_txt(drugi)) == 2
    assert "nie może być przepakowana" in _log_szczegolowy(drugi)
    assert "Plik grupy zastąpiony" not in _raport(drugi)


# --- zastąpienie treści plikiem ---------------------------------------------


def _zapisz_zastepczy(tmp_path: Path, tresc: str, nazwa: str = "zastepczy.txt") -> Path:
    katalog = tmp_path / "zastepcze"
    katalog.mkdir(exist_ok=True)
    plik = katalog / nazwa
    plik.write_text(tresc, encoding="utf-8")
    return plik


def _wejscia_projektu(tmp_path: Path) -> list[PozycjaWejsciowa]:
    uklad = ustal_uklad(_konfiguracja(tmp_path).katalog_wynikow, _NAZWA)
    checkpoint = wczytaj(uklad.checkpoint)
    assert checkpoint is not None
    return odtworz_wejscia(checkpoint, _konfiguracja(tmp_path))


def test_zastapienie_tresci_zachowuje_identyfikator_i_dopisuje_uwage(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A))
    identyfikator = _pierwsze_zrodlo(_manifest(pierwszy))
    pochodzenie = _manifest(pierwszy)["zrodla"][0]["pochodzenie"]
    zastepczy = _zapisz_zastepczy(
        tmp_path, "Treść zapisana ręcznie zamiast pierwotnej, dużo lepsza i pełniejsza."
    )

    drugi = _przetworz(
        tmp_path, _wejscia_projektu(tmp_path), zastepcze_tresci={identyfikator: zastepczy}
    )

    manifest = _manifest(drugi)
    (zrodlo,) = manifest["zrodla"]
    assert zrodlo["identyfikator"] == identyfikator
    assert zrodlo["pochodzenie"] == pochodzenie
    assert zrodlo["status"] == "spakowane"
    assert zrodlo["tresc_zastapiona_plikiem"] == "zastepczy.txt"

    (plik,) = _pliki_txt(drugi)
    tresc = plik.read_text(encoding="utf-8")
    assert "Treść zapisana ręcznie zamiast pierwotnej" in tresc
    assert _TEKST_A not in tresc
    assert "Uwaga o treści: treść zapisana ręcznie w pliku zastepczy.txt" in tresc
    assert f"Identyfikator źródła: {identyfikator}" in tresc

    assert "Treść źródła zastąpiona plikiem:" in _log_wazny(drugi)
    manifest_txt = (drugi.katalog_projektu / "manifest.txt").read_text(encoding="utf-8")
    assert "Treść zastąpiona plikiem zapisanym ręcznie: zastepczy.txt" in manifest_txt


def test_zastapienie_pustym_plikiem_nie_rusza_dotychczasowego_stanu(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A))
    identyfikator = _pierwsze_zrodlo(_manifest(pierwszy))
    (stary_plik,) = _pliki_txt(pierwszy)
    zastepczy = _zapisz_zastepczy(tmp_path, "   \n")

    drugi = _przetworz(
        tmp_path, _wejscia_projektu(tmp_path), zastepcze_tresci={identyfikator: zastepczy}
    )

    (zrodlo,) = _manifest(drugi)["zrodla"]
    assert zrodlo["status"] == "spakowane"
    assert zrodlo["tresc_zastapiona_plikiem"] is None
    assert _TEKST_A in stary_plik.read_text(encoding="utf-8")
    raport = _raport(drugi)
    assert "Zastąpienia treści, które się nie powiodły, liczba: 1" in raport
    assert "Dotychczasowy stan źródła nie został zmieniony." in raport
    assert "Uwaga, zastąpienie treści źródła nie powiodło się:" in _log_wazny(drugi)


def test_zastapienie_tresci_zrodla_z_grupy_przepakowuje_cala_grupe(tmp_path: Path) -> None:
    pierwszy = _przetworz(tmp_path, _pozycje(_TEKST_A, _TEKST_B, grupa="Grupa"))
    (stary_plik,) = _pliki_txt(pierwszy)
    identyfikator_a = _pierwsze_zrodlo(_manifest(pierwszy))
    zastepczy = _zapisz_zastepczy(tmp_path, "Nowa treść pierwszego źródła grupy, zapisana ręcznie.")

    drugi = _przetworz(
        tmp_path, _wejscia_projektu(tmp_path), zastepcze_tresci={identyfikator_a: zastepczy}
    )

    # Skład grupy się nie zmienił, więc plik ma tę samą nazwę i został nadpisany
    # w miejscu: to nie jest zastąpienie pliku, więc raport go nie wymienia.
    (nowy_plik,) = _pliki_txt(drugi)
    assert nowy_plik == stary_plik
    tresc = nowy_plik.read_text(encoding="utf-8")
    assert "Nowa treść pierwszego źródła grupy, zapisana ręcznie." in tresc
    assert _TEKST_A not in tresc
    assert _TEKST_B in tresc
    assert tresc.count("Identyfikator źródła: ") == 2
    assert "Plik grupy zastąpiony:" not in _raport(drugi)
    assert _manifest(drugi)["zastapione_pliki_grup"] == []
