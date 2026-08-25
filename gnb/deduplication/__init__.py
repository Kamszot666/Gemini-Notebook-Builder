"""Wieloetapowa deduplikacja i audytowalne decyzje o duplikatach.

Ten pakiet porównuje znormalizowane dokumenty w kolejności opisanej w sekcji
szesnastej CLAUDE.md: hash treści, porównanie po usunięciu różnic
kosmetycznych, podobieństwo klasyczne, opcjonalnie embeddingi lokalne. Wynikiem
jest lista `DecyzjaDeduplikacji`. Ten pakiet nigdy nie usuwa treści
automatycznie na podstawie podobieństwa semantycznego — może ją jedynie
oznaczyć do decyzji użytkownika.
"""
