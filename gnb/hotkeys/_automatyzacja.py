"""Odczyt paska adresu przeglądarki przez UI Automation, bez symulowania klawiszy.

Moduł jest importowalny na każdym systemie z tego samego powodu co
``_win32.py`` — cała jego zawartość leży za sprawdzeniem
``sys.platform == "win32"``, żeby ``python -m mypy gnb --platform linux``
pomijał gałąź zależną od biblioteki comtypes, która na Linuksie się nie
zainstaluje.

Dopasowanie paska adresu odbywa się po nazwie klasy kontrolki, nie po
lokalizowanej nazwie elementu: lokalizowana nazwa („Pasek adresu i
wyszukiwania” w polskim Chrome) zmienia się wraz z językiem interfejsu
przeglądarki, a nazwa klasy — nie. Obie nazwy klas sprawdzono bezpośrednio
w Chrome i w Firefoksie na komputerze użytkownika, a nie zgadnięto z pamięci,
zgodnie z zaleceniem sekcji dwunastej CLAUDE.md.

Import ``comtypes.client.GetModule("UIAutomationCore.dll")`` generuje przy
pierwszym użyciu plik ``comtypes/gen/UIAutomationClient.py`` — zwykły,
tekstowy kod Pythona wczytywany przez podpisany interpreter, nie żadną nową
bibliotekę natywną, więc reguła kontroli aplikacji Windows z sekcji 18d
CLAUDE.md tu nie ma zastosowania.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import comtypes.client

    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as UIA  # noqa: E402

    # Nazwy klas kontrolki paska adresu, sprawdzone bezpośrednio w obu
    # przeglądarkach. Dopasowanie jest przez zawieranie, nie przez równość, bo
    # Firefox dokłada do klasy dodatkowe, niestabilne sufiksy.
    _KLASY_PASKA_ADRESU = ("OmniboxViewViews", "urlbar-input")

    _automatyzacja = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)

    def odczytaj_pasek_adresu(uchwyt: int) -> str | None:
        """Zwraca wartość paska adresu albo ``None``, gdy nie dało się jej odczytać.

        Różnica między pustym paskiem a nieudanym odczytem jest tu istotna dla
        wywołującego w ``rozpoznanie.py``: to dwie różne sytuacje, patrz sekcja
        dwunasta CLAUDE.md o zaznaczeniu, zastosowana analogicznie do adresu.
        """
        try:
            element = _automatyzacja.ElementFromHandle(uchwyt)
            warunek = _automatyzacja.CreatePropertyCondition(
                UIA.UIA_IsValuePatternAvailablePropertyId, True
            )
            znalezione = element.FindAll(UIA.TreeScope_Descendants, warunek)
        except comtypes.COMError:
            return None

        for indeks in range(znalezione.Length):
            try:
                kandydat = znalezione.GetElement(indeks)
                klasa = kandydat.CurrentClassName or ""
                if not any(fragment in klasa for fragment in _KLASY_PASKA_ADRESU):
                    continue
                wzorzec = kandydat.GetCurrentPattern(UIA.UIA_ValuePatternId)
                if wzorzec is None:
                    continue
                wzorzec_wartosci = wzorzec.QueryInterface(UIA.IUIAutomationValuePattern)
                return str(wzorzec_wartosci.CurrentValue)
            except comtypes.COMError:
                continue
        return None
