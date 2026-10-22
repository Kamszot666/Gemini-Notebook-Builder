"""Rozpoznanie, co globalny skrót ma dodać do aktywnego projektu.

Czysta logika, niezależna od Windows: przyjmuje już zebrane informacje
o aktywnym oknie, ewentualną wartość paska adresu i ewentualną listę
zaznaczonych plików, a zwraca albo opis tego, co dodać, albo porażkę
z czytelnym powodem. Dzięki temu ta funkcja jest testowalna na każdym
systemie, bez ani jednego wywołania Win32 — testy budują ``InformacjeOOknie``
ręcznie.

Rozróżnienie dwóch sytuacji przy przeglądarce jest celowe i zgodne z decyzją
z sekcji dwunastej CLAUDE.md: pasek adresu odczytany i pusty daje jedną
porażkę, a pasek adresu, którego w ogóle nie dało się odczytać, daje inną —
ta druga nigdy nie dodaje niczego po cichu.
"""

from __future__ import annotations

import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from gnb.core.url import czy_wyglada_na_adres
from gnb.hotkeys.model import (
    DodanieZeSkrotu,
    InformacjeOOknie,
    RodzajZaznaczenia,
    TypDodania,
    ZaznaczonyTekst,
)

# Nazwy procesów przeglądarek obsługiwanych w części A etapu jedenastego,
# zgodnie z decyzją użytkownika: to dwie przeglądarki używane na co dzień.
_PRZEGLADARKI = frozenset({"chrome", "firefox"})

# Nazwa klasy okna prawdziwego Eksploratora plików. Sam proces „explorer”
# obsługuje też pulpit i pasek zadań, więc nazwa procesu nie wystarcza do
# rozpoznania, patrz ``_KLASY_PULPITU`` niżej.
_KLASA_OKNA_EKSPLORATORA = "CabinetWClass"

# Klasy okien pulpitu i paska zadań, należące do procesu „explorer”, ale
# niebędące oknem z zawartością. Dostają osobny, czytelniejszy komunikat
# porażki niż nierozpoznany program.
_KLASY_PULPITU = frozenset({"Progman", "WorkerW", "Shell_TrayWnd"})

_SCHEMATY_ROZPOZNAWANE = ("http://", "https://", "ftp://", "file://")
_SCHEMATY_ZAZNACZONYCH_ADRESOW = ("http://", "https://")

KOMUNIKAT_ADRES_INTERFEJSU = (
    "To jest adres interfejsu Gemini Notebook Builder, nie dodano go jako źródła."
)


@dataclass(frozen=True, slots=True)
class PorazkaRozpoznania:
    """Skrót nie ma czego dodać do aktywnego projektu. Niesie czytelny powód."""

    powod: str


