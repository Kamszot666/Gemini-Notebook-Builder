# Architektura — stan po etapie czternastym

Ten dokument opisuje wyłącznie to, co faktycznie istnieje w repozytorium po
zakończeniu etapu czternastego. Pełny docelowy podział na pakiety opisuje
sekcja szósta `CLAUDE.md`.

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

Dwa dalsze argumenty `przetworz_projekt` pochodzą z etapu czternastego.
`zastepcze_tresci` odwzorowuje identyfikator źródła na plik, którego treść
podstawia się za wynik ekstrakcji tego źródła; źródło zachowuje identyfikator
i pochodzenie, nie jest pobierane ponownie, a zastąpienie jest bezpieczne,
bo dotychczasowy stan jest zamieniany dopiero po udanej ekstrakcji
i normalizacji. `ponownie_przetwarzaj_usuniete` rozstrzyga, czy źródło
pominięte z powodu ręcznie usuniętego pliku wynikowego jest przetwarzane od
nowa, gdy jego wejście jest wśród podanych: prawda, domyślnie, to ponowne
podanie przez użytkownika, a fałsz, używany przez wznowienie z zapisanych
wejść, zostawia je pominięte. Na początku każdego przebiegu funkcja
`_odnotuj_brakujace_pliki` zamienia źródła z brakującym plikiem TXT albo PDF na
pominięte, a faza pakowania cofa do przepakowania grupy, do których dochodzą
nowe źródła, i po zapisaniu nowych plików usuwa stare.

## Pakiet gnb.core

- `gnb/core/model.py` — siedem kontraktów danych z sekcji siódmej `CLAUDE.md`.
- `gnb/core/stale.py` — wyliczenia używane przez model danych.
- `gnb/core/wyjatki.py` — taksonomia wyjątków z sekcji siódmej `CLAUDE.md`.
  Dysponent w `gnb/potok.py` zamienia `PominietoZrodlo`, `PrzekroczonoLimit`
  oraz `BrakNarzedzia` na status źródła `pominiete`, a pozostałe wyjątki
  `BladGnb` na status `blad`. Brak opcjonalnego narzędzia albo biblioteki
  (FFmpeg, Audiveris, `mido`, `PyGuitarPro`) jest więc pominięciem, nie błędem;
  brak Tesseracta przy OCR obrazu lub skanu PDF jest natomiast obsługiwany
  wewnątrz ekstraktora jako ostrzeżenie, bez przerywania przetwarzania.
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
  z rejestrem `RejestrEkstraktorowBinarnych` dla PDF, DOCX, EPUB, obrazów,
  nagrań audio oraz materiałów nutowych MIDI, MusicXML i Guitar Pro, pracujący
  wprost na bajtach pliku. Metoda `wyekstrahuj`
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
  wczytuje się bez zmiany numeru schematu. Tak samo dodane w etapie czternastym:
  `zweryfikowane_recznie`, `tresc_zastapiona_plikiem` i `plik_wynikowy_usuniety`
  przy źródle oraz wykaz `zastapione_pliki_grup` przy projekcie.
- `gnb/persistence/pliki_wynikowe.py` — zgodność checkpointu z plikami na
  dysku: wykrywanie plików wynikowych, których nie ma, cofanie grupy do
  przepakowania oraz usuwanie starych plików grup po zapisaniu nowych. Moduł
  niczego nie zapisuje w checkpoincie i nie pisze do logów, bo zapis
  checkpointu ma jednego właściciela naraz.

## Moduł gnb.operacje_projektu

Ręczne operacje użytkownika na źródłach istniejącego projektu: oznaczenie
jako zweryfikowane, usunięcie z projektu i sprawdzenie, czy treść da się
zastąpić plikiem. Każda operacja zapisuje checkpoint, odbudowuje manifest
i raport oraz dopisuje zdarzenie do obu logów. Zastąpienie treści wykonuje
potok, bo wymaga ekstrakcji; ten moduł tylko sprawdza, czy jest możliwe.
Interfejs woła te operacje pod `RejestrZadan.wylacznie()`, które odmawia, gdy
trwa przetwarzanie, żeby zapis checkpointu miał jednego właściciela naraz.
Raport odbudowany po operacji nie zna czasu pracy ani wykazu wejść już
obecnych z ostatniego przebiegu, bo tych danych checkpoint nie przechowuje,
i mówi o tym wprost w wierszu czasu pracy.

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
- `gnb/ui/widoki_zrodel.py` — wykaz źródeł projektu z działaniami, sekcja
  brakujących plików wynikowych i strona potwierdzenia usunięcia. Zależy od
  `widoki.py`, a nie odwrotnie: gotowy fragment jest przekazywany do strony
  projektu jako napis. Sekcja brakujących plików tylko pokazuje rozbieżność.
