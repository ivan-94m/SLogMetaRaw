<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadata delle camere Sony e controlli di sviluppo in luce di scena per DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <b>Italiano</b> · <a href="README.es.md">Español</a> · <a href="README.pt.md">Português</a> · <a href="README.zh.md">简体中文</a>
</p>

---

## Cos'è

Le camere Sony scrivono in ogni file come è stata girata l'inquadratura: bilanciamento in Kelvin, tinta, EI, obiettivo,
diaframma, shutter, profilo colore. Resolve usa questi dati sugli MXF di FX6 e FX9, che hanno il pannello *Camera Raw*.
Sugli MP4 di FX30, FX3, serie a7 o a6000 li ignora.

S-Log MetaRaw legge questi dati e li usa. È fatto di tre parti:

| | Dove | Cosa fa |
|---|---|---|
| **Script** | Workspace › Scripts › S-Log MetaRaw | legge i metadata di tutte le clip del progetto e li scrive nel Media Pool |
| Nodo **S-Log MetaRaw** | Color › OpenFX | sviluppa una clip partendo dai valori di ripresa: bilanciamento, esposizione, spazio colore, toni per zone, false color |
| Nodo **S-Log MetaRaw Detail** | Color › OpenFX | il nodo creativo: recupero locale dei toni, Texture, Clarity, Dehaze |

Nessun file viene transcodificato, nessun originale viene mai scritto.

### Cosa aspettarsi, onestamente

**Non è raw.** Un MP4 log è già demosaicizzato e compresso, a 8 o 10 bit, spesso 4:2:0, con la riduzione rumore della
camera già applicata. Nessun plugin può restituire quello che la camera ha buttato via.

Il nodo applica la scienza colore con rigore. Esposizione e bilanciamento lavorano in luce lineare, partono dai valori
che la camera ha registrato e seguono curve e gamut pubblicati. I toni spostano l'immagine in stop. Lavorata così,
un'immagine log **ha un comportamento che ricorda un file RAW**: il bilanciamento si sposta pulito, l'esposizione si
muove come uno stop di luce, le alte luci si arrotondano invece di rompersi.

Nel lavoro intenso, però, la sola scienza colore non basta. Appena si forzano i limiti della camera, l'assenza di
informazioni nell'immagine si fa sentire: banding nei cieli, rumore nelle ombre alzate, alte luci bruciate che restano
bruciate, colore che si sfalda nei canali compressi. Esponi bene in ripresa. S-Log MetaRaw ti aiuta a tirare fuori il
meglio da quello che c'è. Non può creare quello che non c'è.

---

## Installazione

1. Scarica `SLogMetaRaw-2.1.0.dmg` da **Releases** e aprilo.
2. Doppio clic su **Installa S-Log MetaRaw.pkg**. Non è firmato con un certificato Apple: la prima volta usa tasto
   destro › **Apri**. Chiede la password del Mac perché il plugin va in una cartella di sistema.
3. Riavvia DaVinci Resolve.

L'installer cancella anche la cache dei plugin di Resolve (`OFXPluginCacheV2.xml`), che Resolve ricostruisce al
prossimo avvio. Senza, Resolve mostrerebbe ancora il pannello vecchio e non vedrebbe il nodo Detail.

| Installato | Percorso |
|---|---|
| I due nodi (un solo bundle) | `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` |
| La libreria Python | `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` |
| Lo script del menu | `…/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` |

Mentre lavora tiene un piccolo record JSON per clip in `~/Library/Application Support/SLogMetaRaw/cache`. Nel disco ci
sono anche le guide di tre pagine, in italiano e in inglese.

**Installazione pulita e disinstallazione.** Ogni installazione parte pulita: l'installer sostituisce per intero il
plugin e la libreria precedenti e toglie le installazioni di sviluppo, così non resta nessun file di una versione
vecchia. **Disinstalla S-Log MetaRaw.command**, nel disco (la prima volta: tasto destro › Apri), rimuove tutte le
versioni installate, 1.x e 2.x comprese, con cache, impostazioni e log. Prima di toccare qualcosa elenca tutto, ti chiede
di chiudere Resolve e ti chiede se cancellare anche i CSV esportati. I metadata già scritti nei progetti di Resolve fanno
parte dei progetti e restano.

