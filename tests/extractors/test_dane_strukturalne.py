"""Testy odczytu metadanych z danych strukturalnych JSON-LD i ich scalania."""

from __future__ import annotations

from gnb.extractors.dane_strukturalne import (
    KLUCZ_ROZBIEZNOSCI,
    MetadaneStrukturalne,
    odczytaj_json_ld,
    scal_metadane,
)


def _strona(blok: str, *, typ: str = "application/ld+json") -> str:
    return f'<html><head><script type="{typ}">{blok}</script></head><body><p>x</p></body></html>'


def test_odczytuje_podstawowe_pola_artykulu() -> None:
    metadane = odczytaj_json_ld(
        _strona(
            """
            {
              "@type": "Article",
              "author": "Anna Kowalska",
              "datePublished": "2026-03-01T08:30:00Z",
              "dateModified": "2026-03-05",
              "publisher": {"name": "Serwis Przykład"},
              "description": "Krótki opis artykułu."
            }
            """
        )
    )

    assert metadane.autor == "Anna Kowalska"
    assert metadane.data_publikacji == "2026-03-01"
    assert metadane.data_aktualizacji == "2026-03-05"
    assert metadane.wydawca == "Serwis Przykład"
    assert metadane.opis == "Krótki opis artykułu."


def test_odczytuje_artykul_z_listy_obiektow() -> None:
    metadane = odczytaj_json_ld(
        _strona('[{"@type": "WebSite"}, {"@type": "NewsArticle", "author": "Jan Nowak"}]')
    )

    assert metadane.autor == "Jan Nowak"


def test_odczytuje_artykul_z_pola_graf() -> None:
    metadane = odczytaj_json_ld(
        _strona('{"@graph": [{"@type": "WebPage"}, {"@type": "BlogPosting", "author": "Ewa Bąk"}]}')
    )

    assert metadane.autor == "Ewa Bąk"


def test_typ_zapisany_jako_lista_jest_rozpoznawany() -> None:
    metadane = odczytaj_json_ld(_strona('{"@type": ["Article", "CreativeWork"], "author": "Ola"}'))

    assert metadane.autor == "Ola"


def test_wielu_autorow_laczy_sie_w_jeden_zapis() -> None:
    metadane = odczytaj_json_ld(
        _strona('{"@type": "Article", "author": [{"name": "Anna Nowak"}, "Jan Kowalski"]}')
    )

    assert metadane.autor == "Anna Nowak, Jan Kowalski"


def test_uszkodzony_blok_nie_zatrzymuje_odczytu_pozostalych() -> None:
    strona = (
        '<html><head><script type="application/ld+json">{zepsute</script>'
        '<script type="application/ld+json">{"@type": "Article", "author": "Ewa"}</script>'
        "</head><body>x</body></html>"
    )

    assert odczytaj_json_ld(strona).autor == "Ewa"


def test_blok_innego_typu_jest_pomijany() -> None:
    metadane = odczytaj_json_ld(
        _strona('{"@type": "Article", "author": "Ewa"}', typ="application/json")
    )

    assert metadane.czy_pusta


def test_brak_bloku_daje_wynik_pusty() -> None:
    assert odczytaj_json_ld("<html><body><p>Bez danych strukturalnych.</p></body></html>").czy_pusta


def test_typ_spoza_listy_artykulow_jest_pomijany() -> None:
    assert odczytaj_json_ld(_strona('{"@type": "Product", "author": "Ewa"}')).czy_pusta


def test_data_w_zapisie_dziennym_jest_rozpoznawana() -> None:
    assert (
        odczytaj_json_ld(
            _strona('{"@type": "Article", "datePublished": "01.03.2026"}')
        ).data_publikacji
        == "2026-03-01"
    )


def test_nierozpoznana_data_nie_trafia_do_metadanych() -> None:
    assert (
        odczytaj_json_ld(
            _strona('{"@type": "Article", "datePublished": "wczoraj", "author": "Ewa"}')
        ).data_publikacji
        is None
    )


def test_tresc_porownawcza_pochodzi_z_pola_article_body() -> None:
    metadane = odczytaj_json_ld(
        _strona('{"@type": "Article", "articleBody": "Pełna treść artykułu."}')
    )

    assert metadane.tresc_porownawcza == "Pełna treść artykułu."


def test_scalanie_przyjmuje_wartosc_obecna_tylko_w_danych_strukturalnych() -> None:
    scalone = scal_metadane({}, MetadaneStrukturalne(autor="Anna Nowak", wydawca="Serwis"))

    assert scalone["autor"] == "Anna Nowak"
    assert scalone["wydawca"] == "Serwis"
    assert KLUCZ_ROZBIEZNOSCI not in scalone


def test_scalanie_nie_zglasza_rozbieznosci_przy_zgodnych_wartosciach() -> None:
    scalone = scal_metadane(
        {"autor": "Anna Nowak", "data_publikacji": "2026-03-01"},
        MetadaneStrukturalne(autor="anna nowak", data_publikacji="2026-03-01"),
    )

    assert scalone["autor"] == "Anna Nowak"
    assert KLUCZ_ROZBIEZNOSCI not in scalone


def test_scalanie_zachowuje_obie_wartosci_przy_rozbieznosci() -> None:
    scalone = scal_metadane(
        {"autor": "Anna Nowak", "data_publikacji": "2026-03-01"},
        MetadaneStrukturalne(autor="Jan Kowalski", data_publikacji="2020-01-01"),
    )

    assert scalone["autor"] == "Anna Nowak"
    assert scalone["autor_wg_danych_strukturalnych"] == "Jan Kowalski"
    assert scalone["data_publikacji"] == "2026-03-01"
    assert scalone["data_publikacji_wg_danych_strukturalnych"] == "2020-01-01"
    assert scalone[KLUCZ_ROZBIEZNOSCI] == "autor, data_publikacji"


def test_scalanie_porownuje_daty_po_czesci_dziennej() -> None:
    scalone = scal_metadane(
        {"data_publikacji": "2026-03-01"},
        MetadaneStrukturalne(data_publikacji="2026-03-01"),
    )

    assert KLUCZ_ROZBIEZNOSCI not in scalone
