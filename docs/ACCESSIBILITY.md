# Dostępność interfejsu WWW — stan po etapie dwunastym

Ten dokument opisuje, jak obsługiwać interfejs Gemini Notebook Builder
z klawiatury i z czytnikiem ekranu, oraz co interfejs ogłasza i jak często.
Dotyczy stanu po etapie siódmym, z dopełnieniem o globalny skrót klawiszowy
z etapu jedenastego, część A.

Dokument jest pisany pod odczyt liniowy. Nie ma w nim tabel ani ozdobników,
a polecenia do wpisania są w osobnych blokach.

## Czym jest interfejs

Interfejs to lokalny serwer WWW, który otwierasz w przeglądarce. Uruchamiasz go
poleceniem:

```powershell
python -m gnb.ui.server
```

Koniec polecenia uruchamiającego interfejs.

Po uruchomieniu program wypisuje adres do otwarcia, domyślnie
`http://127.0.0.1:8765/`. Serwer nasłuchuje wyłącznie na pętli zwrotnej, więc
strona nie jest dostępna z innego komputera. Serwer zatrzymujesz klawiszami
Control plus C w oknie, w którym go uruchomiłeś.

Cała praca przez interfejs jest równoważna poleceniu `python -m gnb.cli
przetworz`. Interfejs nie robi nic, czego nie robi wiersz poleceń; jest tylko
inną drogą do tego samego potoku.

## Obsługa z klawiatury

Interfejs jest w całości obsługiwalny z klawiatury. Nie ma elementu, do którego
trzeba użyć myszy.

1. Klawisz Tab przenosi fokus do kolejnego elementu, Shift plus Tab do
   poprzedniego. Kolejność fokusu jest zgodna z kolejnością czytania strony.
2. Elementy interaktywne to prawdziwe przyciski, odnośniki i pola formularza.
   Przycisk aktywujesz klawiszem Enter albo spacją, odnośnik klawiszem Enter.
3. Wskaźnik fokusu jest widoczny: element z fokusem dostaje wyraźną żółtą obwódkę.
4. Interfejs nie przenosi fokusu bez Twojego działania. Jedynym wyjątkiem jest
   przeniesienie fokusu na listę błędów po wysłaniu formularza z błędami; opisano
   to niżej.

## Strona główna

Strona główna ma dwie części.

Pierwsza to formularz nowego projektu. Pola, w kolejności:

1. Nazwa projektu. Pole wymagane. Nazwa staje się nazwą katalogu z wynikami, więc
   podaj krótką i rozpoznawalną, na przykład „Podatki 2026”.
2. Tekst wklejony. Pole wielowierszowe na treść wklejaną wprost.
3. Adresy stron i filmów. Pole wielowierszowe, po jednym adresie w wierszu.
   Przyjmowane są adresy stron internetowych oraz adresy filmów z serwisu
   YouTube, dla których pobierane są napisy.
4. Pliki z dysku. Pole wyboru pliku z możliwością wskazania wielu plików naraz.
   Otwiera zwykłe okno wyboru pliku systemu Windows, w pełni dostępne z NVDA.
   Obsługiwane formaty to te same, które przyjmuje wiersz poleceń: TXT, MD, HTML,
   CSV, SRT, VTT, PDF, DOCX i EPUB.
5. Nazwa grupy tematycznej. Pole opcjonalne. Wszystkie źródła jednego wysłania
   z wypełnioną tą samą nazwą grupy są łączone w możliwie najmniej plików
   wynikowych.

Musisz podać przynajmniej jedno źródło: tekst, adres albo plik. Sam formularz
z nazwą projektu jest niekompletny.

Przycisk „Utwórz projekt i rozpocznij przetwarzanie” wysyła formularz. Po
wysłaniu przeglądarka przechodzi na stronę projektu, a przetwarzanie rusza w tle.

Druga część strony głównej to wykaz projektów do wznowienia. Są to projekty,
które nie doszły do końca albo mają uszkodzony plik checkpointu. Każdy ma własny
odnośnik do strony projektu oraz własny przycisk „Wznów ten projekt”.

## Strona projektu

Strona projektu ma trzy elementy.

### Region stanu przetwarzania

Jest to region o roli „status” z ustawieniem `aria-live` na „polite”. Czytnik
ekranu ogłasza jego zmiany, ale nie przerywa tego, co właśnie czytasz.

Komunikaty postępu są dławione. Region zmienia treść najwyżej raz na cztery
sekundy, a komunikat identyczny z poprzednim nie jest powtarzany. Typowy
komunikat to podsumowanie w rodzaju „Przetworzono 12 z 40 źródeł”. Pojedyncze
zdarzenia nie są ogłaszane.

