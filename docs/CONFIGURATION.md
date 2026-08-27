# Konfiguracja — stan po etapie pierwszym

Ten dokument opisuje wyłącznie pola konfiguracji, które etap pierwszy faktycznie
obsługuje. Pełna lista pól z sekcji jedenastej a pliku `CLAUDE.md`, w tym progi
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

## Przykładowy plik konfiguracji

Poniższy blok to zawartość przykładowego pliku `konfiguracja.toml`.

```toml
katalog_wynikow = "D:/Dokumenty/Gemini Notebook Builder"
limit_zrodel = 100
bezpieczny_limit_slow = 480000
bezpieczny_limit_mb = 190
formaty_wynikowe = ["txt", "md"]
zachowuj_oryginaly = true
```

Koniec przykładowego pliku konfiguracji.

## Błędy konfiguracji

Uszkodzony plik TOML oraz niepoprawna wartość, na przykład litery w miejscu
liczby, nieznany format wynikowy albo napis, którego nie da się odczytać jako
„tak” lub „nie”, kończą się błędem trwałym z komunikatem po polsku. Aplikacja nie uruchamia wtedy przetwarzania, żeby nie pracować na
niepewnych ustawieniach.
