"""Ekstrakcja treści z nagrań mowy: transkrypcja przez faster-whisper.

Moduł obsługuje wyłącznie nagrania mowy. Wykrycie materiału muzycznego kończy
się kontrolowanym pominięciem z czytelnym komunikatem, nigdy transkrypcją,
zgodnie z decyzją opisaną w sekcji pierwszej a punkt czwarty CLAUDE.md. Kolejność
kroków: rozkodowanie nagrania FFmpegiem do fali, pomiar udziału mowy filtrem
Silero, decyzja o odrzuceniu nagrania niemownego, a dopiero potem transkrypcja
tego, co zostało.

Obrona przed halucynacjami modelu Whisper jest wpięta w dwóch miejscach. Filtr
wykrywania aktywności mowy jest włączony w samej transkrypcji, więc model nie
dostaje fragmentów bez mowy. Wynik jest dodatkowo oceniany przez
`gnb.audio.ocena`: powtórzone frazy oraz segmenty niskiej pewności trafiają do
pola ostrzeżeń dokumentu, a stąd, przez potok, do sekcji „Materiały do
sprawdzenia”. Segment niepewny nie znika po cichu.

Struktura dokumentu jest zawsze na poziomie niskim, bo transkrypcja mowy nie ma
nagłówków, list ani tabel — sekcja ósma CLAUDE.md nie pozwala wtedy na wersję
Markdown, dokładnie jak dla napisów filmu.

Brak FFmpega albo biblioteki faster-whisper nie wywraca aplikacji: kończy się
`BrakNarzedzia`, a potok zamienia to na kontrolowany błąd źródła. Wyłączona
w konfiguracji transkrypcja oraz materiał niemowny kończą się `PominietoZrodlo`,
czyli kontrolowanym pominięciem ze statusem „pominiete”.
"""

from __future__ import annotations

from gnb.audio import dekodowanie
from gnb.audio.ocena import ocen_transkrypcje
from gnb.audio.transkrypcja import UstawieniaTranskrypcji, czy_dostepna_biblioteka, transkrybuj
from gnb.audio.wykrywanie_mowy import KOMUNIKAT_NIEMOWNE, dlugosc_mowy_sekundy, ocen_mowe
from gnb.core.model import DokumentWyekstrahowany
from gnb.core.stale import PoziomPewnosciStruktury, TypZrodla
from gnb.core.wyjatki import BrakNarzedzia, PominietoZrodlo
from gnb.extractors.bazowy import PostepEkstrakcji
from gnb.extractors.napisy_wspolne import zapisz_akapity, zbuduj_akapity
from gnb.ingestion.youtube import SegmentNapisow

METODA_EKSTRAKCJI = "transkrypcja_audio"

FORMATY_AUDIO = frozenset({"mp3", "wav", "m4a", "flac", "ogg", "opus", "aac"})

KOMUNIKAT_TRANSKRYPCJA_WYLACZONA = (
    "Transkrypcja nagrań mowy jest wyłączona w konfiguracji (klucz "
    "„transkrypcja_wlaczona”). Nagranie zostało pominięte. Włącz transkrypcję, "
    "żeby przepisać mowę na tekst."
)
KOMUNIKAT_BRAK_BIBLIOTEKI = (
    "Nie znaleziono biblioteki faster-whisper, która przepisuje mowę na tekst. "
    "Zainstaluj ją poleceniem „pip install gnb[audio]”. Bez niej nagrania mowy "
    "nie zostaną przepisane, a pozostałe formaty źródeł działają normalnie."
)
KOMUNIKAT_PUSTA_TRANSKRYPCJA = (
    "Po odfiltrowaniu fragmentów bez mowy w nagraniu nie zostało nic do "
    "przepisania. Nagranie pominięto, żeby pusty plik nie zajmował miejsca "
    "w limicie źródeł notatnika."
)


