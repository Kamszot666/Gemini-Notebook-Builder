# Gemini Notebook Builder

Lokalna aplikacja na Windows 11, która zbiera materiały z wielu źródeł, wydobywa z nich treść, porządkuje ją, usuwa powtórzenia i pakuje w pliki gotowe do wgrania jako źródła w Gemini Notebook, dawniej NotebookLM.

Ten dokument jest pisany do czytania linearnie, także syntezatorem mowy. Nie zawiera tabel, rysunków ze znaków ani ozdobników. Każda sekcja ma nagłówek, po którym możesz przechodzić klawiszem H w NVDA.

## Priorytet numer jeden: dostępność dla osób niewidomych

Ta aplikacja powstaje dla osoby niewidomej, która pracuje na Windows 11 z czytnikiem ekranu NVDA. Dostępność nie jest dodatkiem na końcu prac, tylko wymaganiem funkcjonalnym: funkcja, której nie da się obsłużyć z klawiatury z czytnikiem ekranu, jest w tym projekcie uznawana za niedziałającą.

Co to oznacza w praktyce:

1. Interfejs to zwykła strona WWW zbudowana z prawdziwych elementów HTML: przycisków, odnośników, pól formularza, nagłówków i list. Nie ma elementów, które wymagałyby myszy.
2. Każde pole ma etykietę, którą NVDA odczytuje, a nie tylko tekst podpowiedzi. Błędy formularza są powiązane z polem i pojawiają się także jako lista tekstowa, na którą przechodzi fokus po nieudanym wysłaniu.
3. Postęp długich operacji jest ogłaszany w regionie stanu, w krótkich podsumowaniach, na przykład „Przetworzono 12 z 40 źródeł”, nie częściej niż co kilka sekund. Nie ma lawiny komunikatów.
4. Fokus nie skacze sam. Przenosi się tylko po Twoim działaniu.
5. Ciemny motyw, wysoki kontrast, duża czcionka, brak informacji przekazywanej samym kolorem, poszanowanie ustawienia ograniczenia animacji.
6. Wszystkie adresy internetowe na stronach aplikacji są klikalnymi odnośnikami.
7. Skrót klawiszowy działa w tle i potwierdza wynik dźwiękiem, żeby nie zabierać fokusu z przeglądarki. Dwa różne dźwięki: sukces to dwa krótkie, rosnące tony, porażka to jeden niski, dłuższy ton. Ostatni wynik jest też zapisany jako tekst na stronie.
8. Raporty i manifesty są zwykłym tekstem czytanym linearnie, bez tabel.
9. Dokumentacja opisuje elementy po nazwie i roli, nigdy po położeniu na ekranie.

Pełny opis obsługi z klawiaturą i NVDA jest w `docs/ACCESSIBILITY.md`.

## Do czego to służy

Gemini Notebook przyjmuje ograniczoną liczbę źródeł. Według oficjalnej strony pomocy Google, sprawdzonej 26 września 2026, jest to 50 źródeł w planie bezpłatnym, 100 w planie Plus, 300 w Pro, a w planach Ultra 500 albo 600. Pojedyncze źródło może mieć do 500 000 słów albo 200 MB. Google zaznacza, że te wartości mogą się zmieniać, więc w aplikacji są ustawieniem, a nie stałą.

Przy takich limitach zwykły sposób pracy, czyli jedno źródło to jeden dodany plik albo adres, szybko zużywa miejsce. Kilkadziesiąt krótkich artykułów, notatek i zdjęć potrafi wypełnić cały notatnik, a wiele z tych materiałów jest małych i mogłoby się zmieścić razem w jednym źródle.

Gemini Notebook Builder rozwiązuje ten problem. Zbiera materiały, wyciąga z nich sam tekst, usuwa powtórzenia i łączy małe materiały tematycznie w duże pliki, pilnując wszystkich trzech limitów naraz: liczby źródeł, liczby słów w źródle i rozmiaru pliku. Każdy fragment w połączonym pliku ma nagłówek z pochodzeniem, więc nic nie traci identyfikowalności.

## Zalety i korzyści