**Requisiti:** macOS 12 o successivo, Apple silicon o Intel, e DaVinci Resolve 21. **Testato solo su Resolve Studio 21.1
su macOS.**

**Clip:** Sony XAVC in `.MP4` o `.MXF`. Lo script le legge tutte. I nodi sviluppano **S-Log3** (S-Gamut3.Cine o
S-Gamut3), **S-Log2** e **S-Log** (S-Gamut). Con altri profili restano neutri e lo dicono.

---

## In breve

1. Importa il girato. **Workspace › Scripts › S-Log MetaRaw**: premi **1 · Leggi metadata**, poi **2 · Scrivi in Resolve**.
2. Nella pagina Color metti **S-Log MetaRaw** come **primo nodo**. Prende EI, Kelvin e tinta della clip. A quei valori non
   cambia niente.
3. Correggi bilanciamento ed esposizione nel nodo. Le viste false color aiutano.
4. Modella i toni con **Toni**. Per recupero locale, Texture, Clarity o Dehaze aggiungi **S-Log MetaRaw Detail** come
   nodo successivo.
5. Poi il tuo CST, LUT o DRT.

```
S-Log MetaRaw  →  S-Log MetaRaw Detail  →  CST / LUT / DRT  →  resto del grade
```

---

## Lo script

La finestra ha una riga di pulsanti, una di opzioni e l'elenco delle clip, e segue la lingua di Resolve (italiano,
inglese, spagnolo, portoghese, cinese semplificato).

- Un menu sceglie le clip: *Tutto il Media Pool* o *Clip selezionate nel Media Pool*.
- **1 · Leggi metadata**: una riga per clip con camera, obiettivo, diaframma, shutter, EI, WB, spazio colore e data
  level. La colonna *Stato* dice `letto`, cosa è cambiato durante la ripresa (diaframma, fuoco…) o perché una clip è stata
  saltata. Clicca una riga per vedere tutto quello che è stato letto, diviso come in Catalyst Browse.
- **2 · Scrivi in Resolve**: riempie i campi del Media Pool (pannello Metadata, colonne, keyword per le smart bin, data
  burn) e corregge i valori che Resolve legge male dagli MXF, come *Camera Aperture* `F53343` sulla FX6.
- **Esporta CSV**: esporta i valori per cui Resolve non ha un campo (EI, tinta, modo WB, distanza di fuoco, gamma di
  ripresa…) nel formato CSV dei metadata di Resolve.
- Opzioni:
  - **Tag per camera** (spento): aggiunge camera, gamma e primarie alle keyword.
  - **Sovrascrivi metadata** (acceso): sostituisce i valori già scritti da Resolve; spento, riempie solo i campi vuoti.
  - **Correggi il Data Level** (acceso): imposta il *Data Level* di ogni clip su Full o Video, quello che serve alla
    sua gamma. Il perché è in [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md).
  - **Imposta anche Input Color Space** (spento): per i progetti color managed.
    Uno script non può riportarlo su *Project*: solo tu, a mano.
- La versione in basso a destra, cliccata, controlla GitHub.

La lettura è veloce perché non decodifica niente: al massimo 24 campioni della traccia metadata per clip, con un tempo
massimo di un secondo. Un volume che smette di rispondere viene saltato una volta sola, con un avviso, invece di bloccare
l'elenco.

---

## Il nodo S-Log MetaRaw

Il nodo è puntuale: ogni pixel dipende solo da sé stesso. Non crea mai aloni e **Generate LUT** lo può esportare
(consigliati 65 punti).

