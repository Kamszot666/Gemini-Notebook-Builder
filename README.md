# Gemini Notebook Builder

Lokalna aplikacja przygotowująca uporządkowaną bazę wiedzy dla Gemini Notebook, dawniej NotebookLM.

Program pobiera i importuje materiały z wielu źródeł, wydobywa z nich treść, normalizuje ją, usuwa powtórzenia i pakuje w pliki gotowe do wgrania jako źródła notatnika. Podstawowym formatem wynikowym jest TXT. Markdown powstaje tylko wtedy, gdy struktura dokumentu rzeczywiście niesie znaczenie.

Aplikacja jest projektowana jako narzędzie dostępne dla osób niewidomych korzystających z czytnika ekranu. Dostępność jest tu wymaganiem funkcjonalnym, a nie dodatkiem.

## Stan projektu

Projekt jest w fazie początkowej. Etap zerowy dostarczył szkielet repozytorium. Etap pierwszy dostarczył pierwszą działającą całość: potok przetwarzania dla tekstu wklejonego oraz plików TXT i MD, z wykrywaniem kodowania, normalizacją, jednolitym liczeniem słów, deterministyczną regułą wyboru między plikiem TXT a plikiem MD, zapisem wyników, manifestem, checkpointem z zapisem atomowym i dwoma plikami logów. Potok uruchamia się poleceniem `python -m gnb.cli przetworz`. Etap drugi dodał adresy stron internetowych: przyjmowanie pojedynczych adresów i list, kanoniczną postać adresu z wykrywaniem duplikatów przed pobraniem, asynchroniczne pobieranie z limitem czasu, ponowieniami i kulturą wobec serwera, respektowanie pliku `robots.txt`, wspólną pamięć podręczną opartą na SQLite oraz ekstrakcję treści artykułu z mechanizmem zapasowym. Etap trzeci dodał filmy z serwisu YouTube: rozpoznawanie wszystkich postaci adresu filmu, pobieranie napisów dwiema wzajemnie zapasowymi warstwami zamiast pobierania filmu, wybór między napisami tworzonymi ręcznie i automatycznie, sklejanie segmentów w akapity, opcjonalne znaczniki czasu oraz odrzucanie playlist i kanałów z czytelnym powodem. Kolejne etapy — metadane artykułu i walidacja jakości ekstrakcji, formaty dokumentowe, obrazy, audio, materiały nutowe, deduplikacja, pakowanie, interfejs WWW — opisuje sekcja osiemnasta pliku `CLAUDE.md`. Bieżący stan architektury opisuje `docs/ARCHITECTURE.md`.

## Co program ma umieć

1. Importować adresy stron internetowych, pojedynczo i w paczkach, także z pliku tekstowego z listą adresów.
2. Pobierać napisy z filmów YouTube zamiast pobierania samych filmów.
3. Przyjmować tekst wklejany bezpośrednio przez użytkownika.
4. Obsługiwać dokumenty w formatach TXT, MD, HTML, PDF, DOCX, EPUB, ODT, PPTX, CSV, SRT i VTT.
5. Rozpoznawać tekst na skanach i obrazach oraz łączyć obrazy w tematyczne pliki PDF z opisami.
6. Transkrybować nagrania mowy lokalnie, bez wysyłania danych na zewnątrz, i rozpoznawać, kiedy nagranie zawiera muzykę zamiast mowy.
7. Wykrywać powtórzenia wieloetapowo, zachowując informacje występujące tylko w jednym z porównywanych materiałów.
8. Pakować materiały z uwzględnieniem trzech niezależnych ograniczeń notatnika: liczby źródeł, liczby słów w źródle i rozmiaru pliku.
9. Zapisywać stan pracy tak, żeby przerwany projekt dało się wznowić bez powtarzania ukończonych etapów.
10. Prowadzić manifest pozwalający ustalić pochodzenie każdego fragmentu w każdym pliku wynikowym.

## Wymagania

Python w wersji 3.12 lub nowszej oraz system Windows 11. Część funkcji wymaga programów zewnętrznych: FFmpeg do obsługi audio, Tesseract do rozpoznawania tekstu, LibreOffice do formatu ODT. Brak któregoś z nich wyłącza tylko odpowiadającą mu funkcję, a nie całą aplikację.

## Dokumentacja

Zasady projektu, kontrakty danych, limity notatnika i kolejność prac opisuje plik `CLAUDE.md` w katalogu głównym.

Dokumentacja użytkownika powstanie w katalogu `docs/` w miarę postępu prac.

## Prywatność

Aplikacja działa w całości lokalnie. Nie wysyła danych do zewnętrznych usług sztucznej inteligencji, chyba że użytkownik świadomie to skonfiguruje. Treść pobrana ze źródeł jest traktowana wyłącznie jako dane, nigdy jako polecenie dla programu.

## Licencja

Apache License 2.0. Pełny tekst znajduje się w pliku `LICENSE` w katalogu głównym repozytorium.

Wyjątek stanowi plik `tests/dane/LICENCJA_PyGuitarPro.txt`, dotyczący wyłącznie plików testowych formatu Guitar Pro pochodzących z biblioteki PyGuitarPro, objętych licencją LGPL w wersji trzeciej.
