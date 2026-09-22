# Data level delle camere Sony

Ricerca alla base di `slogmetaraw/datalevel.py` e dello stadio `sm_fix_levels` del nodo.
Ogni affermazione è etichettata: **[S]** documentata da Sony · **[E]** verificata da test
di esperti indipendenti · **[I]** dedotta dalla regola di famiglia, senza fonte sul
modello specifico · **[?]** non verificabile. Le fonti sono in fondo.

---

## 1 · La risposta breve

**"Full range" per una curva log Sony non vuol dire che l'immagine riempie 0–1023.**
Vuol dire che i code value vanno letti **non scalati**. Sony pubblica il nero di S-Log3
al codice 95 su 1023 e quello di S-Log2/S-Log al codice 90: una clip S-Log interpretata
correttamente **deve** avere il nero intorno al 9% sul waveform e sembrare "aperta".
Non è un errore.

L'errore vero è un altro, e ha due direzioni:

| Situazione | Effetto a schermo |
|---|---|
| clip **log** (scala full) letta come **Video** | Resolve espande 64–940 → 0–1023, il nero va **sotto zero**: ombre chiuse, mezzitoni leggermente scuri |
| clip **non log** (scala video) letta come **Full** | il nero resta al codice 64 = **6,3%**: neri alzati, alte luci spente, immagine slavata |

Per una a6300 questo significa:

| Profilo | Range registrato | Se Resolve sbaglia |
|---|---|---|
| S-Log2 (PP7) | full, contenuto da 3 a 104 IRE (codici 90–975) **[S][E]** | letta come Video → ombre chiuse |
| S-Log3 (PP8/9) | full, contenuto da 3,5 a 92 IRE (codici 95–870) **[S][E]** | letta come Video → ombre chiuse |
| Cine1 / ITU709 / Movie | video + super-white fino a 109% **[S][E]** | letta come Full → **neri alzati, immagine "più aperta"** |

Quindi: se la clip che sembra "più aperta" è in un profilo **standard o Cine**, è una vera
detezione sbagliata di Resolve. Se è in **S-Log2/S-Log3** e il nero sta al 9%, è corretta —
il log è piatto per costruzione. La a6300 non ha HLG: ha solo PP1–PP9 **[S]**.

---

## 2 · Le due scale, in numeri

| Scala | 0.0 normalizzato | 1.0 normalizzato | Uso |
|---|---|---|---|
| **video** (legal) | codice 64 = 0 IRE | codice 940 = 100 IRE | curve broadcast; 4–63 sotto-nero, 941–1019 super-white |
| **full** (data) | codice 0 | codice 1023 | curve log Sony, spazi di lavoro RGB |

Conversioni (sono esattamente quelle in `datalevel.remap`):

```
video → full :  x' = x · 876/1023 + 64/1023   =  x · 0,856305 + 0,062561
full  → video:  x' = x · 1023/876 − 64/876    =  x · 1,167808 − 0,073059
```

---

## 3 · Code value pubblicati da Sony **[S]**

Dal *Technical Summary for S-Gamut3.Cine/S-Log3 and S-Gamut3/S-Log3*:

| Riflettanza | S-Log IRE / codice | S-Log2 IRE / codice | S-Log3 IRE / codice |
|---|---|---|---|
| nero 0% | 3,0 % / **90** | 3,0 % / **90** | 3,5 % / **95** |
| grigio 18% | 38 % / **394** | 32 % / **347** | 41 % / **420** |
| bianco 90% | 65 % / **636** | 59 % / **582** | 61 % / **598** |

Nota che gli IRE sono ancorati alla scala **video** (0 IRE = codice 64), mentre l'uso nel
file è **non scalato**: è da qui che nasce praticamente tutta la confusione sull'argomento.
Questi tre valori per ciascuna curva sono verificati contro le funzioni di trasferimento del
plugin in `tests/test_datalevel.py`, con tolleranza di un code value (Sony arrotonda).