| Controllo | Cosa fa |
|---|---|
| **Versione** (in cima) | `v2.1.0`. Una volta al giorno chiede a GitHub l'ultima release. Se ce n'è una diventa **🟢 v2.1.0 → 2.x.y** e il clic apre il download del DMG nel browser. Non installa mai niente da solo |
| **Camera** · **Rileggi metadata** | la camera letta. *Rileggi* rilegge la clip, riporta ogni controllo ai valori di camera e scrive i metadata della clip nel Media Pool |
| **Decode Using** | *Clip* permette di cambiare i controlli; *Camera metadata* li blocca sui valori di ripresa |
| **White Balance** · **Color Temp** · **Tint** | As shot o preset. Adattamento cromatico Bradford in luce lineare, dal bianco registrato dalla camera |
| **Exposure** | indice di esposizione: EI doppio = +1 stop |
| **False color** | temperatura, tinta ed esposizione; vedi sotto |
| **Color Space** · **Gamma** | uscita, come un Color Space Transform; *Timeline* non converte |
| **Toni** | Contrast, Highlights, Shadows, Whites, **Bianco** (stop), Blacks, Vibrance, Saturation (−100…+100) |
| **Zone** (chiuso) | zone Black, Shadow, Light e Specular con Exp (stop), Sat, Range e Falloff; Contrast Pivot; Soft Clip; false color *Zone* |
| **Avanzate** | ingresso del nodo, correzione del data level, stato, **Sblocca controlli senza metadata** |
| **Dati di ripresa** | sola lettura: obiettivo, focale, diaframma, fuoco, shutter, EI, WB, fps, ND, LUT di camera |

**Highlights è una spalla filmica.** In negativo comprime le alte luci con una pendenza che cala in modo continuo verso
l'alto, come la pellicola, ACES 2.0 e AgX. A −100 il massimo che la camera ha registrato (circa +6 stop sopra il grigio in
S-Log3) arriva esattamente sul **Bianco**: niente velo grigio, niente clip. Grigio e toni sotto restano fermi, la pelle a +1
stop si sposta al massimo di 0,05 stop. Le luci più compresse vanno dolcemente verso il bianco senza cambiare tinta. In
positivo dà più stacco alle alte luci, con una pendenza limitata. **Bianco** è dove arriva quel massimo (e il tetto di Soft
Clip): 2,5 stop è il bianco Rec.709 con un CST senza tone mapping. Con un DRT dopo il nodo (ACES, AgX, DaVinci) alzalo a
4–5, altrimenti le alte luci vengono compresse due volte.

**Toni per zone.** Shadows, Whites e le Zone sono esposizioni, in stop, su una fascia di toni: Shadows sotto −1 stop,
Whites da +3,5 stop. Blacks è un velo lineare che sposta il nero senza muovere il grigio. Dentro la zona l'immagine si muove
come con un'esposizione, quindi la texture resta, e la compressione sta in una banda di transizione dichiarata. Nessuna
combinazione di cursori può solarizzare. Il costo di un nodo puntuale, detto chiaramente: quello che comprime, lo comprime
anche nella texture. Per questo il recupero locale è un nodo a parte. Formule e ricette:
[docs/TONE_MAPPING.md](docs/TONE_MAPPING.md).

