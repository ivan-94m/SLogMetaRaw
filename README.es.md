<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadatos de cámara Sony y controles tipo Camera Raw para DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <a href="README.it.md">Italiano</a> · <a href="README.zh.md">简体中文</a> · <b>Español</b> · <a href="README.pt.md">Português</a>
</p>

---

## La idea

La cámara ya grabó cómo estaba ajustada la toma: balance de blancos en kelvin, tinte, EI, óptica, obturador, perfil de
color. En los archivos MXF de una FX6, Resolve usa esa información y abre el panel **Camera Raw › Sony Video**. En los
MP4 de una FX30, una FX3 o una a6300 esa misma información está dentro del archivo, y Resolve la ignora.

S-Log MetaRaw la lee y la vuelve a poner a trabajar: balance de blancos, exposición y espacio de color parten de lo que
grabó la cámara en lugar de una suposición. No se transcodifica nada y jamás se escribe en los archivos originales.

No es raw. Un MP4 log es una imagen ya revelada y comprimida, y ningún plugin puede deshacer eso. Lo que sí puede hacer
es retomar las decisiones tomadas en rodaje —las que el raw te dejaría revisar— sobre la imagen que realmente se grabó,
en luz lineal y con ciencia del color publicada.

| | |
|---|---|
| **Script** (Workspace › Scripts) | Lee los metadatos de **todos los clips del proyecto de una vez**, o solo de los seleccionados, y los escribe en el Media Pool: panel Metadata, columnas, palabras clave para las smart bins, data burn-in, exportación CSV. Muestra todo lo que ha leído, agrupado como lo agrupa Catalyst Browse, y corrige campos que Resolve rellena mal en los MXF, como *Camera Aperture* marcando `F53343` en la FX6. |
| **Plugin** (OpenFX, página Color) | Un clip a la vez, como si tuvieras el panel Raw a mano: Color Temp, Tint, Exposure (EI), White Balance, Color Space/Gamma y tonos. **Se configura solo** con los valores de rodaje de ese clip y, en esos valores, es neutro: mientras no muevas nada, no cambia nada. También corrige el **nivel de datos** cuando Resolve lee el clip en la escala equivocada, revela las altas luces con un **hombro fílmico** que nunca recorta y trae tres vistas de **falso color** para situar exposición y balance midiendo en vez de a ojo. |

---

## Instalación

1. Descarga `SLogMetaRaw-x.y.z.dmg` desde la página **Releases** y ábrelo.
2. Haz doble clic en **Installa S-Log MetaRaw.pkg**. El instalador no está firmado con un certificado de Apple, así que
   la primera vez hay que abrirlo con clic derecho › **Abrir**.
3. Reinicia DaVinci Resolve.

El instalador coloca exactamente tres cosas:

| Ruta | Qué |
|---|---|
| `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` | el nodo OpenFX |
| `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` | la biblioteca de Python (los parsers) |
| `…/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` | la entrada de menú del script |

Durante el uso también escribe una pequeña ficha JSON por clip en `~/Library/Application Support/SLogMetaRaw/cache`, y
las exportaciones CSV van a `~/Documents/SLogMetaRaw`. **Disinstalla S-Log MetaRaw.command**, en el disco, lo elimina
todo. En el disco están además las guías de una página, **S-Log MetaRaw Guide (english).pdf** y
**Guida S-Log MetaRaw (italiano).pdf**.

**Requisitos:** macOS 12 o posterior (Apple Silicon o Intel) y DaVinci Resolve 21. **Probado solo en Resolve Studio 21.1
en macOS.** Las versiones anteriores no se han probado: el script podría funcionar si tienes Python 3 instalado (Resolve
incluye su propio intérprete solo a partir de la 21.1), mientras que el plugin depende de funciones introducidas con
Resolve 21 —sobre todo la gestión de color de OpenFX 1.5—, así que allí habría que ajustar a mano
*Avanzate › Ingresso nodo* (Avanzadas › Entrada del nodo).

**Clips compatibles:** Sony XAVC, `.MP4` o `.MXF`, grabados en **S-Log2 o S-Log3**. Los perfiles que el nodo revela son
`S-Gamut3.Cine/S-Log3`, `S-Gamut3/S-Log3`, `S-Gamut/S-Log2` y `S-Gamut/S-Log`. El script lee los metadatos de cualquier
clip Sony XAVC, sea log o no; con lo demás el nodo se mantiene neutro.