Gdy w przeglądarce działa JavaScript, region odświeża się sam co cztery sekundy.
Gdy przetwarzanie się skończy, region prosi o aktywowanie odnośnika „Odśwież
stan”. Strona nie przeładowuje się sama, ponieważ przeładowanie przeniosłoby
fokus na początek dokumentu.

Gdy JavaScript jest wyłączony, region pokazuje stan z chwili wczytania strony.
Aktualny stan sprawdzasz, aktywując odnośnik „Odśwież stan”, który jest zwykłym
odnośnikiem do tej samej strony.

Po zakończeniu przetwarzania na stronie pojawia się podsumowanie liczbowe oraz
pełna treść raportu końcowego.

### Pola notatnika

Formularz z dwoma niezależnymi polami tekstowymi zapisywanymi razem z projektem.

Pierwsze to instrukcja systemowa notatnika, z limitem dziesięciu tysięcy znaków.
Pod polem jest licznik znaków w regionie o roli „status”. Gdy działa JavaScript,
licznik aktualizuje się z opóźnieniem około siedmiu dziesiątych sekundy po
ostatnim naciśnięciu klawisza, a nie po każdym znaku, żeby czytnik ekranu nie był
zalewany. Próba zapisania instrukcji dłuższej niż limit jest odrzucana, a błąd
jest pokazany przy polu.

Drugie to prompt dla zewnętrznego mechanizmu wyszukującego źródła. Aplikacja
nigdy nie uruchamia tego promptu sama i nigdzie go nie wysyła. Zapisuje go tylko
razem z projektem. Osobny odnośnik „Pokaż prompt wyszukiwania do skopiowania”
otwiera stronę z samą treścią promptu w polu tylko do odczytu.

Przycisk „Zapisz pola” zapisuje obie wartości naraz.

### Odnośniki nawigacyjne

Na dole strony są odnośniki „Odśwież stan” oraz „Wróć do strony głównej”.

## Błędy formularza

Gdy wyślesz formularz z błędem, na przykład bez nazwy projektu albo bez żadnego
źródła, strona wraca z listą błędów na górze formularza. Lista ma rolę „alert”,
więc czytnik ekranu ogłasza ją od razu, i dodatkowo fokus jest na nią
przenoszony. To jedyny przypadek, w którym interfejs przenosi fokus bez Twojego
działania.

Każda pozycja listy jest odnośnikiem do pola, którego dotyczy błąd. Każde pole
z błędem ma ustawione `aria-invalid` na „true” oraz `aria-describedby`
wskazujące komunikat błędu pod polem, więc czytnik ekranu odczytuje ten
komunikat po wejściu w pole.

## Motyw i ruch

Interfejs ma ciemny motyw z jasnym tekstem i wysokim kontrastem, dużą czcionką
podstawową. Żadna informacja nie jest przekazywana wyłącznie kolorem. Interfejs
nie używa animacji utrudniających pracę z czytnikiem ekranu i respektuje
systemowe ustawienie ograniczenia ruchu.

## Bezpieczeństwo w kontekście dostępności

Treść pobrana ze źródeł nigdy nie trafia do przeglądarki jako HTML. Podgląd
artykułu czy transkrypcji jest zawsze zwykłym tekstem z pełnym escapowaniem, więc
strona źródła nie może wpłynąć na zachowanie interfejsu ani na czytnik ekranu.

Interfejs nie ładuje żadnego zasobu z zewnętrznego serwera. Działa bez internetu
i jest przewidywalny dla czytnika ekranu, ponieważ nic w nim nie dochodzi po
wczytaniu strony poza odświeżaniem regionu postępu.

## Globalny skrót klawiszowy

Skrót Control plus Shift plus F12 działa wyłącznie na Windows i wyłącznie, gdy
uruchomiony jest serwer interfejsu poleceniem `python -m gnb.ui.server`. Nie
uruchamia żadnego osobnego procesu w tle i nie działa jako autostart:
rejestracja zachodzi przy starcie serwera, wyrejestrowanie przy jego
zamknięciu.

Naciśnięcie skrótu, w dowolnym programie na pulpicie, dodaje jedną rzecz do
aktywnego projektu skrótu:

1. W Chrome albo w Firefoksie — adres bieżącej strony.
2. W Eksploratorze Windows — zaznaczone pliki.
3. W każdym innym programie, na pulpicie albo bez zaznaczenia w Eksploratorze —
   nic. Skrót wtedy gra dźwięk porażki i zapisuje czytelny powód.

### Aktywny projekt skrótu

