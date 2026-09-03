# Konfiguracja — stan po etapie dziewiątym

Ten dokument opisuje wyłącznie pola konfiguracji, które aplikacja faktycznie
obsługuje po etapie dziewiątym. Pełna lista pól z sekcji jedenastej a pliku
`CLAUDE.md` powstanie w kolejnych etapach razem z funkcjami, których dotyczy.
Treść dwóch pól
tekstowych notatnika, czyli instrukcji systemowej i promptu wyszukiwania, nie
jest polem pliku konfiguracji: zapisuje się ją razem z projektem, w pliku
`pola_notatnika.json` w katalogu projektu, przez interfejs WWW.

## Skąd pochodzą ustawienia

Konfiguracja jest budowana z trzech źródeł. Kolejność pierwszeństwa, od
najsłabszego do najsilniejszego:

1. Wartości domyślne zapisane w kodzie.
2. Plik konfiguracji w formacie TOML.
3. Zmienne środowiskowe z prefiksem `GNB_`.

Brak pliku konfiguracji nie jest błędem. Obowiązują wtedy wartości domyślne,
ewentualnie nadpisane zmiennymi środowiskowymi.

## Gdzie leży plik konfiguracji

Plik nazywa się `konfiguracja.toml` i leży poza repozytorium.

Na Windows jest to podkatalog `Gemini Notebook Builder` w katalogu wskazywanym
przez zmienną środowiskową `APPDATA`, czyli zwykle
`C:\Users\NAZWA\AppData\Roaming\Gemini Notebook Builder\konfiguracja.toml`.

Na pozostałych systemach jest to katalog zgodny ze standardem XDG: podkatalog
`gemini-notebook-builder` w katalogu wskazywanym przez `XDG_CONFIG_HOME`, a gdy
ta zmienna nie jest ustawiona, w katalogu `~/.config`.

## Obsługiwane pola

Nazwa pola w pliku TOML, odpowiadająca zmienna środowiskowa oraz znaczenie:

1. `katalog_wynikow`, zmienna `GNB_KATALOG_WYNIKOW`. Katalog nadrzędny, w którym
   powstają katalogi projektów. Domyślnie jest to podkatalog `Gemini Notebook
   Builder` w katalogu Dokumenty użytkownika, wyznaczany dynamicznie z katalogu
   domowego. Jeżeli katalog Dokumenty został przeniesiony na inny dysk albo ma
   nazwę zależną od języka systemu, ustaw to pole wprost.
2. `limit_zrodel`, zmienna `GNB_LIMIT_ZRODEL`. Maksymalna liczba źródeł w jednym
   notatniku. Domyślnie 100, co odpowiada planowi Gemini Notebook Plus.
3. `bezpieczny_limit_slow`, zmienna `GNB_BEZPIECZNY_LIMIT_SLOW`. Bezpieczny limit
   liczby słów pojedynczego pliku wynikowego. Domyślnie 480000. Margines wobec
   limitu Google wynoszącego 500000 słów istnieje dlatego, że sposób liczenia
   słów po stronie Google może różnić się od naszego. Źródło przekraczające ten
   limit nie jest pomijane: faza pakowania dzieli je na części na granicy
   jednostki strukturalnej, nigdy w środku zdania.
4. `bezpieczny_limit_mb`, zmienna `GNB_BEZPIECZNY_LIMIT_MB`. Bezpieczny limit
   rozmiaru w megabajtach. Dotyczy jednocześnie pliku wynikowego, którego treść
   przekraczająca ten limit jest dzielona na części, oraz surowego pliku
   binarnego przy wejściu — plik PDF, DOCX, EPUB, obraz albo nagranie audio tej
   wielkości jest pomijany, bo nie da się go bezpiecznie wczytać do pamięci
   w całości. Domyślnie 190. Dla plików tekstowych rozmiar surowego pliku nie
   jest ograniczeniem wejścia, bo nadmiarową treścią zajmuje się podział.
5. `formaty_wynikowe`, zmienna `GNB_FORMATY_WYNIKOWE`. Lista formatów plików
   wynikowych. Dozwolone wartości to `txt` i `md`. Format `txt` jest zawsze
   obecny, nawet gdy go nie wymienisz, bo plik TXT powstaje zawsze. Pozostawienie
   samego `txt` wyłącza generowanie wersji MD niezależnie od struktury dokumentu.
   W pliku TOML podaje się to jako listę, na przykład `["txt", "md"]`. W zmiennej
   środowiskowej jako wartości rozdzielone przecinkiem, na przykład `txt,md`.
