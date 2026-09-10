"""Testy komendy `python -m gnb.cli diagnostyka`."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from gnb import cli
from gnb.cli import NARZEDZIA, Narzedzie, _sprawdz_narzedzie


def _uruchom_diagnostyke(*dodatkowe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "gnb.cli", "diagnostyka", *dodatkowe],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


class _FalszywyStrumien:
    """Strumień udający standardowe wyjście, ale niebędący ``io.TextIOWrapper``.

    Służy sprawdzeniu, że przełączenie kodowania rozpoznaje strumień po metodzie
    ``reconfigure``, a nie po konkretnym typie. Wariant `rzuca` sprawdza, że
    nieudane przełączenie nie zatrzymuje aplikacji.
    """

    def __init__(self, *, rzuca: bool = False) -> None:
        self.wywolania: list[dict[str, Any]] = []
        self._rzuca = rzuca

    def reconfigure(self, **argumenty: Any) -> None:
        self.wywolania.append(argumenty)
        if self._rzuca:
            raise ValueError("Tego strumienia nie da się przełączyć.")


def test_diagnostyka_zwraca_kod_zero_niezaleznie_od_dostepnosci_narzedzi() -> None:
    """Brak narzędzia opcjonalnego nie może wywalić komendy diagnostyki."""

    wynik = _uruchom_diagnostyke()

    assert wynik.returncode == 0
    assert "Raport diagnostyczny" in wynik.stdout
    assert "Koniec raportu" in wynik.stdout


def test_diagnostyka_wymienia_wszystkie_sprawdzane_narzedzia() -> None:
    """Raport musi wymieniać nazwę każdego z sześciu narzędzi z sekcji piątej CLAUDE.md."""

    wynik = _uruchom_diagnostyke()

    for nazwa in ("FFmpeg", "Tesseract", "LibreOffice", "MuseScore", "Java", "Audiveris"):
        assert nazwa in wynik.stdout


def test_raport_diagnostyki_wymienia_dane_jezykowe_ocr() -> None:
    """Raport ma osobny wiersz o zainstalowanych danych językowych Tesseracta."""
    raport = cli.zbuduj_raport_diagnostyki()

    assert "Dane językowe OCR:" in raport


def test_diagnostyka_z_opcja_plik_zapisuje_raport_w_utf8(tmp_path: Path) -> None:
    """Opcja --plik zapisuje raport wprost do pliku UTF-8 ze znacznikiem kolejności bajtów.

    Zapis wprost pomija przekierowanie powłoki, które na Windows psuje polskie
    znaki. Test czerwieni się, gdy plik przestanie być czytelnym UTF-8 albo gdy
    zgubi znaki diakrytyczne.
    """

    cel = tmp_path / "podkatalog" / "raport.txt"

    kod = cli.uruchom_diagnostyke(str(cel))

    assert kod == 0
    surowe = cel.read_bytes()
    assert surowe.startswith(b"\xef\xbb\xbf")
    tekst = cel.read_text(encoding="utf-8-sig")
    assert "narzędzi zewnętrznych" in tekst
    assert "Koniec raportu" in tekst


def test_diagnostyka_przez_wiersz_polecen_z_opcja_plik(tmp_path: Path) -> None:
    """Uruchomiona jako podproces komenda zapisuje czytelny raport do wskazanego pliku."""

    cel = tmp_path / "raport.txt"

    wynik = _uruchom_diagnostyke("--plik", str(cel))

    assert wynik.returncode == 0
    assert cel.read_text(encoding="utf-8-sig").count("ż") >= 1


def test_wymus_kodowanie_utf8_przelacza_strumien_bez_typu_textiowrapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Przełączenie kodowania rozpoznaje strumień po metodzie, a nie po typie.

    Test czerwieni się, gdy kod wróci do sprawdzania ``isinstance`` z konkretnym
    typem: sztuczny strumień nie jest ``io.TextIOWrapper``, więc nie zostałby
    wtedy przełączony.
    """

    falszywy_out = _FalszywyStrumien()
    falszywy_err = _FalszywyStrumien()
    monkeypatch.setattr(sys, "stdout", falszywy_out)
    monkeypatch.setattr(sys, "stderr", falszywy_err)

    cli._wymus_kodowanie_utf8()

    assert falszywy_out.wywolania == [{"encoding": "utf-8", "errors": "replace"}]
    assert falszywy_err.wywolania == [{"encoding": "utf-8", "errors": "replace"}]


