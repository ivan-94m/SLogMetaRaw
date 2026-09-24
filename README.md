<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Sony camera metadata and scene-referred development controls for DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<b>English</b> · <a href="README.it.md">Italiano</a> · <a href="README.es.md">Español</a> · <a href="README.pt.md">Português</a> · <a href="README.zh.md">简体中文</a>
</p>

---

## What it is

Sony cameras write the shooting setup into every file: white balance in Kelvin, tint, EI, lens, aperture, shutter,
colour profile. Resolve uses that data for the MXF files of an FX6 or FX9, which get a *Camera Raw* panel. For the MP4
files of an FX30, FX3, a7 or a6000-series camera it ignores the data.

S-Log MetaRaw reads that data and uses it. It has three parts:

| | Where | What it does |
|---|---|---|
| **Script** | Workspace › Scripts › S-Log MetaRaw | reads the metadata of every clip in the project and writes it into the Media Pool |
| **S-Log MetaRaw** node | Color › OpenFX | develops one clip from its as-shot values: white balance, exposure, colour space, tone by zones, false colour |
| **S-Log MetaRaw Detail** node | Color › OpenFX | the creative node: local tone recovery, Texture, Clarity, Dehaze |

No file is transcoded and no original file is ever written.

### What to expect, honestly

**It is not raw.** A log MP4 is already demosaiced, compressed, 8 or 10 bit, often 4:2:0, with the camera's noise
reduction baked in. No plugin can bring back what the camera threw away.

What the node does is apply colour science carefully. Exposure and white balance act in linear light, starting
from the values the camera recorded and following published curves and gamuts. Tone moves the image in stops. Worked this way, a log image
**behaves in a way that reminds you of a raw file**: white balance shifts cleanly, exposure moves like a stop of light,
and highlights roll off instead of breaking.

On heavy work, colour science alone is not enough. As soon as you push past what the camera captured, the missing
information shows: banding in skies, noise in lifted shadows, clipped highlights that stay clipped, and colour that
comes apart in the compressed channels. Expose well at the camera. S-Log MetaRaw helps you get the most out of what
is there. It cannot create what is not there.

---

## Install

1. Download `SLogMetaRaw-2.0.0.dmg` from **Releases** and open it.
2. Double-click **Installa S-Log MetaRaw.pkg**. It is not signed with an Apple certificate: the first time,
   right-click it and choose **Open**. It asks for the Mac password because the plugin goes in a system folder.
3. Restart DaVinci Resolve.

The installer also deletes Resolve's plugin cache (`OFXPluginCacheV2.xml`), which Resolve rebuilds on its next start.
Without that step Resolve would keep showing the old panel and would not list the Detail node.

| Installed | Path |
|---|---|
| The two nodes (one bundle) | `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` |
| The Python library | `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` |
| The menu script | `…/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` |

While it runs it keeps a small JSON record per clip in `~/Library/Application Support/SLogMetaRaw/cache`. The disk image
also holds the three-page guides in Italian and English.

**Clean install and uninstall.** Every install starts clean: the installer replaces the previous plugin and library
entirely and removes developer installs, so no file from an older version stays behind. **Disinstalla S-Log
MetaRaw.command**, on the disk image (the first time: right-click › Open), removes every version ever installed, 1.x and
2.x included, with the cache, settings and logs. It lists everything before touching it, asks you to close Resolve, and
asks before deleting your CSV exports. The metadata already written into Resolve projects is part of the projects and
stays.

**Requirements:** macOS 12 or later, Apple silicon or Intel, and DaVinci Resolve 21. **Tested only on Resolve Studio 21.1
on macOS.**

**Clips:** Sony XAVC in `.MP4` or `.MXF`. The script reads any of them. The nodes develop **S-Log3** (S-Gamut3.Cine or
S-Gamut3), **S-Log2** and **S-Log** (S-Gamut). With any other profile they stay neutral and say so.

---

## Quick start

1. Import the footage. **Workspace › Scripts › S-Log MetaRaw**: press **1 · Read metadata**, then **2 · Write to Resolve**.
2. On the Color page, put **S-Log MetaRaw** as the **first node**. It picks up the clip's EI, Kelvin and tint. At those
   values it changes nothing.
