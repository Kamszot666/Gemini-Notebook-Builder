# Dane testowe — Gemini Notebook Builder

Wszystkie pliki w tym katalogu zostały wygenerowane od zera na potrzeby testów. Nie zawierają materiałów objętych prawami autorskimi ani danych prywatnych, więc można je bezpiecznie trzymać w publicznym repozytorium.

Docelowa lokalizacja w repozytorium: `tests/dane/`.

## Co który plik sprawdza

1. `dokument_strukturalny.md` — dokument z hierarchią nagłówków, dwiema listami i tabelą. Reguła z sekcji ósmej pliku `CLAUDE.md` powinna dla niego wygenerować wersję MD obok TXT.
2. `tekst_plaski.txt` — ta sama treść bez struktury. Program NIE powinien generować dla niego MD. To jest test negatywny do tej samej reguły.
3. `tekst_windows1250.txt` — plik w kodowaniu Windows-1250 z zakończeniami wierszy CRLF i polskimi znakami. Sprawdza wykrywanie kodowania i normalizację. Jeżeli w wyniku pojawią się znaki zapytania lub krzaczki, wykrywanie kodowania nie działa.
4. `artykul_oryginal.html` oraz `artykul_przedruk.html` — ten sam artykuł w dwóch serwisach. Oba mają menu, baner cookies, reklamę, pasek boczny i stopkę, które ekstraktor ma usunąć. Przedruk ma zmieniony tytuł, jedno przeredagowane zdanie i jeden akapit unikalny. Test sprawdza dwie rzeczy naraz: czy deduplikacja rozpozna przedruk oraz czy nie zgubi akapitu, który występuje tylko w jednym z nich.
5. `tabela_metod.csv` — dane tabelaryczne ze średnikiem jako separatorem. Sprawdza zachowanie znaczenia struktury tabelarycznej.
6. `napisy.srt` oraz `napisy.vtt` — sprawdzają usuwanie znaczników czasu z podstawowego TXT przy zachowaniu wersji technicznej.
7. `lista_url.txt` — lista adresów zawierająca: adres poprawny, jego dokładny duplikat, ten sam adres z parametrem śledzącym, dwa adresy w jednym wierszu rozdzielone spacją, tekst niebędący adresem, adres z błędnym protokołem oraz adres domeny, która nie istnieje. Sprawdza walidację, kanonizację adresów i to, czy jeden błędny wpis nie zatrzymuje całej paczki.
8. `dokument.docx` — nagłówki, akapity i lista wypunktowana.
9. `prezentacja.pptx` — dwa slajdy z tytułem i listą.
10. `dokument.odt` — wymaga LibreOffice w trybie bez okna.
11. `ksiazka.epub` — jeden rozdział z nagłówkiem i akapitami.
12. `pdf_tekstowy.pdf` — trzy strony z warstwą tekstową, z powtarzanym na każdej stronie nagłówkiem i numerem strony na dole. Sprawdza usuwanie powtarzalnych nagłówków i numerów stron bez utraty treści merytorycznej.
13. `pdf_skan.pdf` — dwie strony będące obrazami, bez warstwy tekstowej. Sprawdza wykrywanie braku warstwy tekstowej i uruchomienie OCR.
14. `pdf_uszkodzony.pdf` — poprawny nagłówek pliku, uciętą resztę. Ma zakończyć się kontrolowanym błędem, a nie awarią programu.
15. `obraz_wykres.png`, `obraz_zdjecie.jpg`, `obraz.webp`, `obraz.tiff`, `obraz.bmp` — obrazy w pięciu formatach do testu importu i łączenia w tematyczny PDF.
16. `obraz_uszkodzony.jpg` — plik ucięty w jednej trzeciej. Ma zakończyć się kontrolowanym błędem.
17. `audio_muzyka.wav` oraz `audio_muzyka.mp3` — dziesięć sekund akordów bez mowy. Nagrania muzyczne są poza zakresem aplikacji, więc program ma rozpoznać, że to nie jest mowa, pominąć plik z czytelnym komunikatem i zapisać to w raporcie. Uruchomienie transkrypcji na tym pliku jest błędem.
18. `audio_cisza_i_szum.wav` — osiem sekund niemal całkowitej ciszy z krótkim dźwiękiem w środku. To jest materiał, na którym modele Whisper typowo generują halucynacje, czyli wymyślone powtarzane zdania. Jeżeli w wyniku transkrypcji pojawi się jakikolwiek tekst, filtr aktywności mowy nie działa poprawnie.
19. `melodia.mid` — plik MIDI z ośmioma nutami, metrum cztery czwarte, tempo sto dwadzieścia, nazwa utworu zapisana w metadanych. Sprawdza odczyt MIDI oraz konwersję przez MuseScore.
20. `melodia.musicxml` — ta sama melodia zapisana jako MusicXML w formacie partwise, z tonacją, metrum, kluczem i nazwą instrumentu. Sprawdza odczyt notacji oraz wygenerowanie opisu tekstowego zawierającego tonację, metrum, liczbę taktów i instrument.
21. `nuty_skan.png` oraz `nuty_skan.pdf` — zapis nutowy jako obraz: dwa systemy po pięć linii, główki nut z laskami, tytuł i opis tonacji. Sprawdza wykrycie, że materiał jest notacją muzyczną, i skierowanie go do rozpoznawania notacji zamiast do zwykłego OCR tekstowego. Uwaga: to jest zapis uproszczony, narysowany programowo, więc służy do sprawdzenia ścieżki przetwarzania, a nie do oceny jakości rozpoznania.
22. `tabulatura_akordy.gp3`, `tabulatura_akordy.gp4`, `tabulatura_akordy.gp5` — ten sam materiał w trzech wersjach formatu Guitar Pro. Każdy zawiera jedną ścieżkę, osiem taktów, tempo sto dwadzieścia. Sprawdzają odczyt przez bibliotekę PyGuitarPro oraz to, czy program poprawnie rozpoznaje wersję formatu.
23. `tabulatura_efekty.gp5` — czternaście taktów z efektami wykonawczymi. Sprawdza, czy odczyt nie wywraca się na mniej typowych elementach zapisu.

