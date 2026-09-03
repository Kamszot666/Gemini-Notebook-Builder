# Obsługiwane formaty — stan po etapie ósmym

Ten dokument opisuje formaty wejściowe i wynikowe obsługiwane w tej chwili.
Kolejne formaty, czyli ODT, PPTX, obrazy oraz materiały nutowe, dojdą
w etapach opisanych w sekcji osiemnastej pliku `CLAUDE.md`.

## Wejście

Obsługiwane są następujące rodzaje wejścia:

1. Tekst wklejony bezpośrednio przez użytkownika, traktowany jako tekst płaski.
2. Tekst wklejony zadeklarowany przez użytkownika jako Markdown.
3. Plik lokalny w jednym z formatów tekstowych i dokumentowych: TXT, MD, HTML,
   CSV, SRT, VTT, PDF, DOCX albo EPUB. Pierwsze dwa są plikiem tekstowym,
   pozostałe plikiem dokumentem — rozróżnienie opisuje sekcja „Pliki dokumentowe”.
4. Plik obrazu: JPG, PNG, WebP, TIFF, BMP oraz statyczna klatka GIF, a przy
   zainstalowanej bibliotece opcjonalnej pillow-heif także HEIC i HEIF.
   Obsługę obrazów opisuje sekcja „Obrazy”.
5. Adres strony internetowej, podany pojedynczo albo listą.
6. Adres filmu z serwisu YouTube, dla którego pobierane są napisy.

Plik w innym formacie kończy się kontrolowanym błędem `FormatNieobslugiwany`.
Nie zatrzymuje to przetwarzania pozostałych źródeł.

## Adresy stron internetowych

Adres można podać na trzy sposoby: pojedynczo, kilka adresów rozdzielonych
spacjami oraz kilka adresów w osobnych wierszach. To samo dotyczy importowanego
pliku TXT z listą adresów. Wiersz zaczynający się od krzyżyka jest komentarzem.

Zanim cokolwiek zostanie pobrane, aplikacja pokazuje podsumowanie: ile adresów
wykryto, ile jest poprawnych, ile pominięto jako duplikat i ile wpisów odrzucono
wraz z powodem. To jest najtańszy moment na wychwycenie pomyłki.

### Dwie postacie adresu

Adres jest przechowywany w dwóch postaciach. Postać kanoniczna jest kluczem
tożsamości źródła oraz kluczem pamięci podręcznej: schemat i nazwa hosta małymi
literami, bez domyślnego portu, bez fragmentu, z posortowanymi parametrami.
Postać pobierania jest tym, co trafia do serwera, i zachowuje oryginalną
kolejność parametrów, ponieważ część serwisów zwraca przy innej kolejności inną
treść.

Z obu postaci usuwane są wyłącznie znane parametry śledzące, czyli rodzina
`utm_` oraz nazwy takie jak `fbclid`, `gclid`, `msclkid` czy `igshid`. Listę można
rozszerzyć ustawieniem `dodatkowe_parametry_sledzace`. Pozostałe parametry
zostają, nawet gdy wyglądają na zbędne, ponieważ parametr bywa jedynym wskazaniem
konkretnego artykułu.

Przedrostek `www` nie jest usuwany, bo bywają serwisy, w których wersja z nim
i bez niego to dwie różne witryny. Fragment po znaku krzyżyka jest usuwany,
z jednym wyjątkiem: fragment zaczynający się od wykrzyknika albo ukośnika
zostaje, ponieważ w starszych aplikacjach jednostronicowych to on wskazuje
konkretną treść.

### Pobieranie

Każde żądanie ma limit czasu, ograniczoną liczbę ponowień i rosnący odstęp między
próbami. Do jednej domeny idą najwyżej trzy równoległe połączenia, z odstępem
między żądaniami. Klient przedstawia się nazwą wskazującą projekt i domyślnie
respektuje plik `robots.txt`.

Sytuacje kończące się statusem „pominiete”, czyli świadomym pominięciem, a nie
błędem: zakaz w pliku `robots.txt`, nieosiągalny plik `robots.txt`, zasób, który
nie jest stroną HTML, zasób przekraczający bezpieczny limit pobrania oraz strona
budująca treść dopiero przez wykonanie skryptów.

### Reguły witryny, czyli plik robots.txt

Polityka jest zgodna z RFC 9309, sekcja 2.3.1, i wygląda tak:

1. Odpowiedź z rodziny 2xx oznacza wczytanie reguł i stosowanie się do nich.
2. Odpowiedź z rodziny 4xx, w tym 401 i 403, oznacza brak reguł, czyli zgodę na
   pobieranie. Ma to również znaczenie praktyczne: witryny za zaporą aplikacyjną
   często odpowiadają kodem 403 na sam plik `robots.txt` przy nietypowym
   kliencie, mimo że artykuł jest publicznie dostępny w przeglądarce.
3. Odpowiedź z rodziny 5xx oraz błąd sieci oznaczają reguły nieokreślone, a wtedy
   obowiązuje pełny zakaz. Taka sytuacja jest najpierw ponawiana zgodnie
   z ustawieniami odstępów, a dopiero po wyczerpaniu prób źródło zostaje
   pominięte z komunikatem wyjaśniającym.

Wynik odczytu reguł jest zapamiętywany na czas jednego uruchomienia i dotyczy
całej witryny, więc wiele adresów z jednego serwisu pyta o ten plik tylko raz.

Od tej kontroli jest jeden wyjątek. Adres, który podałeś wprost na liście źródeł,
nie podlega sprawdzeniu pliku `robots.txt`. Powód: protokół opisany w RFC 9309
jest adresowany do klientów automatycznych, które same odkrywają adresy
i przeszukują serwis, a ten program wykonuje pojedyncze, jawne polecenie
człowieka dotyczące jednego wskazanego zasobu. Adres, który program znalazłby sam
w treści innego źródła, podlega kontroli bez wyjątku. Każde zastosowanie wyjątku
jest zapisywane w logu szczegółowym razem z adresem, a sam wyjątek można wyłączyć
ustawieniem `wyjatek_robots_dla_zrodel_jawnych`. Decyduje pochodzenie adresu,
a nie domena, więc żaden serwis nie jest traktowany szczególnie.

Warunki korzystania z serwisu są zagadnieniem odrębnym od pliku `robots.txt`
i program ich nie ocenia. Odpowiedzialność za zgodność użycia z warunkami serwisu
spoczywa na osobie korzystającej z narzędzia.

### Strony budowane skryptami

Serwisy, które bez wykonania skryptów zwracają pusty szkielet strony, są
rozpoznawane i nazywane wprost. Warunki muszą zajść jednocześnie: dokument jest
rozbudowany, zawiera znacznik skryptu, a mimo to ekstrakcja daje treść znikomą
albo pustą.

Takie źródło dostaje status „pominiete”, a jego powód trafia do manifestu i do
raportu końcowego. Komunikat podpowiada obejście działające już teraz: otwórz
stronę w przeglądarce, skopiuj treść artykułu i wklej ją jako tekst.

Obsługa takich stron przez przeglądarkę bezgłową jest świadomie poza zakresem
projektu, ponieważ wymagałaby setek megabajtów zależności natywnych.

