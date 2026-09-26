"""Widoki źródeł projektu: wykaz z działaniami, brakujące pliki i potwierdzenie usunięcia.

Wykaz źródeł pokazuje na stronie projektu to, na co użytkownik może zadziałać
ręcznie: oznaczyć źródło z materiałów do sprawdzenia jako zweryfikowane, zastąpić
jego treść plikiem zapisanym ręcznie albo usunąć je z projektu. Każde działanie
jest osobnym formularzem z ochroną przed CSRF. Przyciski nie noszą nazwy
źródła w etykiecie, bo czytnik ekranu odczytywałby ją w całości przy każdym
działaniu: nazwa jest w nagłówku źródła, a przycisk jest z nią powiązany przez
``aria-describedby``, więc czytnik podaje ją jako opis.

Sekcja brakujących plików wynikowych tylko pokazuje rozbieżność między
checkpointem a dyskiem. Niczego nie zmienia: status źródeł zmienia dopiero
początek następnego przebiegu przetwarzania.

Moduł zależy od ``gnb.ui.widoki``, a nie odwrotnie: gotowy fragment HTML jest
przekazywany do strony projektu jako napis, żeby oba moduły się nie importowały
wzajemnie.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import quote

from gnb.ui.html import escapuj
from gnb.ui.widoki import (
    _SKRYPT_FOKUS_BLEDOW,
    BladPola,
    _dokument,
    _lista_bledow,
    _opis_bledu_pola,
    _pole_csrf,
    sciezka_projektu,
)

TEKST_POTWIERDZENIA_USUNIECIA = "USUŃ"

_OPISY_STATUSOW = {
    "oczekuje": "oczekuje na przetworzenie",
    "pobrane": "pobrane",
    "wyekstrahowane": "wyekstrahowane",
    "znormalizowane": "znormalizowane, czeka na zapis plików wynikowych",
    "duplikat": "duplikat innego źródła, bez własnego pliku",
    "spakowane": "spakowane, treść jest w plikach wynikowych",
    "pominiete": "pominięte, bez treści w plikach wynikowych",
    "blad": "zakończone błędem",
}


@dataclass(frozen=True, slots=True)
class ZrodloDoWidoku:
    """Źródło projektu w postaci potrzebnej do pokazania go i jego działań na stronie."""

    identyfikator: str
    pochodzenie: str
    status: str
    grupa: str | None = None
    pliki_wynikowe: tuple[str, ...] = ()
    komunikat: str | None = None
    powody_do_sprawdzenia: tuple[str, ...] = ()
    czy_material_do_sprawdzenia: bool = False
    zweryfikowane_recznie: bool = False
    tresc_zastapiona_plikiem: str | None = None
    czy_mozna_zastapic_tresc: bool = False


@dataclass(frozen=True, slots=True)
class BrakujacyPlikDoWidoku:
    """Plik wynikowy znany checkpointowi, którego nie ma na dysku, wraz ze źródłami."""

    nazwa: str
    pochodzenie_zrodel: tuple[str, ...]
    czy_zajmuje_slot: bool


def czy_potwierdzenie_poprawne(wpisany_tekst: str) -> bool:
    """Sprawdza, czy użytkownik wpisał słowo potwierdzenia usunięcia.

    Wielkość liter nie ma znaczenia, a brak polskiego znaku w słowie „usuń” jest
    tolerowany: potwierdzenie ma chronić przed przypadkowym kliknięciem, a nie
    sprawdzać pisownię.
    """
    znormalizowany = wpisany_tekst.strip().casefold()
    return znormalizowany in (TEKST_POTWIERDZENIA_USUNIECIA.casefold(), "usun")


def sekcje_zrodel(
    nazwa_projektu: str,
    zrodla: Sequence[ZrodloDoWidoku],
    brakujace_pliki: Sequence[BrakujacyPlikDoWidoku],
    token_csrf: str,
) -> str:
    """Buduje sekcje „Pliki wynikowe brakujące na dysku” i „Źródła projektu”.

    Zwraca pusty napis, gdy projekt nie ma jeszcze żadnych źródeł, żeby nie
    pokazywać pustego nagłówka.
    """
    czesci = []
    if brakujace_pliki:
        czesci.append(_sekcja_brakujacych_plikow(brakujace_pliki))
    if zrodla:
        czesci.append(_sekcja_zrodel(sciezka_projektu(nazwa_projektu), zrodla, token_csrf))
    return "\n".join(czesci)


def strona_potwierdzenia_usuniecia(
    *,
    nazwa_projektu: str,
    zrodlo: ZrodloDoWidoku,
    token_csrf: str,
    bledy: list[BladPola] | None = None,
) -> str:
    """Strona z pytaniem, czy na pewno usunąć źródło, z potwierdzeniem wpisanym tekstem."""
    bledy = bledy or []
    sciezka = sciezka_projektu(nazwa_projektu)
    adres_akcji = f"{sciezka}/zrodlo/{_id_w_adresie(zrodlo.identyfikator)}/usun"
    atrybuty, blad = _opis_bledu_pola(bledy, "potwierdzenie")
    opis_grupy = (
        f"<li>To źródło należy do grupy „{escapuj(zrodlo.grupa)}”. Pozostałe źródła "
        "tej grupy zostaną spakowane od nowa, a stary plik grupy zostanie zastąpiony "
        "nowym.</li>"
        if zrodlo.grupa
        else ""
    )
    slowo_potwierdzenia = escapuj(TEKST_POTWIERDZENIA_USUNIECIA)
    tresc = f"""<h1>Usunąć źródło z projektu?</h1>