1. Oszczędność miejsca w notatniku. Liczba zajętych źródeł zależy od liczby grup tematycznych, a nie od liczby materiałów. Wyliczenia są w osobnej sekcji poniżej.
2. Więcej formatów, niż przyjmuje sam Notebook. Aplikacja czyta dokumenty biurowe, arkusze, strony zapisane z przeglądarki, napisy, archiwa ZIP, a nawet zapis nutowy. Wykaz jest w sekcji o formatach.
3. Usuwanie powtórzeń. Ten sam artykuł podany dwa razy, w dwóch adresach albo w dwóch formatach, nie zajmie dwóch miejsc. Deduplikacja ma kilka etapów, od identycznego skrótu treści po podobieństwo. Podobieństwo znaczeniowe nigdy nie usuwa źródła samo, tylko oznacza je do Twojej decyzji. Jeśli dwa źródła mają część wspólną i część unikalną, informacje unikalne są zachowane.
4. Czysty tekst zamiast śmieci. Ze stron są usuwane menu, banery cookies, reklamy i stopki. Zostaje treść artykułu, a adresy cytowane przez autora trafiają do osobnej sekcji na końcu, żeby nie przerywały zdań czytnikowi ekranu.
5. Pełna identyfikowalność. Manifest zapisuje, skąd pochodzi każde źródło, jaką metodą wydobyto treść, co uznano za duplikat i w którym pliku wynikowym trafiło. Każde pominięcie i każde ostrzeżenie trafia jednocześnie do logu, manifestu i raportu, więc nic nie ginie po cichu.
6. Odporność na przerwanie. Praca jest zapisywana w pliku checkpointu, więc przerwany projekt wznawia się bez powtarzania ukończonych etapów. Jeden uszkodzony plik albo jeden niedziałający adres nie zatrzymuje całego projektu.
7. Ochrona przed przekroczeniem limitów. Źródło większe niż limit jest dzielone na części na granicy nagłówka lub akapitu, nigdy w środku zdania. Aplikacja nie dopycha plików sztucznie do limitu: limit jest sufitem, nie celem.
8. Prywatność. Wszystko działa lokalnie. OCR, transkrypcja nagrań mowy i deduplikacja odbywają się na Twoim komputerze. Aplikacja nie wysyła danych do zewnętrznych usług sztucznej inteligencji, chyba że sam to świadomie skonfigurujesz. Treść pobrana ze źródeł jest traktowana wyłącznie jako dane, nigdy jako polecenie.
9. Szacunek dla witryn. Domyślnie respektowany jest plik robots.txt, z jawnym wyjątkiem dla adresów, które wskazujesz sam. Aplikacja nie omija paywalli ani logowania.
10. Trzy sposoby dodawania materiału: interfejs WWW, globalny skrót klawiszowy i terminal. Opisane niżej.

## Dostępność offline i własna baza

Jedno wyjaśnienie na początek: sam Gemini Notebook działa w internecie. Offline działa to, co powstaje po stronie tej aplikacji, i to jest osobna, trwała wartość.

1. Wszystko, co aplikacja tworzy, to zwykłe pliki na Twoim dysku: pliki TXT, w razie potrzeby MD i PDF, manifest w formacie JSON i tekstowy, raport, logi i checkpoint. Otwierasz je dowolnym edytorem, czytnikiem ekranu, wyszukiwarką plików lub programem do notatek, bez internetu i bez konta.
2. Zachowywane są też oryginały źródeł, na przykład surowy plik HTML pobranej strony, o ile nie wyłączysz tej opcji w konfiguracji. Strona, która zniknie z sieci, zostaje u Ciebie.
3. Interfejs WWW działa całkowicie lokalnie. Nie ładuje żadnych zasobów z zewnętrznych serwerów, więc jest szybki, przewidywalny dla czytnika ekranu i działa bez internetu. Serwer nasłuchuje tylko na tym komputerze, pod adresem 127.0.0.1.
4. Internet jest potrzebny wyłącznie do pobierania stron i napisów z YouTube oraz do wgrania gotowych plików do Notebooka. Przetwarzanie plików lokalnych, w tym OCR skanów i transkrypcja nagrań mowy, odbywa się bez sieci. Model transkrypcji pobiera się jednorazowo przy pierwszym użyciu.
5. Kopia zapasowa i przenoszenie to zwykłe kopiowanie katalogu projektu. Ten sam zbiór można wgrać do kilku notatników albo wrócić do niego po latach.
6. Pamięć podręczna pobranych stron jest wspólna dla projektów: strona, która się nie zmieniła, nie jest pobierana drugi raz.

