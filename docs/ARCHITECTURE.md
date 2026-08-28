# Architektura — stan po etapie trzecim

Ten dokument opisuje wyłącznie to, co faktycznie istnieje w repozytorium po
zakończeniu etapu trzeciego. Pełny docelowy podział na pakiety opisuje sekcja
szósta `CLAUDE.md`.

## Potok przetwarzania

Punkt wejścia to funkcja `przetworz_projekt` w `gnb/potok.py`. Uruchamia ona
etapy w stałej kolejności z sekcji ósmej `CLAUDE.md`, w części obsługiwanej przez
etapy pierwszy, drugi i trzeci:

1. Wejście i walidacja — `gnb/ingestion/wejscie.py`, `gnb/ingestion/lista_url.py`.
2. Pobranie stron i napisów oraz import treści i wykrycie kodowania —
   `gnb/ingestion/pobieranie.py`, `gnb/ingestion/youtube.py`,
   `gnb/normalization/kodowanie.py`.
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

Pobranie adresów oraz pobranie napisów są osobnymi fazami, wykonywanymi przed
pętlą po źródłach. Strony pobierają się równolegle, a filmy po kolei, ponieważ
biblioteki napisów pracują synchronicznie i same wykonują swoje żądania.

Pobranie adresów jest osobną fazą, wykonywaną przed pętlą po źródłach. Dzięki
temu strony pobierają się równolegle, z zachowaniem limitu połączeń na domenę
i odstępu między żądaniami, a reszta potoku pozostaje synchroniczna. Adres, który
w checkpoincie ma już status końcowy, nie jest pobierany ponownie, ponieważ jego
identyfikator wynika z kanonicznej postaci adresu, a nie z treści.

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
- `gnb/core/url.py` — walidacja adresu oraz jego dwie postacie: kanoniczna jako
  klucz tożsamości i pobierania jako to, co trafia do serwera.
- `gnb/core/youtube.py` — rozpoznanie adresu filmu, sprowadzenie wszystkich jego
  postaci do jednego adresu kanonicznego oraz odrzucanie playlist i kanałów.
- `gnb/core/nazwy.py` — sanityzacja nazw projektów i plików do postaci
  bezpiecznej dla Windows oraz budowa nazwy pliku wynikowego z trzonu tytułu
  i skrótu identyfikatora źródła. Zasadę opisuje `docs/FORMATS.md`.

## Pakiet gnb.ingestion

- `gnb/ingestion/wejscie.py` — przyjmowanie tekstu wklejonego, plików i adresów,
  walidacja i utworzenie `Zrodlo`. Wskazówka formatu jest przenoszona w osobnej
  strukturze `PozycjaWejsciowa`, poza kontraktem `WejscieSurowe`.
- `gnb/ingestion/lista_url.py` — przyjmowanie list adresów, wykrywanie duplikatów
  po postaci kanonicznej i podsumowanie pokazywane przed pobraniem.
- `gnb/ingestion/pobieranie.py` — asynchroniczny klient HTTP z limitem czasu,
  ponowieniami, rosnącym odstępem, limitem połączeń na domenę i obsługą pamięci
  podręcznej.
- `gnb/ingestion/youtube.py` — pobieranie napisów dwiema wzajemnie zapasowymi
  warstwami oraz metadanych filmu, wraz z zapisem wyniku do pamięci podręcznej.

Wzajemna zastępowalność warstw dotyczy wyłącznie samych napisów. Metadanych
filmu, czyli tytułu, kanału, długości i daty publikacji, nie udostępnia
`youtube-transcript-api`, więc pochodzą one zawsze z `yt-dlp`. Oznacza to, że
`yt-dlp` nie jest warstwą zapasową, tylko zależnością twardą dla pełnej obsługi
serwisu YouTube i nie da się go po prostu wyłączyć. Bez niego film nadal dostanie
transkrypcję, ale bez tytułu, kanału i długości, a więc i bez sensownej nazwy
pliku wynikowego.
- `gnb/ingestion/robots.py` — odczyt pliku `robots.txt` i decyzja o zgodzie na
  pobranie adresu, zgodnie z RFC 9309: 2xx oznacza reguły, 4xx zgodę, a 5xx
  i błąd sieci zakaz po wyczerpaniu ponowień.

## Pakiet gnb.extractors

- `gnb/extractors/bazowy.py` — protokół `Ekstraktor` oraz rejestr dobierający
  ekstraktor po typie źródła i formacie. Nowy format to nowa implementacja
  protokołu plus wpis w rejestrze.
- `gnb/extractors/tekst.py` — tekst płaski, zawsze niski poziom pewności
  struktury, brak bloków.
- `gnb/extractors/markdown.py` — Markdown przez `markdown-it-py` z regułą tabel,
  wysoki poziom pewności, rozpoznane bloki strukturalne.
- `gnb/extractors/youtube.py` — sklejanie segmentów napisów w akapity, usuwanie
  oznaczeń dźwięków i powtórzeń oraz opcjonalne znaczniki czasu.