6. `zachowuj_oryginaly`, zmienna `GNB_ZACHOWUJ_ORYGINALY`. Decyduje, czy w
   katalogu projektu ma powstawać podkatalog `materialy_zrodlowe` z kopią
   każdego przetworzonego źródła. Domyślnie włączone. Po wyłączeniu ten
   podkatalog w ogóle nie powstaje, a przetwarzanie przebiega tak samo.
   W pliku TOML podaje się wartość logiczną, na przykład `zachowuj_oryginaly =
   false`. W zmiennej środowiskowej przyjmowane są napisy `tak` i `nie`, `true`
   i `false` oraz `1` i `0`, niezależnie od wielkości liter.

7. `zachowuj_odnosniki`, zmienna `GNB_ZACHOWUJ_ODNOSNIKI`. Decyduje, czy na końcu
   treści artykułu pobranego ze strony powstaje sekcja „Odnośniki wymienione
   w artykule” z ponumerowanym wykazem adresów. Domyślnie włączone. Wyłączenie
   usuwa sam wykaz, a treść artykułu pozostaje bez zmian. Wartość podaje się tak
   samo jak w polu `zachowuj_oryginaly`.

## Pola pobierania stron internetowych

1. `nazwa_klienta`, zmienna `GNB_NAZWA_KLIENTA`. Nazwa, którą aplikacja
   przedstawia się serwerom. Domyślnie wskazuje projekt i jego repozytorium.
2. `limit_czasu_sekundy`, zmienna `GNB_LIMIT_CZASU_SEKUNDY`. Limit czasu jednego
   żądania. Domyślnie 20.
3. `liczba_ponowien`, zmienna `GNB_LICZBA_PONOWIEN`. Liczba dodatkowych prób po
   błędzie przejściowym. Domyślnie 3. Zero oznacza pracę bez ponawiania.
4. `podstawa_odstepu_sekundy`, zmienna `GNB_PODSTAWA_ODSTEPU_SEKUNDY`. Pierwszy
   odstęp przed ponowieniem, podwajany przy każdej kolejnej próbie. Domyślnie 1.
5. `maksymalny_odstep_sekundy`, zmienna `GNB_MAKSYMALNY_ODSTEP_SEKUNDY`. Sufit
   odstępu, obowiązujący także wtedy, gdy serwer poprosi o dłuższą przerwę
   nagłówkiem `Retry-After`. Domyślnie 30.
6. `odstep_miedzy_zadaniami_sekundy`, zmienna
   `GNB_ODSTEP_MIEDZY_ZADANIAMI_SEKUNDY`. Odstęp między kolejnymi żądaniami do
   tej samej domeny. Domyślnie 1. Zero jest dozwolone.
7. `polaczenia_na_domene`, zmienna `GNB_POLACZENIA_NA_DOMENE`. Maksymalna liczba
   równoczesnych połączeń do jednej domeny. Domyślnie 3.
8. `respektuj_robots`, zmienna `GNB_RESPEKTUJ_ROBOTS`. Respektowanie pliku
   `robots.txt`. Domyślnie włączone.
9. `wyjatek_robots_dla_zrodel_jawnych`, zmienna
   `GNB_WYJATEK_ROBOTS_DLA_ZRODEL_JAWNYCH`. Wyłącza kontrolę pliku `robots.txt`
   dla adresów, które podałeś wprost na liście źródeł. Domyślnie włączony.
   Adres, który program znalazłby sam w treści innego źródła, podlega kontroli
   bez wyjątku. Każde zastosowanie wyjątku jest zapisywane w
   `log_szczegolowy.txt` razem z adresem, żeby dało się je sprawdzić. Ustawienie
   wartości fałsz przywraca kontrolę dla wszystkich adresów; filmy z YouTube są
   wtedy pomijane, ponieważ serwis zabrania w swoim pliku reguł pobierania
   ścieżki `/watch`. Uzasadnienie i warunki zakresu opisuje sekcja piętnasta
   `CLAUDE.md`.
