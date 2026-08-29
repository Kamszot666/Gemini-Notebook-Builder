# Architektura — stan po etapie piątym

Ten dokument opisuje wyłącznie to, co faktycznie istnieje w repozytorium po
zakończeniu etapu piątego. Pełny docelowy podział na pakiety opisuje sekcja
szósta `CLAUDE.md`.

## Potok przetwarzania

Punkt wejścia to funkcja `przetworz_projekt` w `gnb/potok.py`. Uruchamia ona
etapy w stałej kolejności z sekcji ósmej `CLAUDE.md`, w części obsługiwanej przez
etapy od pierwszego do piątego:

1. Wejście i walidacja — `gnb/ingestion/wejscie.py`, `gnb/ingestion/lista_url.py`.
2. Pobranie stron i napisów oraz import treści i wykrycie kodowania —
   `gnb/ingestion/pobieranie.py`, `gnb/ingestion/youtube.py`,
   `gnb/normalization/kodowanie.py`.
3. Ekstrakcja — `gnb/extractors/`.
4. Normalizacja i liczenie słów — `gnb/normalization/normalizacja.py`,
   `gnb/core/liczenie_slow.py`.
5. Klasyfikacja TXT kontra MD — `gnb/output/regula_md.py`.
6. Deduplikacja — `gnb/deduplication/`.
7. Zapis plików wynikowych — `gnb/output/zapis.py`.
8. Manifest — `gnb/output/manifest.py`.
9. Checkpoint — `gnb/persistence/checkpoint.py`.
10. Raport końcowy — `gnb/output/raport.py`.

Etapy kondensacji i grupowania tematycznego są pominięte, ale ich miejsce
w kolejności jest zachowane. Jedno uszkodzone wejście nie zatrzymuje pozostałych;
kończy się kontrolowanym błędem zapisanym w logu, manifeście i raporcie.

### Podział na fazy przez deduplikację

Deduplikacja porównuje wszystkie źródła naraz, więc potok jest podzielony na trzy
fazy w `_Wykonanie`:

1. Faza normalizacji — dla każdego wejścia po kolei: pobranie lub import,
   ekstrakcja, normalizacja, ocena jakości, reguła MD. Znormalizowany tekst trafia
   do podkatalogu `wyniki_posrednie`, a źródło dostaje status `znormalizowane`.
   Plik wynikowy jeszcze nie powstaje.
2. Faza deduplikacji — `deduplikuj` zestawia znormalizowane teksty, oznacza pewne
   duplikaty statusem `duplikat`, a pary o średnim podobieństwie zostawia w całości
   i wpisuje do materiałów do sprawdzenia. Decyzje trafiają do checkpointu,
   manifestu i raportu. Faza wykonuje się raz, co zapisuje znacznik
   `deduplikacja.wykonana` w checkpoincie.
3. Faza zapisu — dla każdego źródła, które przeżyło deduplikację, powstają pliki
   wynikowe TXT i warunkowo MD, a status zmienia się na `spakowane`.

Ten podział jest też podziałem wznowienia: przerwanie w trakcie deduplikacji albo
zapisu nie wymaga ponownej ekstrakcji, bo znormalizowany tekst jest już na dysku.

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
  strukturze `PozycjaWejsciowa`, poza kontraktem `WejscieSurowe`. Format pliku
  decyduje o typie źródła — tekstowy dla TXT i MD, dokument dla pozostałych
  siedmiu — oraz o tym, czy plik wymaga odczytu bajtów zamiast dekodowania
  tekstu (`czy_format_binarny`, dla PDF, DOCX i EPUB).
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

- `gnb/extractors/bazowy.py` — protokół `Ekstraktor` z rejestrem
  `RejestrEkstraktorow` dla formatów tekstowych oraz protokół `EkstraktorBinarny`
  z rejestrem `RejestrEkstraktorowBinarnych` dla PDF, DOCX i EPUB, pracujący
  wprost na bajtach pliku. Nowy format to nowa implementacja właściwego
  protokołu plus wpis we właściwym rejestrze.