---

## Guía

### 1 · El script

**Workspace › Scripts › S-Log MetaRaw.** La ventana tiene tres botones, en el orden en que se usan.

- **Origine** (origen) — *Clip selezionate nel Media Pool* (clips seleccionados), *Bin corrente (con sottocartelle)*
  (bin actual, con subcarpetas) o *Tutto il Media Pool* (todo el Media Pool).
- **1 · Leggi metadata** (leer metadatos) — lee los clips. Todavía no escribe nada. La tabla se llena con una fila por
  clip: Clip, cámara, óptica, focal, diafragma, obturador, ISO/EI, WB, espacio de color, data level y una columna
  *Stato* (estado) que dice `letto` (leído), o `letto · varia: diaframma, fuoco` cuando un valor cambió durante la toma,
  o por qué se omitió un clip. **Al hacer clic en una fila**, el panel inferior muestra todo lo leído, en las mismas
  secciones que usa Catalyst Browse.
- **2 · Scrivi in Resolve** (escribir en Resolve) — escribe los metadatos en el Media Pool.
- **Esporta CSV (campi custom)** (exportar CSV, campos personalizados) — escribe un CSV en `~/Documents/SLogMetaRaw` con
  los valores para los que Resolve no tiene campo (la lista está más abajo).

Dos casillas:

- **Sovrascrivi i campi già compilati** (sobrescribir los campos ya rellenados), activada por defecto. Es la que corrige
  los valores erróneos que Resolve escribe por su cuenta, como *Camera Aperture* `F53343` en los MXF de la FX6. Si la
  desactivas, solo se rellenan los campos vacíos.
- **Correggi il Data Level** (corregir el Data Level), **activada por defecto**. Ajusta el atributo *Data Level* de
  cada clip a Full o Video según la gamma de captura. Es la corrección real: arregla la decodificación para todo el
  proyecto — CST, RCM, monitores de forma de onda, exportaciones — no solo para el nodo, y es reversible. Las curvas
  log de Sony se publican sobre code values sin escalar y necesitan *Full*; Rec.709, Cine y HLG necesitan *Video*.
  En [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) está toda la investigación, cámara por cámara.
- **Imposta anche Input Color Space (RCM) dai metadata** (ajustar también el Input Color Space según los metadatos),
  desactivada por defecto. Útil en un proyecto con gestión de color, pero ojo: una vez fijado desde un script, el valor
  ya no puede devolverse a *Project* por script, solo a mano dentro de Resolve.

Tus archivos originales nunca se modifican: el script solo los lee.

### 2 · El nodo

**Página Color › OpenFX › S-Log MetaRaw**, como **primer nodo**, antes de cualquier CST o LUT. Arriba muestra la cámara y
lleva Color Temp, Tint y Exposure a los valores de rodaje. En esos valores no le hace nada a la imagen: es un punto de
partida, no un look. Si copias el nodo a otro clip, se reconfigura con los datos de ese clip.

