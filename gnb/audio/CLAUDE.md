# Audio — zasady modułu gnb/audio

Ten plik jest wczytywany, gdy pracujesz w katalogu `gnb/audio/`. Przeniesiono go z sekcji piętnastej głównego `CLAUDE.md` bez zmiany treści.

Audio: moduł obsługuje wyłącznie nagrania mowy. Rozróżnianie mowy od muzyki jest wymagane, a nie opcjonalne, i służy tu do odrzucenia materiału, a nie do wyboru trybu. Zastosuj wykrywanie aktywności mowy, na przykład Silero VAD, i próg konfigurowalny. Użytkownik musi móc nadpisać decyzję dla konkretnego pliku, na wypadek nagrania z muzyką w tle. Pamiętaj, że modele Whisper na fragmentach bez mowy generują halucynacje w postaci powtarzanych fraz. Stosuj filtr VAD, wykrywaj powtórzenia i oznaczaj segmenty o niskiej pewności.