## Wyliczenia oszczędności miejsca

Uwaga o rzetelności: poniższe liczby to arytmetyka na jawnie podanych założeniach, a nie pomiary Twoich materiałów. Realna oszczędność zależy od tego, ile masz materiałów, jak są duże i jak je pogrupujesz. Po każdym przebiegu aplikacja sama podaje procent wykorzystania limitu źródeł i największy plik wynikowy w raporcie, więc możesz sprawdzić własne liczby.

Zasada, na której to działa: bez aplikacji każdy materiał zajmuje jedno źródło. Z aplikacją źródło zajmuje jedna grupa tematyczna albo jeden plik wynikowy. Jeden plik wynikowy może pomieścić do 480 000 słów, a więc na przykład 400 artykułów po 1 200 słów.

Przykład pierwszy, artykuły. Założenia: 250 krótkich artykułów, każdy około 1 200 słów, razem 300 000 słów, w pięciu grupach tematycznych po 50 artykułów. Sposób tradycyjny: 250 źródeł, czyli 250 procent limitu planu Plus. Taki zbiór mieści się dopiero w planie Pro (300 źródeł), i to prawie bez zapasu na inne materiały. Z aplikacją: pięć plików po około 60 000 słów, czyli 5 źródeł, 5 procent limitu Plus. Zaoszczędzone miejsca: 245 z 250, czyli 98 procent.

Przykład drugi, zdjęcia i skany. Założenia: 60 zdjęć stron dokumentów w trzech tematach po 20. Sposób tradycyjny: 60 źródeł. Z aplikacją: obrazy z jednej grupy trafiają do jednego tematycznego pliku PDF z opisami i tekstem rozpoznanym OCR, więc 3 źródła. Zaoszczędzone miejsca: 57 z 60, czyli 95 procent. Dodatkowo tekst ze zdjęć jest wyszukiwalny i czytelny dla czytnika ekranu.

Przykład trzeci, mieszany zbiór. Założenia: 100 materiałów, z czego 20 jest powtórzeniami tego samego tekstu z innego adresu lub w innym formacie, a pozostałe 80 układa się w 8 grup. Sposób tradycyjny: 100 źródeł, czyli cały limit planu Plus. Z aplikacją: 20 powtórzeń nie dostaje własnych plików, a 80 materiałów zajmuje 8 źródeł. Zaoszczędzone miejsca: 92 ze 100. Liczba 20 powtórzeń jest założeniem przykładu, nie średnią.

Wniosek: przy grupowaniu tematycznym 100 miejsc planu Plus wystarcza na zbiór, który bez grupowania przekroczyłby nawet 300 miejsc planu Pro, a limit 500 000 słów na źródło przestaje być ograniczeniem, bo aplikacja dzieli za duże materiały bezpiecznie na części.

Oszczędność objętości w bajtach jest zjawiskiem innego rodzaju: plik wynikowy zawiera sam tekst, bez znaczników HTML, stylów, skryptów, reklam ani osadzonych obrazów, więc jest zwykle znacznie mniejszy od strony, PDF-a z grafiką czy dokumentu biurowego, z którego pochodzi. Nie podaję tu procentu, bo zależy od materiału. Rozmiary pojedynczych plików wynikowych są w manifeście.

## Formaty: co można dodać dodatkowo

Według oficjalnej strony pomocy Google, sprawdzonej 26 września 2026, Notebook przyjmuje wprost: DOCX, TXT, Markdown, PDF, CSV, PPTX, dokumenty, arkusze i prezentacje Google, EPUB, wklejony tekst, dźwięk (na przykład MP3 i WAV), obrazy (między innymi JPG, PNG, WebP, HEIC, TIFF, BMP, GIF), adresy stron oraz publiczne filmy z YouTube z napisami. Notebook nie przyjmuje nagrań bez mowy, stron za paywallem ani PDF-ów zabezpieczonych przed kopiowaniem.