10. `maksymalny_rozmiar_pobrania_mb`, zmienna
   `GNB_MAKSYMALNY_ROZMIAR_POBRANIA_MB`. Bezpieczny limit rozmiaru pobieranego
   zasobu. Domyślnie 20. Zasób większy jest pomijany, a nie obcinany.
11. `sciezka_certyfikatow`, zmienna `GNB_SCIEZKA_CERTYFIKATOW`. Ścieżka pliku PEM
    z certyfikatami zaufanych wystawców. Domyślnie pusta, co oznacza magazyn
    wbudowany w bibliotekę HTTP. Ustaw to pole, jeżeli ruch przechodzi przez
    firmowy serwer pośredniczący albo przez program antywirusowy podstawiający
    własny certyfikat — bez tego każde pobieranie kończy się błędem weryfikacji
    certyfikatu. Plik PEM otrzymasz od administratora sieci, a na Windows możesz
    go też wyeksportować z magazynu zaufanych głównych urzędów certyfikacji przez
    przystawkę certmgr, wybierając eksport w formacie Base64 i zapisując
    z rozszerzeniem `pem`. Wskazanie nieistniejącego pliku kończy się błędem,
    a nie cichym pominięciem ustawienia. Nie ma i nie będzie ustawienia
    wyłączającego weryfikację certyfikatu, ponieważ byłoby to obejście
    zabezpieczenia, zakazane w sekcji trzeciej `CLAUDE.md`.
12. `dodatkowe_parametry_sledzace`, zmienna `GNB_DODATKOWE_PARAMETRY_SLEDZACE`.
    Dodatkowe nazwy parametrów adresu uznawanych za śledzące, usuwane obok listy
    wbudowanej. W pliku TOML lista, w zmiennej środowiskowej wartości rozdzielone
    przecinkiem.

## Pola napisów filmów

1. `jezyki_napisow`, zmienna `GNB_JEZYKI_NAPISOW`. Języki napisów w kolejności
   preferencji. Domyślnie polski i angielski. W pliku TOML lista, na przykład
   `["pl", "en"]`, a w zmiennej środowiskowej wartości rozdzielone przecinkiem.
2. `napisy_automatyczne`, zmienna `GNB_NAPISY_AUTOMATYCZNE`. Zgoda na użycie
   napisów tworzonych automatycznie, gdy nie ma napisów tworzonych ręcznie.
   Domyślnie włączona. Napisy automatyczne bywają mniej dokładne, zwłaszcza przy
   nazwach własnych.
3. `napisy_tlumaczone`, zmienna `GNB_NAPISY_TLUMACZONE`. Zgoda na użycie napisów
   przetłumaczonych automatycznie na pierwszy język z listy preferencji, gdy nie
   ma żadnych innych. Domyślnie wyłączona, ponieważ tłumaczenie maszynowe napisów
   automatycznych zwielokrotnia liczbę pomyłek.
4. `awaryjny_dowolny_jezyk`, zmienna `GNB_AWARYJNY_DOWOLNY_JEZYK`. Zgoda na
   pobranie napisów w dowolnym dostępnym języku, gdy nie ma ich w żadnym
   z preferowanych. Domyślnie włączona, ponieważ film trafił na listę źródeł
   świadomie, a napisy w innym języku są danymi poprawnymi, tylko nie
   w preferowanym języku. Użycie tego kroku jest odnotowywane w `log_wazne.txt`
   oraz w manifeście, więc podmiana języka nie jest cicha. Po wyłączeniu film bez
   napisów w preferowanych językach jest pomijany.
5. `znaczniki_czasu`, zmienna `GNB_ZNACZNIKI_CZASU`. Dopisywanie znacznika czasu
   na początku każdego akapitu transkrypcji. Domyślnie wyłączone. Znaczniki
   ułatwiają odnalezienie fragmentu w filmie, ale przy odsłuchu czytnikiem
   ekranu przeszkadzają, dlatego nie są domyślne.

## Pola deduplikacji

Deduplikacja porównuje znormalizowaną treść wszystkich źródeł i usuwa z wyników
te, które są pewnym powtórzeniem innego źródła. Kolejność etapów opisuje sekcja
szesnasta `CLAUDE.md`. Podobieństwo semantyczne, czyli embeddingi lokalne, nigdy
nie usuwa źródła samo z siebie i w tym wydaniu nie jest jeszcze zaimplementowane.

