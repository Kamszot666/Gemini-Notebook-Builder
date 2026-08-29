"""Testy orkiestratora deduplikacji: etapy, progi, determinizm."""

from __future__ import annotations

from gnb.core.stale import WynikDeduplikacji
from gnb.deduplication import UstawieniaDeduplikacji, ZrodloDoDeduplikacji, deduplikuj

_AKAPIT = (
    "Baza wiedzy dla asystenta sztucznej inteligencji jest tym lepsza, im mniej "
    "zawiera powtórzeń oraz im dokładniej wiadomo, skąd pochodzi każdy fragment. "
    "Najczęstszym błędem jest wrzucanie do jednego zbioru wszystkiego, co wpadnie "
    "w ręce, bez sprawdzenia, czy te same treści nie występują już gdzie indziej. "
)
_DLUGI = _AKAPIT * 4


def _zrodlo(identyfikator: str, tekst: str) -> ZrodloDoDeduplikacji:
    return ZrodloDoDeduplikacji(
        identyfikator=identyfikator, tekst=tekst, liczba_slow=len(tekst.split())
    )


def test_identyczny_tekst_jest_pewnym_duplikatem_wykrytym_hashem() -> None:
    wynik = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("b", _DLUGI)])

    assert wynik.identyfikatory_duplikatow == frozenset({"b"})
    assert wynik.identyfikatory_do_przegladu == frozenset()
    (decyzja,) = wynik.decyzje
    assert decyzja.identyfikator_zrodla_glownego == "a"
    assert decyzja.identyfikator_duplikatu == "b"
    assert decyzja.metoda == "hash treści"
    assert decyzja.decyzja is WynikDeduplikacji.DUPLIKAT
    assert decyzja.zachowane_fragmenty_unikalne == []


def test_roznica_wylacznie_kosmetyczna_jest_pewnym_duplikatem() -> None:
    inny_zapis = _DLUGI.replace(", ", " ,  ").upper()
    wynik = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("b", inny_zapis)])

    assert wynik.identyfikatory_duplikatow == frozenset({"b"})
    (decyzja,) = wynik.decyzje
    assert decyzja.metoda == "porównanie kosmetyczne"


def test_przedruk_z_jednym_zmienionym_zdaniem_jest_pewnym_duplikatem_simhashem() -> None:
    # Przedruk artykułu: jedno przeredagowane zdanie i jeden dopisany akapit
    # unikalny, reszta treści bez zmian. Odpowiada opisowi danych testowych
    # artykul_oryginal.html i artykul_przedruk.html.
    przedruk = _DLUGI.replace(
        "im dokładniej wiadomo, skąd pochodzi każdy fragment.",
        "im pewniej można wskazać źródło każdego fragmentu.",
        1,
    ) + (
        "Ten akapit występuje wyłącznie w przedruku i nie może zniknąć podczas "
        "porównywania obu wersji artykułu ze sobą."
    )
    wynik = deduplikuj([_zrodlo("oryginal", _DLUGI), _zrodlo("przedruk", przedruk)])

    assert wynik.identyfikatory_duplikatow == frozenset({"przedruk"})
    (decyzja,) = wynik.decyzje
    assert decyzja.metoda == "SimHash"
    assert decyzja.wynik_podobienstwa >= 0.9


def test_srednie_podobienstwo_zostawia_oba_zrodla_do_rozstrzygniecia() -> None:
    ustawienia = UstawieniaDeduplikacji(prog_duplikatu=0.99, prog_do_przegladu=0.5)
    lekko_inny = _DLUGI.replace("asystenta sztucznej inteligencji", "asystenta")
    wynik = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("b", lekko_inny)], ustawienia)

    assert wynik.identyfikatory_duplikatow == frozenset()
    assert wynik.identyfikatory_do_przegladu == frozenset({"b"})
    (decyzja,) = wynik.decyzje
    assert decyzja.decyzja is WynikDeduplikacji.WYMAGA_DECYZJI_UZYTKOWNIKA


def test_rozne_teksty_nie_daja_zadnej_decyzji() -> None:
    inny = (
        "Wczoraj wieczorem padał deszcz, a rano nad rzeką unosiła się gęsta mgła, "
        "przez którą ledwie było widać drugi brzeg oraz rosnące tam stare wierzby. "
    ) * 4
    wynik = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("b", inny)])

    assert wynik.decyzje == ()
    assert wynik.identyfikatory_duplikatow == frozenset()
    assert wynik.identyfikatory_do_przegladu == frozenset()


def test_reprezentantem_grupy_jest_zrodlo_o_najmniejszym_identyfikatorze() -> None:
    """Kolejność podania nie może wpływać na to, które źródło zostaje.

    Źródła są sortowane po identyfikatorze, więc niezależnie od kolejności na
    liście duplikatem zostaje zawsze to samo źródło.
    """
    w_jedna_strone = deduplikuj([_zrodlo("z", _DLUGI), _zrodlo("a", _DLUGI)])
    w_druga_strone = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("z", _DLUGI)])

    assert w_jedna_strone.identyfikatory_duplikatow == frozenset({"z"})
    assert w_druga_strone.identyfikatory_duplikatow == frozenset({"z"})


def test_wylaczenie_etapu_hash_nie_wykrywa_identycznego_tekstu() -> None:
    """Wyłączony etap musi realnie przestać działać, inaczej test niczego nie chroni."""
    ustawienia = UstawieniaDeduplikacji(
        etap_hash=False, etap_kosmetyczny=False, etap_podobienstwa=False
    )
    wynik = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("b", _DLUGI)], ustawienia)

    assert wynik.decyzje == ()
    assert wynik.identyfikatory_duplikatow == frozenset()


def test_wylaczenie_tylko_hasza_pozostawia_wykrycie_kosmetyczne() -> None:
    ustawienia = UstawieniaDeduplikacji(etap_hash=False)
    wynik = deduplikuj([_zrodlo("a", _DLUGI), _zrodlo("b", _DLUGI)], ustawienia)

    assert wynik.identyfikatory_duplikatow == frozenset({"b"})
    (decyzja,) = wynik.decyzje
    assert decyzja.metoda == "porównanie kosmetyczne"