Sempre **[S]**: *"S-Log3 is recorded as Full range in XAVC, MPEG and HDCAM SR File"*, e
non esiste un'opzione per registrarlo in legal range. L'uscita SDI è full range sempre.
S-Log3 satura intorno al 94 IRE, quindi **non usa i super-white**.

Per **S-Log2 e S-Log v1 non esiste una dichiarazione Sony equivalente**: che siano full
range è attestato da Alister Chapman (*"S-log2 and S-log is always full/data range"*) **[E]**,
non dalla documentazione ufficiale. È l'anello più debole della catena, ed è coerente con i
code value pubblicati (nero a 90, non a 64).

### Tetto di registrazione delle curve non log **[S][E]**

| Curva | Codice hypergamma | Tetto |
|---|---|---|
| Cine1 | HG4609G33 | 109% |
| Cine2 | HG4600G30 | 100% ("optimized for editing") |
| Cine3, Cine4, Movie, Still, ITU709 | — | 109% **[E]** |
| HLG1 / HLG2 / HLG3 | — | ~87% / ~95% / ~100% |

**Resolve non ha un'opzione "extended video"**: ha solo Video e Full. I super-white di una
Cine1 non sono rappresentabili, e questo è un limite reale, non aggirabile da questo plugin.

Utile saperlo: Sony **disabilita** il controllo Black Level quando il profilo è
ITU709(800%), S-Log2 o S-Log3 **[S]**. Su S-Log quindi il nero non può essere spostato dalle
impostazioni di profilo; su Cine/709 sì, ed è una seconda causa di "neri alti" indipendente
dal data level.

---

## 4 · Per famiglia

### Mirrorless, compatte e Cinema Line su MP4 (XAVC S / S-I / HS)

| Corpo | Profili | Scala registrata | Conf. |
|---|---|---|---|
| a6300, a6500 | S-Log2, S-Log3 | full | [S] per S-Log3, [E] per S-Log2 |
| a6300, a6500 | Cine1–4, ITU709, Movie, Still | video + super-white | [S][E] |
| a6400, a6600, a6700, ZV-E10, ZV-E10 II | S-Log2/3, HLG, Cine | log full · HLG e SDR video | [S]/[I] |
| a7 III, a7 IV, a7 V, a7R III/IV/V, a9 II/III, a1, a1 II | S-Log2/3, S-Cinetone, HLG | log full · resto video | [S]/[I] |
| a7S II, a7S III | S-Log2/3 | full (il file interno "flagga" 0–1023) | [E] |
| FX3, FX30, FX2, ZV-E1 | S-Log3, S-Cinetone, HLG | log full · resto video | [S]/[E] |
| RX100 V–VII, RX10 III/IV, RX0 II, ZV-1, ZV-1 II | S-Log2/3, HLG, Cine | log full · resto video | [I] |
| AVCHD (qualunque corpo) | nessun S-Log | video, taggato xvYCC | [E] |

### Cinema Line e camcorder professionali su MXF

| Corpo | Formato | Scala | Conf. |
|---|---|---|---|
| FX6, FX9, FS5/FS5 II, FS7/FS7 II, FR7 | XAVC-I / XAVC-L, S-Log3 | full, 0–1023 | [S][E] |
| stessi corpi, Rec.709 / S-Cinetone | XAVC | video + super-white | [E] |
| PMW-F55 / F5 | XAVC-I, MPEG-2 HD422, SStP | full (Sony cita esplicitamente HDCAM-SR File) | [S] |
| VENICE, VENICE 2, BURANO | X-OCN | **non applicabile**: 16 bit scene-linear | [S] |
| VENICE / BURANO | ProRes interno, S-Log3 | contenuto full, ma **ProRes non ha un flag di range**: va dichiarato a mano | [E] |
| PXW-Z90/Z150/Z190/Z280/Z450 | XAVC-I / XAVC-L | log full · SDR video | [I][E] |
| HDC broadcast | nessuna registrazione interna | SDI S-Log3 full range | [S] parziale |

