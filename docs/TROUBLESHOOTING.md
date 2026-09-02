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
7. Źródło zniknęło z wyników jako duplikat, choć nie jest identyczne.
8. Podkatalog wyników pośrednich został usunięty w trakcie pracy.
9. Jedno źródło dało kilka plików z dopiskiem „czesc” w nazwie.
10. Interfejs WWW nie startuje: port jest zajęty.
11. W interfejsie nie widać postępu, a licznik znaków się nie zmienia.
12. Interfejs odrzuca wysłany plik.

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

## 7. Źródło zniknęło z wyników jako duplikat, choć nie jest identyczne

Objaw. Dla jednego z podanych źródeł nie powstał plik wynikowy. W pliku
`manifest.txt` źródło ma status `duplikat`, a w sekcji „Decyzje deduplikacji”
jest wpis z metodą i wynikiem podobieństwa.

Przyczyna. Trzeci etap deduplikacji porównuje treść i uznaje za pewny duplikat
także źródła bardzo podobne, na przykład ten sam artykuł w dwóch serwisach albo
w dwóch formatach. Próg jest ustawiony wysoko, ale przedruk z jednym
przeredagowanym zdaniem zwykle nadal przekracza próg pewnego duplikatu. Przy
takim wyniku aplikacja nie zachowuje osobno fragmentów obecnych tylko w jednej
wersji; wyjaśnia to sekcja osiemnasta e `CLAUDE.md`.

Co zrobić. Pełny opis decyzji jest w pliku `manifest.json`, w tablicy
`deduplikacja`: identyfikator źródła zachowanego, identyfikator usuniętego,
metoda, wynik podobieństwa i uzasadnienie. Znormalizowany tekst usuniętego
źródła zostaje w podkatalogu `wyniki_posrednie`, w pliku o nazwie
`identyfikator.znormalizowany.txt`, więc da się go obejrzeć i porównać ręcznie.
Jeżeli chcesz zachować oba źródła, podnieś w konfiguracji
`deduplikacja_prog_duplikatu` bliżej jedynki albo wyłącz
`deduplikacja_podobienstwo_wlaczone` i przetwórz projekt pod nową nazwą.

## 8. Podkatalog wyników pośrednich został usunięty w trakcie pracy

Objaw. Część źródeł kończy się statusem `blad` z komunikatem o braku pliku wyniku
pośredniego.

Przyczyna. Po fazie normalizacji, a przed zapisem plików wynikowych,
znormalizowany tekst każdego źródła leży w podkatalogu `wyniki_posrednie`.
Usunięcie zawartości tego podkatalogu w trakcie pracy, między fazą normalizacji a
fazą zapisu, zabiera aplikacji dane potrzebne do zbudowania pliku wynikowego bez
ponownej ekstrakcji. Aplikacja nie próbuje wtedy zgadywać treści: zapisuje
kontrolowany błąd i przechodzi dalej.

Co zrobić. Jeżeli praca została tylko przerwana, a nie dokończona, wznów projekt
tą samą listą źródeł i tą samą nazwą. Źródła, które nie zdążyły dostać statusu
`duplikat` ani `spakowane`, zostaną przetworzone od nowa: strony pobiorą się
ponownie, pliki lokalne zostaną odczytane raz jeszcze. Źródła oznaczone już jako
`blad` nie są ponawiane, więc jeśli status `blad` z tym komunikatem pojawił się
przy dokończonym projekcie, przetwórz go pod nową nazwą. Najprościej: nie usuwaj
podkatalogu `wyniki_posrednie` przed komunikatem „Projekt zakończony”.

## 9. Jedno źródło dało kilka plików z dopiskiem „czesc” w nazwie

Objaw. W katalogu `pliki_wynikowe` dla jednego materiału źródłowego powstało kilka
plików, na przykład `raport_a1b2c3d4_czesc_1_z_3.txt`, `..._czesc_2_z_3.txt`
i `..._czesc_3_z_3.txt`.

Przyczyna. To jest zachowanie zamierzone. Znormalizowana treść źródła przekroczyła
bezpieczny limit słów albo bezpieczny limit rozmiaru, więc faza pakowania
podzieliła ją na części na granicy jednostki strukturalnej. Wcześniej takie
źródło było pomijane w całości, co było cichą utratą treści.

