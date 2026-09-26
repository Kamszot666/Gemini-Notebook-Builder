"""Testy rozwijania archiwów ZIP: ochrona ścieżek, limity, bomba kompresji, zagnieżdżenia."""

from __future__ import annotations

import io
import random
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from gnb.ingestion.archiwum import (
    STATUS_POMINIETE,
    STATUS_ROZWINIETE,
    STATUS_WPISU_POMINIETY,
    STATUS_WPISU_PRZYJETY,
    LimityArchiwum,
    WynikRozwiniecia,
    _bezpieczna_nazwa,
    _nazwa_wpisu,
    _powod_pominiecia,
    _PrzekroczonoLimitArchiwum,
    _Stan,
    _zapisz_wpis,
    rozwin_archiwum,
)

_MOMENT = datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
_DANE = Path(__file__).resolve().parents[1] / "dane" / "formaty"


def _zip(
    wpisy: dict[str, bytes | str], sciezka: Path, *, kompresja: int = zipfile.ZIP_DEFLATED
) -> Path:
    with zipfile.ZipFile(sciezka, "w", kompresja) as archiwum:
        for nazwa, dane in wpisy.items():
            archiwum.writestr(nazwa, dane)
    return sciezka


def _rozwin(
    tmp_path: Path,
    wpisy: dict[str, bytes | str],
    *,
    limity: LimityArchiwum | None = None,
    grupa: str | None = None,
) -> WynikRozwiniecia:
    sciezka = _zip(wpisy, tmp_path / "paczka.zip")
    return rozwin_archiwum(
        sciezka, tmp_path / "wyjscie", limity or LimityArchiwum(), _MOMENT, grupa=grupa
    )


def _po_sciezce(wynik: WynikRozwiniecia) -> dict[str, tuple[str, str | None]]:
    return {wpis.sciezka: (wpis.status, wpis.komunikat) for wpis in wynik.wpisy}


def test_pliki_z_archiwum_sa_wejsciami_pod_nazwami_wlasnymi_z_pochodzeniem(tmp_path: Path) -> None:
    wynik = _rozwin(
        tmp_path,
        {
            "a.txt": "Treść pierwsza.",
            "folder/podfolder/b.md": "# Nagłówek",
            "dane.csv": "x,y\n1,2\n",
        },
    )

    assert wynik.status == STATUS_ROZWINIETE
    assert [pozycja.sciezka_w_archiwum for pozycja in wynik.pozycje] == [
        "a.txt",
        "folder/podfolder/b.md",
        "dane.csv",
    ]
    assert all(pozycja.archiwum == "paczka.zip" for pozycja in wynik.pozycje)
    assert all(pozycja.grupa is None for pozycja in wynik.pozycje)
    for pozycja in wynik.pozycje:
        sciezka = Path(pozycja.wejscie.wartosc)
        assert sciezka.is_file()
        assert sciezka.parent.parent == tmp_path / "wyjscie"
        assert "folder" not in sciezka.name
    assert {wpis.status for wpis in wynik.wpisy} == {STATUS_WPISU_PRZYJETY}
    assert all(wpis.suma_kontrolna and wpis.rozmiar_bajtow for wpis in wynik.wpisy)
    assert (Path(wynik.pozycje[0].wejscie.wartosc)).read_text(encoding="utf-8") == "Treść pierwsza."


def test_grupa_z_archiwum_jest_dziedziczona_tylko_gdy_ja_podano(tmp_path: Path) -> None:
    bez = _rozwin(tmp_path, {"a.txt": "x", "b.txt": "y"})
    z_grupa = rozwin_archiwum(
        tmp_path / "paczka.zip", tmp_path / "inne", LimityArchiwum(), _MOMENT, grupa="Moja grupa"
    )

    assert all(pozycja.grupa is None for pozycja in bez.pozycje)
    assert all(pozycja.grupa == "Moja grupa" for pozycja in z_grupa.pozycje)


DYSK = zipfile.ZipInfo("C:\\dysk.txt").filename  # zipfile zamienia ukośniki zależnie od systemu


def test_sciezki_wychodzace_sa_pomijane_i_nic_nie_powstaje_poza_katalogiem(tmp_path: Path) -> None:
    wynik = _rozwin(
        tmp_path,
        {
            "../ucieczka.txt": "zła",
            "/bezwzgledna.txt": "zła",
            DYSK: "zła",
            "a/../../wyzej.txt": "zła",
            "dobry.txt": "dobra",
        },
    )

    wpisy = _po_sciezce(wynik)
    for zla in ("../ucieczka.txt", "/bezwzgledna.txt", DYSK, "a/../../wyzej.txt"):
        assert wpisy[zla][0] == STATUS_WPISU_POMINIETY, zla
        assert "niebezpieczny" in (wpisy[zla][1] or ""), zla
    assert wpisy["dobry.txt"][0] == STATUS_WPISU_PRZYJETY
    assert len(wynik.pozycje) == 1
    # Poza katalogiem wyjściowym nie ma żadnego pliku poza samym archiwum.
    assert sorted(p.name for p in tmp_path.iterdir()) == ["paczka.zip", "wyjscie"]
    assert not (tmp_path.parent / "ucieczka.txt").exists()


