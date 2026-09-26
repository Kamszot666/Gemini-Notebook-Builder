# Gemini Notebook Builder

Program na Windows, który przygotowuje materiały do Gemini Notebook (dawniej NotebookLM). Zbiera to, co chcesz tam wgrać: strony internetowe, filmy z YouTube, dokumenty, skany, nagrania, a nawet nuty. Wyciąga z nich sam tekst, wyrzuca powtórki i pakuje wszystko w kilka porządnych plików, które wgrywasz do notatnika. Dzięki temu zmieścisz w nim dużo więcej, niż pozwala zwykłe dodawanie po jednym źródle.

Ten opis jest czytany po kolei, bez tabel i rysunków, więc dobrze brzmi w czytniku ekranu. Nagłówki możesz przeskakiwać klawiszem H.

## Najważniejsze: to narzędzie jest robione dla osób niewidomych

Program powstaje dla osoby niewidomej, która pracuje na Windows 11 z czytnikiem NVDA. To nie jest dodatek na koniec. Zasada jest prosta: jeśli czegoś nie da się obsłużyć samą klawiaturą z czytnikiem ekranu, to uznajemy, że to nie działa.

Co to znaczy w praktyce:

1. Interfejs to zwykła strona w przeglądarce, zbudowana z prawdziwych przycisków, odnośników, pól i nagłówków. Do niczego nie potrzeba myszy.
2. Każde pole ma normalną etykietę, którą NVDA czyta. Gdy formularz ma błędy, dostajesz ich listę tekstem i fokus ląduje na niej.
3. Postęp długiej pracy jest ogłaszany krótkimi zdaniami, na przykład „Przetworzono 12 z 40 źródeł”, i to rzadko, żeby czytnik nie zasypał Cię komunikatami.
4. Fokus nigdy nie skacze sam po stronie. Rusza się tylko wtedy, kiedy Ty coś zrobisz.
5. Wysoki kontrast, ciemny motyw, duża czcionka. Nic nie jest przekazane wyłącznie kolorem. Animacje respektują ustawienie ograniczania ruchu.
6. Każdy adres internetowy, który pojawia się na stronach programu, jest klikalnym odnośnikiem.
7. Globalny skrót klawiszowy potwierdza wynik dźwiękiem, żeby nie zabierać Ci fokusu z przeglądarki. Dwa krótkie, rosnące tony to sukces, jeden niski i dłuższy to porażka. Ostatni wynik jest też zapisany tekstem na stronie.
8. Raporty i listy źródeł to zwykły tekst, czytany po kolei.
9. Dokumentacja nazywa elementy po ich nazwie i roli, nigdy po tym, gdzie leżą na ekranie.

## Po co to komu

Notebook ma limity. Według oficjalnej strony pomocy Google, sprawdzonej 26 września 2026: 50 źródeł w planie bezpłatnym, 100 w Plus, 300 w Pro i 500 albo 600 w Ultra. Jedno źródło może mieć do 500 000 słów albo 200 MB. Google zastrzega, że liczby mogą się zmienić, dlatego u nas to ustawienia, a nie zaszyte na sztywno wartości.

Kiedy dodajesz wszystko po kolei, każdy plik, strona i zdjęcie zjada jedno miejsce. Kilkadziesiąt krótkich artykułów, notatek i skanów potrafi wyczerpać cały notatnik, choć razem to wcale nie tak dużo tekstu.

Ten program robi z tym porządek. Zbiera materiały, zostawia sam tekst, usuwa powtórki i łączy małe rzeczy tematycznie w duże pliki. Pilnuje przy tym trzech limitów naraz: ile masz źródeł, ile słów ma jedno źródło i ile waży plik. Każdy kawałek w połączonym pliku ma nagłówek z informacją, skąd pochodzi, więc niczego nie tracisz z oczu.

## Co Ci to daje

