<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadata Sony e controlli Camera Raw per DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <b>Italiano</b> · <a href="README.zh.md">简体中文</a> · <a href="README.es.md">Español</a> · <a href="README.pt.md">Português</a>
</p>

---

## Premessa

La camera ha già registrato com'era impostata la ripresa: bilanciamento del bianco in Kelvin, tint, EI, obiettivo,
shutter, profilo colore. Sugli MXF di un FX6 Resolve usa queste informazioni e apre il pannello
**Camera Raw › Sony Video**. Sugli MP4 di FX30, FX3 o a6300 le stesse informazioni sono dentro al file — e Resolve le
ignora.

S-Log MetaRaw le legge e le rimette al lavoro, così bilanciamento, esposizione e spazio colore partono da quello che ha
registrato la camera invece che da una stima. Niente transcodifica, e i file originali non vengono mai toccati.

Non è raw. Un MP4 log è un'immagine già sviluppata e compressa, e nessun plugin può tornare indietro. Quello che si può
fare è rimettere mano alle decisioni prese in ripresa — quelle che il raw ti lascerebbe rivedere — sull'immagine che è
stata effettivamente registrata, in luce lineare e con scienza del colore pubblicata.

| | |
|---|---|
| **Script** (Workspace › Scripts) | Legge i metadata di **tutte le clip del progetto in una volta sola**, o solo di quelle selezionate, e li registra nel Media Pool: pannello Metadata, colonne, keyword per le smart bin, data burn, export CSV. Mostra tutto quello che ha letto, raggruppato come lo raggruppa Catalyst Browse, e corregge i campi che Resolve compila male sugli MXF, come *Camera Aperture* che sull'FX6 diventa `F53343`. |
| **Plugin** (OpenFX, pagina Color) | Una clip alla volta, come se avessi il pannello Raw sotto mano: Color Temp, Tint, Exposure (EI), White Balance, Color Space/Gamma e toni. **Si imposta da solo** con i valori di ripresa di quella clip, e a quei valori è neutro: finché non muovi qualcosa non cambia niente. Corregge anche il **data level** quando Resolve legge la clip sulla scala sbagliata, sviluppa le alte luci con una **spalla filmica** che non clippa mai, e porta tre viste **false color** per piazzare esposizione e bilanciamento misurando invece che a occhio. |

---

## Installazione

1. Scarica `SLogMetaRaw-x.y.z.dmg` dalla pagina **Releases** e aprilo.
2. Doppio clic su **Installa S-Log MetaRaw.pkg**. L'installer non è firmato con un certificato Apple, quindi la prima
   volta va aperto con tasto destro › **Apri**.
3. Riavvia DaVinci Resolve.

L'installer mette esattamente tre cose:

| Percorso | Cosa |
|---|---|
| `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` | il nodo OpenFX |
| `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` | la libreria Python (i parser) |
| `…/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` | la voce di menu dello script |

Durante l'uso scrive anche una piccola scheda JSON per clip in `~/Library/Application Support/SLogMetaRaw/cache`, e i CSV
esportati finiscono in `~/Documents/SLogMetaRaw`. **Disinstalla S-Log MetaRaw.command**, sul disco, rimuove tutto. Sul
disco ci sono anche le guide di una pagina, **Guida S-Log MetaRaw (italiano).pdf** e
**S-Log MetaRaw Guide (english).pdf**.

**Requisiti:** macOS 12 o successivo (Apple Silicon o Intel) e DaVinci Resolve 21. **Testato solo su Resolve Studio 21.1
su macOS.** Sulle versioni precedenti non è stato provato: lo script potrebbe funzionare se hai Python 3 installato
(Resolve include il proprio interprete solo dalla 21.1), mentre il plugin usa funzioni introdotte con Resolve 21 — la
gestione colore OpenFX 1.5 soprattutto — e lì andrebbe impostato a mano *Avanzate › Ingresso nodo*.

