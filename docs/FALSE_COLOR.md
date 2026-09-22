# False color: come lo fa CineMatch, come lo fa S-Log MetaRaw

Ricerca alla base dei tre toggle *False color* del nodo e dello stadio `sm_false_color`
di `DevelopMath.h`. Le affermazioni su CineMatch vengono dal **binario installato**
(`/Library/OFX/Plugins/CineMatch.ofx.bundle`) e dalle sue risorse, non dalla
documentazione: dove la documentazione conferma, è citata.

![Le tre viste](falsecolor_bands.png)

---

## 1 · CineMatch ha esattamente questa cosa, e sono quattro

Nel binario, nella tabella delle etichette:

```
Exposure False Colors          Exposure False Color Choices
White Balance False Colors     WB False Color Choices
White Balance Picker
```

e fra i simboli dei kernel GPU:

```
apply_middle_grey_false_color   apply_skin_tone_false_color
apply_temperature_false_color   apply_tint_false_color
```

più quattro LUT 64³ dedicate in `/Library/Application Support/CineMatch/Resources/ViewLUTs/`:
`ExpMidGreyFalseColor709.tin`, `ExpSkintoneFalseColor709.tin`, `WBTempHelperLUT.tin`,
`WBTintHelperLUT.tin`.

Sono **due viste di esposizione** (grigio medio, incarnato) e **due di bilanciamento**
(temperatura, tinta), messe nel gruppo `primariesgroup` **accanto agli slider che
servono a regolare** — Exposure, Temp, Tint. Esattamente l'idea da cui parte la tua
richiesta. CineMatch non ha invece zebra, indicatore di clipping, waveform, scope,
lettura IRE né riconoscimento di chart: quelle stringhe nel binario non esistono.

Il workflow che FilmConvert documenta:

> "Green is mapped to the middle grey range for REC.709."
> "This False Color view maps orange to a common exposure for skin tones in REC.709."
> "All warm elements are mapped to orange and all cool elements are mapped to blue."
> "Identify a part of your image that you would like to be neutral and move the
> temperature slider until that area is grey."