1. `deduplikacja_hash_wlaczona`, zmienna `GNB_DEDUPLIKACJA_HASH_WLACZONA`. Etap
   pierwszy: wykrycie tekstów dokładnie identycznych po normalizacji. Domyślnie
   włączony.
2. `deduplikacja_kosmetyczna_wlaczona`, zmienna
   `GNB_DEDUPLIKACJA_KOSMETYCZNA_WLACZONA`. Etap drugi: wykrycie tekstów
   różniących się wyłącznie interpunkcją, odstępami i wielkością liter. Domyślnie
   włączony.
3. `deduplikacja_podobienstwo_wlaczone`, zmienna
   `GNB_DEDUPLIKACJA_PODOBIENSTWO_WLACZONE`. Etap trzeci: podobieństwo klasyczne,
   SimHash dla tekstów dłuższych i porównanie sekwencyjne dla krótszych.
   Domyślnie włączony.
4. `deduplikacja_embeddingi_wlaczone`, zmienna
   `GNB_DEDUPLIKACJA_EMBEDDINGI_WLACZONE`. Etap czwarty: embeddingi lokalne.
   Domyślnie wyłączony. Włączenie w tym wydaniu tylko dopisuje informację do logu
   szczegółowego i nie zmienia wyniku, bo ten etap nie jest jeszcze
   zaimplementowany.
5. `deduplikacja_prog_duplikatu`, zmienna `GNB_DEDUPLIKACJA_PROG_DUPLIKATU`. Próg
   podobieństwa etapu trzeciego, od którego para jest pewnym duplikatem, a
   dublujące źródło znika z wyników. Liczba od zera wyłącznie do jednego włącznie.
   Domyślnie 0,9.
6. `deduplikacja_prog_do_przegladu`, zmienna
   `GNB_DEDUPLIKACJA_PROG_DO_PRZEGLADU`. Niższy próg etapu trzeciego. Para o
   podobieństwie między tym progiem a progiem pewnego duplikatu zostaje w całości,
   oba źródła są zapisywane, a para trafia do sekcji „Materiały do sprawdzenia”
   w raporcie. Musi być nie wyższa niż `deduplikacja_prog_duplikatu`. Domyślnie
   0,75.

## Pola rozpoznawania tekstu z obrazów i skanów

Silnikiem OCR jest wyłącznie Tesseract, wołany przez podproces. Jego brak nie
zatrzymuje aplikacji: obrazy i skany są wtedy zapisywane bez rozpoznanego
tekstu, z ostrzeżeniem.

1. `ocr_wlaczony`, zmienna `GNB_OCR_WLACZONY`. Włączenie OCR obrazów i skanów.
   Domyślnie włączone.
2. `ocr_jezyk`, zmienna `GNB_OCR_JEZYK`. Język OCR w notacji Tesseracta.
   Domyślnie `pol`. Kilka języków naraz podaje się przez plus, na przykład
   `pol+eng`. Wymagany jest odpowiedni plik danych językowych Tesseracta;
   polecenie `diagnostyka` wypisuje listę zainstalowanych.
3. `ocr_psm`, zmienna `GNB_OCR_PSM`. Tryb segmentacji strony Tesseracta, liczba
   od 0 do 13. Domyślnie 3, czyli automatyczna segmentacja bez orientacji.
4. `ocr_rozdzielczosc_pdf_dpi`, zmienna `GNB_OCR_ROZDZIELCZOSC_PDF_DPI`.
   Rozdzielczość rasteryzacji stron skanowanego pliku PDF przed OCR. Domyślnie
   300. Wyższa wartość poprawia rozpoznanie i wydłuża pracę.
5. `ocr_liczba_procesow`, zmienna `GNB_OCR_LICZBA_PROCESOW`. Liczba równoległych
   procesów Tesseracta przy OCR wielu stron skanu. Domyślnie 0, czyli wartość
   dobrana z liczby rdzeni pomniejszonej o jeden, nie więcej niż cztery i nie
   mniej niż jeden. Jeden rdzeń zostaje wolny z powodu dostępnościowego, nie
   wydajnościowego: przy pełnym obciążeniu wszystkich rdzeni synteza mowy
   czytnika ekranu się zacina, a użytkownik właśnie wtedy słucha komunikatów
   o postępie OCR. Wpisanie wartości większej od zera podnosi liczbę procesów
   ręcznie i znosi ten margines.