**Clip supportate:** Sony XAVC, `.MP4` o `.MXF`, registrate in **S-Log2 o S-Log3**. I profili che il nodo sviluppa sono
`S-Gamut3.Cine/S-Log3`, `S-Gamut3/S-Log3`, `S-Gamut/S-Log2` e `S-Gamut/S-Log`. Lo script legge i metadata di qualsiasi
clip Sony XAVC, log o no; il nodo su tutto il resto resta neutro.

### Se lo script non si apre

Apri un progetto e scegli **Workspace › Scripts › S-Log MetaRaw**. Il launcher usa prima la connessione fornita da
Resolve; se `localhost` non risponde, prova gli indirizzi assegnati allo stesso Mac. Non cerca istanze su altri computer
e non modifica le preferenze di rete. Gli errori di avvio sono registrati in
`~/Library/Logs/SLogMetaRaw/launcher.log` e mostrati in un messaggio.

Da questa cartella puoi aggiornare solo lo script con `./install.sh --dev --script-only`. Il lettore usa il Python
incluso in Resolve 21.1 con un percorso libreria esplicito: questo interprete ignora `PYTHONPATH`.

---

## Guida

### 1 · Lo script

**Workspace › Scripts › S-Log MetaRaw.** La finestra è essenziale: una riga di pulsanti, una riga di opzioni, e sotto
le clip lette. Si apre sempre al centro della finestra di DaVinci Resolve (anche a tutto schermo), è ridimensionabile,
e in basso a destra mostra la versione del programma — cliccabile, per il controllo aggiornamenti in arrivo.

- **Origine** — *Tutto il Media Pool* (predefinito) o *Clip selezionate nel Media Pool*.
- **1 · Leggi metadata** — legge le clip, con un indicatore di avanzamento in percentuale: sui progetti grandi vedi
  sempre a che punto è la lettura. Non scrive ancora niente. La tabella si riempie con una riga per clip: Clip, Camera,
  obiettivo, focale, diaframma, shutter, ISO/EI, WB, color space, data level, e una colonna *Stato* che dice `letto`,
  oppure `letto · varia: diaframma, fuoco` quando un valore è cambiato durante la ripresa, o perché una clip è stata
  saltata. **Cliccando una riga** il pannello sotto mostra tutto quello che è stato letto, nelle stesse sezioni di
  Catalyst Browse. Al termine, un suono avvisa che la lettura è finita.
- **2 · Scrivi in Resolve** — registra i metadata nel Media Pool, anche qui con l'avanzamento percentuale e il suono a
  fine operazione.
- **Esporta CSV (campi custom)** — scrive un CSV in `~/Documents/SLogMetaRaw` con i valori per cui Resolve non ha un
  campo (sotto c'è l'elenco).

Tre spunte:

- **Tag per camera** — disattiva di default. Attivala per aggiungere alle keyword di ogni clip la camera (modello), la
  gamma e le primarie: utili per le smart bin.
- **Sovrascrivi i metadata già presenti** — attiva di default. È quella che corregge i valori sbagliati che Resolve
  scrive da solo, tipo *Camera Aperture* `F53343` sugli MXF dell'FX6. Se la togli, vengono riempiti solo i campi vuoti.
- **Correggi il Data Level** — **attiva di default**. Imposta l'attributo *Data Level* di ogni clip su Full o Video
  secondo la gamma di ripresa. È la correzione vera: sistema la decodifica per tutto il progetto — CST, RCM, scope,
  export — non solo per il nodo, ed è reversibile. Le curve log Sony sono pubblicate su code value non scalati e
  vogliono *Full*; Rec.709, Cine e HLG vogliono *Video*. In [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) c'è tutta la
  ricerca, camera per camera.
- **Imposta anche Input Color Space (RCM) dai metadata** — disattiva di default. Comoda in un progetto color managed,
  ma attenzione: una volta impostato via script il valore non si può riportare a *Project* da script — solo a mano,
  dentro Resolve.

I file originali non vengono mai modificati: lo script li legge e basta.

### 2 · Il nodo

