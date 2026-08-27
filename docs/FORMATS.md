# Obsługiwane formaty — stan po etapie drugim

Ten dokument opisuje formaty wejściowe i wynikowe obsługiwane w tej chwili.
Kolejne formaty, czyli YouTube, PDF, DOCX, EPUB, ODT, PPTX, CSV, SRT, VTT, obrazy
oraz materiały nutowe, dojdą w etapach opisanych w sekcji osiemnastej pliku
`CLAUDE.md`.

## Wejście

Obsługiwane są cztery rodzaje wejścia:

1. Tekst wklejony bezpośrednio przez użytkownika, traktowany jako tekst płaski.
2. Tekst wklejony zadeklarowany przez użytkownika jako Markdown.
3. Plik lokalny w formacie TXT lub MD.
4. Adres strony internetowej, podany pojedynczo albo listą.

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

Odnośniki wewnątrz zdań nie są zachowywane, ponieważ adres w środku zdania
utrudnia odsłuchanie tekstu czytnikiem ekranu. Pochodzenie całego artykułu jest
zapisane w manifeście: adres kanoniczny, adres końcowy po przekierowaniach, kod
odpowiedzi HTTP, deklarowane kodowanie oraz nagłówki `ETag` i `Last-Modified`.

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

## Wynik: TXT zawsze, MD warunkowo

Plik TXT powstaje zawsze. Plik MD powstaje dodatkowo tylko wtedy, gdy spełnione
są jednocześnie dwa warunki.

Warunek pierwszy: dokument spełnia co najmniej dwa z czterech warunków
strukturalnych:

1. Zawiera co najmniej trzy nagłówki tworzące rzeczywistą hierarchię co najmniej
   dwupoziomową.
2. Zawiera co najmniej dwie listy, z których przynajmniej jedna ma co najmniej
   trzy elementy.
3. Zawiera co najmniej jedną tabelę.
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

## Nazwy plików wynikowych

Nazwa pliku wynikowego składa się z trzonu tytułu, dwóch podkreśleń i pierwszych
ośmiu znaków skrótu z identyfikatora źródła, na przykład
`baza_wiedzy_dla_asystenta_ai__3f2a9c1d.txt`.

Trzon powstaje z tytułu dokumentu: małe litery, słowa łączone podkreśleniem,
długość najwyżej sześćdziesiąt znaków, przycięcie zawsze na granicy słowa.
Jedynym wyjątkiem jest tytuł, w którym już pierwsze słowo przekracza tę długość —
wtedy to słowo zostaje obcięte, bo inaczej trzon byłby pusty. Gdy dokument nie ma
tytułu albo tytuł po oczyszczeniu jest pusty lub zarezerwowany w systemie
Windows, trzonem staje się typ źródła, na przykład `tekst_wklejony__8d1b80c0`.

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