Sytuacje kończące się statusem „blad”: odpowiedzi 401, 403, 404 i 410 oraz
wyczerpanie ponowień przy błędach przejściowych, czyli przekroczeniu limitu
czasu, zerwaniu połączenia, odpowiedziach z rodziny 5xx i odpowiedzi 429.

Osobnym przypadkiem jest błąd certyfikatu TLS. Nie jest ponawiany, ponieważ
niezaufany certyfikat nie naprawi się przy kolejnej próbie. Komunikat wskazuje
trzy realne przyczyny: przechwytywanie ruchu przez program antywirusowy albo
serwer pośredniczący, przeterminowany certyfikat witryny oraz źle ustawiony
zegar systemowy.

### Ekstrakcja treści artykułu

Treść artykułu jest wydobywana biblioteką `trafilatura`, która odrzuca menu,
banery zgody na pliki cookie, reklamy, ramki boczne i stopkę. Rozpoznane
nagłówki, listy, tabele, cytaty i bloki kodu trafiają do struktury dokumentu,
więc dobrze zbudowany artykuł może dostać także wersję MD.

Gdy trafilatura nic nie zwróci, wchodzi mechanizm zapasowy oparty na `lxml`,
który odzyskuje same akapity. Zgłasza on niski poziom pewności struktury, więc
z materiału odzyskanego awaryjnie wersja MD nigdy nie powstanie.

Pochodzenie całego artykułu jest zapisane w manifeście: adres kanoniczny, adres
końcowy po przekierowaniach, kod odpowiedzi HTTP, deklarowane kodowanie oraz
nagłówki `ETag` i `Last-Modified`.

### Odnośniki wymienione w artykule

Adres odnośnika nie zostaje w środku zdania, ponieważ utrudnia odsłuchanie tekstu
czytnikiem ekranu. W miejscu odnośnika zostaje sam jego tekst, bez numeru
i bez odsyłacza, żeby zdanie brzmiało naturalnie.

Adresy nie są jednak gubione. Na końcu wersji TXT i MD powstaje sekcja
zatytułowana „Odnośniki wymienione w artykule”, zawierająca ponumerowaną listę
pozycji w postaci tekst odnośnika, myślnik, adres. Sekcja powstaje tylko wtedy,
gdy w artykule był co najmniej jeden taki odnośnik. Powtórzony adres pojawia się
w wykazie raz, ponieważ wykaz wskazuje źródła, a nie liczy odwołania.

Do wykazu trafiają wyłącznie pełne adresy HTTP i HTTPS. Pomijane są odsyłacze
w obrębie tej samej strony, adresy poczty, wywołania skryptów oraz adresy
względne, których bez znajomości adresu bazowego nie da się rozwinąć do postaci
użytecznej dla czytelnika.

Powód takiego rozwiązania: adres zacytowany przez autora bywa jedynym wskazaniem
badania albo danych, a identyfikowalność źródeł jest czwartym priorytetem
z sekcji czwartej `CLAUDE.md`, wyżej niż wygoda formatowania. Sekcję można
wyłączyć ustawieniem `zachowuj_odnosniki`.

### Pamięć podręczna

Pobrane strony trafiają do wspólnej pamięci podręcznej, dzięki czemu ten sam
artykuł użyty w dwóch notatnikach pobiera się tylko raz. Wpis starszy niż
ustawiony maksymalny wiek jest odświeżany zapytaniem warunkowym z nagłówkami
`If-None-Match` oraz `If-Modified-Since`. Odpowiedź 304 oznacza, że zapisana
treść jest nadal aktualna. Ścieżkę pliku i sposób czyszczenia opisuje
`docs/CONFIGURATION.md`.

## Kodowanie tekstu

Kodowanie plików jest wykrywane biblioteką `charset-normalizer`. Obsługiwany jest
znak kolejności bajtów dla UTF-8, UTF-16 i UTF-32 — jest on usuwany z wyniku.
Wewnętrznie końce wierszy są sprowadzane do pojedynczego znaku nowej linii,
a znaki Unicode do postaci NFC. Pliki wynikowe są zapisywane w UTF-8 bez znaku
kolejności bajtów, z końcami wierszy LF.

### Białe znaki i znaki niewidoczne

Wewnątrz wiersza tabulatory, twarde spacje, wąskie spacje niepodzielne oraz ciągi
spacji stają się jedną spacją. Powód nie jest kosmetyczny: czytnik ekranu
odczytuje tabulator jako osobny element, a w materiale dla notatnika jest to szum.

Wcięcie na początku wiersza jest zachowywane co do liczby znaków, ponieważ niesie
znaczenie: tak zapisywane są zagnieżdżenia list i wnętrze bloków kodu. Wcięcie
zrobione tabulatorami staje się wcięciem spacjami, po jednej spacji na znak.

Usuwane są znaki niewidoczne dla czytelnika: spacja o zerowej szerokości, spoiwo
słów, znacznik kolejności bajtów wewnątrz tekstu oraz miękki łącznik. Usuwane są
także znaki sterujące inne niż znak nowej linii. Zachowywane są natomiast łącznik
nierozdzielający i spoiwo, czyli ZWNJ oraz ZWJ, ponieważ w części pism i w
sekwencjach emoji zmieniają znaczenie zapisu.

## Wynik: TXT zawsze, MD warunkowo

Plik TXT powstaje zawsze. Plik MD powstaje dodatkowo tylko wtedy, gdy spełnione
są jednocześnie dwa warunki.

Warunek pierwszy: dokument spełnia co najmniej dwa z czterech warunków
strukturalnych:

1. Zawiera co najmniej trzy nagłówki tworzące rzeczywistą hierarchię co najmniej
   dwupoziomową.
2. Zawiera co najmniej dwie listy, z których przynajmniej jedna ma co najmniej
   trzy elementy.
3. Zawiera co najmniej jedną tabelę, którą da się zapisać bez utraty znaczenia.
   Tabela o wierszach różnej długości tego warunku nie spełnia: zapis Markdown ma
   stałą liczbę kolumn wyznaczoną przez nagłówek, więc wiersz o innej liczbie
   komórek albo straciłby nadmiarowe komórki, albo dostałby puste. Sama pionowa
   kreska w treści komórki nie przeszkadza, bo przy zapisie jest escapowana.
4. Zawiera blok kodu lub zapis techniczny, w którym formatowanie niesie
   znaczenie.

Warunek drugi, konieczny: poziom pewności struktury zgłoszony przez ekstraktor
jest co najmniej średni.

W etapie pierwszym poziom pewności wysoki mają wyłącznie pliki MD oraz tekst
wklejony zadeklarowany jako Markdown. Pliki TXT oraz zwykły tekst wklejony mają
zawsze poziom niski, nawet jeżeli zawierają wiersze wyglądające na nagłówki.
Dzięki temu z pliku TXT nigdy nie powstaje wersja MD.

Decyzja o wygenerowaniu wersji MD wraz z listą spełnionych warunków jest
zapisywana w manifeście.

## Filmy z serwisu YouTube