**Pagina Color › OpenFX › S-Log MetaRaw**, come **primo nodo**, prima di CST e LUT. In alto mostra la camera e porta
Color Temp, Tint ed Exposure ai valori di ripresa. A quei valori non fa niente all'immagine: è un punto di partenza, non
un look. Se copi il nodo su un'altra clip, si reimposta con i dati di quella clip.

| Controllo | Intervallo | Default | Cosa fa |
|---|---|---|---|
| **Rileggi metadata** | — | — | rilegge la clip e riporta tutti i controlli ai valori di camera |
| **Decode Using** | Camera metadata / Clip | Clip | *Camera metadata* blocca tutto sui valori di ripresa e ingrigisce i controlli; *Clip* te li lascia modificare |
| **White Balance** | As shot · Daylight 5600 K · Cloudy 6500 K · Shade 7500 K · Tungsten 3200 K · Fluorescent 4000 K · Flash 5500 K · Custom | As shot | preset; muovendo uno slider passa a *Custom* |
| **Color Temp** | 2000–15000 K | di ripresa | adattamento cromatico in luce lineare |
| **Tint** | −100 … +100 | di ripresa | verde/magenta, perpendicolare al luogo di Planck |
| **Exposure** | 25–409600 EI (slider 50–25600) | di ripresa | exposure index: EI doppio = +1 stop |
| **False color: temperatura / tint / esposizione** | acceso · spento | spento | una vista di misura per controllo, ciascuna sopra lo slider che serve. L'esposizione divide in bande le fermate attorno al grigio 18% alla maniera ARRI; le due viste di bilanciamento leggono la distanza dal neutro **in Kelvin e in unità di tint**, quindi la banda dice di quanto sei fuori. Bianco = neutro. Una sola per volta, e la vista sostituisce l'immagine: spegnila prima di renderizzare. [docs/FALSE_COLOR.md](docs/FALSE_COLOR.md) |
| **Color Space** | Timeline · DaVinci WG · Rec.709 · Rec.2020 · P3 D65 · P3 D60 · P3 DCI · S-Gamut · S-Gamut3 · S-Gamut3.Cine · ACES AP0 · ACES AP1 | Timeline | gamut in uscita, come un Color Space Transform. *Timeline* non converte |
| **Gamma** | Timeline · DaVinci Intermediate · Linear · Gamma 2.2 · Gamma 2.4 · Gamma 2.6 · Rec.709 · sRGB · SLog · SLog2 · SLog3 · ACEScct | Timeline | curva in uscita. *Timeline* non converte |
| **Toni › Highlights** | −100 … +100 | 0 | dice, in stop, **dove atterra il tetto del contenitore registrato**. In negativo lo preme verso un asintoto che non raggiunge mai, quindi non clippa nulla, e sposta il grigio 18% di 0,008 stop. A −100 i +7,74 stop che una S-Log3 porta sopra il grigio atterrano esatti su 1,0 lineare, il picco che un segnale Rec.709 contiene. In positivo fa lo specchio: stira il tetto della scala, fino a 2 stop, per riportare al picco un'alta luce che satura prima. La corsa è **lineare nel cursore**, quindi ogni punto vale uguale |
| **Toni › Shadows** | −100 … +100 | 0 | apre o chiude il dettaglio in ombra attorno a −4 stop. È un moltiplicatore, quindi il nero assoluto resta nero a qualsiasi valore, e sotto −8 stop il piede non si muove |
| **Toni › Color Recovery** | −100 … +100 | 0 | quanto colore restituisce la pressa. È il peso fra due modi di applicare la stessa curva: un fattore unico sui tre canali, che tiene tutto il colore di scena, e la curva per canale, dove i tre condividono un soffitto e salendo convergono — perché convergere *è* desaturare, ed è così che fa la pellicola. A destra tiene il colore, a sinistra va verso la pellicola. Non può mai aggiungere colore che il pixel non aveva. È la leva organica per togliere il neon a un cielo recuperato e per non far diventare un piattone rosa una fronte chiara. [docs/TONE_MAPPING.md](docs/TONE_MAPPING.md) |
| **Toni:** Color Boost, Saturation, Contrast | −100 … +100 | 0 | ritocchi di colore e contrasto, sulla stessa scala che Resolve usa per Col Boost e Contrast |
| **Avanzate › Ingresso nodo** | Automatico · DaVinci WG/Intermediate · S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · ACES AP1/ACEScct | Automatico | lo spazio colore che entra nel nodo. *Automatico* lo chiede a Resolve: cambialo solo se quello che risponde è sbagliato |
| **Avanzate › Data level in ingresso** | Automatico · Full (0-1023) · Video (64-940) · Nessuna correzione | Automatico | la scala di code value su cui Resolve ha decodificato la clip. *Automatico* usa l'attributo Data Level della clip; finché quello è su *Auto* non corregge niente, perché il valore che Resolve ha usato davvero non è leggibile da nessuna API. Dichiaralo a mano per un file che nessun NLE segnala bene, tipo un ProRes Atomos della stessa ripresa — vedi [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) |
| **Avanzate › Rilevato / Data level / Stato** | — | — | cosa ha rilevato, quale scala sta usando e perché, e se i metadata sono stati trovati |
| **Dati di ripresa** | — | — | sola lettura: obiettivo, focale, diaframma, fuoco, shutter, ISO/EI, bilanciamento, colore, frame rate, ND/stabilizzatore, LUT di camera, file |