class EkstraktorAudio:
    """Ekstraktor transkrypcji z nagrań mowy."""

    metoda = METODA_EKSTRAKCJI
    tekst_zawiera_znaczniki = False

    def __init__(
        self,
        ustawienia: UstawieniaTranskrypcji | None = None,
        *,
        transkrypcja_wlaczona: bool = False,
        prog_udzialu_mowy: float = 0.5,
        wymus_transkrypcje: bool = False,
    ) -> None:
        self._ustawienia = ustawienia or UstawieniaTranskrypcji()
        self._transkrypcja_wlaczona = transkrypcja_wlaczona
        self._prog_udzialu_mowy = prog_udzialu_mowy
        self._wymus_transkrypcje = wymus_transkrypcje

    def obsluguje(self, typ_zrodla: TypZrodla, format_zrodla: str) -> bool:
        return typ_zrodla is TypZrodla.PLIK_AUDIO and format_zrodla in FORMATY_AUDIO

    def wyekstrahuj(
        self,
        identyfikator_zrodla: str,
        bajty: bytes,
        *,
        postep: PostepEkstrakcji | None = None,
    ) -> DokumentWyekstrahowany:
        """Przepisuje mowę z nagrania na tekst albo pomija materiał niemowny.

        Argument `postep` jest wołany w trakcie transkrypcji z parą liczb
        w sekundach: ile sekund nagrania już przepisano i ile trwa całe nagranie.
        """
        if not self._transkrypcja_wlaczona:
            raise PominietoZrodlo(KOMUNIKAT_TRANSKRYPCJA_WYLACZONA, identyfikator_zrodla)
        if not dekodowanie.czy_dostepny():
            raise BrakNarzedzia(dekodowanie.KOMUNIKAT_BRAK_FFMPEGA, identyfikator_zrodla)
        if not czy_dostepna_biblioteka():
            raise BrakNarzedzia(KOMUNIKAT_BRAK_BIBLIOTEKI, identyfikator_zrodla)

        fala = dekodowanie.dekoduj_do_fali(bajty, identyfikator_zrodla=identyfikator_zrodla)
        dlugosc_nagrania = dekodowanie.dlugosc_fali_sekundy(fala)
        dlugosc_mowy = dlugosc_mowy_sekundy(fala, self._ustawienia.prog_vad)
        ocena_mowy = ocen_mowe(dlugosc_mowy, dlugosc_nagrania, self._prog_udzialu_mowy)

        wymuszono = not ocena_mowy.czy_mowa and self._wymus_transkrypcje
        if not ocena_mowy.czy_mowa and not self._wymus_transkrypcje:
            raise PominietoZrodlo(
                KOMUNIKAT_NIEMOWNE.format(
                    udzial=ocena_mowy.udzial_procent, prog=ocena_mowy.prog_procent
                ),
                identyfikator_zrodla,
            )

        wynik = transkrybuj(
            fala,
            self._ustawienia,
            przy_postepie=postep,
            identyfikator_zrodla=identyfikator_zrodla,
        )
        akapity = zbuduj_akapity(
            [
                SegmentNapisow(poczatek_sekundy=segment.poczatek_sekundy, tekst=segment.tekst)
                for segment in wynik.segmenty
            ]
        )
        tekst = zapisz_akapity(akapity, dlugosc_filmu_sekundy=int(round(dlugosc_nagrania)))
        if not tekst.strip():
            raise PominietoZrodlo(KOMUNIKAT_PUSTA_TRANSKRYPCJA, identyfikator_zrodla)

        ostrzezenia: list[str] = []
        ocena_transkrypcji = ocen_transkrypcje(wynik.segmenty)
        if ocena_transkrypcji.czy_podejrzana:
            ostrzezenia.extend(ocena_transkrypcji.powody)

        metadane = {
            "dlugosc_sekundy": str(int(round(dlugosc_nagrania))),
            "jezyk": wynik.jezyk,
            "model_transkrypcji": self._ustawienia.model,
            "udzial_mowy_procent": str(ocena_mowy.udzial_procent),
        }
        if wymuszono:
            metadane["transkrypcja_wymuszona"] = "tak"

        return DokumentWyekstrahowany(
            identyfikator_zrodla=identyfikator_zrodla,
            tekst=tekst,
            poziom_pewnosci_struktury=PoziomPewnosciStruktury.NISKI,
            metoda_ekstrakcji=METODA_EKSTRAKCJI,
            tytul=None,
            metadane=metadane,
            ostrzezenia=ostrzezenia,
        )