- `gnb/extractors/tekst.py` — tekst płaski, zawsze niski poziom pewności
  struktury, brak bloków.
- `gnb/extractors/markdown.py` — Markdown przez `markdown-it-py` z regułą tabel,
  wysoki poziom pewności, rozpoznane bloki strukturalne.
- `gnb/extractors/napisy_wspolne.py` — wspólne sklejanie segmentów napisów
  w akapity: usuwanie oznaczeń dźwięków i powtórzeń oraz opcjonalne znaczniki
  czasu. Używane przez ekstraktor YouTube oraz ekstraktor plików SRT i VTT.
- `gnb/extractors/youtube.py` — wycinanie stopki tłumaczy z napisów tworzonych
  ręcznie oraz zbieranie metadanych filmu, na bazie napisy_wspolne.
- `gnb/extractors/napisy.py` — ekstraktor plików SRT i VTT: dzieli plik na
  bloki rozdzielone pustym wierszem, a blok bez linii ze znacznikiem czasu
  pomija w całości, co usuwa nagłówek WEBVTT oraz bloki NOTE, STYLE i REGION.
- `gnb/extractors/strona_www.py` — treść artykułu przez `trafilatura`, średni
  poziom pewności, z mechanizmem zapasowym na `lxml` o niskim poziomie pewności.
  Zbiera też odnośniki zewnętrzne i dopisuje na końcu treści ich ponumerowany
  wykaz, a w samym zdaniu zostawia sam tekst odnośnika. Ten sam ekstraktor
  obsługuje też plik HTML lokalny, bez wykrywania stron wymagających skryptów.
- `gnb/extractors/bloki_markdown.py` — zapis listy bloków treści jako tekstu
  w zapisie Markdown, wspólny dla strony internetowej, CSV, DOCX i EPUB.
- `gnb/extractors/plik_csv.py` — plik CSV jako jeden blok tabeli, z automatycznym
  rozpoznaniem ogranicznika kolumn i pierwszym wierszem jako nagłówkiem.
- `gnb/extractors/plik_pdf.py` — tekst z warstwy tekstowej PDF przez `pypdf`,
  z usuwaniem pozycyjnie wykrytego powtarzalnego nagłówka i numeru strony.
  Zawsze niski poziom pewności struktury, bez bloków.
- `gnb/extractors/plik_docx.py` — akapity i tabele DOCX w kolejności
  wystąpienia przez `python-docx`, ze stylem akapitu odwzorowanym wprost na
  rodzaj bloku. Wysoki poziom pewności struktury.
- `gnb/extractors/plik_epub.py` — rozdziały EPUB w kolejności `spine` przez
  `EbookLib`, z pominięciem dokumentu nawigacyjnego i rekurencyjnym wejściem
  w kontenery `div`, `section` i `article`. Wysoki poziom pewności struktury.
- `gnb/extractors/dane_strukturalne.py` — odczyt metadanych artykułu z bloku
  JSON-LD strony oraz scalanie ich z metadanymi ekstraktora, z zachowaniem obu
  wartości przy rozbieżności.

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
- `gnb/output/ocena_jakosci.py` — heurystyczna ocena jakości ekstrakcji dla
  źródeł rozpoznawanych: stron, filmów, PDF, DOCX, EPUB i HTML lokalnego.
  Zwraca ocenę wraz z listą powodów i nigdy nie usuwa źródła.
- `gnb/output/raport.py` — raport końcowy jako zwykły tekst, wraz z wykazem
  źródeł pominiętych i błędnych oraz powodem każdego z nich, a także z sekcją
  „Materiały do sprawdzenia” dla źródeł o podejrzanym wyniku ekstrakcji, źródeł
  z ostrzeżeniem ekstraktora oraz źródeł, które deduplikacja uznała za możliwy
  duplikat i zostawiła do rozstrzygnięcia.

## Pakiet gnb.deduplication

