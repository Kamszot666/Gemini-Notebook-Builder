# Architektura — stan po etapie dziewiątym

Ten dokument opisuje wyłącznie to, co faktycznie istnieje w repozytorium po
zakończeniu etapu dziewiątego. Pełny docelowy podział na pakiety opisuje sekcja
szósta `CLAUDE.md`.

## Potok przetwarzania

Punkt wejścia to funkcja `przetworz_projekt` w `gnb/potok.py`. Wywołuje ją
zarówno wiersz poleceń, jak i interfejs WWW. Uruchamia ona etapy w stałej
kolejności z sekcji ósmej `CLAUDE.md`, w części obsługiwanej przez etapy od
pierwszego do szóstego:

1. Wejście i walidacja — `gnb/ingestion/wejscie.py`, `gnb/ingestion/lista_url.py`.
2. Pobranie stron i napisów oraz import treści i wykrycie kodowania —
   `gnb/ingestion/pobieranie.py`, `gnb/ingestion/youtube.py`,
   `gnb/normalization/kodowanie.py`.
3. Ekstrakcja — `gnb/extractors/`.
4. Normalizacja i liczenie słów — `gnb/normalization/normalizacja.py`,
   `gnb/core/liczenie_slow.py`.
5. Klasyfikacja TXT kontra MD — `gnb/output/regula_md.py`.
6. Deduplikacja — `gnb/deduplication/`.
7. Pakowanie: podział źródeł zbyt dużych i łączenie małych źródeł grup —
   `gnb/packing/`.
8. Zapis plików wynikowych — `gnb/output/zapis.py`, `gnb/output/skladanie.py`.
9. Manifest — `gnb/output/manifest.py`.
10. Checkpoint — `gnb/persistence/checkpoint.py`.
11. Raport końcowy — `gnb/output/raport.py`.

Etap kondensacji jest pominięty, ale jego miejsce w kolejności jest zachowane.
Grupowanie tematyczne działa wyłącznie według jawnej nazwy grupy nadanej przez
użytkownika; bez nazwy każde źródło dostaje własny plik. Jedno uszkodzone wejście
nie zatrzymuje pozostałych; kończy się kontrolowanym błędem zapisanym w logu,
manifeście i raporcie.

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
3. Faza pakowania i zapisu — dla każdego źródła, które przeżyło deduplikację:
   źródło mieszczące się w limicie i bez nazwy grupy dostaje jeden plik TXT
   i warunkowo MD; źródło przekraczające bezpieczny limit słów albo rozmiaru
   jest dzielone na ponumerowane części, każdą w osobnym pliku TXT; źródła z tą
   samą nazwą grupy są łączone w możliwie najmniej wspólnych plików TXT,
   z nagłówkiem metadanych przed treścią każdego fragmentu. Po zapisaniu status
   źródła zmienia się na `spakowane`. Grupa dostaje ten status jednym zapisem
   checkpointu, więc przerwanie w połowie planuje ją od nowa.

Ten podział jest też podziałem wznowienia: przerwanie w trakcie deduplikacji albo
pakowania nie wymaga ponownej ekstrakcji, bo znormalizowany tekst jest już na
dysku.

Pobranie adresów oraz pobranie napisów są osobnymi fazami, wykonywanymi przed
pętlą po źródłach. Strony pobierają się równolegle, a filmy po kolei, ponieważ
biblioteki napisów pracują synchronicznie i same wykonują swoje żądania.

Pobranie adresów jest osobną fazą, wykonywaną przed pętlą po źródłach. Dzięki
temu strony pobierają się równolegle, z zachowaniem limitu połączeń na domenę
i odstępu między żądaniami, a reszta potoku pozostaje synchroniczna. Adres, który
w checkpoincie ma już status końcowy, nie jest pobierany ponownie, ponieważ jego
identyfikator wynika z kanonicznej postaci adresu, a nie z treści.

### Lista wejść, wznowienie i postęp

`przetworz_projekt` zapisuje wejścia bieżącego uruchomienia do pola `wejscia`
checkpointu, rozróżniając je po parze rodzaju i wartości, więc ponowne podanie
tego samego źródła nie mnoży wpisów. Funkcja `odtworz_wejscia` odbudowuje z tej
listy `PozycjaWejsciowa` przez te same funkcje `przyjmij_plik`, `przyjmij_tekst`
i `przyjmij_url`, więc interfejs WWW wznawia projekt bez pytania użytkownika
o źródła. Sekcja czternasta punkt trzeci `CLAUDE.md` wymagała listy wejść od
początku; dodano ją jako pole addytywne z pustą listą domyślną, bez zmiany
numeru schematu.

