<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadatos de cámaras Sony y controles de revelado en luz de escena para DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <a href="README.it.md">Italiano</a> · <b>Español</b> · <a href="README.pt.md">Português</a> · <a href="README.zh.md">简体中文</a>
</p>

---

## Qué es

Las cámaras Sony escriben en cada archivo cómo se rodó el plano: balance de blancos en Kelvin, tinte, EI, objetivo,
diafragma, obturador, perfil de color. Resolve usa esos datos en los MXF de la FX6 y la FX9, que tienen panel
*Camera Raw*. En los MP4 de una FX30, FX3, serie a7 o a6000 los ignora.

S-Log MetaRaw lee esos datos y los usa. Tiene tres partes:

| | Dónde | Qué hace |
|---|---|---|
| **Script** | Workspace › Scripts › S-Log MetaRaw | lee los metadatos de todos los clips del proyecto y los escribe en el Media Pool |
| Nodo **S-Log MetaRaw** | Color › OpenFX | revela un clip a partir de sus valores de rodaje: balance, exposición, espacio de color, tonos por zonas, falso color |
| Nodo **S-Log MetaRaw Detail** | Color › OpenFX | el nodo creativo: recuperación local de tonos, Texture, Clarity, Dehaze |

Ningún archivo se transcodifica y ningún original se escribe nunca.

### Qué esperar, con honestidad

**No es raw.** Un MP4 log ya está demosaicado y comprimido, a 8 o 10 bits, a menudo 4:2:0, con la reducción de ruido de
la cámara ya aplicada. Ningún plugin puede devolver lo que la cámara descartó.

Lo que hace el nodo es aplicar la ciencia del color con rigor. Exposición y balance trabajan en luz lineal, parten de los
valores que la cámara registró y siguen curvas y gamuts publicados. Los tonos mueven la imagen en pasos. Trabajada así,
una imagen log **se comporta de un modo que recuerda a un archivo RAW**: el balance se desplaza limpio, la exposición se
mueve como un paso de luz y las altas luces se redondean en vez de romperse.

En un trabajo intenso, la ciencia del color sola no basta. En cuanto se fuerzan los límites de la cámara, la falta de
información en la imagen se nota: banding en los cielos, ruido en las sombras levantadas, altas luces quemadas que
siguen quemadas, color que se deshace en los canales comprimidos. Expón bien en rodaje. S-Log MetaRaw te ayuda a sacar
lo mejor de lo que hay. No puede crear lo que no hay.

---

## Instalación

1. Descarga `SLogMetaRaw-2.1.1.dmg` desde **Releases** y ábrelo.
2. Doble clic en **Installa S-Log MetaRaw.pkg**. No está firmado con un certificado de Apple: la primera vez, clic
   derecho › **Abrir**. Pide la contraseña del Mac porque el plugin va en una carpeta del sistema.
3. Reinicia DaVinci Resolve.

El instalador también borra la caché de plugins de Resolve (`OFXPluginCacheV2.xml`), que Resolve reconstruye en el
siguiente arranque. Sin eso, Resolve seguiría mostrando el panel antiguo y no vería el nodo Detail.

| Instalado | Ruta |
|---|---|
| Los dos nodos (un solo bundle) | `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` |
| La biblioteca Python | `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` |
| El script del menú | `…/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` |

Mientras funciona guarda un pequeño registro JSON por clip en `~/Library/Application Support/SLogMetaRaw/cache`. El
disco también contiene las guías de tres páginas, en italiano e inglés.

**Instalación limpia y desinstalación.** Cada instalación empieza limpia: el instalador sustituye por completo el plugin
y la biblioteca anteriores y quita las instalaciones de desarrollo, así que no queda ningún archivo de una versión vieja.
**Disinstalla S-Log MetaRaw.command**, en el disco (la primera vez: clic derecho › Abrir), elimina todas las versiones
instaladas, 1.x y 2.x incluidas, con la caché, los ajustes y los registros. Antes de tocar nada lo enumera todo, te pide
cerrar Resolve y te pregunta si borrar también los CSV exportados. Los metadatos ya escritos en los proyectos de Resolve
forman parte de los proyectos y se quedan.

