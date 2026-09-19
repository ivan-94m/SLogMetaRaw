<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadata Sony e controlli Camera Raw per DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

---

## Premessa

Con la scienza del colore e i metadata di ripresa possiamo intervenire sui parametri essenziali delle mirrorless Sony — bilanciamento del bianco, esposizione, spazio colore e curva — **come se fossero file raw**. Dove è possibile, e solo con i profili log (S-Log2 / S-Log3).

## Il problema

DaVinci Resolve legge i dati di ripresa Sony (ISO, bilanciamento del bianco, diaframma, focale…) solo dai file **MXF** di FX6/FX9 e abilita il pannello **Camera Raw › Sony Video** solo per quelli. Gli **MP4** di FX30, FX3, Alpha e a6300 contengono gli stessi dati, ma Resolve li ignora. Catalyst Browse invece li legge.

S-Log MetaRaw porta quei dati dentro Resolve, senza transcodificare né toccare i file originali.

| | |
|---|---|
| **Script S-Log MetaRaw** | Estrae i metadata di **tutte le clip del progetto in una volta sola** (o solo di quelle selezionate) e li registra nel Media Pool: pannello Metadata, colonne, keyword per le smart bin, data burn, export CSV. Mostra tutti i dati letti, come Catalyst Browse, e corregge i campi che Resolve legge male sugli MXF, come *Camera Aperture "F53343"* sull'FX6. |
| **Plugin S-Log MetaRaw** (OpenFX) | Gestione della singola clip come se avessi il pannello Raw sotto mano: Color Temp, Tint, Exposure (EI), White Balance, Color Space/Gamma e toni. **Si imposta da solo** con i valori di ripresa della clip e la interpreta come è stata registrata. |

## Installazione

1. Scarica `SLogMetaRaw-x.y.z.dmg` dalla pagina **Releases** e aprilo.
2. Doppio clic su **Installa S-Log MetaRaw.pkg**. L'installer non è firmato con un certificato Apple, quindi al primo avvio fai tasto destro › **Apri**.
3. Riavvia DaVinci Resolve.

Nel disco ci sono anche le guide di una pagina, **Guida S-Log MetaRaw (italiano).pdf** e **S-Log MetaRaw Guide (english).pdf**, e **Disinstalla S-Log MetaRaw.command**.

Requisiti: macOS 12 o successivo (Apple Silicon o Intel) e DaVinci Resolve 21. **Testato solo su Resolve Studio 21.1 su macOS.** Sulle versioni precedenti non è stato provato: lo script potrebbe funzionare (con Python 3 installato, perché Resolve include il proprio interprete solo dalla 21.1), mentre il plugin usa funzioni introdotte con Resolve 21, come la gestione colore OpenFX 1.5, e lì va impostato a mano *Avanzate › Ingresso nodo*.

## Come si usa

1. **Importa** il girato nel Media Pool.
2. **Workspace › Scripts › S-Log MetaRaw**: premi *Leggi metadata*, poi *Scrivi in Resolve*. Cliccando una clip vedi tutti i dati, divisi nelle sezioni di Catalyst Browse.
3. **Pagina Color**: applica **OpenFX › S-Log MetaRaw** come primo nodo, prima di CST e LUT. Il nodo mostra la camera e porta Color Temp, Tint ed Exposure ai valori di ripresa; a quei valori è neutro. Se copi il nodo su un'altra clip, si reimposta con i dati di quella clip.

| Controllo | Funzione |
|---|---|
| Decode Using | *Clip* usa i controlli; *Camera metadata* torna alla ripresa e ingrigisce i controlli |
| White Balance | *As shot*, preset (Daylight, Cloudy, Shade, Tungsten, Fluorescent, Flash); muovendo gli slider diventa *Custom* |
| Color Temp · Tint | bilanciamento in luce lineare, con adattamento cromatico Bradford dal bianco di ripresa |
| Exposure | in EI: EI doppio = +1 stop |
| Color Space · Gamma | come un Color Space Transform. Il default *Timeline* non converte; le altre scelte convertono (Rec.709, Gamma 2.4, S-Log3, ACES…) |
| Shadows, Highlights, Color Boost, Saturation, Contrast | ritocchi di tono e colore |
| Avanzate › Dati di ripresa | obiettivo, focale, diaframma, fuoco, shutter, ISO/EI, WB, data level, fps (S&Q), ND, LUT di camera |

## Come funziona

- **Dove sono i dati.** Nei file Sony XAVC i dati di ripresa sono per ogni frame:
  - negli **MP4**, nella traccia di metadata temporizzati `rtmd`;
  - negli **MXF**, in pacchetti ANC SMPTE ST 436 (DID 0x43/SDID 0x05).

  In entrambi i casi il formato è KLV con i set di acquisizione **SMPTE RDD 18**, più tag Sony. A questi si aggiungono l'XML *NonRealTimeMeta* (sidecar `M01.XML` o copia incorporata) e l'SPS H.264/HEVC (profilo, bit depth, range). Il parser legge solo l'indice del file e pochi frame: circa 100 KB anche da file di vari GB.
