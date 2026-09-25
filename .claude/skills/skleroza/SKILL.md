---
name: skleroza
description: Użyj, gdy użytkownik napisze słowo „skleroza”: generuje kompletny plik STAN_PROJEKTU.md do Wiedzy projektu w Claude.
---

# Procedura checkpointu pamięci — hasło „skleroza”

Gdy użytkownik napisze słowo „skleroza”, wygeneruj kompletny plik `STAN_PROJEKTU.md` po polsku, przeznaczony do wgrania do Wiedzy projektu w Claude.

Sekcje w tej dokładnie kolejności, ponieważ przy obcięciu kontekstu ma przetrwać to, czego nie da się odtworzyć z kodu:

1. NAGŁÓWEK, w tym jawna informacja, że ten plik zastępuje poprzedni i jest jedynym aktualnym źródłem stanu.
2. STAN NA TERAZ.
3. OTWARTE PYTANIA I DECYZJE DO PODJĘCIA.
4. DECYZJE COFNIĘTE I ODRZUCONE, z wyraźnym ostrzeżeniem przy każdej pozycji, jeżeli stara wersja może zostać pomylona z nową.
5. USTALENIA ZAIMPLEMENTOWANE, z odnośnikami do plików, bez wklejania kodu.
6. METADANE ROZMOWY.
7. DOSŁOWNY KOD, zawsze na samym dole.

Treść kodu czytaj bezpośrednio z repozytorium, nigdy nie odtwarzaj z pamięci rozmowy. Plik niedokończony oznacz jako częściowy i napisz, czego brakuje. Jeżeli decyzja zmieniała się wielokrotnie, pokaż całą sekwencję zmian.

Po wygenerowaniu pliku dopisz zdanie: „Pobierz ten plik i podmień nim poprzedni STAN_PROJEKTU.md w Wiedzy projektu.” Zdanie to dotyczy wyłącznie Claude Code, który dostępu do Wiedzy projektu nie ma. Jeżeli sesja taki dostęp ma — na przykład rozmowa prowadzona w projekcie Claude albo sesja Cowork podpięta do projektu — zapisz checkpoint wprost do Wiedzy projektu, podmieniając w niej poprzedni plik, i napisz użytkownikowi, że to zrobione, zamiast odsyłać go do ręcznej podmiany.
