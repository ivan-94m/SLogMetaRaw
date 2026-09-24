<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>Metadados de câmeras Sony e controles de revelação em luz de cena para o DaVinci Resolve 21</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <a href="README.it.md">Italiano</a> · <a href="README.es.md">Español</a> · <b>Português</b> · <a href="README.zh.md">简体中文</a>
</p>

---

## O que é

As câmeras Sony gravam em cada arquivo como o plano foi filmado: balanço de branco em Kelvin, tint, EI, objetiva,
abertura, obturador, perfil de cor. O Resolve usa esses dados nos MXF da FX6 e da FX9, que ganham o painel *Camera Raw*.
Nos MP4 de uma FX30, FX3, série a7 ou a6000, ignora-os.

O S-Log MetaRaw lê esses dados e usa-os. Tem três partes:

| | Onde | O que faz |
|---|---|---|
| **Script** | Workspace › Scripts › S-Log MetaRaw | lê os metadados de todos os clipes do projeto e grava-os no Media Pool |
| Nó **S-Log MetaRaw** | Color › OpenFX | revela um clipe a partir dos valores de gravação: balanço, exposição, espaço de cor, tons por zonas, falsa cor |
| Nó **S-Log MetaRaw Detail** | Color › OpenFX | o nó criativo: recuperação local de tons, Texture, Clarity, Dehaze |

Nenhum arquivo é transcodificado e nenhum original é alterado.

### O que esperar, com honestidade

**Não é raw.** Um MP4 log já está demosaicado e comprimido, em 8 ou 10 bits, muitas vezes 4:2:0, com a redução de ruído
da câmera já aplicada. Nenhum plugin consegue devolver o que a câmera descartou.

O que o nó faz é aplicar a ciência de cor com rigor. Exposição e balanço trabalham em luz linear, partem dos valores que
a câmera registrou e seguem curvas e gamuts publicados. Os tons movem a imagem em stops. Trabalhada assim, uma imagem log
**comporta-se de um modo que lembra um arquivo RAW**: o balanço desloca-se limpo, a exposição move-se como um stop de
luz e as altas luzes arredondam em vez de quebrar.

Num trabalho intenso, porém, a ciência de cor sozinha não chega. Assim que os limites da câmera são forçados, a falta de
informação na imagem aparece: banding nos céus, ruído nas sombras levantadas, altas luzes estouradas que continuam
estouradas, cor que se desfaz nos canais comprimidos. Exponha bem na gravação. O S-Log MetaRaw ajuda a tirar o melhor do
que existe. Não pode criar o que não existe.

---

## Instalação

1. Baixe `SLogMetaRaw-2.0.1.dmg` em **Releases** e abra-o.
2. Dê um duplo clique em **Installa S-Log MetaRaw.pkg**. Não está assinado com um certificado da Apple: na primeira vez,
   clique com o botão direito › **Abrir**. Pede a senha do Mac porque o plugin vai para uma pasta do sistema.
3. Reinicie o DaVinci Resolve.

O instalador também apaga o cache de plugins do Resolve (`OFXPluginCacheV2.xml`), que o Resolve reconstrói na próxima
inicialização. Sem isso, o Resolve continuaria mostrando o painel antigo e não veria o nó Detail.

| Instalado | Caminho |
|---|---|
| Os dois nós (um único bundle) | `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` |
| A biblioteca Python | `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` |
| O script do menu | `…/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` |

Enquanto funciona, guarda um pequeno registro JSON por clipe em `~/Library/Application Support/SLogMetaRaw/cache`. O
disco também traz os guias de três páginas, em italiano e inglês.

**Instalação limpa e desinstalação.** Cada instalação começa limpa: o instalador substitui por inteiro o plugin e a
biblioteca anteriores e remove as instalações de desenvolvimento, então não fica nenhum arquivo de uma versão antiga.
**Disinstalla S-Log MetaRaw.command**, no disco (na primeira vez: botão direito › Abrir), remove todas as versões
instaladas, 1.x e 2.x incluídas, com o cache, as configurações e os logs. Antes de mexer em algo lista tudo, pede para
fechar o Resolve e pergunta se deve apagar também os CSV exportados. Os metadados já gravados nos projetos do Resolve
fazem parte dos projetos e ficam.