def test_wymus_kodowanie_utf8_toleruje_nieudane_przelaczenie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nieudane przełączenie kodowania nie może zatrzymać aplikacji."""

    monkeypatch.setattr(sys, "stdout", _FalszywyStrumien(rzuca=True))
    monkeypatch.setattr(sys, "stderr", _FalszywyStrumien(rzuca=True))

    cli._wymus_kodowanie_utf8()


def _wpis_musescore() -> Narzedzie:
    return next(narzedzie for narzedzie in NARZEDZIA if narzedzie.nazwa == "MuseScore")


def test_wpis_musescore_nie_obiecuje_konwersji_ani_utraty_funkcji() -> None:
    """Po wariancie bez renderowania wpis nie może mówić o konwersji ani o utracie funkcji."""
    wpis = _wpis_musescore()
    assert "konwersj" not in wpis.do_czego_sluzy.lower()
    assert "nie jest uruchamiany" in wpis.do_czego_sluzy
    assert "nic w tej wersji" in wpis.co_przestanie_dzialac


def test_wyszukiwarka_musescore_jest_sprawdzana_przed_zmienna_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Gdy narzędzie ma wyszukiwarkę, jej wynik ma pierwszeństwo przed shutil.which."""
    plik_wyszukiwarki = tmp_path / "MuseScore4.exe"
    plik_wyszukiwarki.write_bytes(b"")

    monkeypatch.setattr(cli.shutil, "which", lambda _nazwa: str(tmp_path / "z_path.exe"))
    monkeypatch.setattr(cli, "_znajdz_wersje", lambda *_argumenty: "MuseScore 4.4")

    wpis = Narzedzie(
        nazwa="MuseScore",
        polecenia=("mscore",),
        argument_wersji="--version",
        do_czego_sluzy="opis",
        co_przestanie_dzialac="nic",
        wyszukiwarka=lambda: plik_wyszukiwarki,
    )
    wiersz = _sprawdz_narzedzie(wpis)

    assert "MuseScore: JEST" in wiersz
    assert str(plik_wyszukiwarki) in wiersz
    assert "z_path.exe" not in wiersz


def test_wyszukiwarka_zwracajaca_nic_daje_wiersz_brak_z_uczciwymi_zdaniami(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _nazwa: None)
    wpis = Narzedzie(
        nazwa="MuseScore",
        polecenia=("mscore",),
        argument_wersji="--version",
        do_czego_sluzy="jest wykrywany, ale nie jest uruchamiany",
        co_przestanie_dzialac="nic w tej wersji",
        wyszukiwarka=lambda: None,
    )
    wiersz = _sprawdz_narzedzie(wpis)

    assert wiersz.startswith("MuseScore: BRAK")
    assert "przestanie działać konwersja" not in wiersz


def _wpis_java() -> Narzedzie:
    return next(narzedzie for narzedzie in NARZEDZIA if narzedzie.nazwa == "Java")


def test_wpis_java_nie_obiecuje_ze_jest_zawsze_potrzebna() -> None:
    """Zweryfikowano uruchomieniem: instalator Audiverisa dla Windows niesie własną
    Javę i systemowej w ogóle nie używa, więc wpis nie może twierdzić inaczej."""
    wpis = _wpis_java()
    assert "własne" in wpis.do_czego_sluzy or "samodzielne" in wpis.do_czego_sluzy
    assert "nic w tej instalacji" in wpis.co_przestanie_dzialac


def test_znajdz_wersje_woli_wiersz_z_cyfra_nad_dosłownie_pierwszy(tmp_path: Path) -> None:
    """Chroni przed regresją do „zawsze pierwszy wiersz”. Audiveris wypisuje samą
    nazwę programu na pierwszym wierszu, a numer wersji dopiero na drugim —
    dokładnie ten przypadek, w którym dosłownie pierwszy wiersz by zawiódł.
    """
    skrypt = tmp_path / "falszywy_audiveris.py"
    skrypt.write_text("print('Audiveris')\nprint('- Version:      5.11.0')\n", encoding="utf-8")

    wersja = cli._znajdz_wersje(sys.executable, str(skrypt))

    assert wersja is not None
    assert "5.11.0" in wersja
