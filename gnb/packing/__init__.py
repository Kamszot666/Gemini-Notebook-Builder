"""Grupowanie tematyczne i pakowanie źródeł do plików wynikowych.

Ten pakiet działa zawsze po deduplikacji, nigdy przed nią. Dzieli i łączy
źródła z poszanowaniem trzech niezależnych limitów notatnika: liczby źródeł,
liczby słów w źródle i rozmiaru pliku, opisanych w sekcji dziewiątej
CLAUDE.md. Nie zapisuje plików na dysk — tym zajmuje się `gnb.output`.
"""