`przetworz_projekt` przyjmuje też opcjonalny argument `postep`: wywołanie
zwrotne z modułu `gnb/core/postep.py`, wołane na granicach faz oraz po każdym
przetworzonym źródle z obiektem `ZdarzeniePostepu`. Faza `FazaPotoku.OCR` jest
zgłaszana wewnątrz ekstrakcji, dla skanu PDF strona po stronie, a faza
`FazaPotoku.TRANSKRYPCJA` wewnątrz ekstrakcji nagrania mowy, z licznikiem
w minutach nagrania, bo transkrypcja godzinnego nagrania trwa około godziny.
Dzięki temu użytkownik nie zostaje przy niemym oknie. Wiersz poleceń też podaje
tu wywołanie zwrotne, ale wypisuje wyłącznie dławione wiersze faz OCR
i transkrypcji, bez pasków postępu. Dławienie pozostałych zdarzeń jest po
stronie odbiorcy, nie potoku.

`przetworz_projekt` przyjmuje ponadto flagę `wymus_transkrypcje`, która
przełamuje odrzucenie nagrania rozpoznanego jako niemowne. W wierszu poleceń
ustawia ją opcja `--wymus-transkrypcje`.

## Pakiet gnb.core

- `gnb/core/model.py` — siedem kontraktów danych z sekcji siódmej `CLAUDE.md`.
- `gnb/core/stale.py` — wyliczenia używane przez model danych.
- `gnb/core/wyjatki.py` — taksonomia wyjątków z sekcji siódmej `CLAUDE.md`.
- `gnb/core/konfiguracja.py` — wczytywanie konfiguracji z wartości domyślnych,
  pliku TOML i zmiennych środowiskowych z prefiksem `GNB_`. Zakres pól opisuje
  `docs/CONFIGURATION.md`.
- `gnb/core/liczenie_slow.py` — jedna wspólna definicja liczenia słów i znaków.
- `gnb/core/postep.py` — typ `ZdarzeniePostepu` i wyliczenie faz potoku. Osobny
  moduł, żeby pakiet interfejsu nie importował całego potoku dla samego typu.
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
  z rejestrem `RejestrEkstraktorowBinarnych` dla PDF, DOCX, EPUB, obrazów
  i nagrań audio, pracujący wprost na bajtach pliku. Metoda `wyekstrahuj`
  protokołu binarnego przyjmuje opcjonalne wywołanie zwrotne postępu, którym
  ekstraktor PDF zgłasza OCR skanu strona po stronie, a ekstraktor audio
  transkrypcję segment po segmencie. Nowy format to nowa implementacja
  właściwego protokołu plus wpis we właściwym rejestrze; rejestr binarny
  dostaje ustawienia OCR oraz transkrypcji z konfiguracji.
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
  Przy braku warstwy tekstowej i włączonym OCR rasteryzuje strony przez
  `gnb.images.rasteryzacja` i rozpoznaje je przez `gnb.images.tesseract`,
  składając wynik z nagłówkiem „Strona N:” przed każdą stroną. Zawsze niski
  poziom pewności struktury, bez bloków.
- `gnb/extractors/plik_obraz.py` — opis merytoryczny obrazu przez
  `gnb.images.opis` oraz, przy włączonym OCR, tekst rozpoznany przez
  `gnb.images.tesseract`, z oceną jakości OCR z `gnb.images.ocena_ocr`.
  Obsługuje JPG, PNG, WebP, TIFF, BMP, statyczny GIF oraz — z biblioteką
  opcjonalną pillow-heif — HEIC i HEIF. Zawsze niski poziom pewności struktury.
- `gnb/extractors/plik_audio.py` — transkrypcja nagrania mowy: dekodowanie
  FFmpegiem przez `gnb.audio.dekodowanie`, pomiar udziału mowy przez
  `gnb.audio.wykrywanie_mowy`, odrzucenie materiału niemownego wyjątkiem
  `PominietoZrodlo`, transkrypcja przez `gnb.audio.transkrypcja` i ocena
  halucynacji przez `gnb.audio.ocena`. Obsługuje MP3, WAV, M4A, FLAC, OGG,
  OPUS i AAC. Zawsze niski poziom pewności struktury.
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
  Funkcja `zapisz_plik_pakietu` zapisuje gotowy plik części albo pliku grupy w
  formacie TXT, a `zapisz_plik_pdf` zapisuje gotowe bajty tematycznego pliku PDF
  grupy obrazów.
