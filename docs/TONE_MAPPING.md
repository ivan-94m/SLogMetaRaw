# Toni: esposizione per zone, in stop

Come funzionano i controlli **Toni** e **Zone** del nodo S-Log MetaRaw dalla versione 2.0, e
perché sono fatti così. Il recupero locale, che conserva la texture, sta nel nodo separato
**S-Log MetaRaw Detail**: vedi [DETAIL.md](DETAIL.md).

![Le curve a confronto](tone_curve.png)

*Dall'alto: nessun tono; Highlights −100 (la spalla: il massimo registrato arriva sul Bianco);
Highlights −100 con Soft Clip; Shadows +100 con Blacks −67; Contrast +50; stampa Kodak 2383;
incarnato e cielo che salgono di 5 e 6 stop con Highlights −100. Tutte le strisce sono calcolate
dal modello di riferimento del plugin (`tests/model/tone.py`).*

---

## 1 · L'idea

Esposizione e bilanciamento del nodo sono **guadagni in luce lineare di scena**. I Toni ne
sono l'estensione naturale: **un'esposizione per zona, misurata in stop dal grigio 18%**, più
una **spalla filmica** per le alte luci (Highlights).

- Dentro una zona la pendenza è 1: la zona si sposta tutta insieme, come con un'esposizione,
  e la texture resta intatta.
- La compressione avviene solo nella **banda di transizione** fra una zona e l'altra, di
  larghezza dichiarata.
- Ogni pixel riceve **un solo guadagno scalare**, calcolato da una norma dei suoi tre canali:
  la cromaticità non cambia, il nero assoluto resta nero, il guadagno commuta con qualsiasi
  cambio di gamut.
- La curva in stop è una **composizione in ordine fisso** di mappe monotone, con pendenza fra
  0,35 e 2 (fino a 2,86 nelle Zone). **Nessuna combinazione di cursori può solarizzare**, e
  spostando un cursore nella stessa direzione nessun tono torna indietro.
- Niente adattamento all'immagine: niente istogrammi né "auto". Darebbero flicker e non
  avrebbero senso quando Resolve cuoce il nodo in un LUT.

È l'approccio di Baselight Base Grade e della palette HDR di Resolve, con i nomi dei cursori
di Camera Raw.

### Il limite di un operatore puntuale, detto chiaramente

In un operatore puntuale vale `∇ℓ_out = T′(ℓ) · ∇ℓ_in`: dove la curva comprime con pendenza
0,35, **anche la texture scende a 0,35**. Per questo Highlights e Shadows di Lightroom, che
sono locali, non si possono riprodurre qui. Questo nodo resta puntuale di proposito:
**Generate LUT lo può esportare** e non può creare aloni. Il recupero che conserva la
texture lo fa il nodo Detail, messo subito dopo.

Il costo fisico, da tenere presente: alzare le ombre di 1,5 stop in modo puntuale richiede una
transizione di circa 3 stop.

---

## 2 · Il pannello

### Toni (aperto)

| Cursore | Cosa fa | Scala |
|---|---|---|
| **Contrast** | `e + 4c · tanh((e − Pivot)/4)`, con `c = 2^(v/100) − 1`: pendenza ×2 al Pivot a +100, ×½ a −100, estremi limitati | −100…+100 |
| **Highlights** | in negativo una spalla: la pendenza cala in modo continuo verso l'alto e a −100 il massimo registrato arriva sul Bianco; in positivo un'espansione con pendenza ≤ 1,5 | vedi §2b |
| **Bianco (stop)** | dove Highlights −100 porta il massimo registrato, e il tetto di Soft Clip | 2,5 |
| **Shadows** | esposizione dei toni sotto −1 stop; alza anche il nero, che si tiene con Blacks | 100 = 2 stop |
| **Whites** | esposizione dei toni da +3,5 stop al clip, transizione di 1 stop | 100 = 1 stop |
| **Blacks** | velo in luce lineare 5 stop sotto il grigio: −100 = nero giù di 3 stop, +100 = su di 1; grigio fermo | −100…+100 |
| **Vibrance** | saturazione pesata sui colori meno saturi, con gli incarnati protetti (finestra di tinta a 33°) | −100…+100 |
| **Saturation** | saturazione a luminanza invariata, uguale in ogni spazio colore del nodo | −100…+100 |
| **Azzera toni** | riporta a zero i sette cursori; esposizione e bilanciamento non cambiano | — |

Oltre metà corsa Shadows e Whites raggiungono la pendenza minima (0,35): da lì **la banda si
allunga verso l'esterno** invece di schiacciarsi di più.