**False color.** Una vista per controllo, sopra il cursore che serve:
- **Esposizione** usa bande in stop attorno al grigio 18%, nello stile ARRI. Verde è il grigio medio, rosa uno stop sopra
  (l'incarnato), giallo vicino al clip, rosso il clip, blu e viola il fondo.
- **Temperatura** e **Tinta** funzionano come in CineMatch. L'immagine diventa grigia, le dominanti si colorano di
  arancio/blu o verde/magenta, e quelle quasi neutre sono esaltate fino a 8× perché si vedano. Muovi il cursore finché
  quello che deve essere neutro resta grigio. Ogni vista risponde solo al suo cursore.

La vista sostituisce l'immagine: spegnila prima di renderizzare. [docs/FALSE_COLOR.md](docs/FALSE_COLOR.md)

**Data level.** Se Resolve decodifica una clip sulla scala di code value sbagliata, il nodo la corregge prima della curva
log. L'opzione *Correggi il Data Level* dello script la sistema per tutto il progetto.
[docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)

**Senza metadata.** Un ProRes da registratore esterno, o una clip che non si legge, lascia il nodo neutro. Spunta
*Avanzate › Sblocca controlli senza metadata* e scrivi EI, Kelvin e tinta di ripresa: i controlli si attivano e il nodo
parte neutro.

**Velocità.** Aprire un progetto non legge nessun file. Aprire il pannello aspetta al massimo mezzo secondo; un disco
lento finisce in background, con un limite di 15 secondi. *Rileggi* risponde in circa 2 secondi al massimo.

---

## Il nodo S-Log MetaRaw Detail

È il nodo creativo. Lavora **per aree**, su una base che rispetta i bordi, e regola le grandi aree senza appiattire il
dettaglio fine. È la parte di Highlights e Shadows di Lightroom che un nodo puntuale non può copiare.

| Gruppo | Controlli |
|---|---|
| **Gamma dinamica** | Local Contrast, Local Highlights, Local Shadows; viste *guadagno* e *base*. Local Highlights comprime le grandi aree luminose e tiene, anzi rinforza, la texture fine: il cielo si scurisce e le nuvole restano dettagliate. L'Highlights del nodo principale invece ammorbidisce la texture delle alte luci, come la pellicola |
| **Presenza** | Texture, Clarity, Dehaze |
| **Zone locali** | le zone del nodo principale, applicate alle aree |
| **Avanzate** | preservazione del dettaglio, raggio, soglie bordi e rumore, centro di Clarity, **Bianco** di Local Highlights, ingresso del nodo |
| **Velo** | livello e colore del velo che Dehaze toglie: li decidi tu, non vengono mai stimati fotogramma per fotogramma |

- Mettilo **subito dopo** S-Log MetaRaw, prima di CST, LUT o DRT. Decodifica in luce lineare quello che riceve e lo riscrive
  nella stessa codifica, quindi va prima di ogni conversione: lascia Color Space e Gamma del nodo principale su Timeline.
- È **spaziale**, quindi Generate LUT lo esclude, insieme al resto del suo nodo. Tienilo in un nodo tutto suo.
- I raggi seguono l'altezza del fotogramma. Il look è lo stesso a piena risoluzione, in proxy e nel viewer. Nessuna
  statistica per fotogramma, quindi niente flicker.
- Su Metal un fotogramma UHD richiede circa 6–18 ms, misurati su Apple silicon. Il ripiego su CPU è molto più lento.

**I suoi limiti, misurati.** Con Local Highlights −100 l'alone sul lato scuro di un bordo resta sotto il 3% del gradino.
Con Local Shadows o le zone locali a ±100, su un bordo netto di uno stop l'alone arriva a circa il 12% del gradino, al 4–6%
su gradini di 2–3 stop. Se lo vedi, abbassa *Soglia bordi*. Texture non alza la grana sotto la soglia rumore, ma vicino
ai bordi forti la grana può crescere di 1,25–1,7 volte. Dehaze ha bisogno di un velo vero da togliere.
[docs/DETAIL.md](docs/DETAIL.md)

---

## Aggiornamenti e privacy

- I **nodi** chiedono a GitHub l'ultima release di questo progetto al massimo una volta al giorno, in background. La
  richiesta porta solo la versione del programma (`User-Agent: SLogMetaRaw/2.1.0`). Per disattivarlo crea il file vuoto
  `~/Library/Application Support/SLogMetaRaw/no_update_check`.
- Lo **script** controlla solo quando clicchi la sua versione.
- Un clic apre soltanto un link di download delle release GitHub di questo progetto. Niente viene installato senza di te.

---

## Come funziona, in breve

- **Metadata.** I parser sono in Python puro, senza dipendenze. Leggono i metadata di acquisizione SMPTE RDD 18 fotogramma
  per fotogramma (traccia `rtmd` degli MP4, pacchetti ST 436 degli MXF), l'XML NonRealTimeMeta di Sony, l'SPS H.264/HEVC e
  il descrittore immagine MXF. Una clip di più gigabyte costa circa 100 KB di lettura.
- **Dallo script al nodo.** Ogni clip ha un record JSON nella cache. Il nodo trova il suo file dal percorso sorgente che
  Resolve gli passa, legge il record e, se manca, lo crea in background.
- **Matematica del colore.** La catena è: decodifica della curva di camera, rapporto di EI, bilanciamento Bradford dal
  luogo di Planck (con la tinta perpendicolare in CIE 1960 uv), poi toni con un solo guadagno per pixel da una norma dei
  suoi canali (la cromaticità resta), poi colore, poi uscita. Tutto in luce lineare, con curve e gamut pubblicati da Sony.
- **Una matematica, tre implementazioni.** La matematica sta in `ofx/SLogMetaRaw/math` e si compila sia come C++ sia come
  Metal. Un modello Python di riferimento le verifica: CPU e GPU concordano entro 2·10⁻⁴, con l'FMA disattivato su ogni
  percorso.
- **Test.** 322 test automatici: parser, modelli di riferimento, C++, Metal, un host OpenFX in miniatura che carica i due
  nodi come fa Resolve, e i file golden dei pannelli.

---

## Compilare dal sorgente

```bash
make -C ofx/SLogMetaRaw                     # plugin universale, arm64 + x86_64 (serve Xcode)
make -C ofx/SLogMetaRaw test-bins           # binari di test
python3 -m unittest discover tests          # i test
./install.sh --dev                          # script e plugin puntati su questa cartella
./packaging/build_installer.sh              # dist/SLogMetaRaw-<versione>.dmg
python3 -m slogmetaraw clip.MP4             # lettura stile Catalyst da riga di comando
```

```
slogmetaraw/         parser, scrittura in Resolve, finestra dello script, controllo aggiornamenti
resolve_script/      launcher per Workspace › Scripts
ofx/SLogMetaRaw/     math/ (condivisa CPU/Metal), src/ (common, develop, detail), metal/
tools/               generatori di matrici, icone e grafici
tests/               test e modelli di riferimento (le clip di prova non sono nel repository)
packaging/           installer, guide, disinstallatore
docs/                TONE_MAPPING, DETAIL, FALSE_COLOR, DATA_LEVELS
```

---

## Limiti noti

- Il pannello Camera Raw di Resolve e la stabilizzazione giroscopica non si sbloccano per gli MP4: vivono dentro i
  decoder di Resolve. S-Log MetaRaw ricostruisce i controlli del colore, non apre una porta dentro Resolve.
- Alcune camere (fra cui l'a6300) non registrano i Kelvin: in quel caso sono stimati dal preset di luce e segnalati.
- S-Log2 segue il documento Sony. La curva S-Log2 di Resolve differisce di circa 0,15 stop.
- Da verificare su più file: XAVC HS (HEVC), HLG, S-Cinetone, zoom motorizzati.
- **Progetto hobbistico e indipendente**, distribuito così com'è, senza garanzie e senza responsabilità per l'uso
  professionale. Il codice è aperto: leggilo, provalo, modificalo.

---

## Crediti e licenza

**Ivan Mazzone + Claude** · [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).
Scritto con Claude (Anthropic): la 1.0 il 19 settembre 2026, la 1.1.0 il 22 settembre, la 2.0.0 il 23 settembre 2026.
La storia completa è in [RELEASE_NOTES.md](RELEASE_NOTES.md).

Riferimenti per i tag Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) e
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) di AdrianEddy (MIT), da cui viene parte della tabella
dei tag.

[GNU GPL v3.0 o successiva](LICENSE). L'SDK OpenFX è © The Open Effects Association (BSD-3). Sony, XAVC e Catalyst sono
marchi di Sony Group Corporation; DaVinci Resolve è un marchio di Blackmagic Design. Progetto indipendente, non affiliato
né approvato da nessuna delle due aziende.