def test_dowiazanie_symboliczne_jest_pomijane(tmp_path: Path) -> None:
    sciezka = tmp_path / "paczka.zip"
    with zipfile.ZipFile(sciezka, "w") as archiwum:
        dowiazanie = zipfile.ZipInfo("link.txt")
        dowiazanie.external_attr = (stat.S_IFLNK | 0o777) << 16
        archiwum.writestr(dowiazanie, "/etc/passwd")
        archiwum.writestr("dobry.txt", "ok")

    wynik = rozwin_archiwum(sciezka, tmp_path / "wyjscie", LimityArchiwum(), _MOMENT)

    wpisy = _po_sciezce(wynik)
    assert "dowiązaniem symbolicznym" in (wpisy["link.txt"][1] or "")
    assert wpisy["dobry.txt"][0] == STATUS_WPISU_PRZYJETY


def test_wpis_zaszyfrowany_hasłem_jest_pomijany_bez_prob_odczytu() -> None:
    """Biblioteka zeruje flagi przy zapisie, więc sprawdzamy powód dla gotowego wpisu."""
    zaszyfrowany = zipfile.ZipInfo("tajne.txt")
    zaszyfrowany.flag_bits |= 0x1

    assert "zaszyfrowany hasłem" in (_powod_pominiecia(zaszyfrowany, "tajne.txt") or "")
    assert _powod_pominiecia(zipfile.ZipInfo("jawne.txt"), "jawne.txt") is None


def test_nieobslugiwane_puste_i_metadane_systemu_sa_pomijane_z_powodem(tmp_path: Path) -> None:
    wynik = _rozwin(
        tmp_path,
        {
            "program.exe": b"MZ",
            "pusty.txt": "",
            "__MACOSX/._a.txt": b"x",
            ".DS_Store": b"x",
            "Thumbs.db": b"x",
            "utwor.gpx": b"x",
            "bez_rozszerzenia": b"x",
            "dobry.txt": "ok",
        },
    )

    wpisy = _po_sciezce(wynik)
    assert "Nieobsługiwany format pliku: „exe”" in (wpisy["program.exe"][1] or "")
    assert "pusty" in (wpisy["pusty.txt"][1] or "")
    assert "metadanych systemu" in (wpisy["__MACOSX/._a.txt"][1] or "")
    assert "metadanych systemu" in (wpisy[".DS_Store"][1] or "")
    assert "metadanych systemu" in (wpisy["Thumbs.db"][1] or "")
    assert "Guitar Pro" in (wpisy["utwor.gpx"][1] or "")
    assert "brak rozszerzenia" in (wpisy["bez_rozszerzenia"][1] or "")
    assert [p.sciezka_w_archiwum for p in wynik.pozycje] == ["dobry.txt"]


def test_zbyt_wiele_plikow_pomija_cale_archiwum_i_sprzata(tmp_path: Path) -> None:
    wynik = _rozwin(
        tmp_path,
        {f"{numer}.txt": f"treść {numer}" for numer in range(6)},
        limity=LimityArchiwum(maksymalna_liczba_plikow=5),
    )

    assert wynik.status == STATUS_POMINIETE
    assert "więcej niż 5 plików" in (wynik.komunikat or "")
    assert wynik.pozycje == []
    assert not (tmp_path / "wyjscie").exists() or not any((tmp_path / "wyjscie").rglob("*.txt"))


def test_zbyt_duzy_rozmiar_po_rozpakowaniu_pomija_cale_archiwum(tmp_path: Path) -> None:
    losowe = random.Random(1).randbytes(1024 * 1024)  # słabo się kompresuje
    wynik = _rozwin(
        tmp_path,
        {"a.txt": losowe, "b.txt": losowe},
        limity=LimityArchiwum(maksymalny_rozmiar_bajtow=1_500_000),
    )

    assert wynik.status == STATUS_POMINIETE
    assert "przekracza limit" in (wynik.komunikat or "")
    assert wynik.pozycje == []


def test_bomba_kompresji_jest_wykrywana_po_stosunku_kompresji(tmp_path: Path) -> None:
    wynik = _rozwin(tmp_path, {"zera.txt": b"\x00" * 5_000_000, "dobry.txt": "ok"})

    assert wynik.status == STATUS_POMINIETE
    assert "bomby kompresji" in (wynik.komunikat or "")
    assert wynik.pozycje == []


