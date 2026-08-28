# Obsługiwane formaty — stan po etapie trzecim

Ten dokument opisuje formaty wejściowe i wynikowe obsługiwane w tej chwili.
Kolejne formaty, czyli PDF, DOCX, EPUB, ODT, PPTX, CSV, SRT, VTT, obrazy oraz
materiały nutowe, dojdą w etapach opisanych w sekcji osiemnastej pliku
`CLAUDE.md`.

## Wejście

Obsługiwane jest pięć rodzajów wejścia:

1. Tekst wklejony bezpośrednio przez użytkownika, traktowany jako tekst płaski.
2. Tekst wklejony zadeklarowany przez użytkownika jako Markdown.
3. Plik lokalny w formacie TXT lub MD.
4. Adres strony internetowej, podany pojedynczo albo listą.
5. Adres filmu z serwisu YouTube, dla którego pobierane są napisy.

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
MD. Plik TXT zawiera sam tekst transkrypcji; nagłówek metadanych w pliku
wynikowym powstanie wspólnie dla wszystkich typów źródeł w etapie czwartym A.

### Przypadki, w których film nie zostaje przetworzony

Statusem „pominiete” kończą się: brak napisów w wybranych językach, napisy
złożone wyłącznie z oznaczeń dźwięków, playlista, kanał oraz adres YouTube bez
identyfikatora filmu. Przy braku napisów komunikat odsyła do etapu dziewiątego,
w którym powstanie transkrypcja mowy z samego dźwięku.

Statusem „blad” kończą się: film prywatny, usunięty, niedostępny w regionie,
ograniczony wiekiem oraz niepoprawny identyfikator filmu. Zablokowanie żądania
przez serwis i błąd sieci są traktowane jako błędy przejściowe i ponawiane.

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

Pole nieobecne dla danego źródła jest pomijane w całości, a nie drukowane z pustą
wartością. Pola „Adres” i „Plik” wykluczają się wzajemnie, a tekst wklejony nie ma
żadnego z nich.

Nagłówek jest oddzielony od treści dokładnie jednym pustym wierszem. Nie ma linii
ozdobnych ani separatorów ze znaków. Do wersji MD trafia w identycznej postaci
zwykłego tekstu, bez składni Markdown, ponieważ są to metadane strukturalne,
a nie treść artykułu, i nie mogą stać się nagłówkiem sekcji ani trafić do
automatycznego spisu treści notatnika.

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
albo przez napisy. Tekst wklejony oraz pliki TXT i MD nie są oceniane, bo ich
treść jest dokładnie tym, co podał użytkownik. Ostrzeżenie, którego nie da się
naprawić, uczyłoby tylko pomijania wszystkich ostrzeżeń.

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