1. Oszczędzasz miejsca w notatniku. Zajęte miejsca zależą od liczby tematów, a nie od liczby materiałów. Liczby są niżej.
2. Wgrywasz więcej rodzajów plików, niż notatnik przyjmuje sam. Dokumenty biurowe, arkusze, strony zapisane z przeglądarki, napisy, archiwa ZIP, nuty. Pełna lista niżej.
3. Nie wgrywasz powtórek. Ten sam artykuł z dwóch adresów albo w dwóch formatach zajmie jedno miejsce. Jeśli dwa źródła są podobne, ale każde ma coś swojego, program zachowa to unikalne. Podobieństwo „w znaczeniu” nigdy nie kasuje niczego samo, tylko zaznacza źródło do Twojej decyzji.
4. Dostajesz czysty tekst. Ze stron znikają menu, banery o ciasteczkach, reklamy i stopki. Zostaje artykuł. Linki, które autor podał w tekście, lądują w osobnej liście na końcu, żeby nie przerywały zdań, kiedy słuchasz.
5. Wiesz, skąd co jest. Program prowadzi manifest: skąd pochodzi każde źródło, jak wyciągnięto treść, co uznano za powtórkę i w którym pliku wylądowało. Każde pominięcie i każde ostrzeżenie trafia do logu, do manifestu i do raportu. Nic nie znika po cichu.
6. Praca się nie marnuje. Program zapisuje stan pracy, więc przerwany projekt wznawiasz bez robienia wszystkiego od nowa. Jeden zepsuty plik albo martwy link nie zatrzymuje reszty.
7. Nie przekroczysz limitów. Za duże źródło jest dzielone na części na granicy nagłówka albo akapitu, nigdy w środku zdania. Program nie dopycha plików na siłę do limitu: limit to sufit, nie cel.
8. Twoje dane zostają u Ciebie. OCR, zamiana mowy na tekst i usuwanie powtórek dzieją się na Twoim komputerze. Nic nie leci do zewnętrznych usług AI, chyba że sam to świadomie włączysz. Treść pobrana ze stron i plików jest dla programu tylko danymi, nigdy poleceniem.
9. Program jest kulturalny wobec stron. Domyślnie szanuje plik robots.txt (z wyjątkiem adresów, które podajesz sam) i nie obchodzi paywalli ani logowania.
10. Źródła dodajesz na trzy sposoby: w przeglądarce, skrótem klawiszowym i z terminala. Opisane niżej.

## A co z internetem? Baza działa też offline

Uczciwie: sam Gemini Notebook działa w sieci. Ale to, co powstaje po stronie programu, jest Twoje i działa bez internetu.

1. Wszystko ląduje w zwykłych plikach na Twoim dysku: TXT, czasem MD i PDF, plus manifest, raport i logi. Otworzysz je czymkolwiek, czytnikiem ekranu, wyszukiwarką plików czy programem do notatek, bez konta i bez sieci.
2. Program trzyma też oryginały, na przykład surowy plik pobranej strony (możesz to wyłączyć). Jeśli strona zniknie z sieci, u Ciebie zostaje.
3. Interfejs działa w całości lokalnie. Nie pobiera niczego z cudzych serwerów, więc jest szybki i przewidywalny dla czytnika. Serwer słucha tylko na Twoim komputerze, pod adresem 127.0.0.1.
4. Internet jest potrzebny tylko do pobrania stron i napisów z YouTube oraz do wgrania gotowych plików do notatnika. Reszta, w tym rozpoznawanie tekstu ze zdjęć i zamiana nagrań mowy na tekst, działa bez sieci. Model do zamiany mowy na tekst ściąga się raz, przy pierwszym użyciu.
5. Kopia zapasowa to zwykłe skopiowanie katalogu projektu. Tę samą paczkę możesz wgrać do kilku notatników.
6. Strony raz pobrane są pamiętane. Jeśli się nie zmieniły, program nie ściąga ich drugi raz.

## Ile miejsca oszczędzasz

