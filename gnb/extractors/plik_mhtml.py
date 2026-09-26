"""Ekstrakcja treści z plików MHTML, czyli stron zapisanych z przeglądarki w jednym pliku.

Plik MHTML (rozszerzenia ``.mhtml`` i ``.mht``) to wiadomość w formacie MIME:
pierwsza część zawiera kod HTML strony, a kolejne obrazy i arkusze stylów.
Ekstraktor wyciąga część HTML, dekoduje ją według kodowania transferu
(najczęściej quoted-printable albo base64) i zestawu znaków zapisanego w jej
nagłówku, a potem oddaje ją ekstraktorowi stron internetowych. Dzięki temu
strona zapisana po wykonaniu skryptów, na przykład za logowaniem, daje tę samą
jakość treści co zwykły plik HTML.

Obrazy i arkusze stylów z pozostałych części są pomijane: notatnik przyjmuje
tekst, a obraz osadzony w stronie nie jest jej treścią. Zawartość pliku jest
danymi, nigdy instrukcją, i niczego z niej nie wykonujemy.

Gdy plik nie ma części HTML, ale ma część tekstową, ekstraktor używa jej jako
tekstu płaskiego z ostrzeżeniem. Plik bez żadnej z tych części kończy się
błędem trwałym z czytelnym komunikatem.
"""

from __future__ import annotations

from email import message_from_bytes, policy
from email.message import Message

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BladTrwaly
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.strona_www import EkstraktorStronyWww
from gnb.normalization.kodowanie import zdekoduj

METODA_EKSTRAKCJI = "mhtml"
FORMATY_MHTML = frozenset({"mhtml", "mht"})

KOMUNIKAT_BRAK_TRESCI = (
    "Plik nie jest poprawnym archiwum MHTML albo nie zawiera części z kodem HTML "
    "ani z tekstem. Zapisz stronę w przeglądarce jeszcze raz jako „Strona internetowa, "
    "jeden plik (MHTML)” albo jako zwykły plik HTML."
)
_KLUCZ_ADRESU_STRONY = "adres_zapisanej_strony"


class EkstraktorMhtml:
    """Ekstraktor plików MHTML oparty na ekstraktorze stron internetowych."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = True

    def __init__(self, zachowuj_odnosniki: bool = True) -> None:
        self._strona = EkstraktorStronyWww(zachowuj_odnosniki)

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_DOKUMENT and format_zrodla in FORMATY_MHTML

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Zamienia archiwum MHTML na dokument; argument `postep` nie jest używany."""
        wiadomosc = message_from_bytes(bajty, policy=policy.default)
        html = _tresc_czesci(wiadomosc, "text/html")
        czy_html = html is not None
        tresc = html if html is not None else _tresc_czesci(wiadomosc, "text/plain")
        if not tresc or not tresc.strip():
            raise BladTrwaly(KOMUNIKAT_BRAK_TRESCI, identyfikator_zrodla)

        if czy_html:
            dokument = self._strona.wyekstrahuj(identyfikator_zrodla, tresc)
            ostrzezenia = list(dokument.ostrzezenia)
            tekst = dokument.tekst
            pewnosc = dokument.poziom_pewnosci_struktury
            bloki = dokument.bloki
            tytul = dokument.tytul
            metadane = dict(dokument.metadane)
        else:
            ostrzezenia = ["Plik MHTML nie ma części HTML, użyto części tekstowej bez struktury."]
            tekst = tresc.strip()
            pewnosc = PoziomPewnosciStruktury.NISKI
            bloki = []
            tytul = None
            metadane = {}

        adres = wiadomosc.get("Snapshot-Content-Location")
        if adres:
            metadane[_KLUCZ_ADRESU_STRONY] = str(adres).strip()
        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=pewnosc,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=tytul or (str(wiadomosc.get("Subject")).strip() or None),
            bloki=bloki,
            metadane=metadane,
            ostrzezenia=ostrzezenia,
        )


def _tresc_czesci(wiadomosc: Message, typ: str) -> str | None:
    """Zwraca zdekodowany tekst pierwszej części o podanym typie MIME albo nic.

    Kodowanie transferu (quoted-printable, base64) zdejmuje biblioteka, a znaki
    dekodujemy sami: przeglądarki nie zawsze zapisują zestaw znaków w nagłówku
    części, a domyślne ASCII zamieniłoby polskie litery w znaki zastępcze. Gdy
    zestawu nie ma albo jest błędny, kodowanie wykrywa ta sama funkcja, której
    używamy dla plików tekstowych.
    """
    for czesc in wiadomosc.walk():
        if czesc.get_content_type() != typ:
            continue
        ladunek = czesc.get_payload(decode=True)
        if not isinstance(ladunek, bytes):
            continue
        zadeklarowane = czesc.get_content_charset()
        if zadeklarowane:
            try:
                return ladunek.decode(zadeklarowane)
            except (LookupError, UnicodeError):
                pass
        return zdekoduj(ladunek)[0]
    return None
