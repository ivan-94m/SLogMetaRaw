# Changelog

## S-Log MetaRaw 1.1.1

Versione di correzione. Due difetti segnalati sul campo, entrambi riprodotti e
misurati prima di toccare una riga: **le alte luci si invertivano** e **una clip FX6
usciva verde e incorreggibile**. Nel verificarli ne sono usciti altri cinque, elencati
in fondo.

**Aggiornamento:** installa sopra la versione precedente. Non serve cancellare la
cache OFX: il set di parametri non cambia. I nodi già presenti nei progetti
mantengono i loro valori — ma *Highlights* ora vuol dire un'altra cosa, vedi in
fondo.

---

### Le alte luci si invertivano

Lo stadio di tono della 1.1.0 scalava i tre canali per `f(norm)/norm` e poi li tirava
verso la luminanza con una purezza `t^k(t)`. La spalla, da sola, era corretta. Il
difetto era la **coppia**: quando la spalla raggiunge il suo asintoto è piatta, mentre
la purezza continua a scendere senza limite. Con il primo fattore fermo e il secondo
che cala, il prodotto **cala**: un pixel cromatico più luminoso usciva più scuro.

| Highlights | si invertiva sopra |
|---|---|
| −10 | +7,2 stop dal grigio |
| −20 | +6,2 stop |
| −50 | +5,2 stop |
| −100 | +4,2 stop |

Una S-Log3 arriva a +7,74 stop, quindi già a −10 l'ultimo mezzo stop registrato si
invertiva. Sui grigi non succedeva mai, perché lì i due fattori coincidono: si vedeva
solo sul colore — la cima di un cielo, un neon, una lampada — da cui la segnalazione
«a volte». Sulla griglia di controllo: **16.503 passi non monotoni**.

C'era un secondo difetto nello stesso punto. La luminanza verso cui il pixel veniva
tirato è la Y XYZ del gamut del nodo, e in un gamut largo il coefficiente del blu è
**negativo** (DaVinci WG −0,1478, S-Gamut3.Cine −0,1001). Un blu saturo ha Y minore di
zero, e il blend lo spingeva **sotto il nero** dentro una zona luminosa.

### Highlights adesso: una pressa ancorata al contenitore registrato

La scena è una **vasca di luce lineare**. Il grigio 18% è la mediana; il tetto è il
soffitto della curva che **la camera** ha registrato — S-Log3 +7,74 stop sopra il
grigio, S-Log2 +6,26, S-Log +5,76. È una proprietà del formato: lo stesso numero su
ogni fotogramma di ogni clip girata così, qualunque cosa faccia la timeline.
L'esposizione muove l'immagine *dentro* la vasca; la vasca non si muove mai.

`Highlights` dice, **linearmente nel cursore**, dove atterra quel tetto:

- **a −100** il tetto atterra esatto su 1,0 lineare, il picco che un segnale Rec.709
  contiene;
- **in positivo** fa lo specchio e stira la cima della scala fino a 2 stop, per
  riportare al picco un'alta luce che satura prima.

La vecchia legge metteva l'asintoto a `1/|Highlights|`, un'iperbole: i primi dieci
punti di corsa spostavano il tetto da infinito a +5,8 stop, e i novanta rimanenti
valevano 3,3 stop **in tutto**. Da qui «dopo pochi valori è già estremo».

Progressione misurata a −100 su contenitore S-Log3:

| stop di scena | pendenza | |
|---|---|---|
| −4 … −2 | 1,000 | intatto, perfettamente lineare |
| 0 (grigio 18%) | 0,986 | il grigio si sposta di 0,008 stop |
| +1 (incarnato) | 0,928 | |
| +2 (bianco 90%) | 0,695 | comincia a comprimere |
| +3 | 0,287 | |
| +4 → +7,74 | 0,066 → 0,000 | asintotico, non clippa mai |

### Color Recovery: adesso è una miscela, e non può rompere il rolloff

Non è più un esponente che scappa. È il **peso fra due modi di applicare la stessa
curva**: un fattore unico sui tre canali, che conserva tutto il colore di scena, e la
curva per canale, dove i tre condividono un soffitto e salendo convergono — perché
convergere *è* desaturare, ed è così che lo fa la pellicola.

Verso destra tiene il colore, verso sinistra va verso la pellicola. È la leva organica
sul cielo: a −100 di Highlights, un cielo a +4 stop passa da saturazione 0,249
(pellicola) a 0,650 (scena) muovendo solo questo cursore.

**Perché non può invertire**: entrambi i rami sono monotoni in ogni canale e il peso
non dipende dal pixel, quindi la miscela è monotona. Non è una taratura, è una
proprietà strutturale. Verificato: **0 passi non monotoni su 5.996.250 confronti**.

### La clip FX6 usciva verde

Sony scrive la correzione di tinta nel tag RTMD `0x811F` in **centesimi**: la clip
`FX6_0024.MXF` legge **15,17** in Catalyst Browse e nel pannello Camera Raw di
Resolve, e nel file porta **1517**. Quel numero finiva tale e quale in un modello la
cui unità è `Duv × 3000`, che metteva il bianco di ripresa a Duv 0,506 — fuori dal
luogo spettrale — e i rapporti di von Kries uscivano **negativi**: R −0,95, G +1,17,
B −1,73. Un'immagine con il solo canale verde.