Il nodo tiene le impostazioni per clip: vengono salvate con la correzione e ritornano quando riapri quella clip. Si
azzerano solo passando a una clip diversa o premendo *Rileggi metadata*.

### 3 · Un ordine di lavoro

1. Importa il girato, lancia lo script, premi **1** e poi **2**.
2. In pagina Color metti **S-Log MetaRaw** per primo, lascia *Color Space* e *Gamma* su *Timeline* se il progetto è color
   managed, e fai seguire il tuo CST o la tua LUT.
3. Correggi bianco ed esposizione **nel nodo** invece che con lift/gamma/gain: lì l'intervento avviene in luce lineare,
   prima di qualsiasi curva, cioè dove l'avrebbe fatto la camera.

---

## Cosa viene scritto in Resolve

**Campi standard**, compilati solo quando la clip contiene davvero quel valore:

`Camera Manufacturer` · `Camera Type` · `Camera TC Type` · `Camera Serial #` · `Camera Firmware` · `Camera FPS` ·
`Shutter Type` · `Shutter Angle` · `Shutter Speed` · `Exposure Mode` · `ISO` · `White Point (Kelvin)` ·
`White Balance Tint` · `Mon Color Space` · `Monitor LUT` · `LUT Used` · `Lens Type` · `Lens Number` · `Lens Notes` ·
`Camera Aperture Type` · `Camera Aperture` · `Focal Point (mm)` · `Distance` · `ND Filter` · `Codec Bitrate` ·
`Sensor Area Captured` · `PAR Notes` · `Aspect Ratio Notes` · `Gamma Notes` · `Color Space Notes` · `Date Recorded`

In **Camera Notes** finisce un riepilogo leggibile, in **Keywords** modello, gamma, primarie e `S&Q` quando la clip è
girata in slow o fast motion — servono per le smart bin. Tutto quello che è stato letto, anche i valori senza un campo
standard, viene allegato come metadata di terze parti con il prefisso `SLogMetaRaw.`.

**Input Color Space** (solo se spunti la casella) viene mappato così:

| Nella clip | Impostato in Resolve |
|---|---|
| S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · S-Gamut/S-Log | lo stesso nome |
| ITU-R BT.2100 HLG · HLG Live · HLG Mild | Rec.2100 HLG |
| S-Cinetone · ITU-R BT.709-5 | Rec.709 (Scene) |

