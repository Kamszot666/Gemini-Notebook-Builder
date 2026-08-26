# Dokumentacja Gemini Notebook Builder

Ten katalog zawiera dokumentację użytkową projektu, po polsku. Pełne zasady
projektu, kontrakty danych i kolejność etapów opisuje `CLAUDE.md` w katalogu
głównym repozytorium — ten katalog go nie powtarza, tylko uzupełnia
o dokumentację skierowaną do osoby korzystającej z gotowej aplikacji.

## Stan dokumentacji

Po etapie pierwszym istnieją trzy dokumenty:

1. `ARCHITECTURE.md` — podział na moduły i przebieg potoku przetwarzania.
2. `CONFIGURATION.md` — pola konfiguracji obsługiwane w tej chwili, lokalizacja
   pliku `konfiguracja.toml` i zmienne środowiskowe z prefiksem `GNB_`.
3. `FORMATS.md` — obsługiwane wejścia, kodowanie tekstu oraz reguła wyboru
   między plikiem TXT a plikiem MD.

Pozostałe dokumenty wymienione w sekcji dziewiętnastej `CLAUDE.md` — `INSTALL.md`,
`ACCESSIBILITY.md`, `TROUBLESHOOTING.md` — powstaną w kolejnych etapach, razem
z funkcjami, które mają opisywać. Dokumentacja nie opisuje funkcji, których
aplikacja jeszcze nie posiada.