def test_faktyczny_rozmiar_odczytu_tez_jest_limitowany(tmp_path: Path) -> None:
    """Limit liczy bajty faktycznie odczytane, nie tylko rozmiar zadeklarowany w archiwum.

    Biblioteka zip sama odrzuca wpis z nagłówkiem kłamiącym o rozmiarze, więc ten
    licznik jest drugą warstwą obrony. Test sprawdza go bezpośrednio: licznik ma już
    prawie pełny limit, a wpis go przekracza.
    """
    losowe = random.Random(2).randbytes(4096)
    sciezka = _zip({"a.txt": losowe}, tmp_path / "paczka.zip")
    (tmp_path / "w").mkdir()
    stan = _Stan(
        "paczka.zip",
        tmp_path / "w",
        LimityArchiwum(maksymalny_rozmiar_bajtow=10_000),
        _MOMENT,
        None,
    )
    stan.rozmiar_odczytany = 9_000

    with zipfile.ZipFile(sciezka) as archiwum:
        with pytest.raises(_PrzekroczonoLimitArchiwum, match="Faktyczny rozmiar"):
            _zapisz_wpis(archiwum, archiwum.getinfo("a.txt"), tmp_path / "w" / "a", stan)


def test_archiwum_zagniezdzone_jest_rozwijane_do_ograniczonej_glebokosci(tmp_path: Path) -> None:
    wewnetrzne = io.BytesIO()
    _zip({"gleboko.txt": "najgłębiej"}, tmp_path / "trzecie.zip")
    with zipfile.ZipFile(wewnetrzne, "w") as archiwum:
        archiwum.writestr("srodek.txt", "w środku")
        archiwum.write(tmp_path / "trzecie.zip", "trzecie.zip")
    wynik = _rozwin(tmp_path, {"drugie.zip": wewnetrzne.getvalue(), "wierzch.txt": "na wierzchu"})

    assert wynik.status == STATUS_ROZWINIETE
    sciezki = [pozycja.sciezka_w_archiwum for pozycja in wynik.pozycje]
    assert "drugie.zip » srodek.txt" in sciezki
    assert "wierzch.txt" in sciezki
    assert all(pozycja.archiwum == "paczka.zip" for pozycja in wynik.pozycje)
    wpisy = _po_sciezce(wynik)
    assert wpisy["drugie.zip » trzecie.zip"][0] == STATUS_WPISU_POMINIETY
    assert "głębiej niż 2 poziomy" in (wpisy["drugie.zip » trzecie.zip"][1] or "")
    assert not any("gleboko" in (s or "") for s in sciezki)


def test_uszkodzone_i_niebedace_archiwum_jest_pomijane_w_calosci(tmp_path: Path) -> None:
    plik = tmp_path / "zepsute.zip"
    plik.write_bytes(b"to nie jest archiwum")

    wynik = rozwin_archiwum(plik, tmp_path / "wyjscie", LimityArchiwum(), _MOMENT)

    assert wynik.status == STATUS_POMINIETE
    assert "nie jest poprawnym archiwum ZIP" in (wynik.komunikat or "")


def test_archiwum_bez_obslugiwanych_plikow_daje_ostrzezenie(tmp_path: Path) -> None:
    wynik = _rozwin(tmp_path, {"a.exe": b"MZ"})

    assert wynik.status == STATUS_ROZWINIETE
    assert wynik.pozycje == []
    assert any("żaden nie miał obsługiwanego formatu" in o for o in wynik.ostrzezenia)


def test_docx_z_archiwum_zachowuje_bajty_bez_zmian(tmp_path: Path) -> None:
    dane = (_DANE / "dokument.docx").read_bytes()

    wynik = _rozwin(tmp_path, {"raporty/dokument.docx": dane})

    (pozycja,) = wynik.pozycje
    assert Path(pozycja.wejscie.wartosc).read_bytes() == dane
    assert pozycja.format_zrodla == "docx"


def test_ponowne_rozwiniecie_tego_samego_archiwum_trafia_w_to_samo_miejsce(tmp_path: Path) -> None:
    pierwsze = _rozwin(tmp_path, {"a.txt": "x"})
    drugie = rozwin_archiwum(
        tmp_path / "paczka.zip", tmp_path / "wyjscie", LimityArchiwum(), _MOMENT
    )

    assert pierwsze.pozycje[0].wejscie.wartosc == drugie.pozycje[0].wejscie.wartosc


def test_nazwy_z_archiwum_bez_znacznika_utf8_sa_poprawiane_ze_strony_cp852() -> None:
    zepsuta = "Zażółć.txt".encode("cp852").decode("cp437")
    informacja = zipfile.ZipInfo(zepsuta)
    informacja.flag_bits = 0

    assert _nazwa_wpisu(informacja) == "Zażółć.txt"

    z_utf8 = zipfile.ZipInfo("Zażółć.txt")
    z_utf8.flag_bits = 0x800
    assert _nazwa_wpisu(z_utf8) == "Zażółć.txt"


def test_bezpieczna_nazwa_usuwa_katalogi_znaki_specjalne_i_skraca() -> None:
    assert _bezpieczna_nazwa("a/b\\c:d*e?.txt") == "c_d_e_.txt"
    assert _bezpieczna_nazwa("...") == "plik"
    assert _bezpieczna_nazwa("CON") == "CON"  # nazwę zarezerwowaną chroni numer na początku
    długa = "x" * 200 + ".pdf"
    wynik = _bezpieczna_nazwa(długa)
    assert len(wynik) == 80 and wynik.endswith(".pdf")
