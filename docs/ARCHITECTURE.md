# Architektura — stan po etapie pierwszym

Ten dokument opisuje wyłącznie to, co faktycznie istnieje w repozytorium po
zakończeniu etapu pierwszego. Pełny docelowy podział na pakiety opisuje sekcja
szósta `CLAUDE.md`.

## Potok przetwarzania

Punkt wejścia to funkcja `przetworz_projekt` w `gnb/potok.py`. Uruchamia ona
etapy w stałej kolejności z sekcji ósmej `CLAUDE.md`, w części obsługiwanej przez
etap pierwszy:

1. Wejście i walidacja — `gnb/ingestion/wejscie.py`.
2. Import treści i wykrycie kodowania — `gnb/normalization/kodowanie.py`.
3. Ekstrakcja — `gnb/extractors/`.
4. Normalizacja i liczenie słów — `gnb/normalization/normalizacja.py`,
   `gnb/core/liczenie_slow.py`.
5. Klasyfikacja TXT kontra MD — `gnb/output/regula_md.py`.
6. Zapis plików wynikowych — `gnb/output/zapis.py`.
7. Manifest — `gnb/output/manifest.py`.
8. Checkpoint — `gnb/persistence/checkpoint.py`.
9. Raport końcowy — `gnb/output/raport.py`.

Etapy deduplikacji, kondensacji i grupowania są pominięte, ale ich miejsce
w kolejności jest zachowane. Jedno uszkodzone wejście nie zatrzymuje pozostałych;
kończy się kontrolowanym błędem zapisanym w logu, manifeście i raporcie.

## Pakiet gnb.core

- `gnb/core/model.py` — siedem kontraktów danych z sekcji siódmej `CLAUDE.md`.
- `gnb/core/stale.py` — wyliczenia używane przez model danych.
- `gnb/core/wyjatki.py` — taksonomia wyjątków z sekcji siódmej `CLAUDE.md`.
- `gnb/core/konfiguracja.py` — wczytywanie konfiguracji z wartości domyślnych,
  pliku TOML i zmiennych środowiskowych z prefiksem `GNB_`. Zakres pól opisuje
  `docs/CONFIGURATION.md`.
- `gnb/core/liczenie_slow.py` — jedna wspólna definicja liczenia słów i znaków.
- `gnb/core/identyfikatory.py` — sumy kontrolne SHA-256 oraz stabilny
  identyfikator źródła w postaci prefiksu typu i pierwszych szesnastu znaków
  sumy kontrolnej pochodzenia.
- `gnb/core/nazwy.py` — sanityzacja nazw projektów i plików do postaci
  bezpiecznej dla Windows oraz budowa nazwy pliku wynikowego z trzonu tytułu
  i skrótu identyfikatora źródła. Zasadę opisuje `docs/FORMATS.md`.

## Pakiet gnb.ingestion

- `gnb/ingestion/wejscie.py` — przyjmowanie tekstu wklejonego oraz plików,
  walidacja i utworzenie `Zrodlo`. Wskazówka formatu jest przenoszona w osobnej
  strukturze `PozycjaWejsciowa`, poza kontraktem `WejscieSurowe`.

## Pakiet gnb.extractors

- `gnb/extractors/bazowy.py` — protokół `Ekstraktor` oraz rejestr dobierający
  ekstraktor po typie źródła i formacie. Nowy format to nowa implementacja
  protokołu plus wpis w rejestrze.
- `gnb/extractors/tekst.py` — tekst płaski, zawsze niski poziom pewności
  struktury, brak bloków.
- `gnb/extractors/markdown.py` — Markdown przez `markdown-it-py` z regułą tabel,
  wysoki poziom pewności, rozpoznane bloki strukturalne.

## Pakiet gnb.normalization

- `gnb/normalization/kodowanie.py` — wykrywanie kodowania i dekodowanie bajtów.
- `gnb/normalization/normalizacja.py` — końce wierszy, NFC, białe znaki, puste
  wiersze, plus budowa `DokumentZnormalizowany` z licznikami.

## Pakiet gnb.output

- `gnb/output/regula_md.py` — deterministyczna reguła wyboru między TXT a MD.
- `gnb/output/zapis.py` — zapis TXT zawsze, MD warunkowo, w UTF-8 bez BOM z LF.
- `gnb/output/manifest.py` — `manifest.json` jako źródło prawdy i `manifest.txt`
  jako czytelny widok.
- `gnb/output/raport.py` — raport końcowy jako zwykły tekst.

## Pakiet gnb.persistence

- `gnb/persistence/projekt.py` — układ katalogów projektu: materiały źródłowe,
  wyniki pośrednie, pliki wynikowe, logi, manifest, checkpoint.
- `gnb/persistence/checkpoint.py` — `checkpoint.json` z zapisem atomowym przez
  plik tymczasowy i `os.replace`, z jedną kopią zapasową. Po restarcie źródła
  ze statusem końcowym nie są przetwarzane ponownie.

## Pakiet gnb.logging_pl

- `gnb/logging_pl/dziennik.py` — `log_wazne.txt` w formacie
  `ZDARZENIE|Godzina:Minuta` z wierszem daty `--- RRRR-MM-DD (czas lokalny) ---`
  na początku dnia i po uruchomieniu, oraz `log_szczegolowy.txt` na module
  `logging`. Log ważny jest prowadzony w czasie lokalnym systemu, ponieważ czyta
  go użytkownik. Log szczegółowy, manifest i checkpoint są prowadzone w czasie
  UTC jako dane techniczne.

## Wiersz poleceń

`gnb/cli.py` udostępnia dwa polecenia. `diagnostyka` sprawdza narzędzia
zewnętrzne. `przetworz` uruchamia potok dla tekstu wklejonego oraz plików TXT
i MD, z opcjami `--projekt`, `--plik`, `--tekst`, `--tekst-md`, `--katalog`.

## Pozostałe pakiety

Pakiety `gnb.deduplication`, `gnb.packing`, `gnb.documents`, `gnb.audio`,
`gnb.images`, `gnb.music`, `gnb.ui`, `gnb.hotkeys` istnieją jako puste,
importowalne pakiety z docstringiem. Logika powstanie w kolejnych etapach.

## Testy

Testy jednostkowe i integracyjne pokrywają każdy moduł etapu pierwszego. Test
`tests/test_potok_e2e.py` przeprowadza pełny przebieg dla pliku strukturalnego
MD, pliku TXT, pliku w kodowaniu Windows-1250 i tekstu wklejonego, sprawdza
regułę wyboru formatu oraz to, że wznowienie z checkpointu nie duplikuje ani nie
gubi źródeł. Żaden test etapu pierwszego nie korzysta z sieci.