Pobierane są wyłącznie napisy, nigdy sam film. Adres można podać w dowolnej
postaci: `youtube.com/watch?v=IDENTYFIKATOR`, `youtu.be/IDENTYFIKATOR`,
`youtube.com/shorts/IDENTYFIKATOR`, `youtube.com/live/IDENTYFIKATOR` oraz
`youtube.com/embed/IDENTYFIKATOR`. Wszystkie sprowadzają się do jednego adresu
kanonicznego zbudowanego z identyfikatora filmu, więc ten sam film podany
dwukrotnie w różnej postaci jest jednym źródłem.

Adres filmu z dopisanym numerem playlisty, czyli `watch?v=FILM&list=LISTA`, jest
zwykłym pojedynczym filmem. Parametr listy jest pomijany.

### Playlisty i kanały

Playlisty i kanały nie są obsługiwane. Rozwinięcie playlisty na listę filmów
łamałoby przewidywalność limitu źródeł notatnika i uruchamiało masowe pobieranie
bez wyraźnego polecenia. Taki adres dostaje status „pominiete”, a komunikat mówi
wprost, że trzeba podać adresy poszczególnych filmów. Pozostałe źródła są
przetwarzane normalnie.

### Wybór napisów

Kolejność jest deterministyczna i ma cztery kroki. Najpierw napisy tworzone
ręcznie, w kolejnych językach z listy preferencji. Potem napisy automatyczne,
w tej samej kolejności języków. Potem, o ile konfiguracja na to pozwala, napisy
przetłumaczone automatycznie. Na końcu, gdy nic z powyższego nie jest dostępne,
napisy w dowolnym innym języku: najpierw tworzone ręcznie, potem automatyczne,
a w obrębie grupy rosnąco według kodu języka, żeby wybór był powtarzalny.

Krok czwarty można wyłączyć ustawieniem `awaryjny_dowolny_jezyk`. Jego użycie
nie jest ciche: do `log_wazne.txt` trafia ostrzeżenie z tytułem filmu, listą
oczekiwanych języków i językiem pobranym, a manifest dostaje osobne pole.
Wybrany język i typ napisów trafiają do manifestu zawsze, więc wiadomo, skąd
wzięła się treść. Do `log_wazne.txt` trafia też przy każdym filmie jeden wiersz
mówiący, w jakim języku i jakiego rodzaju napisy pobrano.

Napisy pobierają dwie wzajemnie zapasowe warstwy: `youtube-transcript-api` oraz
`yt-dlp`. Obie potrafią przestać działać po zmianach po stronie serwisu, więc
awaria pierwszej przenosi pracę na drugą. Metadane filmu, czyli tytuł, kanał,
długość i data publikacji, pochodzą z `yt-dlp`.

### Postać transkrypcji

Segmenty napisów są sklejane w zdania, a zdania w akapity. Usuwane są oznaczenia
dźwięków w rodzaju „[muzyka]” oraz powtórzenia typowe dla napisów automatycznych,
w których kolejny segment powtarza końcówkę poprzedniego.

Napisy tworzone ręcznie bywają poprzedzone albo zakończone stopką tłumaczy
społecznościowych, na przykład „Tłumaczenie: imię i nazwisko” albo „Subtitles by”.
To nie jest wypowiedź prelegenta, a doklejona do pierwszego zdania zanieczyszcza
materiał, bo model czytający bazę wiedzy uzna nazwiska za treść wykładu. Stopka
jest więc wycinana z tekstu, ale nie jest kasowana: trafia do manifestu, do pola
`atrybucja_napisow`, w całości i bez prób wydzielania nazwisk. Sprawdzane są
wyłącznie skrajne segmenty transkrypcji, po kilka z każdej strony, i wyłącznie
w napisach tworzonych ręcznie, ponieważ automatyczne takich stopek nie zawierają.
Wzorce polskie wymagają dwukropka, więc zdanie prelegenta zaczynające się od słowa
„tłumaczenie” zostaje nietknięte.

Znaczniki czasu są domyślnie wyłączone. Po włączeniu ustawieniem
`znaczniki_czasu` pojawiają się wyłącznie na początku akapitu, w postaci
`[mm:ss]` dla materiałów krótszych niż godzina i `[h:mm:ss]` dla dłuższych.
Format jest jednolity w obrębie całego pliku, a podział na akapity jest taki sam
niezależnie od tego, czy znaczniki są włączone.

Transkrypcja nie ma struktury dokumentu, więc dla filmu nigdy nie powstaje wersja
MD. Plik TXT zawiera sam tekst transkrypcji, poprzedzony nagłówkiem metadanych
opisanym w sekcji „Nagłówek metadanych pliku wynikowego”, wspólnym dla
wszystkich typów źródeł.

### Przypadki, w których film nie zostaje przetworzony

Statusem „pominiete” kończą się: brak napisów w wybranych językach, napisy
złożone wyłącznie z oznaczeń dźwięków, playlista, kanał oraz adres YouTube bez
identyfikatora filmu. Przy braku napisów komunikat odsyła do etapu dziewiątego,
w którym powstanie transkrypcja mowy z samego dźwięku.

Statusem „blad” kończą się: film prywatny, usunięty, niedostępny w regionie,
ograniczony wiekiem oraz niepoprawny identyfikator filmu. Zablokowanie żądania
przez serwis i błąd sieci są traktowane jako błędy przejściowe i ponawiane.

## Pliki dokumentowe

Etap czwarty dodał siedem formatów plików lokalnych: HTML, CSV, SRT, VTT, PDF,
DOCX i EPUB. Wszystkie dostają typ źródła „plik dokument”, w odróżnieniu od
plików TXT i MD, które są „plikiem tekstowym”. Rozróżnienie ma znaczenie
praktyczne: tylko plik dokument z prozą, czyli PDF, DOCX, EPUB i HTML lokalny,
podlega ocenie jakości ekstrakcji opisanej dalej w tym dokumencie.

HTML, CSV, SRT i VTT są plikami tekstowymi w sensie kodowania: kodowanie znaków
jest wykrywane tak samo jak dla pliku TXT. PDF, DOCX i EPUB są kontenerami
binarnymi — próba wykrycia kodowania znakowego na ich bajtach dałaby
bezużyteczny wynik, więc te trzy formaty czyta osobny rejestr ekstraktorów,
pracujący wprost na bajtach pliku, a nie na tekście już rozkodowanym.

### HTML lokalny

Plik HTML lokalny korzysta z dokładnie tego samego ekstraktora co strona
internetowa: ekstrakcja przez `trafilatura` pracuje na kodzie HTML niezależnie
od tego, czy pochodzi z pobrania, czy z dysku. Jedyna różnica: plik lokalny nie
przechodzi przez wykrywanie stron wymagających wykonania skryptów, ponieważ to
jest opisany w CLAUDE.md sposób obejścia takiej strony — zapisanie jej
z przeglądarki po wykonaniu skryptów i podanie zapisanego pliku jako źródła.

### CSV