**Requisitos:** macOS 12 o posterior, Apple silicon o Intel, y DaVinci Resolve 21. **Probado solo en Resolve Studio 21.1
en macOS.**

**Clips:** Sony XAVC en `.MP4` o `.MXF`. El script los lee todos. Los nodos revelan **S-Log3** (S-Gamut3.Cine o
S-Gamut3), **S-Log2** y **S-Log** (S-Gamut). Con otros perfiles se quedan neutros y lo dicen.

---

## En pocas palabras

1. Importa el material. **Workspace › Scripts › S-Log MetaRaw**: pulsa **1 · Leer metadatos** y luego
   **2 · Escribir en Resolve**.
2. En la página Color pon **S-Log MetaRaw** como **primer nodo**. Toma el EI, los Kelvin y el tinte del clip. Con esos
   valores no cambia nada.
3. Corrige balance y exposición en el nodo. Las vistas de falso color ayudan.
4. Da forma a los tonos con **Toni** (Tonos). Para recuperación local, Texture, Clarity o Dehaze añade
   **S-Log MetaRaw Detail** como nodo siguiente.
5. Después, tu CST, LUT o DRT.

```
S-Log MetaRaw  →  S-Log MetaRaw Detail  →  CST / LUT / DRT  →  resto del etalonaje
```

---

## El script

La ventana tiene una fila de botones, una de opciones y la lista de clips, y sigue el idioma de Resolve (español,
inglés, italiano, portugués, chino simplificado). Los paneles de los nodos están en italiano: abajo sus etiquetas van
con traducción.

- Un menú elige los clips: *Todo el Media Pool* o *Clips seleccionados en el Media Pool*.
- **1 · Leer metadatos**: una fila por clip con cámara, objetivo, diafragma, obturador, EI, WB, espacio de color y
  data level. La columna *Estado* dice `leído`, qué cambió durante la toma (diafragma, foco…) o por qué
  se saltó un clip. Haz clic en una fila para ver todo lo leído, agrupado como en Catalyst Browse.
- **2 · Escribir en Resolve**: rellena los campos del Media Pool (panel Metadata, columnas, palabras clave para
  smart bins, data burn-in) y corrige valores que Resolve lee mal de los MXF, como *Camera Aperture* `F53343` en la FX6.
- **Exportar CSV**: exporta los valores para los que Resolve no tiene campo (EI, tinte, modo WB, distancia de foco, gamma
  de captura…) en el formato CSV de metadatos de Resolve.
- Opciones:
  - **Etiqueta por cámara** (apagada): añade cámara, gamma y primarios a las palabras clave.
  - **Sobrescribir metadatos** (encendida): sustituye los valores que Resolve ya escribió; apagada, solo rellena los campos
    vacíos.
  - **Corregir el Data Level** (encendida): pone el *Data Level* de cada clip en Full o Video, lo que pida su gamma. El
    porqué está en [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md).
  - **Establecer también Input Color Space** (apagada): para proyectos con gestión de color.
    Un script no puede devolverlo a *Project*: solo tú, a mano.
- La versión abajo a la derecha, al hacer clic, consulta GitHub.

La lectura es rápida porque no decodifica nada: como máximo 24 muestras de la pista de metadatos por clip, con un límite
de un segundo. Un volumen que deja de responder se salta una sola vez, con un aviso, en lugar de bloquear la lista.

---

## El nodo S-Log MetaRaw

El nodo es puntual: cada píxel depende solo de sí mismo. Nunca crea halos y **Generate LUT** puede exportarlo
(se recomiendan 65 puntos).

