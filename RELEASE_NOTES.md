# Changelog

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
