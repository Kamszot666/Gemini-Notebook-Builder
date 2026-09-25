"""Testy zgodności checkpointu z plikami wynikowymi i przepakowania grup."""

from __future__ import annotations

from pathlib import Path

from gnb.persistence.checkpoint import Checkpoint, StanWyniku, StanZrodla, ZastapionyPlikGrupy
from gnb.persistence.pliki_wynikowe import (
    NOWA_NAZWA_BRAK,
    czlonkowie_grupy,
    domknij_zastapione_pliki,
    pozostale_pliki_zrodla,
    usun_plik_wynikowy,
    usun_pliki_zrodla,
    wycofaj_grupe,
    znajdz_brakujace_pliki,
)
from gnb.persistence.projekt import UkladProjektu, ustal_uklad


def _uklad(tmp_path: Path) -> UkladProjektu:
    uklad = ustal_uklad(tmp_path / "wyniki", "Projekt")
    uklad.pliki_wynikowe.mkdir(parents=True)
    return uklad


def _wynik(sciezka: str, format_pliku: str = "txt", zrodla: tuple[str, ...] = ()) -> StanWyniku:
    return StanWyniku(
        sciezka_wzgledna=sciezka,
        format=format_pliku,
        liczba_slow=5,
        liczba_znakow_pliku=30,
        rozmiar_bajtow=31,
        checksum="c" * 64,
        identyfikatory_zrodel=list(zrodla),
    )


def _stan(
    identyfikator: str,
    *,
    status: str = "spakowane",
    grupa: str | None = None,
    wyniki: list[StanWyniku] | None = None,
    typ: str = "tekst_wklejony",
) -> StanZrodla:
    return StanZrodla(
        identyfikator=identyfikator,
        typ=typ,
        pochodzenie=f"pochodzenie {identyfikator}",
        checksum="a" * 64,
        format_zrodla="txt",
        status=status,
        wyniki=wyniki or [],
        grupa_pakowania=grupa,
    )


def _checkpoint(uklad: UkladProjektu, *stany: StanZrodla) -> Checkpoint:
    return Checkpoint(
        wersja_schematu=4,
        identyfikator_projektu=uklad.identyfikator_projektu,
        nazwa_projektu=uklad.nazwa_projektu,
        katalog_projektu=str(uklad.katalog_projektu),
        konfiguracja={},
        czas_ostatniej_zmiany="2026-09-25T10:00:00+00:00",
        zrodla={stan.identyfikator: stan for stan in stany},
    )


def _utworz(uklad: UkladProjektu, sciezka: str) -> Path:
    plik = uklad.katalog_projektu / sciezka
    plik.parent.mkdir(parents=True, exist_ok=True)
    plik.write_text("treść", encoding="utf-8")
    return plik


def test_znajdz_brakujace_pliki_zwraca_plik_grupy_raz_ze_wszystkimi_zrodlami(
    tmp_path: Path,
) -> None:
    uklad = _uklad(tmp_path)
    wspolny = _wynik("pliki_wynikowe/grupa.txt", zrodla=("a", "b"))
    checkpoint = _checkpoint(
        uklad,
        _stan("a", grupa="G", wyniki=[wspolny]),
        _stan("b", grupa="G", wyniki=[wspolny]),
    )

    brakujace = znajdz_brakujace_pliki(uklad, checkpoint)

    assert len(brakujace) == 1
    assert brakujace[0].nazwa == "grupa.txt"
    assert brakujace[0].identyfikatory_zrodel == ("a", "b")
    assert brakujace[0].czy_zajmuje_slot