Wieloetapowa deduplikacja z sekcji szesnastej `CLAUDE.md`. Wejściem jest lista
`ZrodloDoDeduplikacji` ze znormalizowanym tekstem, wyjściem `WynikDeduplikacjiZbioru`:
lista decyzji `DecyzjaDeduplikacji` wraz z podziałem źródeł na pewne duplikaty
i pary do rozstrzygnięcia. Źródła są porównywane w stałej kolejności rosnących
identyfikatorów, więc wynik jest powtarzalny między uruchomieniami.

- `gnb/deduplication/hasze.py` — etap pierwszy i drugi: suma kontrolna
  znormalizowanego tekstu oraz suma kontrolna tekstu sprowadzonego do samych liter
  i cyfr, która pomija różnice w interpunkcji, odstępach i wielkości liter.
- `gnb/deduplication/simhash.py` — etap trzeci: SimHash na zachodzących na siebie
  trójkach słów, z powtarzalną funkcją skrótu `blake2b`, oraz porównanie
  sekwencyjne z `difflib` dla tekstów krótszych niż próg słów krótkiego tekstu,
  gdzie SimHash jest niestabilny.
- `gnb/deduplication/orkiestrator.py` — łączy etapy, stosuje progi pewnego
  duplikatu i rozstrzygnięcia, buduje audytowalne decyzje. Etap embeddingów
  lokalnych nie jest realizowany; jest domyślnie wyłączony i poza zakresem etapu
  piątego. Pole zachowanych fragmentów unikalnych w tym zakresie pozostaje puste,
  co wyjaśnia sekcja osiemnasta e `CLAUDE.md`.

## Pakiet gnb.persistence

- `gnb/persistence/projekt.py` — układ katalogów projektu, z nazwą katalogu
  wyznaczaną z nazwy podanej przez użytkownika, a w jej braku z pierwszego źródła:
  materiały źródłowe, wyniki pośrednie, pliki wynikowe, logi, manifest, checkpoint.
  Podkatalog `wyniki_posrednie` trzyma znormalizowany tekst każdego źródła
  zapisany w fazie normalizacji, dzięki czemu wznowienie po deduplikacji nie
  wymaga ponownej ekstrakcji.
- `gnb/persistence/cache.py` — wspólna dla projektów pamięć podręczna pobranych
  zasobów, oparta na SQLite, z trybem WAL i numerem wersji schematu.
- `gnb/persistence/checkpoint.py` — `checkpoint.json` z zapisem atomowym przez
  plik tymczasowy i `os.replace`, z jedną kopią zapasową. Po restarcie źródła
  ze statusem końcowym nie są przetwarzane ponownie. Odczyt rozgałęzia się po
  numerze wersji schematu i migruje dane starszej wersji przed budową obiektów,
  więc katalog projektu założony poprzednią wersją aplikacji nadal daje się
  wznowić. Plik w wersji nowszej niż obsługiwana, plik bez numeru wersji oraz plik
  bez spodziewanego pola kończą się błędem trwałym z komunikatem po polsku,
  a nie surowym śladem stosu. Stan deduplikacji, nagłówek metadanych źródła oraz
  wskazanie źródła głównego duplikatu są polami addytywnymi z bezpieczną wartością
  domyślną, więc plik starszej wersji wczytuje się bez zmiany numeru schematu.

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

Pakiety `gnb.packing`, `gnb.documents`, `gnb.audio`, `gnb.images`, `gnb.music`,
`gnb.ui`, `gnb.hotkeys` istnieją jako puste, importowalne pakiety z docstringiem.
Logika powstanie w kolejnych etapach.

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

Test `tests/test_potok_deduplikacja_e2e.py` przeprowadza pełny przebieg dla
deduplikacji: pewny duplikat znika z wyników i zwalnia slot, para o średnim
podobieństwie zostaje w całości wraz z akapitem unikalnym i trafia do materiałów
do sprawdzenia, wznowienie nie zmienia decyzji ani plików, a wyłączenie wszystkich
etapów w konfiguracji realnie zatrzymuje deduplikację. Testy pakietu
`gnb.deduplication` są w `tests/deduplication/`.

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