Due cose lo rendevano *incorreggibile* invece che semplicemente sbagliato:

- il cursore Tint arriva a 100 e non poteva raggiungere 1517 per annullarlo. Restava
  incollato a 100 mentre il valore di ripresa restava 1517, e portarlo a 0 cambiava
  quasi nulla perché il lato ripresa dominava quindici a uno;
- **a controlli fermi l'immagine sembrava giusta**, perché decodifica e codifica sono
  inverse esatte: con bianco scelto uguale a bianco di ripresa i rapporti valgono 1 e
  l'errore si cancella. Quindi *As shot* mostrava bene e qualsiasi altra cosa no.

Corretto a ogni livello:

- **il lettore riporta il numero che mostra la camera** (15,17, come Catalyst e come
  Resolve), non l'intero grezzo;
- **il record è controllato su entrambi i lati**, nello script e nel nodo: Kelvin
  dentro il luogo di Planck, tint dentro la corsa del cursore, EI positivo. Se un
  valore è stato limitato il campo *Stato* lo dice, invece di gradare in silenzio da
  un numero che nessuno ha scelto;
- **il punto di bianco è protetto**: nessun valore che un file può portare produce più
  un colore che i coni non rappresentano;
- **«As shot» legge i valori di ripresa direttamente.** Prima si fidava di un
  assegnamento ai cursori avvenuto una volta sola, quando il nodo si legava alla clip.
  Se i metadata arrivavano dopo — un MXF il cui primo parse supera il watchdog di 8 s,
  una cache scritta dallo script più tardi — i valori nascosti si aggiornavano e i
  cursori visibili no. Il menù diceva *As shot* e il nodo sviluppava da un riferimento
  che nessuno aveva scelto. Ora quella deriva è impossibile.

E una conseguenza pratica: un cursore ancora fermo sul **vecchio** valore di ripresa è
un cursore che il colorist non ha toccato, quindi segue la correzione; uno che è stato
mosso è una decisione di grading e resta esattamente dov'è.

### Altri cinque difetti, trovati verificando i primi due

- **Temp 3200 con Tint +100** — entrambi raggiungibili dai cursori — davano un bianco
  la cui risposta del cono S vale −0,009 e un rapporto di −152. Ora il tint satura
  invece di rompersi, e satura solo dove stava chiedendo un illuminante che non
  esiste.
- **A 25000 K si divideva per zero**: i due campioni del luogo di Planck finivano
  clampati sullo stesso punto e la tangente aveva lunghezza nulla.
- **Contrast** leggeva la luminanza XYZ, negativa per un blu saturo in gamut largo.
  Il `max(Y, 1e-6)` la leggeva come −17,4 stop, e un contrasto negativo la
  trasformava in un guadagno di circa 100.000 su quel pixel. Ora usa la stessa power
  norm dello stadio di tono.
- **Uno spazio colore d'ingresso non riconosciuto** veniva assunto in silenzio. È il
  tipo di errore invisibile finché non tocchi qualcosa, perché a controlli fermi si
  cancella: ora lo dice in *Rilevato* e in *Stato*.
- **Gli script di installazione non erano eseguibili in git.** `pkgbuild` li avrebbe
  impacchettati senza il bit di esecuzione.

### Cosa cambia nei progetti esistenti

`Highlights` **vuol dire un'altra cosa**. Prima il numero fissava l'asintoto a
`1/|H|` in lineare, adesso dice linearmente dove atterra il tetto del contenitore
registrato. Un nodo salvato con la 1.1.0 apre con lo stesso numero e **grada in modo
diverso**, quasi sempre molto meno violento. È dichiarato nella versione delle
impostazioni (4 → 5), e il valore viene conservato, non azzerato: quello che il
colorist aveva chiesto resta visibile invece di essere buttato via.

`Color Recovery` **non toglie più croma alle ombre aperte**. Non è una dimenticanza:
il conto è in [docs/TONE_MAPPING.md](docs/TONE_MAPPING.md) §4. In breve, il guadagno
delle ombre spende già tutto il margine di pendenza disponibile, e qualsiasi peso che
decade a zero fa invertire un canale che vale zero — una primaria satura uscita da un
gamut largo. Il rumore cromatico nelle ombre è un problema di riduzione rumore, non
qualcosa da contrabbandare dentro una curva di tono che deve promettere di non
invertire.

L'esponente del ginocchio passa da 3 a **2,5**: a 3 tutto quello sopra +3 stop finiva
in una banda di 0,139 stop, cioè alte luci piatte. A 2,5 ne restano 0,195, per uno
spostamento del grigio di 0,008 stop — lo 0,55% di un valore.

### Clip lunghe: i metadata di acquisizione non venivano trovati

Segnalato su una clip FX6 di **1h 37m** in 4K: nel nodo tutti i cursori grigi,
Focale, Diaframma, Fuoco, Shutter e ISO/EI a `—`, Bilanciamento `5600K stimato`, e
il campo Colore senza il nome del profilo. Nel Media Pool, invece, i metadata si
vedevano.