- `gnb/ui/server.py` — punkt wejścia `python -m gnb.ui.server`. Nazwa pliku jest
  angielska, bo to część kontraktu komend; logika i komunikaty są po polsku.
- `gnb/ui/stan_skrotu.py` — `AktywnyProjektSkrotu` i `OstatniKomunikatSkrotu`,
  stan globalnego skrótu widoczny w interfejsie. Nie zależy od Windows: żyje
  w `gnb.ui`, nie w `gnb.hotkeys`, żeby strony dało się wyrenderować i
  przetestować także na Linuksie, niezależnie od tego, czy skrót tam działa.

## Pakiet gnb.hotkeys

Globalny skrót klawiszowy Control plus Shift plus F12 z etapu jedenastego,
część A. Moduł wyłącznie dla Windows: cała zawartość plików zależnych od
Windows leży za sprawdzeniem `sys.platform == "win32"`, żeby dało się je
zaimportować (i sprawdzić poleceniem `python -m mypy gnb --platform linux`)
także na Linuksie, gdzie po prostu nic nie eksportują. Reszta pakietu `gnb`
importuje z niego wyłącznie warunkowo, wewnątrz `gnb/ui/serwer.py`, przy
starcie serwera.

- `gnb/hotkeys/stale.py` — kombinacja skrótu i parametry dwóch dźwięków
  potwierdzenia. Bez zależności od Windows, testowalne wszędzie.
- `gnb/hotkeys/model.py` — `InformacjeOOknie`, `DodanieZeSkrotu`, `TypDodania`.
  Typy współdzielone między odczytem stanu pulpitu a rozpoznaniem źródła, bez
  zależności od Windows.
- `gnb/hotkeys/rozpoznanie.py` — czysta funkcja `rozpoznaj`: z gotowych już
  informacji o aktywnym oknie, ewentualnego adresu paska i ewentualnej listy
  zaznaczonych plików ustala, co dodać do aktywnego projektu, albo zwraca
  `PorazkaRozpoznania` z czytelnym powodem. Testowalne bez Windows.
- `gnb/hotkeys/kolejka.py` — `KolejkaSkrotu`: źródła dodane skrótem w trakcie
  trwającego przebiegu, pogrupowane po nazwie projektu. Bez zależności od
  Windows.
- `gnb/hotkeys/_win32.py` — `ctypes`: `WatekSkrotu` rejestruje skrót i prowadzi
  jego pętlę komunikatów w dedykowanym wątku, bo `RegisterHotKey` i
  `UnregisterHotKey` muszą zajść w tym samym wątku Win32. Naciśnięcie skrótu
  jest obsługiwane w osobnym wątku roboczym, nie w wątku pętli komunikatów.
  Ustala też aktywne okno: uchwyt, tytuł, nazwę klasy i nazwę procesu.
- `gnb/hotkeys/_automatyzacja.py` — `comtypes` i UI Automation: odczyt paska
  adresu Chrome i Firefoksa, dopasowywany po nazwie klasy kontrolki
  (`OmniboxViewViews`, `urlbar-input`), sprawdzonej bezpośrednio w obu
  przeglądarkach, nie po lokalizowanej nazwie zależnej od języka interfejsu.
- `gnb/hotkeys/_eksplorator.py` — `comtypes` i `Shell.Application` z późnym,
  dynamicznym wiązaniem: zaznaczone elementy aktywnego okna Eksploratora
  plików.
- `gnb/hotkeys/_dzwieki.py` — `winsound.Beep`, nie `MessageBeep`, żeby dźwięk
  nie zależał od motywu dźwiękowego systemu.
- `gnb/hotkeys/obsluga.py` — `ObslugaSkrotu`: spina wszystko powyższe z
  rejestrem zadań i stanem skrótu z `gnb.ui`. Po naciśnięciu skrótu dodaje
  źródło do kolejki i, jeśli rejestr zadań jest wolny, od razu zaczyna
  przebieg; ten sam mechanizm uruchamia się automatycznie po zakończeniu
  każdego zadania w rejestrze, przez `RejestrZadan.dodaj_nasluch_zakonczenia`.

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