<form class="blok" method="post" action="{escapuj(adres_akcji)}">
{_pole_csrf(token_csrf)}
{_lista_bledow(bledy)}
<h2>Źródło do usunięcia</h2>
<p>{escapuj(zrodlo.pochodzenie)}</p>
<p>Identyfikator źródła: {escapuj(zrodlo.identyfikator)}</p>
<h2>Co się stanie</h2>
<ul>
<li>Źródło zniknie z projektu, z manifestu i z raportu, a jego pliki wynikowe zostaną
usunięte z dysku.</li>
<li>Zachowane oryginały i wysłane pliki zostaną na dysku, w materiałach źródłowych
projektu.</li>
<li>Wznowienie projektu nie przywróci tego źródła. Możesz je dodać ponownie jako
zupełnie nowe źródło.</li>
{opis_grupy}
</ul>
<label for="potwierdzenie">Aby potwierdzić, wpisz słowo {slowo_potwierdzenia}</label>
<input type="text" id="potwierdzenie" name="potwierdzenie" autocomplete="off"{atrybuty}>
{blad}
<button type="submit">Usuń źródło z projektu</button>
</form>
<p><a href="{escapuj(sciezka)}">Anuluj i wróć do projektu</a></p>"""
    return _dokument(
        f"Usunięcie źródła z projektu {nazwa_projektu}",
        tresc,
        skrypt=_SKRYPT_FOKUS_BLEDOW if bledy else "",
    )


def _id_w_adresie(identyfikator: str) -> str:
    return quote(identyfikator, safe="")


def _id_elementu(identyfikator: str) -> str:
    """Zamienia identyfikator źródła na wartość bezpieczną w atrybucie ``id``."""
    return "".join(znak if znak.isalnum() or znak in "-_" else "_" for znak in identyfikator)


def _sekcja_brakujacych_plikow(brakujace: Sequence[BrakujacyPlikDoWidoku]) -> str:
    pozycje = []
    for brak in brakujace:
        zrodla = "; ".join(escapuj(pochodzenie) for pochodzenie in brak.pochodzenie_zrodel)
        skutek = (
            "Źródła tego pliku zostaną pominięte na początku następnego przebiegu."
            if brak.czy_zajmuje_slot
            else "To wersja MD, więc źródła zachowają status, bo ich treść jest w pliku TXT."
        )
        pozycje.append(f"<li>{escapuj(brak.nazwa)}. Źródła: {zrodla}. {escapuj(skutek)}</li>")
    return (
        '<div class="blok" id="pliki-brakujace">\n'
        "<h2>Pliki wynikowe brakujące na dysku</h2>\n"
        "<p>Tych plików wynikowych nie ma już w katalogu projektu, chociaż zapisano je "
        "w checkpoincie. Ta strona tylko pokazuje rozbieżność i niczego nie zmienia. "
        "Status źródeł zmieni się dopiero na początku następnego przebiegu "
        "przetwarzania; dodanie tego samego adresu albo pliku przetworzy źródło "
        "od nowa.</p>\n"
        f"<ul>\n{''.join(pozycje)}\n</ul>\n</div>"
    )


def _sekcja_zrodel(sciezka: str, zrodla: Sequence[ZrodloDoWidoku], token_csrf: str) -> str:
    pozycje = "\n".join(_pozycja_zrodla(sciezka, zrodlo, token_csrf) for zrodlo in zrodla)
    return (
        '<div class="blok" id="zrodla-projektu">\n'
        "<h2>Źródła projektu</h2>\n"
        f"<p>Liczba źródeł: {len(zrodla)}.</p>\n"
        f'<ul class="zrodla">\n{pozycje}\n</ul>\n</div>'
    )


def _pozycja_zrodla(sciezka: str, zrodlo: ZrodloDoWidoku, token_csrf: str) -> str:
    id_el = _id_elementu(zrodlo.identyfikator)
    id_opisu = f"zrodlo-{id_el}-opis"
    adres_zrodla = f"{sciezka}/zrodlo/{_id_w_adresie(zrodlo.identyfikator)}"
    opis_statusu = _OPISY_STATUSOW.get(zrodlo.status, zrodlo.status)

    szczegoly = [f"<li>Status: {escapuj(opis_statusu)}.</li>"]
    if zrodlo.grupa:
        szczegoly.append(f"<li>Grupa tematyczna: {escapuj(zrodlo.grupa)}.</li>")
    if zrodlo.pliki_wynikowe:
        szczegoly.append(
            "<li>Pliki wynikowe: "
            + ", ".join(escapuj(nazwa) for nazwa in zrodlo.pliki_wynikowe)
            + ".</li>"
        )
    if zrodlo.komunikat:
        szczegoly.append(f"<li>Komunikat: {escapuj(zrodlo.komunikat)}</li>")
    if zrodlo.tresc_zastapiona_plikiem:
        szczegoly.append(
            "<li>Treść zastąpiona plikiem zapisanym ręcznie: "
            f"{escapuj(zrodlo.tresc_zastapiona_plikiem)}.</li>"
        )
    if zrodlo.zweryfikowane_recznie:
        szczegoly.append("<li>Zweryfikowane ręcznie przez użytkownika.</li>")
    elif zrodlo.czy_material_do_sprawdzenia:
        powody = "".join(f"<li>{escapuj(powod)}</li>" for powod in zrodlo.powody_do_sprawdzenia)
        szczegoly.append(
            "<li>Materiał do sprawdzenia" + (f":\n<ul>{powody}</ul>" if powody else ".") + "</li>"
        )

    dzialania = []
    if zrodlo.czy_material_do_sprawdzenia and not zrodlo.zweryfikowane_recznie:
        dzialania.append(
            f'<form method="post" action="{escapuj(adres_zrodla)}/zweryfikowane">\n'
            f"{_pole_csrf(token_csrf)}\n"
            f'<button type="submit" aria-describedby="{id_opisu}">'
            "Oznacz jako zweryfikowane</button>\n</form>"
        )
    if zrodlo.czy_mozna_zastapic_tresc:
        dzialania.append(
            f'<form method="post" action="{escapuj(adres_zrodla)}/zastap" '
            'enctype="multipart/form-data">\n'
            f"{_pole_csrf(token_csrf)}\n"
            f'<input type="file" id="zastap-{id_el}" name="plik" required '
            'aria-label="Plik z ręcznie zapisaną treścią tego źródła" '
            f'aria-describedby="{id_opisu}">\n'
            f'<button type="submit" aria-describedby="{id_opisu}">'
            "Zastąp treść plikiem</button>\n</form>"
        )
    dzialania.append(
        f'<p><a href="{escapuj(adres_zrodla)}/usun" aria-describedby="{id_opisu}">'
        "Usuń źródło z projektu</a></p>"
    )

    return (
        f'<li id="zrodlo-{id_el}">\n'
        f'<h3 id="{id_opisu}">{escapuj(zrodlo.pochodzenie)}</h3>\n'
        f"<ul>\n{''.join(szczegoly)}\n</ul>\n"
        f"{chr(10).join(dzialania)}\n</li>"
    )