### Handycam

| Corpo | Scala | Conf. |
|---|---|---|
| FDR-AX700 (ha S-Log2/3 e HLG) | log full · resto video | [I] |
| FDR-AX100, AX53, AX43, AX45, serie CX | **video** (nessun S-Log) | [E][I] |

---

## 5 · Dove il file dichiara il proprio range — e se Sony lo scrive

| Contenitore | Campo | Sony lo scrive? |
|---|---|---|
| MP4 + H.264/HEVC | VUI `video_full_range_flag` (+ primaries/transfer/matrix) | Sì, scrive la VUI. Tutti i dump pubblicati che ho trovato di clip **non log** riportano `tv` (limited). Il campione FX30 S-Log3 di questo progetto riporta invece full (`tests/test_samples.py`). **Non ho trovato un solo dump pubblicato di una clip S-Log consumer**: la tesi "i file interni Sony flaggano full range", ripetuta ovunque, non è mai sostanziata con un nome di campo o un dump. |
| MP4 | box `colr` / `nclx`, bit full_range | Non verificato. Il parser del progetto lo legge comunque. |
| MXF | descrittore CDCI: `0x3304` Black Ref, `0x3305` White Ref, `0x3306` Color Range, `0x3301` Component Depth | Quasi certamente sì. 10 bit: `0/1023/1024` = full, `64/940/897` = video (è la regola di `mxf_get_color_range` di ffmpeg). **Non ho trovato nessun dump pubblicato dei valori che Sony ci scrive**: MediaInfo non li riporta di default (feature request #532, aperta dal 2018). |
| NRT XML (`*M01.XML`) | — | **Non esiste alcun elemento di range.** Ho cercato `LuminanceCodeRange` specificamente: non compare in nessuno schema Sony, tabella ExifTool o parser. L'XML dichiara la *gamma* (`CaptureGammaEquation`), non la scala. |
| RTMD per-frame | `0x8120` Luminance code range | Sì, ed è la dichiarazione Sony più autorevole che esista per clip. L'unico valore confermato contro Catalyst Browse è `2 = Full Scaled Code` (FX6, FX30). Nessun valore "legal" è mai stato osservato. |

**Conclusione**: l'unico posto dove un file Sony dichiara esplicitamente la scala è il flag
del codec (MP4) o il descrittore immagine (MXF), più il tag RTMD 0x8120 quando c'è. Gli altri
metadata Sony dichiarano la **curva**, e la scala è una convenzione che discende da quella.
È per questo che `datalevel.py` fa derivare il valore *richiesto* dalla gamma, e usa i flag
solo come conferma — segnalando il disaccordo invece di nasconderlo.

---

## 6 · Cosa fa DaVinci Resolve

**Auto** è documentato in una sola frase, identica dal manuale di Resolve 12 a quello di
Resolve 20, capitolo *Data Levels, Color Management, and ACES*:

> "When a clip is set to Auto, the Levels setting used is determined based on the codec of
> the source media."

**Il codec. Non i flag.** Non esiste una tabella per-codec pubblicata, né una dichiarazione
che la VUI H.264/HEVC venga consultata. (Per il PNG sì: Resolve 20 legge il range da `cICP`,
confermato sulla mailing list W3C public-png. Per i codec video resta indeterminato.)

Numericamente, su una sorgente YCbCr a 10 bit:

- **Video** → `float = (CV − 64)/876`. Sotto-neri e super-white sopravvivono come valori
  negativi e > 1.0 nel pipeline float a 32 bit.
- **Full** → `float ≈ CV/1023`, nessuna scalatura.

La scalatura avviene **in decodifica**, prima del node graph e **prima** della trasformazione
di input di Resolve Color Management. È la stessa in DaVinci YRGB, in RCM e in ACES: cambia
solo il danno, perché in RCM il valore mal scalato viene poi dato in pasto a un inverso di
S-Log3 fortemente non lineare nel piede, e l'errore diventa una distorsione di tinta e
contrasto invece di un semplice scostamento di livello.

Sony stessa scrive, nel readme di Catalyst Browse, che gli NLE sbagliano:

> "some NLEs could recognize the clip as video range … If the NLE has an input range setting —
> such as newer versions of DaVinci Resolve — you can set the range to Full".

### Perché il nodo non può chiederlo a OpenFX

Ho verificato l'intero set di header OpenFX distribuito con Resolve (`OpenFX-1.4/include`,
`ofxColour.h`, `ofx-native-v1.5_aces-v1.3_ocio-v2.3.h`) e quello upstream. Cercando ogni
proprietà che contenga `Range`, `Level`, `Legal`, `Luma`, `Black` o `White` si ottengono
esattamente due risultati: `kOfxImageEffectPropFrameRange` e
`kOfxImageEffectPropUnmappedFrameRange`. **Nessuna proprietà di range.**

