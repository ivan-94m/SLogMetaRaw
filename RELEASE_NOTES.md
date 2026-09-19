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