3. Fix white balance and exposure in the node. The false colour views help.
4. Shape the tones with **Toni** (Tones). For local recovery, Texture, Clarity or Dehaze, add **S-Log MetaRaw Detail** as the
   next node.
5. Then add your CST, LUT or DRT.

```
S-Log MetaRaw  →  S-Log MetaRaw Detail  →  CST / LUT / DRT  →  the rest of the grade
```

---

## The script

The window has one row of buttons, one row of options and the clip list. It follows Resolve's language (English,
Italian, Spanish, Portuguese, Simplified Chinese). The nodes' panels are in Italian: below, their labels come with a
translation.

- A menu picks the clips: *Whole Media Pool* or *Selected clips in the Media Pool*.
- **1 · Read metadata**: one row per clip with camera, lens, aperture, shutter, EI, WB, colour space and data level.
  The *Status* column says `read`, what changed during the take (aperture, focus…), or why a clip was
  skipped. Click a row to see everything that was read, grouped as in Catalyst Browse.
- **2 · Write to Resolve**: fills the Media Pool fields (Metadata panel, columns, keywords for smart bins,
  data burn-in) and fixes values Resolve reads wrong from MXF, such as *Camera Aperture* `F53343` on the FX6.
- **Export CSV**: exports the values Resolve has no field for (EI, tint, WB mode, focus distance, capture gamma…) in Resolve's own
  metadata CSV format.
- Options:
  - **Camera tag** (off): adds camera, gamma and primaries to the keywords.
  - **Overwrite metadata** (on): replaces values Resolve already filled in; off, it fills only the empty fields.
  - **Correct the Data Level** (on): sets each clip's *Data Level* to Full or Video, whichever its gamma needs.
    [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) explains why.
  - **Also set Input Color Space** (off): for colour-managed projects.
    A script cannot put this back to *Project*: only you can, by hand.
- The version at the bottom right checks GitHub when clicked.

Reading is quick because nothing is decoded: at most 24 samples of the metadata track per clip, with a one-second budget.
A volume that stops answering is skipped once, with a message, instead of blocking the list.

---

## The S-Log MetaRaw node

The node is pointwise: each pixel depends only on itself. It never makes halos, and **Generate LUT** can export it
(65 points recommended).

| Control | What it does |
|---|---|
| **Version** (top) | `v2.0.0`. Once a day it asks GitHub for the latest release. If there is one it reads **🟢 v2.0.0 → 2.x.y**, and a click opens the DMG download in the browser. It never installs anything itself |
| **Camera** · **Rileggi metadata** | the camera that was read. *Rileggi* re-reads the clip, sets every control back to the camera values and writes the clip's metadata into the Media Pool |
| **Decode Using** | *Clip* lets you change the controls; *Camera metadata* locks them to the as-shot values |
| **White Balance** · **Color Temp** · **Tint** | As shot or presets. Bradford chromatic adaptation in linear light, from the white the camera recorded |
| **Exposure** | exposure index: double the EI is +1 stop |
| **False color** | temperature, tint and exposure; see below |
| **Color Space** · **Gamma** | output, like a Color Space Transform; *Timeline* does not convert |
| **Toni** (Tones) | Contrast, Highlights, Shadows, Whites, **Bianco** (white, in stops), Blacks, Vibrance, Saturation (−100…+100) |
| **Zone** (Zones, closed) | Black, Shadow, Light and Specular zones with Exp (stops), Sat, Range and Falloff; Contrast Pivot; Soft Clip; *Zone* false colour |
| **Avanzate** (Advanced) | node input, data-level correction, status, **Sblocca controlli senza metadata** (unlock without metadata) |
| **Dati di ripresa** (shooting data) | read only: lens, focal length, aperture, focus, shutter, EI, WB, fps, ND, camera LUT |