Aplikacja czyta wszystko z tej listy, co potrafi przetworzyć lokalnie, a dodatkowo formaty, których nie ma na liście Google. Wszystko sprowadza do plików TXT, MD albo PDF, które Notebook przyjmuje.

Dodatkowo, względem listy Google, aplikacja obsługuje:

1. Strony zapisane z przeglądarki w jednym pliku: MHTML i MHT. Wygodne dla stron za logowaniem albo budowanych skryptami: zapisujesz stronę już wyświetloną w przeglądarce i podajesz plik.
2. Pliki HTML, HTM i XHTML zapisane na dysku.
3. Dokumenty OpenDocument: ODT, ODS i ODP.
4. Arkusze Excela: XLSX, XLSM i stary XLS, a także TSV.
5. Stare formaty Microsoft Office: DOC i PPT, przez LibreOffice, oraz RTF.
6. Napisy SRT i VTT.
7. Pliki tekstu prostego: JSON, XML, YAML, YML, TOML, INI, CFG i LOG.
8. Archiwa ZIP, z ochroną przed złośliwymi archiwami: limity liczby plików, rozmiaru, stopnia kompresji i zagłębienia oraz ochrona ścieżek.
9. Listy adresów: plik TXT złożony wyłącznie z adresów jest listą źródeł, z której pobierane są wszystkie strony. Adres zaczynający się od www. jest przyjmowany bez schematu. Adresy znalezione w treści zwykłych plików TXT i MD są także pobierane, z kontrolą robots.txt.
10. Materiały muzyczne w postaci zapisu: pliki MIDI, MusicXML i skompresowany MXL, formaty Guitar Pro 3, 4 i 5, a także skany nut i tabulatur w PDF lub obrazach, rozpoznawane programem Audiveris. Wynik zawsze jest opisem tekstowym: taktowania, tonacji, dźwięków, tabulatury. Nagrania utworów muzycznych jako dźwięku nie są obsługiwane.

Dodatkowo, dla formatów wspólnych z Notebookiem, aplikacja daje coś, czego on nie daje:

1. Skany PDF bez warstwy tekstowej i obrazy są rozpoznawane OCR i wracają jako tekst, który można przeszukać i odczytać czytnikiem ekranu.
2. Nagrania mowy są transkrybowane lokalnie, z odrzucaniem nagrań muzycznych i szumu.
3. Napisy z YouTube są pobierane jako tekst, z zapisem tytułu, kanału i języka, a nie odsyłaczem do filmu.
4. Wiele małych źródeł jest łączonych w jeden plik z nagłówkiem pochodzenia przy każdym fragmencie.

Szczegółowy opis każdego formatu, jego ograniczeń i ostrzeżeń jest w `docs/FORMATS.md`.

## Instalacja

Wymagania: Windows 11, Python 3.12 lub nowszy, około jednego gigabajta wolnego miejsca. Polecenia wpisuj w PowerShell. Każdy blok poleceń kończy się wyraźnie, żeby czytnik ekranu nie mieszał go z opisem.

Krok pierwszy, Python. Poniższe polecenie instaluje go menedżerem winget, wbudowanym w Windows 11.

```powershell
winget install --id Python.Python.3.12 --exact
```

Zamknij i otwórz terminal, a potem sprawdź wersję:

```powershell
py -3.12 --version
```

Koniec bloku poleceń.

Krok drugi, pobranie repozytorium. Jeśli nie masz programu git, zainstaluj go poleceniem `winget install --id Git.Git --exact` i otwórz terminal ponownie.

```powershell
git clone https://github.com/Kamszot666/Gemini-Notebook-Builder.git
cd Gemini-Notebook-Builder
```

Koniec bloku poleceń.