| Control | Rango | Por defecto | Qué hace |
|---|---|---|---|
| **Rileggi metadata** (releer metadatos) | — | — | vuelve a leer el clip y devuelve todos los controles a los valores de cámara |
| **Decode Using** | Camera metadata / Clip | Clip | *Camera metadata* fija todo en los valores de rodaje y desactiva los controles; *Clip* te deja modificarlos |
| **White Balance** | As shot · Daylight 5600 K · Cloudy 6500 K · Shade 7500 K · Tungsten 3200 K · Fluorescent 4000 K · Flash 5500 K · Custom | As shot | preajustes; al mover un deslizador pasa a *Custom* |
| **Color Temp** | 2000–15000 K | el de rodaje | adaptación cromática en luz lineal |
| **Tint** | −100 … +100 | el de rodaje | verde/magenta, perpendicular al lugar de Planck |
| **Exposure** | 25–409600 EI (deslizador 50–25600) | el de rodaje | índice de exposición: el doble de EI equivale a +1 paso |
| **False color: temperatura / tint / esposizione** | activado · desactivado | desactivado | una vista de medición por control, cada una encima del deslizador al que sirve. La de exposición divide en bandas los pasos alrededor del gris 18% al estilo ARRI; las dos de balance leen la distancia al neutro **en kelvin y en unidades de tinte**, así que la banda dice cuánto te falta. Blanco = neutro. Solo una a la vez, y la vista sustituye la imagen: apágala antes de renderizar. [docs/FALSE_COLOR.md](docs/FALSE_COLOR.md) |
| **Color Space** | Timeline · DaVinci WG · Rec.709 · Rec.2020 · P3 D65 · P3 D60 · P3 DCI · S-Gamut · S-Gamut3 · S-Gamut3.Cine · ACES AP0 · ACES AP1 | Timeline | gamut de salida, como un Color Space Transform. *Timeline* no convierte |
| **Gamma** | Timeline · DaVinci Intermediate · Linear · Gamma 2.2 · Gamma 2.4 · Gamma 2.6 · Rec.709 · sRGB · SLog · SLog2 · SLog3 · ACEScct | Timeline | curva de salida. *Timeline* no convierte |
| **Toni › Highlights** | −100 … +100 | 0 | dice, en pasos, **dónde aterriza el techo del contenedor grabado**. En negativo lo prensa hacia una asíntota que nunca alcanza, así que nada recorta, y mueve el gris 18% solo 0,008 pasos. A −100 los +7,74 pasos que un S-Log3 lleva sobre el gris aterrizan exactamente en 1,0 lineal, el pico que admite una señal Rec.709. En positivo hace el espejo: estira el techo de la escala, hasta 2 pasos, para devolver al pico una alta luz que satura antes. El recorrido es **lineal en el deslizador** |
| **Toni › Shadows** | −100 … +100 | 0 | abre o cierra el detalle en sombra alrededor de −4 pasos. Es un multiplicador, así que el negro absoluto sigue siendo negro con cualquier valor |
| **Toni › Color Recovery** | −100 … +100 | 0 | cuánto color devuelve la prensa. Es el peso entre dos maneras de aplicar la misma curva: un único factor sobre los tres canales, que conserva todo el color de escena, y la curva por canal, donde los tres comparten un techo y al subir convergen — porque converger *es* desaturar, que es como lo hace la película. A la derecha conserva el color, a la izquierda va hacia la película. Nunca puede añadir color que el píxel no tenía. [docs/TONE_MAPPING.md](docs/TONE_MAPPING.md) |
| **Toni:** Color Boost, Saturation, Contrast | −100 … +100 | 0 | retoques de color y contraste |
| **Avanzate › Ingresso nodo** (entrada del nodo) | Automatico · DaVinci WG/Intermediate · S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · ACES AP1/ACEScct | Automatico | el espacio de color que entra en el nodo. *Automatico* se lo pregunta a Resolve; cámbialo solo si lo que responde es incorrecto |
| **Avanzate › Data level in ingresso** (nivel de datos de entrada) | Automatico · Full (0-1023) · Video (64-940) · Nessuna correzione | Automatico | la escala de code values con la que Resolve decodificó el clip. *Automatico* usa el atributo Data Level del clip; mientras siga en *Auto* no corrige nada, porque el valor que Resolve usó realmente no es legible desde ninguna API. Decláralo a mano para un archivo que ningún NLE señala bien, como un ProRes de Atomos de la misma toma — ver [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) |
| **Avanzate › Rilevato / Data level / Stato** (detectado / nivel de datos / estado) | — | — | qué se detectó, qué escala se está usando y por qué, y si se encontraron los metadatos |
| **Dati di ripresa** (datos de rodaje) | — | — | solo lectura: óptica, focal, diafragma, foco, obturador, ISO/EI, balance, color, frame rate, ND/estabilizador, LUT de cámara, archivo |

El nodo guarda sus ajustes por clip: se guardan con la corrección y vuelven cuando regresas a ese clip. Solo se
reinician al pasar a otro clip o al pulsar *Rileggi metadata*.

### 3 · Un orden de trabajo

1. Importa el material, ejecuta el script, pulsa **1** y luego **2**.
2. En la página Color pon **S-Log MetaRaw** el primero, deja *Color Space* y *Gamma* en *Timeline* si el proyecto tiene
   gestión de color, y que le sigan tu CST o tu LUT de siempre.
