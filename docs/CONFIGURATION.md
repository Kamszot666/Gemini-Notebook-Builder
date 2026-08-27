# Konfiguracja — stan po etapie trzecim

Ten dokument opisuje wyłącznie pola konfiguracji, które aplikacja faktycznie
obsługuje po etapie trzecim. Pełna lista pól z sekcji jedenastej a pliku `CLAUDE.md`, w tym progi
deduplikacji, ustawienia OCR, transkrypcji, generowania PDF oraz treść instrukcji
systemowej notatnika, powstanie w kolejnych etapach razem z funkcjami, których
dotyczy.

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
   liczby słów pojedynczego źródła. Domyślnie 480000. Margines wobec limitu
   Google wynoszącego 500000 słów istnieje dlatego, że sposób liczenia słów po
   stronie Google może różnić się od naszego.
4. `bezpieczny_limit_mb`, zmienna `GNB_BEZPIECZNY_LIMIT_MB`. Bezpieczny limit
   rozmiaru pojedynczego źródła w megabajtach. Domyślnie 190.
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
4. `znaczniki_czasu`, zmienna `GNB_ZNACZNIKI_CZASU`. Dopisywanie znacznika czasu
   na początku każdego akapitu transkrypcji. Domyślnie wyłączone. Znaczniki
   ułatwiają odnalezienie fragmentu w filmie, ale przy odsłuchu czytnikiem
   ekranu przeszkadzają, dlatego nie są domyślne.

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
znaczniki_czasu = false

uzywaj_cache = true
maksymalny_wiek_cache_dni = 30
```

Koniec przykładowego pliku konfiguracji.

## Błędy konfiguracji

Uszkodzony plik TOML oraz niepoprawna wartość, na przykład litery w miejscu
liczby, nieznany format wynikowy albo napis, którego nie da się odczytać jako
„tak” lub „nie”, kończą się błędem trwałym z komunikatem po polsku. Aplikacja nie uruchamia wtedy przetwarzania, żeby nie pracować na
niepewnych ustawieniach.