Co zrobić. Wgraj do notatnika wszystkie części. Każda ma w nagłówku metadanych
wiersz „Część: N z M”, więc kolejność jest jednoznaczna. Jeżeli w raporcie
końcowym, w sekcji „Materiały do sprawdzenia”, przy tym źródle jest ostrzeżenie
podziału, obejrzyj styk części: znaczy to, że pojedyncze zdanie samo przekraczało
limit i cięcie wypadło na granicy słowa. Jeżeli chcesz mniejszej liczby części,
zwiększ `bezpieczny_limit_slow` w konfiguracji, pamiętając o marginesie wobec
twardego limitu notatnika wynoszącego 500000 słów.

## 10. Interfejs WWW nie startuje, bo port jest zajęty

Objaw. Polecenie `python -m gnb.ui.server` kończy się komunikatem, że nie udało
się uruchomić serwera, a port może być zajęty. Zwykle w komunikacie systemu jest
zwrot „address already in use” albo „Only one usage of each socket address”.

Przyczyna. Domyślny port 8765 jest już używany przez inny program albo przez
poprzednie, niezamknięte uruchomienie interfejsu.

Co zrobić. Zamknij poprzednie uruchomienie interfejsu, jeśli takie zostało, albo
wskaż inny port. Numer portu podajesz w pliku `konfiguracja.toml` polem
`port_nasluchu` albo zmienną środowiskową `GNB_PORT_NASLUCHU`:

```powershell
$env:GNB_PORT_NASLUCHU = "8790"
python -m gnb.ui.server
```

Adres nasłuchu musi pozostać adresem pętli zwrotnej. Wpisanie adresu spoza pętli
zwrotnej, na przykład `0.0.0.0`, kończy się błędem konfiguracji, ponieważ
interfejs nie ma uwierzytelniania i nie wolno go wystawiać do sieci.

## 11. W interfejsie nie widać postępu, a licznik znaków się nie zmienia

Objaw. Region stanu przetwarzania na stronie projektu pokazuje wciąż tę samą
treść, choć projekt się przetwarza. Licznik znaków pod polem instrukcji
systemowej nie reaguje na wpisywanie.

Przyczyna. W przeglądarce jest wyłączony JavaScript. Odświeżanie regionu postępu
i licznik znaków to jedyne dwie rzeczy w interfejsie, które go wymagają.

Co zrobić. Aktualny stan przetwarzania sprawdzasz, aktywując odnośnik „Odśwież
stan” na stronie projektu; jest to zwykły odnośnik do tej samej strony, więc
działa bez JavaScriptu. Licznik znaków instrukcji pokazuje wtedy stan z chwili
wczytania strony, a przekroczenie limitu i tak jest blokowane przy zapisie, po
stronie serwera, z czytelnym błędem przy polu. Jeżeli wolisz pełną obsługę,
włącz JavaScript dla adresu `http://127.0.0.1`.

## 12. Interfejs odrzuca wysłany plik

Objaw. Po wysłaniu formularza nowego projektu z plikiem pojawia się strona błędu
z komunikatem o zbyt dużym żądaniu albo o zbyt dużej liczbie plików.

Przyczyna. Wysłany plik przekracza bezpieczny limit rozmiaru wysyłki, domyślnie
190 megabajtów, albo liczba plików w jednym wysłaniu przekracza limit źródeł
notatnika.

Co zrobić. Przy zbyt dużym pliku sprawdź, czy to na pewno dokument tekstowy, a nie
na przykład skan w wysokiej rozdzielczości. Limit rozmiaru wysyłki zmieniasz
polem `maksymalny_rozmiar_wysylki_mb` w konfiguracji albo zmienną
`GNB_MAKSYMALNY_ROZMIAR_WYSYLKI_MB`. Pamiętaj, że pojedyncze źródło notatnika ma
twardy limit 200 megabajtów niezależnie od planu. Przy zbyt dużej liczbie plików
podziel je na kilka wysłań: checkpoint kumuluje źródła między uruchomieniami, więc
kolejne wysłanie z tą samą nazwą projektu dokłada źródła do istniejącego projektu.