- `gnb/output/skladanie.py` — składanie treści jednego pliku z fragmentów wraz
  z nagłówkiem metadanych przed każdym oraz z wierszem „Kolejny fragment tego
  pliku:” między nimi.
- `gnb/output/tekst_bez_znacznikow.py` — przepisanie Markdown na czysty tekst
  z zachowaną strukturą, używane do wersji TXT źródeł markdownowych.
- `gnb/output/manifest.py` — `manifest.json` jako źródło prawdy i `manifest.txt`
  jako czytelny widok. Plik grupy jest w manifeście liczony raz, a jego wpis
  wymienia wszystkie źródła w nim zawarte.
- `gnb/output/ocena_jakosci.py` — heurystyczna ocena jakości ekstrakcji dla
  źródeł rozpoznawanych: stron, filmów, PDF, DOCX, EPUB i HTML lokalnego.
  Zwraca ocenę wraz z listą powodów i nigdy nie usuwa źródła.
- `gnb/output/raport.py` — raport końcowy jako zwykły tekst, wraz z wykazem
  źródeł pominiętych i błędnych oraz powodem każdego z nich, a także z sekcją
  „Materiały do sprawdzenia” dla źródeł o podejrzanym wyniku ekstrakcji, źródeł
  z ostrzeżeniem ekstraktora, źródeł z ostrzeżeniem podziału oraz źródeł, które
  deduplikacja uznała za możliwy duplikat i zostawiła do rozstrzygnięcia.
  Wykorzystanie limitu źródeł jest liczone po sumie plików TXT i tematycznych
  plików PDF, bo to one zajmują sloty notatnika, a nie po odrębnych materiałach
  źródłowych.

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

## Pakiet gnb.packing

Podział źródeł zbyt dużych i łączenie małych źródeł grup, zawsze po deduplikacji.
Pakiet nie dotyka dysku ani nie buduje nagłówków metadanych — decyduje wyłącznie,
które źródła trafią do którego pliku i w jakiej postaci treści.

- `gnb/packing/limity.py` — dwa limity treści traktowane niezależnie: liczba słów
  liczona wspólną definicją z `gnb/core/liczenie_slow.py` oraz rozmiar w bajtach
  kodowania UTF-8. Trzecie ograniczenie z sekcji dziewiątej `CLAUDE.md`, liczba
  źródeł, dotyczy całego notatnika i jest pilnowane w potoku.
- `gnb/packing/podzial.py` — podział jednej treści przekraczającej limit na
  możliwie najmniejszą liczbę części. Granica podziału wypada jak najwyżej
  w hierarchii: blok rozdzielony pustym wierszem, potem wiersz, potem zdanie,
  a w ostateczności granica słowa. Cięcie na granicy słowa, czyli wewnątrz
  zdania, dokłada ostrzeżenie kierowane do manifestu i raportu. Liczniki słów
  i bajtów są sumowane przyrostowo, więc podział źródła o setkach tysięcy słów
  bez akapitów nie ma złożoności kwadratowej.
- `gnb/packing/pakowanie.py` — planowanie plików grupy: źródło samo przekraczające
  limit trafia do własnych plików-części, pozostałe są dokładane po kolei do
  bieżącego pliku grupy, a przekroczenie któregokolwiek limitu zamyka plik
  i otwiera następny, numerowany jak część.

Kryterium grupowania w tym etapie to jawne przypisanie przez użytkownika. Bez
embeddingów i bez interfejsu żadne automatyczne kryterium tematyczne nie jest
dostępne, a łączenie po samym typie źródła byłoby łączeniem przypadkowym,
zakazanym w sekcji dziesiątej `CLAUDE.md`. Przypisanie per źródło z interfejsu
jest zadaniem etapu siódmego.

## Pakiet gnb.persistence

- `gnb/persistence/projekt.py` — układ katalogów projektu, z nazwą katalogu
  wyznaczaną z nazwy podanej przez użytkownika, a w jej braku z pierwszego źródła:
  materiały źródłowe, wyniki pośrednie, pliki wynikowe, pliki wysłane przez
  interfejs, logi, manifest, checkpoint oraz plik `pola_notatnika.json`.
  Podkatalog `wyniki_posrednie` trzyma znormalizowany tekst każdego źródła
  zapisany w fazie normalizacji, dzięki czemu wznowienie po deduplikacji nie
  wymaga ponownej ekstrakcji. Podkatalog `pliki_wejsciowe` powstaje leniwie,
  dopiero przy pierwszej wysyłce pliku przez interfejs.
