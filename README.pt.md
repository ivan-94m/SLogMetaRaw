<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadados de câmera Sony e controles no estilo Camera Raw para o DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <a href="README.it.md">Italiano</a> · <a href="README.zh.md">简体中文</a> · <a href="README.es.md">Español</a> · <b>Português</b>
</p>

---

## A ideia

A câmera já registrou como a tomada estava ajustada: balanço de branco em kelvin, tint, EI, lente, obturador, perfil de
cor. Nos arquivos MXF de uma FX6, o Resolve usa essas informações e abre o painel **Camera Raw › Sony Video**. Nos MP4 de
uma FX30, FX3 ou a6300 essas mesmas informações estão dentro do arquivo — e o Resolve as ignora.

O S-Log MetaRaw lê tudo isso e coloca de volta em uso: balanço de branco, exposição e espaço de cor partem do que a
câmera registrou, em vez de um chute. Nada é transcodificado e os arquivos originais nunca são alterados.

Não é raw. Um MP4 em log é uma imagem já revelada e comprimida, e nenhum plugin desfaz isso. O que dá para fazer é
retomar as decisões tomadas na captação — aquelas que o raw deixaria revisar — sobre a imagem que foi de fato gravada, em
luz linear e com ciência das cores publicada.

| | |
|---|---|
| **Script** (Workspace › Scripts) | Lê os metadados de **todos os clipes do projeto de uma vez**, ou apenas dos selecionados, e grava no Media Pool: painel Metadata, colunas, palavras-chave para smart bins, data burn-in, exportação em CSV. Mostra tudo o que leu, agrupado como o Catalyst Browse agrupa, e corrige campos que o Resolve preenche errado nos MXF, como *Camera Aperture* aparecendo como `F53343` na FX6. |
| **Plugin** (OpenFX, página Color) | Um clipe por vez, como se você tivesse o painel Raw à mão: Color Temp, Tint, Exposure (EI), White Balance, Color Space/Gamma e tons. Ele **se configura sozinho** com os valores de captação daquele clipe e, nesses valores, é neutro: enquanto você não mexer em nada, nada muda. |

---

## Instalação

1. Baixe `SLogMetaRaw-x.y.z.dmg` na página **Releases** e abra o arquivo.
2. Clique duas vezes em **Installa S-Log MetaRaw.pkg**. O instalador não é assinado com um certificado da Apple, então na
   primeira vez é preciso abrir com o botão direito › **Abrir**.
3. Reinicie o DaVinci Resolve.

O instalador coloca exatamente três coisas:

| Caminho | O que é |
|---|---|
| `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` | o nó OpenFX |
| `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` | a biblioteca Python (os parsers) |
| `…/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` | o item de menu do script |

Durante o uso ele também grava uma pequena ficha JSON por clipe em `~/Library/Application Support/SLogMetaRaw/cache`, e
as exportações em CSV vão para `~/Documents/SLogMetaRaw`. O **Disinstalla S-Log MetaRaw.command**, na imagem de disco,
remove tudo. Na imagem também estão os guias de uma página, **S-Log MetaRaw Guide (english).pdf** e
**Guida S-Log MetaRaw (italiano).pdf**.

**Requisitos:** macOS 12 ou posterior (Apple Silicon ou Intel) e DaVinci Resolve 21. **Testado apenas no Resolve Studio
21.1 no macOS.** Versões anteriores não foram testadas: o script talvez funcione se você tiver o Python 3 instalado (o
Resolve inclui o próprio interpretador somente a partir da 21.1), enquanto o plugin depende de recursos introduzidos no
Resolve 21 — o gerenciamento de cores do OpenFX 1.5 acima de tudo —, então ali seria preciso ajustar à mão
*Avanzate › Ingresso nodo* (Avançado › Entrada do nó).

**Clipes compatíveis:** Sony XAVC, `.MP4` ou `.MXF`, gravados em **S-Log2 ou S-Log3**. Os perfis que o nó revela são
`S-Gamut3.Cine/S-Log3`, `S-Gamut3/S-Log3`, `S-Gamut/S-Log2` e `S-Gamut/S-Log`. O script lê os metadados de qualquer
clipe Sony XAVC, em log ou não; no resto, o nó permanece neutro.

---

## Guia

### 1 · O script