Uwaga: to arytmetyka na podanych założeniach, a nie pomiar Twoich plików. Ile naprawdę zaoszczędzisz, zależy od tego, jak dużo masz materiałów i jak je pogrupujesz. Po każdym przebiegu program sam pisze w raporcie, ile procent limitu źródeł zużyłeś i który plik jest największy, więc łatwo sprawdzisz własne liczby.

Zasada jest prosta. Bez programu każdy materiał to jedno źródło. Z programem jedno źródło to jedna grupa tematyczna. Jeden plik pomieści do 480 000 słów, czyli na przykład 400 artykułów po 1200 słów.

Przykład pierwszy, artykuły. Masz 250 krótkich artykułów po około 1200 słów, razem 300 000 słów, w pięciu tematach po 50. Po staremu to 250 źródeł, czyli 250 procent limitu planu Plus. Zmieściłbyś się dopiero w Pro (300) i to prawie bez zapasu. Z programem to pięć plików po mniej więcej 60 000 słów, czyli 5 źródeł, 5 procent limitu Plus. Oszczędzasz 245 z 250 miejsc, czyli 98 procent.

Przykład drugi, zdjęcia i skany. Masz 60 zdjęć stron dokumentów w trzech tematach po 20. Po staremu to 60 źródeł. Z programem zdjęcia z jednego tematu idą do jednego PDF-a, razem z opisami i tekstem rozpoznanym z obrazu, więc to 3 źródła. Oszczędzasz 57 z 60 miejsc, czyli 95 procent. Do tego tekst ze zdjęć da się przeszukiwać i czytać czytnikiem.

Przykład trzeci, mieszanka. Masz 100 materiałów, z czego 20 to powtórki tego samego z innego adresu albo w innym formacie, a pozostałe 80 układa się w 8 tematów. Po staremu to 100 źródeł, czyli cały plan Plus. Z programem 20 powtórek nie dostaje własnych plików, a 80 materiałów zajmuje 8 źródeł. Oszczędzasz 92 ze 100 miejsc. Liczba 20 powtórek to założenie do przykładu, nie średnia.

Wniosek: przy grupowaniu tematycznym 100 miejsc planu Plus starcza na zbiór, który bez grupowania przekroczyłby nawet 300 miejsc planu Pro. A limit 500 000 słów na źródło przestaje przeszkadzać, bo program sam bezpiecznie dzieli za duże rzeczy.

Jest jeszcze oszczędność w bajtach. Plik wynikowy to sam tekst, bez znaczników, stylów, skryptów, reklam i obrazków, więc zwykle jest wyraźnie mniejszy od strony, PDF-a z grafiką czy dokumentu biurowego. Nie podam procentu, bo zależy od materiału. Rozmiar każdego pliku wynikowego jest w manifeście.

## Jakie formaty obsługuje

Według oficjalnej strony pomocy Google (sprawdzonej 26 września 2026) sam Notebook przyjmuje: DOCX, TXT, Markdown, PDF, CSV, PPTX, dokumenty, arkusze i prezentacje Google, EPUB, wklejony tekst, dźwięk (na przykład MP3 i WAV), obrazy, adresy stron i publiczne filmy z YouTube z napisami. Nie przyjmuje nagrań bez mowy, stron za paywallem ani PDF-ów zabezpieczonych przed kopiowaniem.

Program czyta to wszystko, co potrafi przerobić u Ciebie na komputerze, a do tego wiele rzeczy spoza tej listy. Wszystko zamienia na pliki TXT, MD albo PDF, które notebook przyjmie.

Czego notebook nie ma na swojej liście, a program obsłuży:

1. Strony zapisane z przeglądarki w jednym pliku, czyli MHTML i MHT. Bardzo wygodne dla stron za logowaniem albo takich, które budują się skryptami: zapisujesz stronę już wyświetloną i podajesz plik.
2. Pliki HTML, HTM i XHTML z dysku.
3. Dokumenty OpenDocument: ODT, ODS, ODP.
4. Arkusze Excela: XLSX, XLSM, stary XLS, a także TSV.
5. Stare pliki Office: DOC i PPT (przez LibreOffice) oraz RTF.
6. Napisy SRT i VTT.
7. Pliki tekstowe z danymi: JSON, XML, YAML, YML, TOML, INI, CFG, LOG.
8. Archiwa ZIP, z zabezpieczeniami przed złośliwymi paczkami: limity liczby plików, rozmiaru, stopnia kompresji i zagłębienia oraz ochrona ścieżek.
9. Listy adresów. Plik TXT złożony z samych adresów jest listą źródeł i program pobiera każdą stronę. Adres zaczynający się od www. działa bez https. Adresy znalezione w treści zwykłych plików TXT i MD też są pobierane, ale z kontrolą robots.txt.
10. Nuty w postaci zapisu: MIDI, MusicXML i MXL, Guitar Pro 3, 4 i 5, a także skany nut i tabulatur w PDF lub obrazach, które rozpoznaje program Audiveris. Wynik to zawsze opis tekstem: metrum, tonacja, dźwięki, tabulatura. Nagrań muzyki jako dźwięku program nie obsługuje.

Nawet tam, gdzie notebook coś przyjmuje, program dokłada wartość:

1. Skany PDF bez tekstu i zdjęcia są rozpoznawane (OCR) i wracają jako tekst, który można przeszukać i przeczytać czytnikiem.
2. Nagrania mowy zamieniają się na tekst u Ciebie na komputerze, a muzyka i szum są odrzucane.
3. Napisy z YouTube trafiają do plików jako tekst, razem z tytułem, kanałem i językiem, a nie jako sam link do filmu.
4. Wiele małych źródeł jest łączonych w jeden plik z nagłówkiem pochodzenia przy każdym fragmencie.

Szczegóły i ograniczenia każdego formatu są w docs/FORMATS.md.

## Instalacja krok po kroku

Potrzebujesz Windows 11, Pythona 3.12 albo nowszego i około gigabajta wolnego miejsca. Polecenia wpisuj w PowerShellu. Po każdym bloku poleceń piszę, że się skończył, żeby czytnik nie mieszał go z opisem.

Krok pierwszy, Python. Ten sposób używa wbudowanego w Windows 11 menedżera winget.

```powershell
winget install --id Python.Python.3.12 --exact
```

Zamknij terminal, otwórz go od nowa i sprawdź wersję:

```powershell
py -3.12 --version
```

Koniec bloku poleceń.

Krok drugi, pobranie programu. Jeśli nie masz gita, zainstaluj go poleceniem `winget install --id Git.Git --exact` i otwórz terminal od nowa.

```powershell
git clone https://github.com/Kamszot666/Gemini-Notebook-Builder.git
cd Gemini-Notebook-Builder
```

Koniec bloku poleceń.

