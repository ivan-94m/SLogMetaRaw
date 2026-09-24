# Changelog

## S-Log MetaRaw 2.0.0

Una versione maggiore, perché cambiano insieme la matematica, i controlli e il codice:

- i **Toni** sono rifatti da zero, con un Highlights che è una vera spalla filmica;
- nasce un **secondo nodo** per il recupero locale e la presenza;
- il **bilanciamento del bianco** non si inverte più in nessun punto, e la tinta della FX6 si legge giusta;
- i **false color** di temperatura e tinta si comportano come quelli di CineMatch;
- il nodo **avvisa da solo** quando esce una versione nuova;
- la lettura dei metadata è **molto più veloce** e ha limiti di tempo chiari;
- il plugin è **riscritto in moduli**.

I toni della 1.x non si possono convertire nei nuovi, e questo è il motivo del salto a 2.0.

Una premessa, che vale per tutto quello che segue. I controlli lavorano su una scienza colore applicata con rigore, e per
questo l'immagine si comporta in un modo che ricorda un file RAW. Resta però un MP4 log: nel lavoro intenso la sola
scienza colore non basta, e la mancanza di informazioni nell'immagine si fa sentire appena si forzano i limiti della
camera.

### Prima di aggiornare

- **I toni della 1.x ripartono da zero.** Highlights, Shadows, Contrast, Saturation, Color Boost e Color Recovery sono
  sostituiti da controlli nuovi, con una matematica diversa che non ha una conversione fedele. Per conservare l'aspetto di
  una clip finita, **prima di aggiornare** usa Generate LUT su quel nodo: congela il grade, senza animazioni.
- Dopo l'aggiornamento lo Stato del nodo dice cosa c'era, per esempio "Toni 1.1 azzerati (H −40, C +15)". La prima
  modifica ai nuovi toni toglie la nota.
- **Esposizione, data level, Color Space e Gamma non cambiano**: stessa matematica, stessi valori.
- **Il bilanciamento usa una curva di Planck più precisa** (vedi sotto): nei valori di ripresa non cambia niente, e negli
  spostamenti la differenza arriva al massimo a quella di circa 100 K a 5600 K, negli spostamenti più estremi.
- L'installer cancella la cache dei plugin di Resolve (`OFXPluginCacheV2.xml`), che Resolve ricostruisce al prossimo avvio.
  Senza, mostrerebbe il pannello vecchio e non vedrebbe il nodo Detail. Se installi a mano, cancellala tu. Poi riavvia
  Resolve.
- **Ogni installazione parte pulita**: il plugin e la libreria precedenti vengono sostituiti per intero (un pacchetto
  macOS aggiunge e sostituisce file, non toglie quelli vecchi) e le installazioni di sviluppo vengono tolte.
- **Il disinstallatore è rifatto**: rimuove tutte le versioni installate (1.x, 2.x, il vecchio nome SonyMeta, le
  installazioni di sviluppo) con cache, impostazioni e log; prima elenca tutto, chiede di chiudere Resolve e chiede se
  cancellare anche i CSV esportati; alla fine controlla che non sia rimasto niente. Con `--dry-run` mostra cosa
  rimuoverebbe senza toccare niente.

### Toni: esposizione per zone, con i nomi di Camera Raw

- **Contrast, Highlights, Shadows, Whites, Blacks, Vibrance, Saturation** (−100…+100), nell'ordine di Camera Raw.
- **Highlights è una spalla filmica.** In negativo comprime le alte luci con una pendenza che cala in modo continuo verso
  l'alto, come la pellicola, ACES 2.0 e AgX: a −100 il massimo che la camera registra (circa +6 stop sopra il grigio in
  S-Log3) arriva esattamente sul **Bianco**, senza velo grigio e senza clip. Grigio e toni sotto restano fermi, la pelle a
  +1 stop si sposta di 0,05 stop al massimo. Le luci più compresse vanno dolcemente verso il bianco a tinta costante
  (in Oklab): l'arancio non vira al salmone, il blu non vira al lavanda. Con un Bianco alto (DRT) −100 abbassa comunque
  il massimo di almeno 1,5 stop; con Soft Clip acceso la spalla lascia spazio al tetto. In positivo dà più stacco alle
  alte luci, con una pendenza limitata.
