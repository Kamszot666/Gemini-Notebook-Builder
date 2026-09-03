"""Nagłówek metadanych dopisywany na początku każdego pliku wynikowego.

Sama treść źródła nie mówi, skąd pochodzi. Transkrypcja filmu bez tytułu i adresu
jest w notatniku materiałem bez kontekstu, a artykuł bez daty publikacji bywa
różnicą między informacją a dezinformacją. Nagłówek rozwiązuje to raz, wspólnie
dla wszystkich typów źródeł.

Zasady zapisu, ustalone przez użytkownika:

1. Każdy wiersz ma postać etykieta, dwukropek, spacja, wartość.
2. Kolejność pól jest stała i wynika z listy w tym module.
3. Pole nieobecne dla danego źródła jest pomijane w całości, a nie drukowane
   z pustą wartością.
4. Pola „Adres” i „Plik” wykluczają się wzajemnie. Adres dotyczy źródeł
   sieciowych i jest adresem pobierania, nie postacią kanoniczną. Plik dotyczy
   źródeł lokalnych i jest nazwą pliku wejściowego.
5. Nagłówek oddziela od treści dokładnie jeden pusty wiersz. Nie ma linii
   ozdobnych ani separatorów ze znaków.
6. Nagłówek trafia w identycznej postaci do wersji TXT i do wersji MD, zawsze
   jako zwykły tekst, bez składni Markdown. Są to metadane strukturalne, a nie
   treść artykułu, więc nie mogą stać się nagłówkiem sekcji ani trafić do
   automatycznego spisu treści notatnika.

Nagłówek nie jest wliczany do limitów notatnika. Limit słów i limit rozmiaru
sprawdzane są na samej treści dokumentu, ponieważ nagłówek jest informacją
o źródle, a nie jego treścią.
"""

from __future__ import annotations

from collections.abc import Mapping

from gnb.core.stale import TypZrodla

ETYKIETA_TYTUL = "Tytuł"
ETYKIETA_TYP = "Typ źródła"
ETYKIETA_ADRES = "Adres"
ETYKIETA_PLIK = "Plik"
ETYKIETA_AUTOR = "Autor"
ETYKIETA_DATA_PUBLIKACJI = "Data publikacji"
ETYKIETA_KANAL = "Kanał"
ETYKIETA_DLUGOSC = "Długość"
ETYKIETA_JEZYK_NAPISOW = "Język napisów"
ETYKIETA_RODZAJ_NAPISOW = "Rodzaj napisów"
ETYKIETA_JEZYK = "Język"
ETYKIETA_DATA_IMPORTU = "Data importu"
ETYKIETA_IDENTYFIKATOR = "Identyfikator źródła"
ETYKIETA_CZESC = "Część"

# Stała kolejność pól nagłówka. Pole spoza tej listy nie trafia do wyniku, żeby
# układ nagłówka był przewidywalny przy odsłuchu czytnikiem ekranu.
KOLEJNOSC_POL: tuple[str, ...] = (
    ETYKIETA_TYTUL,
    ETYKIETA_TYP,
    ETYKIETA_ADRES,
    ETYKIETA_PLIK,
    ETYKIETA_AUTOR,
    ETYKIETA_DATA_PUBLIKACJI,
    ETYKIETA_KANAL,
    ETYKIETA_DLUGOSC,
    ETYKIETA_JEZYK_NAPISOW,
    ETYKIETA_RODZAJ_NAPISOW,
    ETYKIETA_JEZYK,
    ETYKIETA_DATA_IMPORTU,
    ETYKIETA_IDENTYFIKATOR,
    ETYKIETA_CZESC,
)

# Nazwy typów źródła w postaci zrozumiałej bez znajomości kodu.
OPISY_TYPOW_ZRODLA = {
    TypZrodla.STRONA_WWW: "strona internetowa",
    TypZrodla.YOUTUBE: "film z serwisu YouTube",
    TypZrodla.TEKST_WKLEJONY: "tekst wklejony",
    TypZrodla.PLIK_TEKSTOWY: "plik tekstowy",
    TypZrodla.PLIK_DOKUMENT: "dokument",
    TypZrodla.PLIK_AUDIO: "nagranie",
    TypZrodla.PLIK_OBRAZ: "obraz",
    TypZrodla.PLIK_NUTY: "materiał nutowy",
}

