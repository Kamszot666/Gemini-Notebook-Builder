# Rozwiązywanie problemów

Ten dokument opisuje problemy, które wystąpiły w rzeczywistej pracy z aplikacją,
oraz te, które wynikają wprost z jej budowy. Każdy przypadek ma tę samą budowę:
objaw, przyczyna, co zrobić.

Dokument jest pisany pod odczyt czytnikiem ekranu. Nie ma w nim tabel ani
ozdobników, a polecenia do wpisania są w osobnych blokach.

## Spis przypadków

1. Windows blokuje `pytest.exe`, `mypy.exe` albo bibliotekę DLL narzędzia
   deweloperskiego.
2. Błąd weryfikacji certyfikatu przy każdym połączeniu HTTPS.
3. `ModuleNotFoundError` przy pierwszym imporcie.
4. Ponowne uruchomienie kończy się wznowieniem i niczego nie przetwarza.
5. Źródło jest w wynikach, ale plik zawiera sam nagłówek metadanych.
6. Projekt z poprzedniej wersji aplikacji nie daje się wznowić.

## 1. Windows blokuje plik wykonywalny narzędzia deweloperskiego

Objaw. Wywołanie `pytest`, `mypy` albo `ruff` kończy się komunikatem
o zablokowaniu przez administratora, o niezaufanym wydawcy albo o braku
biblioteki DLL. Zdarza się to nagle, w środowisku, w którym te same narzędzia
działały jeszcze poprzedniego dnia.

Przyczyna. Pliki takie jak `pytest.exe` nie są programami, tylko nakładkami
generowanymi lokalnie przez `pip` w chwili instalacji. Powstają na jednym
komputerze, więc nie mają podpisu cyfrowego ani reputacji w chmurze Microsoftu.
Kontrola aplikacji Windows potrafi je z tego powodu zablokować. W tym projekcie
zdarzyło się to dwa razy: przy bibliotece DLL wymaganej przez nowszą wersję
`mypy` oraz przy pliku `pytest.exe`, którego nakładka została przepisana podczas
instalacji zależności etapu trzeciego.

Co zrobić. Uruchamiaj narzędzia jako moduły Pythona, a nie przez ich własne pliki
wykonywalne. Wywołanie `python -m` uruchamia podpisany plik `python.exe`
i ładuje narzędzie jako moduł, więc kod wykonuje się identycznie.

```powershell
python -m pytest -q
python -m mypy gnb
python -m ruff check .
python -m ruff format .
```

To nie jest obchodzenie zabezpieczenia. Zakaz omijania zabezpieczeń w tym
projekcie dotyczy paywalli, logowania i zabezpieczeń treści, a nie sposobu
uruchamiania własnego narzędzia deweloperskiego.

## 2. Błąd weryfikacji certyfikatu przy każdym połączeniu HTTPS

Objaw. Każde pobranie strony kończy się błędem weryfikacji certyfikatu, zwykle
z komunikatem zawierającym zwrot „certificate verify failed”. Dotyczy wszystkich
adresów, a nie jednego serwisu, i te same adresy otwierają się bez problemu
w przeglądarce.

Przyczyna. Ruch HTTPS jest przechwytywany po drodze. Robi tak część programów
antywirusowych z modułem skanowania połączeń szyfrowanych oraz serwery
pośredniczące w sieciach firmowych. Taki program podstawia własny certyfikat,
którego nie ma w składzie certyfikatów zaufanych używanym przez Pythona,
więc weryfikacja słusznie się nie powodzi.

Co zrobić. Wskaż aplikacji plik PEM z certyfikatem urzędu, którym posługuje się
przechwytujący program. Służy do tego pole konfiguracji `sciezka_certyfikatow`
albo zmienna środowiskowa `GNB_SCIEZKA_CERTYFIKATOW`. Plik z certyfikatem
eksportuje się z programu antywirusowego albo dostaje od administratora sieci.

Wpis w pliku `konfiguracja.toml`:

```toml
sciezka_certyfikatow = "C:/certyfikaty/firmowy.pem"
```

Nie wyłączaj weryfikacji certyfikatów. Aplikacja takiej możliwości nie ma
celowo: wyłączenie sprawdzania sprawia, że nie da się stwierdzić, czy materiał
w notatniku pochodzi z tego serwisu, który wskazałeś.

## 3. Błąd `ModuleNotFoundError` przy pierwszym imporcie

Objaw. Uruchomienie dowolnego polecenia aplikacji kończy się komunikatem
`ModuleNotFoundError` przy pierwszym imporcie, najczęściej dotyczącym pakietu
`gnb` albo jednej z zależności.

