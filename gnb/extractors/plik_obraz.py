"""Ekstrakcja treści z plików obrazów: opis merytoryczny oraz tekst z OCR.

Obsługiwane są JPG, PNG, WebP, TIFF, BMP oraz statyczna klatka GIF. Formaty HEIC
i HEIF wymagają biblioteki opcjonalnej pillow-heif; jej brak zgłaszany jest jako
`FormatNieobslugiwany` z informacją, jak dołożyć obsługę tych dwóch formatów,
a nie wyłącza całego ekstraktora.

Wynik ekstrakcji obrazu to opis merytoryczny zbudowany z dostępnego materiału
tekstowego oraz, osobną oznaczoną sekcją, tekst rozpoznany przez OCR. Treść
wizualna nigdy nie jest interpretowana ani wysyłana do zewnętrznej usługi,
zgodnie z sekcją trzecią CLAUDE.md i decyzją siódmą etapu ósmego. Struktura
dokumentu jest zawsze na poziomie niskim, więc sekcja ósma CLAUDE.md nie pozwala
na wersję Markdown.

Obraz zawsze dostaje niepustą treść. Gdy nie ma z czego zbudować opisu
merytorycznego, zapisywany jest jawny komunikat o braku opisu wraz z formatem
i wymiarami obrazu, zgodnie z decyzją siódmą etapu ósmego. Obraz wskazany przez
użytkownika nie jest pomijany po cichu: użytkownik sam decyduje, czy taki obraz
zostawić w notatniku.

Rozpoznanie OCR jest domyślnie wyłączone w samym ekstraktorze i włączane przez
rejestr budowany z konfiguracji. Dzięki temu ekstrakcja metadanych obrazu działa
tak samo, gdy OCR jest wyłączony albo gdy nie ma Tesseracta.
"""

from __future__ import annotations

import io

from PIL import Image, UnidentifiedImageError
from PIL.ExifTags import Base as EtykietaExif

from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BrakNarzedzia, FormatNieobslugiwany
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.images.ocena_ocr import OcenaOcr, ocen_ocr
from gnb.images.opis import BRAK_OPISU, MaterialDoOpisu, zbuduj_opis
from gnb.images.tesseract import UstawieniaOcr, czy_dostepny, rozpoznaj_tekst

METODA_EKSTRAKCJI = "obraz"
METODA_EKSTRAKCJI_OCR = "obraz-ocr"

FORMATY_OBRAZOW = frozenset(
    {"jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp", "gif", "heic", "heif"}
)

NAGLOWEK_SEKCJI_OCR = "Rozpoznany tekst (OCR):"
KOMUNIKAT_OCR_PUSTY = "OCR nie rozpoznał żadnego tekstu na tym obrazie."
KOMUNIKAT_OCR_NIEWYKONANY = "OCR nie został wykonany dla tego obrazu."

KOMUNIKAT_USZKODZONY_OBRAZ = (
    "Pliku obrazu nie dało się odczytać: jest uszkodzony albo ma nieobsługiwaną postać wewnętrzną."
)
KOMUNIKAT_BRAK_PILLOW_HEIF = (
    "Obsługa formatów HEIC i HEIF wymaga biblioteki opcjonalnej pillow-heif. "
    "Zainstaluj ją poleceniem „pip install gnb[obrazy-heic]” albo przekonwertuj "
    "obraz do formatu JPG lub PNG."
)
OSTRZEZENIE_OCR_BEZ_TESSERACTA = (
    "OCR jest włączony, ale nie znaleziono programu Tesseract, więc obraz "
    "zapisano bez rozpoznanego tekstu."
)
OSTRZEZENIE_KLATKA_ANIMOWANEGO_GIF = (
    "Plik GIF jest animowany. Do przetworzenia wzięto wyłącznie pierwszą klatkę."
)