- `gnb/persistence/pola_notatnika.py` — trwałe przechowywanie dwóch pól
  tekstowych notatnika, instrukcji systemowej i promptu wyszukiwania, w pliku
  `pola_notatnika.json` w katalogu projektu, zapisem atomowym tym samym wzorcem
  co checkpoint. To osobny plik, a nie pole checkpointu, bo treść pól nie jest
  stanem potoku i nie ma wpływu na wznowienie.
- `gnb/persistence/cache.py` — wspólna dla projektów pamięć podręczna pobranych
  zasobów, oparta na SQLite, z trybem WAL i numerem wersji schematu.
- `gnb/persistence/checkpoint.py` — `checkpoint.json` z zapisem atomowym przez
  plik tymczasowy i `os.replace`, z jedną kopią zapasową. Po restarcie źródła
  ze statusem końcowym nie są przetwarzane ponownie. Odczyt rozgałęzia się po
  numerze wersji schematu i migruje dane starszej wersji przed budową obiektów,
  więc katalog projektu założony poprzednią wersją aplikacji nadal daje się
  wznowić. Plik w wersji nowszej niż obsługiwana, plik bez numeru wersji oraz plik
  bez spodziewanego pola kończą się błędem trwałym z komunikatem po polsku,
  a nie surowym śladem stosu. Stan deduplikacji, nagłówek metadanych źródła,
  wskazanie źródła głównego duplikatu, nazwa grupy pakowania, ostrzeżenia
  podziału, numer i liczba części pliku wynikowego oraz lista wejść projektu są
  polami addytywnymi z bezpieczną wartością domyślną, więc plik starszej wersji
  wczytuje się bez zmiany numeru schematu.

## Pakiet gnb.logging_pl

- `gnb/logging_pl/dziennik.py` — `log_wazne.txt` w formacie
  `ZDARZENIE|Godzina:Minuta` z wierszem daty `--- RRRR-MM-DD (czas lokalny) ---`
  na początku dnia i po uruchomieniu, oraz `log_szczegolowy.txt` na module
  `logging`. Log ważny jest prowadzony w czasie lokalnym systemu, ponieważ czyta
  go użytkownik. Log szczegółowy, manifest i checkpoint są prowadzone w czasie
  UTC jako dane techniczne.

## Pakiet gnb.ui

Dostępny interfejs WWW. Serwer nasłuchuje wyłącznie na pętli zwrotnej, bez
zasobów z zewnętrznego serwera. Pakiet nie zawiera logiki przetwarzania: spina
istniejący potok z żądaniem HTTP przez semantyczny, dostępny HTML.

- `gnb/ui/html.py` — jedyne miejsce, przez które przechodzi każdy napis
  pochodzący ze źródła, z nazwy pliku, z komunikatu błędu i z pola użytkownika,
  zanim znajdzie się w odpowiedzi. Sekcja jedenasta punkt drugi `CLAUDE.md`.
- `gnb/ui/csrf.py` — ochrona przez podwójne przesłanie tokenu: token w ciasteczku
  sesji `HttpOnly`, `SameSite=Strict`, oraz ten sam token w ukrytym polu
  formularza, porównywane `secrets.compare_digest`.
- `gnb/ui/formularze.py` — parsowanie ciała żądań. Multipart jest dzielony
  ręcznie po ciągu granicznym, a nie modułem `email`, bo `email` normalizuje
  końce wierszy i uszkodziłby wysłany plik binarny. Zawartość każdej części jest
  odtwarzana bajt w bajt.
- `gnb/ui/postep.py` — `DlawikPostepu`: pierwsze zdarzenie przechodzi od razu,
  kolejne najwyżej raz na cztery sekundy, a komunikat identyczny z widocznym nie
  jest powtarzany. Zdarzenie zakończenia projektu przechodzi zawsze.
- `gnb/ui/zadania.py` — `RejestrZadan`: uruchamia potok w wątku roboczym i trzyma
  stan najwyżej jednego zadania. Drugie żądanie uruchomienia jest odrzucane,
  a nie kolejkowane. Wyjątek w wątku staje się stanem błędu.