**Requisitos:** macOS 12 ou posterior, Apple silicon ou Intel, e DaVinci Resolve 21. **Testado apenas no Resolve Studio
21.1 em macOS.**

**Clipes:** Sony XAVC em `.MP4` ou `.MXF`. O script lê todos. Os nós revelam **S-Log3** (S-Gamut3.Cine ou S-Gamut3),
**S-Log2** e **S-Log** (S-Gamut). Com outros perfis ficam neutros e avisam.

---

## Em resumo

1. Importe o material. **Workspace › Scripts › S-Log MetaRaw**: clique **1 · Ler metadados** e depois
   **2 · Gravar no Resolve**.
2. Na página Color, coloque o **S-Log MetaRaw** como **primeiro nó**. Ele pega o EI, os Kelvin e o tint do clipe. Nesses
   valores não muda nada.
3. Corrija balanço e exposição no nó. As vistas de falsa cor ajudam.
4. Molde os tons com **Toni** (Tons). Para recuperação local, Texture, Clarity ou Dehaze, acrescente o
   **S-Log MetaRaw Detail** como nó seguinte.
5. Depois, o seu CST, LUT ou DRT.

```
S-Log MetaRaw  →  S-Log MetaRaw Detail  →  CST / LUT / DRT  →  resto da correção
```

---

## O script

A janela tem uma linha de botões, uma de opções e a lista de clipes, e segue o idioma do Resolve (português, inglês,
italiano, espanhol, chinês simplificado). Os painéis dos nós estão em italiano: abaixo, os rótulos vêm com tradução.

- Um menu escolhe os clipes: *Todo o Media Pool* ou *Clipes selecionados no Media Pool*.
- **1 · Ler metadados**: uma linha por clipe com câmera, objetiva, abertura, obturador, EI, WB, espaço de cor e
  data level. A coluna *Estado* diz `lido`, o que mudou durante a tomada (abertura, foco…) ou por que um
  clipe foi pulado. Clique numa linha para ver tudo o que foi lido, agrupado como no Catalyst Browse.
- **2 · Gravar no Resolve**: preenche os campos do Media Pool (painel Metadata, colunas, palavras-chave para smart
  bins, data burn-in) e corrige valores que o Resolve lê errado dos MXF, como *Camera Aperture* `F53343` na FX6.
- **Exportar CSV**: exporta os valores para os quais o Resolve não tem campo (EI, tint, modo WB, distância de foco, gama
  de captura…) no formato CSV de metadados do próprio Resolve.
- Opções:
  - **Tag por câmera** (desligada): acrescenta câmera, gama e primárias às palavras-chave.
  - **Sobrescrever metadados** (ligada): substitui os valores que o Resolve já gravou; desligada, preenche só os campos
    vazios.
  - **Corrigir o Data Level** (ligada): coloca o *Data Level* de cada clipe em Full ou Video, conforme a gama exige. O
    porquê está em [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md).
  - **Definir também Input Color Space** (desligada): para projetos com gerenciamento de cor.
    Um script não consegue voltá-lo para *Project*: só você, à mão.
- A versão no canto inferior direito, clicada, consulta o GitHub.

A leitura é rápida porque nada é decodificado: no máximo 24 amostras da faixa de metadados por clipe, com limite de um
segundo. Um volume que para de responder é pulado uma única vez, com um aviso, em vez de travar a lista.

---

## O nó S-Log MetaRaw

O nó é pontual: cada pixel depende só de si mesmo. Nunca cria halos e o **Generate LUT** pode exportá-lo
(recomendados 65 pontos).