6. `sciezka_tesseract`, zmienna `GNB_SCIEZKA_TESSERACT`. Pełna ścieżka pliku
   wykonywalnego Tesseracta. Domyślnie pusta, co oznacza odnalezienie go w
   zmiennej PATH oraz w znanych miejscach instalacji na Windows.
7. `sciezka_tessdata`, zmienna `GNB_SCIEZKA_TESSDATA`. Katalog danych językowych
   Tesseracta. Domyślnie pusty, co oznacza katalog wskazany przez samo narzędzie.
   Wskazanie nieistniejącego katalogu jest błędem konfiguracji.

## Pola transkrypcji nagrań mowy

Transkrypcję wykonuje biblioteka faster-whisper na modelu Whisper. Rozkodowanie
nagrania do fali dźwiękowej robi program FFmpeg — jest on wymagany dla nagrań
na każdym systemie.

1. `transkrypcja_wlaczona`, zmienna `GNB_TRANSKRYPCJA_WLACZONA`. Włączenie
   transkrypcji nagrań mowy. Domyślnie prawda. Przy wartości fałsz nagranie
   audio dostaje status „pominiete” z czytelnym powodem.
2. `transkrypcja_model`, zmienna `GNB_TRANSKRYPCJA_MODEL`. Nazwa modelu Whisper:
   `tiny`, `base`, `small`, `medium` albo `large-v3`. Domyślnie `medium`. Model
   średni robi na polskim zauważalnie mniej błędów niż mały, a błędna
   transkrypcja to cicha korupcja materiału źródłowego — ten sam argument, dla
   którego przy OCR wybrano dane językowe „best” zamiast „fast”. Zmiana na
   mniejszy model to zmiana tej jednej wartości, bez dotykania kodu.
3. `transkrypcja_jezyk`, zmienna `GNB_TRANSKRYPCJA_JEZYK`. Kod języka mowy
   w nagraniu, na przykład `pl`. Domyślnie `pl`.
4. `transkrypcja_urzadzenie`, zmienna `GNB_TRANSKRYPCJA_URZADZENIE`. Urządzenie
   obliczeniowe. Dopuszczalne są wyłącznie wartości `procesor` i `cpu`, obie
   znaczą to samo. Domyślnie `procesor`. Ustawienie karty graficznej kończy się
   jawnym błędem konfiguracji: aktualna macierz zgodności ROCm dla systemu
   Windows nie wymienia grafiki zintegrowanej Vega w procesorach serii 7030,
   a stos DirectML to osobny ciężki stos natywny. Aplikacja nie przełącza po
   cichu z powrotem na procesor, bo cicha podmiana jest gorsza niż jawna odmowa.
5. `transkrypcja_typ_obliczen`, zmienna `GNB_TRANSKRYPCJA_TYP_OBLICZEN`. Typ
   obliczeń modelu, na przykład `int8`, `int8_float32` albo `float32`. Domyślnie
   `int8`, czyli kwantyzacja ośmiobitowa — najszybsza na procesorze.
6. `transkrypcja_liczba_watkow`, zmienna `GNB_TRANSKRYPCJA_LICZBA_WATKOW`. Liczba
   wątków procesora dla transkrypcji. Domyślnie 0, czyli wartość dobrana z liczby
   rdzeni pomniejszonej o jeden, nie mniej niż jeden. Jeden rdzeń zostaje wolny
   z powodu dostępnościowego, nie wydajnościowego: przy pełnym obciążeniu
   wszystkich rdzeni synteza mowy czytnika ekranu się zacina, a użytkownik
   właśnie wtedy słucha komunikatów o postępie. Wpisanie wartości większej od
   zera podnosi liczbę wątków ręcznie i znosi ten margines. Tak samo dobierana
   jest liczba procesów OCR.
7. `transkrypcja_prog_vad`, zmienna `GNB_TRANSKRYPCJA_PROG_VAD`. Próg filtra
   wykrywania aktywności mowy Silero, liczba od zera wyłącznie do jednego
   włącznie. Domyślnie 0,5. Wyższa wartość odrzuca więcej cichych fragmentów.
