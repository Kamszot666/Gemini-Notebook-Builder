"""Odczyt zaznaczonych plików w aktywnym oknie Eksploratora przez Shell.Application.

Wiązanie z obiektem COM ``Shell.Application`` jest późne i dynamiczne —
``comtypes.client.CreateObject(..., dynamic=True)`` — zgodnie z decyzją
przyjętą w planie etapu jedenastego: w odróżnieniu od UI Automation
w ``_automatyzacja.py``, gdzie typowane wiązanie jest praktycznie konieczne ze
względu na złożone sygnatury interfejsu, ``Shell.Application`` jest zwykłym
obiektem IDispatch, więc wczesne generowanie typowanego wrappera nie wnosi tu
nic poza kolejnym lokalnie budowanym artefaktem.

Moduł jest importowalny na każdym systemie; cała jego zawartość leży za
sprawdzeniem ``sys.platform == "win32"`` z tego samego powodu co w
``_win32.py`` i ``_automatyzacja.py``.

Obiekt ``Shell.Application`` jest tworzony od nowa przy każdym wywołaniu
``odczytaj_zaznaczenie``, w wątku, który go używa — celowo, z tego samego
powodu co w ``_automatyzacja.py``: wskaźnik COM utworzony w jednym wątku nie
jest bezpieczny do użycia w innym bez marshalingu, a naciśnięcie skrótu jest
obsługiwane w nowym wątku roboczym przy każdym naciśnięciu. Wołający
w ``obsluga.py`` inicjuje COM w tym wątku przed wywołaniem tej funkcji.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    from pathlib import Path

    import comtypes.client

    def odczytaj_zaznaczenie(uchwyt: int) -> tuple[Path, ...]:
        """Zwraca zaznaczone elementy okna Eksploratora o podanym uchwycie.

        Zwraca krotkę pustą, gdy żadne otwarte okno powłoki nie odpowiada temu
        uchwytowi albo gdy nic w nim nie jest zaznaczone. Pusta krotka jest tu
        normalnym wynikiem, nie błędem — ``rozpoznanie.py`` sam decyduje, czy
        to porażka.
        """
        try:
            powloka = comtypes.client.CreateObject("Shell.Application", dynamic=True)
            okna = powloka.Windows()
        except (comtypes.COMError, OSError):
            return ()

        for indeks in range(okna.Count):
            try:
                okno = okna.Item(indeks)
                if int(okno.HWND) != uchwyt:
                    continue
                zaznaczone = okno.Document.SelectedItems()
                return tuple(
                    Path(str(zaznaczone.Item(pozycja).Path)) for pozycja in range(zaznaczone.Count)
                )
            except (comtypes.COMError, AttributeError, OSError):
                continue
        return ()
