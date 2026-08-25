"""Przyjmowanie wejść od użytkownika: adres URL, lista adresów, plik, tekst wklejony.

Ten pakiet odpowiada za walidację i zamianę wejścia surowego (`WejscieSurowe`)
na źródło (`Zrodlo`) gotowe do pobrania albo importu. Nie zawiera logiki
ekstrakcji treści ani pobierania danych z sieci — tym zajmuje się `gnb.extractors`.
"""