Plik CSV staje się jedną tabelą. Ogranicznik kolumn jest rozpoznawany
automatycznie spośród przecinka, średnika, tabulatora i pionowej kreski;
gdy rozpoznanie się nie powiedzie, przyjmowany jest przecinek. Pierwszy wiersz
jest zawsze traktowany jako nagłówek kolumn — to jest założenie, nie wynik
wykrycia, bo z samego pliku CSV nie da się tego jednoznacznie rozstrzygnąć.

Plik CSV nie ma tytułu ani podziału na akapity z natury formatu, więc świadomie
nie podlega ocenie jakości ekstrakcji: dla tabeli danych brak tytułu nie jest
oznaką utraty treści. Wersja TXT rozpisuje tabelę jako kolejne wiersze „nazwa
kolumny: wartość”, po jednym wierszu na komórkę, tą samą drogą co tabela
w dokumencie Markdown — czytnik ekranu odsłuchuje to wyraźnie lepiej niż wiersz
z komórkami rozdzielonymi przecinkami.

### Napisy z pliku: SRT i VTT

Oba formaty mają tę samą budowę: bloki rozdzielone pustym wierszem, z jedną
linią zawierającą znacznik czasu w postaci „początek --> koniec”. Blok bez
takiej linii jest pomijany w całości, co naturalnie usuwa nagłówek „WEBVTT”
oraz bloki komentarza `NOTE`, `STYLE` i `REGION` pliku VTT, bez osobnej obsługi
każdego z nich.

Pominięcie bloku, który nie jest ani nagłówkiem, ani komentarzem, jest już
utratą treści, więc takie bloki są liczone. Ich liczba trafia do metadanych
źródła jako `liczba_blokow_pominietych`, a niezerowa wartość daje ostrzeżenie
widoczne w manifeście i w sekcji „Materiały do sprawdzenia” raportu końcowego.

Segmenty są sklejane w akapity dokładnie tym samym mechanizmem co napisy
pobrane z YouTube: fragmenty urwane w połowie zdania są łączone w zdania,
a segmenty, które powtarzają końcówkę poprzedniego — co zdarza się w plikach
eksportowanych z automatycznego rozpoznawania mowy — nie dublują tekstu
w wyniku. Powtórzeniem jest przy tym wyłącznie rzeczywiste nakładanie się, czyli
sytuacja, w której koniec dotychczasowego akapitu jest dosłownie początkiem
nowego segmentu. Zdanie powtórzone w innym miejscu wypowiedzi zostaje, bo jest
treścią, a nie skutkiem przewijania tekstu na ekranie.

Znaczniki wewnątrzwierszowe, na przykład wyróżnienia i wskazania mówiącego
w pliku VTT, są usuwane. Usuwane są też oznaczenia dźwięków, ale wyłącznie te,
które rzeczywiście nimi są. Zawartość nawiasu zawierająca cyfrę zostaje zawsze,
bo daty, zakresy lat i numery nie są oznaczeniami dźwięków. Nawias obejmujący
cały segment jest oznaczeniem, ponieważ segment złożony wyłącznie z nawiasu nie
jest wypowiedzią. Nawias wewnątrz zdania jest oznaczeniem tylko wtedy, gdy ma
najwyżej trzy słowa i nie zawiera znaku końca zdania. Przy wątpliwości nawias
zostaje, bo utrata treści kosztuje więcej niż zostawiona etykieta dźwięku.

Plik napisów, tak jak transkrypcja YouTube, nie ma struktury dokumentu i nie
ma tytułu, więc nigdy nie powstaje dla niego wersja MD i nie podlega ocenie
jakości ekstrakcji.

### PDF

Ekstraktor najpierw czyta tekst już obecny w pliku PDF. Gdy warstwy tekstowej
nie ma — plik jest skanem złożonym z obrazów stron — i OCR jest włączony w
konfiguracji, każda strona jest rasteryzowana biblioteką pypdfium2 w
rozdzielczości `ocr_rozdzielczosc_pdf_dpi` i rozpoznawana programem Tesseract.
Wynik jest składany w jeden tekst, w którym przed treścią każdej strony stoi
wiersz „Strona N:”, więc numery stron nie giną. Metoda ekstrakcji zapisana w
manifeście to wtedy `pdf-ocr`, a nie `pdf`.

Tekst z OCR zawsze dostaje ostrzeżenie „Tekst tego pliku PDF pochodzi z OCR
skanu, więc może zawierać błędy rozpoznania”, więc trafia do sekcji „Materiały
do sprawdzenia” raportu końcowego. Jeżeli rozpoznany tekst wygląda na przekłamany
— dużo znaków nietekstowych albo słów bez samogłosek — dochodzi drugie
ostrzeżenie z powodem.

Gdy OCR jest wyłączony albo nie znaleziono Tesseracta, ze skanu nie powstaje
żadna treść, a plik dostaje ostrzeżenie o braku warstwy tekstowej, zapisane w
manifeście, w logu szczegółowym oraz w sekcji „Materiały do sprawdzenia”.

Plik zaszyfrowany albo zabezpieczony przed kopiowaniem kończy się błędem trwałym
z czytelnym komunikatem: taki plik nie zaimportuje się także wprost do notatnika,
niezależnie od planu. Plik uszkodzony albo o nieprawidłowej strukturze kończy się
tym samym rodzajem błędu, a nie awarią programu.

Nagłówek i numer strony, powtarzane na każdej stronie dłuższego dokumentu, są
usuwane, żeby nie zaśmiecały wyniku tyloma powtórzeniami, ile jest stron.
Wykrywanie jest celowo pozycyjne i ostrożne: sprawdzane są wyłącznie pierwsze
dwa wiersze każdej strony, a wiersz znika ze wszystkich stron tylko wtedy, gdy
jego treść jest identyczna na każdej z nich. Numer strony jest wykrywany
wzorcem w rodzaju „Strona 3” albo „Page 3 of 10”, bo jego treść zmienia się na
każdej stronie i porównanie tekstu by go nie złapało. Żaden inny wiersz nie
jest ruszany, więc treść merytoryczna nie ginie nawet wtedy, gdy przypadkiem
powtarza się między stronami — powtórzeniami między źródłami zajmuje się
deduplikacja, opisana niżej, a nie ekstrakcja.

PDF nie ma niezawodnie odtwarzalnej struktury dokumentu: format zapisuje tekst
jako pozycjonowane fragmenty na stronie, a nie jako drzewo nagłówków
i akapitów. Ekstraktor nie zgaduje nagłówków z wielkości czcionki i nie tworzy
bloków strukturalnych, więc dla pliku PDF nigdy nie powstaje wersja MD.

### DOCX

Format DOCX niesie prawdziwą strukturę semantyczną: styl akapitu mówi wprost,
czy jest nagłówkiem i którego poziomu, czy elementem listy wypunktowanej albo
numerowanej, a tabela jest osobnym elementem dokumentu. Akapity i tabele są
czytane w kolejności występowania w pliku, a kolejne akapity tego samego stylu
listy są sklejane w jeden blok listy. Tytuł pochodzi z właściwości pliku, a gdy
jej brak, z pierwszego rozpoznanego nagłówka. Autor oraz daty utworzenia
i modyfikacji, jeżeli są w pliku, trafiają do metadanych źródła.