- **Nuovo cursore Bianco (stop)** nei Toni: dove arriva il massimo con Highlights −100 e dove Soft Clip mette il tetto.
  2,5 = il bianco di un Rec.709 con un CST senza tone mapping; con un DRT (ACES, AgX, DaVinci) va alzato a 4-5.
- Shadows e Whites sono **esposizioni per zona in stop dal grigio 18%**, come nella palette HDR di Resolve o in Base Grade
  di Baselight:
  - Shadows: sotto −1 stop, 100 = 2 stop.
  - Whites: da +3,5 stop, 100 = 1 stop.
  - Dentro la zona l'immagine si sposta come con un'esposizione e la texture resta; la compressione sta in una banda di
    transizione dichiarata.
- **Contrast** ruota attorno al Pivot con estremi limitati: a +100 la pendenza al pivot raddoppia, a −100 si dimezza. Non
  porta più l'immagine al grigio.
- **Blacks** è un velo in luce lineare: abbassa il nero fino a 3 stop o lo alza di 1, senza muovere il grigio.
- **Saturation e Vibrance** lavorano attorno alla luminanza e non dipendono più dallo spazio colore del nodo. Vibrance
  protegge gli incarnati. Un limite morbido impedisce canali negativi.
- **Un solo guadagno per pixel**, calcolato da una norma dei tre canali: la cromaticità resta, il nero assoluto resta nero.
- **Nessuna combinazione di cursori può solarizzare**, e un cursore che continua nella stessa direzione non fa mai tornare
  indietro un tono.
- Niente adattamento all'immagine (istogrammi, "auto"): darebbe flicker e non avrebbe senso dentro un LUT.
- Pulsante **Azzera toni**.
- Il nodo resta **puntuale**: Generate LUT lo esporta (consigliati 65 punti) e non può creare aloni.
- **Il costo, dichiarato**: un nodo puntuale che comprime una banda comprime anche la texture che ci sta dentro. Il
  recupero che la conserva sta nel nodo Detail.
- Tolti **Color Boost** e **Color Recovery**: le loro funzioni passano a Vibrance, alla Sat delle zone e a Soft Clip Color.

Formule, curve e ricette in `docs/TONE_MAPPING.md`.

### Nuovo gruppo Zone

- Quattro zone come nella palette HDR di Resolve: **Black, Shadow, Light e Specular**, ciascuna con Exp (stop), Sat, Range
  (bordo in stop) e Falloff (larghezza della transizione).
- **Contrast Pivot**: il tono attorno a cui ruota Contrast.
- **Soft Clip** e Soft Clip Color: ripiega le alte luci verso un tetto, al livello del Bianco, che non raggiungono mai.
  Color decide se le luci ripiegate vanno verso il bianco, come la pellicola, o tengono il loro colore. È contenimento, non
  recupero.
- **False color Zone**: colora ogni pixel con la zona che lo muove.
- Pulsante **Azzera zone**.
- I bordi di tutte le zone sono riportati attraverso il Contrast, quindi restano in stop di scena qualunque Contrast usi.

### Nuovo nodo: S-Log MetaRaw Detail

Il recupero "alla Lightroom" è per natura locale, e un nodo puntuale non lo può fare. Il nuovo nodo, nello stesso bundle,
lavora per aree su una base che rispetta i bordi:

- **Gamma dinamica**: Local Contrast, Local Highlights, Local Shadows.
- **Local Highlights è diverso dall'Highlights del nodo principale.** Comprime le grandi aree luminose (la base) con la
  stessa famiglia di spalla, ma lascia passare il dettaglio fine e lo rinforza dove la base è compressa, sopra la soglia
  del rumore: un cielo si scurisce e le nuvole tengono o guadagnano texture, come l'Highlights di Lightroom. Quello del
  nodo principale invece ammorbidisce la texture delle alte luci, come la pellicola. Anche qui le luci compresse vanno
  verso il bianco a tinta costante, e sui clip del sensore il dettaglio (che lì non c'è) sfuma. Ha il suo **Bianco
  (stop)** in Avanzate; non conosce l'EI scelto nel nodo principale, quindi se lo cambi molto correggi il Bianco.
  **Soglia bordi** decide cosa conta come dettaglio: più bassa, meno aloni e meno texture tenuta.
- **Zone locali**: le stesse zone del nodo principale, applicate alle aree invece che ai pixel.
- **Presenza**:
  - Texture: dettaglio fine; non alza la grana sotto la soglia rumore.
  - Clarity: contrasto locale a media scala.
  - Dehaze: livello e colore del velo li decidi tu, non vengono mai stimati per fotogramma, quindi niente flicker.
- Viste di controllo del **guadagno** e della **base**; pulsante **Azzera dettaglio**.
- Raggi relativi all'altezza del fotogramma: **stesso aspetto** a piena risoluzione, in proxy e nel viewer.
- Su Metal un fotogramma UHD costa 6–18 ms (misurati su Apple silicon). C'è un ripiego su CPU, bit-identico con qualsiasi
  numero di thread.
- **Dove metterlo**: dopo S-Log MetaRaw, prima di CST, LUT o DRT. È spaziale, quindi Generate LUT lo esclude insieme al
  resto del suo nodo: se esporti LUT, tienilo in un nodo dedicato.
- **Ingresso**: il nodo decodifica in luce lineare quello che riceve e lo riscrive nella stessa codifica. In automatico
  chiede lo spazio colore a Resolve; in YRGB, dove Resolve non lo dice, usa la codifica di camera della clip. La riga in
  cima dice sempre quale ha scelto. Va messo prima di qualsiasi conversione: se il nodo principale converte l'uscita
  (Color Space/Gamma diversi da Timeline), il suo campo Rilevato lo ricorda.
- **Limiti misurati e dichiarati**:
  - Local Highlights −100: sul lato scuro di un bordo l'alone resta sotto il 3% del gradino; sul lato chiaro una fascia
    larga come il raggio viene compressa meno, come nella 2.0 di prova (meno con Soglia bordi più bassa);
  - Local Shadows e zone locali a ±100: su un gradino netto di 1 stop l'alone arriva a circa il 12% del gradino (4–6% su
    gradini di 2–3 stop);
  - vicino ai bordi forti la grana cresce di 1,25–1,7 volte.

Guida in `docs/DETAIL.md`.

### Bilanciamento del bianco: niente più inversioni, e la tinta della FX6

- **La tinta della FX6 si leggeva cento volte troppo grande.** La camera la scrive in centesimi: un file che nel menu, in
  Catalyst Browse e nel pannello Camera Raw di Resolve dice 4,55 contiene 455. Il nodo prendeva 455 (limitato a 100) come
  tinta di ripresa: bilanciamento sbagliato già a riposo. Ora si legge il valore della camera.
- **Color Temp e Tint potevano invertirsi.** Due cause, entrambe tolte:
  - la curva di Planck (approssimazione di Kim et al.) aveva delle giunture a 2222 K e 4000 K. Ora è quella di Krystek,
    liscia, entro 1,4·10⁻⁴ dall'integrale di Planck esatto fra 1500 e 15000 K;
  - una tinta verde a bassi Kelvin portava a zero il cono S (blu) del bianco nell'adattamento Bradford, e da lì la risposta
    si ribaltava: era il caso di una FX6 a 3200 K con la tinta letta +100. Il lato verde ora si ferma dolcemente prima di
    quel punto (da circa +33 a 3200 K, +9 a 2000 K); da 5600 K in su non cambia niente.
- Verificato su tutta la corsa dei cursori: alzare Color Temp scalda sempre, alzare Tint aggiunge sempre magenta, qualunque
  sia il bianco di ripresa.
- I record dei metadata scritti dalle versioni precedenti si rileggono da soli: si sistemano anche le clip FX6 lunghe che
  mostravano "5600K stimato".

### False color di temperatura e tinta: come CineMatch

Le due viste del bilanciamento ora si comportano come quelle di CineMatch (FilmConvert):

- l'immagine diventa **grigia**;
- le dominanti si colorano con le sue tinte: **arancio / blu** per la temperatura, **verde / magenta** per la tinta;
- le dominanti quasi neutre sono **esaltate fino a 8×**, perché si vedano prima di diventare una dominante visibile.

Si regola come là: muovi il cursore finché quello che deve essere neutro resta grigio.

Una differenza voluta. CineMatch decide l'asse dalla tinta HSL del pixel. S-Log MetaRaw lo decide dalla risposta reale
dei due cursori, misurata in CIE 1960 uv al valore corrente. Così una dominante verde non accende la vista della
temperatura, e ogni vista risponde solo al suo cursore.