**Workspace › Scripts › S-Log MetaRaw.** A janela tem três botões, na ordem em que se usam.

- **Origine** (origem) — *Clip selezionate nel Media Pool* (clipes selecionados), *Bin corrente (con sottocartelle)*
  (bin atual, com subpastas) ou *Tutto il Media Pool* (todo o Media Pool).
- **1 · Leggi metadata** (ler metadados) — lê os clipes. Ainda não grava nada. A tabela se preenche com uma linha por
  clipe: clipe, câmera, lente, distância focal, diafragma, obturador, ISO/EI, WB, espaço de cor, data level e uma coluna
  *Stato* (situação) que diz `letto` (lido), ou `letto · varia: diaframma, fuoco` quando algum valor mudou durante a
  tomada, ou por que um clipe foi pulado. **Clicando numa linha**, o painel de baixo mostra tudo o que foi lido, nas
  mesmas seções que o Catalyst Browse usa.
- **2 · Scrivi in Resolve** (gravar no Resolve) — grava os metadados no Media Pool.
- **Esporta CSV (campi custom)** (exportar CSV, campos personalizados) — grava um CSV em `~/Documents/SLogMetaRaw` com os
  valores para os quais o Resolve não tem campo (a lista está mais adiante).

Duas caixas de seleção:

- **Sovrascrivi i campi già compilati** (sobrescrever campos já preenchidos), ligada por padrão. É ela que corrige os
  valores errados que o Resolve grava sozinho, como *Camera Aperture* `F53343` nos MXF da FX6. Se você desligar, apenas
  os campos vazios são preenchidos.
- **Imposta anche Input Color Space (RCM) dai metadata** (definir também o Input Color Space pelos metadados),
  desligada por padrão. Útil num projeto com gerenciamento de cores, mas atenção: uma vez definido por script, o valor
  não pode voltar para *Project* por script — só à mão, dentro do Resolve.

Seus arquivos originais nunca são modificados: o script apenas os lê.

### 2 · O nó

**Página Color › OpenFX › S-Log MetaRaw**, como **primeiro nó**, antes de qualquer CST ou LUT. No alto ele mostra a
câmera e leva Color Temp, Tint e Exposure aos valores de captação. Nesses valores ele não faz nada com a imagem: é um
ponto de partida, não um look. Se você copiar o nó para outro clipe, ele se reconfigura com os dados daquele clipe.

| Controle | Faixa | Padrão | O que faz |
|---|---|---|---|
| **Rileggi metadata** (reler metadados) | — | — | relê o clipe e devolve todos os controles aos valores da câmera |
| **Decode Using** | Camera metadata / Clip | Clip | *Camera metadata* trava tudo nos valores de captação e desativa os controles; *Clip* permite alterá-los |
| **White Balance** | As shot · Daylight 5600 K · Cloudy 6500 K · Shade 7500 K · Tungsten 3200 K · Fluorescent 4000 K · Flash 5500 K · Custom | As shot | predefinições; ao mover um controle deslizante passa a *Custom* |
| **Color Temp** | 2000–15000 K | o da captação | adaptação cromática em luz linear |
| **Tint** | −100 … +100 | o da captação | verde/magenta, perpendicular ao lugar de Planck |
| **Exposure** | 25–409600 EI (deslizante 50–25600) | o da captação | índice de exposição: o dobro do EI equivale a +1 stop |
| **Color Space** | Timeline · DaVinci WG · Rec.709 · Rec.2020 · P3 D65 · P3 D60 · P3 DCI · S-Gamut · S-Gamut3 · S-Gamut3.Cine · ACES AP0 · ACES AP1 | Timeline | gamut de saída, como um Color Space Transform. *Timeline* não converte |
| **Gamma** | Timeline · DaVinci Intermediate · Linear · Gamma 2.2 · Gamma 2.4 · Gamma 2.6 · Rec.709 · sRGB · SLog · SLog2 · SLog3 · ACEScct | Timeline | curva de saída. *Timeline* não converte |
| **Toni** (tons): Shadows, Highlights, Color Boost, Saturation, Contrast | −1 … +1 | 0 | ajustes finos de tom e cor |
| **Avanzate › Ingresso nodo** (entrada do nó) | Automatico · DaVinci WG/Intermediate · S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · ACES AP1/ACEScct | Automatico | o espaço de cor que entra no nó. *Automatico* pergunta ao Resolve; mude apenas se a resposta dele estiver errada |
| **Avanzate › Rilevato / Stato** (detectado / situação) | — | — | o que foi detectado e se os metadados foram encontrados |
| **Dati di ripresa** (dados de captação) | — | — | somente leitura: lente, distância focal, diafragma, foco, obturador, ISO/EI, balanço, cor, frame rate, ND/estabilizador, LUT da câmera, arquivo |

