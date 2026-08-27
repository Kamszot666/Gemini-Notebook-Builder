# Obsługiwane formaty — stan po etapie pierwszym

Ten dokument opisuje formaty wejściowe i wynikowe obsługiwane w tej chwili.
Kolejne formaty, czyli strony WWW, YouTube, PDF, DOCX, EPUB, ODT, PPTX, CSV, SRT,
VTT, obrazy oraz materiały nutowe, dojdą w etapach opisanych w sekcji osiemnastej
pliku `CLAUDE.md`.

## Wejście

W etapie pierwszym obsługiwane są trzy rodzaje wejścia:

1. Tekst wklejony bezpośrednio przez użytkownika, traktowany jako tekst płaski.
2. Tekst wklejony zadeklarowany przez użytkownika jako Markdown.
3. Plik lokalny w formacie TXT lub MD.

Plik w innym formacie kończy się kontrolowanym błędem `FormatNieobslugiwany`.
Nie zatrzymuje to przetwarzania pozostałych źródeł.

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