Krok trzeci, własne środowisko i biblioteki.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Koniec bloku poleceń. Jeśli PowerShell nie pozwala aktywować środowiska, pomiń drugą linię i wołaj Pythona wprost, na przykład `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.

Krok czwarty, sprawdzenie, czy wszystko jest na miejscu. Program wypisze, jakich narzędzi brakuje, do czego służą i co przestanie działać bez nich.

```powershell
python -m gnb.cli diagnostyka
```

Koniec bloku poleceń.

Krok piąty, narzędzia dodatkowe. Są opcjonalne. Bez nich program i tak obsłuży tekst, strony, YouTube, PDF-y z tekstem, DOCX, EPUB, dokumenty OpenDocument, arkusze, RTF, MHTML i ZIP. Brak narzędzia wyłącza tylko jedną funkcję i daje zrozumiały komunikat.

1. Tesseract: rozpoznawanie tekstu ze zdjęć i skanów. Przydadzą się polskie dane językowe.
2. FFmpeg: odczyt nagrań mowy.
3. LibreOffice: tylko dla starych DOC i PPT.
4. Java i Audiveris: rozpoznawanie nut ze skanów.

Dodatkowe biblioteki Pythona doinstalujesz grupami: `pip install -e ".[audio]"` dla zamiany mowy na tekst, `pip install -e ".[nuty]"` dla MIDI i Guitar Pro, `pip install -e ".[obrazy-heic]"` dla zdjęć HEIC. Pełny opis, razem z polskimi danymi dla Tesseracta, jest w docs/INSTALL.md.

Jedna uwaga dla osób z włączonym Inteligentnym sterowaniem aplikacjami w Windows: narzędzia programistyczne uruchamiaj przez `python -m`, na przykład `python -m pytest`, a nie przez pliki z katalogu Scripts, bo Windows potrafi je zablokować.

## Ustawienia

Nie musisz niczego ustawiać, bo są sensowne wartości domyślne. Jeśli chcesz coś zmienić, ustawienia biorą się z trzech miejsc. Od najsłabszego: wartości wbudowane, plik konfiguracji, zmienne środowiskowe zaczynające się od GNB_. Zmienna środowiskowa zawsze wygrywa.

Plik nazywa się `konfiguracja.toml` i leży poza repozytorium, zwykle w `C:\Users\TWOJA_NAZWA\AppData\Roaming\Gemini Notebook Builder`. Jego brak nie jest błędem.

Najczęściej zmieniane rzeczy:

1. `katalog_wynikow`: gdzie mają lądować projekty. Domyślnie podkatalog `Gemini Notebook Builder` w Dokumentach.
2. `limit_zrodel`: ile źródeł masz w notatniku. Domyślnie 100 (plan Plus). Wpisz 50, 300, 500 albo 600 dla innych planów.
3. `bezpieczny_limit_slow` i `bezpieczny_limit_mb`: domyślnie 480 000 słów i 190 MB, z zapasem wobec limitów Google.
4. `formaty_wynikowe`: `["txt", "md"]` włącza Markdown tam, gdzie ma sens. TXT powstaje zawsze.
5. `zachowuj_oryginaly`: czy trzymać kopie oryginałów. Domyślnie tak.
6. `respektuj_robots` i `wyjatek_robots_dla_zrodel_jawnych`: jak program traktuje robots.txt.
7. Progi usuwania powtórek, ustawienia OCR i zamiany mowy na tekst, ścieżki do narzędzi i limity dla archiwów ZIP.
8. `globalny_skrot_wlaczony`: włącza albo wyłącza skrót klawiszowy.

Przykład dla jednej sesji PowerShella:

```powershell
$env:GNB_LIMIT_ZRODEL = "300"
```

Koniec bloku poleceń. Pełny spis pól i przykładowy plik są w docs/CONFIGURATION.md.

## Jak uruchomić

```powershell
python -m gnb.ui.server
```

Koniec bloku poleceń. Program wypisze adres, domyślnie `http://127.0.0.1:8765/`. Otwórz go w przeglądarce. Zatrzymasz go klawiszami Control plus C w oknie terminala. Uruchamiaj tylko jeden taki serwer naraz, bo drugi nie zdoła zająć skrótu klawiszowego.

## Jak dodawać źródła

### Sposób pierwszy: w przeglądarce

Strona główna ma formularz nowego projektu. Pola po kolei:

1. Nazwa projektu, wymagana. To będzie nazwa katalogu z wynikami, więc niech będzie krótka, na przykład „Podatki 2026”.
2. Nazwa grupy tematycznej, wymagana. Wszystko z jednego wysłania z tą samą grupą zostanie połączone w jak najmniej plików. Pole podpowiada grupy, które projekt już zna.
3. Tekst wklejony. Duże pole na tekst.
4. Adresy stron i filmów, po jednym w wierszu. Adres z www. na początku działa bez https.
5. Pliki z dysku. Możesz wskazać wiele plików naraz, w zwykłym oknie wyboru pliku Windows.