class EkstraktorObrazu:
    """Ekstraktor opisu i tekstu OCR z plików obrazów."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def __init__(
        self,
        ustawienia_ocr: UstawieniaOcr | None = None,
        *,
        ocr_wlaczony: bool = False,
    ) -> None:
        self._ustawienia_ocr = ustawienia_ocr or UstawieniaOcr()
        self._ocr_wlaczony = ocr_wlaczony

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_OBRAZ and format_zrodla in FORMATY_OBRAZOW

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Buduje opis obrazu i, jeżeli OCR jest włączony, dołącza rozpoznany tekst.

        OCR pojedynczego obrazu jest jednym krokiem, więc argument `postep` jest
        przyjmowany dla zgodności z kontraktem i nie jest używany; postęp
        raportuje potok po każdym przetworzonym źródle.
        """
        obraz, format_pliku = self._otworz(identyfikator_zrodla, bajty)
        ostrzezenia: list[str] = []

        if getattr(obraz, "is_animated", False):
            # Po otwarciu obraz jest na pierwszej klatce; przetwarzana jest tylko ona.
            ostrzezenia.append(OSTRZEZENIE_KLATKA_ANIMOWANEGO_GIF)

        wymiary = (obraz.width, obraz.height)
        metadane_obrazu = _metadane_z_obrazu(obraz)

        tekst_ocr, ocr_wykonany = self._rozpoznaj(identyfikator_zrodla, obraz, ostrzezenia)
        if ocr_wykonany:
            ocena = ocen_ocr(tekst_ocr)
            if ocena.czy_wymaga_sprawdzenia:
                ostrzezenia.extend(ocena.powody)
        else:
            ocena = None

        opis = zbuduj_opis(
            MaterialDoOpisu(
                nazwa_pliku=None,
                format_obrazu=format_pliku,
                wymiary=wymiary,
                metadane_obrazu=metadane_obrazu,
                tekst_ocr=tekst_ocr if ocr_wykonany else None,
            )
        )

        tekst = _zloz_tekst(opis, format_pliku, wymiary, tekst_ocr, ocr_wykonany)
        metadane = _metadane_dokumentu(format_pliku, wymiary, metadane_obrazu, ocr_wykonany, ocena)

        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI_OCR if ocr_wykonany else METODA_EKSTRAKCJI,
            tytul=metadane_obrazu.get("tytul"),
            metadane=metadane,
            ostrzezenia=ostrzezenia,
        )

    def _otworz(self, identyfikator_zrodla: str, bajty: bytes) -> tuple[Image.Image, str]:
        """Otwiera obraz z bajtów, wczytując wsparcie HEIC dopiero gdy jest potrzebne."""
        _zarejestruj_heif_jesli_dostepne()
        try:
            obraz = Image.open(io.BytesIO(bajty))
            obraz.load()
        except UnidentifiedImageError as blad:
            if _wyglada_na_heif(bajty):
                raise FormatNieobslugiwany(
                    KOMUNIKAT_BRAK_PILLOW_HEIF, identyfikator_zrodla
                ) from blad
            raise FormatNieobslugiwany(KOMUNIKAT_USZKODZONY_OBRAZ, identyfikator_zrodla) from blad
        except OSError as blad:
            raise FormatNieobslugiwany(KOMUNIKAT_USZKODZONY_OBRAZ, identyfikator_zrodla) from blad
        return obraz, (obraz.format or "").lower()

    def _rozpoznaj(
        self, identyfikator_zrodla: str, obraz: Image.Image, ostrzezenia: list[str]
    ) -> tuple[str, bool]:
        """Zwraca rozpoznany tekst i informację, czy OCR faktycznie się wykonał."""
        if not self._ocr_wlaczony:
            return "", False
        if not czy_dostepny(self._ustawienia_ocr.sciezka_tesseract):
            ostrzezenia.append(OSTRZEZENIE_OCR_BEZ_TESSERACTA)
            return "", False
        try:
            tekst = rozpoznaj_tekst(
                _do_png(obraz),
                self._ustawienia_ocr,
                identyfikator_zrodla=identyfikator_zrodla,
            )
        except BrakNarzedzia:
            ostrzezenia.append(OSTRZEZENIE_OCR_BEZ_TESSERACTA)
            return "", False
        return tekst.strip(), True


def _zloz_tekst(
    opis: str,
    format_pliku: str,
    wymiary: tuple[int, int],
    tekst_ocr: str,
    ocr_wykonany: bool,
) -> str:
    """Składa opis obrazu z sekcją rozpoznanego tekstu w jeden dokument.

    Obraz zawsze dostaje niepustą treść, nawet gdy nie ma z czego zbudować opisu
    merytorycznego: zapisywany jest wtedy jawny komunikat o braku opisu wraz
    z formatem i wymiarami obrazu, zgodnie z decyzją siódmą etapu ósmego. Pusty
    ciąg w pliku wynikowym wyglądałby jak przeoczenie, a jawny brak mówi
    użytkownikowi, że sam musi ocenić przydatność tego obrazu.
    """
    if opis == BRAK_OPISU:
        naglowek = (
            f"{opis}\nFormat i wymiary: {format_pliku.upper()}, "
            f"{wymiary[0]} na {wymiary[1]} pikseli"
        )
    else:
        naglowek = opis

    if tekst_ocr:
        sekcja = tekst_ocr
    elif ocr_wykonany:
        sekcja = KOMUNIKAT_OCR_PUSTY
    else:
        sekcja = KOMUNIKAT_OCR_NIEWYKONANY
    return f"{naglowek}\n\n{NAGLOWEK_SEKCJI_OCR}\n{sekcja}"


