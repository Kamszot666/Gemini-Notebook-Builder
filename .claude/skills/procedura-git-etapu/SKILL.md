---
name: procedura-git-etapu
description: Użyj na początku i na końcu etapu albo naprawy: kolejność kroków Git, kontrole, push, pull request i scalenie squash po polsku.
---

# Procedura Git na zakończenie etapu

Po ukończeniu etapu wysyłasz pracę na GitHub samodzielnie, bez pytania użytkownika o zgodę na każdy krok. Zgoda na tę procedurę jest udzielona z góry, właśnie w tym miejscu. Dotyczy ona wyłącznie kroków opisanych poniżej. Wszystko, czego tu nie ma, nadal wymaga pytania.

Kolejność jest wiążąca.

1. Na początku etapu utwórz gałąź funkcjonalną z aktualnego `main`, o nazwie w postaci `etap-NN-krotki-opis`, na przykład `etap-01-pipeline-tekstowy`. Nie pracuj bezpośrednio na `main`. Cała ta procedura obowiązuje też poza etapami z sekcji osiemnastej, na przykład przy naprawie usterki znalezionej na rzeczywistym przebiegu — wtedy gałąź nazywaj z przedrostkiem `naprawa-`, na przykład `naprawa-limit-zrodel-grupowanie`, zamiast wzorca `etap-NN`.
2. W trakcie etapu rób małe, tematyczne commity z wiadomościami po polsku w trybie rozkazującym.
3. Przed wysłaniem uruchom komplet kontroli: `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy gnb`, `python -m mypy gnb --platform linux` oraz `python -m pytest -q -m "not siec and not wolne and not pulpit"`. Wszystkie muszą przejść. Postać `python -m` jest obowiązkowa z powodu opisanego w sekcji piątej.
4. Jeżeli którakolwiek kontrola nie przechodzi, nie wysyłaj niczego. Napraw problem i powtórz krok trzeci. Wysłanie kodu z czerwonymi testami jest złamaniem tej procedury.
5. Sprawdź, czy do commitów nie trafiło nic, co nie powinno być publiczne: sekrety, tokeny, bezwzględne ścieżki z nazwą konta użytkownika, prywatne materiały źródłowe, katalog wyników.
6. Wyślij gałąź poleceniem `git push -u origin nazwa-galezi`.
7. Utwórz pull request przez GitHub CLI, z tytułem i opisem po polsku.
8. Scal pull request metodą squash, z usunięciem gałęzi, poleceniem `gh pr merge --squash --delete-branch`.
9. Wróć na `main` i pobierz scalony stan: `git switch main` oraz `git pull`.
10. Dopiero teraz wypisz blok przekazania do projektu Claude opisany w sekcji osiemnastej a, dopisując w nim numer scalonego pull requestu.

Opis pull requestu ma być czytelny liniowo i zawierać, w tej kolejności: nazwę etapu, listę tego, co powstało wraz z nazwami plików, listę podjętych decyzji, wynik kontroli z kroku trzeciego wraz z liczbą testów, listę rzeczy świadomie odłożonych na później oraz nazwę następnego etapu. Bez tabel, bez ozdobników. Opis jest dla użytkownika czytany syntezatorem mowy, a nie ozdobą.

Czego w tej procedurze nie wolno, niezależnie od okoliczności:

1. Żadnego `push --force`, `reset --hard`, `clean -fdx`, nadpisywania historii ani usuwania gałęzi innych niż własna gałąź etapu po scaleniu.
2. Żadnego scalania, gdy kontrole z kroku trzeciego nie przechodzą.
3. Żadnego rozwiązywania konfliktu scalania na własną rękę. Przy konflikcie zatrzymaj się, opisz go i poczekaj na decyzję użytkownika.
4. Żadnego scalania pull requestu utworzonego przez kogoś innego.
5. Jeżeli GitHub CLI nie jest zainstalowany lub nie jest zalogowany, nie próbuj obejść tego innym sposobem. Wykonaj kroki od pierwszego do szóstego, a potem napisz użytkownikowi, jakiego polecenia brakuje i co ma zrobić.
