"""Testy filtra elementów strony działającego na drzewie XML trafilatury.

Drzewa są budowane ręcznie z wymyślonej treści: żadna strona prawdziwego serwisu
ani nazwisko prawdziwej osoby nie trafia do repozytorium. Każdy przypadek
odpowiada elementowi strony zaobserwowanemu na prawdziwych portalach.
"""

from __future__ import annotations

from lxml import etree

from gnb.extractors.filtr_elementow_strony import WynikFiltra, przefiltruj_drzewo

_AKAPIT_1 = (
    "Rada miasta przyjęła uchwałę w sprawie nowego planu zagospodarowania terenów "
    "nad rzeką po kilkugodzinnej debacie radnych."
)
_AKAPIT_2 = (
    "Mieszkańcy dzielnicy od dawna zabiegali o zmianę przeznaczenia gruntów i teraz "
    "liczą na szybkie rozpoczęcie prac budowlanych."
)
_AKAPIT_3 = (
    "Pierwsze prace mają ruszyć wiosną, o ile pozwolą na to warunki pogodowe oraz "
    "terminy przetargów ogłoszonych przez urząd."
)
_AKAPIT_4 = (
    "Koszt inwestycji oszacowano wstępnie na kilkanaście milionów złotych, z czego "
    "część ma pochodzić z dofinansowania ze środków zewnętrznych."
)


def _drzewo(*bloki: str, autor: str = "") -> etree._Element:
    """Buduje drzewo w postaci, jaką zwraca trafilatura: korzeń `doc` z elementem `main`."""
    atrybut = f' author="{autor}"' if autor else ""
    return etree.fromstring(f"<doc{atrybut}><main>{''.join(bloki)}</main></doc>".encode())


def _p(tekst: str) -> str:
    return f"<p>{tekst}</p>"


def _teksty(drzewo: etree._Element) -> list[str]:
    glowny = drzewo.find("main")
    assert glowny is not None
    return [" ".join("".join(blok.itertext()).split()) for blok in glowny]


def _powody(wynik: WynikFiltra) -> list[str]:
    return [fragment.powod for fragment in wynik.usuniete]


def test_wiersze_reklama_znikaja_z_artykulu() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p("REKLAMA"), _p(_AKAPIT_2), _p("Reklama"), _p(_AKAPIT_3))

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2, _AKAPIT_3]
    assert [fragment.tekst for fragment in wynik.usuniete] == ["REKLAMA", "Reklama"]
    assert set(_powody(wynik)) == {"reklama"}


def test_przyciski_udostepniania_znikaja_ale_zdanie_ze_slowem_udostepnij_zostaje() -> None:
    zdanie = "Udostępnij te informacje znajomym, jeśli uważasz je za ważne dla okolicy i sąsiadów."
    drzewo = _drzewo(
        _p("Udostępnij na FacebookuUdostępnij na XUdostępnij na WhatsAppKopiuj link"),
        _p(_AKAPIT_1),
        _p(zdanie),
        _p("Udostępnij"),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, zdanie]
    assert _powody(wynik) == ["przyciski udostępniania", "przyciski udostępniania"]


def test_znacznik_wideo_znika_razem_z_tytulem_filmu_pod_nim() -> None:
    drzewo = _drzewo(
        _p(_AKAPIT_1),
        _p("WIDEO"),
        _p("Jak ugotować zupę w dwadzieścia minut. Przepis krok po kroku"),
        _p(_AKAPIT_2),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2]
    assert _powody(wynik) == ["znacznik wideo", "tytuł polecanego wideo"]


def test_wideo_nie_zabiera_dlugiego_akapitu_ktory_po_nim_nastepuje() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p("WIDEO"), _p(_AKAPIT_2 * 3))

    przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, " ".join((_AKAPIT_2 * 3).split())]