O nó guarda os ajustes por clipe: eles são salvos junto com a correção e voltam quando você retorna àquele clipe. Só são
zerados ao passar para outro clipe ou ao pressionar *Rileggi metadata*.

### 3 · Uma ordem de trabalho

1. Importe o material, rode o script, pressione **1** e depois **2**.
2. Na página Color coloque o **S-Log MetaRaw** em primeiro lugar, deixe *Color Space* e *Gamma* em *Timeline* se o
   projeto tiver gerenciamento de cores, e deixe o seu CST ou a sua LUT virem em seguida.
3. Corrija branco e exposição **no nó**, e não com lift/gamma/gain: ali o ajuste acontece em luz linear, antes de
   qualquer curva, que é onde a câmera teria feito isso.

---

## O que é gravado no Resolve

**Campos padrão**, preenchidos apenas quando o clipe realmente contém aquele valor:

`Camera Manufacturer` · `Camera Type` · `Camera TC Type` · `Camera Serial #` · `Camera Firmware` · `Camera FPS` ·
`Shutter Type` · `Shutter Angle` · `Shutter Speed` · `Exposure Mode` · `ISO` · `White Point (Kelvin)` ·
`White Balance Tint` · `Mon Color Space` · `Monitor LUT` · `LUT Used` · `Lens Type` · `Lens Number` · `Lens Notes` ·
`Camera Aperture Type` · `Camera Aperture` · `Focal Point (mm)` · `Distance` · `ND Filter` · `Codec Bitrate` ·
`Sensor Area Captured` · `PAR Notes` · `Aspect Ratio Notes` · `Gamma Notes` · `Color Space Notes` · `Date Recorded`

Em **Camera Notes** entra um resumo legível; em **Keywords**, o modelo da câmera, a gamma, as primárias e `S&Q` quando o
clipe foi gravado em câmera lenta ou rápida — é isso que faz as smart bins funcionarem. Tudo o que foi lido, inclusive os
valores sem campo padrão, também é anexado como metadados de terceiros com o prefixo `SLogMetaRaw.`.

**Input Color Space** (somente se você marcar a caixa) é mapeado assim:

| No clipe | Definido no Resolve |
|---|---|
| S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · S-Gamut/S-Log | o mesmo nome |
| ITU-R BT.2100 HLG · HLG Live · HLG Mild | Rec.2100 HLG |
| S-Cinetone · ITU-R BT.709-5 | Rec.709 (Scene) |

**A exportação em CSV** cobre aquilo para o que o Resolve não tem campo: EI, ISO, ganho, modo de WB, predefinição de luz,
tint, modo AE, área de AF, distância focal equivalente a 35 mm, distância de foco, espaço de cor, gamma de captação,
luminance code range, range do codec, estabilizador, LUT de monitoração, modo de gravação, fps de captação, hora da
gravação e formato. O arquivo é escrito no formato CSV de metadados do próprio Resolve (UTF-16); importe com
**File › Import › Metadata**, com a opção de criar campos personalizados ativada.

---

## Como funciona

### Onde estão os dados, e o quão pouco do arquivo é lido

Nos arquivos Sony XAVC os dados de captação são gravados **quadro a quadro**:

- nos **MP4**, na trilha de metadados temporizados `rtmd`;
- nos **MXF**, em pacotes ANC SMPTE ST 436 (DID 0x43 / SDID 0x05).

Os dois são estruturas KLV com os conjuntos de aquisição **SMPTE RDD 18**, mais as tags próprias da Sony. Ao lado deles
está o XML *NonRealTimeMeta* — o arquivo `M01.XML` ou uma cópia embutida — com modelo, número de série, firmware, gamma
de captação e primárias, e o **SPS** do H.264/HEVC, que fornece perfil, profundidade de bits e range completo ou
limitado.

