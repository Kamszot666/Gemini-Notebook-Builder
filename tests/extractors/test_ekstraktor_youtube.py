"""Testy zamiany napisów filmu na tekst z akapitami i znacznikami czasu.

Testy nie korzystają z sieci. Napisy są przygotowane w kodzie.
"""

from __future__ import annotations

from gnb.core.stale import PoziomPewnosciStruktury
from gnb.extractors.youtube import (
    MINIMALNA_DLUGOSC_AKAPITU,
    Akapit,
    usun_atrybucje,
    zapisz_akapity,
    zbuduj_akapity,
    zbuduj_dokument,
)
from gnb.ingestion.youtube import (
    TYP_NAPISOW_AUTOMATYCZNE,
    TYP_NAPISOW_RECZNE,
    MetadaneFilmu,
    Napisy,
    SegmentNapisow,
    WynikYouTube,
)


def _segmenty(*pary: tuple[float, str]) -> tuple[SegmentNapisow, ...]:
    return tuple(SegmentNapisow(poczatek, tekst) for poczatek, tekst in pary)


def _wynik(
    segmenty: tuple[SegmentNapisow, ...],
    *,
    dlugosc_sekundy: int | None = 600,
    typ: str = TYP_NAPISOW_RECZNE,
) -> WynikYouTube:
    return WynikYouTube(
        identyfikator="iG9CE55wbtY",
        adres_kanoniczny="https://www.youtube.com/watch?v=iG9CE55wbtY",
        metadane=MetadaneFilmu(
            identyfikator="iG9CE55wbtY",
            tytul="Wykład o bazach wiedzy",
            kanal="Kanał testowy",
            dlugosc_sekundy=dlugosc_sekundy,
            data_publikacji="2026-03-01",
        ),
        napisy=Napisy(jezyk="pl", typ=typ, segmenty=segmenty, metoda="atrapa"),
    )


def _dlugie_zdanie(numer: int) -> str:
    return (
        f"Zdanie numer {numer} opisuje kolejny fragment wykładu i jest na tyle długie, "
        "żeby akapit szybko osiągnął wymaganą długość minimalną."
    )


def test_segmenty_sa_sklejane_w_zdania() -> None:
    akapity = zbuduj_akapity(
        _segmenty((0.0, "Pierwsza część zdania"), (2.0, "i jego dokończenie."))
    )

    assert len(akapity) == 1
    assert akapity[0].tekst == "Pierwsza część zdania i jego dokończenie."


def test_puste_segmenty_sa_pomijane() -> None:
    akapity = zbuduj_akapity(
        _segmenty((0.0, "Zdanie pierwsze."), (1.0, "   "), (2.0, ""), (3.0, "Zdanie drugie."))
    )

    assert akapity[0].tekst == "Zdanie pierwsze. Zdanie drugie."


def test_powtorzenia_z_napisow_automatycznych_sa_usuwane() -> None:
    akapity = zbuduj_akapity(
        _segmenty(
            (0.0, "baza wiedzy jest tym lepsza"),
            (1.5, "baza wiedzy jest tym lepsza im mniej"),
            (3.0, "im mniej zawiera powtórzeń"),
        )
    )

    assert akapity[0].tekst == "baza wiedzy jest tym lepsza im mniej zawiera powtórzeń"


def test_powtorzony_identyczny_segment_znika() -> None:
    akapity = zbuduj_akapity(
        _segmenty((0.0, "To samo zdanie."), (2.0, "To samo zdanie."), (4.0, "Nowe zdanie."))
    )

    assert akapity[0].tekst == "To samo zdanie. Nowe zdanie."


def test_oznaczenia_dzwiekow_i_znaczniki_sa_usuwane() -> None:
    akapity = zbuduj_akapity(
        _segmenty(
            (0.0, "[muzyka]"),
            (1.0, "<c.colorE5E5E5>Właściwa</c> treść wykładu."),
            (2.0, "(śmiech)"),
            (3.0, "♪♪"),
        )
    )

    assert len(akapity) == 1
    assert akapity[0].tekst == "Właściwa treść wykładu."


def test_napisy_bez_mowy_daja_pusty_wynik() -> None:
    assert zbuduj_akapity(_segmenty((0.0, "[muzyka]"), (5.0, "♪"), (9.0, "(oklaski)"))) == []


def test_akapit_konczy_sie_na_granicy_zdania_po_osiagnieciu_dlugosci() -> None:
    segmenty = _segmenty(*[(float(numer * 5), _dlugie_zdanie(numer)) for numer in range(1, 5)])

    akapity = zbuduj_akapity(segmenty)

    assert len(akapity) >= 2
    for akapit in akapity[:-1]:
        assert akapit.tekst.endswith(".")
        assert len(akapit.tekst) >= MINIMALNA_DLUGOSC_AKAPITU