Potrzebujesz przynajmniej jednego źródła. Przycisk „Utwórz projekt i rozpocznij przetwarzanie” wszystko uruchamia. Na stronie projektu widzisz postęp, potem podsumowanie i raport.

Na stronie projektu możesz:

1. Dosłać kolejne źródła formularzem pod raportem.
2. Przejść po liście źródeł. Każde ma własny nagłówek i własne przyciski: oznacz jako zweryfikowane, zastąp treść własnym plikiem, usuń z projektu.
3. Oznaczyć źródło z ostrzeżeniem jako zweryfikowane. Jeśli pochodzi z sieci, program pobierze je jeszcze raz.
4. Usunąć źródło jednym przyciskiem, bez wpisywania żadnego potwierdzenia.
5. Wpisać instrukcję systemową dla notatnika (do 10 000 znaków, z licznikiem, który czyta czytnik) oraz osobny prompt do zewnętrznego wyszukiwania źródeł. Program nigdy nie uruchamia tego promptu sam.
6. Ustawić projekt jako ten, do którego wpada materiał ze skrótu klawiszowego.

Plik TXT złożony z samych adresów wysłany w formularzu jest listą źródeł: program pobierze wszystkie wskazane strony.

### Sposób drugi: skrót klawiszowy

Control plus Shift plus F12 działa w dowolnym programie, kiedy serwer jest uruchomiony. Możesz dodawać strony jedna po drugiej, nie wchodząc do samego programu.

1. W Chrome albo Firefoksie dodaje adres strony, na której jesteś.
2. W Eksploratorze Windows dodaje zaznaczone pliki.
3. W innych programach nic nie dodaje i gra dźwięk porażki. Powód jest zapisany na stronie.

Materiał trafia do aktywnego projektu skrótu, który wybierasz przyciskiem „Ustaw jako aktywny projekt skrótu” na stronie projektu. Jeśli żadnego nie wybrałeś, wpada do projektu „Adresy ze skrótu”. Dwa krótkie rosnące tony to sukces, jeden niski dłuższy to porażka. Ostatni wynik jest też napisany na stronie głównej i na stronie projektu. Jeśli akurat trwa przetwarzanie, materiał czeka w kolejce i zostanie przetworzony zaraz po nim.

Gdyby NVDA przechwytywało tę kombinację, zmień jej przypisanie w Preferencje, Gesty wejściowe. Skrót wyłączysz kluczem `globalny_skrot_wlaczony`.

### Sposób trzeci: terminal

Polecenie `przetworz` robi to samo co strona. Wyjście jest czytane po kolei, bez pasków postępu, i kończy się jednym zdaniem podsumowania. Kod wyjścia zero to „zrobione”, dwa to „nie podano żadnych źródeł”.

```powershell
python -m gnb.cli przetworz --projekt "Podatki 2026" --grupa "Ulgi" --url https://przyklad.pl/artykul --plik C:\materialy\ulgi.pdf
python -m gnb.cli przetworz --projekt "Podatki 2026" --tekst "Krótka notatka do dodania"
python -m gnb.cli przetworz --lista-url C:\materialy\adresy.txt --sprawdz-liste
python -m gnb.cli przetworz --projekt "Nuty" --plik C:\nuty\utwor.pdf --nuty
python -m gnb.cli przetworz --projekt "Wywiady" --plik C:\nagrania\rozmowa.mp3 --wymus-transkrypcje
```

Koniec bloku poleceń. Opcje `--plik`, `--tekst`, `--tekst-md`, `--url` i `--lista-url` możesz podawać wiele razy. `--grupa` wrzuca wszystkie źródła z tego wywołania do jednej grupy tematycznej. `--sprawdz-liste` tylko pokazuje podsumowanie listy adresów (ile wykryto, ile poprawnych, ile powtórek, ile odrzuconych i dlaczego), bez pobierania. `--nuty` każe traktować PDF-y i obrazy jak nuty. `--wymus-transkrypcje` przepisuje nagranie, które program uznał za niemowne, na przykład z głośną muzyką w tle.