Krok trzeci, środowisko wirtualne i zależności.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Koniec bloku poleceń. Jeśli aktywacja środowiska jest zablokowana zasadami PowerShell, pomiń drugą linię i wywołuj Pythona wprost, na przykład `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.

Krok czwarty, sprawdzenie środowiska. To polecenie wypisuje raport o narzędziach zewnętrznych. Dla każdego brakującego mówi, do czego służy i co przestanie działać bez niego.

```powershell
python -m gnb.cli diagnostyka
```

Koniec bloku poleceń.

Krok piąty, narzędzia zewnętrzne. Są opcjonalne. Bez żadnego z nich aplikacja działa dla tekstu, stron, YouTube, PDF z tekstem, DOCX, EPUB, formatów OpenDocument, arkuszy, RTF, MHTML i archiwów ZIP. Brak narzędzia wyłącza tylko odpowiadającą mu funkcję i daje czytelny komunikat.

1. Tesseract: OCR obrazów i skanów. Potrzebne są też polskie dane językowe.
2. FFmpeg: dekodowanie nagrań mowy.
3. LibreOffice: tylko dla starych formatów DOC i PPT.
4. Java i Audiveris: rozpoznawanie nut ze skanów.

Zależności opcjonalne Pythona doinstalujesz grupami: `pip install -e ".[audio]"` dla transkrypcji, `pip install -e ".[nuty]"` dla MIDI i Guitar Pro, `pip install -e ".[obrazy-heic]"` dla HEIC. Szczegóły, w tym dogranie polskich danych Tesseracta, opisuje `docs/INSTALL.md`.

Uwaga dla użytkowników z włączoną kontrolą aplikacji Windows: narzędzia deweloperskie uruchamiaj przez `python -m`, na przykład `python -m pytest`, a nie przez pliki z katalogu Scripts.

## Konfiguracja

Konfiguracja jest opcjonalna, bo aplikacja ma sensowne wartości domyślne. Ustawienia pochodzą z trzech miejsc, od najsłabszego do najsilniejszego: wartości domyślne w kodzie, plik TOML, zmienne środowiskowe z prefiksem GNB_. Zmienna środowiskowa zawsze wygrywa.

Plik konfiguracji nazywa się `konfiguracja.toml` i leży poza repozytorium, w podkatalogu `Gemini Notebook Builder` katalogu wskazywanego przez zmienną APPDATA, czyli zwykle w `C:\Users\NAZWA\AppData\Roaming\Gemini Notebook Builder`. Brak pliku nie jest błędem.

Najważniejsze ustawienia:

1. `katalog_wynikow`: gdzie powstają projekty. Domyślnie podkatalog `Gemini Notebook Builder` w Dokumentach.
2. `limit_zrodel`: liczba źródeł notatnika. Domyślnie 100, plan Plus. Wpisz 50, 300, 500 albo 600 dla innych planów.
3. `bezpieczny_limit_slow` i `bezpieczny_limit_mb`: domyślnie 480 000 słów i 190 MB, z marginesem względem limitów Google.
4. `formaty_wynikowe`: `["txt", "md"]` włącza warunkowe generowanie wersji Markdown. TXT powstaje zawsze.
5. `zachowuj_oryginaly`: czy zachowywać kopie oryginałów. Domyślnie tak.
6. `respektuj_robots` i `wyjatek_robots_dla_zrodel_jawnych`: zasady wobec pliku robots.txt.
7. Progi deduplikacji, OCR, transkrypcji, ścieżki do narzędzi zewnętrznych i limity archiwów ZIP.
8. `globalny_skrot_wlaczony`: włącza albo wyłącza globalny skrót klawiszowy.

Przykład zmiennej środowiskowej dla jednej sesji PowerShell:

```powershell
$env:GNB_LIMIT_ZRODEL = "300"
```

Koniec bloku poleceń. Pełny wykaz pól z przykładowym plikiem jest w `docs/CONFIGURATION.md`.

## Jak uruchomić aplikację

Interfejs WWW uruchamiasz poleceniem:

```powershell
python -m gnb.ui.server
```

Koniec bloku poleceń. Serwer wypisze adres, domyślnie `http://127.0.0.1:8765/`. Otwórz go w przeglądarce. Serwer zatrzymasz klawiszami Control plus C w oknie terminala. Uruchamiaj tylko jeden serwer naraz: drugi nie zdoła zająć globalnego skrótu.

## Jak dodawać źródła

### Sposób pierwszy: interfejs WWW

Strona główna ma formularz nowego projektu. Pola po kolei:

1. Nazwa projektu, wymagana. Staje się nazwą katalogu z wynikami, więc podaj krótką, na przykład „Podatki 2026”.
2. Nazwa grupy tematycznej, wymagana. Źródła jednego wysłania z tą samą grupą trafiają do możliwie najmniejszej liczby plików. Pole podpowiada grupy, które projekt już zna.
3. Tekst wklejony. Pole wielowierszowe.
4. Adresy stron i filmów, po jednym w wierszu. Adres z www. na początku jest przyjmowany bez https.
5. Pliki z dysku. Pole wyboru pliku, w którym można wskazać wiele plików naraz. Otwiera zwykłe okno wyboru pliku Windows.

Musisz podać co najmniej jedno źródło. Przycisk „Utwórz projekt i rozpocznij przetwarzanie” wysyła formularz. Strona projektu pokazuje postęp w regionie stanu, potem podsumowanie i raport.

Na stronie projektu możesz:

1. Dosłać kolejne źródła formularzem pod raportem.
2. Przejść po liście źródeł, gdzie każde ma własny nagłówek i własne działania: oznaczyć jako zweryfikowane, zastąpić treść własnym plikiem albo usunąć z projektu.
3. Oznaczyć źródło z ostrzeżeniem jako zweryfikowane. Jeśli pochodzi z sieci, aplikacja pobierze je jeszcze raz.
4. Usunąć źródło jednym przyciskiem, bez wpisywania potwierdzenia.
5. Wpisać instrukcję systemową dla notatnika, do dziesięciu tysięcy znaków, z licznikiem odczytywanym przez czytnik ekranu, oraz osobny prompt dla zewnętrznego wyszukiwania źródeł. Aplikacja nigdy nie wykonuje tego promptu sama.
6. Ustawić projekt jako aktywny projekt skrótu klawiszowego.

Plik TXT wysłany w formularzu, złożony wyłącznie z adresów, jest listą źródeł: aplikacja pobiera wszystkie wskazane strony.

### Sposób drugi: globalny skrót klawiszowy

Skrót Control plus Shift plus F12 działa w dowolnym programie, gdy uruchomiony jest serwer interfejsu. Dzięki niemu możesz dodawać kolejne strony jedna po drugiej, bez wchodzenia do interfejsu aplikacji.

1. W Chrome albo Firefoksie dodaje adres bieżącej strony.
2. W Eksploratorze Windows dodaje zaznaczone pliki.
3. W innych programach nic nie dodaje i gra dźwięk porażki, a powód jest zapisany na stronie.

Materiał trafia do aktywnego projektu skrótu, który wybierasz przyciskiem „Ustaw jako aktywny projekt skrótu” na stronie projektu. Jeżeli nie wybrałeś żadnego, trafia do projektu „Adresy ze skrótu”. Dwa dźwięki mówią o wyniku: dwa krótkie rosnące tony to sukces, jeden niski dłuższy ton to porażka. Ostatni wynik jest także tekstem na stronie głównej i na stronie projektu. Skrót zapisuje materiał od razu, a jeśli trwa akurat przetwarzanie, przetworzy go w kolejnym przebiegu.

Jeżeli NVDA przechwytuje kombinację, zmień jej przypisanie w Preferencje, Gesty wejściowe. Wyłączenie skrótu: klucz konfiguracji `globalny_skrot_wlaczony`.

### Sposób trzeci: terminal

Polecenie `przetworz` uruchamia ten sam potok co interfejs. Wyjście jest linearne, bez pasków postępu, i kończy się jednym zdaniem podsumowania. Kod wyjścia zero oznacza wykonany potok, dwa oznacza brak podanych źródeł.

```powershell
python -m gnb.cli przetworz --projekt "Podatki 2026" --grupa "Ulgi" --url https://przyklad.pl/artykul --plik C:\materialy\ulgi.pdf
python -m gnb.cli przetworz --projekt "Podatki 2026" --tekst "Krótka notatka do dodania"
python -m gnb.cli przetworz --lista-url C:\materialy\adresy.txt --sprawdz-liste
python -m gnb.cli przetworz --projekt "Nuty" --plik C:\nuty\utwor.pdf --nuty
python -m gnb.cli przetworz --projekt "Wywiady" --plik C:\nagrania\rozmowa.mp3 --wymus-transkrypcje
```

