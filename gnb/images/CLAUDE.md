# Obrazy — zasady modułu gnb/images

Ten plik jest wczytywany, gdy pracujesz w katalogu `gnb/images/`. Przeniesiono go z sekcji piętnastej głównego `CLAUDE.md` bez zmiany treści.

Obrazy: obsłuż JPG, PNG, WebP, TIFF, BMP oraz statyczną klatkę GIF. Dla HEIC i HEIF potrzebna jest biblioteka `pillow-heif`. Każdy obraz ma mieć identyfikator, nazwę, źródło, tytuł, opis merytoryczny, informację o OCR i numer strony w PDF. Jeżeli narzędzie tworzy rzeczywistą strukturę dostępności PDF, wykorzystaj ją. Jeżeli nie, nie nazywaj zwykłego opisu tekstowego tagiem alt.
