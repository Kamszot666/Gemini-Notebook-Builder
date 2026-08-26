"""Testy zapisu plików wynikowych: TXT zawsze, MD warunkowo."""

from __future__ import annotations

from pathlib import Path

from gnb.core.model import DokumentZnormalizowany
from gnb.core.stale import FormatWynikowy
from gnb.output.regula_md import DecyzjaFormatu
from gnb.output.zapis import zapisz_wyniki

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