Akapity i tabele opakowane w kontrolki zawartości, czyli w element `w:sdt`, są
rozwijane i czytane normalnie. Ta konstrukcja jest powszechna w dokumentach
utworzonych z szablonów, a bez rozwinięcia jej zawartość nie trafiłaby do wyniku
wcale.

Ekstraktor nie rozpoznaje bloków kodu, ponieważ DOCX nie ma dla nich
standardowego stylu, a zgadywanie po nazwie czcionki byłoby heurystyką bez
pewności.

Plik uszkodzony albo niebędący dokumentem programu Word kończy się błędem
trwałym z czytelnym komunikatem, a nie awarią programu. Jedno uszkodzone źródło
nie zatrzymuje pozostałych źródeł tej samej partii.

### EPUB

Rozdziały, zapisane wewnątrz pliku EPUB jako osobne pliki XHTML, są czytane
w kolejności lektury zapisanej w spisie `spine`, a nie w kolejności zapisania
wewnątrz archiwum — tylko `spine` gwarantuje właściwą kolejność. Dokument
nawigacyjny EPUB 3, czyli plik ze spisem treści, jest pomijany, bo jest spisem
odnośników, a nie treścią książki.

Każdy rozdział jest rozbierany na nagłówki, akapity, listy, tabele i cytaty
wprost ze znaczników XHTML, z wejściem rekurencyjnym w kontenery `div`,
`section` i `article`, żeby treść owinięta w takie elementy, typowa dla plików
EPUB generowanych automatycznie, nie zginęła. Tytuł i autor pochodzą
z metadanych Dublin Core pliku, obecnych w każdym poprawnym pliku EPUB.

Treść, dla której nie ma osobnej gałęzi, też nie ginie. Tekst leżący
bezpośrednio w kontenerze, bez otaczającego akapitu, staje się akapitem.
Znacznik spoza listy obsługiwanych — na przykład `figcaption`, `dl`, `dt`, `dd`,
`aside` albo `figure` — jest przechodzony rekurencyjnie, gdy zawiera w środku
znany blok, a w przeciwnym razie daje jeden akapit z całą swoją treścią.
Nagłówek dokumentu XHTML, czyli `head` razem z tytułem pliku, stylami
i skryptami, jest pomijany, bo nie jest treścią książki.

Komórki wiersza tabeli są zbierane w kolejności ich wystąpienia w dokumencie,
niezależnie od tego, czy są komórką nagłówkową `th`, czy zwykłą `td`. Wiersz
zawierający oba rodzaje zachowuje więc kolejność kolumn.

Rozdział, którego nie da się sparsować, jest pomijany, ale zgłasza ostrzeżenie
z nazwą pliku rozdziału, więc nie znika po cichu. Pozostałe rozdziały są
odczytywane normalnie. Plik uszkodzony albo niebędący książką EPUB kończy się
błędem trwałym z czytelnym komunikatem, a nie awarią programu.

### Obrazy

Plik obrazu daje źródło typu „obraz”. Wynik ekstrakcji to opis merytoryczny
złożony wyłącznie z materiału, który aplikacja już ma, oraz, osobną oznaczoną
sekcją, tekst rozpoznany przez OCR. Treść wizualna nigdy nie jest interpretowana
ani wysyłana do zewnętrznej usługi.

Opis merytoryczny powstaje z opisowej nazwy pliku, formatu i wymiarów obrazu,
pola opisowego z metadanych EXIF lub pól tekstowych formatu PNG, a dla obrazu
wyjętego z treści strony także z tekstu alternatywnego, podpisu figury i
otaczającego akapitu. Gdy nie ma z czego zbudować opisu, w pliku wynikowym
pojawia się jawny komunikat o jego braku wraz z formatem i wymiarami — obraz
wskazany przez użytkownika nie jest pomijany po cichu. Sam tekst OCR nie jest
w opisie powtarzany w całości, tylko odnotowany; pełny tekst stoi w osobnej
sekcji.

OCR obrazu jest wykonywany, gdy jest włączony w konfiguracji i gdy znaleziono
Tesseract. Wynik pusty albo złożony ze śmieci dostaje ostrzeżenie i trafia do
sekcji „Materiały do sprawdzenia”, zamiast zniknąć po cichu. Struktura dokumentu
obrazu jest zawsze na poziomie niskim, więc dla obrazu nigdy nie powstaje wersja
Markdown.

Animowany plik GIF jest przetwarzany z pierwszej klatki, z ostrzeżeniem o tym.
Formaty HEIC i HEIF wymagają biblioteki opcjonalnej pillow-heif; jej brak
kończy się błędem `FormatNieobslugiwany` ze wskazówką instalacji, a nie
wyłączeniem całej obsługi obrazów. Plik uszkodzony kończy się tym samym rodzajem
błędu, a nie awarią programu.

Pliki obrazów nie są zapisywane jako TXT: cała grupa obrazów trafia do jednego
tematycznego pliku PDF, opisanego w sekcji „Pakowanie i podział plików
wynikowych”.

### Poziom pewności struktury plików dokumentowych

DOCX i EPUB niosą znaczniki semantyczne wprost z formatu — styl akapitu albo
znacznik XHTML — więc ich struktura jest odwzorowywana, a nie zgadywana,
i dostaje wysoki poziom pewności. HTML lokalny dostaje ten sam poziom co strona
internetowa, bo struktura jest tam dopiero rozpoznawana przez `trafilatura`.
PDF nie ma niezawodnie odtwarzalnej struktury, więc zawsze dostaje poziom
niski, tak samo jak obraz. Plik CSV dostaje wysoki poziom mimo braku nagłówków
czy list, bo jego jedyna struktura — tabela — jest odczytywana wprost, bez
zgadywania.

## Czym różni się wersja TXT od wersji MD

Gdy źródłem jest Markdown, obie wersje mają inną treść. Wersja MD zachowuje
pełny zapis Markdown. Wersja TXT dostaje ten sam dokument przepisany bez znaków
składni, ale z zachowaną strukturą:

1. Nagłówek jest osobnym wierszem tekstu, bez krat.
2. Element listy wypunktowanej jest wierszem zaczynającym się myślnikiem
   i spacją. Element listy numerowanej zachowuje swój numer w postaci numeru,
   kropki i spacji, ponieważ numer niesie znaczenie: kolejność kroków oraz
   możliwość odwołania się w tekście do konkretnego punktu. Numeracja zaczynająca
   się od innej liczby niż jeden jest zachowywana. Zagnieżdżenie listy jest
   oddane wcięciem dwóch spacji na każdy poziom.
3. Tabela jest rozpisana wierszami w postaci nazwa kolumny, dwukropek, wartość,
   po jednym wierszu na komórkę i z pustym wierszem między rekordami.
4. Blok kodu traci ogrodzenie, ale zachowuje wcięcia i łamanie wierszy.
5. Cytat blokowy staje się zwykłymi wierszami tekstu.
6. Gwiazdki, podkreślenia i pojedyncze grawisy znikają, zostaje sam tekst.
   Adres odnośnika jest dopisywany w nawiasie po jego treści, żeby informacja
   o pochodzeniu nie przepadła.

