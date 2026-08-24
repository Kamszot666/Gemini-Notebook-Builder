# Jak przygotować bazę wiedzy dla asystenta AI

Baza wiedzy dla asystenta AI jest tym lepsza, im mniej zawiera powtórzeń i im dokładniej wiadomo, skąd pochodzi każdy fragment.

## Trzy najczęstsze błędy

### Błąd pierwszy: nadmiar

Najczęstszym błędem jest wrzucanie do jednego zbioru wszystkiego, co wpadnie w ręce, bez sprawdzenia, czy te same treści nie występują w kilku miejscach.

- Powtórzone artykuły z kilku serwisów.
- Kilka wersji tego samego dokumentu.
- Transkrypcje nagrań, które są odczytaniem tego samego tekstu.

### Błąd drugi: nadgorliwe usuwanie

Drugim częstym błędem jest usuwanie materiałów tylko dlatego, że wyglądają podobnie do innych. Podobieństwo nie oznacza tożsamości.

1. Sprawdź, czy oba materiały mają część wspólną.
2. Sprawdź, czy któryś ma treść, której nie ma drugi.
3. Zachowaj informacje unikalne.

### Błąd trzeci: utrata pochodzenia

Trzecim błędem jest utrata informacji o pochodzeniu. Bez niej nie da się później zweryfikować żadnego twierdzenia.

## Porównanie metod wykrywania duplikatów

| Metoda | Koszt | Wykrywa |
| --- | --- | --- |
| Suma kontrolna | bardzo niski | teksty identyczne |
| Porównanie po normalizacji | niski | różnice kosmetyczne |
| MinHash | średni | duże pokrycie fragmentów |
| Embeddingi | wysoki | podobieństwo znaczeniowe |

## Podsumowanie

Wartość bazy wiedzy zależy od jakości, a nie od liczby plików.