_SEKUND_W_MINUCIE = 60
_SEKUND_W_GODZINIE = 3600


def zbuduj_naglowek(pola: Mapping[str, str]) -> str:
    """Buduje nagłówek metadanych z podanych pól, w stałej kolejności.

    Pole puste albo nieobecne jest pomijane. Pusty zestaw pól daje pusty napis,
    a nie sam pusty wiersz.
    """
    wiersze = [
        f"{etykieta}: {pola[etykieta].strip()}"
        for etykieta in KOLEJNOSC_POL
        if pola.get(etykieta) and pola[etykieta].strip()
    ]
    return "\n".join(wiersze)


def polacz_z_trescia(naglowek: str, tresc: str) -> str:
    """Skleja nagłówek z treścią, oddzielając je dokładnie jednym pustym wierszem."""
    if not naglowek:
        return tresc
    if not tresc:
        return naglowek
    return f"{naglowek}\n\n{tresc}"


def z_oznaczeniem_czesci(naglowek: str, numer_czesci: int, liczba_czesci: int) -> str:
    """Dokłada do nagłówka wiersz „Część: N z M” dla źródła podzielonego na części.

    Pole części jest ostatnie w stałej kolejności pól nagłówka, więc dopisanie go
    na końcu zachowuje przewidywalny układ przy odsłuchu czytnikiem ekranu.
    Nagłówek pusty daje sam ten wiersz.
    """
    wiersz = f"{ETYKIETA_CZESC}: {numer_czesci} z {liczba_czesci}"
    return wiersz if not naglowek else f"{naglowek}\n{wiersz}"


def opis_typu_zrodla(typ: TypZrodla) -> str:
    """Zwraca nazwę typu źródła w postaci przeznaczonej dla człowieka."""
    return OPISY_TYPOW_ZRODLA.get(typ, typ.value)


def opis_dlugosci(sekundy: int) -> str:
    """Zamienia liczbę sekund na czytelny opis czasu trwania.

    Zapis jest słowny, a nie w postaci dwukropków, ponieważ czytnik ekranu
    odczytuje „20 minut 3 sekundy” zrozumiale, a zapis „20:03” bywa odczytywany
    jako godzina.
    """
    if sekundy < 0:
        return ""
    godziny, reszta = divmod(sekundy, _SEKUND_W_GODZINIE)
    minuty, sekundy_reszty = divmod(reszta, _SEKUND_W_MINUCIE)

    czesci: list[str] = []
    if godziny:
        czesci.append(f"{godziny} {_odmiana(godziny, 'godzina', 'godziny', 'godzin')}")
    if minuty:
        czesci.append(f"{minuty} {_odmiana(minuty, 'minuta', 'minuty', 'minut')}")
    if sekundy_reszty or not czesci:
        czesci.append(
            f"{sekundy_reszty} {_odmiana(sekundy_reszty, 'sekunda', 'sekundy', 'sekund')}"
        )
    return " ".join(czesci)


def _odmiana(liczba: int, pojedyncza: str, mnoga: str, dopelniacz: str) -> str:
    """Dobiera polską formę rzeczownika do liczby.

    Reguła jest zwyczajna dla polszczyzny: jeden bierze liczbę pojedynczą,
    końcówki od dwóch do czterech biorą liczbę mnogą, a pozostałe dopełniacz.
    Wyjątkiem są liczby od jedenastu do czternastu, które zawsze biorą
    dopełniacz.
    """
    if liczba == 1:
        return pojedyncza
    ostatnia = liczba % 10
    dwie_ostatnie = liczba % 100
    if 2 <= ostatnia <= 4 and not 12 <= dwie_ostatnie <= 14:
        return mnoga
    return dopelniacz