| Control | Qué hace |
|---|---|
| **Versión** (arriba) | `v2.1.1`. Una vez al día pregunta a GitHub por la última release. Si la hay muestra **🟢 v2.1.1 → 2.x.y** y el clic abre la descarga del DMG en el navegador. Nunca instala nada por sí mismo |
| **Camera** · **Rileggi metadata** | la cámara leída. *Rileggi* (releer) vuelve a leer el clip, devuelve cada control a los valores de cámara y escribe los metadatos del clip en el Media Pool |
| **Decode Using** | *Clip* permite cambiar los controles; *Camera metadata* los bloquea en los valores de rodaje |
| **White Balance** · **Color Temp** · **Tint** | As shot o presets. Adaptación cromática Bradford en luz lineal, desde el blanco que registró la cámara |
| **Exposure** | índice de exposición: el doble de EI = +1 paso |
| **False color** | temperatura, tinte y exposición; ver abajo |
| **Color Space** · **Gamma** | salida, como un Color Space Transform; *Timeline* no convierte |
| **Toni** (Tonos) | Contrast, Highlights, Shadows, Whites, **Bianco** (blanco, en pasos), Blacks, Vibrance, Saturation (−100…+100) |
| **Zone** (Zonas, cerrado) | zonas Black, Shadow, Light y Specular con Exp (pasos), Sat, Range y Falloff; Contrast Pivot; Soft Clip; falso color *Zone* |
| **Avanzate** (Avanzado) | entrada del nodo, corrección del data level, estado, **Sblocca controlli senza metadata** (desbloquear sin metadatos) |
| **Dati di ripresa** (datos de rodaje) | solo lectura: objetivo, focal, diafragma, foco, obturador, EI, WB, fps, ND, LUT de cámara |

**Highlights es un hombro de película.** En negativo comprime las altas luces con una pendiente que baja de forma
continua hacia arriba, como la película, ACES 2.0 y AgX. A −100 el valor más alto que registró la cámara (unos +6 pasos
sobre el gris en S-Log3) llega exactamente al **Bianco**: sin velo gris y sin clip. El gris y lo que está debajo no se
mueven, y la piel a +1 paso se desplaza 0,05 pasos como mucho. Las luces más comprimidas van suavemente hacia el blanco sin
cambiar de tono. En positivo da más fuerza a las altas luces, con una pendiente limitada. **Bianco** es donde llega ese
máximo (y el techo de Soft Clip): 2,5 pasos es el blanco de Rec.709 con un CST sin tone mapping. Con un DRT después del nodo
(ACES, AgX, DaVinci), súbelo a 4–5, o las altas luces se comprimen dos veces.

**Tonos por zonas.** Shadows, Whites y las Zonas son exposiciones, en pasos, sobre una franja de tonos: Shadows por debajo
de −1 paso, Whites desde +3,5 pasos. Blacks es un velo lineal que mueve el negro sin mover el gris. Dentro de una zona la
imagen se mueve como con una exposición, así que la textura se conserva, y la compresión está en una banda de transición
declarada. Ninguna combinación de deslizadores puede solarizar. El coste de un nodo puntual, dicho claro: lo que comprime,
lo comprime también en la textura. Por eso la recuperación local es un nodo aparte. Fórmulas y recetas:
[docs/TONE_MAPPING.md](docs/TONE_MAPPING.md).

**Falso color.** Una vista por control, encima del deslizador al que sirve:
- **Exposición** usa bandas en pasos alrededor del gris 18%, al estilo ARRI. Verde es el gris medio, rosa un paso por
  encima (la piel), amarillo cerca del clip, rojo el clip, azul y violeta el fondo.
- **Temperatura** y **Tinte** funcionan como en CineMatch. La imagen se vuelve gris, las dominantes se colorean de
  naranja/azul o verde/magenta, y las casi neutras se amplifican hasta 8× para que se vean. Mueve el deslizador hasta que
  lo que debe ser neutro se quede gris. Cada vista responde solo a su deslizador.

La vista sustituye la imagen: apágala antes de renderizar. [docs/FALSE_COLOR.md](docs/FALSE_COLOR.md)

**Data level.** Si Resolve decodifica un clip en la escala de code values equivocada, el nodo la corrige antes de la
curva log. La opción *Corregir el Data Level* del script lo arregla para todo el proyecto.
[docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)

