# Instalacja — stan po etapie dziewiątym

Ten dokument opisuje przygotowanie środowiska do pracy z aplikacją: Pythona,
środowiska wirtualnego, zależności oraz narzędzi zewnętrznych. Narzędzia
zewnętrzne są podzielone na etapy, w których stają się potrzebne, więc nie
trzeba instalować wszystkiego na raz.

Dokument jest pisany pod obsługę klawiaturą i czytnik ekranu NVDA. Nie opisuje
elementów przez ich położenie na ekranie. Polecenia do wpisania są w osobnych
blokach. Ścieżki w przykładach nie zawierają nazwy konta użytkownika.

## 1. Wymagania

1. Windows 11. Aplikacja działa też na Linuksie, ale ten dokument opisuje
   Windows, bo takie jest podstawowe środowisko projektu.
2. Python w wersji 3.12 albo nowszej.
3. Około jednego gigabajta miejsca na dysku na środowisko wirtualne
   z zależnościami. Tesseract i pozostałe narzędzia zewnętrzne zajmują dodatkowe
   miejsce.

## 2. Instalacja Pythona

Najprościej przez menedżer pakietów `winget`, wbudowany w Windows 11. Otwórz
terminal — PowerShell albo Terminal Windows — i wpisz:

```powershell
winget install --id Python.Python.3.12 --exact
```

Instalator `winget` działa bez okien, więc czytnik ekranu nie musi po nim
nawigować. Po instalacji zamknij i otwórz terminal na nowo, żeby zmiana zmiennej
PATH weszła w życie, a potem sprawdź wersję:

```powershell
py -3.12 --version
```

Jeżeli wolisz instalator ze strony `python.org`, w jego oknie zaznacz pole „Add
python.exe to PATH” przed przejściem dalej. Pole to jest jednym z pierwszych
elementów okna instalatora i NVDA odczytuje je jako pole wyboru.

## 3. Pobranie repozytorium

```powershell
git clone https://github.com/Kamszot666/Gemini-Notebook-Builder.git
cd Gemini-Notebook-Builder
```

Jeżeli nie masz programu `git`, zainstaluj go poleceniem
`winget install --id Git.Git --exact` i otwórz terminal na nowo.

## 4. Środowisko wirtualne i zależności

Wszystkie polecenia wykonuj w katalogu repozytorium.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Grupa `dev` zawiera zależności aplikacji oraz narzędzia deweloperskie: `pytest`,
`ruff` i `mypy`. Jeżeli aktywacja środowiska jest zablokowana zasadami
wykonywania skryptów PowerShell, nie musisz jej wykonywać — zamiast tego
wywołuj `python.exe` wprost ze ścieżki środowiska:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Obsługa formatów obrazów HEIC i HEIF jest zależnością opcjonalną. Doinstaluj ją
tylko wtedy, gdy będziesz przetwarzać takie pliki:

```powershell
pip install -e ".[obrazy-heic]"
```

Transkrypcja nagrań mowy wymaga biblioteki faster-whisper, również zależności
opcjonalnej. Grupa `dev` już ją zawiera, więc do pracy deweloperskiej nie trzeba
nic dokładać. Do samego uruchamiania aplikacji doinstaluj ją tak:

```powershell
pip install -e ".[audio]"
```

Bez tej biblioteki wszystkie pozostałe formaty działają normalnie, a nagranie
audio dostaje status błędu z czytelnym komunikatem.

## 5. Sprawdzenie środowiska

```powershell
python -m gnb.cli diagnostyka
```

Raport wypisuje po jednym wierszu na narzędzie zewnętrzne oraz wiersz
o zainstalowanych danych językowych OCR. Brak narzędzia opcjonalnego nie jest
błędem: raport mówi, do czego służy i co przestanie działać bez niego.

Aby zapisać raport do pliku czytelnego czytnikiem ekranu, użyj opcji `--plik`
zamiast przekierowania powłoki. Przekierowanie operatorem `>` w programie
PowerShell psuje polskie znaki:

```powershell
python -m gnb.cli diagnostyka --plik raport_diagnostyki.txt
```

## 6. Narzędzia zewnętrzne według etapów

Aplikacja działa bez żadnego narzędzia zewnętrznego dla tekstu wklejonego,
plików TXT i MD, stron internetowych, napisów z serwisu YouTube oraz plików
PDF z warstwą tekstową, DOCX i EPUB. Poniższe narzędzia są potrzebne dopiero
dla konkretnych rodzajów materiału.

### Etap ósmy: Tesseract — OCR obrazów i skanów

Tesseract rozpoznaje tekst na obrazach oraz na skanowanych plikach PDF bez
warstwy tekstowej. Bez niego takie pliki są zapisywane bez rozpoznanego tekstu,
z ostrzeżeniem w raporcie.

