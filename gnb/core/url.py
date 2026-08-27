"""Walidacja adresów internetowych oraz ich postać kanoniczna i pobierania.

Moduł rozdziela dwie różne postacie tego samego adresu, bo służą do czego
innego i mylenie ich powoduje trudne do wykrycia błędy.

Adres kanoniczny jest kluczem tożsamości. Na jego podstawie powstaje
identyfikator źródła oraz klucz pamięci podręcznej, dlatego musi być stabilny:
schemat i nazwa hosta małymi literami, usunięty domyślny port, usunięty
fragment, usunięte znane parametry śledzące oraz posortowane parametry
pozostałe. Dwa zapisy tego samego adresu dają ten sam klucz.

Adres pobierania jest tym, co realnie wysyłamy do serwera. Zachowuje oryginalną
kolejność parametrów, ponieważ część serwisów zwraca inną treść przy zmienionej
kolejności. Usuwane są z niego wyłącznie parametry śledzące.

Zakres czyszczenia jest celowo wąski. Usuwamy tylko znane parametry śledzące,
a wszystkie pozostałe zostawiamy, nawet gdy wyglądają na zbędne. Parametr bywa
jedynym wskazaniem konkretnego artykułu, a zbyt agresywne czyszczenie zlałoby
dwa różne źródła w jedno.

Przedrostek ``www`` nie jest usuwany z nazwy hosta, ponieważ istnieją serwisy,
w których wersja z nim i bez niego to dwie różne witryny.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from gnb.core.wyjatki import BladTrwaly

SCHEMATY_DOZWOLONE = ("http", "https")
_PORTY_DOMYSLNE = {"http": 80, "https": 443}

# Prefiksy nazw parametrów uznawanych za śledzące. Cała rodzina „utm_” pochodzi
# z kampanii marketingowych i nigdy nie wskazuje treści.
PREFIKSY_PARAMETROW_SLEDZACYCH = ("utm_",)

# Nazwy parametrów śledzących wskazywane wprost. Lista jest zamknięta i jawna,
# bo usunięcie parametru niosącego treść byłoby utratą źródła. Użytkownik może
# ją rozszerzyć w konfiguracji, bez zmiany kodu.
PARAMETRY_SLEDZACE = frozenset(
    {
        "dclid",
        "epik",
        "fbclid",
        "gbraid",
        "gclid",
        "igshid",
        "li_fat_id",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "msclkid",
        "oly_anon_id",
        "oly_enc_id",
        "s_kwcid",
        "ttclid",
        "twclid",
        "vero_conv",
        "vero_id",
        "wbraid",
        "yclid",
        "_ga",
        "_gl",
        "_hsenc",
        "_hsmi",
    }
)

# Fragment zaczynający się od jednego z tych znaków wskazuje treść, a nie
# miejsce na stronie. Występuje w starszych aplikacjach jednostronicowych,
# w których „#!/artykul/12” jest jedynym wskazaniem konkretnej podstrony.
_ZNAKI_FRAGMENTU_TRESCIOWEGO = ("!", "/")

_ZNAKI_BEZPIECZNE_W_SCIEZCE = "/%:@!$&'()*+,;=~"


def waliduj_adres(adres: str) -> str:
    """Sprawdza adres i zwraca go po obcięciu białych znaków.

    Adres bez schematu, ze schematem innym niż HTTP lub HTTPS albo bez nazwy
    hosta kończy się błędem trwałym z komunikatem po polsku. Nie zgadujemy
    brakującego schematu, ponieważ dopisanie ``https`` do przypadkowego tekstu
    zamieniłoby literówkę w pozornie poprawne źródło.
    """
    oczyszczony = adres.strip()
    if not oczyszczony:
        raise BladTrwaly("Adres jest pusty.")

    czesci = urlsplit(oczyszczony)
    if czesci.scheme.lower() not in SCHEMATY_DOZWOLONE:
        raise BladTrwaly(
            f"Adres „{oczyszczony}” nie zaczyna się od http albo https. "
            "Podaj pełny adres razem ze schematem."
        )
    if not czesci.hostname:
        raise BladTrwaly(f"Adres „{oczyszczony}” nie zawiera nazwy hosta.")
    if "." not in czesci.hostname and czesci.hostname != "localhost":
        raise BladTrwaly(
            f"Nazwa hosta w adresie „{oczyszczony}” wygląda na niepełną. "
            "Podaj adres z pełną nazwą domeny."
        )
    return oczyszczony


def czy_wyglada_na_adres(tekst: str) -> bool:
    """Zwraca prawdę, gdy tekst przechodzi walidację adresu, bez zgłaszania błędu."""
    try:
        waliduj_adres(tekst)
    except BladTrwaly:
        return False
    return True


def adres_kanoniczny(adres: str, dodatkowe_parametry_sledzace: Iterable[str] = ()) -> str:
    """Zwraca postać kanoniczną adresu, używaną jako klucz tożsamości źródła.

    Postać kanoniczna ma schemat i nazwę hosta małymi literami, usunięty
    domyślny port, ścieżkę co najmniej jednoznakową, parametry bez śledzących
    i posortowane oraz usunięty fragment, o ile fragment nie wskazuje treści.
    """
    czesci = urlsplit(waliduj_adres(adres))
    parametry = _bez_parametrow_sledzacych(
        parse_qsl(czesci.query, keep_blank_values=True), dodatkowe_parametry_sledzace
    )
    return urlunsplit(
        (
            czesci.scheme.lower(),
            _autorytet(czesci.scheme, czesci.netloc),
            _sciezka(czesci.path),
            urlencode(sorted(parametry)),
            _fragment(czesci.fragment),
        )
    )


def adres_pobierania(adres: str, dodatkowe_parametry_sledzace: Iterable[str] = ()) -> str:
    """Zwraca adres wysyłany do serwera: bez parametrów śledzących, w oryginalnej kolejności.

    W odróżnieniu od postaci kanonicznej kolejność parametrów pozostaje taka,
    jak podał użytkownik, ponieważ część serwerów zwraca przy innej kolejności
    inną treść albo odpowiada błędem.
    """
    czesci = urlsplit(waliduj_adres(adres))
    parametry = _bez_parametrow_sledzacych(
        parse_qsl(czesci.query, keep_blank_values=True), dodatkowe_parametry_sledzace
    )
    return urlunsplit(
        (
            czesci.scheme.lower(),
            _autorytet(czesci.scheme, czesci.netloc),
            _sciezka(czesci.path),
            urlencode(parametry),
            _fragment(czesci.fragment),
        )
    )


def czy_parametr_sledzacy(nazwa: str, dodatkowe: Iterable[str] = ()) -> bool:
    """Rozstrzyga, czy parametr o podanej nazwie jest parametrem śledzącym."""
    nazwa_mala = nazwa.strip().lower()
    if nazwa_mala in PARAMETRY_SLEDZACE:
        return True
    if any(nazwa_mala.startswith(prefiks) for prefiks in PREFIKSY_PARAMETROW_SLEDZACYCH):
        return True
    return nazwa_mala in {dodatkowy.strip().lower() for dodatkowy in dodatkowe}


def _bez_parametrow_sledzacych(
    parametry: Sequence[tuple[str, str]], dodatkowe: Iterable[str]
) -> list[tuple[str, str]]:
    """Odfiltrowuje parametry śledzące, zachowując kolejność pozostałych."""
    dodatkowe_male = {dodatkowy.strip().lower() for dodatkowy in dodatkowe if dodatkowy.strip()}
    return [
        (nazwa, wartosc)
        for nazwa, wartosc in parametry
        if not czy_parametr_sledzacy(nazwa, dodatkowe_male)
    ]


def _autorytet(schemat: str, netloc: str) -> str:
    """Buduje część autorytetu adresu: host małymi literami, bez domyślnego portu."""
    czesci = urlsplit(f"{schemat}://{netloc}")
    host = (czesci.hostname or "").lower()
    port = czesci.port
    if port is not None and port == _PORTY_DOMYSLNE.get(schemat.lower()):
        port = None

    dane_logowania = ""
    if czesci.username:
        dane_logowania = czesci.username
        if czesci.password:
            dane_logowania = f"{dane_logowania}:{czesci.password}"
        dane_logowania = f"{dane_logowania}@"

    return f"{dane_logowania}{host}{f':{port}' if port is not None else ''}"


def _sciezka(sciezka: str) -> str:
    """Zwraca ścieżkę adresu, zamieniając ścieżkę pustą na pojedynczy ukośnik.

    Adres bez ścieżki i adres z samym ukośnikiem wskazują ten sam zasób, więc
    muszą dawać ten sam klucz tożsamości.
    """
    if not sciezka:
        return "/"
    return quote(sciezka, safe=_ZNAKI_BEZPIECZNE_W_SCIEZCE)


def _fragment(fragment: str) -> str:
    """Usuwa fragment adresu, chyba że wskazuje on treść, a nie miejsce na stronie."""
    if fragment.startswith(_ZNAKI_FRAGMENTU_TRESCIOWEGO):
        return fragment
    return ""