- `gnb/ui/projekty.py` — wykrywanie projektów w katalogu wyników i wyróżnianie
  niedokończonych. Uszkodzony checkpoint jednego projektu nie wywraca listy.
- `gnb/ui/widoki.py` — generowanie stron: strona główna z formularzem nowego
  projektu i wykazem projektów do wznowienia, strona projektu z regionem postępu,
  dwoma polami tekstowymi i raportem, strony błędu. Ciemny motyw, style w jednym
  elemencie `style`, dwa krótkie skrypty wbudowane w stronę.
- `gnb/ui/serwer.py` — `ThreadingHTTPServer` z routingiem tablicą tras. Każdy
  POST wymaga zgodnego tokenu CSRF, a po udanym POST serwer przekierowuje kodem
  303. Nieobsłużony wyjątek staje się stroną 500.
- `gnb/ui/server.py` — punkt wejścia `python -m gnb.ui.server`. Nazwa pliku jest
  angielska, bo to część kontraktu komend; logika i komunikaty są po polsku.

## Wiersz poleceń

`gnb/cli.py` udostępnia trzy polecenia. `diagnostyka` sprawdza narzędzia
zewnętrzne. `przetworz` uruchamia potok dla tekstu wklejonego, plików
tekstowych, dokumentowych, obrazów i nagrań mowy oraz adresów stron i filmów,
z opcjami `--projekt`, `--plik`, `--tekst`, `--tekst-md`, `--url`,
`--lista-url`, `--sprawdz-liste`, `--katalog`, `--grupa` oraz
`--wymus-transkrypcje`. Opcja `--grupa` przypisuje wszystkie źródła jednego
wywołania do wspólnej grupy tematycznej pakowania; kolejną grupę w tym samym
projekcie dodaje się osobnym wywołaniem, bo checkpoint kumuluje źródła między
uruchomieniami. Opcja `--wymus-transkrypcje` przełamuje odrzucenie nagrania
rozpoznanego jako niemowne. `pamiec` pokazuje stan wspólnej pamięci podręcznej
i pozwala ją wyczyścić.

## Pakiet gnb.images

Rozpoznawanie tekstu z obrazów i skanów oraz generowanie tematycznych plików
PDF. Pakiet nie zna potoku ani checkpointu — jest zbiorem narzędzi wołanych
przez ekstraktory i przez fazę pakowania.

- `gnb/images/tesseract.py` — odnajdywanie pliku wykonywalnego Tesseracta oraz
  wołanie go przez podproces: obraz PNG standardowym wejściem, tekst standardowym
  wyjściem. `rozpoznaj_wiele` uruchamia procesy Tesseracta równolegle, zachowując
  kolejność wejścia i zgłaszając postęp po każdym gotowym obrazie. Każdy OCR to
  osobny proces systemowy, zgodnie z sekcją piętnastą `CLAUDE.md`.
- `gnb/images/rasteryzacja.py` — renderowanie stron pliku PDF do obrazów PNG
  przez `pypdfium2`, w rozdzielczości z konfiguracji. Strony renderowane po
  kolei, bo PDFium nie jest bezpieczny wątkowo.
- `gnb/images/ocena_ocr.py` — ocena jakości tekstu z OCR: „poprawna”, „pusta”
  albo „podejrzana”, z listą powodów.
- `gnb/images/opis.py` — składanie opisu merytorycznego obrazu wyłącznie z
  dostępnego materiału tekstowego, nigdy przez zewnętrzną usługę. Brak materiału
  daje jawny komunikat, a nie pusty ciąg.
- `gnb/images/pdf_tematyczny.py` — budowanie pliku PDF grupy obrazów przez
  `reportlab`, z osadzoną czcionką DejaVuSans z katalogu `gnb/images/czcionki`.
  Opis obrazu jest zwykłym tekstem akapitu, a nie tagiem alt, bo reportlab w tym
  trybie nie tworzy struktury dostępności PDF.

## Pakiet gnb.audio

Transkrypcja nagrań mowy oraz odrzucanie materiału niemownego. Pakiet nie zna
potoku ani checkpointu — jest zbiorem narzędzi wołanych przez ekstraktor audio.

- `gnb/audio/dekodowanie.py` — rozkodowanie dowolnego nagrania przez podproces
  FFmpeg do fali 16 kHz mono float32. Nagranie trafia do FFmpega jako plik
  tymczasowy, bo kontenery MP4 i M4A trzymają nagłówek na końcu pliku i wymagają
  wejścia, po którym można się przemieszczać. Brak FFmpega kończy się
  `BrakNarzedzia`.
