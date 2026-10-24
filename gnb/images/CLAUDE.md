# Obrazy — zasady modułu gnb/images

Ten plik jest wczytywany, gdy pracujesz w katalogu `gnb/images/`. Przeniesiono go z sekcji piętnastej głównego `CLAUDE.md` bez zmiany treści.

Obrazy: obsłuż JPG, PNG, WebP, TIFF, BMP oraz statyczną klatkę GIF. Dla HEIC i HEIF potrzebna jest biblioteka `pillow-heif`. Każdy obraz ma mieć identyfikator, nazwę, źródło, tytuł, opis merytoryczny, informację o OCR i numer strony w PDF. Jeżeli narzędzie tworzy rzeczywistą strukturę dostępności PDF, wykorzystaj ją. Jeżeli nie, nie nazywaj zwykłego opisu tekstowego tagiem alt.

## Zdjęcia kartek akt (część E etapu siedemnastego)

Ustawienie `grupy_obrazow_jako_skany` (domyślnie fałsz) zmienia pakowanie grup obrazów: zamiast tematycznego pliku PDF powstaje plik MD (i TXT, jeśli włączony) z sekcją każdego skanu pod nagłówkiem drugiego poziomu z dokładną nazwą pliku. Dopiski odręczne przepisane przez osobę widzącą leżą obok zdjęcia jako `NAZWA_dopiski.txt` albo `.md` i są osobną sekcją pod odczytem OCR (`gnb/ingestion/dopiski.py`, `gnb/output/skany.py`). Pełny opis w `docs/FORMATS.md`, sekcja „Obrazy”.

Reguły, które łatwo zepsuć:

1. Odczyt OCR zwraca średnią pewność słów (`rozpoznaj_z_pewnoscia`, format TSV żądany ustawieniem `-c tessedit_create_tsv=1`, nigdy słowem `tsv`: to słowo Tesseract czyta jako plik `configs/tsv`, którego nie ma w katalogu z samymi plikami `*.traineddata`, i oddaje wtedy zwykły tekst z kodem zero; wynik niebędący TSV jest błędem trwałym, nie zerem słów). Odczyt pusty, podejrzany albo poniżej progu `ocr_prog_pewnosci` jest „nieczytelny dla OCR”: bełkot idzie do wyników pośrednich, a do pliku wynikowego tylko zdanie o braku odczytu.
2. Przy słabym pierwszym odczycie `odczytaj_strone` sprawdza obrót strony o 90, 180 i 270 stopni (`obrot_strony.py`, wykrywanie orientacji Tesseracta `--psm 0`, dane `osd.traineddata`; bez nich próby po kolei, ale tylko poniżej progu nieczytelności). Kartki leżą pod statywem obrócone, a EXIF tego nie pokazuje. Podpowiedzi orientacji się nie ufa: obrócony odczyt jest kandydatem i wygrywa tylko większą sumą pewności słów. Obrót to `rotate(-kat, expand=True)`; znak kąta pilnuje test.
3. Przygotowanie zdjęcia (`przygotowanie.py`) jest drugą próbą przy słabym pierwszym odczycie, nie krokiem stałym. Pomiar pokazał, że pogarsza odczyt drobnego, ostrego druku. Nie włączaj go przed każdym odczytem bez nowego pomiaru.
4. Skan nieczytelny nie bierze udziału w deduplikacji, bo jego tekst jest wspólnym zdaniem i wszystkie takie skany byłyby uznane za duplikaty.
5. Zdjęcia z prawdziwych akt nie mogą trafić do repozytorium ani do testów. Testy używają wyłącznie obrazów syntetycznych.
