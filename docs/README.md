# Dokumentacja Gemini Notebook Builder

Ten katalog zawiera dokumentację użytkową projektu, po polsku. Pełne zasady
projektu, kontrakty danych i kolejność etapów opisuje `CLAUDE.md` w katalogu
głównym repozytorium — ten katalog go nie powtarza, tylko uzupełnia
o dokumentację skierowaną do osoby korzystającej z gotowej aplikacji.

## Stan dokumentacji

Po etapie siódmym istnieje pięć dokumentów:

1. `ARCHITECTURE.md` — podział na moduły i przebieg potoku przetwarzania, wraz
   z osobną fazą pobierania stron, podziałem potoku na fazy przez deduplikację,
   fazą pakowania, migracją schematu checkpointu oraz pakietem interfejsu WWW.
2. `CONFIGURATION.md` — pola konfiguracji obsługiwane w tej chwili, lokalizacja
   pliku `konfiguracja.toml`, zmienne środowiskowe z prefiksem `GNB_`, ustawienia
   pobierania, napisów filmów, deduplikacji, wspólnej pamięci podręcznej oraz
   interfejsu WWW.
3. `FORMATS.md` — obsługiwane wejścia, w tym adresy stron internetowych i filmów
   z serwisu YouTube, formaty dokumentowe, kodowanie tekstu, obsługa błędów
   sieciowych, ocena jakości ekstrakcji, ostrzeżenia ekstraktorów, reguła wyboru
   między plikiem TXT a plikiem MD oraz pakowanie i podział plików wynikowych.
4. `ACCESSIBILITY.md` — obsługa dostępnego interfejsu WWW z klawiatury i z NVDA,
   zachowanie regionów o roli „status”, dławienie komunikatów postępu, pola
   instrukcji systemowej i promptu wyszukiwania, wznowienie projektu.
5. `TROUBLESHOOTING.md` — objaw, przyczyna i sposób postępowania dla problemów
   napotkanych w rzeczywistej pracy: blokady narzędzi deweloperskich przez
   kontrolę aplikacji Windows, błędów weryfikacji certyfikatu, pracy bez
   aktywnego środowiska wirtualnego, wznowienia projektu, plików wynikowych bez
   treści, projektów z poprzedniej wersji aplikacji, źródeł usuniętych jako
   duplikat, usuniętego podkatalogu wyników pośrednich, źródeł podzielonych
   na części oraz zajętego portu interfejsu.

Dokument `INSTALL.md` wymieniony w sekcji dziewiętnastej `CLAUDE.md` nadal nie
powstał. Przygotowanie środowiska deweloperskiego opisuje na razie sekcja piąta
`CLAUDE.md`.

## Interfejs WWW

Interfejs uruchamiasz poleceniem `python -m gnb.ui.server`. Otwiera on lokalny
serwer, domyślnie pod adresem `http://127.0.0.1:8765/`, dostępny wyłącznie z tego
komputera. W przeglądarce podajesz źródła, obserwujesz dławiony postęp, wznawiasz
niedokończone projekty i zapisujesz dwa pola tekstowe notatnika. Cała praca przez
interfejs jest równoważna poleceniu `python -m gnb.cli przetworz`. Szczegóły
obsługi z klawiatury i z czytnikiem ekranu opisuje `ACCESSIBILITY.md`.
