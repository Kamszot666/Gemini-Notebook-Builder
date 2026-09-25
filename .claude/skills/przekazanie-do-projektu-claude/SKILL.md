---
name: przekazanie-do-projektu-claude
description: Użyj po ukończeniu etapu projektu albo gdy natrafisz na decyzję wykraczającą poza zadanie: określa blok przekazania do projektu Claude i plik PRZEKAZANIE.md.
---

# Zakończenie etapu i przekazanie do projektu Claude

Praca jest podzielona między dwa miejsca. Kod powstaje tutaj, w Claude Code. Decyzje architektoniczne, przegląd ustaleń i pamięć długoterminowa projektu są w projekcie Claude w przeglądarce.

Po ukończeniu każdego etapu z sekcji osiemnastej, a także zawsze gdy natrafisz na decyzję wykraczającą poza aktualne zadanie, zakończ swoją wypowiedź blokiem o dokładnie takiej strukturze:

1. Nagłówek trzeciego poziomu o treści: „Przejdź do projektu Claude”.
2. Jedno zdanie mówiące, który etap został ukończony i co konkretnie działa.
3. Nagłówek trzeciego poziomu o treści: „Prompt do wklejenia w projekcie Claude”.
4. Blok kodu oznaczony jako `text`, zawierający gotową do skopiowania treść, bez Twoich komentarzy w środku.

Treść w bloku ma zawierać, w tej kolejności: nazwę ukończonego etapu, numer scalonego pull requestu, listę tego, co powstało wraz z nazwami plików, listę decyzji podjętych po drodze wraz z krótkim uzasadnieniem każdej, listę pytań otwartych, których nie powinieneś rozstrzygać samodzielnie, oraz nazwę następnego planowanego etapu.

Blok ma być samowystarczalny. Użytkownik wkleja go do projektu Claude bez dopisywania czegokolwiek, więc nie odwołuj się w nim do „poprzedniej wiadomości” ani do rzeczy widocznych tylko tutaj.

Poza wypisaniem bloku w oknie zapisz jego pełną treść, wraz z nagłówkami i przypomnieniem o haśle „skleroza”, do pliku `PRZEKAZANIE.md` w katalogu głównym repozytorium, w kodowaniu UTF-8 ze znacznikiem kolejności bajtów. Następnie otwórz ten plik i nie czekaj na zamknięcie edytora:

```powershell
Start-Process -FilePath "C:\Program Files\Notepad++\notepad++.exe" -ArgumentList (Resolve-Path .\PRZEKAZANIE.md).Path
```

Powód: użytkownik pracuje z czytnikiem ekranu, a kopiowanie długiego bloku wprost z terminala jest zawodne. Plik `PRZEKAZANIE.md` jest materiałem kontekstowym projektu Claude i jest wpisany do `.gitignore` obok `STAN_PROJEKTU.md`, więc nie trafia do repozytorium.

Po tym bloku nie pisz nic więcej i nie zaczynaj kolejnego etapu. Poczekaj na to, co użytkownik przyniesie z projektu Claude.

Dodatkowo przypomnij jednym zdaniem, żeby po zamknięciu tematu w projekcie Claude wpisać tam słowo „skleroza”, pobrać wygenerowany plik `STAN_PROJEKTU.md` i podmienić nim poprzednią wersję w Wiedzy projektu.
