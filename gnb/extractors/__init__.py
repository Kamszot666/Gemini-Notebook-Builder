"""Adaptery ekstrakcji treści dla poszczególnych typów źródeł.

Każdy adapter zamienia pobrane albo zaimportowane źródło na
`DokumentWyekstrahowany`. Nowy format dodaje się jako nowy adapter w tym
pakiecie, bez zmian w pozostałych podsystemach. Ten pakiet nie normalizuje
treści ani nie decyduje o deduplikacji — tym zajmują się kolejne etapy potoku.
"""