def test_akapit_zaczyna_sie_od_momentu_pierwszego_segmentu() -> None:
    segmenty = _segmenty(*[(float(numer * 5), _dlugie_zdanie(numer)) for numer in range(1, 5)])

    akapity = zbuduj_akapity(segmenty)

    assert akapity[0].poczatek_sekundy == 5.0
    assert akapity[1].poczatek_sekundy > akapity[0].poczatek_sekundy


def test_domyslnie_tekst_nie_zawiera_znacznikow_czasu() -> None:
    dokument = zbuduj_dokument(_wynik(_segmenty((12.0, "Pierwsze zdanie wykładu."))))

    assert dokument.tekst == "Pierwsze zdanie wykładu."
    assert "[" not in dokument.tekst


def test_wlaczone_znaczniki_dodaja_znacznik_na_poczatku_akapitu() -> None:
    dokument = zbuduj_dokument(
        _wynik(_segmenty((72.0, "Pierwsze zdanie wykładu."))), znaczniki_czasu=True
    )

    assert dokument.tekst == "[01:12] Pierwsze zdanie wykładu."


def test_film_dluzszy_niz_godzina_dostaje_znacznik_z_godzinami() -> None:
    dokument = zbuduj_dokument(
        _wynik(_segmenty((3725.0, "Zdanie po godzinie.")), dlugosc_sekundy=7200),
        znaczniki_czasu=True,
    )

    assert dokument.tekst == "[1:02:05] Zdanie po godzinie."


def test_format_znacznika_jest_jednolity_w_obrebie_pliku() -> None:
    segmenty = _segmenty((5.0, _dlugie_zdanie(1)), (3700.0, _dlugie_zdanie(2)))

    tekst = zapisz_akapity(
        zbuduj_akapity(segmenty), znaczniki_czasu=True, dlugosc_filmu_sekundy=7200
    )

    for wiersz in tekst.splitlines():
        if wiersz:
            assert wiersz.count(":") >= 2, "wszystkie znaczniki mają mieć człon godzinowy"


def test_wlaczenie_znacznikow_nie_zmienia_podzialu_na_akapity() -> None:
    segmenty = _segmenty(*[(float(numer * 5), _dlugie_zdanie(numer)) for numer in range(1, 6)])
    wynik = _wynik(segmenty)

    bez = zbuduj_dokument(wynik).tekst.split("\n\n")
    ze = zbuduj_dokument(wynik, znaczniki_czasu=True).tekst.split("\n\n")

    assert len(bez) == len(ze)
    for akapit_bez, akapit_ze in zip(bez, ze, strict=True):
        assert akapit_ze.endswith(akapit_bez)


def test_dokument_ma_niski_poziom_pewnosci_wiec_nie_powstanie_wersja_md() -> None:
    dokument = zbuduj_dokument(_wynik(_segmenty((0.0, "Treść wykładu."))))

    assert dokument.poziom_pewnosci_struktury is PoziomPewnosciStruktury.NISKI
    assert dokument.bloki == []


def test_metadane_filmu_trafiaja_do_dokumentu() -> None:
    dokument = zbuduj_dokument(
        _wynik(_segmenty((0.0, "Treść wykładu.")), typ=TYP_NAPISOW_AUTOMATYCZNE)
    )

    assert dokument.tytul == "Wykład o bazach wiedzy"
    assert dokument.metadane["kanal"] == "Kanał testowy"
    assert dokument.metadane["jezyk_napisow"] == "pl"
    assert dokument.metadane["typ_napisow"] == TYP_NAPISOW_AUTOMATYCZNE
    assert dokument.metadane["dlugosc_sekundy"] == "600"
    assert dokument.metadane["adres_kanoniczny"].endswith("iG9CE55wbtY")


def test_zapis_pustej_listy_akapitow_daje_pusty_tekst() -> None:
    assert zapisz_akapity([]) == ""
    assert zapisz_akapity([], znaczniki_czasu=True) == ""


def test_akapit_bez_interpunkcji_jest_zamykany_po_dlugosci_maksymalnej() -> None:
    """Materiał bez kropek nie może zamienić się w jeden nieskończony blok."""
    segmenty = _segmenty(
        *[
            (float(numer), f"fragment numer {numer} wypowiedziany bez znaku końca zdania")
            for numer in range(1, 40)
        ]
    )

    akapity = zbuduj_akapity(segmenty)

    assert len(akapity) >= 2
    assert isinstance(akapity[0], Akapit)
    assert not any(akapit.tekst.endswith(".") for akapit in akapity)


