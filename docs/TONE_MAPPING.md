# Spalla, piede e colore: come sono fatti Highlights e Shadows

Ricerca alla base dello stadio `sm_tone` di `DevelopMath.h`. Le misure vengono dai
LUT installati su questa macchina; le formule di riferimento dal codice sorgente di
OpenDRT, dalla documentazione ACES 2.0 e dal sorgente di darktable. Dove non sono
riuscito a stabilire qualcosa, è scritto in fondo.

![Le curve a confronto](tone_curve.png)

---

## 1 · Cosa c'era prima, misurato

L'operatore precedente era un **gradino, non una spalla**:

```
ev_out = ev + highlights · 2 · clamp(ev/5, 0, 1)²
```

| ev in | pendenza | cosa succede |
|---|---|---|
| +1 | 0,840 | comprime |
| +3 | 0,520 | comprime |
| +4,9 | 0,216 | comprime molto |
| **+5,0** | **salta a 1,000** | **smette del tutto** |
| +8 | 1,000 | nessuna compressione, solo un offset fisso |

Tre difetti, tutti misurati:

1. **Sopra +5 stop la pendenza torna esattamente a 1.** Non è una spalla: abbassa il
   tetto di 2 stop e continua a clippare, solo più tardi.
2. **Salto di pendenza da 0,202 a 1,000 in un punto.** In un cielo i pixel che valgono
   esattamente +5 stop formano una curva di livello, e attorno a una sorgente
   luminosa quelle curve sono concentriche: **un anello**, che si legge come un alone
   pur essendo l'operatore puntuale. È il difetto che più assomiglia al problema che
   si voleva risolvere.
3. **Recupera 0,9 stop.** Porta il clip di un Rec.709 da +2,47 a +3,40 stop sopra il
   grigio. Una S-Log3 ne porta ~6: se ne buttavano via 3,5.

Inoltre il guadagno era applicato uguale a X, Y e Z, quindi la cromaticità era
conservata **esattamente**: le alte luci recuperate restavano alla saturazione di
scena (neon) e le ombre alzate si portavano dietro tutto il rumore croma.

---

## 2 · L'alone: chi lo fa davvero

Il controllo Highlights del pannello Camera Raw di Resolve è **quasi certamente
puntuale**, non spaziale. La prova documentale: il manuale afferma che le regolazioni
della palette Primaries si possono cuocere in un LUT 3D (Resolve 21.1, p. 3484 e
p. 310), e un LUT 3D è per definizione una mappa puntuale. Non c'è raggio, né soglia,
né riferimento ai pixel vicini — a differenza di Photoshop e Lightroom, che espongono
un `Radius` ed è lì che gli aloni nascono davvero.

E un operatore puntuale monotono **non può** fare un alone. Con `out = f(in)` e
`f' ≥ 0` si ha `grad out = f'(in) · grad in`: il gradiente conserva il segno pixel per
pixel, non nascono estremi locali, non c'è inversione. È una dimostrazione, non
un'opinione.

Allora da dove viene il bagliore? Il controllo non lo crea: **lo smaschera**.

1. **Velo dell'obiettivo.** Attorno a una finestra bruciata c'è una rampa luminosa
   reale, che si estende per decine di pixel. Finché la zona è clippata la rampa è
   schiacciata contro il soffitto e invisibile. Recuperi le alte luci e la rampa torna
   visibile — c'era già.
2. **Ringing del codec.** XAVC-I è DCT: ai bordi ad alto contrasto lascia un
   sovraelongamento chiaro e uno scuro (mosquito noise). Stesso smascheramento. Più il
   4:2:2, che porta la crominanza dal lato sbagliato del bordo.
3. **Camera Raw → Sharpness ha default 20, non 0** su Sony, Canon e CinemaDNG
   (manuale p. 189, p. 174). È uno sharpener spaziale che gira al debayer, **nello
   stesso pannello**. Genera over/undershoot ai bordi; poi Highlights abbassa il lato
   chiaro e rende più visibile l'undershoot scuro sul lato scuro.
4. **Mid/Detail è locale** ed è a tre campi di distanza nella stessa riga numerica.
   Blackmagic chiama il suo fratello maggiore Contrast Pop *"localized contrast
   adjustment"* con un *"Detail size"* (p. 3546). Facilissimo attribuirne l'alone a
   Highlights.

**Se il bagliore ti dà fastidio, prova in quest'ordine**: Sharpness a 0, Mid/Detail a
0, e poi guarda il bordo al 100% *prima* di qualsiasi correzione, con una riduzione di
guadagno temporanea che scopra il cielo. Se la frangia è già lì, nessun tone mapper la
toglierà: è nel file.

