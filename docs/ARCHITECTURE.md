# Architektura — stan po etapie zerowym

Ten dokument opisuje wyłącznie to, co faktycznie istnieje w repozytorium po
zakończeniu etapu zerowego. Pełny docelowy podział na pakiety opisuje sekcja
szósta `CLAUDE.md`.

## Pakiet gnb.core

Jedyny pakiet z rzeczywistą logiką w etapie zerowym.

- `gnb/core/model.py` — siedem kontraktów danych z sekcji siódmej CLAUDE.md:
  `WejscieSurowe`, `Zrodlo`, `BlokTresci`, `DokumentWyekstrahowany`,
  `DokumentZnormalizowany`, `DecyzjaDeduplikacji`, `PlikWynikowy`. Wszystkie
  jako dataklasy z adnotacjami typów.
- `gnb/core/stale.py` — wyliczenia używane przez model danych: `TypWejscia`,
  `TypZrodla`, `StatusZrodla`, `RodzajBloku`, `PoziomPewnosciStruktury`,
  `WynikDeduplikacji`, `FormatWynikowy`.
- `gnb/core/wyjatki.py` — taksonomia wyjątków z sekcji siódmej CLAUDE.md:
  `BladPrzejsciowy`, `BladTrwaly`, `FormatNieobslugiwany`, `BrakNarzedzia`,
  `PrzekroczonoLimit`, wspólna podstawa `BladGnb`.

## Wiersz poleceń

`gnb/cli.py` udostępnia polecenie `diagnostyka`, uruchamiane jako
`python -m gnb.cli diagnostyka` albo, po instalacji pakietu, jako
`gnb diagnostyka`. Sprawdza dostępność FFmpeg, Tesseract, LibreOffice
(`soffice`), MuseScore (`mscore` na Linuksie i macOS, `MuseScore4.exe` albo
`MuseScore3.exe` na Windows) oraz Java. Dla każdego brakującego narzędzia
wypisuje, do czego służy i co przestaje działać bez niego. Zawsze kończy się
kodem zero — brak narzędzia opcjonalnego nie jest błędem aplikacji.

## Pozostałe pakiety

Pakiety `gnb.ingestion`, `gnb.extractors`, `gnb.normalization`,
`gnb.deduplication`, `gnb.packing`, `gnb.documents`, `gnb.audio`,
`gnb.images`, `gnb.music`, `gnb.output`, `gnb.ui`, `gnb.hotkeys`,
`gnb.persistence`, `gnb.logging_pl` istnieją na razie wyłącznie jako puste,
importowalne pakiety z docstringiem opisującym docelową odpowiedzialność.
Nie zawierają jeszcze żadnej logiki — powstanie ona w etapach opisanych
w sekcji osiemnastej CLAUDE.md.

## Testy

- `tests/core/test_model.py` — tworzenie każdej struktury danych z poprawnymi
  polami oraz sprawdzenie, że statusy źródła odpowiadają dokładnie liście
  z CLAUDE.md.
- `tests/core/test_wyjatki.py` — każdy wyjątek niesie komunikat po polsku
  i opcjonalny identyfikator źródła.
- `tests/test_diagnostyka.py` — komenda diagnostyki kończy się kodem zero
  i wymienia wszystkie sprawdzane narzędzia niezależnie od tego, czy są
  zainstalowane w środowisku uruchomieniowym.