| Controle | O que faz |
|---|---|
| **Versão** (no topo) | `v2.0.1`. Uma vez por dia pergunta ao GitHub pela última release. Se houver, mostra **🟢 v2.0.1 → 2.x.y** e o clique abre o download do DMG no navegador. Nunca instala nada sozinho |
| **Camera** · **Rileggi metadata** | a câmera lida. *Rileggi* (reler) lê o clipe de novo, devolve cada controle aos valores da câmera e grava os metadados do clipe no Media Pool |
| **Decode Using** | *Clip* permite mudar os controles; *Camera metadata* trava-os nos valores de gravação |
| **White Balance** · **Color Temp** · **Tint** | As shot ou presets. Adaptação cromática Bradford em luz linear, a partir do branco que a câmera registrou |
| **Exposure** | índice de exposição: o dobro do EI = +1 stop |
| **False color** | temperatura, tint e exposição; veja abaixo |
| **Color Space** · **Gamma** | saída, como um Color Space Transform; *Timeline* não converte |
| **Toni** (Tons) | Contrast, Highlights, Shadows, Whites, **Bianco** (branco, em stops), Blacks, Vibrance, Saturation (−100…+100) |
| **Zone** (Zonas, fechado) | zonas Black, Shadow, Light e Specular com Exp (stops), Sat, Range e Falloff; Contrast Pivot; Soft Clip; falsa cor *Zone* |
| **Avanzate** (Avançado) | entrada do nó, correção do data level, estado, **Sblocca controlli senza metadata** (desbloquear sem metadados) |
| **Dati di ripresa** (dados de gravação) | só leitura: objetiva, focal, abertura, foco, obturador, EI, WB, fps, ND, LUT da câmera |

**Highlights é um ombro de película.** Em negativo comprime as altas luzes com uma inclinação que diminui de forma
contínua para cima, como a película, o ACES 2.0 e o AgX. A −100 o valor mais alto que a câmera registrou (cerca de +6 stops
acima do cinza em S-Log3) chega exatamente ao **Bianco**: sem véu cinza e sem clip. O cinza e o que está abaixo não se
movem, e a pele a +1 stop se desloca no máximo 0,05 stop. As luzes mais comprimidas vão suavemente para o branco sem mudar
de matiz. Em positivo dá mais força às altas luzes, com inclinação limitada. **Bianco** é onde esse máximo chega (e o teto do
Soft Clip): 2,5 stops é o branco Rec.709 com um CST sem tone mapping. Com um DRT depois do nó (ACES, AgX, DaVinci), suba
para 4–5, senão as altas luzes são comprimidas duas vezes.

**Tons por zonas.** Shadows, Whites e as Zonas são exposições, em stops, sobre uma faixa de tons: Shadows abaixo de −1 stop,
Whites a partir de +3,5 stops. Blacks é um véu linear que move o preto sem mover o cinza. Dentro de uma zona a imagem se
move como numa exposição, então a textura se mantém, e a compressão fica numa faixa de transição declarada. Nenhuma
combinação de controles pode solarizar. O custo de um nó pontual, dito claramente: o que ele comprime, comprime também na
textura. Por isso a recuperação local é um nó separado. Fórmulas e receitas: [docs/TONE_MAPPING.md](docs/TONE_MAPPING.md).

**Falsa cor.** Uma vista por controle, acima do controle deslizante a que serve:
- **Exposição** usa faixas em stops em torno do cinza 18%, no estilo ARRI. Verde é o cinza médio, rosa um stop acima (a
  pele), amarelo perto do clip, vermelho o clip, azul e violeta o fundo.
- **Temperatura** e **Tint** funcionam como no CineMatch. A imagem fica cinza, as dominantes ganham laranja/azul ou
  verde/magenta, e as quase neutras são amplificadas até 8× para aparecerem. Mova o controle até o que deve ser neutro
  ficar cinza. Cada vista responde só ao seu controle.

A vista substitui a imagem: desligue-a antes de renderizar. [docs/FALSE_COLOR.md](docs/FALSE_COLOR.md)

**Data level.** Se o Resolve decodifica um clipe na escala de code values errada, o nó corrige antes da curva log. A
opção *Corrigir o Data Level* do script resolve isso para o projeto inteiro. [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)