— [CineMatch Resolve Workflow Guide](https://www.filmconvert.com/blog/cinematch-resolve-workflow-guide/)

### Le soglie esatte dei suoi kernel

**Grigio medio** — un colore solo, RGB(157, 216, 0), su `|log2(Y/0.18)| < 0.40` stop,
con rampa lineare da 1.0 sul grigio a 0.0 a ±0.40. Fuori dalla banda l'immagine resta
monocromatica.

**Incarnato** — un colore solo, RGB(250, 124, 8), da 0 a +2 stop sopra il grigio, con
spline vincolata: plateau pieno fra +0.5 e +1.5 stop.

**Temperatura e tinta** — e qui sta la differenza che conta:

```c
float4 hsl = rgb_to_hsl(clamp(v, 0.0f, 1.0f));
float normalized_hue = hsl.x > 0.9f ? hsl.x - 1.0f : hsl.x;
...
if (in warm band) hsl.x = 0.08f; else hsl.x = 0.586f;
v = hsl_to_rgb(hsl);
v = saturate(v, remap(hsl.y, 0.0f, 1.0f, 8.0f, 1.0f));
```

| Vista | Banda | Tinta HSL | Gradi | Forzata a |
|---|---|---|---|---|
| Temperatura | caldo | −0.025 … 0.160 | −9° … 58° | 29° (arancio) |
| Temperatura | freddo | 0.50 … 0.75 | 180° … 270° | 211° (blu) |
| Tinta | verde | 0.20 … 0.45 | 72° … 162° | 108° (verde) |
| Tinta | magenta | 0.80 … 0.95 | 288° … 342° | 306° (magenta) |

**CineMatch non calcola una temperatura di colore.** Desatura il fotogramma, classifica
ogni pixel **per tinta HSL**, forza le tinte in banda a un valore canonico e alza la
saturazione fino a **8×** sui pixel quasi neutri (`remap(hsl.y, 0,1, 8,1)`: più il pixel
è neutro, più viene esaltato). I neutri cadono fra le due bande e restano grigi — ed è
questo che fa funzionare il "regola finché non diventa grigio".

È una **mappa di classificazione per tinta**, non una mappa colorimetrica. Funziona ed è
robusta, ma non può dirti *di quanto* sei fuori.

---

## 2 · Il riferimento: ARRI ALEXA

La convenzione canonica, dall'ARRI ALEXA Pocket Manual:

| Colore | Livello segnale | Significato |
|---|---|---|
| Rosso | 99–100% | clipping del bianco |
| Giallo | 97–99% | appena sotto il clipping |
| Rosa | 52–56% | **una fermata sopra il grigio medio** (incarnato caucasico) |
| Verde | 38–42% | grigio neutro 18% |
| Blu | 2,5–4,0% | appena sopra il clipping del nero |
| Viola | 0–2,5% | clipping del nero |

Il resto resta monocromatico: solo ~14 IRE su 100 sono colorati. È una scelta di
progetto, non una limitazione — bande strette su àncore che contano, e l'immagine
ancora leggibile intorno. Leeming LUT Pro dichiara gli stessi bersagli in altra forma:
grigio 18% a 42 IRE, incarnato fra 70 e 75 IRE.

Nota: il rosa di ARRI significa letteralmente "una fermata sopra il grigio medio", non
"incarnato" in senso stretto.

---

## 3 · Perché l'icona non può stare a sinistra dello slider

Verificato sull'SDK che Resolve distribuisce
(`/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/OpenFX/`):

- **`kOfxParamPropLayoutHint` non esiste.** Né `NoNewLine`, né `setLayoutHint`, né
  `kOfxParamPropLayoutPadWidth`. Cercando `Layout` in tutto l'SDK si trovano due sole
  occorrenze, entrambe in un rimando di documentazione senza rapporto.
  Il motivo: quella proprietà **non fa parte di OpenFX**, è un'estensione Foundry/Nuke
  dichiarata in `fnPublicOfxExtensions.h`, che Resolve non distribuisce.
- Resolve dichiara `pageRowCount=0` e `pageColumnCount=0`: non implementa nemmeno il
  meccanismo di layout a griglia previsto da OpenFX. Impagina i parametri come una pila
  verticale di righe etichettate.
- `supportsCustomInteract=0`: un plugin non può disegnarsi un widget nel pannello.

Quindi **ogni parametro occupa una riga intera, e non c'è modo di affiancarne due.**
Non è una scelta: è il limite dell'host.

Cosa invece esiste: `kOfxPropIcon` e il metodo `ParamDescriptor::setIcon(nome, pngFormat)`,
sulla classe base di *tutti* i tipi di parametro. La documentazione OpenFX è però
permissiva — *"Some applications are able to display icons instead of text"* — e **non è
documentato da nessuna parte se Resolve le disegni davvero**. Indizio contrario: CineMatch,
plugin commerciale con un pannello complesso, spedisce **una sola** immagine (la miniatura
160×90 dell'effetto) e nessuna icona, e chiama i suoi pulsanti a parole, incluso
`Reset On Screen Control` — proprio il tipo di comando che sarebbe stato un'icona se si
fosse potuto.

**Cosa fa S-Log MetaRaw**: chiama `setIcon` con le tre icone (sono nel bundle, in
`Contents/Resources/`), e mette ogni toggle **immediatamente sopra lo slider che serve**.
Se Resolve disegna l'icona, si vede l'icona; se la ignora, resta l'etichetta, che dice la
stessa cosa. È esattamente la struttura di CineMatch — booleana + menu sopra lo slider —
arrivata per la stessa strada.

---

## 4 · Cosa fa S-Log MetaRaw, e in cosa differisce

Tre viste, una per controllo, mutuamente esclusive.

### Esposizione

Bande in **fermate attorno al grigio 18%**, secondo la struttura ARRI:

| Colore | Fermate | Significato |
|---|---|---|
| Rosso | ≥ +5,5 | clip |
| Giallo | +4,0 … +5,5 | vicino al clip |
| Rosa | +0,70 … +1,30 | una fermata sopra il grigio (incarnato) |
| Verde | −0,33 … +0,33 | grigio 18% |
| Blu | −6,0 … −4,0 | ombra profonda |
| Viola | ≤ −6,0 | clip del nero |
| Grigi | il resto | l'immagine resta leggibile |

Le fermate sono misurate sulla **luminanza lineare**, non sul segnale codificato: sono
quindi indipendenti dalla curva log della clip, e la lettura non cambia passando da
S-Log2 a S-Log3 o da una timeline all'altra.

### Temperatura e tinta — la differenza sostanziale

Qui non si classifica per tinta: si **misura**. Per ogni pixel si calcola la distanza dal
bianco dello spazio di lavoro in **CIE 1960 uv**, la stessa coordinata su cui il nodo
costruisce già il bilanciamento del bianco, e la si proietta attraverso **l'inverso della
risposta reale dei due slider**, misurata in `buildParams` al valore corrente:

```
neutralUV(k, t, k,       t)      dove sta il neutro adesso
neutralUV(k, t, k + 100, t)      dove va con +100 K di slider
neutralUV(k, t, k,   t + 5)      dove va con +5 di tint
```

Invertita quella matrice 2×2, il numero dietro a una banda **è in Kelvin e in unità di
tint**: dice di quanto muovere lo slider, non "c'è una dominante". Verificato in
`tests/test_falsecolor.py`: un errore di 100 K su 5600 K si legge 100,5 K; un errore di
20 di tint si legge 20,04.

Ricavare la derivata al valore corrente dello slider, invece che da una tangente teorica
al locus planckiano, è quello che toglie la diafonia fra i due assi: un errore di sola
tinta di ±20 unità sbava di ±5 K invece che di ±170 K, e la lettura resta buona anche a
3200 K, dove la scala Kelvin è quasi quattro volte più fitta che a 6500 K.

| Vista | Banda centrale | Poi | Poi | Oltre |
|---|---|---|---|---|
| Temperatura | ±75 K → bianco | ±200 K | ±500 K | blu / rosso pieno |
| Tinta | ±2 → bianco | ±5 | ±12 | verde / magenta pieno |

**Bianco = neutro.** Il colore di una banda è la dominante che c'è davvero: scaldi quello
che legge blu, togli verde a quello che legge verde. I pixel troppo scuri per portare una
tinta affidabile (sotto −4 stop) sono marcati grigio scuro, i clippati rosso — marcati,
non indovinati, perché lì la crominanza non significa niente.

### Dove sta nella pipeline

Le tre viste sono prese **subito dopo esposizione e bilanciamento, prima dei trim di tono
e saturazione**. Non è un dettaglio: un trim di saturazione scalerebbe la deviazione
cromatica e farebbe **mentire** la lettura in Kelvin, un trim di contrasto sposterebbe le
fermate. Così rispondono solo ai tre controlli a cui appartengono.

La banda viene poi riportata in lineare Rec.709, convertita nel gamut in cui il nodo sta
scrivendo e ricodificata lì, così esce dello stesso colore qualunque cosa faccia la
timeline — DaVinci WG/Intermediate, ACEScct, Rec.709. Verificato in `tests/test_falsecolor.py`.

### Confronto

| | CineMatch | S-Log MetaRaw |
|---|---|---|
| Viste esposizione | 2 (grigio medio, incarnato), un colore ciascuna | 1, sei bande ARRI insieme |
| Viste bilanciamento | 2, classificazione per tinta HSL | 2, deviazione colorimetrica in uv |
| Lettura | qualitativa: "c'è dominante / non c'è" | quantitativa: Kelvin e unità di tint |
| Su contenuto saturo | la satura 1×, i neutri 8×: il neutro spicca | tutto va in banda per magnitudine |
| Neutro appare | grigio (assenza di colore) | bianco (banda centrale) |
| Dove sta | sopra gli slider, booleana + menu | sopra gli slider, tre booleane con icona |

Il punto forte di CineMatch è la robustezza su scene sature: esaltando i quasi-neutri di
8× e lasciando stare i colori, il grigio salta all'occhio. Il punto forte di questa
implementazione è che dice **di quanto** sei fuori. Non ho trovato nessuno strumento, in
tutta la ricerca, che faccia una mappa colorimetrica CCT/Duv per pixel: la cosa più vicina
sono i DCTL MONONODES (*Highlight Neutrals*, *Balance*), che restano classificatori di
tinta. Sembra terreno non occupato.

---

## 5 · Come si usano

1. Metti il nodo per primo, *Decode Using* su **Clip** (le viste servono a regolare i tre
   controlli: in *Camera metadata* quei controlli sono bloccati e il nodo è trasparente).
2. **Esposizione**: accendi la vista, punta il grigio medio o l'incarnato, muovi
   *Exposure* finché la zona giusta diventa verde (grigio 18%) o rosa (una fermata sopra).
3. **Temperatura**: accendi la vista, trova una superficie che deve essere neutra, muovi
   *Color Temp* finché diventa bianca.
4. **Tinta**: idem con *Tint*. Un paio di passate alternate e converge.
5. Spegni la vista prima di renderizzare.

**Attenzione**: la vista sostituisce l'immagine, non è un overlay — in Resolve un plugin
OpenFX non ha modo di disegnare sopra il viewer nel pannello (gli overlay interact
esistono ma vanno accesi a mano dal menu del viewer e servono a widget trascinabili).
Quindi se la lasci accesa, **renderizzi il false color**. Il campo *Avanzate › Rilevato*
lo scrive a chiare lettere quando una vista è attiva.

---

## 6 · Cosa non è stato possibile stabilire

1. **Se Resolve disegni davvero `kOfxPropIcon` sui parametri.** Nessuna documentazione,
   nessun post, nessun sorgente in un senso o nell'altro; il catalogo di stranezze OFX di
   Resolve tenuto da Natron non ne parla. Si vede aprendo il pannello.
2. **Le etichette del menu esposizione di CineMatch**: non esistono come stringhe nel
   binario (sono inlined), la documentazione le chiama "Middle Grey" e "Skintones".
3. **I nomi interni dei parametri non-gruppo di CineMatch**: ottimizzati come stringhe
   corte e inlined nelle istruzioni; servirebbe disassemblare.
4. **I valori RGB delle bande ARRI**: il PDF ufficiale è una scansione raster senza testo.
   Gli intervalli in percentuale sono confermati, i colori esatti no.
5. **I valori per banda dei preset False Color di ResolveFX**: il manuale documenta i
   controlli, non i numeri.

---

## Fonti

[CineMatch Resolve Workflow Guide](https://www.filmconvert.com/blog/cinematch-resolve-workflow-guide/) ·
[CineMatch Premiere Workflow Guide](https://www.filmconvert.com/blog/cinematch-workflow-guide/) ·
[ARRI ALEXA Pocket Manual, False Color Exposure Check](https://www.manualslib.com/manual/1152031/Arri-Alexa.html?page=37) ·
[ARRI LogC False Color Exposure Zones and Key](https://www.arri.com/resource/blob/390448/2d469ae1e98110562fe347cea50a284b/arri-logc-false-color-specification-data.pdf) ·
[SmallHD Exposure Assist](https://guide.smallhd.com/m/all_monitors/l/808517-exposure-assist-false-color) ·
[Leeming LUT Pro](https://www.leeminglutpro.com/) ·
[MONONODES Utility DCTL](https://mononodes.com/utility-dctl/) ·
[lut_builder](https://github.com/Today20092/lut_builder) ·
[Natron, README-hosts.txt (stranezze OFX di Resolve)](https://github.com/NatronGitHub/openfx-misc/blob/master/README-hosts.txt) ·
[Foundry fnPublicOfxExtensions.h](https://github.com/NatronGitHub/openfx/blob/master/include/nuke/fnPublicOfxExtensions.h) ·
[OpenFX 1.5: Effect Parameters](https://openfx.readthedocs.io/en/main/Reference/ofxParameter.html) ·
SDK OpenFX distribuito con DaVinci Resolve (`ofxCore.h`, `ofxsParam.h`) ·
binario e risorse di CineMatch 1.35 installato