Sotto −6 stop e sopra +5,5 stop il colore sfuma nel grigio: lì la tinta è rumore o clipping.

Le vecchie bande in Kelvin (bianco = neutro, 75/200/500 K) non ci sono più. La vista dell'esposizione non cambia.
Dettagli in `docs/FALSE_COLOR.md`.

### Versione e aggiornamenti nel nodo

- In cima a entrambi i nodi c'è la versione.
- Il controllo su GitHub gira da solo, al massimo una volta al giorno, in background, senza fermare Resolve. La richiesta
  porta solo la versione del programma.
- Se c'è una versione nuova il pulsante mostra **🟢 v2.0.0 → 2.x.y**, e il clic apre il download del DMG nel browser.
  - Il programma non installa nulla.
  - Apre solo gli installer delle release di questo progetto.
- Senza novità, il clic controlla subito.
- Per disattivare il controllo automatico crea il file `~/Library/Application Support/SLogMetaRaw/no_update_check`.
- Lo script controlla solo quando si clicca la sua versione, e il controllo non blocca più i pulsanti.

### Metadata: più veloci, con limiti di tempo umani

**Nel nodo**

- Aprire un progetto non lancia più letture: il nodo usa solo la cache.
- Aprendo il pannello il nodo aspetta al massimo **mezzo secondo**. Se il disco è lento la lettura continua da sola, con un
  limite di 15 s, e i valori arrivano alla riapertura. Dopo un timeout si ritenta dopo un minuto, non a ogni clic.
- **Rileggi metadata** risponde in circa 2 s al massimo: la scrittura nel Media Pool continua in background.
- La lettura per il nodo campiona 8 punti della clip invece di 120, con accessi mirati. Su HDD e NAS si passa da secondi
  a decine di millisecondi, con gli stessi valori.
- ProRes, MOV, BRAW e gli altri formati non Sony non avviano più il lettore.
- I messaggi dicono cosa è successo e cosa fare: disco lento, formato non Sony, metadata non trovati.
- Gli errori del lettore finiscono in `~/Library/Logs/SLogMetaRaw/plugin-child.log`.

**Nello script**

- La lettura non avanza più al ritmo del timer della finestra: 21 clip passano da circa 30 s a meno di un secondo.
- Ogni clip si legge con al massimo 24 campioni in un secondo, con letture mirate. La LUT di camera incorporata non si
  legge se non serve.
- Un volume che non risponde viene saltato **una volta sola**, con un avviso: "Il volume «X» non risponde: saltate N clip".
  Il limite è di 10 s per la prima clip del volume e 6 s per le successive.
- "Scrivi in Resolve" scrive più clip per ogni aggiornamento della finestra.
- *Rileggi metadata* trova la clip nel Media Pool confrontando prima i percorsi normalizzati; risolve i collegamenti
  simbolici solo se non trova niente.
- L'avvio dal menu non aspetta più inutilmente quando Resolve fornisce già la connessione.

**MXF**

- Gli **MXF FX6 lunghi** (oltre circa 20 minuti) ora si leggono correttamente: l'inizio dell'essenza viene dal partition
  pack invece che da una ricerca nei primi 4 MB.
- Riconosciuti `s-gamut3-cine` e `s-log3-cine` scritti nell'XML NonRealTimeMeta.

**Cache**

- Nuova versione di cache (5), con record parziali segnati come tali.
- Il record completo dello script sostituisce quello parziale del nodo, mai il contrario.

### Sblocca controlli senza metadata

- Nuova spunta in **Avanzate**. Per ProRes da registratori esterni o clip che non si leggono, attiva i controlli con i
  **riferimenti di ripresa** che scrivi tu: EI, Kelvin e Tint.
- Appena spuntata, il nodo parte neutro. Cambiare un riferimento cambia i numeri, non l'immagine.
- Se l'ingresso non è noto il nodo lo dice e resta neutro finché non scegli *Ingresso nodo*.
- Se poi i metadata arrivano, il nodo lo segnala; *Rileggi* li adotta.
- La riga Camera dice sempre in che stato si trova il nodo: metadata letti, non trovati, sbloccato, profilo non log.

### Correzioni