8. `transkrypcja_prog_udzialu_mowy`, zmienna `GNB_TRANSKRYPCJA_PROG_UDZIALU_MOWY`.
   Najmniejszy udział mowy w długości nagrania, przy którym nagranie jest
   uznawane za mowę i przechodzi do transkrypcji. Liczba od zera do jednego
   włącznie. Domyślnie 0,5. Nagranie poniżej tego progu jest pomijane jako
   materiał niemowny. Wartość zero oznacza „nigdy nie odrzucaj”, czyli globalny
   odpowiednik opcji `--wymus-transkrypcje` z wiersza poleceń. To jest
   heurystyka, a nie klasyfikator muzyki: utwór ze śpiewem może częściowo
   zarejestrować się jako mowa.

## Pola grafiki i generowanych plików PDF

1. `jakosc_grafik`, zmienna `GNB_JAKOSC_GRAFIK`. Jakość zapisu obrazów jako JPEG
   w tematycznym pliku PDF, liczba od 1 do 100. Domyślnie 85. Niższa wartość
   zmniejsza plik PDF kosztem szczegółów obrazu.
2. `maksymalny_wymiar_grafiki_px`, zmienna `GNB_MAKSYMALNY_WYMIAR_GRAFIKI_PX`.
   Największy dopuszczalny dłuższy bok obrazu osadzanego w PDF. Domyślnie 2600.
   Większy obraz jest proporcjonalnie zmniejszany.
3. `maksymalny_rozmiar_pdf_mb`, zmienna `GNB_MAKSYMALNY_ROZMIAR_PDF_MB`. Limit
   rozmiaru pojedynczego tematycznego pliku PDF. Domyślnie 190. Grupa obrazów
   przekraczająca ten limit jest dzielona na kilka plików PDF; pojedynczego
   obrazu nie da się podzielić, więc taki plik dostaje ostrzeżenie.

## Pola interfejsu WWW

Interfejs uruchamiasz poleceniem `python -m gnb.ui.server`.

1. `adres_nasluchu`, zmienna `GNB_ADRES_NASLUCHU`. Adres, na którym nasłuchuje
   serwer interfejsu. Domyślnie `127.0.0.1`. Dozwolone są wyłącznie adresy pętli
   zwrotnej: `127.0.0.1`, `localhost` oraz `::1`. Wartość spoza tej listy kończy
   się błędem trwałym, ponieważ sekcja jedenasta `CLAUDE.md` zakazuje nasłuchu na
   innym adresie, dopóki interfejs nie ma uwierzytelniania.
2. `port_nasluchu`, zmienna `GNB_PORT_NASLUCHU`. Numer portu interfejsu.
   Domyślnie 8765. Numer musi mieścić się w przedziale od 1 do 65535.
3. `limit_znakow_instrukcji_systemowej`, zmienna
   `GNB_LIMIT_ZNAKOW_INSTRUKCJI_SYSTEMOWEJ`. Maksymalna liczba znaków pola
   instrukcji systemowej notatnika. Domyślnie 10000, zgodnie z sekcją jedenastą a
   `CLAUDE.md`. Interfejs pokazuje licznik użytych znaków i blokuje zapis treści
   dłuższej niż limit.
4. `maksymalny_rozmiar_wysylki_mb`, zmienna `GNB_MAKSYMALNY_ROZMIAR_WYSYLKI_MB`.
   Bezpieczny limit rozmiaru pliku wysyłanego przez formularz interfejsu.
   Domyślnie 190. Żądanie z większą treścią jest odrzucane, a nie obcinane.

## Pamięć podręczna pobranych stron

Pamięć podręczna jest wspólna dla wszystkich projektów i leży w katalogu danych
aplikacji, obok pliku konfiguracji, a nie wewnątrz katalogu projektu. Dzięki temu
ten sam artykuł użyty w dwóch notatnikach pobiera się tylko raz.

1. `uzywaj_cache`, zmienna `GNB_UZYWAJ_CACHE`. Włączenie pamięci podręcznej.
   Domyślnie włączona.
2. `maksymalny_wiek_cache_dni`, zmienna `GNB_MAKSYMALNY_WIEK_CACHE_DNI`. Wiek,
   po którym wpis jest usuwany przy kolejnym uruchomieniu. Domyślnie 30 dni.
   Ustawienie istnieje po to, żeby plik nie rósł bez końca.
3. `sciezka_cache`, zmienna `GNB_SCIEZKA_CACHE`. Ścieżka pliku SQLite. Domyślnie
   plik `cache.sqlite3` w katalogu danych aplikacji.

Ścieżkę pliku, stan i liczbę zapamiętanych zasobów pokazuje polecenie:

