# Skrypt sprawdza, które narzędzia potrzebne w projekcie Gemini Notebook Builder
# są już zainstalowane w systemie i widoczne w zmiennej PATH.
# Wynik jest wypisywany jako zwykły tekst, wiersz po wierszu, żeby dało się go
# wygodnie odczytać czytnikiem ekranu.
# Uruchomienie: w oknie PowerShell wpisz kropkę, ukośnik i nazwę pliku.

$ErrorActionPreference = "SilentlyContinue"

function Sprawdz-Narzedzie {
    param(
        [string]$Nazwa,
        [string]$Polecenie,
        [string]$Argument,
        [string]$DoCzegoSluzy
    )

    $sciezka = (Get-Command $Polecenie -ErrorAction SilentlyContinue).Source

    if ($null -eq $sciezka) {
        Write-Output "$Nazwa : BRAK. Sluzy do: $DoCzegoSluzy"
        return
    }

    $wersja = & $Polecenie $Argument 2>&1 | Select-Object -First 1
    Write-Output "$Nazwa : JEST. Wersja: $wersja"
    Write-Output "    Sciezka: $sciezka"
}

Write-Output "Raport srodowiska dla projektu Gemini Notebook Builder"
Write-Output "Data sprawdzenia: $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
Write-Output ""
Write-Output "Czesc pierwsza: narzedzia podstawowe"
Write-Output ""

Sprawdz-Narzedzie -Nazwa "Python" -Polecenie "python" -Argument "--version" -DoCzegoSluzy "uruchamianie calej aplikacji"
Sprawdz-Narzedzie -Nazwa "Git" -Polecenie "git" -Argument "--version" -DoCzegoSluzy "praca z repozytorium"

Write-Output ""
Write-Output "Wszystkie wersje Pythona zainstalowane w systemie:"
$listaPythonow = & py -0p 2>&1
if ($LASTEXITCODE -eq 0) {
    $listaPythonow | ForEach-Object { Write-Output "    $_" }
} else {
    Write-Output "    Nie udalo sie odczytac listy. Program uruchamiajacy o nazwie py moze nie byc zainstalowany."
}

Write-Output ""
Write-Output "Czesc druga: narzedzia opcjonalne"
Write-Output ""

Sprawdz-Narzedzie -Nazwa "FFmpeg" -Polecenie "ffmpeg" -Argument "-version" -DoCzegoSluzy "konwersja i przygotowanie plikow audio"
Sprawdz-Narzedzie -Nazwa "Tesseract" -Polecenie "tesseract" -Argument "--version" -DoCzegoSluzy "rozpoznawanie tekstu na skanach i obrazach"
Sprawdz-Narzedzie -Nazwa "LibreOffice" -Polecenie "soffice" -Argument "--version" -DoCzegoSluzy "konwersja plikow ODT oraz czesc obslugi PPTX"
Sprawdz-Narzedzie -Nazwa "Audiveris" -Polecenie "audiveris" -Argument "-version" -DoCzegoSluzy "rozpoznawanie zapisu nutowego z obrazow i PDF"
Sprawdz-Narzedzie -Nazwa "Java" -Polecenie "java" -Argument "-version" -DoCzegoSluzy "uruchamianie Audiveris, czyli rozpoznawanie nut ze skanow i zdjec"
Sprawdz-Narzedzie -Nazwa "MuseScore 4" -Polecenie "MuseScore4.exe" -Argument "--version" -DoCzegoSluzy "konwersja plikow MIDI i MusicXML na PDF oraz odczyt tonacji i metrum"
Sprawdz-Narzedzie -Nazwa "MuseScore 3" -Polecenie "MuseScore3.exe" -Argument "--version" -DoCzegoSluzy "starsza wersja MuseScore, alternatywa dla wersji czwartej"

Write-Output ""
Write-Output "Czesc trzecia: jezyki zainstalowane dla Tesseract"
$tesseract = (Get-Command tesseract -ErrorAction SilentlyContinue).Source
if ($null -ne $tesseract) {
    $jezyki = & tesseract --list-langs 2>&1
    $jezyki | ForEach-Object { Write-Output "    $_" }
    Write-Output ""
    if ($jezyki -contains "pol") {
        Write-Output "Jezyk polski dla Tesseract jest zainstalowany."
    } else {
        Write-Output "UWAGA: brakuje jezyka polskiego dla Tesseract. Rozpoznawanie polskich tekstow bedzie slabe."
    }
} else {
    Write-Output "    Tesseract nie jest zainstalowany, wiec nie ma czego sprawdzac."
}

Write-Output ""
Write-Output "Koniec raportu."
