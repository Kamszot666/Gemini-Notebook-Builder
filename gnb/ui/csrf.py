"""Ochrona przed CSRF oparta na podwójnym przesłaniu tokenu.

Operacje zmieniające stan idą metodą POST i muszą nieść w ukrytym polu formularza
token zgadzający się z tokenem zapisanym w ciasteczku sesji, zgodnie z sekcją
jedenastą punkt czwarty CLAUDE.md. Porównanie jest wykonywane funkcją
``secrets.compare_digest``, więc nie zależy od czasu porównania.

Sesja jest minimalna: jedno ciasteczko z losowym tokenem, bez żadnych danych
osobowych i bez trwałego magazynu po stronie serwera. Ciasteczko jest
``HttpOnly`` i ``SameSite=Strict``. Flagi ``Secure`` nie ma, ponieważ interfejs
działa po zwykłym HTTP na pętli zwrotnej, gdzie HTTPS nie występuje, a wymóg
``Secure`` uniemożliwiłby ustawienie ciasteczka.
"""

from __future__ import annotations

import secrets
from http.cookies import CookieError, SimpleCookie

NAZWA_CIASTECZKA = "gnb_sesja"
NAZWA_POLA_FORMULARZA = "token_csrf"
_DLUGOSC_TOKENU_BAJTOW = 32


def nowy_token() -> str:
    """Zwraca nowy losowy token sesji, bezpieczny kryptograficznie."""
    return secrets.token_urlsafe(_DLUGOSC_TOKENU_BAJTOW)


def token_z_ciasteczka(naglowek_cookie: str | None) -> str | None:
    """Wydobywa token sesji z nagłówka ``Cookie`` żądania, jeżeli tam jest."""
    if not naglowek_cookie:
        return None
    ciasteczka: SimpleCookie = SimpleCookie()
    try:
        ciasteczka.load(naglowek_cookie)
    except CookieError:
        return None
    morsel = ciasteczka.get(NAZWA_CIASTECZKA)
    return morsel.value if morsel is not None else None


def naglowek_ustawienia_ciasteczka(token: str) -> str:
    """Buduje wartość nagłówka ``Set-Cookie`` dla tokenu sesji."""
    return f"{NAZWA_CIASTECZKA}={token}; Path=/; HttpOnly; SameSite=Strict"


def zgodny(token_ciasteczka: str | None, token_formularza: str | None) -> bool:
    """Rozstrzyga, czy token z formularza zgadza się z tokenem z ciasteczka.

    Brak któregokolwiek tokenu oznacza brak zgodności, a więc odrzucenie żądania.
    """
    if not token_ciasteczka or not token_formularza:
        return False
    return secrets.compare_digest(token_ciasteczka, token_formularza)