**Highlights is a film shoulder.** Pulled down, it compresses the highlights with a slope that falls smoothly towards the
top, the way film, ACES 2.0 and AgX do. At −100 the brightest value the camera recorded (about +6 stops over grey in
S-Log3) lands exactly on **Bianco**: no grey veil and no clip. Grey and everything below stay put, and skin at +1 stop moves
by 0.05 stops at most. The most compressed highlights drift gently towards white without changing hue. Pushed up, it gives
the highlights more snap, with a bounded slope. **Bianco** is where that top lands (and Soft Clip's roof): 2.5 stops is
Rec.709 white through a plain CST without tone mapping. With a DRT after the node (ACES, AgX, DaVinci), raise it to 4–5,
or the highlights are compressed twice.

**Tones by zones.** Shadows, Whites and the Zones are exposure changes, in stops, over a range of tones: Shadows below
−1 stop, Whites from +3.5 stops. Blacks is a linear veil that moves black without moving grey. Inside a zone the image moves
like an exposure, so texture is kept, and the compression sits in a declared transition band. No combination of sliders can
solarise. The honest cost of a pointwise node: whatever it compresses, it compresses the texture too. That is why local
recovery is a separate node. Formulas and recipes: [docs/TONE_MAPPING.md](docs/TONE_MAPPING.md).

**False colour.** One view per control, above the slider it serves:
- **Exposure** uses ARRI-style bands on the stops around 18% grey. Green is middle grey, pink is one stop over (skin),
  yellow is near clip, red is clipped, and blue and purple are the bottom.
- **Temperature** and **Tint** work as in CineMatch. The picture turns grey, casts show in orange/blue or green/magenta,
  and near-neutral casts are boosted up to 8× so they show. Move the slider until what should be neutral stays grey.
  Each view reacts only to its own slider.

The view replaces the image. Turn it off before you render. [docs/FALSE_COLOR.md](docs/FALSE_COLOR.md)

**Data level.** If Resolve decodes a clip on the wrong code-value scale, the node corrects it before the log curve.
The script's *Correct the Data Level* option fixes it for the whole project. [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)

**Without metadata.** A ProRes from an external recorder, or a clip that cannot be read, leaves the node neutral. Tick
*Avanzate › Sblocca controlli senza metadata* and type the shooting EI, Kelvin and tint: the controls come alive, and
the node starts neutral.

**Speed.** Opening a project does not read any file. Opening the panel waits at most half a second; a slow disk
finishes in the background, with a 15-second limit. *Rileggi* answers within about 2 seconds.

---

## The S-Log MetaRaw Detail node

This is the creative node. It works **by areas**, over an edge-aware base, and adjusts large areas without flattening
the fine detail. That is the part of Lightroom's Highlights and Shadows a pointwise node cannot copy.

| Group | Controls |
|---|---|
| **Gamma dinamica** (dynamic range) | Local Contrast, Local Highlights, Local Shadows; *gain* and *base* views. Local Highlights compresses the large bright areas and keeps, even strengthens, the fine texture: a sky gets deeper and its clouds keep their detail. The main node's Highlights instead softens highlight texture, like film |
| **Presenza** (presence) | Texture, Clarity, Dehaze |
| **Zone locali** (local zones) | the main node's zones, applied to the areas |
| **Avanzate** (advanced) | detail preservation, radius, edge and noise thresholds, Clarity centre, **Bianco** for Local Highlights, node input |
| **Velo** (haze) | the level and colour of the haze Dehaze removes: you set them, they are never guessed frame by frame |

- Place it **right after** S-Log MetaRaw, before CST, LUT or DRT. It decodes what it receives to linear light and writes it
  back in the same encoding, so it must sit before any conversion: keep the main node's Color Space and Gamma on Timeline.
- It is **spatial**, so Generate LUT leaves it out, together with the rest of its node. Keep it in a node of its own.
- The radii follow the frame height. The look is the same at full resolution, in proxy and in the viewer. No per-frame
  statistics, so no flicker.
- On Metal a UHD frame takes about 6–18 ms, measured on Apple silicon. The CPU fallback is much slower.

**Its limits, measured.** With Local Highlights −100 the halo on the dark side of an edge stays under 3% of the step. With
Local Shadows or the local zones at ±100, on a hard one-stop edge the halo reaches about 12% of the step, and 4–6% on 2–3 stop
edges. If you see one, lower *Soglia bordi* (edge threshold). Texture does not raise grain below the noise threshold,
but next to strong edges grain can grow 1.25–1.7×. Dehaze needs a real haze to remove. [docs/DETAIL.md](docs/DETAIL.md)

---

## Updates and privacy

- The **nodes** ask GitHub for this project's latest release at most once a day, in the background. The request
  carries only the program version (`User-Agent: SLogMetaRaw/2.0.0`). To turn it off, create the empty file
  `~/Library/Application Support/SLogMetaRaw/no_update_check`.
- The **script** checks only when you click its version.
- A click only opens a download link from this project's GitHub releases. Nothing is installed without you.

---

## How it works, in short

- **Metadata.** The parsers are pure Python, with no dependencies. They read the per-frame SMPTE RDD 18 acquisition
  metadata (MP4 `rtmd` track, MXF ST 436 packets), Sony's NonRealTimeMeta XML, the H.264/HEVC SPS and the MXF picture
  descriptor. A multi-gigabyte clip costs about 100 KB of reading.
- **From the script to the node.** Each clip gets a JSON record in the cache. The node finds its file through Resolve's
  source path, reads that record, and creates it in the background when it is missing.
- **Colour maths.** The chain is: decode the camera curve, apply the EI ratio, apply Bradford white balance from the Planckian locus
  (with tint perpendicular to it in CIE 1960 uv), then tone with one gain per pixel from a norm of its channels (so
  chromaticity is kept), then colour, then output. Everything is in linear light, with Sony's published curves and gamuts.
- **One maths, three implementations.** The maths lives in `ofx/SLogMetaRaw/math` and compiles both as C++ and as
  Metal. A Python reference model checks both: CPU and GPU agree within 2·10⁻⁴, with FMA disabled on every path.
- **Tests.** 322 automated tests: parsers, reference models, C++, Metal, a miniature OpenFX host that loads both
  nodes the way Resolve does, and golden files of the panels.

---

## Building from source

```bash
make -C ofx/SLogMetaRaw                     # universal plugin, arm64 + x86_64 (needs Xcode)
make -C ofx/SLogMetaRaw test-bins           # test binaries
python3 -m unittest discover tests          # the test suite
./install.sh --dev                          # script and plugin pointing at this folder
./packaging/build_installer.sh              # dist/SLogMetaRaw-<version>.dmg
python3 -m slogmetaraw clip.MP4             # Catalyst-style readout from the command line
```

```
slogmetaraw/         parsers, Resolve writing, the script window, update check
resolve_script/      launcher for Workspace › Scripts
ofx/SLogMetaRaw/     math/ (shared CPU/Metal), src/ (common, develop, detail), metal/
tools/               generators for matrices, icons and charts
tests/               tests and reference models (the sample clips are not in the repository)
packaging/           installer, guides, uninstaller
docs/                TONE_MAPPING, DETAIL, FALSE_COLOR, DATA_LEVELS
```

---

## Known limits

- Resolve's own Camera Raw panel and gyro stabilisation cannot be unlocked for MP4. Both live inside Resolve's
  decoders. S-Log MetaRaw rebuilds the colour controls. It does not open a door into Resolve.
- Some cameras (the a6300 among them) do not record a Kelvin value. It is then estimated from the lighting preset and flagged.
- S-Log2 follows the Sony paper. Resolve's own S-Log2 curve differs by about 0.15 stop.
- Still to be checked on more files: XAVC HS (HEVC), HLG, S-Cinetone, power zooms.
- **An independent hobby project**, distributed as is, with no warranty and no liability for professional use. The
  code is open: read it, test it, change it.

---

## Credits and licence

**Ivan Mazzone + Claude** · [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).
Written with Claude (Anthropic): 1.0 on 19 September 2026, 1.1.0 on 22 September, 2.0.0 on 23 September 2026. The full
history is in [RELEASE_NOTES.md](RELEASE_NOTES.md) (in Italian).

Sony tag references: SMPTE RDD 18, [ExifTool](https://exiftool.org) and
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) by AdrianEddy (MIT), from which part of the tag table
comes.

[GNU GPL v3.0 or later](LICENSE). The OpenFX SDK is © The Open Effects Association (BSD-3). Sony, XAVC and Catalyst are
trademarks of Sony Group Corporation; DaVinci Resolve is a trademark of Blackmagic Design. This is an independent project,
not affiliated with or endorsed by either company.