- La cache riconosce la stessa clip anche attraverso un collegamento simbolico o con un percorso in forma Unicode diversa.
  Scarta invece il record di un file diverso che occupa lo stesso percorso.
- Una clip letta dopo un timeout non riceveva i valori di camera.
- Copiando un nodo su una clip senza metadata restavano la correzione di data level e lo spazio colore della clip
  precedente.
- Un errore del kernel Metal lasciava l'uscita indefinita: ora è un errore esplicito.
- **Parità CPU/GPU**: le funzioni Metal ora sono precise e senza FMA, come la CPU su arm64 e Intel. Un test lo verifica su
  tutti e tre i percorsi.
- Un processo figlio bloccato su un volume morto non può più tenere fermo il pannello: viene terminato con tutto il suo
  gruppo, senza attese bloccanti.
- Una temperatura di ripresa sotto 1667 K faceva dividere per zero il calcolo del bianco.

### Sotto il cofano

- **Il plugin è diviso in moduli**:
  - la matematica è condivisa fra CPU e Metal (`math/`), e da lì il generatore scrive il C++ e il sorgente Metal;
  - il codice comune (file, JSON, processi, versioni, parametri) sta in `src/common`;
  - ogni nodo ha il suo modulo;
  - il Metal ha un contesto con cache delle pipeline per dispositivo.
- Un solo meccanismo per lanciare processi, con limiti di tempo e terminazione dell'intero gruppo.
- Commenti sfoltiti: restano quelli utili alla manutenzione (vincoli esterni, invarianti, trappole numeriche). Teoria e
  misure stanno in `docs/`.
- La versione vive in un solo posto (`slogmetaraw/__init__.py`), da cui la prendono plugin, pacchetto, DMG e guide.

### Test

Da 193 a **322 test**. Nuove verifiche:

- modelli Python di riferimento per toni, colore e Detail;
- parità Python / C++ / Metal entro 2·10⁻⁴, anche nella slice Intel sotto Rosetta;
- invarianti dei toni: niente solarizzazione, monotonia, identità a riposo;
- la spalla di Highlights: pendenza che cala senza mai risalire, grigio fermo, atterraggio sul Bianco, colori che vanno
  verso il bianco senza canali negativi;
- Local Highlights: texture tenuta dove il nodo principale la ammorbidisce, nessuna inversione del dettaglio, aloni entro
  quelli della 2.0 di prova;
- il bilanciamento: bianchi sempre reali, Color Temp e Tint monotoni su tutta la corsa, la tinta FX6 in centesimi;
- invarianti del Detail: aloni, rumore, stesso risultato con 1 o N thread;
- un host OpenFX in miniatura che carica i due nodi come Resolve;
- i file golden dei due pannelli;
- i tempi dei processi figli;
- il controllo aggiornamenti.

### Documentazione

- README riscritto da zero in cinque lingue.
- Guida di tre pagine, in italiano e in inglese, nel DMG.
- Nuovi `docs/TONE_MAPPING.md` e `docs/DETAIL.md`, `docs/FALSE_COLOR.md` aggiornato.

---

## S-Log MetaRaw 1.1.0

Questa versione tocca tutte e due le metà del programma. Lo script ha una finestra
nuova, parla cinque lingue e sa scrivere in Resolve una clip alla volta. Il nodo
impara tre cose che prima non sapeva fare: correggere il **data level** quando
Resolve lo sbaglia, **misurare** esposizione e bilanciamento con tre false color, e
sviluppare le alte luci con una **vera spalla filmica** invece del gradino che aveva.

**Aggiornamento:** installa sopra la versione precedente. Prima di riavviare Resolve
conviene cancellare
`~/Library/Application Support/Blackmagic Design/DaVinci Resolve/OFXPluginCacheV2.xml`,
perché il set di parametri del nodo è cambiato e con la cache vecchia Resolve mostra
il pannello di prima. I nodi già presenti nei progetti mantengono i valori impostati;
vedi *Cosa cambia nei progetti esistenti* in fondo.

---

### Data level: quando Resolve interpreta male la scala

Le curve log Sony sono pubblicate su code value **non scalati** — il nero di S-Log3
è il codice 95 su 1023, il grigio 18% è 420 — mentre Rec.709, le Cine e HLG sono
ancorate al range legale. Resolve decide quale scala usare dall'attributo *Data
Level* della clip, e il suo *Auto* è documentato come una deduzione dal codec. Quando
sbaglia, ogni valore che entra nella decodifica log è sbagliato, soprattutto nelle
ombre.