Pozostałe polecenia:

```powershell
python -m gnb.cli diagnostyka
python -m gnb.cli diagnostyka --plik raport.txt
python -m gnb.cli pamiec
python -m gnb.cli pamiec --wyczysc
```

Koniec bloku poleceń. `diagnostyka` sprawdza narzędzia zewnętrzne, a `pamiec` pokazuje albo czyści pamięć pobranych stron.

## Co dostajesz po przetworzeniu

Każdy projekt to osobny katalog w Dokumentach, w podkatalogu `Gemini Notebook Builder`. W środku osobno leżą: materiały źródłowe, wyniki pośrednie, pliki do wgrania do notatnika, manifest, logi i zapis stanu pracy. Pliki, które wgrywasz do notatnika, są w podkatalogu `pliki_wynikowe`, więc nie musisz niczego szukać. Wgraj je do notatnika jako źródła i gotowe.

Manifest ma dwie wersje: `manifest.json` jest głównym zapisem, a `manifest.txt` to jego czytelny widok. Raport na końcu to zwykły tekst: ile wejść, ile źródeł poprawnych, ile pominiętych, ile błędów, ile powtórek, ile plików TXT, MD i PDF, jaki procent limitu źródeł zużyłeś, który plik jest największy i ile słów razem. Są też dwa logi: `log_wazne.txt` z krótkimi zdarzeniami w Twoim czasie lokalnym i `log_szczegolowy.txt` z danymi technicznymi.

## Czego program nie robi

1. Nie obchodzi paywalli, logowania ani zabezpieczeń. Dla stron za logowaniem zapisz stronę w przeglądarce jako MHTML albo HTML i podaj ten plik.
2. Strony budowane w całości skryptami rozpoznaje i pomija z komunikatem, jak je obejść. Przeglądarki bezgłowej w środku nie ma.
3. Nagrań muzyki jako dźwięku nie obsługuje. Muzykę w postaci nut tak.
4. Podobieństwo „w znaczeniu” tylko zaznacza źródła do Twojej decyzji, nigdy samo niczego nie usuwa.
5. Google może liczyć słowa trochę inaczej niż my, dlatego domyślnie zostawiamy zapas: 480 000 słów i 190 MB.
6. Program jest na Windows 11. Kod ma zasady przenośności na Linuksa, ale skrót klawiszowy jest tylko dla Windows.

## Gdzie szukać szczegółów

Wszystko, co najważniejsze, masz wyżej. Gdyby coś jeszcze trzeba było sprawdzić dokładniej, jest to w katalogu docs: INSTALL.md (instalacja, narzędzia dodatkowe), CONFIGURATION.md (każde ustawienie), FORMATS.md (każdy format, jego ograniczenia i ostrzeżenia), ACCESSIBILITY.md (obsługa z klawiatury i NVDA), TROUBLESHOOTING.md (co robić, gdy coś nie działa), ARCHITECTURE.md (jak to jest zbudowane) oraz DECYZJE_I_ZAGADNIENIA.md (decyzje projektowe i sprawy otwarte). Spis jest w docs/README.md. Zasady projektu i kontrakty danych są w pliku CLAUDE.md w katalogu głównym.

## Prywatność

Program działa w całości lokalnie. Nie wysyła danych do zewnętrznych usług AI, chyba że sam to świadomie skonfigurujesz. To repozytorium jest publiczne, więc nie ma w nim haseł, tokenów ani danych osobowych.

## Licencja

Apache License 2.0. Pełny tekst jest w pliku `LICENSE`.

Wyjątek: plik `tests/dane/LICENCJA_PyGuitarPro.txt` dotyczy tylko plików testowych formatu Guitar Pro pochodzących z biblioteki PyGuitarPro, która jest na licencji LGPL w wersji trzeciej.