```powershell
python -m gnb.cli pamiec
```

Koniec polecenia pokazującego stan pamięci podręcznej.

Całą zawartość usuwa polecenie:

```powershell
python -m gnb.cli pamiec --wyczysc
```

Koniec polecenia czyszczącego pamięć podręczną.

Treść stron jest zapisywana w postaci skompresowanej biblioteką zlib, a nazwa
użytej metody kompresji trafia do rekordu. Dzięki temu metodę da się później
zmienić bez unieważniania całej bazy, a wpisy zapisane wcześniej bez kompresji
nadal dają się odczytać. Gdy kompresja nie zmniejsza rozmiaru, zapisywana jest
postać pierwotna.

Plik ma włączony tryb WAL oraz limit czasu oczekiwania na blokadę, ponieważ dwa
uruchomienia aplikacji mogą sięgnąć do niego naraz. Zajętość bazy jest traktowana
jako błąd przejściowy, a nie jako awaria przetwarzania. W bazie zapisany jest
numer wersji schematu. Znane starsze wersje są migrowane z zachowaniem
zawartości, a wersja nieznana jest świadomie odrzucana, ponieważ zawartość zawsze
można odtworzyć, pobierając zasób ponownie.

## Przykładowy plik konfiguracji

Poniższy blok to zawartość przykładowego pliku `konfiguracja.toml`.

```toml
katalog_wynikow = "D:/Dokumenty/Gemini Notebook Builder"
limit_zrodel = 100
bezpieczny_limit_slow = 480000
bezpieczny_limit_mb = 190
formaty_wynikowe = ["txt", "md"]
zachowuj_oryginaly = true
zachowuj_odnosniki = true

nazwa_klienta = "GeminiNotebookBuilder/0.1 (+https://github.com/Kamszot666/Gemini-Notebook-Builder)"
limit_czasu_sekundy = 20
liczba_ponowien = 3
podstawa_odstepu_sekundy = 1
maksymalny_odstep_sekundy = 30
odstep_miedzy_zadaniami_sekundy = 1
polaczenia_na_domene = 3
respektuj_robots = true
wyjatek_robots_dla_zrodel_jawnych = true
maksymalny_rozmiar_pobrania_mb = 20
sciezka_certyfikatow = ""
dodatkowe_parametry_sledzace = []

jezyki_napisow = ["pl", "en"]
napisy_automatyczne = true
napisy_tlumaczone = false
awaryjny_dowolny_jezyk = true
znaczniki_czasu = false

deduplikacja_hash_wlaczona = true
deduplikacja_kosmetyczna_wlaczona = true
deduplikacja_podobienstwo_wlaczone = true
deduplikacja_embeddingi_wlaczone = false
deduplikacja_prog_duplikatu = 0.9
deduplikacja_prog_do_przegladu = 0.75

ocr_wlaczony = true
ocr_jezyk = "pol"
ocr_psm = 3
ocr_rozdzielczosc_pdf_dpi = 300
ocr_liczba_procesow = 0
sciezka_tesseract = ""
sciezka_tessdata = ""

transkrypcja_wlaczona = true
transkrypcja_model = "medium"
transkrypcja_jezyk = "pl"
transkrypcja_urzadzenie = "procesor"
transkrypcja_typ_obliczen = "int8"
transkrypcja_liczba_watkow = 0
transkrypcja_prog_vad = 0.5
transkrypcja_prog_udzialu_mowy = 0.5

jakosc_grafik = 85
maksymalny_wymiar_grafiki_px = 2600
maksymalny_rozmiar_pdf_mb = 190

uzywaj_cache = true
maksymalny_wiek_cache_dni = 30

adres_nasluchu = "127.0.0.1"
port_nasluchu = 8765
limit_znakow_instrukcji_systemowej = 10000
maksymalny_rozmiar_wysylki_mb = 190
```

Koniec przykładowego pliku konfiguracji.

## Błędy konfiguracji

Uszkodzony plik TOML oraz niepoprawna wartość, na przykład litery w miejscu
liczby, nieznany format wynikowy albo napis, którego nie da się odczytać jako
„tak” lub „nie”, kończą się błędem trwałym z komunikatem po polsku. Aplikacja nie uruchamia wtedy przetwarzania, żeby nie pracować na
niepewnych ustawieniach.