- **Scrittura in Resolve.** Lo script usa l'API di scripting di Resolve 21.1 (Python 3.14 incluso in Resolve). Ogni clip riceve una scheda JSON in `~/Library/Application Support/SLogMetaRaw/cache`.
- **Lettura nel plugin.** Il plugin conosce il file della clip grazie all'estensione Resolve `kOfxImageEffectPropSrcFilePath` e legge quella scheda. Se manca, la genera da solo con `ResolvePython -m slogmetaraw --cache`. Lo spazio colore del nodo lo riceve da Resolve tramite la gestione colore OpenFX 1.5.
- **Calcoli.** Il plugin lavora in luce lineare: esposizione come rapporto EI/EI di ripresa, bilanciamento con von Kries in LMS Bradford dal bianco di ripresa (luogo di Planck più tint). Le curve seguono le specifiche ufficiali: S-Log2/S-Log3 dai paper Sony, DaVinci Intermediate, ACEScct, Rec.709, sRGB. Il render gira su **Metal** (kernel compilato a runtime) con fallback CPU.
- **Verifiche.** Etichette e valori sono stati confrontati campo per campo con Catalyst Browse su FX6, FX30 e a6300. Anche la matematica è verificata: il modello Python, la versione C++ e il kernel Metal coincidono entro 2·10⁻⁴, e i test di esportazione LUT dentro Resolve hanno confermato gli stessi calcoli (errore < 0,0003).

## Compilare dal sorgente

```bash
make -C ofx/SLogMetaRaw                     # plugin universale arm64 + x86_64 (serve Xcode)
./install.sh --dev                          # installa script e plugin puntando a questa cartella
python3 -m unittest discover -s tests       # test (parser, modello, C++, Metal)
./packaging/build_installer.sh              # crea dist/SLogMetaRaw-x.y.z.dmg
python3 -m slogmetaraw cartella_o_file      # vista stile Catalyst da riga di comando
```

```
slogmetaraw/         parser (mp4, mxf, rtmd, nrt, codec), scrittura Resolve, finestra dello script
resolve_script/      launcher per Workspace › Scripts
ofx/SLogMetaRaw/     plugin OpenFX (C++, Metal); DevelopMath.h è generato da tools/build_math.py
tools/               matrici dei gamut, generatori, icone
tests/               test (i clip di esempio non sono nel repository)
packaging/           installer: pacchetto, guida PDF, disinstallatore
```

## Limiti noti

- Il **vero** pannello Camera Raw e la **stabilizzazione con giroscopio** nativi di Resolve non si possono attivare sugli MP4: dipendono dal decoder interno di Resolve (Sony solo per gli MXF, giroscopio solo per Blackmagic). SLogMetaRaw è l'equivalente per i controlli colore.
- Servono profili **S-Log2 o S-Log3**; con altri profili il nodo resta neutro.
- Alcune camere non registrano la temperatura colore (per esempio l'a6300): il valore viene stimato dal preset e segnalato.
- **S-Log2:** la formula segue il paper Sony (18% = codice 347). La curva S-Log2 installata con Resolve differisce di circa 0,15 stop.
- Da validare con altri file: XAVC HS (HEVC), HLG/S-Cinetone, zoom motorizzati, GPS.
- **Progetto hobbistico e indipendente**, distribuito così com'è, senza garanzie e senza alcuna responsabilità per l'uso in contesti professionali. Il codice è aperto: chiunque può verificarlo, provarlo e modificarlo.

## Crediti

**Ivan Mazzone + Claude** — [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).

Riferimenti per i tag Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) (Sony.pm) e [telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) di AdrianEddy (MIT). Parte della tabella dei tag deriva da quest'ultimo.

Sony, XAVC e Catalyst sono marchi di Sony Group Corporation; DaVinci Resolve è un marchio di Blackmagic Design. Progetto indipendente, non affiliato né approvato da nessuna delle due aziende.

## Licenza

[GNU General Public License v3.0 o successiva](LICENSE). Software libero: puoi usarlo, studiarlo, modificarlo e
ridistribuirlo; chi lo ridistribuisce, anche modificato, deve farlo con la stessa licenza e con il codice sorgente
disponibile. Nessuna garanzia di alcun tipo.

L'OpenFX SDK è di The Open Effects Association (BSD a 3 clausole) e parte della tabella dei tag Sony deriva da
telemetry-parser (MIT): entrambe compatibili con la GPL-3.

---

### English

**S-Log MetaRaw** brings Sony camera metadata into DaVinci Resolve 21 without transcoding. It reads the per-frame `rtmd` / RDD 18 acquisition metadata from XAVC MP4 and MXF files, so white balance, exposure and colour space start from the values the camera recorded. A **Resolve script** writes the metadata into Media Pool fields. **SLogMetaRaw** is an OpenFX node for the Color page that emulates the *Camera Raw › Sony Video* controls (Color Temp, Tint, Exposure/EI, White Balance presets, Color Space/Gamma as a CST) and **sets itself to each clip's as-shot values**. It runs in linear light on Metal. macOS 12+, Resolve 21.1. Hobby project, provided as is, no warranty. Licensed under the GNU GPL v3 or later. By Ivan Mazzone + Claude (github.com/ivan-94m, @ivan_94m). Tested only on Resolve Studio 21.1 (macOS).
