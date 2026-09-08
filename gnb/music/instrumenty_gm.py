"""Nazwy instrumentów według standardu General MIDI, po polsku.

Standard General MIDI przypisuje 128 barw instrumentów numerom programu oraz
osobną mapę instrumentów perkusyjnych numerom nut na kanale dziesiątym. Ten
moduł tłumaczy jedno i drugie na czytelne nazwy polskie, potrzebne do opisu
tekstowego materiału nutowego.

Uwaga o numeracji. Publikowana specyfikacja General MIDI numeruje instrumenty od
jedynki, ale w samym pliku MIDI oraz w bibliotekach odczytu numer programu jest
liczony od zera. Tablica `INSTRUMENTY_GM` jest indeksowana od zera, zgodnie
z danymi w pliku. Pomyłka o jeden zamieniłaby na przykład gitarę akustyczną
nylonową na stalową bez żadnego widocznego objawu, więc jest to błąd cichej
utraty poprawności danych, przed którym ostrzega sekcja czwarta CLAUDE.md.
"""

from __future__ import annotations

# Numer programu General MIDI liczony od zera odwzorowany na polską nazwę barwy.
# Kolejność i grupowanie po osiem odpowiadają rodzinom brzmień ze specyfikacji
# General MIDI Level 1.
INSTRUMENTY_GM: dict[int, str] = {
    0: "fortepian koncertowy",
    1: "fortepian jasny",
    2: "fortepian elektryczny (grand)",
    3: "pianino honky-tonk",
    4: "pianino elektryczne 1",
    5: "pianino elektryczne 2",
    6: "klawesyn",
    7: "klawinet",
    8: "czelesta",
    9: "dzwonki",
    10: "pozytywka",
    11: "wibrafon",
    12: "marimba",
    13: "ksylofon",
    14: "dzwony rurowe",
    15: "cymbały",
    16: "organy elektroniczne (drawbar)",
    17: "organy perkusyjne",
    18: "organy rockowe",
    19: "organy kościelne",
    20: "fisharmonia",
    21: "akordeon",
    22: "harmonijka ustna",
    23: "bandoneon",
    24: "gitara akustyczna (struny nylonowe)",
    25: "gitara akustyczna (struny stalowe)",
    26: "gitara elektryczna (jazz)",
    27: "gitara elektryczna (czysta)",
    28: "gitara elektryczna (tłumiona)",
    29: "gitara elektryczna (overdrive)",
    30: "gitara elektryczna (przester)",
    31: "flażolety gitarowe",
    32: "kontrabas (akustyczny bas)",
    33: "gitara basowa (palcami)",
    34: "gitara basowa (kostką)",
    35: "gitara basowa bezprogowa",
    36: "gitara basowa slap 1",
    37: "gitara basowa slap 2",
    38: "bas syntezatorowy 1",
    39: "bas syntezatorowy 2",
    40: "skrzypce",
    41: "altówka",
    42: "wiolonczela",
    43: "kontrabas smyczkowy",
    44: "smyczki tremolo",
    45: "smyczki pizzicato",
    46: "harfa",
    47: "kotły",
    48: "zespół smyczkowy 1",
    49: "zespół smyczkowy 2",
    50: "smyczki syntezatorowe 1",
    51: "smyczki syntezatorowe 2",
    52: "chór (śpiew na „a”)",
    53: "głos (śpiew na „o”)",
    54: "głos syntezatorowy",
    55: "uderzenie orkiestry",
    56: "trąbka",
    57: "puzon",
    58: "tuba",
    59: "trąbka tłumiona",
    60: "waltornia",
    61: "sekcja dęta blaszana",
    62: "dęte blaszane syntezatorowe 1",
    63: "dęte blaszane syntezatorowe 2",
    64: "saksofon sopranowy",
    65: "saksofon altowy",
    66: "saksofon tenorowy",
    67: "saksofon barytonowy",
    68: "obój",
    69: "rożek angielski",
    70: "fagot",
    71: "klarnet",
    72: "flet piccolo",
    73: "flet poprzeczny",
    74: "flet prosty",
    75: "flet Pana",
    76: "dęcie w butelkę",
    77: "shakuhachi",
    78: "gwizd",
    79: "okaryna",
    80: "solo syntezatorowe (fala prostokątna)",
    81: "solo syntezatorowe (fala piłokształtna)",
    82: "solo syntezatorowe (calliope)",
    83: "solo syntezatorowe (chiff)",
    84: "solo syntezatorowe (charang)",
    85: "solo syntezatorowe (głos)",
    86: "solo syntezatorowe (kwinty)",
    87: "solo syntezatorowe (bas i solo)",
    88: "tło syntezatorowe (new age)",
    89: "tło syntezatorowe (ciepłe)",
    90: "tło syntezatorowe (polysynth)",
    91: "tło syntezatorowe (chór)",
    92: "tło syntezatorowe (smyczkowe)",
    93: "tło syntezatorowe (metaliczne)",
    94: "tło syntezatorowe (halo)",
    95: "tło syntezatorowe (sweep)",
    96: "efekt syntezatorowy (deszcz)",
    97: "efekt syntezatorowy (ścieżka filmowa)",
    98: "efekt syntezatorowy (kryształ)",
    99: "efekt syntezatorowy (atmosfera)",
    100: "efekt syntezatorowy (jasność)",
    101: "efekt syntezatorowy (gobliny)",
    102: "efekt syntezatorowy (echa)",
    103: "efekt syntezatorowy (sci-fi)",
    104: "sitar",
    105: "banjo",
    106: "shamisen",
    107: "koto",
    108: "kalimba",
    109: "dudy",
    110: "skrzypce ludowe",
    111: "shanai",
    112: "dzwoneczek",
    113: "agogo",
    114: "steel drum",
    115: "drewniany bloczek",
    116: "bęben taiko",
    117: "tom melodyczny",
    118: "bęben syntezatorowy",
    119: "talerz odwrócony",
    120: "szum progów gitary",
    121: "oddech",
    122: "brzeg morza",
    123: "ćwierkanie ptaka",
    124: "dzwonek telefonu",
    125: "helikopter",
    126: "brawa",
    127: "wystrzał",
}

