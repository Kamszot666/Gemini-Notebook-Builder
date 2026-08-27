"""Przyjmowanie wejść użytkownika, walidacja i tworzenie źródeł.

Po etapie drugim obsługiwane są trzy rodzaje wejścia: tekst wklejony
bezpośrednio, plik lokalny w formacie TXT lub MD oraz adres strony internetowej.
Moduł zamienia wejście na `PozycjaWejsciowa`, a następnie na zwalidowane
`Zrodlo` z deterministycznym identyfikatorem i pełną sumą kontrolną.

Dla adresu strony identyfikator powstaje z kanonicznej postaci adresu, a nie
z treści, ponieważ musi być znany przed pobraniem. Dzięki temu wznowienie pracy
wie, którego adresu nie trzeba pobierać ponownie. Suma kontrolna treści jest
uzupełniana po pobraniu.

Wskazówka formatu, czyli rozszerzenie pliku albo zadeklarowany format tekstu
wklejonego, jest przenoszona osobno w `PozycjaWejsciowa`, żeby nie zmieniać
kontraktu danych `WejscieSurowe`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from gnb.core.identyfikatory import (
    identyfikator_zrodla,
    suma_kontrolna_bajtow,
    suma_kontrolna_pliku,
    suma_kontrolna_tekstu_wklejonego,
)
from gnb.core.konfiguracja import Konfiguracja
from gnb.core.model import WejscieSurowe, Zrodlo
from gnb.core.stale import StatusZrodla, TypWejscia, TypZrodla
from gnb.core.url import adres_kanoniczny, adres_pobierania
from gnb.core.wyjatki import BladTrwaly, FormatNieobslugiwany, PrzekroczonoLimit
from gnb.normalization.kodowanie import zdekoduj

FORMATY_PLIKOW = frozenset({"txt", "md"})
FORMATY_TEKSTU_WKLEJONEGO = frozenset({"txt", "md"})
FORMAT_STRONY_WWW = "html"
_ZNAK_BOM = "\ufeff"
_BAJTOW_W_MEGABAJCIE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class PozycjaWejsciowa:
    """Jedno wejście przygotowane do przetwarzania.

    Pole `format_zrodla` to małą literą zapisane rozszerzenie pliku bez kropki
    albo zadeklarowany format tekstu wklejonego, czyli ``txt`` lub ``md``. Dla
    strony internetowej jest to ``html``.

    Pole `adres_kanoniczny` jest wypełnione wyłącznie dla adresów stron. Wartość
    w `wejscie.wartosc` jest wtedy adresem wysyłanym do serwera, czyli może mieć
    inną kolejność parametrów niż postać kanoniczna.

    Pole `wskazane_jawnie` mówi, czy wejście pochodzi wprost z listy podanej przez
    użytkownika. Od tego zależy wyjątek od kontroli pliku ``robots.txt`` opisany
    w sekcji piętnastej CLAUDE.md. Adres znaleziony kiedyś przez sam program
    w treści innego źródła będzie miał tu wartość fałsz.
    """

    wejscie: WejscieSurowe
    format_zrodla: str
    adres_kanoniczny: str | None = None
    wskazane_jawnie: bool = True


def przyjmij_tekst(
    tresc: str, moment_dodania: datetime, *, format_tekstu: str = "txt"
) -> PozycjaWejsciowa:
    """Tworzy pozycję wejściową z tekstu wklejonego przez użytkownika.

    Domyślnie tekst wklejony jest traktowany jako tekst płaski. Format ``md``
    wskazuje, że użytkownik świadomie deklaruje tekst jako Markdown.
    """
    format_znormalizowany = format_tekstu.strip().lower() or "txt"
    if format_znormalizowany not in FORMATY_TEKSTU_WKLEJONEGO:
        raise FormatNieobslugiwany(
            f"Nieobsługiwany format tekstu wklejonego: „{format_tekstu}”. Dozwolone: txt, md."
        )
    wejscie = WejscieSurowe(
        identyfikator_wejscia=_identyfikator_wejscia(TypWejscia.TEKST, tresc),
        typ_wejscia=TypWejscia.TEKST,
        wartosc=tresc,
        moment_dodania=moment_dodania,
    )
    return PozycjaWejsciowa(wejscie=wejscie, format_zrodla=format_znormalizowany)


def przyjmij_url(
    adres: str, moment_dodania: datetime, dodatkowe_parametry_sledzace: tuple[str, ...] = ()
) -> PozycjaWejsciowa:
    """Tworzy pozycję wejściową z adresu strony internetowej.

    Adres jest walidowany, a następnie zapisywany w dwóch postaciach: kanonicznej
    jako klucz tożsamości oraz pobierania jako to, co realnie trafi do serwera.
    Niepoprawny adres kończy się błędem trwałym.
    """
    kanoniczny = adres_kanoniczny(adres, dodatkowe_parametry_sledzace)
    do_pobrania = adres_pobierania(adres, dodatkowe_parametry_sledzace)
    wejscie = WejscieSurowe(
        identyfikator_wejscia=_identyfikator_wejscia(TypWejscia.URL, kanoniczny),
        typ_wejscia=TypWejscia.URL,
        wartosc=do_pobrania,
        moment_dodania=moment_dodania,
    )
    return PozycjaWejsciowa(
        wejscie=wejscie, format_zrodla=FORMAT_STRONY_WWW, adres_kanoniczny=kanoniczny
    )


def identyfikator_strony(adres_kanoniczny_zrodla: str) -> str:
    """Buduje identyfikator źródła sieciowego z kanonicznej postaci jego adresu.

    Identyfikator jest znany przed pobraniem, dzięki czemu wznowienie pracy
    rozpoznaje adresy już przetworzone i nie pobiera ich ponownie.
    """
    return identyfikator_zrodla(
        TypZrodla.STRONA_WWW, suma_kontrolna_bajtow(adres_kanoniczny_zrodla.encode("utf-8"))
    )


def przyjmij_plik(sciezka: Path, moment_dodania: datetime) -> PozycjaWejsciowa:
    """Tworzy pozycję wejściową ze ścieżki pliku lokalnego."""
    format_zrodla = sciezka.suffix.lstrip(".").lower()
    wejscie = WejscieSurowe(
        identyfikator_wejscia=_identyfikator_wejscia(TypWejscia.PLIK, str(sciezka)),
        typ_wejscia=TypWejscia.PLIK,
        wartosc=str(sciezka),
        moment_dodania=moment_dodania,
    )
    return PozycjaWejsciowa(wejscie=wejscie, format_zrodla=format_zrodla)


def waliduj_i_utworz_zrodlo(
    pozycja: PozycjaWejsciowa, konfiguracja: Konfiguracja, moment: datetime
) -> Zrodlo:
    """Waliduje wejście i buduje z niego zwalidowane `Zrodlo`.

    Dla pliku sprawdzane jest istnienie, to czy jest zwykłym plikiem, obsługiwany
    format oraz mieszczenie się w bezpiecznym limicie rozmiaru. Dla tekstu
    wklejonego sprawdzane jest, czy nie jest pusty. Błędy są zgłaszane jako
    wyjątki z komunikatem po polsku.
    """
    if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK:
        return _zrodlo_z_pliku(pozycja, konfiguracja, moment)
    if pozycja.wejscie.typ_wejscia is TypWejscia.URL:
        return _zrodlo_z_url(pozycja, moment)
    return _zrodlo_z_tekstu(pozycja, moment)


def wczytaj_tresc_zrodla(pozycja: PozycjaWejsciowa) -> tuple[str, str]:
    """Zwraca rozkodowany tekst źródła oraz nazwę użytego kodowania.

    Dla pliku bajty są wczytywane z dysku i dekodowane z wykryciem kodowania.
    Dla tekstu wklejonego zwracany jest wprost jego tekst, po odcięciu znaku
    kolejności bajtów, jeżeli występuje. Treść adresu strony nie pochodzi z tej
    funkcji, tylko z osobnej fazy pobrania w potoku.
    """
    if pozycja.wejscie.typ_wejscia is TypWejscia.URL:
        raise BladTrwaly(
            "Treść strony internetowej pochodzi z fazy pobrania, a nie z odczytu wejścia."
        )
    if pozycja.wejscie.typ_wejscia is TypWejscia.PLIK:
        dane = Path(pozycja.wejscie.wartosc).read_bytes()
        return zdekoduj(dane)
    tekst = pozycja.wejscie.wartosc
    if tekst.startswith(_ZNAK_BOM):
        tekst = tekst[len(_ZNAK_BOM) :]
    return tekst, "utf-8 (tekst wklejony)"


def identyfikator_awaryjny(pozycja: PozycjaWejsciowa) -> str:
    """Buduje zastępczy identyfikator dla wejścia, którego nie dało się zwalidować."""
    skrot = hashlib.sha256(
        f"{pozycja.wejscie.typ_wejscia.value}|{pozycja.wejscie.wartosc}".encode()
    ).hexdigest()[:16]
    return f"blad-{skrot}"


def _zrodlo_z_pliku(
    pozycja: PozycjaWejsciowa, konfiguracja: Konfiguracja, moment: datetime
) -> Zrodlo:
    sciezka = Path(pozycja.wejscie.wartosc)
    if not sciezka.exists():
        raise BladTrwaly(f"Plik nie istnieje: {sciezka}.")
    if not sciezka.is_file():
        raise BladTrwaly(f"Ścieżka nie wskazuje zwykłego pliku: {sciezka}.")
    if pozycja.format_zrodla not in FORMATY_PLIKOW:
        raise FormatNieobslugiwany(
            f"Nieobsługiwany format pliku: „{pozycja.format_zrodla or 'brak rozszerzenia'}”. "
            "Etap pierwszy obsługuje TXT i MD."
        )
    rozmiar = sciezka.stat().st_size
    limit_bajtow = konfiguracja.bezpieczny_limit_mb * _BAJTOW_W_MEGABAJCIE
    if rozmiar > limit_bajtow:
        raise PrzekroczonoLimit(
            f"Plik {sciezka.name} ma {rozmiar} bajtów, ponad bezpieczny limit "
            f"{limit_bajtow} bajtów. Podział zbyt dużego źródła to zadanie etapu szóstego."
        )
    suma = suma_kontrolna_pliku(sciezka)
    return Zrodlo(
        identyfikator_zrodla=identyfikator_zrodla(TypZrodla.PLIK_TEKSTOWY, suma),
        typ_zrodla=TypZrodla.PLIK_TEKSTOWY,
        pochodzenie=sciezka.name,
        checksum=suma,
        status=StatusZrodla.OCZEKUJE,
        utworzono=moment,
        zaktualizowano=moment,
    )


def _zrodlo_z_url(pozycja: PozycjaWejsciowa, moment: datetime) -> Zrodlo:
    """Buduje źródło dla adresu strony. Suma kontrolna treści dochodzi po pobraniu."""
    kanoniczny = pozycja.adres_kanoniczny or adres_kanoniczny(pozycja.wejscie.wartosc)
    return Zrodlo(
        identyfikator_zrodla=identyfikator_strony(kanoniczny),
        typ_zrodla=TypZrodla.STRONA_WWW,
        pochodzenie=kanoniczny,
        checksum=None,
        status=StatusZrodla.OCZEKUJE,
        utworzono=moment,
        zaktualizowano=moment,
    )


def _zrodlo_z_tekstu(pozycja: PozycjaWejsciowa, moment: datetime) -> Zrodlo:
    tresc = pozycja.wejscie.wartosc
    if not tresc.strip():
        raise BladTrwaly("Tekst wklejony jest pusty.")
    suma = suma_kontrolna_tekstu_wklejonego(tresc)
    return Zrodlo(
        identyfikator_zrodla=identyfikator_zrodla(TypZrodla.TEKST_WKLEJONY, suma),
        typ_zrodla=TypZrodla.TEKST_WKLEJONY,
        pochodzenie="tekst wklejony",
        checksum=suma,
        status=StatusZrodla.OCZEKUJE,
        utworzono=moment,
        zaktualizowano=moment,
    )


def _identyfikator_wejscia(typ: TypWejscia, wartosc: str) -> str:
    skrot = hashlib.sha256(f"{typ.value}|{wartosc}".encode()).hexdigest()[:12]
    return f"wej-{skrot}"