### 2b · Highlights: la spalla

Fino alla 2.0 di prova Highlights era una zona come le altre: spostava di 2 stop tutto quello che
stava sopra +2 stop, con pendenza 1. Il massimo registrato scendeva da +6 a +4 stop, ancora sopra
il bianco di un Rec.709 (+2,47): le luci più forti restavano bruciate e quelle sotto diventavano
lastre grigie, con tutto il loro contrasto. Non è così che la pellicola, ACES 2.0 o AgX guadagnano
gamma dinamica.

Ora è una spalla. Con `u = t − 0` (t dopo il Contrast, 0 = grigio) e `ψ` il raccordo C² di
larghezza 2 stop delle zone:

```
D(u) = [sp(1,4 (ψ(u) − 0,9)) − sp(−1,26)] / 1,4        sp(y) = log2(1 + 2^y)
T(t) = t + E · D(u)
```

- `D′` sale da 0 a 1 senza mai tornare indietro: in negativo la pendenza di `T` cala in modo
  continuo da 1 verso il basso, e non risale mai. Grigio e toni sotto non si muovono.
- **Atterraggio.** A −100 il massimo che la camera registra, `6 + log2(EI scelto / EI di ripresa)`
  stop sopra il grigio (il clip del sensore misurato su FX30, FX6, a7S III, a6300: +6,06…+6,17),
  arriva esattamente sul **Bianco**. Il nodo risolve `E` in doppia precisione: niente velo grigio,
  niente clip.
- **Almeno 1,5 stop.** Se il Bianco è più alto del massimo meno 1,5 stop (un Bianco da DRT a 5–7, o
  un EI abbassato), −100 porta comunque il massimo 1,5 stop più giù: Highlights non si spegne mai.
- **Con Soft Clip acceso** la spalla lascia spazio al tetto: il massimo finisce un decimo di stop
  sotto il Bianco invece di un terzo.
- **Pendenza minima 0,06**, come ACES 2.0 e AgX a +6 stop. Se il Bianco è troppo basso per far
  entrare tutto (Bianco sotto circa 2,3 senza Contrast, EI raddoppiato, Contrast oltre +20),
  il massimo si ferma pochi centesimi di stop sopra.
- **Il cursore** è addolcito, `a(1,5 − 0,5a)`. Scena che arriva sul Bianco:

| Highlights | −10 | −25 | −50 | −75 | −100 |
|---|---|---|---|---|---|
| valore di scena che arriva sul bianco | +2,59 | +2,81 | +3,28 | +4,08 | +6,0 |

- **La pelle** a +1 stop si sposta di 0,008 / 0,035 / 0,055 stop a −10 / −50 / −100.
- **In positivo**: `E = +0,5a`, pendenza fino a 1,5: più stacco, mai solarizzazione.
- **Colore.** Dove la spalla comprime, i colori vanno verso il bianco: croma `× 2^(0,12 · d)`
  (d = quanto la spalla ha abbassato, in stop), **in Oklab, a tinta e chiarezza costanti**: una
  linea retta in luce lineare piegherebbe l'arancio verso il salmone e il blu verso il lavanda. In
  più, i canali del gamut di uscita (Rec.709 se il nodo non converte) restano sotto il punto dove
  il massimo arriva davvero. Le luci al neon restano neon, con il nucleo che schiarisce.
- **LED e neon oltre il locus.** S-Gamut3.Cine arriva oltre i colori reali, dove Oklab non vale (i
  suoi coni diventano negativi): lì il percorso sfuma nella linea retta verso la norma, che non può
  dare canali negativi, e in ogni caso non esce dal gamut che il nodo scrive.
- **Con un DRT** (ACES, AgX, DaVinci) dopo il nodo, il DRT comprime a sua volta: alza il Bianco a
  4–5, o le alte luci vengono compresse due volte e diventano grigie.
- **Il costo**: è puntuale, quindi la texture dentro le alte luci si ammorbidisce come in
  pellicola (a −100 un dettaglio a +4 stop tiene circa un sesto del suo contrasto). La texture la
  tiene Local Highlights, nel nodo Detail.
- Whites, le Zone e Soft Clip vengono **dopo** la spalla, con i bordi riportati attraverso di essa:
  Whites sposta ancora il massimo, ma a −100 ha poco spazio (−0,21 / +0,32 stop).

### Zone (chiuso)

Quattro zone come nella palette HDR di Resolve, ciascuna con **Exp** (stop), **Sat**, **Range**
(bordo in stop dal grigio) e **Falloff** (larghezza della transizione in stop):