**L'export CSV** copre quello per cui Resolve non ha un campo: EI, ISO, gain, modo WB, preset di luce, tint, modo AE,
area AF, focale equivalente 35 mm, distanza di fuoco, color space, gamma di ripresa, luminance code range, range del
codec, stabilizzatore, LUT di monitoring, modo di registrazione, fps di ripresa, ora di registrazione, formato. Il file è
scritto nel formato CSV dei metadata di Resolve (UTF-16); si importa da **File › Import › Metadata**, con l'opzione per
creare i campi custom attiva.

---

## Come funziona

### Dove sono i dati, e quanto poco file viene letto

Nei file Sony XAVC i dati di ripresa sono registrati **fotogramma per fotogramma**:

- negli **MP4**, nella traccia di metadata temporizzati `rtmd`;
- negli **MXF**, in pacchetti ANC SMPTE ST 436 (DID 0x43 / SDID 0x05).

In entrambi i casi sono strutture KLV con i set di acquisizione **SMPTE RDD 18**, più i tag proprietari Sony. Accanto ci
sono l'XML *NonRealTimeMeta* — il sidecar `M01.XML` o una copia incorporata — con modello, matricola, firmware, gamma di
ripresa e primarie, e l'**SPS** H.264/HEVC, che dà profilo, bit depth e range pieno o limitato. Sugli MXF legge anche
il **descrittore immagine CDCI** (livelli di riferimento del nero e del bianco), che è l'unico posto in cui un MXF
dichiari la propria scala di code value.

### Data level

Sony pubblica le sue curve log su code value **non scalati** — il nero di S-Log3 è il codice 95 su 1023, il grigio 18%
è 420, il bianco 90% è 598; S-Log2 e S-Log mettono il nero a 90 — mentre Rec.709, le Cine e HLG sono ancorate al range
legale, 0 IRE = codice 64. Resolve decide su quale scala decodificare una clip dall'attributo *Data Level*, e il suo
*Auto* è documentato come una deduzione dal codec. Quando sbaglia, ogni valore che entra nella decodifica log è
sbagliato, e soprattutto nelle ombre: una clip log letta come *Video* chiude i neri, una Rec.709 o Cine letta come
*Full* li alza e slava l'immagine.