- **Lo script legge e corregge l'attributo.** Nuova casella *Correggi il Data Level*,
  attiva di default: imposta *Data Level* su Full o Video secondo la gamma di ripresa.
  È la correzione vera — sistema la decodifica per tutto il progetto, CST, scope ed
  export compresi, non solo per il nodo — ed è reversibile.
- **Il nodo compensa quello che resta.** Nuovo controllo *Avanzate › Data level in
  ingresso*: Automatico, Full, Video o nessuna correzione. La rimappatura avviene sui
  code value, nella codifica di camera, **prima** della decodifica log, così
  esposizione e bilanciamento continuano a lavorare su luce lineare corretta.
  Funziona uguale in DaVinci YRGB, in timeline color managed e in ACES.
- **Sugli MXF il range prima non veniva letto affatto.** Ora si legge il descrittore
  immagine CDCI (livelli di riferimento del nero e del bianco).
- Nuove colonne nel CSV e nuove righe nel pannello dettagli: scala richiesta dalla
  gamma, range dichiarato dal file e da dove, interpretazione di Resolve.

La ricerca completa, camera per camera, è in `docs/DATA_LEVELS.md`.

### False color: tre viste di misura

Un pulsante per ciascuno dei tre controlli che servono a regolare, ciascuno sopra il
proprio cursore.

- **Esposizione** — bande in fermate attorno al grigio 18%, nella convenzione ARRI:
  verde sul grigio medio, rosa una fermata sopra (incarnato), giallo vicino al clip,
  rosso al clip, blu e viola in basso.
- **Temperatura** e **Tint** — leggono quanto ogni pixel è lontano dal neutro
  **in Kelvin e in unità di tint**: la banda dice di quanto muovere lo slider, non
  solo che c'è una dominante. Bianco = neutro.

Sono prese subito dopo esposizione e bilanciamento e prima dei trim, così rispondono
solo ai controlli a cui appartengono. Dettagli e confronto con CineMatch in
`docs/FALSE_COLOR.md`.

### Highlights e Shadows rifatti

Il vecchio operatore era un **gradino, non una spalla**: sopra +5 stop la pendenza
tornava esattamente a 1 — nessuna compressione, solo un offset — con un salto di
pendenza da 0,20 a 1,00 in un punto, che in un cielo si legge come una riga. E
recuperava 0,9 stop su una S-Log3 che ne porta circa 6.

- **Highlights in negativo è una spalla filmica**: ripiega le alte luci verso un
  asintoto che non raggiunge mai, quindi **non clippa più niente**, spostando il
  grigio 18% di 0,003 stop. Al massimo porta i ~6 stop sopra il grigio di una S-Log3
  dentro i 2,47 che prende un Rec.709.
- **Shadows apre il dettaglio in ombra** attorno a −4 stop senza toccare il grigio né
  il piede: essendo un moltiplicatore, **il nero assoluto resta nero** a qualsiasi
  valore, e sotto −8 stop il piede non si muove.
- **Nuovo controllo *Color Recovery***: verso destra restituisce colore alle alte luci
  recuperate — una fronte chiara tiene il suo calore invece di diventare un piattone
  rosa — e toglie croma alle ombre aperte, dove sta il rumore. Verso sinistra va verso
  la pellicola. Non può mai aggiungere colore che il pixel non aveva.
- Tutto **puntuale**: l'uscita di un pixel dipende solo da quel pixel, quindi non può
  creare aloni. E **C⁴ alla giunzione**, quindi non può nemmeno stampare l'anello
  concentrico che una curva con la curvatura che salta produce in un cielo.

Le curve sono tarate contro la stampa Kodak 2383 e la Blackmagic Gen 5, misurate dai
LUT che Resolve installa. Metodo, formule e un compromesso dichiarato in
`docs/TONE_MAPPING.md`.

### La scala dei controlli di tono

I cinque trim del gruppo *Toni* passano da −1…+1 a **−100…+100 con due decimali**, la
stessa scala che Resolve usa per Col Boost, Shad e High. I valori salvati vengono
convertiti: una color fatta prima apre identica.