Anche la gestione colore di OpenFX 1.5 non lo esprime: i 180 identificatori di colourspace
dichiarano un attributo `Encoding` i cui unici valori sono `""`, `hdr-video`, `log`,
`scene-linear`, `sdr-video` — famiglie di transfer, non scala del segnale.

Restano due strade, e questo progetto le usa entrambe:
1. leggere il file per conto proprio via `kOfxImageEffectPropSrcFilePath` (estensione privata
   di Resolve, dichiarata in `ofxImageEffectExt.h`);
2. leggere l'attributo della clip via API di scripting — `GetClipProperty('Data Level')`
   restituisce `'Auto'`, `'Full'` o `'Video'`, e `SetClipProperty` lo scrive.

La seconda è la più importante: rende la correzione una **differenza nota** invece di una
congettura. Quando l'attributo è ancora su `Auto` il valore effettivo non è osservabile da
nessuna API, e allora il nodo **non corregge niente** e lo dice.

---

## 7 · Come lo fa CineMatch, per confronto

CineMatch espone un parametro `datarange` ("Data Range": *Limited* / *Full*) nel gruppo
Advanced. Il default **non viene dedotto dal file**: arriva da un attributo `range` sul
profilo camera in `cmCameraList_v046.xml`, scelto dall'utente con due menu a tendina. Il
plugin non legge mai il file sorgente. La matematica applicata è la stessa affine 64–940
usata qui, applicata per canale in RGB.

Nel listino, tutti i corpi Sony moderni sono taggati `Limited` per S-Log3 — in apparente
contraddizione con Sony. La lettura coerente è che "Limited" descriva **ciò che arriva al
plugin dopo che l'host ha già espanso 64–940 → 0–1**, non il file: applicare `full_to_legal`
a `(CV−64)/876` restituisce esattamente `CV/1023`. Depone a favore il fatto che i corpi più
vecchi abbiano due voci per lo stesso pacchetto, "(AVCHD)" = Full e "(XAVC S)" = Limited,
che a parità di sensore hanno gli stessi code value e differiscono solo per come gli NLE li
hanno storicamente interpretati.

La differenza pratica con questo plugin: CineMatch chiede all'utente di sapere la risposta,
qui la risposta viene letta da Resolve e dai metadata, e l'utente interviene solo quando
vuole scavalcarla.

---

## 8 · Cosa fa S-Log MetaRaw

1. **Lo script** legge `Data Level` di ogni clip e, con la casella *Correggi il Data Level*
   attiva, lo imposta esplicitamente a Full o Video secondo la gamma di ripresa. È la
   correzione vera: vale per tutto il progetto — CST, RCM, scope, export — non solo per il
   nodo. È reversibile (`SetClipProperty` riaccetta `'Auto'`).