def test_podpisy_zdjec_znikaja_ale_zdanie_z_nazwa_agencji_zostaje() -> None:
    zdanie = "Informację potwierdziła we wtorek rzeczniczka PAP, powołując się na własne źródła."
    drzewo = _drzewo(
        _p("Anna Przykładowa/Agencja/NurPhoto via Getty Images / Getty Images"),
        _p(_AKAPIT_1),
        _p("Jan Wzorcowy / East News"),
        _p(_AKAPIT_2),
        _p("Źródło zdjęć: © Portal Przykładowy"),
        _p(zdanie),
        _p(_AKAPIT_3),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2, zdanie, _AKAPIT_3]
    assert _powody(wynik) == [
        "podpis zdjęcia",
        "podpis zdjęcia",
        "źródło zdjęcia, wideo albo artykułu",
    ]


def test_blok_newslettera_znika_od_naglowka_do_przycisku_zapisu() -> None:
    drzewo = _drzewo(
        _p(_AKAPIT_1),
        _p("BLISKO LUDZI"),
        _p("Newsletter portalu przykładowego, co tydzień, prosto na Twoją skrzynkę."),
        _p("Najważniejsze informacje przeplatane rozrywką."),
        _p("Zapisz mnie"),
        _p(_AKAPIT_2),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2]
    assert _powody(wynik) == ["blok newslettera"] * 3 + ["przycisk newslettera"]


def test_newsletter_bez_przycisku_zabiera_tylko_swoj_naglowek() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p("Newsletter dla czytelników"), _p(_AKAPIT_2))

    przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2]


def test_notki_o_autorze_licznik_komentarzy_i_biogram_znikaja() -> None:
    biogram = (
        "Dziennikarz od 2010 roku. Współpracował z portalami i stacjami radiowymi "
        "z regionu, specjalizuje się w sprawach miejskich i samorządowych."
    )
    drzewo = _drzewo(
        _p(_AKAPIT_1),
        _p(_AKAPIT_2),
        _p(_AKAPIT_3),
        _p(_AKAPIT_4),
        _p("Jan PrzykładowyDziennikarz portalu"),
        _p("Dziennikarz portalu"),
        _p("2139 komentarzy"),
        _p("Jan Przykładowy Reporter"),
        _p(biogram),
        autor="Jan Przykładowy; Redakcja",
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2, _AKAPIT_3, _AKAPIT_4]
    assert _powody(wynik) == [
        "notka o autorze",
        "notka o autorze",
        "licznik komentarzy",
        "notka o autorze",
        "biogram autora",
    ]


def test_krotkie_zdanie_zaczynajace_sie_od_slowa_autor_zostaje() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p("Autor zaprzecza."), _p(_AKAPIT_2))

    wynik = przefiltruj_drzewo(drzewo)

    assert wynik.usuniete == []
    assert _teksty(drzewo) == [_AKAPIT_1, "Autor zaprzecza.", _AKAPIT_2]


