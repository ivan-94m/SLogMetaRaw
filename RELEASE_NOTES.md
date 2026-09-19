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