Powód takiego rozdziału jest praktyczny. Wcześniej oba pliki miały identyczną
treść i zajmowały dwa sloty notatnika na to samo. Teraz wersja TXT jest czytelna
liniowo czytnikiem ekranu, a wersja MD zachowuje formatowanie.

Przepisanie nie może gubić treści. Sprawdza to test
`tests/output/test_tekst_bez_znacznikow.py`, który porównuje obie wersje pliku
`tests/dane/dokument_strukturalny.md` i wymaga, żeby w wersji TXT znalazł się
każdy wiersz treści i każda komórka tabeli.

## Nagłówek metadanych pliku wynikowego

Każdy plik wynikowy zaczyna się nagłówkiem metadanych źródła. Sama treść nie
mówi, skąd pochodzi: transkrypcja filmu bez tytułu i adresu jest w notatniku
materiałem bez kontekstu, a artykuł bez daty publikacji bywa różnicą między
informacją a dezinformacją.

Każdy wiersz nagłówka ma postać etykieta, dwukropek, spacja, wartość. Kolejność
pól jest stała:

1. Tytuł.
2. Typ źródła.
3. Adres, dla źródeł sieciowych. Jest to adres pobierania, a nie postać
   kanoniczna, żeby dało się go wkleić do przeglądarki wprost.
4. Plik, dla źródeł lokalnych. Jest to nazwa pliku wejściowego.
5. Autor.
6. Data publikacji.
7. Kanał, wyłącznie dla filmu.
8. Długość, wyłącznie dla filmu, zapisana słownie, na przykład „20 minut 3 sekundy”.
9. Język napisów, wyłącznie dla filmu z pobranymi napisami.
10. Rodzaj napisów, wyłącznie dla filmu z pobranymi napisami.
11. Data importu, w czasie lokalnym.
12. Identyfikator źródła.
13. Część, wyłącznie dla źródła podzielonego, w postaci „2 z 3”.

Pole nieobecne dla danego źródła jest pomijane w całości, a nie drukowane z pustą
wartością. Pola „Adres” i „Plik” wykluczają się wzajemnie, a tekst wklejony nie ma
żadnego z nich.

Nagłówek jest oddzielony od treści dokładnie jednym pustym wierszem. Nie ma linii
ozdobnych ani separatorów ze znaków. Do wersji MD trafia w identycznej postaci
zwykłego tekstu, bez składni Markdown, ponieważ są to metadane strukturalne,
a nie treść artykułu, i nie mogą stać się nagłówkiem sekcji ani trafić do
automatycznego spisu treści notatnika.

## Pakowanie i podział plików wynikowych

Po deduplikacji, a przed zapisem, działa faza pakowania. Rozstrzyga ona, ile
plików wynikowych powstanie i które źródła trafią do którego pliku, z poszanowaniem
trzech niezależnych limitów notatnika: liczby źródeł, liczby słów w pliku oraz
rozmiaru pliku w bajtach.

### Podział źródła zbyt dużego

Źródło, którego znormalizowana treść przekracza bezpieczny limit słów albo
bezpieczny limit rozmiaru, nie jest pomijane. Jest dzielone na możliwie
najmniejszą liczbę części, każda w osobnym pliku TXT. Granica podziału wypada jak
najwyżej w hierarchii: najpierw na granicy akapitu, czyli pustego wiersza, potem
na granicy wiersza, potem na granicy zdania, a dopiero w ostateczności na granicy
słowa. Cięcie na granicy słowa oznacza cięcie wewnątrz zdania i dokłada
ostrzeżenie, które trafia do manifestu oraz do sekcji „Materiały do sprawdzenia”
w raporcie.

Każda część zachowuje ten sam identyfikator źródła i dostaje w nagłówku
metadanych wiersz „Część: N z M”. Nazwa pliku części to nazwa źródła z dopiskiem
`_czesc_N_z_M`, na przykład `raport_roczny_a1b2c3d4_czesc_2_z_3.txt`. Numer części
jest uzupełniany zerami do szerokości liczby wszystkich części, więc części
sortują się w katalogu w naturalnej kolejności także wtedy, gdy jest ich więcej
niż dziewięć.

### Łączenie małych źródeł jednej grupy

Małe źródła można łączyć w jeden plik, żeby oszczędzać sloty notatnika. Łączenie
następuje wyłącznie w obrębie grupy tematycznej nadanej przez użytkownika, nigdy
przypadkowo. W wierszu poleceń grupę nadaje opcja `--grupa NAZWA`, wspólna dla
wszystkich źródeł jednego wywołania `przetworz`. Kolejną grupę w tym samym
projekcie dodaje się osobnym wywołaniem: checkpoint kumuluje źródła między
uruchomieniami. Źródło bez nazwy grupy dostaje własny plik, dokładnie jak przed
tym etapem.

W pliku grupy przed treścią każdego fragmentu stoi jego nagłówek metadanych,
a fragmenty rozdziela wiersz „Kolejny fragment tego pliku:”. Gdy skład grupy nie
mieści się w jednym pliku, powstaje kilka plików grupy, numerowanych jak części,
a każdy zaczyna się wierszem „Plik grupy „NAZWA”, część N z M.”. Źródło należące
do grupy, ale samo przekraczające limit, jest dzielone na własne pliki-części
i nie jest łączone z pozostałymi.

Pliki części i pliki grupy powstają wyłącznie w formacie TXT. Fragment ani
kompilacja kilku źródeł nie są jednym dokumentem, więc gwarancja wiernej struktury
Markdown by tu nie obowiązywała. Decyzja jest zapisana w manifeście.

### Tematyczne pliki PDF z obrazami

Źródła będące obrazami są pakowane osobno. Grupa obrazów — nadana opcją
`--grupa`, a w jej braku domyślna grupa „Obrazy” — daje jeden tematyczny plik
PDF. W pliku każdy obraz ma osobną stronę: nagłówek metadanych, osadzony obraz
oraz opis merytoryczny wraz z tekstem OCR. Do pliku PDF osadzana jest czcionka
DejaVuSans, więc polskie znaki są czytelne niezależnie od czcionek systemu.

Obraz przed osadzeniem jest sprowadzany do RGB, ograniczany w wymiarze do
`maksymalny_wymiar_grafiki_px` i zapisywany jako JPEG o jakości `jakosc_grafik`,
żeby rozmiar pliku PDF mieścił się w limicie źródła notatnika. Grupa jest
dzielona na kilka plików PDF dopiero po przekroczeniu bezpiecznego limitu słów
albo limitu `maksymalny_rozmiar_pdf_mb`. Pojedynczy obraz zawsze tworzy własny
plik, nawet gdy sam przekracza limit — obrazu nie da się rozciąć, więc taki plik
dostaje ostrzeżenie kierujące do zmniejszenia jakości albo wymiaru grafiki.

Opis obrazu w pliku PDF jest zwykłym tekstem akapitu pod obrazem, a nie tagiem
alternatywnym: biblioteka reportlab w tym trybie nie tworzy rzeczywistej
struktury dostępności PDF, więc nazywanie opisu tagiem alt byłoby nieuczciwe.