## Pakiet gnb.music

Odczyt materiałów nutowych w formatach natywnych i wykrywanie MuseScore. Pakiet
nie zna potoku ani checkpointu — jest zbiorem narzędzi wołanych przez adaptery
ekstrakcji.

- `gnb/music/model.py` — kontrakt `OpisPartytury`, wspólny wynik trzech
  parserów, oraz funkcje `opis_jako_tekst`, `opis_jako_metadane`
  i `zbuduj_dokument_wyekstrahowany`. Ta ostatnia twardo ustawia niski poziom
  pewności struktury, żeby dla opisu nutowego nie powstała wersja Markdown.
- `gnb/music/instrumenty_gm.py` — 128 barw General MIDI indeksowanych od zera
  oraz mapa perkusji kanału dziesiątego, po polsku.
- `gnb/music/tonacje.py` — odwzorowanie oznaczeń tonacji z MIDI, MusicXML
  i Guitar Pro na polskie nazwy.
- `gnb/music/nuty_teoria.py` — nazywanie pojedynczych dźwięków z numeru MIDI
  i wartości rytmicznych po polsku, dodane w etapie trzynastym dla zapisu
  dźwięków ścieżki strunowej.
- `gnb/music/midi.py` — odczyt MIDI biblioteką `mido`. Liczba taktów jest zawsze
  przybliżona, bo format nie zapisuje podziału na takty.
- `gnb/music/musicxml.py` — odczyt MusicXML i kontenera MXL biblioteką
  standardową `xml.etree.ElementTree`. Liczba taktów dokładna.
- `gnb/music/guitarpro.py` — odczyt Guitar Pro gp3, gp4 i gp5 biblioteką
  `PyGuitarPro`. Brak biblioteki kończy się `BrakNarzedzia`. Od etapu
  trzynastego dodatkowo buduje, dla każdej ścieżki strunowej, zapis jej
  dźwięków takt po takcie — szczegóły w `docs/FORMATS.md`, sekcja „Materiały
  nutowe”.
- `gnb/music/musescore.py` — odnajdywanie pliku wykonywalnego MuseScore wzorem
  `gnb/images/tesseract.py`. MuseScore nie jest uruchamiany; moduł służy tylko
  diagnostyce.
- `gnb/music/audiveris.py` — odnajdywanie pliku wykonywalnego Audiverisa, tym
  samym wzorem. W przeciwieństwie do MuseScore Audiveris jest naprawdę
  uruchamiany, przez adapter opisany niżej.

Cztery adaptery w `gnb/extractors/` — `plik_midi.py`, `plik_musicxml.py`,
`plik_guitarpro.py`, `plik_nuty_skanowane.py` — bramkują się na typie źródła
`PLIK_NUTY` i swoim zbiorze formatów. Dyspozytorem jest `RejestrEkstraktorowBinarnych`.
Adapter zapisu skanowanego, `plik_nuty_skanowane.py`, uruchamia Audiverisa
w trybie wsadowym w katalogu tymczasowym, a wyeksportowany przez niego MusicXML
przepuszcza przez ten sam parser co plik MusicXML podany wprost — granica
między częścią A a częścią B etapu dziesiątego wypadła dokładnie na tym pliku,
zgodnie z planem. Limit czasu jest liczony na stronę, nie na cały plik, bo
Audiveris przetwarza wielostronicowy PDF jednym wywołaniem i sam łączy strony
w jedną ciągłą partyturę. Postęp strona po stronie jest wykrywany odczytem
rosnącego pliku dziennika Audiverisa w trakcie jego pracy, nie przez parsowanie
strumienia na żywo. Szczegóły, w tym trzy różnice opisu wobec formatów
natywnych, opisuje `docs/FORMATS.md`, sekcja „Materiały nutowe”.

## Pozostałe pakiety

Pakiet `gnb.documents` jest dziś pusty. Adaptery formatów dokumentowych, które
aplikacja faktycznie obsługuje, leżą razem z pozostałymi adapterami
w `gnb.extractors`, opisanym w sekcji „Ekstraktory” wyżej — nie w `gnb.documents`,
mimo że sekcja szósta CLAUDE.md przydziela im ten pakiet. Kod poszedł inną drogą,
spójną samą w sobie, bo wszystkie ekstraktory leżą obok siebie w jednym miejscu;
`gnb.documents` pozostaje zarezerwowany, bez logiki. Pakiet `gnb.hotkeys` nie
jest pusty — opisuje go osobna sekcja „Pakiet gnb.hotkeys” wyżej w tym pliku.

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