3. Corrige blancos y exposición **en el nodo** y no con lift/gamma/gain: ahí el ajuste ocurre en luz lineal, antes de
   cualquier curva, que es donde lo habría hecho una cámara.

---

## Qué se escribe en Resolve

**Campos estándar**, rellenados solo cuando el clip contiene realmente ese valor:

`Camera Manufacturer` · `Camera Type` · `Camera TC Type` · `Camera Serial #` · `Camera Firmware` · `Camera FPS` ·
`Shutter Type` · `Shutter Angle` · `Shutter Speed` · `Exposure Mode` · `ISO` · `White Point (Kelvin)` ·
`White Balance Tint` · `Mon Color Space` · `Monitor LUT` · `LUT Used` · `Lens Type` · `Lens Number` · `Lens Notes` ·
`Camera Aperture Type` · `Camera Aperture` · `Focal Point (mm)` · `Distance` · `ND Filter` · `Codec Bitrate` ·
`Sensor Area Captured` · `PAR Notes` · `Aspect Ratio Notes` · `Gamma Notes` · `Color Space Notes` · `Date Recorded`

En **Camera Notes** va un resumen legible; en **Keywords**, el modelo de cámara, la gamma, las primarias y `S&Q` cuando
el clip se grabó en cámara lenta o rápida: eso es lo que hace funcionar las smart bins. Todo lo leído, incluidos los
valores sin campo estándar, se adjunta además como metadatos de terceros con el prefijo `SLogMetaRaw.`.

**Input Color Space** (solo si marcas la casilla) se mapea así:

| En el clip | Se ajusta en Resolve |
|---|---|
| S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · S-Gamut/S-Log | el mismo nombre |
| ITU-R BT.2100 HLG · HLG Live · HLG Mild | Rec.2100 HLG |
| S-Cinetone · ITU-R BT.709-5 | Rec.709 (Scene) |

**La exportación CSV** cubre lo que Resolve no tiene dónde poner: EI, ISO, ganancia, modo de WB, preajuste de luz, tinte,
modo AE, área de AF, focal equivalente a 35 mm, distancia de foco, espacio de color, gamma de captación, luminance code
range, rango del códec, estabilizador, LUT de monitorado, modo de grabación, fps de captación, hora de grabación y
formato. El archivo se escribe en el formato CSV de metadatos del propio Resolve (UTF-16); se importa con
**File › Import › Metadata**, con la opción de crear campos personalizados activada.

---

## Cómo funciona

### Dónde están los datos y qué poco se lee del archivo

En los archivos Sony XAVC los datos de rodaje se graban **fotograma a fotograma**:

- en **MP4**, en la pista de metadatos temporizados `rtmd`;
- en **MXF**, en paquetes ANC SMPTE ST 436 (DID 0x43 / SDID 0x05).

Ambos son estructuras KLV con los conjuntos de adquisición **SMPTE RDD 18**, más las etiquetas propias de Sony. Junto a
ellos está el XML *NonRealTimeMeta* —el archivo `M01.XML` o una copia incrustada— con modelo, número de serie, firmware,
gamma de captación y primarias, y el **SPS** de H.264/HEVC, que aporta perfil, profundidad de bits y rango completo o
limitado.

El parser lee el índice del archivo y muestrea la pista de metadatos **una vez por segundo, hasta 120 muestras**. Así es
como la columna *Stato* puede avisarte de que el diafragma o el foco cambiaron durante la toma, y por eso un clip de
varios GB cuesta unos **100 KB de lectura**: no se decodifica nada ni se renderiza ningún fotograma.

Todo en Python puro, sin dependencias externas, sin ExifTool, sin nada que instalar aparte del propio paquete.

### Del script al nodo

El script usa la API de scripting de Resolve 21.1 (Resolve incluye Python 3.14). Además de los campos del Media Pool,
cada clip recibe una ficha JSON plana en `~/Library/Application Support/SLogMetaRaw/cache`, con el nombre derivado de un
hash de la ruta del clip.

El nodo sabe cuál es el archivo del clip gracias a la extensión de Resolve `kOfxImageEffectPropSrcFilePath`, y lee esa
ficha: así se configura solo. Si la ficha falta, la genera ejecutando `ResolvePython -m slogmetaraw --cache` sobre el
clip. Esa lectura corre en el hilo de la interfaz, así que va atada en corto: 8 segundos como máximo, un solo intento por
clip, y los archivos que en el disco son solo un marcador de posición de un servicio en la nube se omiten en lugar de
descargarse. El espacio de color de trabajo del nodo llega desde Resolve mediante la gestión de color de OpenFX 1.5.