def _tresci(segmenty: tuple[SegmentNapisow, ...]) -> list[str]:
    return [segment.tekst for segment in segmenty]


def test_stopka_tlumaczy_na_poczatku_jest_wycinana() -> None:
    segmenty = _segmenty(
        (0.0, "Tłumaczenie: Radek Tomaszewski"),
        (1.0, "Korekta: Jakub Bruszewski"),
        (2.0, "Dzień dobry. Jak się macie?"),
    )

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert _tresci(zachowane) == ["Dzień dobry. Jak się macie?"]
    assert atrybucja == "Tłumaczenie: Radek Tomaszewski Korekta: Jakub Bruszewski"


def test_stopka_tlumaczy_na_koncu_jest_wycinana() -> None:
    segmenty = _segmenty(
        (0.0, "Dzień dobry."),
        (5.0, "Na tym kończymy wykład."),
        (9.0, "Subtitles by the Amara community"),
    )

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert _tresci(zachowane) == ["Dzień dobry.", "Na tym kończymy wykład."]
    assert atrybucja == "Subtitles by the Amara community"


def test_stopka_w_obu_miejscach_jest_wycinana() -> None:
    segmenty = _segmenty(
        (0.0, "Translated by Anna Nowak"),
        (2.0, "Właściwa treść wykładu."),
        (8.0, "Reviewed by Piotr Kowalski"),
    )

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert _tresci(zachowane) == ["Właściwa treść wykładu."]
    assert atrybucja == "Translated by Anna Nowak Reviewed by Piotr Kowalski"


def test_brak_stopki_niczego_nie_usuwa() -> None:
    segmenty = _segmenty((0.0, "Dzień dobry."), (3.0, "Zaczynamy wykład."))

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert _tresci(zachowane) == ["Dzień dobry.", "Zaczynamy wykład."]
    assert atrybucja == ""


def test_slowo_tlumaczenie_w_wypowiedzi_prelegenta_zostaje() -> None:
    """Wzorce polskie wymagają dwukropka, więc zwykła wypowiedź nie jest wycinana."""
    segmenty = _segmenty(
        (0.0, "Tłumaczenie maszynowe jest dziś znacznie lepsze niż dziesięć lat temu."),
        (6.0, "Nadal jednak myli nazwy własne."),
    )

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert len(zachowane) == 2
    assert atrybucja == ""


def test_stopka_nie_jest_wycinana_z_napisow_automatycznych() -> None:
    segmenty = _segmenty((0.0, "Tłumaczenie: Radek Tomaszewski"), (2.0, "Dzień dobry."))

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_AUTOMATYCZNE)

    assert len(zachowane) == 2
    assert atrybucja == ""


def test_stopka_w_srodku_materialu_nie_jest_ruszana() -> None:
    """Skanowane są wyłącznie brzegi, więc zdanie ze środka zostaje nietknięte."""
    srodek = [(float(numer), f"Zdanie numer {numer} z wykładu.") for numer in range(1, 12)]
    srodek[5] = (6.0, "Tłumaczenie: ktoś w środku materiału")
    segmenty = _segmenty(*srodek)

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert len(zachowane) == len(segmenty)
    assert atrybucja == ""


def test_stopka_w_jednym_segmencie_z_trescia_usuwa_tylko_swoj_wiersz() -> None:
    segmenty = _segmenty((0.0, "Tłumaczenie: Anna Nowak\nDzień dobry."))

    zachowane, atrybucja = usun_atrybucje(segmenty, TYP_NAPISOW_RECZNE)

    assert _tresci(zachowane) == ["Dzień dobry."]
    assert atrybucja == "Tłumaczenie: Anna Nowak"


def test_atrybucja_trafia_do_metadanych_dokumentu() -> None:
    segmenty = _segmenty((0.0, "Tłumaczenie: Radek Tomaszewski"), (2.0, "Właściwa treść wykładu."))

    dokument = zbuduj_dokument(_wynik(segmenty))

    assert dokument.metadane["atrybucja_napisow"] == "Tłumaczenie: Radek Tomaszewski"
    assert "Tłumaczenie" not in dokument.tekst
    assert dokument.tekst == "Właściwa treść wykładu."


def test_dokument_bez_stopki_nie_ma_pola_atrybucji() -> None:
    dokument = zbuduj_dokument(_wynik(_segmenty((0.0, "Właściwa treść wykładu."))))

    assert "atrybucja_napisow" not in dokument.metadane