Pochodzenie plików Guitar Pro. Pochodzą one z zestawu testowego biblioteki PyGuitarPro, dostępnej pod adresem https://github.com/Perlence/PyGuitarPro na licencji LGPL w wersji trzeciej. Treść licencji znajduje się w pliku `LICENCJA_PyGuitarPro.txt`. Są to pliki syntetyczne, bez tytułu i bez nazwiska autora, utworzone wyłącznie do testów, więc można je bezpiecznie trzymać w publicznym repozytorium.

## Czego tu nie ma i trzeba dodać samodzielnie

Nagranie mowy. Nie da się go wygenerować bez syntezatora, a nagranie własnym głosem jest lepszym testem, bo obejmuje polskie głoski i naturalne tempo.

Sposób nagrania na Windows 11 z NVDA:

1. Naciśnij klawisz Windows, wpisz „Rejestrator dźwięku” i naciśnij Enter.
2. Naciśnij Control plus R, żeby rozpocząć nagrywanie.
3. Przeczytaj na głos przez około dwadzieścia sekund dowolny fragment, na przykład pierwszy akapit z pliku `tekst_plaski.txt`.
4. Naciśnij Control plus R ponownie, żeby zakończyć nagrywanie.
5. Nagranie zapisuje się w katalogu Dokumenty, w podkatalogu Nagrania dźwiękowe. Skopiuj je do `tests/dane/` pod nazwą `audio_mowa.m4a`.

Adresy filmów YouTube. Wybierz trzy adresy samodzielnie i wpisz je do pliku tekstowego `tests/dane/lista_youtube.txt`: jeden film z napisami tworzonymi ręcznie, jeden wyłącznie z napisami automatycznymi i jeden bez żadnych napisów. Nie wpisuję ich za Ciebie, bo dostępność napisów zmienia się w czasie i test przestałby działać.

Plik w nowym formacie Guitar Pro. Formaty gpx oraz gp, czyli wersje szósta i siódma programu, nie są obsługiwane przez PyGuitarPro. W zestawie nie ma takiego pliku, bo nie da się go wygenerować bez samego programu Guitar Pro. Jeżeli masz własny, wstaw go do `tests/dane/` pod nazwą `tabulatura_nowy_format.gp`. Posłuży do sprawdzenia, czy program zgłasza czytelnie nieobsługiwaną wersję zamiast próbować zgadywać zawartość.

Prawdziwy skan nut. Plik `nuty_skan.png` jest rysunkiem programowym i nie zastąpi zdjęcia albo skanu prawdziwej partytury. Do oceny jakości rozpoznawania notacji dołóż jeden własny skan, najlepiej utworu z domeny publicznej, żeby dało się go trzymać w publicznym repozytorium. Dużym źródłem takich materiałów jest biblioteka IMSLP pod adresem https://imslp.org, gdzie znaczna część zbiorów to utwory, których prawa autorskie wygasły. Sprawdzaj status każdego pliku osobno, bo IMSLP zawiera również wydania współczesne objęte prawami.
