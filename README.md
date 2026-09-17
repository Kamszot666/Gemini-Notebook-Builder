# Gemini Notebook Builder

Lokalna aplikacja przygotowująca uporządkowaną bazę wiedzy dla Gemini Notebook, dawniej NotebookLM.

Program pobiera i importuje materiały z wielu źródeł, wydobywa z nich treść, normalizuje ją, usuwa powtórzenia i pakuje w pliki gotowe do wgrania jako źródła notatnika. Podstawowym formatem wynikowym jest TXT. Markdown powstaje tylko wtedy, gdy struktura dokumentu rzeczywiście niesie znaczenie.

Aplikacja jest projektowana jako narzędzie dostępne dla osób niewidomych korzystających z czytnika ekranu. Dostępność jest tu wymaganiem funkcjonalnym, a nie dodatkiem.

## Stan projektu

Etapy od zerowego do jedenastego, część A, są ukończone. Potok przetwarzania obsługuje w jednym projekcie: tekst wklejony, pliki TXT i MD, adresy stron internetowych wraz z listami adresów i pamięcią podręczną, filmy z serwisu YouTube przez pobieranie napisów, dokumenty w formatach HTML, PDF, DOCX, EPUB, CSV, SRT i VTT, obrazy i skany rozpoznawane OCR-em i pakowane w tematyczne pliki PDF, nagrania mowy transkrybowane lokalnie z odrzucaniem materiału muzycznego, oraz materiały nutowe w formatach MIDI, MusicXML, Guitar Pro i w postaci skanu rozpoznawanego optycznie programem Audiveris. Każdy przebieg przechodzi przez wieloetapową deduplikację i pakowanie z uwzględnieniem trzech niezależnych limitów notatnika, zapisuje manifest, checkpoint z możliwością wznowienia i dwa pliki logów. Interfejs to lokalny, dostępny serwer WWW uruchamiany poleceniem `python -m gnb.ui.server`, z opcjonalnym globalnym skrótem klawiszowym Control plus Shift plus F12 dodającym do aktywnego projektu adres z przeglądarki albo zaznaczone pliki z Eksploratora. Szczegółową listę etapów i to, co jeszcze przed nami, opisuje sekcja osiemnasta pliku `CLAUDE.md`. Bieżący stan architektury opisuje `docs/ARCHITECTURE.md`.

## Co program ma umieć

1. Importować adresy stron internetowych, pojedynczo i w paczkach, także z pliku tekstowego z listą adresów.
2. Pobierać napisy z filmów YouTube zamiast pobierania samych filmów.
3. Przyjmować tekst wklejany bezpośrednio przez użytkownika.
4. Obsługiwać dokumenty w formatach TXT, MD, HTML, PDF, DOCX, EPUB, CSV, SRT i VTT.
5. Rozpoznawać tekst na skanach i obrazach oraz łączyć obrazy w tematyczne pliki PDF z opisami.
6. Transkrybować nagrania mowy lokalnie, bez wysyłania danych na zewnątrz, i rozpoznawać, kiedy nagranie zawiera muzykę zamiast mowy.
7. Czytać materiały nutowe w formatach MIDI, MusicXML i Guitar Pro oraz rozpoznawać zapis nutowy ze skanu i obrazu programem Audiveris, zawsze jako opis tekstowy, nigdy jako podgląd partytury.
8. Wykrywać powtórzenia wieloetapowo, zachowując informacje występujące tylko w jednym z porównywanych materiałów.
9. Pakować materiały z uwzględnieniem trzech niezależnych ograniczeń notatnika: liczby źródeł, liczby słów w źródle i rozmiaru pliku.
10. Zapisywać stan pracy tak, żeby przerwany projekt dało się wznowić bez powtarzania ukończonych etapów.
11. Prowadzić manifest pozwalający ustalić pochodzenie każdego fragmentu w każdym pliku wynikowym.
12. Udostępniać dostępny interfejs WWW oraz opcjonalny globalny skrót klawiszowy dodający materiał do aktywnego projektu bez przełączania się do aplikacji.

## Wymagania

Python w wersji 3.12 lub nowszej oraz system Windows 11. Część funkcji wymaga programów zewnętrznych: FFmpeg do obsługi audio, Tesseract do rozpoznawania tekstu, MuseScore do samego wykrycia wersji materiałów nutowych (nie jest uruchamiany), Java i Audiveris do rozpoznawania zapisu nutowego ze skanu, oraz LibreOffice, dziś wykrywany, ale bez żadnego zastosowania w aplikacji, bo obsługa formatu ODT nie jest jeszcze zrealizowana. Brak któregokolwiek z tych narzędzi wyłącza tylko odpowiadającą mu funkcję, a nie całą aplikację — pełny opis daje `python -m gnb.cli diagnostyka`.

## Dokumentacja

Zasady projektu, kontrakty danych, limity notatnika i kolejność prac opisuje plik `CLAUDE.md` w katalogu głównym.

Dokumentacja użytkownika jest w katalogu `docs/`: instalacja, konfiguracja, obsługiwane formaty, dostępność, rozwiązywanie problemów i architektura. Spis treści i kolejność lektury opisuje `docs/README.md`.

## Prywatność

Aplikacja działa w całości lokalnie. Nie wysyła danych do zewnętrznych usług sztucznej inteligencji, chyba że użytkownik świadomie to skonfiguruje. Treść pobrana ze źródeł jest traktowana wyłącznie jako dane, nigdy jako polecenie dla programu.

## Licencja

Apache License 2.0. Pełny tekst znajduje się w pliku `LICENSE` w katalogu głównym repozytorium.

Wyjątek stanowi plik `tests/dane/LICENCJA_PyGuitarPro.txt`, dotyczący wyłącznie plików testowych formatu Guitar Pro pochodzących z biblioteki PyGuitarPro, objętych licencją LGPL w wersji trzeciej.