- `gnb/audio/transkrypcja.py` — adapter biblioteki faster-whisper. Strażnik
  atrapy modułu `av` wstawia puste atrapy do `sys.modules` wyłącznie wtedy, gdy
  prawdziwy import PyAV zawiedzie, i zapisuje powód — Inteligentne sterowanie
  aplikacjami Windows blokuje niepodpisane biblioteki natywne PyAV. Do biblioteki
  trafia tablica NumPy, nigdy ścieżka pliku, więc dekoder PyAV nie jest wołany.
  Model jest zapamiętywany między wywołaniami. Liczba wątków dobierana jak
  procesy OCR: rdzenie minus jeden, z powodu dostępnościowego.
- `gnb/audio/wykrywanie_mowy.py` — pomiar udziału mowy filtrem Silero wbudowanym
  w faster-whisper oraz decyzja o odrzuceniu nagrania niemownego przed
  transkrypcją. Heurystyka, nie klasyfikator muzyki.
- `gnb/audio/ocena.py` — obrona przed halucynacjami Whispera: powtórzona fraza
  i wysoki udział segmentów niskiej pewności dają ocenę „podejrzana”, a źródło
  trafia do sekcji „Materiały do sprawdzenia”.

## Pozostałe pakiety

Pakiety `gnb.documents`, `gnb.music`, `gnb.hotkeys` istnieją jako puste,
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

Test `tests/test_potok_deduplikacja_e2e.py` przeprowadza pełny przebieg dla
deduplikacji: pewny duplikat znika z wyników i zwalnia slot, para o średnim
podobieństwie zostaje w całości wraz z akapitem unikalnym i trafia do materiałów
do sprawdzenia, wznowienie nie zmienia decyzji ani plików, a wyłączenie wszystkich
etapów w konfiguracji realnie zatrzymuje deduplikację. Testy pakietu
`gnb.deduplication` są w `tests/deduplication/`.

Test `tests/test_potok_pakowanie_e2e.py` przeprowadza pełny przebieg dla
pakowania: małe źródła jednej grupy łączą się w jeden plik bez utraty treści
i z nagłówkiem przed każdym fragmentem, grupa zbyt liczna dzieli się na kolejne
pliki, wznowienie nie zmienia plików, a źródło bez grupy zostaje osobno obok
grupy. Test `tests/test_potok_e2e.py` sprawdza dodatkowo, że źródło przekraczające
bezpieczny limit słów jest dzielone na ponumerowane części zamiast pomijane oraz
że duży plik binarny nadal jest odrzucany przy wejściu. Testy pakietu
`gnb.packing` są w `tests/packing/`.

Testy są zbierane w trybie importu `importlib`, ustawionym w `pyproject.toml`.
Dzięki temu pliki testowe o tej samej nazwie mogą leżeć w różnych katalogach,
na przykład `tests/core/test_youtube.py` obok `tests/ingestion/test_youtube.py`.
W domyślnym trybie takie pliki zderzają się przy zbieraniu testów.

Testy pakietu `gnb.ui` są w `tests/ui/`. Pokrywają escapowanie treści ze
źródła, ochronę przed CSRF, parsowanie formularzy wraz z odtworzeniem wysłanego
pliku binarnego bajt w bajt, dławienie komunikatów postępu na podstawionym
zegarze, rejestr zadań w tle, wykrywanie niedokończonych projektów, dostępność
wygenerowanego HTML oraz pełny przebieg przez serwer na losowym porcie pętli
zwrotnej. Test `tests/test_potok_wznowienie_e2e.py` sprawdza zapis listy wejść do
checkpointu, odtworzenie wejść przy wznowieniu bez podania źródeł oraz kolejność
zdarzeń postępu.

Testy kanaryjne w `tests/test_youtube_kanaryjny.py` są jedynymi, które sięgają do
prawdziwego serwisu. Mają marker `siec`, są domyślnie wyłączone i sprawdzają
wyłącznie to, czy każda z dwóch warstw pobierania nadal się przebija. Poza nimi
żaden test nie korzysta z sieci. Pobieranie jest sprawdzane na sztucznym
transporcie `httpx.MockTransport`, a odstępy i ponowienia na podstawionym
usypiaczu, więc testy są deterministyczne i nie czekają naprawdę. Ewentualne
testy sieciowe mają dostać marker `siec`, domyślnie wyłączony.