O parser lê o índice do arquivo e amostra a trilha de metadados **uma vez por segundo, até 120 amostras**. É assim que a
coluna *Stato* consegue avisar que o diafragma ou o foco mudaram durante a tomada, e é por isso que um clipe de vários GB
custa cerca de **100 KB de leitura**: nada é decodificado e nenhum quadro é renderizado.

Tudo em Python puro, sem dependências externas, sem ExifTool, sem nada a instalar além do próprio pacote.

### Do script ao nó

O script usa a API de scripting do Resolve 21.1 (o Resolve traz o Python 3.14). Além dos campos do Media Pool, cada
clipe recebe uma ficha JSON plana em `~/Library/Application Support/SLogMetaRaw/cache`, com o nome derivado de um hash do
caminho do clipe.

O nó descobre qual é o arquivo do clipe pela extensão do Resolve `kOfxImageEffectPropSrcFilePath` e lê essa ficha — é
assim que ele se configura sozinho. Se a ficha não existir, ele a gera rodando `ResolvePython -m slogmetaraw --cache` no
clipe. Essa leitura roda na thread da interface, então fica na coleira: no máximo 8 segundos, uma única tentativa por
clipe, e arquivos que no disco são apenas um marcador de um serviço de nuvem são pulados em vez de baixados. O espaço de
cor de trabalho do nó vem do Resolve pelo gerenciamento de cores do OpenFX 1.5.

### A matemática das cores

Tudo acontece em **luz linear**, no gamut que entra no nó, nesta ordem:

1. **Decodificar** a curva de entrada e multiplicar pela razão de exposição `EI escolhido / EI de captação` — dobrar o EI
   é exatamente um stop.
2. **Balanço de branco**: adaptação de von Kries em **LMS Bradford**, do branco de captação para o branco escolhido. Os
   dois brancos vêm do **lugar de Planck** (aproximação cúbica de Kim et al., 2002, válida entre 1667 e 25000 K); o
   *Tint* desloca o branco perpendicularmente ao lugar, no plano CIE 1960 *uv*. O resultado é normalizado para que esse
   deslocamento não altere a luminância do D65.
3. **Tons**: `Shadows`, `Highlights` e `Contrast` agem sobre a luminância em log2 em torno do cinza 18%, com os pesos de
   sombras e altas luzes se dissolvendo ao longo de cinco stops, de modo que fiquem onde devem em vez de inclinar a
   imagem inteira.
4. **Saturation e Color Boost**: um escalonamento em torno da luminância; o Color Boost é um vibrance, ponderado pelo
   quanto cada pixel já está saturado, então levanta as cores apagadas e deixa quietas as que já são fortes.
5. **Color Space / Gamma**: se algum dos dois difere do espaço do nó, há uma conversão através do XYZ, exatamente como um
   Color Space Transform; caso contrário, a imagem é recodificada na curva com que entrou.

As funções de transferência seguem as definições publicadas: **S-Log, S-Log2 e S-Log3** dos documentos da Sony,
**DaVinci Intermediate**, **ACEScct**, **Rec.709** (OETF da BT.709), **sRGB** e as gammas puras 2,2 / 2,4 / 2,6. As
matrizes de gamut, com suas inversas, cobrem DaVinci Wide Gamut, Rec.709, Rec.2020, P3 D65/D60/DCI, S-Gamut, S-Gamut3,
S-Gamut3.Cine, ACES AP0 e AP1 (o S-Gamut3 usa as mesmas primárias do S-Gamut, como a Sony documenta).

A matemática vive em um único arquivo, `DevelopMath.h`, gerado por `tools/build_math.py` e compilado **tanto** como C++
**quanto** como kernel **Metal**, de modo que os caminhos de GPU e CPU não possam divergir. A renderização roda em Metal,
com alternativa em CPU.

Quando a câmera não gravou a temperatura de cor — a a6300, entre outras —, o valor é deduzido da predefinição de luz que
ela de fato gravou (Daylight 5600 K, Cloudy 6500 K, Shade 7500 K, Incandescent 3200 K, Fluorescent 4000 K; caso
contrário, 5600 K) e o nó sinaliza como estimado, na linha de situação e nos dados de captação.