S-Log MetaRaw capisce quale scala serve alla gamma della clip, legge cosa sta facendo davvero Resolve (`Data Level` è
esposto dall'API di scripting) e chiude il buco da entrambi i lati: lo script imposta l'attributo giusto — e così
sistema la decodifica per tutto il progetto, non solo per questo nodo — e il nodo corregge quello che resta, rimappando
i code value nella codifica di camera **prima** della decodifica log, così esposizione e bilanciamento continuano a
lavorare su luce lineare corretta. Funziona uguale in DaVinci YRGB, in timeline color managed e in ACES: quando al
nodo arriva DaVinci WG/Intermediate o ACEScct invece della codifica di camera, la rimappatura fa un giro completo
attraverso trasformazioni esattamente invertibili. In [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) c'è tutta la ricerca:
i numeri pubblicati da Sony, una tabella per famiglia di camere, cosa dichiara davvero ogni contenitore e cosa non è
stato possibile stabilire.

Il parser legge l'indice del file e campiona la traccia di metadata **una volta al secondo, fino a 120 campioni**. È così
che la colonna *Stato* può dirti che diaframma o fuoco sono cambiati durante la ripresa, ed è il motivo per cui una clip
da diversi GB costa circa **100 KB di lettura**: non si decodifica niente, non si renderizza nessun fotogramma.

Tutto in Python puro, senza dipendenze esterne, senza ExifTool, senza niente da installare oltre al pacchetto stesso.

### Dallo script al nodo

Lo script usa l'API di scripting di Resolve 21.1 (Resolve include Python 3.14). Oltre ai campi del Media Pool, ogni clip
riceve una scheda JSON piatta in `~/Library/Application Support/SLogMetaRaw/cache`, con il nome ricavato da un hash del
percorso della clip.

Il nodo sa qual è il file della clip grazie all'estensione Resolve `kOfxImageEffectPropSrcFilePath`, e legge quella
scheda: è così che si imposta da solo. Se la scheda manca, se la genera eseguendo `ResolvePython -m slogmetaraw --cache`
sulla clip. Quella lettura gira sul thread dell'interfaccia, quindi è tenuta al guinzaglio: al massimo 8 secondi, un solo
tentativo per clip, e i file che sul disco sono solo un segnaposto di un servizio cloud vengono saltati invece che
scaricati. Lo spazio colore di lavoro del nodo arriva da Resolve tramite la gestione colore OpenFX 1.5.

### La matematica del colore

Tutto avviene in **luce lineare**, nel gamut che entra nel nodo, in quest'ordine:

1. **Decodifica** della curva in ingresso e moltiplicazione per il rapporto di esposizione `EI scelto / EI di ripresa` —
   raddoppiare l'EI è esattamente uno stop.
2. **Bilanciamento del bianco**: adattamento di von Kries in **LMS Bradford**, dal bianco di ripresa al bianco scelto.
   Entrambi i bianchi vengono dal **luogo di Planck** (approssimazione cubica di Kim et al. 2002, valida fra 1667 e
   25000 K); il *Tint* sposta il bianco perpendicolarmente al luogo, nel piano CIE 1960 *uv*. Il risultato è normalizzato
   perché lo spostamento non cambi la luminanza del D65.
3. **Toni**: la scena è una vasca di luce lineare con il grigio 18% come mediana e un tetto dato dalla curva che la
   camera ha registrato — +7,74 stop per l'S-Log3, una proprietà del formato, mai dell'immagine. `Highlights` è una
   pressa che scende da quel tetto; `Shadows` è una campana attorno a −4 stop; `Contrast` è una legge di potenza sulla
   stessa power norm. Tutti e tre sono monotoni per canale per costruzione, quindi un pixel più luminoso non può mai
   uscire più scuro.
4. **Saturation e Color Boost**: una scalatura attorno alla luminanza; il Color Boost è una vibrance, pesata su quanto
   ogni pixel è già saturo, quindi alza i colori spenti e lascia stare quelli già forti.
5. **Color Space / Gamma**: se uno dei due è diverso dallo spazio del nodo, conversione attraverso XYZ, esattamente come
   un Color Space Transform; altrimenti l'immagine viene ricodificata nella curva con cui è entrata.

Le funzioni di trasferimento seguono le definizioni pubblicate: **S-Log, S-Log2 e S-Log3** dai paper Sony, **DaVinci
Intermediate**, **ACEScct**, **Rec.709** (OETF BT.709), **sRGB** e le gamma pure 2.2 / 2.4 / 2.6. Le matrici di gamut,
con le rispettive inverse, coprono DaVinci Wide Gamut, Rec.709, Rec.2020, P3 D65/D60/DCI, S-Gamut, S-Gamut3,
S-Gamut3.Cine, ACES AP0 e AP1 (S-Gamut3 ha le stesse primarie di S-Gamut, come documenta Sony).

La matematica sta in un unico file, `DevelopMath.h`, generato da `tools/build_math.py` e compilato **sia** come C++
**sia** come kernel **Metal**: così il percorso GPU e quello CPU non possono divergere. Il render gira su Metal, con
fallback su CPU.

Dove la camera non ha registrato la temperatura colore — l'a6300 per esempio — il valore viene ricavato dal preset di
luce che invece ha registrato (Daylight 5600 K, Cloudy 6500 K, Shade 7500 K, Incandescent 3200 K, Fluorescent 4000 K,
altrimenti 5600 K) e il nodo lo segnala come stimato, nella riga di stato e nei dati di ripresa.

### Cosa è stato verificato

- **Campo per campo contro Catalyst Browse** su FX6, FX30 e a6300: etichette e valori.
- **Tre implementazioni che coincidono.** Il modello di riferimento in Python, il codice C++ e il kernel Metal coincidono
  entro **2·10⁻⁴** su una scansione casuale di parametri e spazi colore.
- **Dentro Resolve**: le LUT esportate dal nodo sono state confrontate con lo stesso modello, errore sotto **0,0003**.
- **Un host OpenFX in miniatura** (`tests/host_test.cpp`) carica il plugin compilato e ripete quello che fa Resolve —
  caricamento, descrizione, entrambi i contesti, costruzione del nodo su una clip vera — così un crash nel pannello si
  vede qui invece che in Resolve.
- In tutto 25 test automatici: parser, modello di sviluppo, C++, Metal, host OpenFX, parametri del plugin.

---

## Compilare dal sorgente

```bash
make -C ofx/SLogMetaRaw                     # plugin universale arm64 + x86_64 (serve Xcode)
./install.sh --dev                          # installa script e plugin puntando a questa cartella
./install.sh --dev --script-only            # aggiorna solo lo script, senza password amministratore
python3 -m unittest discover -s tests       # i 25 test
./packaging/build_installer.sh              # crea dist/SLogMetaRaw-x.y.z.dmg
python3 -m slogmetaraw cartella_o_file      # vista stile Catalyst da riga di comando
python3 -m slogmetaraw --cache clip.MP4     # scrive solo la scheda JSON che legge il nodo
```

```
slogmetaraw/         parser mp4, mxf, rtmd, nrt, codec · scrittura in Resolve · finestra dello script
resolve_script/      launcher per Workspace › Scripts
ofx/SLogMetaRaw/     plugin OpenFX (C++, Metal); DevelopMath.h è generato da tools/build_math.py
tools/               matrici dei gamut, generatori, icone
tests/               test (i clip di esempio non sono nel repository)
packaging/           installer: pacchetto, guida PDF, disinstallatore
```

---

## Limiti noti

- Il pannello Camera Raw **vero** e la **stabilizzazione con giroscopio** di Resolve non si possono sbloccare sugli MP4:
  dipendono entrambi dal decoder interno di Resolve (Sony solo per gli MXF, giroscopio solo per le camere Blackmagic).
  S-Log MetaRaw è l'equivalente per i controlli colore, non una porta d'ingresso.
- Servono **S-Log2 o S-Log3**. Con altri profili il nodo resta neutro e lo dice.
- Alcune camere non registrano la temperatura colore: viene stimata dal preset di luce e segnalata come tale.
- **S-Log2:** la formula segue il paper Sony (grigio 18% al codice 347). La curva S-Log2 installata con Resolve
  differisce di circa 0,15 stop, quindi le due non atterrano esattamente nello stesso punto.
- Da validare con altri file: XAVC HS (HEVC), HLG e S-Cinetone, zoom motorizzati, GPS.
- **Progetto hobbistico e indipendente**, distribuito così com'è, senza garanzie e senza alcuna responsabilità per l'uso
  in contesti professionali. Il codice è aperto: chiunque può leggerlo, provarlo e modificarlo.

---

## Crediti

**Ivan Mazzone + Claude** — [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).

Scritto insieme a **Claude Opus 5** (Anthropic): la versione 1.0 è del 19 settembre 2026, la 1.0.1 del giorno dopo e la
1.1.0 del 22 settembre 2026. Il changelog è in [RELEASE_NOTES.md](RELEASE_NOTES.md).

Riferimenti per i tag Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) (Sony.pm) e
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) di AdrianEddy (MIT). Parte della tabella dei tag
deriva da quest'ultimo.

Sony, XAVC e Catalyst sono marchi di Sony Group Corporation; DaVinci Resolve è un marchio di Blackmagic Design. Progetto
indipendente, non affiliato né approvato da nessuna delle due aziende.

## Licenza

[GNU General Public License v3.0 o successiva](LICENSE). Software libero: puoi usarlo, studiarlo, modificarlo e
ridistribuirlo; chi lo ridistribuisce, anche modificato, deve farlo con la stessa licenza e con il codice sorgente
disponibile. Nessuna garanzia di alcun tipo.

L'OpenFX SDK è di The Open Effects Association (BSD a 3 clausole) e parte della tabella dei tag Sony deriva da
telemetry-parser (MIT): entrambe compatibili con la GPL-3.
