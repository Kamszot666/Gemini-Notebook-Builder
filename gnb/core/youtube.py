"""Rozpoznawanie adresów serwisu YouTube i sprowadzanie ich do jednej postaci.

Tożsamość źródła opiera się na identyfikatorze filmu, a nie na pełnym adresie.
Ten sam film podany jako `watch`, `youtu.be`, `shorts`, `live` albo `embed` daje
ten sam adres kanoniczny, czyli jedno źródło. Parametry towarzyszące, w tym
numer playlisty i moment startu, nie wchodzą do postaci kanonicznej, ponieważ
nie zmieniają tego, jaki film jest oglądany.

Playlisty i kanały są rozpoznawane osobno i odrzucane. Rozwinięcie playlisty na
listę filmów łamałoby przewidywalność limitu źródeł notatnika i uruchamiało
masowe pobieranie bez wyraźnego polecenia użytkownika. Komunikat odrzucenia
mówi wprost, co jest nie tak i co zrobić dalej, żeby nie zostawiać użytkownika
z samym stwierdzeniem, że adres jest nieobsługiwany.

Moduł nie łączy się z siecią. Pracuje wyłącznie na napisie adresu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from urllib.parse import parse_qs, urlsplit

HOSTY_YOUTUBE = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtube-nocookie.com",
        "www.youtube-nocookie.com",
    }
)
HOSTY_SKROCONE = frozenset({"youtu.be", "www.youtu.be"})

WZORZEC_IDENTYFIKATORA = re.compile(r"^[A-Za-z0-9_-]{11}$")

# Segmenty ścieżki, po których następuje identyfikator filmu.
_SEGMENTY_FILMU = ("shorts", "live", "embed", "v")

# Segmenty ścieżki wskazujące kanał, a nie film. Nazwa użytkownika poprzedzona
# małpą jest osobnym przypadkiem, bo nie ma przed sobą żadnego segmentu.
_SEGMENTY_KANALU = ("channel", "c", "user")
_SEGMENT_PLAYLISTY = "playlist"

KOMUNIKAT_PLAYLISTA = (
    "Adres wskazuje playlistę, a nie pojedynczy film. Rozwijanie playlist nie jest "
    "obsługiwane. Dodaj do listy źródeł adresy poszczególnych filmów."
)
KOMUNIKAT_KANAL = (
    "Adres wskazuje kanał, a nie pojedynczy film. Pobieranie całych kanałów nie jest "
    "obsługiwane. Dodaj do listy źródeł adresy poszczególnych filmów."
)
KOMUNIKAT_NIEROZPOZNANY = (
    "Adres należy do serwisu YouTube, ale nie wskazuje pojedynczego filmu. "
    "Podaj adres filmu w postaci youtube.com/watch?v=IDENTYFIKATOR albo youtu.be/IDENTYFIKATOR."
)


class RodzajAdresuYouTube(Enum):
    """Rodzaj zasobu, na który wskazuje adres serwisu YouTube."""

    FILM = auto()
    PLAYLISTA = auto()
    KANAL = auto()
    NIEROZPOZNANY = auto()


@dataclass(frozen=True, slots=True)
class AdresYouTube:
    """Wynik rozpoznania adresu serwisu YouTube."""

    rodzaj: RodzajAdresuYouTube
    identyfikator_filmu: str | None = None
    adres_kanoniczny: str | None = None
    powod_odrzucenia: str | None = None

    @property
    def czy_film(self) -> bool:
        """Prawda, gdy adres wskazuje pojedynczy film możliwy do przetworzenia."""
        return self.rodzaj is RodzajAdresuYouTube.FILM


def czy_adres_youtube(adres: str) -> bool:
    """Rozstrzyga, czy adres należy do serwisu YouTube, niezależnie od jego rodzaju."""
    host = (urlsplit(adres.strip()).hostname or "").lower()
    return host in HOSTY_YOUTUBE or host in HOSTY_SKROCONE


def adres_kanoniczny_filmu(identyfikator_filmu: str) -> str:
    """Buduje kanoniczny adres filmu z jego identyfikatora."""
    return f"https://www.youtube.com/watch?v={identyfikator_filmu}"


def rozpoznaj(adres: str) -> AdresYouTube:
    """Rozpoznaje adres YouTube i zwraca jego rodzaj wraz z identyfikatorem filmu.

    Adres filmu z dopisanym numerem playlisty, czyli postać
    ``watch?v=FILM&list=LISTA``, jest zwykłym pojedynczym filmem. Parametr listy
    jest wtedy pomijany, bo wskazuje kontekst odtwarzania, a nie inny materiał.
    """
    czesci = urlsplit(adres.strip())
    host = (czesci.hostname or "").lower()
    segmenty = [segment for segment in czesci.path.split("/") if segment]
    parametry = parse_qs(czesci.query)

    if host in HOSTY_SKROCONE:
        return _z_segmentu_identyfikatora(segmenty[0] if segmenty else "")

    if host not in HOSTY_YOUTUBE:
        return AdresYouTube(
            rodzaj=RodzajAdresuYouTube.NIEROZPOZNANY, powod_odrzucenia=KOMUNIKAT_NIEROZPOZNANY
        )

    if _czy_kanal(segmenty):
        return AdresYouTube(rodzaj=RodzajAdresuYouTube.KANAL, powod_odrzucenia=KOMUNIKAT_KANAL)

    if segmenty and segmenty[0].lower() == _SEGMENT_PLAYLISTY:
        return AdresYouTube(
            rodzaj=RodzajAdresuYouTube.PLAYLISTA, powod_odrzucenia=KOMUNIKAT_PLAYLISTA
        )

    if segmenty and segmenty[0].lower() == "watch":
        return _z_segmentu_identyfikatora(_pierwsza_wartosc(parametry, "v"))

    if len(segmenty) >= 2 and segmenty[0].lower() in _SEGMENTY_FILMU:
        return _z_segmentu_identyfikatora(segmenty[1])

    if not segmenty and "list" in parametry:
        return AdresYouTube(
            rodzaj=RodzajAdresuYouTube.PLAYLISTA, powod_odrzucenia=KOMUNIKAT_PLAYLISTA
        )

    return AdresYouTube(
        rodzaj=RodzajAdresuYouTube.NIEROZPOZNANY, powod_odrzucenia=KOMUNIKAT_NIEROZPOZNANY
    )


def _czy_kanal(segmenty: list[str]) -> bool:
    """Rozstrzyga, czy ścieżka wskazuje kanał, także w wariancie z zakładką.

    Zakładka kanału, na przykład ``/@nazwa/shorts``, jest kanałem, mimo że jej
    ostatni segment nosi tę samą nazwę co ścieżka pojedynczego filmu krótkiego.
    Rozstrzyga położenie: przy filmie segment ``shorts`` jest pierwszy i ma po
    sobie identyfikator, przy kanale występuje po nazwie kanału.
    """
    if not segmenty:
        return False
    pierwszy = segmenty[0]
    if pierwszy.startswith("@"):
        return True
    return pierwszy.lower() in _SEGMENTY_KANALU


def _z_segmentu_identyfikatora(wartosc: str) -> AdresYouTube:
    """Buduje wynik rozpoznania z napisu, który ma być identyfikatorem filmu."""
    identyfikator = wartosc.strip()
    if not WZORZEC_IDENTYFIKATORA.match(identyfikator):
        return AdresYouTube(
            rodzaj=RodzajAdresuYouTube.NIEROZPOZNANY, powod_odrzucenia=KOMUNIKAT_NIEROZPOZNANY
        )
    return AdresYouTube(
        rodzaj=RodzajAdresuYouTube.FILM,
        identyfikator_filmu=identyfikator,
        adres_kanoniczny=adres_kanoniczny_filmu(identyfikator),
    )


def _pierwsza_wartosc(parametry: dict[str, list[str]], nazwa: str) -> str:
    """Zwraca pierwszą wartość parametru zapytania albo napis pusty."""
    wartosci = parametry.get(nazwa)
    return wartosci[0] if wartosci else ""