### Lo script

- **Finestra rifatta**: una riga di pulsanti, una di opzioni, avanzamento in tempo
  reale con percentuale, le due tabelle e una riga di stato. Si apre centrata sulla
  finestra di Resolve (anche a tutto schermo), è ridimensionabile e resta in primo
  piano.
- **Cinque lingue** — italiano, inglese, spagnolo, portoghese e cinese semplificato —
  seguendo la lingua di Resolve. Una stringa senza traduzione resta nella lingua di
  partenza, mai vuota.
- **La scansione arriva sempre in fondo**: la lettura gira in un processo separato con
  un limite di 15 secondi per clip, così un file su un volume morto viene segnato e
  saltato invece di bloccare tutto.
- **Suono di notifica** a fine lettura e scrittura, diverso se ci sono stati errori.
- **Controllo aggiornamenti** cliccando la versione in basso a destra: se ce n'è una
  più recente il testo diventa verde e il click avvia **solo il download** del disco.
  Offline o errori finiscono nella barra di stato, mai in un'eccezione.
- **Tag per camera** su richiesta (spento di default), per le smart bin.

### Il bottone "Rileggi metadata" del nodo

Ora fa due cose in un colpo: rilegge la clip dal file **e** scrive i metadata nella
clip corrispondente del Media Pool, come farebbe lo script ma per una sola clip. Il
campo Stato riporta quanti campi sono stati scritti, quali rifiutati e il Data Level
risultante.

### Correzioni

- **La finestra dello script non si chiudeva** in certe condizioni, e poteva lasciare
  processi appesi alla chiusura di Resolve.
- **Avvio dal menu di Resolve** non affidabile: il launcher ora usa la connessione
  fornita da Resolve e, se `localhost` non risponde, prova gli indirizzi assegnati allo
  stesso Mac. Gli errori di avvio finiscono in un messaggio e in
  `~/Library/Logs/SLogMetaRaw/launcher.log`.
- **Timecode con frame rate non interi**: 23,976 e 29,97 venivano troncati a 23 e 29,
  e su clip lunghe l'End TC e la durata derivavano. Ora si arrotonda al base timecode
  corretto.
- **Divisione per zero** leggendo una clip con un solo campione richiesto.
- **Un file malformato non ferma più l'intera scansione** da riga di comando: l'errore
  esce su stderr e si prosegue con la clip successiva.
- **Percorsi con accenti o emoji**: la chiave della cache viene normalizzata NFC in
  Python e nel plugin, e il parser JSON del plugin gestisce i caratteri fuori dal
  piano base. Prima un'emoji nel percorso mandava in confusione i campi a sola lettura
  e faceva mancare la cache.
- **Il range dichiarato dal codec** veniva letto male quando l'MP4 non aveva la VUI ma
  aveva il box `colr`: il fallback non scattava mai.
- **Un pixel assurdamente luminoso** (o un infinito arrivato da un nodo a monte) poteva
  uscire nero dalla spalla per straripamento in virgola mobile a 32 bit. Riscritta nella
  forma algebrica equivalente che non straripa.
- **L'installer si fermava con "Installazione non riuscita".** Gli script `preinstall` e
  `postinstall` del pacchetto non avevano il bit di esecuzione: macOS li avvia con
  `execve`, che fallisce, e PackageKit lo riporta come *"il file preinstall non esiste"*
  interrompendo tutto. Il bit non era registrato nel repository in nessun commit, quindi
  chiunque avesse clonato il progetto avrebbe costruito un pacchetto che non si installa.
  Corretto sul filesystem, nell'indice di git, e forzato di nuovo in fase di build perché
  non possa sparire un'altra volta.
- **La versione del pacchetto era scritta a mano** in `distribution.xml` e nella pagina di
  benvenuto dell'installer, mentre il DMG la leggeva dal sorgente: l'installer poteva
  dichiarare una versione diversa da quella del disco. Ora c'è una sola sorgente e un test
  che la verifica su tutti i file del pacchetto.
- Il nodo non può più far cadere Resolve se manca un parametro: si disattiva e lascia
  passare l'immagine.

### Cosa cambia nei progetti esistenti

