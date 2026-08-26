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

## Parser Markdown

Struktura plików Markdown jest rozpoznawana biblioteką `markdown-it-py`
w presecie CommonMark z jawnie włączoną regułą tabel. Tabele nie należą do
specyfikacji CommonMark, dlatego reguła jest włączana wprost — trzeci warunek
reguły wyboru formatu wymaga rozpoznania tabeli.

## Liczenie słów

Liczba słów to liczba niepustych fragmentów tekstu po podziale znormalizowanego
tekstu na dowolnych ciągach białych znaków. Ta sama definicja jest używana
wszędzie, gdzie projekt odwołuje się do limitu słów notatnika. Źródło
przekraczające bezpieczny limit słów jest w etapie pierwszym oznaczane błędem —
podział zbyt dużego źródła to zadanie etapu szóstego.
