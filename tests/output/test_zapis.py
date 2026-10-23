"""Testy zapisu plików wynikowych: MD domyślnie, TXT opcjonalnie."""

from __future__ import annotations

from pathlib import Path

from gnb.core.liczenie_slow import policz_slowa
from gnb.core.model import DokumentZnormalizowany
from gnb.core.stale import FormatWynikowy
from gnb.output.zapis import zapisz_plik_pakietu, zapisz_wyniki

_DOKUMENT = DokumentZnormalizowany(
    identyfikator_zrodla="plik_tekstowy-1",
    tekst="Pierwszy wiersz.\n\nDrugi wiersz z ą, ć, ż.",
    liczba_slow=8,
    liczba_znakow=40,
)

_DOKUMENT_Z_PODEJRZANA_SKLADNIA = DokumentZnormalizowany(
    identyfikator_zrodla="plik_tekstowy-2",
    tekst="# To nie jest nagłówek\n\n- to nie jest lista\n\n1. ani ta\n\n> ani cytat\n\nwzór 2*3*4",
    liczba_slow=20,
    liczba_znakow=70,
)


def test_domyslnie_powstaje_wylacznie_md_bez_bom_i_z_koncem_lf(tmp_path: Path) -> None:
    wyniki = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT)

    assert [wynik.format for wynik in wyniki] == [FormatWynikowy.MD]
    assert not (tmp_path / "notatka.txt").exists()
    dane = (tmp_path / "notatka.md").read_bytes()
    assert not dane.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in dane
    assert dane.endswith(b"\n")


def test_md_powstaje_dla_zrodla_bez_zadnej_struktury_jako_akapity(tmp_path: Path) -> None:
    """Dawniej reguła z sekcji ósmej odmawiała pliku MD dokumentowi bez struktury."""
    zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT)

    assert (tmp_path / "notatka.md").read_text(encoding="utf-8") == (
        "Pierwszy wiersz.\n\nDrugi wiersz z ą, ć, ż.\n"
    )


def test_txt_powstaje_obok_md_gdy_jest_wlaczony(tmp_path: Path) -> None:
    wyniki = zapisz_wyniki(
        tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT, formaty_wlaczone=("md", "txt")
    )

    assert {wynik.format for wynik in wyniki} == {FormatWynikowy.MD, FormatWynikowy.TXT}
    assert (tmp_path / "notatka.md").exists()
    assert (tmp_path / "notatka.txt").exists()


def test_samo_txt_nie_tworzy_pliku_md(tmp_path: Path) -> None:
    wyniki = zapisz_wyniki(
        tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT, formaty_wlaczone=("txt",)
    )

    assert [wynik.format for wynik in wyniki] == [FormatWynikowy.TXT]
    assert not (tmp_path / "notatka.md").exists()


def test_tekst_bez_struktury_jest_escapowany_a_plik_txt_zostaje_doslowny(tmp_path: Path) -> None:
    zapisz_wyniki(
        tmp_path,
        "notatka",
        "plik_tekstowy-2",
        _DOKUMENT_Z_PODEJRZANA_SKLADNIA,
        formaty_wlaczone=("md", "txt"),
    )

    md = (tmp_path / "notatka.md").read_text(encoding="utf-8")
    assert "\\# To nie jest nagłówek" in md
    assert "\\- to nie jest lista" in md
    assert "1\\. ani ta" in md
    assert "\\> ani cytat" in md
    assert "2\\*3\\*4" in md
    # Plik TXT nie zna składni Markdown, więc zachowuje tekst bez zmian.
    assert (tmp_path / "notatka.txt").read_text(encoding="utf-8") == (
        _DOKUMENT_Z_PODEJRZANA_SKLADNIA.tekst + "\n"
    )