**Sin metadatos.** Un ProRes de grabador externo, o un clip que no se puede leer, deja el nodo neutro. Marca
*Avanzate › Sblocca controlli senza metadata* y escribe el EI, los Kelvin y el tinte de rodaje: los controles se activan
y el nodo empieza neutro.

**Velocidad.** Abrir un proyecto no lee ningún archivo. Abrir el panel espera como mucho medio segundo; un disco lento
termina en segundo plano, con un límite de 15 segundos. *Rileggi* responde en unos 2 segundos como máximo.

---

## El nodo S-Log MetaRaw Detail

Es el nodo creativo. Trabaja **por áreas**, sobre una base que respeta los bordes, y ajusta las grandes áreas sin
aplanar el detalle fino. Es la parte de Highlights y Shadows de Lightroom que un nodo puntual no puede copiar.

| Grupo | Controles |
|---|---|
| **Gamma dinamica** (rango dinámico) | Local Contrast, Local Highlights, Local Shadows; vistas de *ganancia* y *base*. Local Highlights comprime las grandes áreas luminosas y conserva, incluso refuerza, la textura fina: el cielo se oscurece y las nubes mantienen su detalle. El Highlights del nodo principal en cambio suaviza la textura de las altas luces, como la película |
| **Presenza** (presencia) | Texture, Clarity, Dehaze |
| **Zone locali** (zonas locales) | las zonas del nodo principal, aplicadas a las áreas |
| **Avanzate** (avanzado) | preservación del detalle, radio, umbrales de bordes y ruido, centro de Clarity, **Bianco** de Local Highlights, entrada del nodo |
| **Velo** | nivel y color del velo que quita Dehaze: los decides tú, nunca se estiman fotograma a fotograma |

- Ponlo **justo después** de S-Log MetaRaw, antes de CST, LUT o DRT. Decodifica a luz lineal lo que recibe y lo vuelve a
  escribir en la misma codificación, así que va antes de cualquier conversión: deja Color Space y Gamma del nodo principal
  en Timeline.
- Es **espacial**, así que Generate LUT lo excluye, junto con el resto de su nodo. Tenlo en un nodo propio.
- Los radios siguen la altura del fotograma. El look es el mismo a resolución completa, en proxy y en el visor. Sin
  estadísticas por fotograma, así que sin parpadeo.
- En Metal un fotograma UHD tarda unos 6–18 ms, medidos en Apple silicon. La alternativa por CPU es mucho más lenta.

**Sus límites, medidos.** Con Local Highlights −100 el halo en el lado oscuro de un borde queda por debajo del 3% del
escalón. Con Local Shadows o las zonas locales a ±100, en un borde nítido de un paso el halo llega a cerca del 12% del escalón, y al 4–6% en
escalones de 2–3 pasos. Si lo ves, baja *Soglia bordi* (umbral de bordes). Texture no sube el grano por debajo del
umbral de ruido, pero junto a bordes fuertes el grano puede crecer 1,25–1,7 veces. Dehaze necesita un velo real que
quitar. [docs/DETAIL.md](docs/DETAIL.md)

---

## Actualizaciones y privacidad

- Los **nodos** preguntan a GitHub por la última release de este proyecto como mucho una vez al día, en segundo plano.
  La petición lleva solo la versión del programa (`User-Agent: SLogMetaRaw/2.1.1`). Para desactivarlo crea el archivo
  vacío `~/Library/Application Support/SLogMetaRaw/no_update_check`.
- El **script** solo consulta cuando haces clic en su versión.
- Un clic solo abre un enlace de descarga de las releases de GitHub de este proyecto. Nada se instala sin ti.

---

## Cómo funciona, en breve

- **Metadatos.** Los parsers son Python puro, sin dependencias. Leen los metadatos de adquisición SMPTE RDD 18 fotograma a
  fotograma (pista `rtmd` de los MP4, paquetes ST 436 de los MXF), el XML NonRealTimeMeta de Sony, el SPS H.264/HEVC y el
  descriptor de imagen MXF. Un clip de varios gigabytes cuesta unos 100 KB de lectura.