def _metadane_z_obrazu(obraz: Image.Image) -> dict[str, str]:
    """Wyciąga z obrazu opisowe pola metadanych: opis, tytuł, autora, słowa kluczowe.

    Czytane są zarówno pola EXIF, jak i tekstowe pola formatu PNG. Pola Windows
    (XPTitle, XPComment, XPKeywords) są zapisane jako UTF-16, więc wymagają
    osobnego rozkodowania.
    """
    metadane: dict[str, str] = {}

    tekstowe_png = getattr(obraz, "text", None)
    if isinstance(tekstowe_png, dict):
        for zrodlowy, docelowy in (
            ("Description", "opis"),
            ("Title", "tytul"),
            ("Author", "autor"),
            ("Comment", "komentarz"),
            ("Keywords", "slowa_kluczowe"),
        ):
            wartosc = _oczysc(tekstowe_png.get(zrodlowy))
            if wartosc:
                metadane.setdefault(docelowy, wartosc)

    try:
        exif = obraz.getexif()
    except (OSError, ValueError, AttributeError):
        exif = None
    if exif:
        opis = _oczysc(_jako_tekst(exif.get(EtykietaExif.ImageDescription.value)))
        if opis:
            metadane.setdefault("opis", opis)
        autor = _oczysc(_jako_tekst(exif.get(EtykietaExif.Artist.value)))
        if autor:
            metadane.setdefault("autor", autor)
        for numer, klucz in (
            (0x9C9B, "tytul"),
            (0x9C9C, "komentarz"),
            (0x9C9E, "slowa_kluczowe"),
        ):
            wartosc = _oczysc(_z_pola_windows(exif.get(numer)))
            if wartosc:
                metadane.setdefault(klucz, wartosc)

    return metadane


def _metadane_dokumentu(
    format_pliku: str,
    wymiary: tuple[int, int],
    metadane_obrazu: dict[str, str],
    ocr_wykonany: bool,
    ocena: OcenaOcr | None,
) -> dict[str, str]:
    """Buduje słownik metadanych źródła zapisywany później w manifeście."""
    metadane = {
        "format_obrazu": format_pliku.upper(),
        "wymiary_pikseli": f"{wymiary[0]} na {wymiary[1]}",
        "ocr_wykonany": "tak" if ocr_wykonany else "nie",
    }
    if metadane_obrazu.get("autor"):
        metadane["autor"] = metadane_obrazu["autor"]
    if ocena is not None:
        metadane["ocena_ocr"] = ocena.ocena
    return metadane


def _do_png(obraz: Image.Image) -> bytes:
    """Zapisuje obraz jako PNG w pamięci, sprowadzając go do trybu RGB."""
    bufor = io.BytesIO()
    obraz.convert("RGB").save(bufor, format="PNG")
    return bufor.getvalue()


def _zarejestruj_heif_jesli_dostepne() -> None:
    """Rejestruje w Pillow obsługę HEIC i HEIF, gdy biblioteka pillow-heif jest dostępna."""
    try:
        import pillow_heif
    except ImportError:
        return
    pillow_heif.register_heif_opener()


def _wyglada_na_heif(bajty: bytes) -> bool:
    """Rozpoznaje sygnaturę pliku HEIF po polu ``ftyp`` w nagłówku kontenera."""
    if len(bajty) < 12 or bajty[4:8] != b"ftyp":
        return False
    marka = bajty[8:32]
    return b"heic" in marka or b"heif" in marka or b"mif1" in marka or b"heix" in marka


def _jako_tekst(wartosc: object) -> str | None:
    """Sprowadza wartość pola EXIF do tekstu, jeżeli da się to zrobić sensownie."""
    if isinstance(wartosc, str):
        return wartosc
    if isinstance(wartosc, bytes):
        return wartosc.decode("utf-8", errors="replace")
    return None


def _z_pola_windows(wartosc: object) -> str | None:
    """Rozkodowuje pole XP formatu EXIF zapisane jako UTF-16 z terminatorem zerowym."""
    if isinstance(wartosc, bytes):
        return wartosc.decode("utf-16-le", errors="replace").rstrip("\x00")
    if isinstance(wartosc, tuple):
        try:
            return bytes(wartosc).decode("utf-16-le", errors="replace").rstrip("\x00")
        except (ValueError, TypeError):
            return None
    if isinstance(wartosc, str):
        return wartosc
    return None


def _oczysc(wartosc: str | None) -> str:
    """Sprowadza wartość do jednego wiersza bez nadmiarowych białych znaków."""
    if not wartosc:
        return ""
    return " ".join(wartosc.split())