**Si cercava in una finestra fissa di 4 MiB dall'inizio del file, e poi si
rinunciava.** L'elemento ANC che porta i dati Sony è il *Data item* del content
package, quindi sta dopo i metadata di header, dopo l'eventuale index table e dopo
il primo elemento immagine — che in 4K long-GOP è l'I-frame di ancoraggio del GOP.
E l'index table cresce con la durata: 97 minuti a 25p fanno circa 145.800 voci, che
da sole spingono la prima essenza oltre i 4 MiB. Non trovandola, il lettore usciva
subito, **saltando le altre dodici finestre che stava già per leggere**.

Adesso il file lo si chiede al file. Un MXF dichiara nei suoi partition pack quanti
byte di metadata di header e di indice stanno davanti all'essenza, e nel Random
Index Pack in coda elenca l'offset di ogni partizione: sono poche centinaia di byte
di lettura e danno l'offset esatto invece di una scommessa. Se anche quello non
basta, si provano tutte le partizioni e poi le finestre sparse nel file, e solo
allora si rinuncia — dicendo quanti punti sono stati provati e quanti byte letti.
Tutti quei campi sono a 64 bit, quindi non c'è alcun limite ai 4 GB.

Corretti nello stesso giro altri due modi di mollare: un elemento ANC **a cavallo**
del bordo della finestra ora viene completato invece di essere scartato in silenzio,
e un elemento ANC che non è di Sony — un timecode, per dire — non interrompe più la
ricerca. La finestra, infine, si dimensiona sul bitrate della clip invece di essere
4 MiB fissi.

### Il profilo sopravvive nel sidecar XML

Su quella clip l'XML `*M01.XML` c'era e si leggeva benissimo — è da lì che
arrivavano obiettivo, LUT e frame rate. Conteneva anche `CaptureGammaEquation`, cioè
il profilo di ripresa, che veniva **letto e poi buttato via**: `color_space` si
costruiva solo dall'RTMD. Un `color_space` vuoto fa sollevare `NotSupported`, che
mette `supported = 0`, che spegne tutti e dodici i cursori.

Ora, quando l'RTMD non c'è, il profilo si ricava dall'XML. Il nodo **si accende** e
tono, contrasto e colore lavorano pieni. Bilanciamento ed Exposure restano mosse
relative a partire dai default, e il campo *Stato* lo dice a chiare lettere invece
di lasciar credere che 5600 K sia un dato letto. Anche il campo Bilanciamento
smette di scrivere `5600K stimato` quando i valori di ripresa non sono stati
trovati affatto: erano due situazioni diverse che dicevano la stessa cosa.

La conversione è conservativa: `s-log3-cine` → `S-Gamut3.Cine/S-Log3`,
`s-log3` + `s-gamut3` → `S-Gamut3/S-Log3`, e un profilo non logaritmico resta tale,
così una clip Rec.709 continua a lasciare il nodo neutro.

### Data level: un S-Log3 visto dall'XML non è più «Video»

`FULL_SCALE_XML_GAMMAS` confrontava per uguaglianza esatta, ma le Cinema Line
scrivono `s-log3-cine`, che nel set non c'era: si finiva su **Video**, il contrario
di quello che la tabella dello stesso modulo dichiara per l'S-Log3. Ora al nome
dell'XML si applica la stessa clausola permissiva del nome RTMD.

### La lettura non blocca più il pannello, e insiste di più quando serve

Il lettore gira sul thread interfaccia di Resolve e aveva un solo tentativo da 8
secondi. Ora i tentativi sono tre, con budget crescenti: **2, 8 e 20 secondi**. Il
primo copre il caso normale su disco locale senza che il pannello si senta; i
successivi scattano **solo** dopo un timeout, che è il caso della presa lunga su
unità esterna. Un fallimento pulito — un file che non è Sony — resta definitivo al
primo colpo: riprovarlo tre volte bloccherebbe il pannello mezzo minuto per
arrivare alla stessa risposta.

### Verifica

- **252 test**, tutti verdi.
- Il C++ in float32 coincide con il riferimento Python in float64 su **tutta** la
  corsa di ogni controllo: il fuzz andava a metà scala, adesso va da estremo a
  estremo.
- La clip che ha fatto emergere il difetto di scansione è di decine di gigabyte e non
  esiste una copia. Quello che conta di lei è la sua **forma**, e
  `tests/mxf_fixture.py` la scrive in pochi megabyte: partition pack, index table che
  spinge l'essenza oltre i 4 MiB, elemento ANC Sony vero e Random Index Pack in coda.
  Il payload decodifica esattamente i valori attesi — 5600 K, tint 15,17, EI 800,
  ISO 12800, S-Gamut3.Cine/S-Log3 — quindi i test provano il parser, non un mock.
- `docs/tone_curve.png` ha due strisce nuove: la stessa rampa blu attraverso il
  vecchio stadio — culmina a +2 stop e poi **scende** da 0,82 a 0,34 — e attraverso
  questo, monotona fino in cima.

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