| Zona | Agisce | Range | Falloff |
|---|---|---|---|
| Black | sotto il bordo | −4 | 1 |
| Shadow | sotto il bordo | +1 | 2 |
| Light | sopra il bordo | −1 | 2 |
| Specular | sopra il bordo | +4 | 1 |

- **Contrast Pivot**: il tono attorno a cui ruota Contrast.
- **False color: zone**: colora ogni pixel con la zona che lo muove, misurata sulla stessa
  grandezza che le zone leggono (la norma dopo Blacks). Dove due zone si sovrappongono le tinte
  si mescolano.
- **Soft Clip** e **Color**: ripiega le alte luci verso un tetto, al livello del **Bianco** (nei
  Toni), che non raggiungono mai. È *contenimento*, non recupero; con Highlights −100 il massimo
  si ferma circa un terzo di stop sotto il Bianco.
  Con Color a sinistra le luci ripiegate vanno verso il bianco come la pellicola; a destra
  tengono il loro colore.
- **Azzera zone**.

I bordi di Shadows, Whites e delle Zone sono **riportati attraverso il Contrast e la spalla di
Highlights**: restano in stop di scena qualunque sia il Contrast o Highlights.

---

## 3 · Come è fatto (in breve)

Tutto in luce lineare di scena, dopo Exposure e White Balance:

1. **Norma** `N = Σ|c|³ / Σc²` in Rec.2020 fisso (la *power norm* di darktable): `N(x,x,x) = x`,
   liscia, senza scambi di canale.
2. **Blacks**: velo lineare a scala fissa, con la rinormalizzazione che tiene fermo il grigio.
3. `e = log2(N/0,18)` con un pavimento morbido a −16 stop.
4. **Contrast**, poi la **spalla di Highlights**, poi i **7 slot di zona** in ordine fisso:
   Specular, Whites, Light verso l'alto (uno slot resta libero); Black, Shadows, Shadow verso il
   basso. Ogni slot usa la legge ρ/ψ: raccordo C² di larghezza fissa più un limitatore di
   pendenza.
5. **Soft Clip**.
6. Un solo guadagno `x′ = x · G`.
7. **Verso il bianco**, solo dove la spalla comprime (vedi §2b).
8. **Colore** attorno a `Y·D65` nel gamut d'uscita (Rec.2020 se il nodo non converte):
   Saturation, Vibrance, Sat di zona, un limite morbido che impedisce canali negativi e, con
   Soft Clip, la purezza e il limite dei canali sotto il tetto.

Il modello di riferimento è `tests/model/tone.py`; il C++ e il Metal lo seguono entro 2e-4
(test di parità su pannelli casuali, anche con Rosetta per la slice x86_64).

---

## 4 · Ricette

- **Cielo o finestre che bruciano**: Highlights −50…−100 (con un DRT dopo, Bianco a 4–5). Per
  la texture delle nuvole: Local Highlights nel nodo Detail.
- **Controluce con viso in ombra**: Shadows +30…+60 e Blacks −20…−40 per tenere il nero.
- **Look più "pellicola"**: Contrast +20…+30, Highlights −60.
- **Sat delle ombre rumorose**: Zone › Shadow Sat −30…−50.
- **Recupero dei riflessi speculari**: Zone › Specular Exp −1…−2.

---

## 5 · LUT

Il nodo è puntuale, quindi Generate LUT lo include. Nei nodi del reticolo l'errore resta sotto
3e-4; fra un nodo e l'altro conta l'interpolazione. **Con 65 punti** i cursori Camera Raw a ±100
restano entro circa 3,5 code value S-Log3. Con 33 punti, nel piede lineare di S-Log3 (Shadows
+100) si arriva a circa 10 CV, e alcune Zone estreme (Black o Shadow +3) superano anche a 65
punti: per quei grade conviene esportare a 65 punti o lasciare il nodo attivo.

---

## Fonti

Baselight Base Grade (FilmLight, Lowepost) · palette HDR e pannello Camera Raw del manuale di
DaVinci Resolve 21.1 · darktable (power norm, tone equalizer, filmic rgb, sigmoid) · OpenDRT
(purity limit, tonescale) · ACES 2.0 (tonescale di Michaelis–Menten, `Lib.Academy.Tonescale.ctl`) ·
AgX (Sobotka; forma minima di Wrensch) · la stampa Kodak 2383 misurata dal LUT di Resolve · Paris,
Hasinoff, Kautz, *Local Laplacian Filters* (2011) e il Lightroom Journal di Adobe (2012) sul perché
Highlights e Shadows di Lightroom sono locali.
