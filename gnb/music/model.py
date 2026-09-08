"""Model opisu materiału nutowego oraz zamiana opisu na dokument wyekstrahowany.

`OpisPartytury` jest wspólnym wynikiem trzech parserów: MIDI, MusicXML i Guitar
Pro. Każdy parser wypełnia tyle pól, ile potrafi odczytać z pliku, a nieznane
zostawia jako `None` albo pustą listę. Nigdy nie wstawiamy wartości zastępczej,
na przykład zera albo słowa „brak”, bo taka wartość byłaby nieodróżnialna od
danych rzeczywistych.

Funkcja `opis_jako_tekst` buduje z opisu czytelny liniowo tekst po polsku, bez
znaczników Markdown, który trafia do notatnika. Funkcja `opis_jako_metadane`
buduje z tego samego opisu słownik napisów do manifestu. Funkcja
`zbuduj_dokument_wyekstrahowany` jest wspólnym finałem czterech adapterów
ekstrakcji: składa `DokumentWyekstrahowany` z twardo ustawionym niskim poziomem
pewności struktury, żeby reguła generowania Markdown nie utworzyła wersji MD
z opisu, który prozą nie jest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury

# Nazwy formatów źródłowych do wyświetlenia w opisie tekstowym. Klucz jest
# wartością pola `OpisPartytury.format_zrodlowy`.
_NAZWY_FORMATOW: dict[str, str] = {
    "midi": "MIDI",
    "musicxml": "MusicXML",
    "mxl": "MusicXML (skompresowany kontener MXL)",
    "gp3": "Guitar Pro 3",
    "gp4": "Guitar Pro 4",
    "gp5": "Guitar Pro 5",
}

_KONCOWY_AKAPIT = (
    "Ten opis powstał z automatycznego odczytu pliku i może być niepełny. Nie "
    "jest podglądem partytury — do notatnika trafia tylko ten opis, ponieważ "
    "notatnik nie czyta zapisu nutowego."
)

_ADNOTACJA_PRZYBLIZENIA = "wartość przybliżona, wyliczona z długości nagrania MIDI w czasie"


@dataclass(slots=True)
class OpisPartytury:
    """Zestaw informacji o materiale nutowym odczytany z pliku źródłowego.

    Świadomie nie ma tu pola „poziom pewności odczytu”. Dla formatu natywnego
    odczyt jest albo dokładny, albo go nie ma: pojedyncze fakty niosą własną
    uczciwość — liczba taktów z MIDI jest oznaczona jako przybliżona, zmiany
    metrum czy tempa dają ostrzeżenie, przyjęcie trybu durowego jest odnotowane,
    a wiersza brakującego pola po prostu nie ma. Jedna zbiorcza ocena pewności
    dublowałaby to nierzetelnie. Pole poziomu pewności rozpoznania jest
    zarezerwowane dla wartości zwracanej przez program Audiveris w części B
    etapu dziesiątego, gdzie jest to prawdziwa wielkość statystyczna.

    Pole `ostrzezenia_zmian` niesie sytuacje, w których plik zmienia metrum,
    tempo albo tonację, a opis podaje wartość początkową. Trafiają one do pola
    ostrzeżeń `DokumentWyekstrahowany`, a stąd do manifestu i do sekcji
    „Materiały do sprawdzenia” raportu. Pole `uwagi_odczytu` niesie łagodniejsze
    założenia interpretacyjne, na przykład przyjęcie trybu durowego przy braku
    oznaczenia w pliku; te trafiają do tekstu opisu i do metadanych, ale nie do
    sekcji „Materiały do sprawdzenia”.
    """

    format_zrodlowy: str
    metoda_odczytu: str
    tytul: str | None = None
    tonacja: str | None = None
    metrum: str | None = None
    tempo_bpm: int | None = None
    liczba_taktow: int | None = None
    liczba_taktow_przyblizona: bool = False
    instrumenty: list[str] = field(default_factory=list)
    struktura_czesci: list[str] = field(default_factory=list)
    ostrzezenia_zmian: list[str] = field(default_factory=list)
    uwagi_odczytu: list[str] = field(default_factory=list)


def _nazwa_formatu(format_zrodlowy: str) -> str:
    """Zwraca nazwę formatu do wyświetlenia, awaryjnie sam kod formatu."""
    return _NAZWY_FORMATOW.get(format_zrodlowy, format_zrodlowy)


def _opis_liczby_taktow(opis: OpisPartytury) -> str | None:
    """Buduje opis liczby taktów z adnotacją o przybliżeniu, gdy trzeba."""
    if opis.liczba_taktow is None:
        return None
    if opis.liczba_taktow_przyblizona:
        return f"{opis.liczba_taktow} ({_ADNOTACJA_PRZYBLIZENIA})"
    return str(opis.liczba_taktow)


def opis_jako_tekst(opis: OpisPartytury) -> str:
    """Buduje czytelny liniowo opis materiału nutowego jako zwykły tekst.

    Wiersz o polu nieznanym jest pomijany w całości, a nie zapisywany jako „nie
    odczytano”. Sekcje listowe pojawiają się tylko wtedy, gdy mają zawartość.
    Ostatni akapit jest zawsze, bo sekcja siedemnasta CLAUDE.md zabrania
    deklarowania stuprocentowej poprawności rozpoznania.
    """
    wiersze: list[str] = [
        f"Materiał nutowy: {opis.tytul}" if opis.tytul else "Materiał nutowy bez tytułu",
        f"Format źródłowy: {_nazwa_formatu(opis.format_zrodlowy)}",
    ]
    if opis.tonacja:
        wiersze.append(f"Tonacja: {opis.tonacja}")
    if opis.metrum:
        wiersze.append(f"Metrum: {opis.metrum}")
    if opis.tempo_bpm is not None:
        wiersze.append(f"Tempo: {opis.tempo_bpm} uderzeń na minutę")
    opis_taktow = _opis_liczby_taktow(opis)
    if opis_taktow is not None:
        wiersze.append(f"Liczba taktów: {opis_taktow}")
    if opis.instrumenty:
        wiersze.append(f"Instrumenty: {', '.join(opis.instrumenty)}")

    if opis.struktura_czesci:
        wiersze.append("")
        wiersze.append("Struktura części:")
        wiersze.extend(f"  - {czesc}" for czesc in opis.struktura_czesci)

    if opis.ostrzezenia_zmian:
        wiersze.append("")
        wiersze.append("Ostrzeżenia odczytu:")
        wiersze.extend(f"  - {ostrzezenie}" for ostrzezenie in opis.ostrzezenia_zmian)

    if opis.uwagi_odczytu:
        wiersze.append("")
        wiersze.append("Uwagi odczytu:")
        wiersze.extend(f"  - {uwaga}" for uwaga in opis.uwagi_odczytu)

    wiersze.append("")
    wiersze.append(_KONCOWY_AKAPIT)
    return "\n".join(wiersze)


def opis_jako_metadane(opis: OpisPartytury) -> dict[str, str]:
    """Buduje słownik metadanych źródła z opisu materiału nutowego.

    Klucz pojawia się tylko wtedy, gdy odpowiadające pole jest znane. Wszystkie
    wartości są napisami, bo `StanZrodla.metadane` to `dict[str, str]`.
    Zgodnie z sekcją czternastą CLAUDE.md manifest jest źródłem prawdy, a proza
    należy do widoku i do opisu, więc liczba taktów trafia tu jako sama liczba,
    a informacja o przybliżeniu jako osobny klucz `nuty_liczba_taktow_przyblizona`
    o wartości „tak” albo „nie”. Zdanie wyjaśniające jest wyłącznie w tekście opisu.
    """
    metadane: dict[str, str] = {
        "nuty_format": opis.format_zrodlowy,
        "nuty_metoda_odczytu": opis.metoda_odczytu,
    }
    if opis.tytul:
        metadane["nuty_tytul"] = opis.tytul
    if opis.tonacja:
        metadane["nuty_tonacja"] = opis.tonacja
    if opis.metrum:
        metadane["nuty_metrum"] = opis.metrum
    if opis.tempo_bpm is not None:
        metadane["nuty_tempo_bpm"] = str(opis.tempo_bpm)
    if opis.liczba_taktow is not None:
        metadane["nuty_liczba_taktow"] = str(opis.liczba_taktow)
        metadane["nuty_liczba_taktow_przyblizona"] = (
            "tak" if opis.liczba_taktow_przyblizona else "nie"
        )
    if opis.instrumenty:
        metadane["nuty_instrumenty"] = ", ".join(opis.instrumenty)
    if opis.struktura_czesci:
        metadane["nuty_struktura_czesci"] = "; ".join(opis.struktura_czesci)
    if opis.ostrzezenia_zmian:
        metadane["nuty_zmiany"] = " | ".join(opis.ostrzezenia_zmian)
    if opis.uwagi_odczytu:
        metadane["nuty_uwagi_odczytu"] = " | ".join(opis.uwagi_odczytu)
    return metadane


def zbuduj_dokument_wyekstrahowany(
    identyfikator_zrodla: str, opis: OpisPartytury, *, metoda_ekstrakcji: str
) -> DokumentWyekstrahowany:
    """Składa `DokumentWyekstrahowany` z opisu materiału nutowego.

    Poziom pewności struktury jest twardo niski: opis nutowy nie ma nagłówków,
    list ani tabel, więc reguła z sekcji ósmej CLAUDE.md nie ma tworzyć wersji
    Markdown. Ostrzeżenia o zmianach metrum, tempa i tonacji przechodzą do pola
    ostrzeżeń dokumentu, skąd potok kieruje je do manifestu i raportu.
    """
    return DokumentWyekstrahowany(
        identyfikator_zrodla=identyfikator_zrodla,
        tekst=opis_jako_tekst(opis),
        poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
        metoda_ekstrakcji=metoda_ekstrakcji,
        tytul=opis.tytul,
        metadane=opis_jako_metadane(opis),
        ostrzezenia=list(opis.ostrzezenia_zmian),
    )
