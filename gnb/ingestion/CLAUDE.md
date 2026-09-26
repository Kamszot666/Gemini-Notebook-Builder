# Pobieranie stron, robots.txt, listy adresów i YouTube — zasady modułu gnb/ingestion

Ten plik jest wczytywany, gdy pracujesz w katalogu `gnb/ingestion/`. Dotyczy też adapterów `gnb/extractors/strona_www.py` i `gnb/extractors/youtube.py`. Przeniesiono go z sekcji piętnastej głównego `CLAUDE.md` bez zmiany treści.

Strony WWW: podstawowym ekstraktorem jest trafilatura, z mechanizmem zapasowym. Respektuj `robots.txt`, ustaw rozpoznawalny User-Agent, ogranicz współbieżność do najwyżej trzech połączeń na domenę i stosuj odstęp między żądaniami. Politykę wobec odpowiedzi serwera na żądanie pliku `robots.txt` opisuje RFC 9309, sekcja 2.3.1: kod z rodziny 2xx oznacza obowiązujące reguły, kod z rodziny 4xx, w tym 401 i 403, oznacza brak reguł, czyli zgodę, a kod z rodziny 5xx oraz błąd sieci oznaczają reguły nieokreślone, czyli pełny zakaz po wyczerpaniu ponowień.

### Wyjątek dla źródeł wskazanych jawnie

Decyzja: kontrola `robots.txt` nie obowiązuje dla adresów, które użytkownik podał wprost na liście źródeł. Obowiązuje bez zmian dla wszystkich adresów, które program znalazłby sam w treści innego źródła.

Uzasadnienie: protokół Robots Exclusion, opisany w RFC 9309, jest adresowany do klientów automatycznych, które odkrywają adresy samodzielnie i przeszukują serwis. Ten program działa inaczej: wykonuje pojedyncze, jawne polecenie człowieka dotyczące jednego wskazanego zasobu. To jest zachowanie agenta użytkownika, a nie robota przeszukującego. Plik `robots.txt` nie jest ani paywallem, ani logowaniem, ani zabezpieczeniem technicznym, więc zakaz z sekcji trzeciej niniejszej instrukcji go nie obejmuje.

Zakres wyjątku. Cztery warunki, które muszą być spełnione łącznie:

1. Adres pochodzi bezpośrednio z listy źródeł podanej przez użytkownika.
2. Pobierany jest dokładnie ten jeden zasób, bez przechodzenia po odnośnikach.
3. Zastosowanie wyjątku jest zapisywane w `log_szczegolowy.txt` przy każdym użyciu, razem z adresem, żeby dało się to zaudytować.
4. Wyjątek da się wyłączyć w konfiguracji.

Klucz konfiguracji: `wyjatek_robots_dla_zrodel_jawnych`, wartość logiczna, domyślnie prawda, zmienna środowiskowa `GNB_WYJATEK_ROBOTS_DLA_ZRODEL_JAWNYCH`. Przy wartości fałsz kontrola obowiązuje wszystkie adresy bez wyjątku, a film z YouTube zostaje pominięty ze statusem informującym o zakazie w `robots.txt`.

Zastrzeżenie pierwsze: wyjątek nie jest uzasadniony tym, że korzystamy wyłącznie z interfejsu napisów, a nie ze stron serwisu. Byłoby to nieprawdziwe, ponieważ druga warstwa pobierania, czyli `yt-dlp`, sięga po stronę `/watch`. Wyjątek dotyczy obu warstw, a jego jedynym uzasadnieniem jest charakter działania programu opisany wyżej.

Zastrzeżenie drugie: warunki korzystania z serwisu są zagadnieniem odrębnym od `robots.txt` i program ich nie ocenia. Odpowiedzialność za zgodność użycia z warunkami serwisu spoczywa na użytkowniku narzędzia.

Implementacja: wyjątek jest ogólnym mechanizmem opartym na pochodzeniu adresu, a nie warunkiem na domenę `youtube.com`. Żaden serwis nie jest traktowany szczególnie; szczególne jest to, skąd adres pochodzi.

Adresy z plików: automatycznie pobierane są adresy z plików TXT, MD i DOCX, i to wyłącznie adresy jawne, czyli zapisane w widocznym tekście i zaczynające się od http:// albo https://. Decyzja użytkownika, nie otwieraj jej ponownie: odnośnik ukryty pod innym tekstem jest pomijany, nie czytaj celów odnośników z relacji DOCX ani z pól HYPERLINK, a w Markdown usuwaj cele `[tekst](adres)` i definicje odnośników. Z plików HTML, HTM, XHTML, MHTML i MHT adresy nie są pobierane w ogóle. Plik złożony wyłącznie z adresów jest listą źródeł jawnych; adresy z treści zwykłego pliku nie są jawne i podlegają `robots.txt` oraz limitowi `limit_adresow_z_pliku`. Zachowanie jest wspólne dla interfejsu WWW i polecenia `przetworz --plik` (`gnb/ingestion/adresy_z_plikow.py`).

Import listy adresów: pole URL oraz importowany plik TXT muszą przyjmować pojedynczy adres, wiele adresów rozdzielonych spacjami oraz wiele adresów w osobnych wierszach. Przed rozpoczęciem przetwarzania pokaż użytkownikowi podsumowanie: liczbę wykrytych adresów, liczbę poprawnych, liczbę duplikatów oraz liczbę prawdopodobnie błędnych. Duplikaty wykrywaj po kanonicznej postaci adresu, czyli po usunięciu parametrów śledzących i ujednoliceniu zapisu. Użytkownik ma zobaczyć to podsumowanie zanim cokolwiek zostanie pobrane, bo to jest moment, w którym najtaniej wychwycić pomyłkę.

YouTube: preferuj napisy zamiast pobierania filmu. Używaj `yt-dlp` oraz `youtube-transcript-api` jako warstw wzajemnie zapasowych, ponieważ obie potrafią przestać działać po zmianach po stronie serwisu. Obsłuż napisy ręczne i automatyczne, brak napisów, film prywatny, film usunięty, błędny URL i błąd sieci. Zapisz tytuł, kanał, URL, język, typ napisów, datę importu i długość, jeżeli są dostępne.