Cosa può fare questo stadio: **non aggiungerne**, ed essere abbastanza graduale da non
trasformare la rampa rivelata in un bordo. Il vecchio operatore faceva l'opposto.

---

## 3 · I riferimenti, misurati

Dai LUT che Resolve installa, non da manuali.

**Kodak 2383** (`Film Looks/Rec709 Kodak 2383 D65.cube`, ingresso Cineon dichiarato
nell'header) e **Blackmagic Gen 5** (`Blackmagic Gen 5 Film to Video.cube`):

| pendenza a | grigio | +1 | +2 | +3 | +4 | +6 |
|---|---|---|---|---|---|---|
| Kodak 2383 | 1,60 | 1,13 | 0,69 | 0,31 | 0,14 | 0,014 |
| BMD Gen 5 | 1,27 | 0,93 | 0,74 | 0,60 | 0,34 | 0,051 |

Il grigio 18% finisce a 45,6 IRE sulla stampa e a ~41 IRE su Gen 5. Entrambe
asintotano: Kodak verso +6,5 stop, Gen 5 verso +7.

### La desaturazione della pellicola non è un termine separato

Applicando la stessa curva neutra **per canale** ho riprodotto i numeri di
saturazione del 2383 quasi esatti:

| campione | +2 | +3 | +4 |
|---|---|---|---|
| cielo blu, pellicola | 0,710 | 0,468 | 0,257 |
| cielo blu, per canale | 0,708 | 0,480 | 0,248 |

È la conseguenza del fatto che i tre canali asintotano allo stesso soffitto: salendo
convergono, e convergere *è* desaturare. La pellicola non "desatura le alte luci",
ha tre strati che saturano insieme.

### Ma il per-canale schiaccia gli incarnati

| campione | scena | per canale a +3 stop |
|---|---|---|
| incarnato | 0,466 | **0,122** |
| fogliame (mezzitoni) | 0,667 | **0,876** (sovrasatura) |

Il per-canale lega la perdita di croma alla **distanza fra i canali**: un colore
saturo (cielo) si comporta bene, un colore chiaro e poco saturo (incarnato) perde
tutto. È letteralmente il piattone rosa. Per questo la via scelta è norma + purezza.

---

## 4 · Come è fatto

Tutto in **lineare di scena**, dopo esposizione e bilanciamento e prima dei trim di
saturazione. Essendo dopo la decodifica log, è agnostico alla curva: S-Log, S-Log2 e
S-Log3 passano tutti dallo stesso stadio.

```
norm  = power norm(R, G, B)
t     = spalla(norm) / norm            rapporto di compressione, 1 = intatto
rgb'  = rgb · t
purezza p = t ^ k(t)
rgb'' = y + (rgb' − y) · p
```

### La norma

```
norm(R,G,B) = (|R|³ + |G|³ + |B|³) / (R² + G² + B²)
```

È la *power norm* di darktable (il suo default). Proprietà che serve: `norm(x,x,x) = x`
**esattamente**, così un pixel neutro resta neutro a qualsiasi impostazione.

Perché non le alternative:

| norma | cielo blu | problema |
|---|---|---|
| luminanza Y | 0,120 | sottostima i colori saturi: sfuggono alla compressione e bruciano |
| max(RGB) | 0,300 | **cambia canale** dove uno clippa e un altro no. Una funzione puntuale di una quantità spazialmente discontinua produce frange — il manuale di darktable lo dice: *"may produce halos or fringes where channels are clipped"* |
| power norm | 0,268 | prende i saturi come max, senza discontinuità |

OpenDRT usa una scelta diversa e più elaborata (norma euclidea su RGB desaturato del
35% verso pesi sbilanciati sul blu), ma la conclusione è la stessa: **né luminanza né
max(RGB)**.

### La spalla

```
spalla(L) = L / (1 + (L·a)^n)^(1/n)        a = |Highlights|, n = 3
```

È la stessa primitiva che darktable usa in AgX (`_sigmoid(x, power)`). Proprietà:

- `f(0) = 0` e `f'(0) = 1` **esattamente**;
- tende all'asintoto `1/a` senza **mai** raggiungerlo: nessun valore di scena, per
  quanto alto, clippa;
- **C^∞ per x > 0**, e alla giunzione con un tratto lineare la continuità dipende da n:
  n=1 darebbe solo C¹, n<1 addirittura derivata seconda infinita, **n=3 dà C⁴**.
  Niente giunzione, niente curvatura che salta, niente anello concentrico;
- `a = 0` dà l'identità esatta senza bisogno di un ramo: il nodo resta neutro a zero.

Con `a = 1` ripiega +6 stop dentro +2,47, cioè dentro il bianco di un Rec.709,
spostando il grigio 18% di **0,003 stop** e un incarnato a +1 stop di 0,053.

### Il piede

```
guadagno(ev) = 2^( Shadows · 1,5 · exp(−((ev + 4)/1,8)²) )
```

Una campana liscia in log2, centrata a −4 stop dove vive il dettaglio in ombra, che
muore a entrambe le estremità:

| a | campana | guadagno |
|---|---|---|
| grigio (0 stop) | 0,007 | 1,007 (+0,011 stop) |
| −4 stop | 1,000 | 2,83 (+1,5 stop) |
| −8 stop | 0,007 | 1,007 |
| −10 stop | 0,000 | 1,000 |

Essendo un **moltiplicatore**, `f(0) = 0` a qualsiasi impostazione: il nero assoluto
resta nero. E il piede del nero, sotto −8 stop, non si muove — che è la richiesta.

L'ampiezza è vincolata: sopra 2,10 stop la curva si ripiegherebbe e le ombre
**solarizzerebbero**. 1,5 lascia margine; la pendenza minima misurata è 0,285.

### Il colore

Scalare tutti e tre i canali per lo stesso fattore **non cambia la saturazione**. Il
commento nel sorgente di darktable lo dice bene: una curva che conserva i rapporti è
*saturation-invariant*, quindi un'alta luce compressa mantiene tutto il suo colore e
viene fuori come una macchia uniforme e piena senza gradazione interna. Una curva che
conserva i rapporti **non brucia mai verso il bianco da sola**: la purezza va ridotta
esplicitamente.

```
k(t) = 0,5 · (1 + 1,0 · max(1 − t, 0)) · 2^(−ColorRecovery)
p    = t^k(t)          se t < 1, altrimenti 1
```

L'esponente **cresce dove la curva ha compresso di più** — è il meccanismo del
*Purity Limit* di OpenDRT, dove `p = 1 + 4·(1 − tonescale)·(...)`. Serve perché una
legge di potenza singola può centrare l'incarnato o l'estremo alto, non entrambi:

| | incarnato +3 | cielo +6 |
|---|---|---|
| esponente fisso 0,8 | 0,297 ✓ | 0,285 (troppo colorato) |
| **esponente crescente** | **0,305 ✓** | **0,115** |
| pellicola | 0,154 | 0,056 |

Il bersaglio concordato era ~0,30 sull'incarnato: più ricco della pellicola, che a
0,154 dà proprio il piattone. Il cursore **Color Recovery** muove l'esponente: verso
destra restituisce colore, verso sinistra va verso la pellicola.

Il cursore non può mai **aggiungere** croma che il pixel non aveva: `p ≤ 1` sempre.
È la stessa regola di darktable v7 (*"resaturation is allowed only where filmic
desaturated"*).

Verso destra toglie anche croma alle ombre aperte, proporzionalmente a quanto sono
state alzate — dove sta il rumore cromatico.

---

## 5 · Dove questo sta rispetto allo stato dell'arte

| | questo nodo | OpenDRT | ACES 2.0 | AgX |
|---|---|---|---|---|
| primitiva spalla | soft-clip n=3 | `(x/(x+s))^p` | Michaelis-Menten × toe quadratico | soft-clip, stessa famiglia |
| `f(0) = 0` | **sì, esatto** | **no**, `tn_off = 0.005` alza il nero a ~5/255 | sì | sì (clamp) |
| norma | power norm | euclidea su RGB desaturato | JMh (M) | per canale |
| purezza | `t^k(t)`, k cresce | `1 − t^p`, p cresce | compressione di M in JMh | conseguenza del per-canale |
| protezione incarnato | esponente crescente | finestra di tinta sull'arancio (`pt_lmh_r`) | nessuna — è nota per gli incarnati *"pasty pastel"* | nessuna |

Due cose che questo nodo fa **meglio** dei riferimenti: il nero è ancorato
esattamente (OpenDRT di default no), e la spalla è C⁴ alla giunzione.

Una che fa **peggio**: la protezione degli incarnati di OpenDRT è una finestra
gaussiana di tinta centrata sull'arancio, più selettiva di un esponente che dipende
solo dalla compressione. Qui non è implementata — richiederebbe un `atan2` per pixel
e una tabella di tinta — e il bersaglio di 0,30 è raggiunto lo stesso, ma su un
soggetto arancione molto saturo il comportamento sarà meno raffinato.

### Un compromesso dichiarato

Sopra +3 stop questa spalla comprime **più** di entrambi i riferimenti: fra +3 e +6
stop tiene 0,14 stop di separazione contro i 0,26 del Kodak. È il prezzo di un
ginocchio abbastanza netto da non toccare i mezzitoni (n=3 sposta il grigio di 0,003
stop; n=2 lo sposterebbe di 0,023 e l'incarnato di 0,154). La priorità era esplicita:
non incidere sui mezzitoni. Il test
`test_above_three_stops_it_compresses_harder_than_film` registra il compromesso
perché non venga scambiato per un difetto.

---

## 6 · Cosa non sono riuscito a stabilire

1. **L'algoritmo vero di Resolve.** Blackmagic non ha mai pubblicato la funzione di
   Highlights. Che sia puntuale è dedotto dall'affermazione sui LUT 3D, non da una
   dichiarazione degli sviluppatori.
2. **Nessuno l'ha mai misurato.** Ho cercato specificamente test con step wedge o bordo
   netto su Highlights di Resolve: zero risultati, ovunque. È il buco di prove più
   grosso. Il test che lo chiuderebbe: applicare solo Highlights, esportare un LUT 3D
   a 65 punti, riapplicarlo e differenziare. Se il LUT riproduce l'effetto, è puntuale
   — dimostrato, non dedotto.
3. **Se la curva di Resolve sia monotona agli estremi.** Se a −100 si ripiegasse,
   produrrebbe un bordo chiaro da sola, puntualmente. Nessuno ha pubblicato il grafico.
4. **Il razionale scritto di Jed Smith sulla scelta della norma.** Ho il codice e la
   documentazione dei parametri, non un passaggio in cui spiega perché l'euclidea su
   RGB desaturato batta una norma di luminanza.
5. **Una fonte pubblicata che dica "una giunzione solo C¹ produce contouring visibile
   in una DRT".** Non sembra esistere. La letteratura sulle bande di Mach copre il caso
   della derivata prima; il caso della derivata seconda per le curve di tono no.
6. **Una curva pubblicata per la desaturazione delle ombre.** La tecnica è reale
   (c'è letteratura brevettuale sul decadimento della crominanza per il rumore) ma
   **le DRT moderne fanno l'opposto**: ACES 2.0 e OpenDRT *aumentano* deliberatamente
   la croma nelle ombre per non avere mezzitoni slavati. Qui è su un cursore che parte
   da zero, quindi è una scelta esplicita di chi corregge, non un default.

---

## Fonti

**Misurate in locale** · `Film Looks/Rec709 Kodak 2383 D65.cube` e
`Blackmagic Design/Blackmagic Gen 5 Film to Video.cube` nella cartella LUT di Resolve ·
`/Applications/DaVinci Resolve/DaVinci Resolve Manual.pdf` (21.1, 4351 pagine)

**Codice e documentazione** ·
[OpenDRT (Jed Smith)](https://github.com/jedypod/open-display-transform/blob/main/display-transforms/opendrt/OpenDRT.dctl) ·
[parametri OpenDRT](https://github.com/jedypod/open-display-transform/blob/main/display-transforms/opendrt/docs/opendrt-parameters.md) ·
[ACES 2.0 Chroma Compression](https://docs.acescentral.com/system-components/output-transforms/technical-details/chroma-compression/) ·
[implementazione OCIO di ACES 2.0](https://github.com/AcademySoftwareFoundation/OpenColorIO/blob/main/src/OpenColorIO/ops/fixedfunction/ACES2/Transform.cpp) ·
[darktable AgX](https://github.com/darktable-org/darktable/blob/master/src/iop/agx.c) ·
[darktable filmic rgb](https://github.com/darktable-org/darktable/blob/master/src/iop/filmicrgb.c) ·
[darktable, norme di crominanza](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/filmic-rgb/) ·
[darktable tone equalizer, aloni e guided filter](https://docs.darktable.org/usermanual/development/en/module-reference/processing-modules/tone-equalizer/) ·
[Hable, curve filmiche a tratti](http://filmicworlds.com/blog/filmic-tonemapping-with-piecewise-power-curves/)

**Meccanismo degli aloni** ·
[He, Sun, Tang — Guided Image Filtering](https://pubmed.ncbi.nlm.nih.gov/23599054/) ·
[Photoshop Shadows/Highlights, il parametro Radius](https://helpx.adobe.com/photoshop/using/adjust-shadow-highlight-detail.html) ·
[veiling glare](https://en.wikipedia.org/wiki/Veiling_glare) ·
[mosquito noise](https://en.wikipedia.org/wiki/Mosquito_noise) ·
[bande di Mach](https://en.wikipedia.org/wiki/Mach_bands)