Przyczyna. Polecenie zostało wykonane bez aktywnego środowiska wirtualnego.
Uruchomiony wtedy Python systemowy nie widzi pakietów zainstalowanych w katalogu
`.venv`.

Co zrobić. Aktywuj środowisko przed pracą:

```powershell
.\.venv\Scripts\Activate.ps1
```

Jeżeli aktywacja jest zablokowana zasadami wykonywania skryptów PowerShell,
wywołaj plik `python.exe` wprost ze ścieżki środowiska. Nie wymaga to aktywacji
i działa zawsze:

```powershell
.\.venv\Scripts\python.exe -m gnb.cli diagnostyka
```

## 4. Ponowne uruchomienie kończy się wznowieniem i niczego nie przetwarza

Objaw. Polecenie `przetworz` kończy się natychmiast, raport pokazuje te same
liczby co poprzednio, a w katalogu wyników nie przybywa plików. W logu ważnym
widnieje wpis „Projekt wznowiony”.

Przyczyna. To jest zachowanie zamierzone, a nie usterka. Projekt o tej samej
nazwie ma już checkpoint, w którym wszystkie źródła mają status końcowy.
Wznowienie celowo nie przetwarza ponownie tego, co zostało ukończone, ponieważ
powtórne pobieranie i powtórna ekstrakcja kosztowałyby czas i zmieniłyby wyniki
bez powodu.

Co zrobić. Jeżeli chcesz przetworzyć materiał od nowa, uruchom polecenie
z nową nazwą projektu:

```powershell
python -m gnb.cli przetworz --projekt "Nowa nazwa" --plik SCIEZKA
```

Jeżeli chcesz dodać nowe źródła do istniejącego projektu, podaj tę samą nazwę
projektu i nowe wejścia. Źródła już przetworzone zostaną pominięte, a nowe
dojdą.

## 5. Źródło jest w wynikach, ale plik zawiera sam nagłówek metadanych

Objaw. Plik wynikowy ma kilkadziesiąt bajtów i zawiera wyłącznie nagłówek
metadanych: tytuł, typ źródła, datę importu i identyfikator. Nie ma w nim
żadnej treści.

Przyczyna. Ekstrakcja nie odczytała z pliku niczego. Typowe powody to plik PDF
bez warstwy tekstowej, czyli skan, plik CSV bez wiersza z danymi oraz plik
napisów zawierający same znaczniki czasu.

Co zrobić. Zajrzyj do raportu końcowego, do sekcji „Materiały do sprawdzenia”.
Każde takie źródło jest tam wymienione z nazwy razem z powodem. Ten sam powód
jest zapisany przy źródle w pliku `manifest.txt`, w polu ostrzeżeń, oraz w pliku
`log_szczegolowy.txt`.

Źródło nie jest kasowane i liczy się do limitu źródeł notatnika, więc plik bez
treści warto usunąć z katalogu plików wynikowych przed wgraniem materiału do
notatnika, żeby nie zajmował slotu. Rozpoznawanie tekstu ze skanu, czyli OCR,
jest zadaniem etapu ósmego i na razie nie działa.

## 6. Projekt z poprzedniej wersji aplikacji nie daje się wznowić

Objaw. Uruchomienie polecenia `przetworz` dla istniejącego katalogu projektu
kończy się komunikatem o uszkodzonym pliku checkpointu albo o pochodzeniu
projektu z nowszej wersji aplikacji.

Przyczyna. Plik `checkpoint.json` zawiera numer wersji schematu. Aplikacja czyta
pliki w wersji bieżącej oraz w wersjach starszych, które potrafi zmigrować. Nie
czyta natomiast pliku zapisanego wersją nowszą niż ta, którą uruchamiasz,
ponieważ nie ma jak odgadnąć znaczenia pól, których jeszcze nie zna.

Co zrobić. Przy komunikacie o nowszej wersji zaktualizuj aplikację do
najnowszej wersji z repozytorium. Jeżeli to niemożliwe, utwórz projekt pod inną
nazwą; katalog z poprzednim projektem pozostanie nietknięty.

Przy komunikacie o uszkodzonym pliku sprawdź, czy obok niego leży plik
`checkpoint.json.bak`. Aplikacja próbuje tej kopii samodzielnie, więc jeżeli
komunikat mimo to się pojawił, uszkodzone są oba pliki. Wtedy jedynym wyjściem
jest utworzenie projektu pod nową nazwą. Pliki wynikowe z poprzedniego przebiegu
pozostają w katalogu i nadal nadają się do wgrania do notatnika.