### Las matemáticas del color

Todo ocurre en **luz lineal**, en el gamut que entra en el nodo, en este orden:

1. **Decodificar** la curva de entrada y multiplicar por la relación de exposición `EI elegido / EI de rodaje`: duplicar
   el EI es exactamente un paso.
2. **Balance de blancos**: adaptación de von Kries en **LMS Bradford**, del blanco de rodaje al blanco elegido. Ambos
   blancos salen del **lugar de Planck** (aproximación cúbica de Kim et al. 2002, válida entre 1667 y 25000 K); el
   *Tint* desplaza el blanco perpendicularmente al lugar, en el plano CIE 1960 *uv*. El resultado se normaliza para que
   el desplazamiento no altere la luminancia del D65.
3. **Tonos**: la escena es un depósito de luz lineal con el gris 18% como mediana y un techo dado por la curva que la
   cámara grabó — +7,74 pasos para S-Log3, una propiedad del formato, nunca de la imagen. `Highlights` es una prensa que
   baja desde ese techo; `Shadows` es una campana alrededor de −4 pasos; `Contrast` es una ley de potencia sobre la misma
   power norm. Los tres son monótonos por canal por construcción, así que un píxel más brillante nunca puede salir más
   oscuro.
4. **Saturation y Color Boost**: un escalado alrededor de la luminancia; Color Boost es un vibrance, ponderado según lo
   saturado que ya está cada píxel, así que levanta los colores apagados y deja en paz los que ya son intensos.
5. **Color Space / Gamma**: si alguno difiere del espacio del nodo, una conversión a través de XYZ, exactamente igual
   que un Color Space Transform; si no, la imagen se vuelve a codificar en la curva con la que entró.
6. **Gamut**: lo último antes de codificar. Un color fuera del espacio en el que estamos escribiendo no es un look, es una
   señal que allí no puede existir — un LED de escena saturado convertido de S-Gamut3.Cine a Rec.709 mide R −0,125,
   G −0,292 — y ningún control de tono puede arreglarlo, porque la prensa multiplica los tres canales por un factor
   *positivo*. La distancia de cada canal al acromático se comprime hacia una asíntota que nunca alcanza, que es
   exactamente el punto en el que ese canal valdría cero: **el nodo no puede emitir un canal negativo**. Dentro del gamut
   no hace nada en absoluto: un color que ya está dentro queda por debajo del umbral y sale bit a bit como entró.

Las funciones de transferencia siguen las definiciones publicadas: **S-Log, S-Log2 y S-Log3** de los documentos de Sony,
**DaVinci Intermediate**, **ACEScct**, **Rec.709** (OETF de BT.709), **sRGB** y las gammas puras 2,2 / 2,4 / 2,6. Las
matrices de gamut, con sus inversas, cubren DaVinci Wide Gamut, Rec.709, Rec.2020, P3 D65/D60/DCI, S-Gamut, S-Gamut3,
S-Gamut3.Cine, ACES AP0 y AP1 (S-Gamut3 comparte las primarias de S-Gamut, como documenta Sony).

Las matemáticas viven en un solo archivo, `DevelopMath.h`, generado por `tools/build_math.py` y compilado **tanto** como
C++ **como** en el kernel de **Metal**, de manera que las rutas de GPU y CPU no puedan separarse. El render corre sobre
Metal, con alternativa en CPU.

Cuando la cámara no grabó la temperatura de color —la a6300, entre otras—, el valor se deduce del preajuste de luz que sí
grabó (Daylight 5600 K, Cloudy 6500 K, Shade 7500 K, Incandescent 3200 K, Fluorescent 4000 K; en cualquier otro caso,
5600 K) y el nodo lo señala como estimado, en la línea de estado y en los datos de rodaje.

### Qué se ha comprobado

- **Campo por campo contra Catalyst Browse** en FX6, FX30 y a6300: etiquetas y valores.
- **Tres implementaciones que coinciden.** El modelo de referencia en Python, el código C++ y el kernel Metal coinciden
  dentro de **2·10⁻⁴** en un barrido aleatorio de parámetros y espacios de color.
