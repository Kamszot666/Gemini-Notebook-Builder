"""Testy zapisu plików wynikowych: TXT zawsze, MD warunkowo."""

from __future__ import annotations

from pathlib import Path

from gnb.core.model import DokumentZnormalizowany
from gnb.core.stale import FormatWynikowy
from gnb.output.regula_md import DecyzjaFormatu
from gnb.output.zapis import zapisz_plik_pakietu, zapisz_wyniki

_DOKUMENT = DokumentZnormalizowany(
    identyfikator_zrodla="plik_tekstowy-1",
    tekst="Pierwszy wiersz.\n\nDrugi wiersz z ą, ć, ż.",
    liczba_slow=8,
    liczba_znakow=40,
)


def _decyzja(generuj_md: bool) -> DecyzjaFormatu:
    return DecyzjaFormatu(
        generuj_md=generuj_md,
        spelnione_warunki=("co najmniej jedna tabela",) if generuj_md else (),
        poziom_pewnosci_wystarczajacy=generuj_md,
    )


def test_txt_powstaje_zawsze_bez_bom_i_z_koncem_lf(tmp_path: Path) -> None:
    wyniki = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT, _decyzja(False))

    assert [wynik.format for wynik in wyniki] == [FormatWynikowy.TXT]
    dane = (tmp_path / "notatka.txt").read_bytes()
    assert not dane.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in dane
    assert dane.endswith(b"\n")


def test_md_powstaje_gdy_regula_na_to_pozwala(tmp_path: Path) -> None:
    wyniki = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT, _decyzja(True))

    formaty = {wynik.format for wynik in wyniki}
    assert formaty == {FormatWynikowy.TXT, FormatWynikowy.MD}
    assert (tmp_path / "notatka.md").exists()


def test_md_nie_powstaje_gdy_format_wylaczony_w_konfiguracji(tmp_path: Path) -> None:
    wyniki = zapisz_wyniki(
        tmp_path,
        "notatka",
        "plik_tekstowy-1",
        _DOKUMENT,
        _decyzja(True),
        formaty_wlaczone=("txt",),
    )
    assert [wynik.format for wynik in wyniki] == [FormatWynikowy.TXT]
    assert not (tmp_path / "notatka.md").exists()


def test_opis_pliku_zawiera_zgodne_liczniki_i_sume_kontrolna(tmp_path: Path) -> None:
    (wynik,) = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT, _decyzja(False))

    dane = (tmp_path / "notatka.txt").read_bytes()
    assert wynik.rozmiar_bajtow == len(dane)
    assert wynik.liczba_slow == len(dane.decode("utf-8").split())
    assert wynik.identyfikatory_zrodel == ["plik_tekstowy-1"]
    assert len(wynik.checksum) == 64


def test_liczba_znakow_pliku_jest_wieksza_o_koncowy_znak_nowej_linii(tmp_path: Path) -> None:
    """Dwie miary liczą co innego, dlatego noszą różne nazwy.

    Liczba znaków źródła liczy sam tekst dokumentu i służy do sprawdzania limitu
    notatnika. Liczba znaków pliku liczy jego zawartość, więc obejmuje też znak
    nowej linii dopisywany na końcu każdego pliku wynikowego.
    """
    (wynik,) = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT, _decyzja(False))

    tresc = (tmp_path / "notatka.txt").read_text(encoding="utf-8")
    assert tresc.endswith("\n")
    assert wynik.liczba_znakow == len(tresc)
    assert wynik.liczba_znakow == len(_DOKUMENT.tekst) + 1
    assert wynik.liczba_slow == _DOKUMENT.liczba_slow


def test_zapisz_plik_pakietu_pisze_txt_bez_bom_z_koncem_lf_i_liczy_zawartosc(
    tmp_path: Path,
) -> None:
    tresc = (
        "Tytuł: A\n\nPierwsza treść.\n\nKolejny fragment tego pliku:\n\nTytuł: B\n\nDruga treść."
    )
    wynik = zapisz_plik_pakietu(
        tmp_path, "grupa_temat_abcd1234", tresc, ["plik_tekstowy-1", "plik_tekstowy-2"]
    )

    dane = (tmp_path / "grupa_temat_abcd1234.txt").read_bytes()
    assert not dane.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in dane
    assert dane.endswith(b"\n")
    assert wynik.format == FormatWynikowy.TXT
    assert wynik.identyfikatory_zrodel == ["plik_tekstowy-1", "plik_tekstowy-2"]
    assert wynik.rozmiar_bajtow == len(dane)
    assert wynik.liczba_slow == len(dane.decode("utf-8").split())
    assert len(wynik.checksum) == 64


def test_zapisz_plik_pakietu_nie_tworzy_pliku_md(tmp_path: Path) -> None:
    zapisz_plik_pakietu(tmp_path, "czesc", "Tytuł: A\nCzęść: 1 z 2\n\nTreść.", ["plik_dokument-1"])

    assert (tmp_path / "czesc.txt").exists()
    assert not (tmp_path / "czesc.md").exists()