# Instrument perkusyjny General MIDI odwzorowany z numeru nuty na kanale
# dziesiątym. Zakres numerów nut to 35 do 81 włącznie.
PERKUSJA_GM_KLAWISZE: dict[int, str] = {
    35: "bęben basowy akustyczny",
    36: "bęben basowy 1",
    37: "rimshot (uderzenie w obręcz werbla)",
    38: "werbel akustyczny",
    39: "klaśnięcie",
    40: "werbel elektryczny",
    41: "tom podłogowy niski",
    42: "hi-hat zamknięty",
    43: "tom podłogowy wysoki",
    44: "hi-hat pedałowy",
    45: "tom niski",
    46: "hi-hat otwarty",
    47: "tom nisko-średni",
    48: "tom wysoko-średni",
    49: "talerz crash 1",
    50: "tom wysoki",
    51: "talerz ride 1",
    52: "talerz chiński",
    53: "kopułka talerza ride",
    54: "tamburyn",
    55: "talerz splash",
    56: "dzwonek krowi (cowbell)",
    57: "talerz crash 2",
    58: "vibraslap",
    59: "talerz ride 2",
    60: "bongo wysokie",
    61: "bongo niskie",
    62: "konga wysoka tłumiona",
    63: "konga wysoka otwarta",
    64: "konga niska",
    65: "timbale wysokie",
    66: "timbale niskie",
    67: "agogo wysokie",
    68: "agogo niskie",
    69: "cabasa",
    70: "marakasy",
    71: "gwizdek krótki",
    72: "gwizdek długi",
    73: "guiro krótkie",
    74: "guiro długie",
    75: "klawesy",
    76: "bloczek drewniany wysoki",
    77: "bloczek drewniany niski",
    78: "cuica tłumiona",
    79: "cuica otwarta",
    80: "trójkąt tłumiony",
    81: "trójkąt otwarty",
}

NAZWA_ZESTAWU_PERKUSYJNEGO = "zestaw perkusyjny"


def nazwa_instrumentu(numer_programu: int, *, perkusja: bool = False) -> str:
    """Zwraca polską nazwę barwy dla numeru programu General MIDI.

    Argument `perkusja` ustawiony na prawdę oznacza kanał dziesiąty, na którym
    numer programu nie wybiera barwy melodycznej, tylko zestaw perkusyjny —
    wynikiem jest wtedy zawsze stała `NAZWA_ZESTAWU_PERKUSYJNEGO`. Numer spoza
    zakresu 0 do 127 nie jest błędem danych wejściowych, tylko brakiem
    odwzorowania, więc funkcja zwraca opis zastępczy, a nie zgłasza wyjątku.
    """
    if perkusja:
        return NAZWA_ZESTAWU_PERKUSYJNEGO
    nazwa = INSTRUMENTY_GM.get(numer_programu)
    if nazwa is not None:
        return nazwa
    return f"instrument nr {numer_programu}"


def nazwa_klawisza_perkusji(numer_nuty: int) -> str:
    """Zwraca polską nazwę instrumentu perkusyjnego dla numeru nuty kanału dziesiątego.

    Numer nuty spoza mapy General MIDI dostaje opis zastępczy zamiast wyjątku,
    ponieważ pojedynczy nietypowy dźwięk perkusji nie może zatrzymać opisu całego
    materiału.
    """
    nazwa = PERKUSJA_GM_KLAWISZE.get(numer_nuty)
    if nazwa is not None:
        return nazwa
    return f"element perkusji nr {numer_nuty}"