**Sem metadados.** Um ProRes de gravador externo, ou um clipe que não pode ser lido, deixa o nó neutro. Marque
*Avanzate › Sblocca controlli senza metadata* e digite o EI, os Kelvin e o tint de gravação: os controles se ativam e o
nó começa neutro.

**Velocidade.** Abrir um projeto não lê nenhum arquivo. Abrir o painel espera no máximo meio segundo; um disco lento
termina em segundo plano, com limite de 15 segundos. *Rileggi* responde em cerca de 2 segundos no máximo.

---

## O nó S-Log MetaRaw Detail

É o nó criativo. Trabalha **por áreas**, sobre uma base que respeita as bordas, e ajusta as grandes áreas sem achatar o
detalhe fino. É a parte de Highlights e Shadows do Lightroom que um nó pontual não consegue copiar.

| Grupo | Controles |
|---|---|
| **Gamma dinamica** (faixa dinâmica) | Local Contrast, Local Highlights, Local Shadows; vistas de *ganho* e *base*. Local Highlights comprime as grandes áreas claras e mantém, até reforça, a textura fina: o céu escurece e as nuvens mantêm o detalhe. O Highlights do nó principal, ao contrário, suaviza a textura das altas luzes, como a película |
| **Presenza** (presença) | Texture, Clarity, Dehaze |
| **Zone locali** (zonas locais) | as zonas do nó principal, aplicadas às áreas |
| **Avanzate** (avançado) | preservação do detalhe, raio, limiares de bordas e ruído, centro do Clarity, **Bianco** do Local Highlights, entrada do nó |
| **Velo** (véu) | nível e cor do véu que o Dehaze remove: quem decide é você, nunca são estimados quadro a quadro |

- Coloque-o **logo depois** do S-Log MetaRaw, antes de CST, LUT ou DRT. Ele decodifica para luz linear o que recebe e
  grava de volta na mesma codificação, então vai antes de qualquer conversão: deixe Color Space e Gamma do nó principal em
  Timeline.
- É **espacial**, por isso o Generate LUT o exclui, junto com o resto do seu nó. Mantenha-o num nó próprio.
- Os raios seguem a altura do quadro. O visual é o mesmo em resolução total, em proxy e no visor. Sem estatísticas por
  quadro, portanto sem flicker.
- No Metal um quadro UHD leva cerca de 6–18 ms, medidos em Apple silicon. A alternativa por CPU é bem mais lenta.

**Os seus limites, medidos.** Com Local Highlights −100 o halo no lado escuro de uma borda fica abaixo de 3% do degrau.
Com Local Shadows ou as zonas locais a ±100, numa borda nítida de um stop o halo chega a cerca de 12% do degrau, e a 4–6% em
degraus de 2–3 stops. Se o vir, baixe *Soglia bordi* (limiar de bordas). Texture não sobe o grão abaixo do limiar de
ruído, mas junto a bordas fortes o grão pode crescer 1,25–1,7 vezes. O Dehaze precisa de um véu real para remover.
[docs/DETAIL.md](docs/DETAIL.md)

---

## Atualizações e privacidade

- Os **nós** perguntam ao GitHub pela última release deste projeto no máximo uma vez por dia, em segundo plano. A
  requisição leva só a versão do programa (`User-Agent: SLogMetaRaw/2.0.1`). Para desativar, crie o arquivo vazio
  `~/Library/Application Support/SLogMetaRaw/no_update_check`.
- O **script** só consulta quando você clica na sua versão.
- Um clique apenas abre um link de download das releases do GitHub deste projeto. Nada é instalado sem você.

---

## Como funciona, em resumo

- **Metadados.** Os parsers são Python puro, sem dependências. Leem os metadados de aquisição SMPTE RDD 18 quadro a quadro
  (faixa `rtmd` dos MP4, pacotes ST 436 dos MXF), o XML NonRealTimeMeta da Sony, o SPS H.264/HEVC e o descritor de imagem
  MXF. Um clipe de vários gigabytes custa cerca de 100 KB de leitura.