def test_akapit_zaczynajacy_sie_od_nazwiska_autora_ale_bedacy_wypowiedzia_zostaje() -> None:
    wypowiedz = "Jan Przykładowy: nie zgadzam się z tą uchwałą"
    drzewo = _drzewo(
        _p(_AKAPIT_1), _p(_AKAPIT_2), _p(wypowiedz), _p(_AKAPIT_3), autor="Jan Przykładowy"
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert wynik.usuniete == []
    assert wypowiedz in _teksty(drzewo)


def test_biogram_bez_poprzedzajacej_notki_o_autorze_zostaje() -> None:
    zdanie = "Dziennikarz od lat relacjonuje obrady rady miasta i opisuje spory radnych."
    drzewo = _drzewo(_p(_AKAPIT_1), _p(zdanie), _p(_AKAPIT_2))

    wynik = przefiltruj_drzewo(drzewo)

    assert wynik.usuniete == []


def test_czytaj_takze_znika_razem_z_tytulami_odnosnikow() -> None:
    drzewo = _drzewo(
        _p(_AKAPIT_1),
        _p("Czytaj także"),
        '<p><ref target="https://przyklad.example/a">Pierwszy polecany artykuł o drodze</ref></p>',
        '<p><ref target="https://przyklad.example/b">Drugi polecany artykuł o przetargu</ref></p>',
        _p(_AKAPIT_2),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2]
    assert _powody(wynik) == ["blok polecanych artykułów"] * 3
    assert list(drzewo.iter("ref")) == []


def test_seria_trzech_akapitow_z_samych_odnosnikow_znika() -> None:
    drzewo = _drzewo(
        _p(_AKAPIT_1),
        *(
            f'<p><ref target="https://przyklad.example/{n}">Polecany tekst numer {n}</ref></p>'
            for n in range(3)
        ),
        _p(_AKAPIT_2),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [_AKAPIT_1, _AKAPIT_2]
    assert set(_powody(wynik)) == {"seria odnośników"}


def test_dwa_akapity_z_samych_odnosnikow_zostaja() -> None:
    drzewo = _drzewo(
        _p(_AKAPIT_1),
        '<p><ref target="https://przyklad.example/1">skazał go na osiem lat więzienia</ref></p>',
        '<p><ref target="https://przyklad.example/2">uznał za winnego</ref></p>',
        _p(_AKAPIT_2),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert wynik.usuniete == []
    assert len(_teksty(drzewo)) == 4


def test_akapit_rozciety_reklama_jest_zlaczony() -> None:
    drzewo = _drzewo(
        _p("Rada przyjęła uchwałę po długiej debacie, a radni"),
        _p("REKLAMA"),
        _p("zagłosowali jednogłośnie za planem."),
        _p(_AKAPIT_2),
    )

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [
        "Rada przyjęła uchwałę po długiej debacie, a radni zagłosowali jednogłośnie za planem.",
        _AKAPIT_2,
    ]
    assert len(wynik.zlaczenia) == 1


def test_akapity_oddzielone_reklama_nie_sa_laczone_gdy_pierwszy_konczy_sie_kropka() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p("REKLAMA"), _p("zagłosowali jednogłośnie za planem."))

    wynik = przefiltruj_drzewo(drzewo)

    assert len(_teksty(drzewo)) == 2
    assert wynik.zlaczenia == []


def test_akapity_oddzielone_reklama_nie_sa_laczone_gdy_drugi_zaczyna_sie_wielka_litera() -> None:
    drzewo = _drzewo(_p("Rada przyjęła uchwałę po długiej debacie"), _p("REKLAMA"), _p(_AKAPIT_2))

    wynik = przefiltruj_drzewo(drzewo)

    assert len(_teksty(drzewo)) == 2
    assert wynik.zlaczenia == []


def test_zlaczenie_zachowuje_odnosnik_z_drugiego_akapitu() -> None:
    drzewo = _drzewo(
        _p("Rada przyjęła uchwałę po długiej debacie, a radni"),
        _p("REKLAMA"),
        '<p>zagłosowali za <ref target="https://przyklad.example/plan">przyjęciem planu</ref>.</p>',
    )

    przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == [
        "Rada przyjęła uchwałę po długiej debacie, a radni zagłosowali za przyjęciem planu."
    ]
    assert [ref.get("target") for ref in drzewo.iter("ref")] == ["https://przyklad.example/plan"]


def test_bezpiecznik_zostawia_tresc_gdy_filtr_usunalby_zbyt_wiele() -> None:
    drzewo = _drzewo(
        _p("Krótki tekst artykułu."),
        _p("Udostępnij na Facebooku"),
        _p("Newsletter " + "słowo " * 30),
        _p("Zapisz mnie"),
    )
    przed = _teksty(drzewo)

    wynik = przefiltruj_drzewo(drzewo)

    assert _teksty(drzewo) == przed
    assert wynik.usuniete == []
    assert wynik.zaproponowane
    assert wynik.ostrzezenie is not None
    assert "procent treści" in wynik.ostrzezenie


def test_artykul_bez_elementow_strony_zostaje_nietkniety() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p(_AKAPIT_2), _p(_AKAPIT_3))

    wynik = przefiltruj_drzewo(drzewo)

    assert not wynik.zawiera_cos_do_zapisu()
    assert len(_teksty(drzewo)) == 3


def test_zapis_tekstowy_wymienia_kazdy_usuniety_fragment_z_powodem() -> None:
    drzewo = _drzewo(_p(_AKAPIT_1), _p("REKLAMA"), _p(_AKAPIT_2))

    tekst = przefiltruj_drzewo(drzewo).jako_tekst("strona_www-abc")

    assert "strona_www-abc" in tekst
    assert "Liczba usuniętych fragmentów: 1." in tekst
    assert "1. Powód: reklama. Tekst: REKLAMA" in tekst