2. **Il nodo** confronta la scala che la curva richiede con quella su cui Resolve ha
   decodificato la clip e, se differiscono, applica la remap affine sui **code value**, nel
   dominio della curva di camera, **prima** della decodifica log — così esposizione e
   bilanciamento continuano a lavorare su valori lineari corretti. Quando il nodo riceve
   DaVinci WG/Intermediate, Rec.709 o ACEScct invece della codifica di camera, la remap fa
   un giro completo (lineare → gamut camera → curva camera → remap → indietro): le funzioni
   di trasferimento e le matrici sono inverse esatte, quindi il risultato è identico in ogni
   pipeline. È verificato in `tests/test_datalevel.py`.
3. **Avanzate › Data level in ingresso** permette di dichiarare a mano la scala (utile su un
   ProRes Atomos della stessa ripresa, che nessun NLE segnala correttamente) o di disattivare
   del tutto la correzione.

Limite noto: la remap è per canale in RGB, come in CineMatch e come in ogni conversione
legal↔full standard. Resolve scala la crominanza su 64–960 invece di 64–940, quindi resta un
errore di saturazione di circa il 2% che una remap in RGB non può annullare. È molto sotto
l'errore che stiamo correggendo.

---

## 9 · Come verificarlo sui propri file

```bash
# 1. cosa dichiara il contenitore (colr MP4 / CDCI MXF)
ffprobe -v error -select_streams v:0 \
  -show_entries stream=codec_name,pix_fmt,color_range,color_space,color_transfer,color_primaries \
  -of default=noprint_wrappers=1 CLIP.MP4
```

```bash
# 2. cosa dichiara il bitstream (il flag autorevole per H.264/HEVC)
ffmpeg -v trace -i CLIP.MP4 -c copy -bsf:v trace_headers -f null - 2>&1 \
  | grep -m5 -iE "video_full_range_flag|video_signal_type"
```

```bash
# 3. i livelli di riferimento di un MXF (spesso visibili solo in MediaTrace)
mediainfo --Details=1 CLIP.MXF | grep -iE "Black Ref|White Ref|Color Range|Component Depth"
```

```bash
# 4. i code value davvero presenti: è questo che chiude ogni discussione
ffprobe -v error -f lavfi "movie='CLIP.MP4',format=yuv422p10le,signalstats" \
  -show_entries frame_tags=lavfi.signalstats.YMIN,lavfi.signalstats.YMAX,lavfi.signalstats.YAVG \
  -of csv=p=0 | head
```

Lettura del punto 4: una S-Log3 corretta ha `YMIN` intorno a 95 e `YMAX` che non supera
~890; una S-Log2 arriva fino a ~975; una Cine1 parte da 64 e può arrivare a ~1019. Lo stesso
si vede sul waveform di Resolve con Data Level = Full: nero al 9% per il log, nero a 0% per
le curve broadcast.

Il modo più rapido dentro questo progetto:

```bash
python3 -m slogmetaraw CLIP.MP4 | grep -iA2 "Data level"
```

---

## 10 · Cosa non sono riuscito a determinare

Elencato apposta, perché il codice non deve dare l'impressione di sapere più di quanto sappia.

1. **Nessuna dichiarazione Sony per-modello** del data level. L'unica affermazione ufficiale
   è a livello di formato (S-Log3 in XAVC / MPEG / HDCAM-SR).
2. **Nessuna dichiarazione Sony che S-Log2 sia full range.** Solo Chapman, più la coerenza
   dei code value pubblicati.
3. **Nessuna prova a livello di bitstream** che un corpo consumer Sony scriva
   `video_full_range_flag = 1` su una clip S-Log. L'affermazione è ripetuta ovunque e non è
   mai sostanziata.
4. **Nessun dump pubblicato** dei valori Black Ref / White Ref che Sony scrive negli MXF.
5. **L'algoritmo esatto di Auto in Resolve non è pubblicato.** "Based on the codec" e
   nient'altro.