Koniec bloku poleceń. Opcje `--plik`, `--tekst`, `--tekst-md`, `--url` i `--lista-url` można podawać wielokrotnie. Opcja `--grupa` przypisuje wszystkie źródła jednego wywołania do wspólnej grupy tematycznej. Opcja `--sprawdz-liste` wypisuje tylko podsumowanie listy adresów, czyli ile wykryto, ile jest poprawnych, ile duplikatów i ile odrzuconych z powodem, bez pobierania. Opcja `--nuty` traktuje PDF i obrazy jako materiał nutowy. Opcja `--wymus-transkrypcje` przepisuje nagranie, które program uznał za niemowne.

Pozostałe polecenia:

```powershell
python -m gnb.cli diagnostyka
python -m gnb.cli diagnostyka --plik raport.txt
python -m gnb.cli pamiec
python -m gnb.cli pamiec --wyczysc
```

Koniec bloku poleceń. `diagnostyka` sprawdza narzędzia zewnętrzne, a `pamiec` pokazuje albo czyści pamięć podręczną pobranych stron.

## Co powstaje po przetworzeniu

Każdy projekt to osobny katalog w Dokumentach, w podkatalogu `Gemini Notebook Builder`. Wewnątrz jest osobno: materiały źródłowe, wyniki pośrednie, pliki wynikowe do wgrania do notatnika, manifest, logi i checkpoint. Pliki do wgrania leżą w podkatalogu `pliki_wynikowe`, więc łatwo je znaleźć bez przeglądania reszty.

Po przetworzeniu wgraj pliki z tego podkatalogu do notatnika jako źródła.

Manifest ma dwie postacie: `manifest.json` jest źródłem prawdy, a `manifest.txt` to czytelny widok. Raport końcowy jest zwykłym tekstem: liczba wejść, źródeł prawidłowych, pominiętych, błędów, duplikatów, plików TXT, MD i PDF, procent wykorzystania limitu źródeł, największy plik i łączna liczba słów. Dwa logi: `log_wazne.txt` z krótkimi zdarzeniami w czasie lokalnym i `log_szczegolowy.txt` z danymi technicznymi w UTC.

## Uczciwe ograniczenia

1. Aplikacja nie obchodzi paywalli, logowania ani zabezpieczeń. Dla stron za logowaniem zapisz stronę w przeglądarce jako MHTML albo HTML i podaj plik.
2. Strony budowane w całości skryptami są rozpoznawane i pomijane z komunikatem, jak je obejść. Przeglądarka bezgłowa jest świadomie poza zakresem.
3. Nagrania utworów muzycznych jako dźwięku są poza zakresem. Muzyka w postaci zapisu nutowego jest obsługiwana.
4. Podobieństwo znaczeniowe tylko oznacza źródła do decyzji, nigdy nie usuwa ich samo.
5. Sposób liczenia słów po stronie Google może się różnić od naszego, stąd domyślne marginesy 480 000 słów i 190 MB.
6. Aplikacja jest przeznaczona na Windows 11. Ma zasady przenośności na Linuksa, ale moduł skrótu klawiszowego jest wyłącznie dla Windows.

## Dokumentacja

Zasady projektu, kontrakty danych, limity i kolejność prac: plik `CLAUDE.md` w katalogu głównym.

Dokumentacja użytkownika w katalogu `docs/`: `INSTALL.md`, `CONFIGURATION.md`, `FORMATS.md`, `ACCESSIBILITY.md`, `TROUBLESHOOTING.md`, `ARCHITECTURE.md` i `DECYZJE_I_ZAGADNIENIA.md`. Spis i kolejność lektury opisuje `docs/README.md`.

## Prywatność

Aplikacja działa w całości lokalnie. Nie wysyła danych do zewnętrznych usług sztucznej inteligencji, chyba że użytkownik świadomie to skonfiguruje. Repozytorium jest publiczne, więc nie zawiera haseł, tokenów ani danych osobowych.

## Licencja

Apache License 2.0. Pełny tekst znajduje się w pliku `LICENSE` w katalogu głównym repozytorium.

Wyjątek stanowi plik `tests/dane/LICENCJA_PyGuitarPro.txt`, dotyczący wyłącznie plików testowych formatu Guitar Pro pochodzących z biblioteki PyGuitarPro, objętych licencją LGPL w wersji trzeciej.
