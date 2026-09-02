"""Testy ochrony przed CSRF opartej na podwójnym przesłaniu tokenu."""

from __future__ import annotations

from gnb.ui.csrf import (
    NAZWA_CIASTECZKA,
    naglowek_ustawienia_ciasteczka,
    nowy_token,
    token_z_ciasteczka,
    zgodny,
)


def test_token_z_formularza_zgodny_z_tokenem_ciasteczka_przechodzi() -> None:
    token = nowy_token()
    assert zgodny(token, token) is True


def test_brak_tokenu_formularza_jest_odrzucany() -> None:
    token = nowy_token()
    assert zgodny(token, None) is False
    assert zgodny(token, "") is False


def test_token_cudzej_sesji_jest_odrzucany() -> None:
    assert zgodny(nowy_token(), nowy_token()) is False


def test_token_odczytany_z_naglowka_cookie() -> None:
    token = nowy_token()
    naglowek = f"{NAZWA_CIASTECZKA}={token}; inne=1"
    assert token_z_ciasteczka(naglowek) == token


def test_brak_ciasteczka_sesji_daje_none() -> None:
    assert token_z_ciasteczka(None) is None
    assert token_z_ciasteczka("inne=1") is None


def test_naglowek_ciasteczka_jest_httponly_i_samesite_strict() -> None:
    naglowek = naglowek_ustawienia_ciasteczka("abc")
    assert "HttpOnly" in naglowek
    assert "SameSite=Strict" in naglowek
    assert "Path=/" in naglowek