- `gnb/extractors/strona_www.py` — treść artykułu przez `trafilatura`, średni
  poziom pewności, z mechanizmem zapasowym na `lxml` o niskim poziomie pewności.
  Zbiera też odnośniki zewnętrzne i dopisuje na końcu treści ich ponumerowany
  wykaz, a w samym zdaniu zostawia sam tekst odnośnika.

## Pakiet gnb.normalization

- `gnb/normalization/kodowanie.py` — wykrywanie kodowania i dekodowanie bajtów.
- `gnb/normalization/normalizacja.py` — końce wierszy, NFC, białe znaki, puste
  wiersze, plus budowa `DokumentZnormalizowany` z licznikami.

## Pakiet gnb.output

- `gnb/output/regula_md.py` — deterministyczna reguła wyboru między TXT a MD.
- `gnb/output/zapis.py` — zapis TXT zawsze, MD warunkowo, w UTF-8 bez BOM z LF.
- `gnb/output/tekst_bez_znacznikow.py` — przepisanie Markdown na czysty tekst
  z zachowaną strukturą, używane do wersji TXT źródeł markdownowych.
- `gnb/output/manifest.py` — `manifest.json` jako źródło prawdy i `manifest.txt`
  jako czytelny widok.
- `gnb/output/raport.py` — raport końcowy jako zwykły tekst, wraz z wykazem
  źródeł pominiętych i błędnych oraz powodem każdego z nich.

## Pakiet gnb.persistence

- `gnb/persistence/projekt.py` — układ katalogów projektu, z nazwą katalogu
  wyznaczaną z nazwy podanej przez użytkownika, a w jej braku z pierwszego źródła:
  materiały źródłowe,
  wyniki pośrednie, pliki wynikowe, logi, manifest, checkpoint.
- `gnb/persistence/cache.py` — wspólna dla projektów pamięć podręczna pobranych
  zasobów, oparta na SQLite, z trybem WAL i numerem wersji schematu.
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

`gnb/cli.py` udostępnia trzy polecenia. `diagnostyka` sprawdza narzędzia
zewnętrzne. `przetworz` uruchamia potok dla tekstu wklejonego, plików TXT i MD
oraz adresów stron, z opcjami `--projekt`, `--plik`, `--tekst`, `--tekst-md`,
`--url`, `--lista-url`, `--sprawdz-liste` i `--katalog`. `pamiec` pokazuje stan
wspólnej pamięci podręcznej i pozwala ją wyczyścić.

## Pozostałe pakiety

Pakiety `gnb.deduplication`, `gnb.packing`, `gnb.documents`, `gnb.audio`,
`gnb.images`, `gnb.music`, `gnb.ui`, `gnb.hotkeys` istnieją jako puste,
importowalne pakiety z docstringiem. Logika powstanie w kolejnych etapach.

## Testy

Testy jednostkowe i integracyjne pokrywają każdy moduł etapów pierwszego
i drugiego. Test `tests/test_potok_e2e.py` przeprowadza pełny przebieg dla pliku
strukturalnego MD, pliku TXT, pliku w kodowaniu Windows-1250 i tekstu wklejonego.
Test `tests/test_potok_youtube_e2e.py` przeprowadza pełny przebieg dla filmów,
w tym pominięcie playlisty i kanału, brak napisów, film prywatny, znaczniki
czasu, wznowienie bez ponownego pobrania oraz oszczędność dzięki pamięci
podręcznej. Warstwy pobierania napisów są w nim podstawione danymi sztucznymi.

Test `tests/test_potok_url_e2e.py` przeprowadza pełny przebieg dla adresów stron,
w tym pominięcie zakazane przez `robots.txt`, błąd 404, zasób innego typu,
wznowienie bez ponownego pobrania oraz oszczędność pobrania dzięki pamięci
podręcznej.

Testy są zbierane w trybie importu `importlib`, ustawionym w `pyproject.toml`.
Dzięki temu pliki testowe o tej samej nazwie mogą leżeć w różnych katalogach,
na przykład `tests/core/test_youtube.py` obok `tests/ingestion/test_youtube.py`.
W domyślnym trybie takie pliki zderzają się przy zbieraniu testów.

Testy kanaryjne w `tests/test_youtube_kanaryjny.py` są jedynymi, które sięgają do
prawdziwego serwisu. Mają marker `siec`, są domyślnie wyłączone i sprawdzają
wyłącznie to, czy każda z dwóch warstw pobierania nadal się przebija. Poza nimi
żaden test nie korzysta z sieci. Pobieranie jest sprawdzane na sztucznym
transporcie `httpx.MockTransport`, a odstępy i ponowienia na podstawionym
usypiaczu, więc testy są deterministyczne i nie czekają naprawdę. Ewentualne
testy sieciowe mają dostać marker `siec`, domyślnie wyłączony.