def test_znajdz_brakujace_pliki_pomija_istniejace_i_zrodla_niespakowane(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    _utworz(uklad, "pliki_wynikowe/jest.txt")
    checkpoint = _checkpoint(
        uklad,
        _stan("a", wyniki=[_wynik("pliki_wynikowe/jest.txt")]),
        _stan("b", status="pominiete", wyniki=[_wynik("pliki_wynikowe/nie_ma.txt")]),
    )

    assert znajdz_brakujace_pliki(uklad, checkpoint) == []


def test_brak_pliku_md_nie_zajmuje_slotu(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    checkpoint = _checkpoint(uklad, _stan("a", wyniki=[_wynik("pliki_wynikowe/a.md", "md")]))

    (brak,) = znajdz_brakujace_pliki(uklad, checkpoint)

    assert not brak.czy_zajmuje_slot


def test_usun_plik_wynikowy_nie_wychodzi_poza_katalog_projektu(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    poza = tmp_path / "poza.txt"
    poza.write_text("nie ruszaj", encoding="utf-8")

    assert not usun_plik_wynikowy(uklad, "../../poza.txt")
    assert poza.exists()


def test_usun_plik_wynikowy_usuwa_istniejacy_i_zwraca_falsz_dla_brakujacego(
    tmp_path: Path,
) -> None:
    uklad = _uklad(tmp_path)
    plik = _utworz(uklad, "pliki_wynikowe/a.txt")

    assert usun_plik_wynikowy(uklad, "pliki_wynikowe/a.txt")
    assert not plik.exists()
    assert not usun_plik_wynikowy(uklad, "pliki_wynikowe/a.txt")


def test_wycofaj_grupe_cofa_czlonkow_i_zapisuje_stare_pliki_jako_oczekujace(
    tmp_path: Path,
) -> None:
    uklad = _uklad(tmp_path)
    wspolny = _wynik("pliki_wynikowe/grupa.txt", zrodla=("a", "b"))
    checkpoint = _checkpoint(
        uklad,
        _stan("a", grupa="G", wyniki=[wspolny]),
        _stan("b", grupa="G", wyniki=[wspolny]),
        _stan("c", grupa="Inna", wyniki=[_wynik("pliki_wynikowe/c.txt")]),
    )

    cofniete = wycofaj_grupe(checkpoint, "G")

    assert cofniete == ["a", "b"]
    for identyfikator in cofniete:
        assert checkpoint.zrodla[identyfikator].status == "znormalizowane"
        assert checkpoint.zrodla[identyfikator].wyniki == []
    assert checkpoint.zrodla["c"].status == "spakowane"
    assert checkpoint.zastapione_pliki_grup == [
        ZastapionyPlikGrupy("pliki_wynikowe/grupa.txt", "", "G")
    ]


def test_wycofaj_grupe_nie_dubluje_oczekujacego_wpisu_ani_nie_rusza_nut(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    wspolny = _wynik("pliki_wynikowe/grupa.txt", zrodla=("a",))
    checkpoint = _checkpoint(
        uklad,
        _stan("a", grupa="G", wyniki=[wspolny]),
        _stan("nuty", grupa="G", typ="plik_nuty", wyniki=[_wynik("pliki_wynikowe/n.txt")]),
    )

    wycofaj_grupe(checkpoint, "G", dodatkowe_sciezki=["pliki_wynikowe/grupa.txt"])
    wycofaj_grupe(checkpoint, "G", dodatkowe_sciezki=["pliki_wynikowe/grupa.txt"])

    assert len(checkpoint.zastapione_pliki_grup) == 1
    assert checkpoint.zrodla["nuty"].status == "spakowane"
    assert [stan.identyfikator for stan in czlonkowie_grupy(checkpoint, "G")] == []


def test_domknij_usuwa_stary_plik_i_zapisuje_nowa_nazwe(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    stary = _utworz(uklad, "pliki_wynikowe/stary.txt")
    _utworz(uklad, "pliki_wynikowe/nowy.txt")
    checkpoint = _checkpoint(
        uklad, _stan("a", grupa="G", wyniki=[_wynik("pliki_wynikowe/nowy.txt")])
    )
    checkpoint.zastapione_pliki_grup.append(
        ZastapionyPlikGrupy("pliki_wynikowe/stary.txt", "", "G")
    )

    domkniete = domknij_zastapione_pliki(uklad, checkpoint)

    assert [wpis.nowa_nazwa for wpis in domkniete] == ["nowy.txt"]
    assert not stary.exists()
    assert checkpoint.zastapione_pliki_grup[0].nowa_nazwa == "nowy.txt"
    assert domknij_zastapione_pliki(uklad, checkpoint) == []


def test_domknij_pomija_plik_nadpisany_pod_ta_sama_nazwa(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    plik = _utworz(uklad, "pliki_wynikowe/grupa.txt")
    checkpoint = _checkpoint(
        uklad, _stan("a", grupa="G", wyniki=[_wynik("pliki_wynikowe/grupa.txt")])
    )
    checkpoint.zastapione_pliki_grup.append(
        ZastapionyPlikGrupy("pliki_wynikowe/grupa.txt", "", "G")
    )

    assert domknij_zastapione_pliki(uklad, checkpoint) == []
    assert plik.exists()
    assert checkpoint.zastapione_pliki_grup == []


def test_domknij_zapisuje_brak_nowego_pliku_gdy_grupa_nie_ma_zrodel(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    stary = _utworz(uklad, "pliki_wynikowe/stary.txt")
    checkpoint = _checkpoint(uklad)
    checkpoint.zastapione_pliki_grup.append(
        ZastapionyPlikGrupy("pliki_wynikowe/stary.txt", "", "G")
    )

    (wpis,) = domknij_zastapione_pliki(uklad, checkpoint)

    assert wpis.nowa_nazwa == NOWA_NAZWA_BRAK
    assert not stary.exists()


def test_usun_pliki_zrodla_i_pozostale_pliki(tmp_path: Path) -> None:
    uklad = _uklad(tmp_path)
    plik_txt = _utworz(uklad, "pliki_wynikowe/a.txt")
    plik_md = _utworz(uklad, "pliki_wynikowe/a.md")
    stan = _stan(
        "a",
        wyniki=[_wynik("pliki_wynikowe/a.txt"), _wynik("pliki_wynikowe/a.md", "md")],
    )

    assert pozostale_pliki_zrodla(uklad, stan, ["pliki_wynikowe/a.txt"]) == ["a.md"]
    assert usun_pliki_zrodla(uklad, stan) == ["a.txt", "a.md"]
    assert not plik_txt.exists()
    assert not plik_md.exists()