- **Do script ao nó.** Cada clipe tem um registro JSON no cache. O nó encontra o seu arquivo pelo caminho de origem que o
  Resolve lhe passa, lê o registro e, se faltar, cria-o em segundo plano.
- **Matemática da cor.** A cadeia é: decodificação da curva da câmera, razão de EI, balanço Bradford a partir do lócus de
  Planck (com o tint perpendicular em CIE 1960 uv), depois tons com um único ganho por pixel a partir de uma norma dos
  seus canais (a cromaticidade se mantém), depois cor, depois saída. Tudo em luz linear, com as curvas e gamuts
  publicados pela Sony.
- **Uma matemática, três implementações.** A matemática fica em `ofx/SLogMetaRaw/math` e é compilada como C++ e como
  Metal. Um modelo Python de referência verifica as duas: CPU e GPU concordam dentro de 2·10⁻⁴, com FMA desativado em
  todos os caminhos.
- **Testes.** 322 testes automáticos: parsers, modelos de referência, C++, Metal, um host OpenFX em miniatura que carrega
  os dois nós como o Resolve faz, e arquivos golden dos painéis.

---

## Compilar a partir do código

```bash
make -C ofx/SLogMetaRaw                     # plugin universal, arm64 + x86_64 (requer Xcode)
make -C ofx/SLogMetaRaw test-bins           # binários de teste
python3 -m unittest discover tests          # os testes
./install.sh --dev                          # script e plugin apontando para esta pasta
./packaging/build_installer.sh              # dist/SLogMetaRaw-<versão>.dmg
python3 -m slogmetaraw clip.MP4             # leitura estilo Catalyst pela linha de comando
```

```
slogmetaraw/         parsers, gravação no Resolve, janela do script, verificação de atualizações
resolve_script/      lançador para Workspace › Scripts
ofx/SLogMetaRaw/     math/ (compartilhada CPU/Metal), src/ (common, develop, detail), metal/
tools/               geradores de matrizes, ícones e gráficos
tests/               testes e modelos de referência (os clipes de teste não estão no repositório)
packaging/           instalador, guias, desinstalador
docs/                TONE_MAPPING, DETAIL, FALSE_COLOR, DATA_LEVELS
```

---

## Limites conhecidos

- O painel Camera Raw do Resolve e a estabilização por giroscópio não podem ser desbloqueados para MP4: vivem dentro dos
  decodificadores do Resolve. O S-Log MetaRaw reconstrói os controles de cor; não abre uma porta dentro do Resolve.
- Algumas câmeras (entre elas a a6300) não registram os Kelvin: nesse caso são estimados a partir do preset de luz e
  sinalizados.
- O S-Log2 segue o documento da Sony. A curva S-Log2 do Resolve difere em cerca de 0,15 stop.
- Ainda por verificar em mais arquivos: XAVC HS (HEVC), HLG, S-Cinetone, zooms motorizados.
- **Um projeto independente e amador**, distribuído como está, sem garantia e sem responsabilidade pelo uso profissional.
  O código é aberto: leia, teste, altere.

---

## Créditos e licença

**Ivan Mazzone + Claude** · [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m).
Escrito com o Claude (Anthropic): a 1.0 em 19 de setembro de 2026, a 1.1.0 em 22 de setembro, a 2.0.0 em 23 de setembro
de 2026. A história completa está em [RELEASE_NOTES.md](RELEASE_NOTES.md) (em italiano).

Referências para as tags Sony: SMPTE RDD 18, [ExifTool](https://exiftool.org) e
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser) de AdrianEddy (MIT), de onde vem parte da tabela de
tags.

[GNU GPL v3.0 ou posterior](LICENSE). O SDK OpenFX é © The Open Effects Association (BSD-3). Sony, XAVC e Catalyst são
marcas da Sony Group Corporation; DaVinci Resolve é uma marca da Blackmagic Design. Projeto independente, não afiliado nem
endossado por nenhuma das duas empresas.
