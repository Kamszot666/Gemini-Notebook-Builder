"""Testy dwóch plików logów projektu."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from gnb.logging_pl.dziennik import DziennikSzczegolowy, DziennikWazny

# Strefa użyta w testach odpowiada polskiemu czasowi letniemu, żeby sprawdzić
# zapis czasu lokalnego, a nie czasu UTC.
_STREFA_LOKALNA = timezone(timedelta(hours=2))


class _ZegarKrokowy:
    def __init__(self, start: datetime, krok: timedelta) -> None:
        self._teraz = start
        self._krok = krok

    def __call__(self) -> datetime:
        biezacy = self._teraz
        self._teraz = self._teraz + self._krok
        return biezacy


def test_log_wazny_ma_zatwierdzony_format_i_wiersz_daty(tmp_path: Path) -> None:
    zegar = _ZegarKrokowy(
        datetime(2026, 8, 26, 9, 5, tzinfo=_STREFA_LOKALNA), timedelta(minutes=1)
    )
    dziennik = DziennikWazny(tmp_path / "log_wazne.txt", zegar)

    dziennik.zapisz("Projekt utworzony")
    dziennik.zapisz("Źródło przyjęte")

    wiersze = (tmp_path / "log_wazne.txt").read_text(encoding="utf-8").splitlines()
    assert wiersze[0] == "--- 2026-08-26 (czas lokalny) ---"
    assert wiersze[1] == "Projekt utworzony|09:05"
    assert wiersze[2] == "Źródło przyjęte|09:06"


def test_wiersz_daty_pojawia_sie_przy_zmianie_dnia(tmp_path: Path) -> None:
    zegar = _ZegarKrokowy(
        datetime(2026, 8, 26, 23, 59, tzinfo=_STREFA_LOKALNA), timedelta(minutes=5)
    )
    dziennik = DziennikWazny(tmp_path / "log_wazne.txt", zegar)

    dziennik.zapisz("Przed północą")
    dziennik.zapisz("Po północy")

    tekst = (tmp_path / "log_wazne.txt").read_text(encoding="utf-8")
    assert tekst.count("--- 2026-08-26 (czas lokalny) ---") == 1
    assert tekst.count("--- 2026-08-27 (czas lokalny) ---") == 1


def test_domyslny_zegar_dziennika_waznego_uzywa_czasu_lokalnego(tmp_path: Path) -> None:
    dziennik = DziennikWazny(tmp_path / "log_wazne.txt")
    dziennik.zapisz("Projekt utworzony")

    oczekiwana_data = datetime.now().astimezone().strftime("%Y-%m-%d")
    tekst = (tmp_path / "log_wazne.txt").read_text(encoding="utf-8")
    assert tekst.startswith(f"--- {oczekiwana_data} (czas lokalny) ---")


def test_zdarzenie_z_pionowa_kreska_jest_odrzucane(tmp_path: Path) -> None:
    dziennik = DziennikWazny(tmp_path / "log_wazne.txt")
    with pytest.raises(ValueError, match="pionowej kreski"):
        dziennik.zapisz("złe|zdarzenie")


def test_log_szczegolowy_ma_wszystkie_pola(tmp_path: Path) -> None:
    sciezka = tmp_path / "log_szczegolowy.txt"
    with DziennikSzczegolowy(sciezka, "proj-abc") as log:
        log.info("Komunikat testowy", extra={"identyfikator_zrodla": "plik_tekstowy-1"})
        try:
            raise RuntimeError("wyjątek testowy")
        except RuntimeError:
            log.error("Błąd źródła", exc_info=True)

    tekst = sciezka.read_text(encoding="utf-8")
    assert "|INFO|" in tekst
    assert "|plik_tekstowy-1|Komunikat testowy" in tekst
    assert "RuntimeError: wyjątek testowy" in tekst


def test_kontekst_szczegolowy_usuwa_uchwyt_po_wyjsciu(tmp_path: Path) -> None:
    logger = logging.getLogger("gnb.projekt.proj-xyz")
    liczba_przed = len(logger.handlers)
    with DziennikSzczegolowy(tmp_path / "log.txt", "proj-xyz"):
        assert len(logger.handlers) == liczba_przed + 1
    assert len(logger.handlers) == liczba_przed