### O que foi conferido

- **Campo a campo contra o Catalyst Browse** na FX6, na FX30 e na a6300: rótulos e valores.
- **Três implementações que coincidem.** O modelo de referência em Python, o código C++ e o kernel Metal coincidem dentro
  de **2·10⁻⁴** numa varredura aleatória de parâmetros e espaços de cor.
- **Dentro do Resolve**: as LUTs exportadas do nó foram comparadas com o mesmo modelo, com erro abaixo de **0,0003**.
- **Um host OpenFX em miniatura** (`tests/host_test.cpp`) carrega o plugin compilado e executa o que o Resolve executa —
  carga, descrição, os dois contextos, construção do nó sobre um clipe real —, de modo que uma falha no painel do nó
  aparece aqui e não no Resolve.
- No total, 25 testes automáticos: parsers, modelo de revelação, C++, Metal, host OpenFX e parâmetros do plugin.

---

## Compilar a partir do código-fonte

```bash
make -C ofx/SLogMetaRaw                     # plugin universal arm64 + x86_64 (requer Xcode)
./install.sh --dev                          # instala script e plugin apontando para esta pasta
python3 -m unittest discover -s tests       # os 25 testes
./packaging/build_installer.sh              # gera dist/SLogMetaRaw-x.y.z.dmg
python3 -m slogmetaraw pasta_ou_arquivo     # visão no estilo Catalyst pela linha de comando
python3 -m slogmetaraw --cache clip.MP4     # grava apenas a ficha JSON que o nó lê
```

```
slogmetaraw/         parsers mp4, mxf, rtmd, nrt, codec · gravação no Resolve · janela do script
resolve_script/      lançador para Workspace › Scripts
ofx/SLogMetaRaw/     plugin OpenFX (C++, Metal); DevelopMath.h é gerado por tools/build_math.py
tools/               matrizes de gamut, geradores, ícones
tests/               testes (os clipes de exemplo não estão no repositório)
packaging/           instalador: pacote, guia em PDF, desinstalador
```

---

## Limitações conhecidas

- O painel Camera Raw **de verdade** e a **estabilização por giroscópio** do Resolve não podem ser liberados nos MP4:
  ambos dependem do decodificador interno do Resolve (Sony só para MXF, giroscópio só para câmeras Blackmagic). O
  S-Log MetaRaw é o equivalente para os controles de cor, não uma porta de entrada.
- São necessários **S-Log2 ou S-Log3**. Com outros perfis o nó permanece neutro e avisa.
- Algumas câmeras não gravam a temperatura de cor: ela é estimada pela predefinição de luz e sinalizada.
- **S-Log2:** a fórmula segue o documento da Sony (cinza 18% no código 347). A curva S-Log2 que vem com o Resolve difere
  em cerca de 0,15 stop, então as duas não caem exatamente no mesmo ponto.
- Ainda a validar com mais arquivos: XAVC HS (HEVC), HLG e S-Cinetone, zooms motorizados, GPS.
- **Projeto independente e amador**, distribuído como está, sem garantias e sem qualquer responsabilidade pelo uso em
  contextos profissionais. O código é aberto: qualquer pessoa pode ler, testar e modificar.

---

## Créditos

**Ivan Mazzone + Claude** — [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).

Escrito junto com o **Claude Opus 5** (Anthropic): a versão 1.0 é de 19 de setembro de 2026, e a 1.0.1 do dia seguinte.

Referências para as tags da Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) (Sony.pm) e
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser), de AdrianEddy (MIT). Parte da tabela de tags vem
deste último.

Sony, XAVC e Catalyst são marcas da Sony Group Corporation; DaVinci Resolve é marca da Blackmagic Design. Projeto
independente, sem afiliação nem aprovação de nenhuma das duas empresas.

## Licença

[GNU General Public License v3.0 ou posterior](LICENSE). Software livre: você pode usar, estudar, modificar e
redistribuir; quem redistribuir, modificado ou não, deve fazê-lo sob a mesma licença e com o código-fonte disponível. Sem
garantia de nenhum tipo.

O SDK do OpenFX pertence à The Open Effects Association (BSD de 3 cláusulas) e parte da tabela de tags da Sony vem do
telemetry-parser (MIT): ambas compatíveis com a GPL-3.