- **Del script al nodo.** Cada clip tiene un registro JSON en la caché. El nodo encuentra su archivo por la ruta de origen
  que Resolve le da, lee ese registro y, si falta, lo crea en segundo plano.
- **Matemática del color.** La cadena es: decodificación de la curva de cámara, relación de EI, balance Bradford desde el
  locus de Planck (con el tinte perpendicular en CIE 1960 uv), luego tonos con una sola ganancia por píxel a partir de una
  norma de sus canales (la cromaticidad se conserva), luego color, luego salida. Todo en luz lineal, con las curvas y
  gamuts publicados por Sony.
- **Una matemática, tres implementaciones.** La matemática está en `ofx/SLogMetaRaw/math` y se compila como C++ y como
  Metal. Un modelo Python de referencia verifica ambas: CPU y GPU coinciden dentro de 2·10⁻⁴, con FMA desactivado en todas
  las rutas.
- **Tests.** 322 tests automáticos: parsers, modelos de referencia, C++, Metal, un host OpenFX en miniatura que carga los
  dos nodos como lo hace Resolve, y archivos golden de los paneles.

---

## Compilar desde el código

```bash
make -C ofx/SLogMetaRaw                     # plugin universal, arm64 + x86_64 (requiere Xcode)
make -C ofx/SLogMetaRaw test-bins           # binarios de test
python3 -m unittest discover tests          # los tests
./install.sh --dev                          # script y plugin apuntando a esta carpeta
./packaging/build_installer.sh              # dist/SLogMetaRaw-<versión>.dmg
python3 -m slogmetaraw clip.MP4             # lectura estilo Catalyst desde la línea de comandos
```

```
slogmetaraw/         parsers, escritura en Resolve, ventana del script, comprobación de actualizaciones
resolve_script/      lanzador para Workspace › Scripts
ofx/SLogMetaRaw/     math/ (compartida CPU/Metal), src/ (common, develop, detail), metal/
tools/               generadores de matrices, iconos y gráficos
tests/               tests y modelos de referencia (los clips de prueba no están en el repositorio)
packaging/           instalador, guías, desinstalador
docs/                TONE_MAPPING, DETAIL, FALSE_COLOR, DATA_LEVELS
```

---

## Límites conocidos

- El panel Camera Raw de Resolve y la estabilización por giroscopio no se pueden desbloquear para MP4: viven dentro de los
  decodificadores de Resolve. S-Log MetaRaw reconstruye los controles de color; no abre una puerta dentro de Resolve.
- Algunas cámaras (entre ellas la a6300) no registran los Kelvin: entonces se estiman a partir del preset de luz y se
  señalan.
- S-Log2 sigue el documento de Sony. La curva S-Log2 de Resolve difiere en unos 0,15 pasos.
- Pendiente de comprobar con más archivos: XAVC HS (HEVC), HLG, S-Cinetone, zooms motorizados.
- **Un proyecto independiente y aficionado**, distribuido tal cual, sin garantía y sin responsabilidad por el uso
  profesional. El código es abierto: léelo, pruébalo, cámbialo.

---

## Créditos y licencia

**Ivan Mazzone + Claude** · [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).
Escrito con Claude (Anthropic): la 1.0 el 19 de septiembre de 2026, la 1.1.0 el 22 de septiembre, la 2.0.0 el 23 de
septiembre de 2026. La historia completa está en [RELEASE_NOTES.md](RELEASE_NOTES.md) (en italiano).

Referencias para las etiquetas Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) y
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) de AdrianEddy (MIT), de donde viene parte de la tabla
de etiquetas.

[GNU GPL v3.0 o posterior](LICENSE). El SDK OpenFX es © The Open Effects Association (BSD-3). Sony, XAVC y Catalyst son
marcas de Sony Group Corporation; DaVinci Resolve es una marca de Blackmagic Design. Proyecto independiente, no afiliado
ni respaldado por ninguna de las dos empresas.