def test_zrodlo_ze_struktura_zachowuje_markdown_w_md_i_przepisuje_txt(tmp_path: Path) -> None:
    dokument = DokumentZnormalizowany(
        identyfikator_zrodla="plik_tekstowy-3",
        tekst="# Tytuł\n\nAkapit.\n\n- jeden\n- dwa",
        liczba_slow=7,
        liczba_znakow=30,
    )

    zapisz_wyniki(
        tmp_path,
        "notatka",
        "plik_tekstowy-3",
        dokument,
        formaty_wlaczone=("md", "txt"),
        tekst_txt="Tytuł\n\nAkapit.\n\n- jeden\n- dwa",
    )

    assert (tmp_path / "notatka.md").read_text(encoding="utf-8").startswith("# Tytuł\n")
    assert (tmp_path / "notatka.txt").read_text(encoding="utf-8").startswith("Tytuł\n")


def test_opis_pliku_zawiera_zgodne_liczniki_i_sume_kontrolna(tmp_path: Path) -> None:
    (wynik,) = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT)

    dane = (tmp_path / "notatka.md").read_bytes()
    assert wynik.rozmiar_bajtow == len(dane)
    assert wynik.liczba_slow == len(dane.decode("utf-8").split())
    assert wynik.identyfikatory_zrodel == ["plik_tekstowy-1"]
    assert len(wynik.checksum) == 64


def test_liczba_slow_pliku_md_nie_zalezy_od_znacznikow_skladni(tmp_path: Path) -> None:
    """Ten sam tekst w MD i w TXT daje tę samą liczbę słów, więc limit nie zależy od formatu."""
    wyniki = zapisz_wyniki(
        tmp_path,
        "notatka",
        "plik_tekstowy-2",
        _DOKUMENT_Z_PODEJRZANA_SKLADNIA,
        formaty_wlaczone=("md", "txt"),
    )

    slowa = {wynik.format: wynik.liczba_slow for wynik in wyniki}
    assert slowa[FormatWynikowy.MD] == slowa[FormatWynikowy.TXT]
    assert slowa[FormatWynikowy.TXT] == policz_slowa(
        (tmp_path / "notatka.txt").read_text(encoding="utf-8")
    )


def test_liczba_znakow_pliku_jest_wieksza_o_koncowy_znak_nowej_linii(tmp_path: Path) -> None:
    """Dwie miary liczą co innego, dlatego noszą różne nazwy.

    Liczba znaków źródła liczy sam tekst dokumentu i służy do sprawdzania limitu
    notatnika. Liczba znaków pliku liczy jego zawartość, więc obejmuje też znak
    nowej linii dopisywany na końcu każdego pliku wynikowego.
    """
    (wynik,) = zapisz_wyniki(tmp_path, "notatka", "plik_tekstowy-1", _DOKUMENT)

    tresc = (tmp_path / "notatka.md").read_text(encoding="utf-8")
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


def test_zapisz_plik_pakietu_pisze_md_i_liczy_slowa_bez_skladni(tmp_path: Path) -> None:
    tresc = "# Grupa\n\n## Źródło\n\n- Tytuł: A\n\nTreść."

    wynik = zapisz_plik_pakietu(
        tmp_path, "czesc", tresc, ["plik_dokument-1"], format_pliku=FormatWynikowy.MD
    )

    assert (tmp_path / "czesc.md").exists()
    assert not (tmp_path / "czesc.txt").exists()
    assert wynik.format == FormatWynikowy.MD
    # Krzyżyki nagłówków nie są słowami: Grupa, Źródło, myślnik listy, Tytuł:, A, Treść.
    assert wynik.liczba_slow == 6
    assert len(tresc.split()) == 8


def test_domyslny_zapis_pakietu_to_txt_i_nie_tworzy_pliku_md(tmp_path: Path) -> None:
    zapisz_plik_pakietu(tmp_path, "czesc", "Tytuł: A\nCzęść: 1 z 2\n\nTreść.", ["plik_dokument-1"])

    assert (tmp_path / "czesc.txt").exists()
    assert not (tmp_path / "czesc.md").exists()