Grupa mieszana, w której są i obrazy, i źródła tekstowe, daje dwa pliki: PDF dla
obrazów i plik tekstowy dla reszty. Taka grupa zajmuje wtedy dwa sloty
notatnika. Jest to świadomie przyjęte uproszczenie.

### Limit liczby źródeł

Limit liczby źródeł notatnika dotyczy plików do wgrania, a nie odrębnych
materiałów źródłowych. Jedno źródło podzielone na trzy części zajmuje trzy sloty,
a plik grupy łączący pięć źródeł zajmuje jeden. Tematyczny plik PDF grupy obrazów
zajmuje jeden slot niezależnie od liczby obrazów. Raport końcowy liczy
wykorzystanie limitu po sumie plików TXT i plików PDF do wgrania.

## Metadane z danych strukturalnych strony

Strony często opisują artykuł blokiem `application/ld+json` w standardzie
schema.org. Aplikacja odczytuje z niego autora, datę publikacji, datę
aktualizacji, wydawcę i opis, i uzupełnia nimi metadane z ekstraktora. Blok
o innym typie niż `Article`, `NewsArticle` albo `BlogPosting` jest pomijany,
podobnie jak blok, którego nie da się odczytać. Brak danych strukturalnych nie
jest błędem: są one dodatkiem do ekstrakcji, a nie warunkiem przetworzenia
źródła.

Pole `articleBody` jest odczytywane wyłącznie jako materiał porównawczy do oceny
jakości ekstrakcji. Nigdy nie zastępuje wyniku ekstraktora, bo serwisy wypełniają
je bardzo nierówno: bywa puste, skrócone do zajawki albo pozbawione śródtytułów.

Gdy ekstraktor i dane strukturalne podają to samo, w manifeście jest jedna
wartość. Gdy podają co innego, żadna z nich nie jest kasowana. Pod kluczem pola
zostaje wartość z ekstraktora, wartość z danych strukturalnych trafia pod klucz
z przyrostkiem `_wg_danych_strukturalnych`, a nazwy pól rozbieżnych są wymienione
pod kluczem `rozbieznosc_metadanych`. Rozbieżność jest dopisywana także do logu
szczegółowego. Ciche wybranie jednej z dwóch sprzecznych dat oznaczałoby wpisanie
do manifestu daty, której w źródle nie było.

W nagłówku pliku wynikowego pojawia się wartość z ekstraktora, ponieważ pochodzi
z tej samej ścieżki co treść. Obie wartości są w manifeście.

## Ocena jakości ekstrakcji

Źródło, z którego wyciągnięto trzysta znaków zamiast dwunastu tysięcy, wygląda
w wynikach dokładnie tak samo jak poprawne: ma plik, wpis w manifeście i sumę
kontrolną. Żeby taka cicha utrata treści dała się zauważyć, każde źródło
przechodzące przez rozpoznawanie treści dostaje ocenę jakości: „poprawna” albo
„podejrzana”.

Oceniane są strony internetowe i filmy, bo ich treść powstaje przez ekstrakcję
albo przez napisy, a od etapu czwartego także pliki PDF, DOCX, EPUB i HTML
lokalny, z tego samego powodu. Tekst wklejony oraz pliki TXT i MD nie są
oceniane, bo ich treść jest dokładnie tym, co podał użytkownik.

Obrazy mają własną, osobną ocenę: jakość tekstu rozpoznanego przez OCR. Wynik
pusty jest oceniany jako „pusta”, a wynik z wysokim udziałem znaków
nietekstowych albo słów bez samogłosek jako „podejrzana”. Obie oceny kierują
obraz do sekcji „Materiały do sprawdzenia”. Ten sam mechanizm obejmuje tekst z
OCR skanowanego pliku PDF. Plik CSV oraz
napisy z pliku SRT i VTT też nie są oceniane: z natury formatu nie mają tytułu
ani podziału na akapity, więc dostałyby nienaprawialne ostrzeżenie przy każdym
pliku. Ostrzeżenie, którego nie da się naprawić, uczyłoby tylko pomijania
wszystkich ostrzeżeń.

Ocena „podejrzana” powstaje, gdy zachodzi co najmniej jeden z warunków:

1. Treść ma mniej niż pięćdziesiąt słów.
2. Źródło nie ma tytułu.
3. Treść nie ma podziału na akapity.
4. Treść zawiera zwrot typowy dla strony błędu albo dla żądania włączenia
   skryptów.
5. Ten sam akapit powtarza się co najmniej trzy razy.
6. W oryginale jest więcej odnośników niż słów w wyniku ekstrakcji.
7. Treść z danych strukturalnych jest ponad dwa razy dłuższa od wyniku
   ekstrakcji.
8. W treści jest więcej nagłówków niż akapitów, przy co najmniej dwóch
   nagłówkach.
9. Co najmniej dwa nagłówki nie mają pod sobą żadnej treści.

Warunki ósmy i dziewiąty dotyczą tylko materiału z rozpoznaną strukturą.
Transkrypcja filmu nie ma nagłówków, więc nie może stać się przez nie podejrzana.

Źródło podejrzane jest zapisywane normalnie i nigdy nie jest kasowane ani
pomijane. Ma pliki wynikowe, ma status „spakowane” i liczy się do limitu źródeł.
Zmienia się tylko to, że użytkownik o nim wie: ocena i lista powodów trafiają do
manifestu, wpis pojawia się w logu ważnym i w logu szczegółowym, a raport końcowy
wymienia takie źródła w sekcji „Materiały do sprawdzenia”.

Progi są celowo zachowawcze. Fałszywe podejrzenie kosztuje jedno zajrzenie do
pliku, a przeoczona utrata treści kosztuje wiarygodność całej bazy wiedzy.

## Ostrzeżenia ekstraktorów

Ocena jakości jest heurystyką, czyli przypuszczeniem. Obok niej działa drugi,
niezależny mechanizm: ostrzeżenie zgłoszone wprost przez ekstraktor. Ostrzeżenie
nie jest przypuszczeniem, tylko stwierdzeniem — na przykład że plik PDF nie ma
warstwy tekstowej, że rozdziału EPUB nie dało się sparsować albo że w pliku
napisów pominięto bloki bez znacznika czasu.

Ostrzeżenie przechodzi tę samą drogę co pominięcie. Trafia jednocześnie do
checkpointu, do manifestu w obu postaciach, do logu szczegółowego, do logu
ważnego oraz do sekcji „Materiały do sprawdzenia” raportu końcowego. Wykaz
w raporcie rozdziela ostrzeżenia ekstrakcji od powodów podejrzenia, żeby nie
trzeba było zgadywać, które zdanie jest faktem, a które heurystyką. Ostrzeżenie
nie zmienia statusu źródła: źródło jest zapisywane normalnie i nie jest
kasowane. Tak dzieje się jednak tylko wtedy, gdy wynik ekstrakcji ma jakąkolwiek
treść — dotyczy to na przykład skanu PDF bez warstwy tekstowej, bo ocena jakości
i tak ocenia ten format i oznacza go jako podejrzany.

