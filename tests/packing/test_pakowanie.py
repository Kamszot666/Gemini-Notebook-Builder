"""Testy planowania plików wynikowych: podział źródeł dużych i łączenie małych."""

from __future__ import annotations

from gnb.packing.limity import LimityPakowania
from gnb.packing.pakowanie import (
    ZrodloDoPakowania,
    rozplanuj_grupe,
    rozplanuj_pojedyncze_zrodlo,
)

_DUZY_ROZMIAR = 10_000_000


def _slowa_planu(plany: list) -> list[str]:
    slowa: list[str] = []
    for plan in plany:
        for fragment in plan.fragmenty:
            slowa.extend(fragment.tekst.split())
    return slowa


def test_pojedyncze_zrodlo_w_limicie_daje_jeden_plik_bez_numeracji() -> None:
    plany = rozplanuj_pojedyncze_zrodlo(
        "plik_tekstowy-1", "krótka treść", LimityPakowania(100, _DUZY_ROZMIAR)
    )

    assert len(plany) == 1
    (plan,) = plany
    assert plan.czy_grupa is False
    assert plan.numer_czesci is None
    assert plan.liczba_czesci is None
    assert [f.identyfikator for f in plan.fragmenty] == ["plik_tekstowy-1"]


def test_pojedyncze_zrodlo_ponad_limit_dzieli_sie_na_ponumerowane_czesci() -> None:
    tekst = "\n\n".join(" ".join(["slowo"] * 8) for _ in range(3))
    plany = rozplanuj_pojedyncze_zrodlo(
        "plik_tekstowy-1", tekst, LimityPakowania(limit_slow=10, limit_bajtow=_DUZY_ROZMIAR)
    )

    assert [p.numer_czesci for p in plany] == [1, 2, 3]
    assert {p.liczba_czesci for p in plany} == {3}
    assert all(p.czy_grupa is False for p in plany)
    assert all(len(p.fragmenty) == 1 for p in plany)
    assert all(p.fragmenty[0].identyfikator == "plik_tekstowy-1" for p in plany)
    assert _slowa_planu(plany) == tekst.split()


def test_grupa_malych_zrodel_laczy_sie_w_jeden_plik() -> None:
    zrodla = [
        ZrodloDoPakowania("plik_tekstowy-b", "druga notatka krótka", grupa="Temat"),
        ZrodloDoPakowania("plik_tekstowy-a", "pierwsza notatka krótka", grupa="Temat"),
    ]
    plany = rozplanuj_grupe("Temat", zrodla, LimityPakowania(100, _DUZY_ROZMIAR))

    assert len(plany) == 1
    (plan,) = plany
    assert plan.czy_grupa is True
    assert plan.grupa == "Temat"
    assert plan.numer_czesci is None
    # Fragmenty są uporządkowane rosnąco po identyfikatorze, więc wynik jest
    # powtarzalny niezależnie od kolejności podania źródeł.
    assert [f.identyfikator for f in plan.fragmenty] == ["plik_tekstowy-a", "plik_tekstowy-b"]


def test_grupa_przekraczajaca_limit_dzieli_sie_na_kolejne_pliki() -> None:
    tekst_zrodla = " ".join(["wyraz"] * 8)
    zrodla = [
        ZrodloDoPakowania(f"plik_tekstowy-{litera}", tekst_zrodla, grupa="Temat")
        for litera in "abcd"
    ]
    plany = rozplanuj_grupe(
        "Temat", zrodla, LimityPakowania(limit_slow=20, limit_bajtow=_DUZY_ROZMIAR)
    )

    assert [p.numer_czesci for p in plany] == [1, 2]
    assert {p.liczba_czesci for p in plany} == {2}
    assert all(p.czy_grupa is True for p in plany)
    # Każdy plik grupy mieści co najwyżej dwa źródła po osiem słów, bo trzy
    # przekroczyłyby limit dwudziestu słów.
    assert [len(p.fragmenty) for p in plany] == [2, 2]
    assert _slowa_planu(plany) == tekst_zrodla.split() * 4


def test_grupa_z_jednym_zrodlem_ponad_limit_dzieli_je_osobno_a_reszte_laczy() -> None:
    duze = ZrodloDoPakowania(
        "plik_tekstowy-duze",
        "\n\n".join(" ".join(["duzo"] * 8) for _ in range(3)),
        grupa="Temat",
    )
    male_a = ZrodloDoPakowania("plik_tekstowy-a", "mała notatka a", grupa="Temat")
    male_b = ZrodloDoPakowania("plik_tekstowy-b", "mała notatka b", grupa="Temat")
    limity = LimityPakowania(limit_slow=10, limit_bajtow=_DUZY_ROZMIAR)

    plany = rozplanuj_grupe("Temat", [duze, male_a, male_b], limity)

    czesci_duzego = [p for p in plany if p.fragmenty[0].identyfikator == "plik_tekstowy-duze"]
    plik_grupy = [p for p in plany if p.czy_grupa]

    assert len(czesci_duzego) == 3
    assert all(p.czy_grupa is False for p in czesci_duzego)
    assert len(plik_grupy) == 1
    assert [f.identyfikator for f in plik_grupy[0].fragmenty] == [
        "plik_tekstowy-a",
        "plik_tekstowy-b",
    ]


def test_grupa_jest_powtarzalna() -> None:
    zrodla = [
        ZrodloDoPakowania("plik_tekstowy-c", "trzecia notatka", grupa="T"),
        ZrodloDoPakowania("plik_tekstowy-a", "pierwsza notatka", grupa="T"),
        ZrodloDoPakowania("plik_tekstowy-b", "druga notatka", grupa="T"),
    ]
    limity = LimityPakowania(100, _DUZY_ROZMIAR)

    prosto = rozplanuj_grupe("T", zrodla, limity)
    odwrotnie = rozplanuj_grupe("T", list(reversed(zrodla)), limity)
    assert prosto == odwrotnie