- **Dentro de Resolve**: las LUT exportadas desde el nodo se compararon con el mismo modelo, con un error inferior a
  **0,0003**.
- **Un host OpenFX en miniatura** (`tests/host_test.cpp`) carga el plugin compilado y ejecuta lo que ejecuta Resolve
  —carga, descripción, ambos contextos, construcción del nodo sobre un clip real—, de modo que un fallo en el panel del
  nodo aparece aquí y no en Resolve.
- En total, 25 pruebas automáticas: parsers, modelo de revelado, C++, Metal, host OpenFX y parámetros del plugin.

---

## Compilar desde el código fuente

```bash
make -C ofx/SLogMetaRaw                     # plugin universal arm64 + x86_64 (requiere Xcode)
./install.sh --dev                          # instala script y plugin apuntando a esta carpeta
python3 -m unittest discover -s tests       # las 25 pruebas
./packaging/build_installer.sh              # crea dist/SLogMetaRaw-x.y.z.dmg
python3 -m slogmetaraw carpeta_o_archivo    # vista estilo Catalyst desde la línea de comandos
python3 -m slogmetaraw --cache clip.MP4     # escribe solo la ficha JSON que lee el nodo
```

```
slogmetaraw/         parsers mp4, mxf, rtmd, nrt, codec · escritura en Resolve · ventana del script
resolve_script/      lanzador para Workspace › Scripts
ofx/SLogMetaRaw/     plugin OpenFX (C++, Metal); DevelopMath.h lo genera tools/build_math.py
tools/               matrices de gamut, generadores, iconos
tests/               pruebas (los clips de ejemplo no están en el repositorio)
packaging/           instalador: paquete, guía PDF, desinstalador
```

---

## Limitaciones conocidas

- El panel Camera Raw **de verdad** y la **estabilización por giroscopio** de Resolve no se pueden desbloquear en los
  MP4: ambos dependen del decodificador interno de Resolve (Sony solo para MXF, giroscopio solo para cámaras Blackmagic).
  S-Log MetaRaw es el equivalente para los controles de color, no una puerta de entrada.
- Hacen falta **S-Log2 o S-Log3**. Con otros perfiles el nodo se mantiene neutro y lo indica.
- Algunas cámaras no graban la temperatura de color: se estima a partir del preajuste de luz y se señala.
- **S-Log2:** la fórmula sigue el documento de Sony (gris 18% en el código 347). La curva S-Log2 que instala Resolve
  difiere en unos 0,15 pasos, así que las dos no aterrizan exactamente en el mismo sitio.
- Pendiente de validar con más archivos: XAVC HS (HEVC), HLG y S-Cinetone, zooms motorizados, GPS.
- **Proyecto independiente y de aficionado**, distribuido tal cual, sin garantías y sin responsabilidad alguna por su uso
  en contextos profesionales. El código es abierto: cualquiera puede leerlo, probarlo y modificarlo.

---

## Créditos

**Ivan Mazzone + Claude** — [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).

Escrito junto a **Claude Opus 5** (Anthropic): la versión 1.0 lleva fecha del 19 de septiembre de 2026, la 1.0.1 del
día siguiente y la 1.1.0 del 22 de septiembre de 2026. El changelog está en [RELEASE_NOTES.md](RELEASE_NOTES.md).

Referencias para las etiquetas de Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) (Sony.pm) y
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) de AdrianEddy (MIT). Parte de la tabla de etiquetas
procede de este último.

Sony, XAVC y Catalyst son marcas de Sony Group Corporation; DaVinci Resolve es una marca de Blackmagic Design. Proyecto
independiente, no afiliado ni respaldado por ninguna de las dos empresas.

## Licencia

[GNU General Public License v3.0 o posterior](LICENSE). Software libre: puedes usarlo, estudiarlo, modificarlo y
redistribuirlo; quien lo redistribuya, modificado o no, debe hacerlo con la misma licencia y con el código fuente
disponible. Sin garantía de ningún tipo.

El SDK de OpenFX pertenece a The Open Effects Association (BSD de 3 cláusulas) y parte de la tabla de etiquetas de Sony
procede de telemetry-parser (MIT): ambas compatibles con la GPL-3.
