# Dostępność interfejsu WWW

Ten dokument opisuje, jak obsługiwać interfejs Gemini Notebook Builder
z klawiatury i z czytnikiem ekranu, oraz co interfejs ogłasza i jak często.
Dotyczy stanu po etapie siódmym.

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

## Jednoczesne przetwarzanie

Jednocześnie może działać tylko jeden projekt. Próba uruchomienia drugiego
przetwarzania, gdy pierwsze trwa, kończy się czytelnym komunikatem, a nie
kolejkowaniem. Poczekaj na komunikat o zakończeniu, zanim uruchomisz kolejny
projekt albo wznowisz inny.