6. Le righe **[I]** nelle tabelle (HXR-NX, RX0 II, a7 II, Z450, FR7, HDC) sono deduzioni di
   famiglia, non fonti sul modello.

Per i punti 1–4 il rimedio è nel progetto stesso: eseguire lo script su clip reali delle
proprie camere e leggere la sezione VIDEO del pannello dettagli, che ora riporta insieme il
range dichiarato dal file, i livelli di riferimento MXF e la scala richiesta dalla curva.
Se i due non coincidono, il campo *Interpretazione in Resolve* lo dice esplicitamente.

---

## Fonti

**Sony** · [Technical Summary S-Gamut3.Cine/S-Log3](https://pro.sony/s3/cms-static-content/uploadfile/06/1237494271406.pdf) ([mirror leggibile](http://starcentral.ca/forums/LUTs/TechnicalSummary_for_S-Gamut3Cine_S-Gamut3_S-Log3_V1_01.pdf)) · [Picture Profile ILCE-6300](https://helpguide.sony.net/ilc/1540/v1/en/contents/TP0000824626.html) · [Picture Profile ILCE-6400](https://helpguide.sony.net/ilc/1810/v1/en/contents/TP0002273496.html) · [Picture Profile DSC-RX100M7](https://helpguide.sony.net/dsc/1920/v1/en/contents/TP0001211745.html) · [Caratteristiche dei formati file](https://support.d-imaging.sony.co.jp/support/ilc/hevc/01/en/index.html) · [Broadcast XAVC white paper](https://pro.sony/en_EE/technology/xavc/broadcast-xavc-white-paper) · [X-OCN](https://pro.sony/ue_US/technology/recording-formats/technology-xocn) · readme di Catalyst Browse

**Alister Chapman (Sony Independent Certified Expert)** · [Sony's Internal Recording Levels Are Correct](https://www.xdcam-user.com/2019/03/01/sonys-internal-recording-levels-are-correct/) · [Are You Screwing Up Your Footage In Resolve?](https://www.xdcam-user.com/2014/03/19/are-you-screwing-up-your-footage-in-resolve/) · [S-Log2 e S-Log3 sulla a6300](https://www.xdcam-user.com/2016/05/11/using-s-log2-and-s-log3-with-the-sony-a6300-with-luts-to-download/) · [interno contro esterno](https://www.xdcam-user.com/2020/01/05/why-does-s-log-recorded-internally-look-different-to-s-log-recorded-on-an-external-recorder/) · [Cinegamma e Hypergamma](https://www.xdcam-user.com/picture-settings-and-luts/picture-profile-guide/correct-exposure-with-cinegammas-and-hypergammas/)

**Blackmagic** · DaVinci Resolve 20 Reference Manual, cap. 9 *Data Levels, Color Management, and ACES* · SDK OpenFX distribuito con Resolve (`ofxImageEffectExt.h`, `ofxColour.h`)

**Altro** · [CineD, neri chiusi su a7S/a7S II](https://www.cined.com/fix-crushed-blacks-on-sony-a7s-and-a7s-ii-external-recordings/) · [Newsshooter, X-OCN Explained](https://www.newsshooter.com/2023/05/09/sony-x-ocn-explained/) · [AbelCine, X-OCN workflows](https://www.abelcine.com/articles/blog-and-knowledge/tutorials-and-guides/x-ocn-workflows-with-the-sony-venice) · [wolfcrow, esporre S-Log3](https://wolfcrow.com/how-to-expose-s-log3/) · [colour-science, discussione #786](https://github.com/colour-science/colour/discussions/786) · [ffmpeg `mxf_get_color_range`](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/mxfdec.c) · [MediaInfo feature request #532](https://sourceforge.net/p/mediainfo/feature-requests/532/) · [FilmConvert, CineMatch Resolve workflow](https://www.filmconvert.com/blog/cinematch-resolve-workflow-guide/)
