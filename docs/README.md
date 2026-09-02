# Dokumentacja Gemini Notebook Builder

Ten katalog zawiera dokumentację użytkową projektu, po polsku. Pełne zasady
projektu, kontrakty danych i kolejność etapów opisuje `CLAUDE.md` w katalogu
głównym repozytorium — ten katalog go nie powtarza, tylko uzupełnia
o dokumentację skierowaną do osoby korzystającej z gotowej aplikacji.

## Stan dokumentacji

Po etapie szóstym istnieją cztery dokumenty:

1. `ARCHITECTURE.md` — podział na moduły i przebieg potoku przetwarzania, wraz
   z osobną fazą pobierania stron, podziałem potoku na fazy przez deduplikację,
   fazą pakowania oraz migracją schematu checkpointu.
2. `CONFIGURATION.md` — pola konfiguracji obsługiwane w tej chwili, lokalizacja
   pliku `konfiguracja.toml`, zmienne środowiskowe z prefiksem `GNB_`, ustawienia
   pobierania, napisów filmów, deduplikacji oraz wspólnej pamięci podręcznej.
3. `FORMATS.md` — obsługiwane wejścia, w tym adresy stron internetowych i filmów
   z serwisu YouTube, formaty dokumentowe, kodowanie tekstu, obsługa błędów
   sieciowych, ocena jakości ekstrakcji, ostrzeżenia ekstraktorów, reguła wyboru
   między plikiem TXT a plikiem MD oraz pakowanie i podział plików wynikowych.
4. `TROUBLESHOOTING.md` — objaw, przyczyna i sposób postępowania dla problemów
   napotkanych w rzeczywistej pracy: blokady narzędzi deweloperskich przez
   kontrolę aplikacji Windows, błędów weryfikacji certyfikatu, pracy bez
   aktywnego środowiska wirtualnego, wznowienia projektu, plików wynikowych bez
   treści, projektów z poprzedniej wersji aplikacji, źródeł usuniętych jako
   duplikat, usuniętego podkatalogu wyników pośrednich oraz źródeł podzielonych
   na części.

Pozostałe dokumenty wymienione w sekcji dziewiętnastej `CLAUDE.md` — `INSTALL.md`
oraz `ACCESSIBILITY.md` — powstaną w kolejnych etapach, razem z funkcjami, które
mają opisywać. Dokumentacja nie opisuje funkcji, których aplikacja jeszcze nie
posiada, a interfejs użytkownika, którego dotyczyłby dokument o dostępności, jest
zadaniem etapu siódmego.