Skrót dodaje materiał do jednego, jawnie wybranego projektu, nigdy do „ostatnio
otwartego”. Wybierasz go przyciskiem „Ustaw jako aktywny projekt skrótu” na
stronie danego projektu. Strona główna i strona każdego projektu pokazują
tekst „Aktywny projekt skrótu: nazwa” albo „Brak aktywnego projektu skrótu” —
region ten sam, co reszta stanu skrótu, więc czytnik ekranu odczyta go razem
z resztą strony przy zwykłym przechodzeniu po treści. Po ponownym uruchomieniu
serwera interfejsu wybór jest pusty, dopóki go nie ustawisz ponownie: nic nie
trafi po cichu do projektu wybranego przed restartem.

Naciśnięcie skrótu bez ustawionego aktywnego projektu jest porażką skrótu —
nic nie zostaje dodane, a komunikat mówi wprost, że trzeba najpierw wybrać
projekt.

### Potwierdzenie bez przenoszenia fokusu

Skrót działa w tle, często w oknie przeglądarki, więc nie może przenieść
fokusu do interfejsu Gemini Notebook Builder — to naruszyłoby zasadę
nieprzenoszenia fokusu bez działania użytkownika. Zamiast tego naciśnięcie
skrótu daje dwa niezależne potwierdzenia, które usłyszysz i przeczytasz bez
przełączania okna:

1. Dźwięk, natychmiast: dwa krótkie, rosnące tony przy powodzeniu, jeden
   niski i dłuższy ton przy porażce. Dźwięki różnią się rytmem, nie tylko
   wysokością, żeby rozróżnienie nie zależało od słuchu absolutnego.
2. Trwały tekstowy komunikat w sekcji „Globalny skrót klawiszowy” na stronie
   głównej i na stronie projektu, do sprawdzenia później, oraz w logu
   `gnb.hotkeys`.

### Kolejka w trakcie przetwarzania

Gdy w chwili naciśnięcia skrótu inne przetwarzanie już trwa, dodane źródło nie
jest odrzucane: zapisuje się od razu w pamięci serwera i zostaje przetworzone
w kolejnym przebiegu, uruchamianym samoczynnie po zakończeniu bieżącego
zadania. To nie jest nowy proces w tle — to dokończenie pracy, którą już
zacząłeś naciśnięciem skrótu.

Ta kolejka żyje wyłącznie w pamięci procesu serwera. Jeżeli zamkniesz serwer
interfejsu dokładnie wtedy, gdy kolejka ma jeszcze nieprzetworzone pozycje,
te pozycje przepadają — mimo że usłyszałeś dźwięk sukcesu w chwili ich
dodania. Nie dzieje się to po cichu: serwer przy zamknięciu zapisuje
ostrzeżenie z liczbą utraconych pozycji i nazwą dotkniętego projektu do
`log_wazne.txt`, do `log_szczegolowy.txt` tego projektu oraz do ostatniego
komunikatu skrótu widocznego w interfejsie. Jeżeli po ponownym uruchomieniu
serwera zobaczysz taki komunikat, dodaj brakujący materiał ponownie —
program go nie odzyska sam.

### Strony wymagające zalogowania

Skrót czyta adres strony i zaznaczone pliki, nigdy zaznaczony tekst na
stronie — pomiar na komputerze użytkownika wykazał, że wzorzec tekstowy UI
Automation jest w Chrome i w Firefoksie dostępny, ale nie zwraca niepustego
zaznaczenia treści strony; przyczyna nie została ustalona, a temat pozostaje
otwarty w `CLAUDE.md`. Do tego czasu strona wymagająca zalogowania, na której
sam adres nie wystarczy jako źródło, korzysta z obejścia bez żadnego nowego
mechanizmu: zapisz stronę z przeglądarki klawiszami Control plus S jako plik
HTML (Firefox i Chrome zapisują wtedy również obrazy strony w osobnym
podkatalogu — to jest w porządku, do notatnika trafia sama treść tekstowa),
a potem w Eksploratorze zaznacz zapisany plik HTML i naciśnij skrót jeszcze
raz, tym razem w oknie Eksploratora.

### Wyłączenie

Ustawienie `globalny_skrot_wlaczony` w konfiguracji, opisane w
`docs/CONFIGURATION.md`, wyłącza cały mechanizm. Polecenie `python -m gnb.cli
diagnostyka` zawsze zawiera wiersz o stanie tego skrótu: włączony, wyłączony
ustawieniem albo niedostępny na systemie innym niż Windows.

## Jednoczesne przetwarzanie

Jednocześnie może działać tylko jeden projekt. Próba uruchomienia drugiego
przetwarzania, gdy pierwsze trwa, kończy się czytelnym komunikatem, a nie
kolejkowaniem. Poczekaj na komunikat o zakończeniu, zanim uruchomisz kolejny
projekt albo wznowisz inny.