Test `tests/test_potok_dokumentow_e2e.py` przeprowadza pełny przebieg dla
dokumentów: wszystkie formaty dokumentowe naraz bez błędów, CSV i napisy bez
oceny jakości (nie podlegają jej, bo nie mają ekstrakcji do oceniania), skan PDF
bez warstwy tekstowej trafiający do materiałów do sprawdzenia, uszkodzony PDF
i uszkodzony dokument niezatrzymujące pozostałych źródeł, oraz ostrzeżenie
ekstraktora docierające do manifestu i raportu.

Test `tests/test_potok_obrazy_e2e.py` przeprowadza pełny przebieg dla obrazów
i skanów: rozpoznany tekst w wyniku, skan PDF rozpoznawany strona po stronie,
grupa obrazów dająca jeden plik PDF na jeden slot, grupa mieszana obrazu
i tekstu dająca dwa pliki — PDF dla obrazu, TXT dla tekstu, zgodnie z sekcją 18d
CLAUDE.md — oraz skan bez OCR trafiający do materiałów do sprawdzenia zamiast
znikać po cichu. Testy zależne od rozpoznania polskiego tekstu pomijają się
czytelnym komunikatem, gdy w środowisku brakuje danych językowych Tesseracta.

Test `tests/test_potok_audio_e2e.py` przeprowadza pełny przebieg dla nagrań
mowy: wyłączoną transkrypcję pomijającą nagranie, materiał muzyczny odrzucany
bez transkrypcji, nagranie mowy z nagłówkiem niosącym rozpoznany język oraz
dłuższe nagranie w formacie m4a.

Test `tests/test_potok_nuty_e2e.py` przeprowadza pełny przebieg dla materiałów
nutowych: plik MIDI i plik Guitar Pro dające opis tekstowy z liczbą taktów, dwa
materiały nutowe w jednej grupie dostające mimo to osobne pliki, skan nut
z opcją `--nuty` pomijany bez Audiverisa i nie zajmujący przez to slotu limitu,
oraz — z markerem `wolne` — prawdziwe rozpoznanie skanu przez zainstalowanego
Audiverisa.

Testy pakietu `gnb.hotkeys` są w `tests/hotkeys/`: stałe skrótu, kolejka,
rozpoznanie tego, co dodać, na podstawie stanu aktywnego okna, cykl życia
`ObslugaSkrotu` oraz warstwa Win32. Testy odczytu paska adresu przez UI
Automation i zaznaczenia w Eksploratorze mają marker `pulpit`, bo wymagają
odpowiednio otwartej przeglądarki albo Eksploratora z zaznaczeniem, i są
domyślnie pominięte.

Test `tests/test_potok_mieszany_e2e.py` jest testem scalającym, dodanym w etapie
dwunastym: sprawdza jeden przebieg łączący naraz sześć typów źródeł — tekst
wklejony, plik Markdown, dokument PDF, obraz, materiał nutowy natywny oraz skan
nut pominięty z braku Audiverisa — i weryfikuje spójność między manifestem,
raportem końcowym i rzeczywistą zawartością katalogu wyników, w tym sumami
kontrolnymi policzonymi niezależnie z plików na dysku. Dziesięć pozostałych
testów end-to-end sprawdza pojedyncze ścieżki potoku osobno; ten sprawdza, czy
trzy niezależne opisy tego samego przebiegu — plik, manifest i raport —
zgadzają się ze sobą, gdy typy źródeł są wymieszane w jednym wywołaniu.

Testy kanaryjne w `tests/test_youtube_kanaryjny.py` są jedynymi, które sięgają do
prawdziwego serwisu. Mają marker `siec`, są domyślnie wyłączone i sprawdzają
wyłącznie to, czy każda z dwóch warstw pobierania nadal się przebija. Poza nimi
żaden test nie korzysta z sieci. Pobieranie jest sprawdzane na sztucznym
transporcie `httpx.MockTransport`, a odstępy i ponowienia na podstawionym
usypiaczu, więc testy są deterministyczne i nie czekają naprawdę. Ewentualne
testy sieciowe mają dostać marker `siec`, domyślnie wyłączony.