Instalacja przez `winget`:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
```

Instalator UB Mannheim nie zawsze dopisuje Tesseract do zmiennej PATH. Jeżeli
polecenie `diagnostyka` po instalacji pokazuje „Tesseract: BRAK”, wskaż ścieżkę
wprost w konfiguracji albo zmienną środowiskową:

```powershell
$env:GNB_SCIEZKA_TESSERACT = "C:/Program Files/Tesseract-OCR/tesseract.exe"
```

Dogranie polskich danych językowych opisuje osobno sekcja siódma. Jest ono
konieczne: bez pliku `pol.traineddata` OCR polskiego tekstu daje wynik
systematycznie błędny.

### Etap dziewiąty: FFmpeg — rozkodowanie nagrań mowy

```powershell
winget install --id Gyan.FFmpeg --exact
```

FFmpeg rozkodowuje każde nagranie audio do fali dźwiękowej, zanim trafi ono do
transkrypcji. Ścieżka audio używa wyłącznie FFmpega, nie dekodera wbudowanego
w bibliotekę transkrypcji, więc dla nagrań jest on wymagany na każdym systemie.
Po instalacji uruchom nową sesję programu PowerShell, żeby zmiana zmiennej PATH
weszła w życie, i sprawdź wynik: wiersz „FFmpeg” w raporcie `python -m gnb.cli
diagnostyka` musi pokazywać wersję i ścieżkę.

Brak FFmpega nie wywraca aplikacji — nagranie audio dostaje wtedy status błędu
z czytelnym komunikatem, a pozostałe formaty źródeł są przetwarzane normalnie.

#### Model transkrypcji Whisper — pobiera się sam przy pierwszym uruchomieniu

Model rozpoznawania mowy nie jest dołączony do aplikacji ani do repozytorium.
Przy pierwszym uruchomieniu transkrypcji biblioteka faster-whisper pobiera go
z sieci. Model domyślny, czyli średni z kwantyzacją ośmiobitową, waży około
półtora gigabajta. Ląduje w katalogu pamięci podręcznej biblioteki Hugging Face
w katalogu domowym użytkownika, w podkatalogu `.cache\huggingface\hub`, i jest
pobierany tylko raz.

Pierwszego pobrania nie należy przerywać: przerwane pobranie zostawia model
w stanie, z którego trzeba go pobrać od nowa. Podczas pierwszego uruchomienia
transkrypcja może przez kilka albo kilkanaście minut stać bez znaku życia —
to jest pobieranie modelu, a nie zawieszenie.

Jeżeli zależy Ci na szybszym pierwszym uruchomieniu, ustaw tymczasowo mniejszy
model, pamiętając, że mniejszy model robi na polskim więcej błędów:

```powershell
$env:GNB_TRANSKRYPCJA_MODEL = "small"
```

Transkrypcja działa wyłącznie na procesorze. Ustawienie karty graficznej kończy
się jawnym błędem konfiguracji — powód opisuje `CONFIGURATION.md`.

### Etap dziesiąty: MuseScore, Java, Audiveris — materiały nutowe

MuseScore konwertuje pliki MIDI i MusicXML, Java uruchamia Audiveris, które
rozpoznaje zapis nutowy z obrazów. Na Windows plik wykonywalny MuseScore nie
nazywa się `mscore`, tylko `MuseScore4.exe`, i leży w podkatalogu `bin`
katalogu instalacyjnego — polecenie `diagnostyka` sprawdza obie konwencje nazw.
Etap dziesiąty nie jest jeszcze zrealizowany.

### LibreOffice — pliki ODT

LibreOffice w trybie bez okna jest potrzebny do importu plików ODT. Obsługa ODT
nie jest jeszcze zrealizowana.

## 7. Dogranie polskich danych językowych Tesseracta

Instalator UB Mannheim pozwala zaznaczyć dodatkowe języki podczas instalacji,
w gałęzi „Additional language data”. Jeżeli instalowałeś Tesseract przez
`winget` albo pominąłeś ten krok, dograj polski ręcznie.

1. Ustal katalog `tessdata` swojej instalacji Tesseracta. Zwykle jest to
   `C:\Program Files\Tesseract-OCR\tessdata`.
2. Pobierz plik `pol.traineddata` z repozytorium `tessdata_best`, które daje
   najlepszą jakość rozpoznania:
   `https://github.com/tesseract-ocr/tessdata_best/raw/main/pol.traineddata`.
3. Umieść pobrany plik w katalogu `tessdata`.

Zamiast wkładać plik do katalogu instalacji możesz trzymać go we własnym
katalogu i wskazać go aplikacji:

```powershell
$env:GNB_SCIEZKA_TESSDATA = "C:/dane/tessdata"
```

Sprawdź wynik:

```powershell
python -m gnb.cli diagnostyka
```

Wiersz „Dane językowe OCR” musi wymieniać `pol`. Jeżeli go nie ma, plik trafił
do niewłaściwego katalogu.

Domyślnym językiem OCR jest polski. Aby rozpoznawać materiał dwujęzyczny, ustaw
w konfiguracji `ocr_jezyk` na przykład na `pol+eng`; wymaga to danych językowych
obu języków.

## 8. Uruchamianie aplikacji

Interfejs WWW:

```powershell
python -m gnb.ui.server
```

Serwer nasłuchuje domyślnie pod adresem `http://127.0.0.1:8765/`, wyłącznie na
tym komputerze. Obsługę interfejsu z klawiatury i z NVDA opisuje
`ACCESSIBILITY.md`.

Wiersz poleceń:

```powershell
python -m gnb.cli przetworz --projekt "Nazwa" --plik SCIEZKA
```

Pliki obrazów i nagrania mowy podajesz tą samą opcją `--plik` co dokumenty.
Pełny wykaz opcji jest w `ARCHITECTURE.md`, a obsługiwane formaty w `FORMATS.md`.

## 9. Narzędzia deweloperskie

Narzędzia deweloperskie uruchamiaj przez `python -m`, a nie przez ich pliki
wykonywalne z katalogu `Scripts`. Wyjaśnia to `TROUBLESHOOTING.md`, przypadek
pierwszy.

```powershell
python -m pytest -q -m "not siec and not wolne"
python -m ruff check .
python -m ruff format --check .
python -m mypy gnb
```

Testy OCR pomijają się z komunikatem, gdy Tesseract nie jest zainstalowany.
Testy transkrypcji pomijają się, gdy brakuje FFmpega, biblioteki faster-whisper
albo pobranego modelu Whisper, a testy długotrwałe są domyślnie wyłączone
markerem `wolne`. Komplet testów przechodzi więc także w środowisku bez tych
narzędzi — bez ani jednego błędu, wyłącznie z pominięciami.
