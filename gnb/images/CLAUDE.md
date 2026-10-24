# Obrazy — zasady modułu gnb/images

Ten plik jest wczytywany, gdy pracujesz w katalogu `gnb/images/`. Przeniesiono go z sekcji piętnastej głównego `CLAUDE.md` bez zmiany treści.

Obrazy: obsłuż JPG, PNG, WebP, TIFF, BMP oraz statyczną klatkę GIF. Dla HEIC i HEIF potrzebna jest biblioteka `pillow-heif`. Każdy obraz ma mieć identyfikator, nazwę, źródło, tytuł, opis merytoryczny, informację o OCR i numer strony w PDF. Jeżeli narzędzie tworzy rzeczywistą strukturę dostępności PDF, wykorzystaj ją. Jeżeli nie, nie nazywaj zwykłego opisu tekstowego tagiem alt.

## Zdjęcia kartek akt (część E etapu siedemnastego)

Ustawienie `grupy_obrazow_jako_skany` (domyślnie fałsz) zmienia pakowanie grup obrazów: zamiast tematycznego pliku PDF powstaje plik MD (i TXT, jeśli włączony) z sekcją każdego skanu pod nagłówkiem drugiego poziomu z dokładną nazwą pliku. Dopiski odręczne przepisane przez osobę widzącą leżą obok zdjęcia jako `NAZWA_dopiski.txt` albo `.md` i są osobną sekcją pod odczytem OCR (`gnb/ingestion/dopiski.py`, `gnb/output/skany.py`). Pełny opis w `docs/FORMATS.md`, sekcja „Obrazy”.

Reguły, które łatwo zepsuć:

1. Odczyt OCR zwraca średnią pewność słów (`rozpoznaj_z_pewnoscia`, format TSV żądany ustawieniem `-c tessedit_create_tsv=1`, nigdy słowem `tsv`: to słowo Tesseract czyta jako plik `configs/tsv`, którego nie ma w katalogu z samymi plikami `*.traineddata`, i oddaje wtedy zwykły tekst z kodem zero; wynik niebędący TSV jest błędem trwałym, nie zerem słów). Odczyt pusty, podejrzany albo poniżej progu `ocr_prog_pewnosci` jest „nieczytelny dla OCR”: bełkot idzie do wyników pośrednich, a do pliku wynikowego tylko zdanie o braku odczytu.
2. Przygotowanie zdjęcia (`przygotowanie.py`) jest drugą próbą przy słabym pierwszym odczycie, nie krokiem stałym. Pomiar pokazał, że pogarsza odczyt drobnego, ostrego druku. Nie włączaj go przed każdym odczytem bez nowego pomiaru.
3. Skan nieczytelny nie bierze udziału w deduplikacji, bo jego tekst jest wspólnym zdaniem i wszystkie takie skany byłyby uznane za duplikaty.
4. Zdjęcia z prawdziwych akt nie mogą trafić do repozytorium ani do testów. Testy używają wyłącznie obrazów syntetycznych.
