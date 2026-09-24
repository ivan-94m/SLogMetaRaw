# Graphify — S-Log MetaRaw (dev, non pubblicata)

Mappa strutturale del codice per orientarsi rapidamente. Rigenerare quando
cambiano moduli, import o il confine Python/OFX.

- Versione in sviluppo: `1.1.0` (branch `claude/trusting-dijkstra-3g2722`)
- Ultima versione pubblicata (RELEASE_NOTES.md): `1.1.0`
- Rigenerato: 2026-09-24, commit base `b5e59c2`

## Due sottosistemi

```
DaVinci Resolve
  ├─ Scripts > Utility            OFX Node (SLogMetaRaw.ofx)
  │  resolve_script/SLogMetaRaw.py   ofx/SLogMetaRaw/SLogMetaRaw.cpp
  │        │ sys.path.insert(LIB_DIR)      │ legge plugin_cache JSON
  │        ▼                               │ bottone "Rileggi" → spawn:
  │  slogmetaraw/ui.py (finestra)           python3 -m slogmetaraw --to-resolve
  │        │ Popen --helper                 │
  │        ▼                               ▼
  │  slogmetaraw/__main__.py  ───────────────────────────────┘
  │        │
  │        ▼
  │  slogmetaraw/extract.py (read_clip)
  │        │
  │        ├─ codec.py    (SPS H.264/HEVC)
  │        ├─ datalevel.py(range/scala)
  │        ├─ mp4.py      (reader ISO-BMFF)
  │        ├─ mxf.py      (reader MXF + ANC)
  │        ├─ nrt.py      (XML NonRealTimeMeta)
  │        └─ rtmd.py     (decoder payload 'rtmd')
  │
  │  slogmetaraw/ui.py usa anche:
  │        ├─ resolve_io.py  (scrive nel Media Pool)
  │        ├─ plugin_cache.py(scrive JSON per il nodo OFX) ─┐
  │        ├─ camera.py      (tabelle gamut/tone, condivise │
  │        │                  con ofx/DevelopMath.h)        │
  │        ├─ i18n.py        (traduzioni finestra)           │
  │        ├─ osx_utils.py   (bounds finestre/schermo)        │
  │        └─ update.py      (check GitHub Releases)           │
  │                                                              │
  └── ~/Library/.../SLogMetaRaw/cache/<fnv1a64(path)>.json ◄─────┘
```

## Nodi (moduli) e scopo — una riga

| Modulo | Scopo |
|---|---|
| `slogmetaraw/__init__.py` | Entry point pacchetto: espone `read_clip`, `DatalessError`, `find_sidecar`. |
| `slogmetaraw/__main__.py` | CLI e modalità interne `--helper` / `--to-resolve`. |
| `slogmetaraw/extract.py` | Orchestratore: unisce codec+datalevel+mp4+mxf+nrt+rtmd in un solo `read_clip()`. |
| `slogmetaraw/rtmd.py` | Decoder del payload acquisizione Sony `rtmd` (comune a MP4 e MXF). |
| `slogmetaraw/mp4.py` | Reader ISO-BMFF minimale (solo box header + box necessari). |
| `slogmetaraw/mxf.py` | Reader MXF: ANC packet (ST 436) + NRT XML embedded. |
| `slogmetaraw/nrt.py` | Parser XML NonRealTimeMeta (sidecar `*M01.XML` o embedded). |
| `slogmetaraw/codec.py` | Parsing SPS H.264/HEVC (profilo, livello, VUI). |
| `slogmetaraw/datalevel.py` | Calcolo range dati (Full/Video) e correzione da applicare. |
| `slogmetaraw/camera.py` | Tabelle gamut/as-shot — specchio di `ofx/SLogMetaRaw/DevelopMath.h`. |
| `slogmetaraw/resolve_io.py` | Scrive i risultati nei metadati del Media Pool di Resolve. |
| `slogmetaraw/plugin_cache.py` | Scrive/legge la cache JSON per-clip letta dal nodo OFX. |
| `slogmetaraw/connect.py` | Connessione al server di scripting Resolve, scrittura singola clip. |
| `slogmetaraw/ui.py` | Finestra script (Workspace > Scripts), orchestratore lato UI. |
| `slogmetaraw/i18n.py` | Traduzioni finestra (segue la lingua di Resolve). |
| `slogmetaraw/osx_utils.py` | Helper macOS: bounds display/finestre. |
| `slogmetaraw/update.py` | Check versione contro le GitHub Releases del progetto. |
| `resolve_script/SLogMetaRaw.py` | Launcher installato in Fusion/Scripts/Utility; avvia `ui.py`. |
| `ofx/SLogMetaRaw/SLogMetaRaw.cpp` | Nodo OFX: parametri, rendering, legge cache, spawn `--to-resolve`. |
| `ofx/SLogMetaRaw/DevelopMath.h` | Sviluppo log→lineare, data level, tone mapping (Metal/CPU). |
| `ofx/SLogMetaRaw/MetalKernel.mm` | Kernel GPU (Metal) per il rendering del nodo. |
| `tools/build_math.py` | Genera `DevelopMathSource.inc` da `DevelopMath.h` per l'embedding Metal. |
| `tools/gamut_matrices.py` | Genera le matrici gamut usate da `camera.py` / `DevelopMath.h`. |

## Note per la manutenzione

- `camera.py` e `DevelopMath.h` devono restare sincronizzati manualmente
  (stessi codici gamut/transfer); non c'è un solo generatore per entrambi.
- Il confine tra i due sottosistemi è solo su disco: JSON di `plugin_cache.py`
  in lettura, e uno spawn di processo Python (`--to-resolve`) in scrittura.
- `extract.py` è il punto di ingresso da cui *tutte* le sorgenti metadati
  passano: aggiungere un nuovo formato camera significa aggiungere un reader
  e collegarlo lì.