- I nodi che avevano **Highlights e Shadows a zero** aprono **identici**.
- I nodi che li **usavano** tengono i loro numeri ma rendono diversamente: il vecchio
  operatore non aveva una spalla da convertire, quindi non esiste una conversione
  fedele. Non viene azzerato niente di nascosto, così l'intenzione resta visibile.
- Gli altri trim di tono vengono riscalati automaticamente e non cambiano aspetto.
- La correzione del data level parte **spenta** sui nodi salvati prima di questa
  versione, così nessuna color già fatta cambia.

### Test

Da 22 a **193 test**. Nuove suite per data level, false color, tone mapping,
interfaccia, launcher, aggiornamenti, connessione a Resolve e installazione. La
matematica del nodo è verificata su tre implementazioni che devono concordare: CPU,
kernel Metal e un modello Python di riferimento.

---

## S-Log MetaRaw 1.0.1

Versione di stabilità: dopo i blocchi e le chiusure improvvise di DaVinci Resolve segnalati sulla 1.0.

- **Corretto il difetto che rendeva instabile il nodo.** Resolve descrive un plugin una volta per ogni contesto
  che supporta: i nomi dei parametri venivano marcati come "già usati" alla prima descrizione, così nel secondo
  contesto il nodo nasceva senza controlli e Resolve lo segnalava come non disponibile o si chiudeva.
- **Il nodo non può più far cadere Resolve:** se un parametro manca, si disattiva e lascia passare l'immagine.
- **Niente più attese lunghe nell'interfaccia:** la lettura dei metadata ha un limite di 8 secondi, non viene
  ritentata a ogni clic, e le clip che sul disco sono solo un segnaposto vengono saltate invece di essere scaricate.
- **Script più robusto:** un errore in una clip non ferma più le altre, gli errori compaiono nella finestra
  invece di chiudere lo script, e se il disco è pieno lo dice invece di fallire in silenzio.
- **Lo script non lascia più processi appesi** quando Resolve viene chiuso con la finestra aperta.
- Pannello riordinato come il Camera Raw Sony, guide in italiano e inglese, licenza GNU GPL v3.
- Nuovi test: un host OpenFX in miniatura carica il plugin e ripete le azioni di Resolve (caricamento,
  descrizione dei due contesti, creazione del nodo su una clip vera), così questi difetti non possono tornare.

**Aggiornamento:** installa sopra la versione precedente e riavvia Resolve. I nodi già presenti nei progetti
mantengono i valori impostati.

---

## S-Log MetaRaw 1.0

Prima versione pubblica. Ivan Mazzone + Claude — github.com/ivan-94m · @ivan_94m.

**Script S-Log MetaRaw** (Workspace › Scripts › S-Log MetaRaw)
- Legge i metadata di ripresa Sony da MP4 (XAVC S / S-I / HS) e MXF (XAVC Intra/Long): obiettivo, focale, diaframma, fuoco, shutter, ISO/EI, gain, bilanciamento del bianco, tint, S-Log/S-Gamut, data level, S&Q, LUT di camera, IBIS/giroscopio e altro. Le etichette sono le stesse di Catalyst Browse.
- Registra i dati nei campi del Media Pool di Resolve (Metadata, colonne, keyword, data burn) e corregge i valori che Resolve legge male sugli MXF.
- Esporta un CSV per creare campi personalizzati; i file originali non vengono mai modificati.

**Plugin S-Log MetaRaw** (OpenFX › S-Log MetaRaw)
- Controlli in stile Camera Raw "Sony Video" per gli MP4 che Resolve non abilita: Decode Using, White Balance (As shot / preset / Custom), Color Space e Gamma come un CST, Color Temp, Tint, Exposure (EI), Shadows, Highlights, Color Boost, Saturation, Contrast.
- Si imposta da solo con i valori di ripresa della clip, anche quando il nodo viene copiato su altre clip.
- Luce lineare, adattamento cromatico Bradford, GPU Metal con fallback CPU; plugin universale Apple Silicon + Intel.

**Requisiti:** macOS 12+, DaVinci Resolve 21. Testato solo su Resolve Studio 21.1 su macOS; versioni precedenti non provate. Installer non firmato: al primo avvio usa tasto destro › Apri.

**Licenza:** GNU GPL v3 o successiva. Progetto hobbistico e indipendente, distribuito così com'è, senza garanzie e senza responsabilità per l'uso professionale. Codice aperto a verifiche, test e modifiche.