def rozpoznaj(
    okno: InformacjeOOknie,
    adres_paska: str | None,
    pliki_zaznaczone: Sequence[Path],
    *,
    zaznaczony_tekst: str | None = None,
    adres_nasluchu: str = "127.0.0.1",
    port_nasluchu: int | None = None,
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    """Ustala, co dodać do aktywnego projektu na podstawie stanu aktywnego okna.

    Argument ``adres_paska`` ma trzy możliwe znaczenia: wartość ze spacjami
    obciętymi to odczytany adres, pusty napis to odczytany, ale pusty pasek
    adresu, a ``None`` oznacza, że paska adresu w ogóle nie dało się odczytać.
    Tylko pierwsza sytuacja kończy się dodaniem adresu.

    Argument ``zaznaczony_tekst`` dotyczy wyłącznie przeglądarek. Niepusty
    tekst ma pierwszeństwo przed paskiem adresu; ``None`` albo tekst złożony
    z samych białych znaków oznacza, że nic nie zaznaczono, i skrót działa jak
    dotąd. Adres interfejsu, czyli pętla zwrotna albo adres i port nasłuchu
    z konfiguracji, nigdy nie jest przyjmowany jako źródło.
    """
    if okno.nazwa_procesu in _PRZEGLADARKI:
        return _rozpoznaj_przegladarke(
            okno, adres_paska, zaznaczony_tekst, adres_nasluchu, port_nasluchu
        )
    if okno.nazwa_klasy == _KLASA_OKNA_EKSPLORATORA:
        return _rozpoznaj_eksplorator(pliki_zaznaczone)
    if okno.nazwa_klasy in _KLASY_PULPITU:
        return PorazkaRozpoznania("Aktywne okno to pulpit. Nic nie dodano.")
    nazwa = okno.nazwa_procesu or "nieznany"
    return PorazkaRozpoznania(f"Aktywny program to {nazwa}, nie wiem, jak z niego coś dodać.")


def _rozpoznaj_przegladarke(
    okno: InformacjeOOknie,
    adres_paska: str | None,
    zaznaczony_tekst: str | None,
    adres_nasluchu: str,
    port_nasluchu: int | None,
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    if zaznaczony_tekst is not None:
        zaznaczenie = sklasyfikuj_zaznaczenie(zaznaczony_tekst)
        if zaznaczenie is not None:
            return _rozpoznaj_zaznaczenie(zaznaczenie, adres_nasluchu, port_nasluchu)
    if adres_paska is None:
        return PorazkaRozpoznania(
            f"Nie udało się odczytać paska adresu w oknie „{okno.tytul}”. Nic nie dodano."
        )
    adres = adres_paska.strip()
    if not adres:
        return PorazkaRozpoznania(
            f"Pasek adresu w oknie „{okno.tytul}” jest pusty. Nic nie dodano."
        )
    znormalizowany = _znormalizowany_adres(adres)
    if not czy_wyglada_na_adres(znormalizowany):
        # Pasek adresu zawiera to, co jest w nim wpisane, nie to, co jest
        # załadowane — na przykład wpisywane właśnie hasło wyszukiwania, zanim
        # przeglądarka przejdzie na stronę wyników. Sprawdzamy tą samą
        # walidacją, z której korzysta reszta aplikacji przy przyjmowaniu URL
        # (`gnb.core.url.waliduj_adres`), żeby nie dodawać do projektu czegoś,
        # co i tak zostałoby odrzucone dalej w potoku, tylko wtedy bez dźwięku
        # sukcesu i bez czytelnego powodu.
        return PorazkaRozpoznania(
            f"Zawartość paska adresu w oknie „{okno.tytul}” nie wygląda na adres "
            "strony. Nic nie dodano."
        )
    if czy_adres_interfejsu(znormalizowany, adres_nasluchu, port_nasluchu):
        return PorazkaRozpoznania(KOMUNIKAT_ADRES_INTERFEJSU)
    return DodanieZeSkrotu(typ=TypDodania.ADRES, opis=okno.tytul or adres, adres=znormalizowany)


def sklasyfikuj_zaznaczenie(tekst: str) -> ZaznaczonyTekst | None:
    """Rozpoznaje, czy zaznaczony tekst to same adresy, czy zwykły tekst.

    Zwraca ``None`` dla tekstu pustego po usunięciu białych znaków, bo wtedy
    nic nie jest zaznaczone. Rodzaj ``ADRESY`` wymaga, żeby każdy niepusty
    wiersz był adresem ``http`` albo ``https`` bez spacji w środku; jedno
    słowo więcej w którymkolwiek wierszu czyni całość zwykłym tekstem. Końce
    wierszy ze schowka Windows są sprowadzane do pojedynczego znaku nowego
    wiersza.
    """
    ujednolicony = tekst.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not ujednolicony:
        return None
    wiersze = [wiersz.strip() for wiersz in ujednolicony.split("\n") if wiersz.strip()]
    if all(_jest_adresem_http(wiersz) for wiersz in wiersze):
        return ZaznaczonyTekst(
            rodzaj=RodzajZaznaczenia.ADRESY, adresy=tuple(dict.fromkeys(wiersze))
        )
    return ZaznaczonyTekst(rodzaj=RodzajZaznaczenia.TEKST, tekst=ujednolicony)


def _jest_adresem_http(wiersz: str) -> bool:
    return (
        wiersz.lower().startswith(_SCHEMATY_ZAZNACZONYCH_ADRESOW)
        and not any(znak.isspace() for znak in wiersz)
        and czy_wyglada_na_adres(wiersz)
    )


def _rozpoznaj_zaznaczenie(
    zaznaczenie: ZaznaczonyTekst, adres_nasluchu: str, port_nasluchu: int | None
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    if zaznaczenie.rodzaj is RodzajZaznaczenia.TEKST:
        return DodanieZeSkrotu(
            typ=TypDodania.TEKST, opis="zaznaczony tekst", tekst=zaznaczenie.tekst
        )
    dozwolone = tuple(
        adres
        for adres in zaznaczenie.adresy
        if not czy_adres_interfejsu(adres, adres_nasluchu, port_nasluchu)
    )
    if not dozwolone:
        return PorazkaRozpoznania(KOMUNIKAT_ADRES_INTERFEJSU)
    return DodanieZeSkrotu(
        typ=TypDodania.ADRESY_Z_ZAZNACZENIA,
        opis=dozwolone[0] if len(dozwolone) == 1 else f"{len(dozwolone)} adresów",
        adresy=dozwolone,
        liczba_pominietych_adresow_interfejsu=len(zaznaczenie.adresy) - len(dozwolone),
    )


def czy_adres_interfejsu(adres: str, adres_nasluchu: str, port_nasluchu: int | None) -> bool:
    """Prawda, gdy adres wskazuje na interfejs aplikacji, a nie na zewnętrzną stronę.

    Interfejsem jest każdy adres pętli zwrotnej (``127.0.0.1``, ``localhost``,
    ``localhost.``, ``::1``, ``::ffff:127.0.0.1``) oraz adres nieokreślony
    (``0.0.0.0``), niezależnie od portu, oraz adres i port nasłuchu z konfiguracji.
    Schemat nie ma znaczenia: ``https://127.0.0.1:8765/`` to ta sama strona
    co ``http://127.0.0.1:8765/``.
    """
    try:
        czesci = urlsplit(adres)
        host = (czesci.hostname or "").lower()
        port = czesci.port
    except ValueError:
        return False
    if not host:
        return False
    # Nazwa z kropką na końcu (``localhost.``) to ta sama nazwa w pełnej postaci.
    host = host.rstrip(".")
    if host == "localhost":
        return True
    try:
        adres_ip = ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        # Adres IPv4 zapisany jako IPv6 (``::ffff:127.0.0.1``) ma w Pythonie 3.12
        # ``is_loopback`` równe fałszowi, więc sprawdzamy jego postać IPv4.
        if isinstance(adres_ip, ipaddress.IPv6Address) and adres_ip.ipv4_mapped is not None:
            adres_ip = adres_ip.ipv4_mapped
        # Adres nieokreślony (0.0.0.0, ::) część systemów kieruje do własnego komputera.
        if adres_ip.is_loopback or adres_ip.is_unspecified:
            return True
    if port_nasluchu is None:
        return False
    domyslny_port = 443 if czesci.scheme.lower() == "https" else 80
    return host == adres_nasluchu.lower() and (port or domyslny_port) == port_nasluchu


def _rozpoznaj_eksplorator(
    pliki_zaznaczone: Sequence[Path],
) -> DodanieZeSkrotu | PorazkaRozpoznania:
    if not pliki_zaznaczone:
        return PorazkaRozpoznania(
            "Aktywne okno to Eksplorator plików bez zaznaczenia. Nic nie dodano."
        )
    pierwszy = pliki_zaznaczone[0].name
    if len(pliki_zaznaczone) == 1:
        opis = pierwszy
    else:
        opis = f"{pierwszy} i {len(pliki_zaznaczone) - 1} więcej"
    return DodanieZeSkrotu(typ=TypDodania.PLIKI, opis=opis, pliki=tuple(pliki_zaznaczone))


def _znormalizowany_adres(adres: str) -> str:
    """Dokłada schemat ``https://``, gdy pasek adresu pokazuje go bez schematu.

    Współczesne przeglądarki chowają schemat ``https://`` w pasku adresu, co
    sprawdzono na komputerze użytkownika zarówno w Chrome, jak i w Firefoksie.
    Adres z rozpoznawalnym schematem, na przykład ``http://`` z połączenia bez
    szyfrowania, zostaje bez zmian.
    """
    if adres.lower().startswith(_SCHEMATY_ROZPOZNAWANE):
        return adres
    return f"https://{adres}"