Osobnym mechanizmem, obsługiwanym przez potok, a nie przez ekstraktor, jest
wykrycie wyniku bez żadnej treści merytorycznej dla formatu celowo wyłączonego
z oceny jakości, czyli CSV oraz napisów SRT i VTT. Plik CSV bez wiersza danych
albo plik napisów bez żadnego tekstu dałby plik wynikowy zawierający wyłącznie
nagłówek metadanych, a taki plik nie wniesie nic do notatnika. Takie źródło
dostaje status „pominiete” zamiast „spakowane”, plik wynikowy dla niego nie
powstaje, a powód trafia do checkpointu, do manifestu, do obu logów oraz do
wykazu źródeł nieprzetworzonych w raporcie końcowym — tak samo jak przy
przekroczeniu limitu słów.

## Deduplikacja

Po normalizacji, a przed zapisem plików wynikowych, potok porównuje znormalizowany
tekst wszystkich źródeł i usuwa z wyników te, które są powtórzeniem innego źródła.
Etapy są trzy i można je wyłączać osobno w konfiguracji.

1. Hash treści — wykrywa teksty dokładnie identyczne po normalizacji.
2. Porównanie kosmetyczne — wykrywa teksty różniące się wyłącznie interpunkcją,
   odstępami i wielkością liter, na przykład ten sam artykuł zapisany raz z
   cudzysłowami prostymi, a raz drukarskimi.
3. Podobieństwo klasyczne — dla tekstów dłuższych SimHash na trójkach słów, dla
   krótszych porównanie sekwencyjne. Ma dwa progi. Powyżej progu pewnego duplikatu
   dublujące źródło znika z wyników. Między progiem niższym a progiem pewnego
   duplikatu oba źródła zostają, a para trafia do sekcji „Materiały do
   sprawdzenia” raportu, do rozstrzygnięcia przez człowieka.

Źródła są porównywane w kolejności rosnących identyfikatorów, więc przy grupie
powtórzeń zawsze zostaje to samo źródło, niezależnie od kolejności podania na
liście. Źródło uznane za pewny duplikat dostaje status „duplikat”, nie powstaje
dla niego plik wynikowy i nie liczy się do limitu źródeł notatnika. Jego oryginał
oraz znormalizowany tekst zostają na dysku: oryginał w podkatalogu materiałów
źródłowych, znormalizowany tekst w podkatalogu wyników pośrednich.

Każda decyzja jest audytowalna. Plik `manifest.json` zawiera tablicę
`deduplikacja` z identyfikatorem źródła zachowanego, identyfikatorem usuniętego,
metodą, wynikiem podobieństwa i uzasadnieniem. Plik `manifest.txt` pokazuje to
samo w sekcji „Decyzje deduplikacji”. Raport końcowy podaje liczbę wykrytych
duplikatów i liczbę źródeł po deduplikacji.

W tym wydaniu deduplikacja nie wycina osobno fragmentów obecnych tylko w jednej
z dwóch bardzo podobnych wersji: pole zachowanych fragmentów unikalnych zostaje
puste. Powód i warunek rewizji opisuje sekcja osiemnasta e `CLAUDE.md`. Etap
czwarty, czyli embeddingi lokalne, nie jest jeszcze zaimplementowany; jego
włączenie w konfiguracji tylko dopisuje informację do logu.

## Dwie miary liczby znaków

W manifeście występują dwie liczby znaków i mierzą co innego, dlatego noszą różne
nazwy.

1. Liczba znaków źródła, zapisana przy wpisie źródła, liczy sam znormalizowany
   tekst dokumentu. To ona służy do sprawdzania limitu notatnika.
2. Liczba znaków pliku, zapisana przy wpisie pliku wynikowego pod nazwą
   `liczba_znakow_pliku`, liczy zawartość zapisanego pliku. Jest zawsze o jeden
   większa, ponieważ każdy plik wynikowy kończy się znakiem nowej linii.

Liczby słów są w obu miejscach takie same, bo znak nowej linii nie tworzy nowego
słowa.

Obie liczby przy pliku wynikowym obejmują nagłówek metadanych, ponieważ dotyczą
zawartości pliku. Limity notatnika są natomiast sprawdzane na samej treści
dokumentu, bez nagłówka: limit słów i limit rozmiaru mówią o tym, ile materiału
niesie źródło, a nagłówek jest informacją o źródle, a nie jego treścią.

## Nazwy plików wynikowych

Nazwa pliku wynikowego składa się z trzonu tytułu, podkreślenia i pierwszych
ośmiu znaków skrótu z identyfikatora źródła, na przykład
`baza_wiedzy_dla_asystenta_ai_3f2a9c1d.txt`. Gotowa nazwa nie zawiera ciągów
podkreśleń ani podkreśleń na brzegach, ponieważ czytnik ekranu odczytuje każdy
taki znak osobno.

Trzon powstaje z tytułu dokumentu: małe litery, słowa łączone podkreśleniem,
długość najwyżej sześćdziesiąt znaków, przycięcie zawsze na granicy słowa.
Jedynym wyjątkiem jest tytuł, w którym już pierwsze słowo przekracza tę długość —
wtedy to słowo zostaje obcięte, bo inaczej trzon byłby pusty. Gdy dokument nie ma
tytułu albo tytuł po oczyszczeniu jest pusty lub zarezerwowany w systemie
Windows, trzonem staje się typ źródła, na przykład `tekst_wklejony_8d1b80c0`.

Polskie znaki diakrytyczne są zachowywane. Nazwa pliku staje się nazwą źródła
w notatniku i jest odsłuchiwana czytnikiem ekranu, więc zamiana liter na
odpowiedniki bez ogonków pogorszyłaby jej odczyt.

Skrót na końcu nazwy pełni dwie role. Wiąże plik z wpisem w manifeście bez
otwierania pliku oraz zapewnia unikalność nazwy, dzięki czemu dwa różne źródła
o identycznym tytule nie kolidują i nie jest potrzebny żaden licznik. Nazwa jest
stabilna między uruchomieniami, ponieważ identyfikator źródła jest wyprowadzany
z treści źródła, a nie z kolejności jego podania.

## Parser Markdown

Struktura plików Markdown jest rozpoznawana biblioteką `markdown-it-py`
w presecie CommonMark z jawnie włączoną regułą tabel. Tabele nie należą do
specyfikacji CommonMark, dlatego reguła jest włączana wprost — trzeci warunek
reguły wyboru formatu wymaga rozpoznania tabeli.

## Liczenie słów

Liczba słów to liczba niepustych fragmentów tekstu po podziale znormalizowanego
tekstu na dowolnych ciągach białych znaków. Ta sama definicja jest używana
wszędzie, gdzie projekt odwołuje się do limitu słów notatnika.

Źródło przekraczające bezpieczny limit słów albo bezpieczny limit rozmiaru pliku
dostaje status „pominiete”, a nie „blad”. Nie jest to awaria, tylko przypadek
jeszcze nieobsłużony: podział zbyt dużego źródła na części to zadanie etapu
szóstego. Taki sam status dostaje źródło odrzucone z powodu przekroczenia limitu
liczby źródeł w notatniku. Każde pominięcie trafia do manifestu, do raportu
końcowego i do logu szczegółowego, razem z komunikatem wyjaśniającym powód.
