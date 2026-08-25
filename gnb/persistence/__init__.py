"""Checkpoint projektu, lokalna pamięć podręczna i baza SQLite.

Zapis checkpointu jest atomowy: plik tymczasowy w tym samym katalogu,
a następnie `os.replace`, z zachowaniem jednej kopii zapasowej. Zapis
checkpointu wykonuje wyłącznie jeden wątek, zgodnie z sekcją piętnastą
CLAUDE.md.
"""
