<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>面向 DaVinci Resolve 21 的索尼拍摄元数据与 Camera Raw 式调节</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <a href="README.it.md">Italiano</a> · <b>简体中文</b> · <a href="README.es.md">Español</a> · <a href="README.pt.md">Português</a>
</p>

---

## 初衷

相机在拍摄时已经把设置记录了下来：以开尔文表示的白平衡、tint、EI、镜头、快门、色彩描述文件。对于 FX6 的 MXF 文件，Resolve 会使用这些信息，并打开 **Camera Raw › Sony Video** 面板；而对于 FX30、FX3 或 a6300 的 MP4 文件，同样的信息就在文件里，Resolve 却视而不见。

S-Log MetaRaw 把这些信息读出来并重新派上用场：白平衡、曝光和色彩空间从相机真正记录的数值出发，而不是靠猜。不转码，也绝不写入原始文件。

它不是 raw。log 的 MP4 是已经显影并压缩过的图像，任何插件都无法把这一步倒回去。它能做的，是在实际录下来的图像上、在线性光下、依据公开的色彩科学，重新处理拍摄时做出的那些决定——也就是 raw 会允许你回头修改的那些。

| | |
|---|---|
| **脚本**（Workspace › Scripts） | **一次性读取项目中全部素材**（或仅选中的素材）的元数据，并写入媒体池：元数据面板、列、用于智能媒体夹的关键词、数据烧录、CSV 导出。它像 Catalyst Browse 那样分组展示读到的全部内容，并修正 Resolve 在 MXF 上填错的字段，例如 FX6 上 *Camera Aperture* 显示为 `F53343`。 |
| **插件**（OpenFX，Color 页面） | 逐个片段处理，就像手边有 Raw 面板：Color Temp、Tint、Exposure (EI)、White Balance、Color Space/Gamma 以及影调。它会依据该片段的拍摄数值**自动完成设置**，并且在这些数值上是中性的：只要你不动任何控件，画面就不会改变。它还会在 Resolve 用错标度读取片段时修正**数据电平**，用一条永不裁切的**胶片式肩部**显影高光，并提供三种**伪色**视图，让曝光与白平衡靠测量而不是靠眼睛来确定。 |

---

## 安装

1. 从 **Releases** 页面下载 `SLogMetaRaw-x.y.z.dmg` 并打开。
2. 双击 **Installa S-Log MetaRaw.pkg**。安装包未使用 Apple 证书签名，因此首次打开需右键点击并选择**打开**。
3. 重新启动 DaVinci Resolve。

安装程序只放三样东西：

| 路径 | 内容 |
|---|---|
| `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` | OpenFX 节点 |
| `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` | Python 库（解析器） |
| `…/Blackmagic Design/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` | 脚本的菜单项 |

使用过程中还会在 `~/Library/Application Support/SLogMetaRaw/cache` 为每个片段写入一份小的 JSON 记录，导出的 CSV 放在 `~/Documents/SLogMetaRaw`。磁盘映像中的 **Disinstalla S-Log MetaRaw.command** 可以把这些全部移除。映像里还有单页指南 **S-Log MetaRaw Guide (english).pdf** 与 **Guida S-Log MetaRaw (italiano).pdf**。

**系统要求：** macOS 12 或更高版本（Apple Silicon 或 Intel）与 DaVinci Resolve 21。**仅在 macOS 上的 Resolve Studio 21.1 中测试过。** 更早的版本未经测试：若系统已安装 Python 3，脚本或许可用（Resolve 自 21.1 起才自带解释器）；插件则依赖 Resolve 21 引入的功能，尤其是 OpenFX 1.5 色彩管理，在旧版本上需要手动设置 *Avanzate › Ingresso nodo*（高级 › 节点输入）。

**支持的素材：** 索尼 XAVC，`.MP4` 或 `.MXF`，以 **S-Log2 或 S-Log3** 拍摄。节点能够处理的描述文件为 `S-Gamut3.Cine/S-Log3`、`S-Gamut3/S-Log3`、`S-Gamut/S-Log2` 和 `S-Gamut/S-Log`。脚本可以读取任何索尼 XAVC 片段的元数据，无论是否 log；对于其他情况，节点保持中性。

---

## 使用指南

### 1 · 脚本

**Workspace › Scripts › S-Log MetaRaw。** 窗口里有三个按钮，按使用顺序排列。

- **Origine**（来源）——*Clip selezionate nel Media Pool*（媒体池中选中的片段）、*Bin corrente (con sottocartelle)*（当前媒体夹，含子文件夹）或 *Tutto il Media Pool*（整个媒体池）。
- **1 · Leggi metadata**（读取元数据）——读取片段，此时还不写入任何内容。表格中每个片段一行：片段名、机型、镜头、焦距、光圈、快门、ISO/EI、白平衡、色彩空间、data level，以及一列 *Stato*（状态），显示 `letto`（已读取），或 `letto · varia: diaframma, fuoco`（读取成功，但光圈、对焦在拍摄过程中有变化），或说明该片段为何被跳过。**点击某一行**，下方面板会按 Catalyst Browse 的分组显示读到的全部内容。
- **2 · Scrivi in Resolve**（写入 Resolve）——把元数据写进媒体池。
- **Esporta CSV (campi custom)**（导出 CSV，自定义字段）——把 Resolve 没有对应字段的数值写成 CSV，保存到 `~/Documents/SLogMetaRaw`（清单见下文）。

两个复选框：

- **Sovrascrivi i campi già compilati**（覆盖已有内容的字段），默认开启。正是它修正了 Resolve 自行写入的错误值，例如 FX6 的 MXF 上 *Camera Aperture* 为 `F53343`。关闭后只填写空白字段。
- **Correggi il Data Level**（修正数据电平），**默认开启**。根据拍摄伽马将每个片段的 *Data Level* 属性设为 Full 或 Video。这才是真正的修正：它修复的是整个项目的解码 —— CST、RCM、示波器、导出都包括在内，而不只是这个节点 —— 并且可以撤销。索尼的 log 曲线以未缩放的 code value 发布，需要 *Full*；Rec.709、Cine 和 HLG 需要 *Video*。逐机型的完整调研见 [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)。
- **Imposta anche Input Color Space (RCM) dai metadata**（同时根据元数据设置输入色彩空间），默认关闭。在色彩管理项目中很实用，但请注意：一旦由脚本设置，就无法再由脚本改回 *Project*，只能在 Resolve 中手动改。

原始文件永远不会被修改：脚本只做读取。

### 2 · 节点

**Color 页面 › OpenFX › S-Log MetaRaw**，作为**第一个节点**，放在 CST 和 LUT 之前。顶部显示机型，并把 Color Temp、Tint、Exposure 设为拍摄数值。在这些数值上它对画面不做任何处理：这是起点，不是风格。把节点复制到另一个片段上，它会按那个片段的数据重新设置自己。

| 控制项 | 范围 | 默认 | 作用 |
|---|---|---|---|
| **Rileggi metadata**（重新读取元数据） | — | — | 重新读取片段，并把所有控件恢复为相机数值 |
| **Decode Using** | Camera metadata / Clip | Clip | *Camera metadata* 将一切锁定在拍摄数值并置灰控件；*Clip* 允许修改 |
| **White Balance** | As shot · Daylight 5600 K · Cloudy 6500 K · Shade 7500 K · Tungsten 3200 K · Fluorescent 4000 K · Flash 5500 K · Custom | As shot | 预设；拖动滑块后切换为 *Custom* |
| **Color Temp** | 2000–15000 K | 拍摄值 | 在线性光下做色适应 |
| **Tint** | −100 … +100 | 拍摄值 | 绿/品红，垂直于普朗克轨迹 |
| **Exposure** | 25–409600 EI（滑块 50–25600） | 拍摄值 | 曝光指数：EI 加倍即 +1 档 |
| **False color：色温 / 色调 / 曝光** | 开 · 关 | 关 | 每个控件一个测量视图，各自位于所服务滑块的上方。曝光视图按 ARRI 方式以 18% 中灰为中心划分档位；两个白平衡视图**以开尔文和色调单位**读出与中性的距离，因此色带直接告诉你滑块还差多少。白色 = 中性。一次只能开一个，且该视图会替换画面：渲染前请关闭。[docs/FALSE_COLOR.md](docs/FALSE_COLOR.md) |
| **Color Space** | Timeline · DaVinci WG · Rec.709 · Rec.2020 · P3 D65 · P3 D60 · P3 DCI · S-Gamut · S-Gamut3 · S-Gamut3.Cine · ACES AP0 · ACES AP1 | Timeline | 输出色域，相当于 Color Space Transform。*Timeline* 不做转换 |
| **Gamma** | Timeline · DaVinci Intermediate · Linear · Gamma 2.2 · Gamma 2.4 · Gamma 2.6 · Rec.709 · sRGB · SLog · SLog2 · SLog3 · ACEScct | Timeline | 输出曲线。*Timeline* 不做转换 |
| **Toni › Highlights** | −100 … +100 | 0 | 以档为单位指明**所录制容器的顶端落在哪里**。负值把它压向一个永远达不到的渐近线，因此绝不裁切，18% 中灰仅移动 0.008 档。在 −100 时，S-Log3 中灰之上的 +7.74 档正好落在 1.0 线性值，即 Rec.709 信号所能容纳的峰值。正值则做镜像：把标度顶端拉伸最多 2 档，把尚未到达峰值就饱和的高光重新提到峰值。行程在滑块上是**线性的**，每一格的份量相同 |
| **Toni › Shadows** | −100 … +100 | 0 | 在 −4 档附近打开或压暗暗部细节。它是乘性增益，因此任何设置下绝对黑仍为黑，−8 档以下的趾部原样不动 |
| **Toni › Color Recovery** | −100 … +100 | 0 | 压制还回多少色彩。它是同一条曲线两种施加方式之间的权重：对三个通道施加同一个系数，完整保留场景色彩；以及逐通道施加，三个通道共用一个上限，上升时彼此收敛——因为收敛**就是**去饱和，胶片正是这样做的。向右保留色彩，向左趋近胶片。它绝不会添加像素本来没有的色彩。这是让恢复后的天空褪去霓虹感、让明亮额头不变成死板粉色的有机手段。[docs/TONE_MAPPING.md](docs/TONE_MAPPING.md) |
| **Toni:** Color Boost、Saturation、Contrast | −100 … +100 | 0 | 色彩与对比度微调 |
| **Avanzate › Ingresso nodo**（高级 › 节点输入） | Automatico · DaVinci WG/Intermediate · S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · ACES AP1/ACEScct | Automatico | 进入节点的色彩空间。*Automatico* 向 Resolve 询问；只有当 Resolve 给出的答案不对时才手动更改 |
| **Avanzate › Data level in ingresso**（高级 › 输入数据电平） | Automatico · Full (0-1023) · Video (64-940) · Nessuna correzione | Automatico | Resolve 解码该片段所用的 code value 标度。*Automatico* 读取片段的 Data Level 属性；只要它仍为 *Auto*，就不做任何修正，因为 Resolve 实际采用的值无法通过任何 API 读取。对于没有任何 NLE 能正确标记的文件（例如同一条素材的 Atomos ProRes），请手动声明 — 参见 [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md) |
| **Avanzate › Rilevato / Data level / Stato**（检测结果 / 数据电平 / 状态） | — | — | 检测到了什么、正在使用哪种标度及其原因，以及是否找到了元数据 |
| **Dati di ripresa**（拍摄数据） | — | — | 只读：镜头、焦距、光圈、对焦、快门、ISO/EI、白平衡、色彩、帧率、ND/防抖、机内 LUT、文件 |

节点按片段保存设置：它们随调色一起保存，回到该片段时会恢复。只有切换到另一个片段，或按下 *Rileggi metadata*，才会重置。

### 3 · 一套可行的流程

1. 导入素材，运行脚本，依次按 **1** 和 **2**。
2. 在 Color 页面把 **S-Log MetaRaw** 放在第一位；若项目启用了色彩管理，就让 *Color Space* 与 *Gamma* 保持 *Timeline*，随后接上你惯用的 CST 或 LUT。
3. 白平衡和曝光**在节点里**调整，而不是用 lift/gamma/gain：节点里的调整发生在线性光下、任何曲线之前，也就是相机当初会做这件事的位置。

---

## 会写入 Resolve 的内容

**标准字段**，只有片段中确实存在该数值时才填写：

`Camera Manufacturer` · `Camera Type` · `Camera TC Type` · `Camera Serial #` · `Camera Firmware` · `Camera FPS` ·
`Shutter Type` · `Shutter Angle` · `Shutter Speed` · `Exposure Mode` · `ISO` · `White Point (Kelvin)` ·
`White Balance Tint` · `Mon Color Space` · `Monitor LUT` · `LUT Used` · `Lens Type` · `Lens Number` · `Lens Notes` ·
`Camera Aperture Type` · `Camera Aperture` · `Focal Point (mm)` · `Distance` · `ND Filter` · `Codec Bitrate` ·
`Sensor Area Captured` · `PAR Notes` · `Aspect Ratio Notes` · `Gamma Notes` · `Color Space Notes` · `Date Recorded`

**Camera Notes** 会得到一段便于阅读的摘要；**Keywords** 会得到机型、gamma、色彩基色，以及片段为升降格拍摄时的 `S&Q`——这些正是智能媒体夹所需要的。读到的全部内容（包括没有标准字段可放的数值）还会以 `SLogMetaRaw.` 前缀作为第三方元数据附加到片段上。

**Input Color Space**（仅在你勾选复选框时）按下表映射：

| 片段中的记录 | 在 Resolve 中设置为 |
|---|---|
| S-Gamut3.Cine/S-Log3 · S-Gamut3/S-Log3 · S-Gamut/S-Log2 · S-Gamut/S-Log | 同名 |
| ITU-R BT.2100 HLG · HLG Live · HLG Mild | Rec.2100 HLG |
| S-Cinetone · ITU-R BT.709-5 | Rec.709 (Scene) |

**CSV 导出**涵盖 Resolve 没有字段可放的内容：EI、ISO、增益、白平衡模式、光源预设、tint、AE 模式、AF 区域、35mm 等效焦距、对焦距离、色彩空间、拍摄 gamma、luminance code range、编码 range、防抖、监看 LUT、录制模式、拍摄帧率、录制时间、格式。文件采用 Resolve 自身的元数据 CSV 格式（UTF-16）；通过 **File › Import › Metadata** 导入，并启用创建自定义字段的选项。

---

## 工作原理

### 数据在哪里，以及只读取了多少

索尼 XAVC 文件**逐帧**记录拍摄数据：

- **MP4** 保存在 `rtmd` 定时元数据轨中；
- **MXF** 保存在 SMPTE ST 436 ANC 包中（DID 0x43 / SDID 0x05）。

两者都是 KLV 结构，承载 **SMPTE RDD 18** 采集集合，外加索尼自有标签。与之并列的还有 *NonRealTimeMeta* XML（`M01.XML` 伴随文件或内嵌副本），提供机型、机身序列号、固件、拍摄 gamma 与色彩基色；以及 H.264/HEVC 的 **SPS**，提供 profile、位深与全/有限范围。

解析器读取文件索引，并**每秒采样一次元数据轨，最多 120 个样本**。正因如此，*Stato* 列才能告诉你光圈或对焦在拍摄过程中发生了变化；也正因如此，一个几 GB 的片段只需约 **100 KB 的读取量**：不解码任何内容，也不渲染任何一帧。

全部用纯 Python 编写，没有外部依赖，不需要 ExifTool，除了软件包本身无需安装任何东西。

### 从脚本到节点

脚本使用 Resolve 21.1 的脚本 API（Resolve 自带 Python 3.14）。除了媒体池字段，每个片段还会在 `~/Library/Application Support/SLogMetaRaw/cache` 得到一份扁平的 JSON 记录，文件名由片段路径的哈希生成。

节点通过 Resolve 的 `kOfxImageEffectPropSrcFilePath` 扩展得知片段对应的文件，并读取那份记录——它就是这样完成自我设置的。若记录不存在，便对该片段运行 `ResolvePython -m slogmetaraw --cache` 自行生成。这个读取过程运行在界面线程上，因此被严格约束：最多 8 秒、每个片段只尝试一次，而磁盘上仅为云端占位符的文件会被跳过而不是下载。节点的工作色彩空间由 Resolve 通过 OpenFX 1.5 色彩管理提供。

### 色彩计算

全部在**线性光**下、在进入节点的色域中，按以下顺序进行：

1. **解码**输入曲线，并乘以曝光比 `所选 EI / 拍摄 EI`——EI 加倍恰好是一档。
2. **白平衡**：在 **Bradford LMS** 空间中做 von Kries 色适应，从拍摄白点变换到所选白点。两个白点都取自**普朗克轨迹**（Kim 等人 2002 年的三次近似，适用范围 1667–25000 K）；*Tint* 在 CIE 1960 *uv* 平面上沿垂直于轨迹的方向移动白点。结果经过归一化，使这一变换不改变 D65 的亮度。
3. **影调**：`Shadows`、`Highlights` 和 `Contrast` 作用于以 18% 灰为中心的 log2 亮度，暗部与亮部的权重在五档的范围内衰减为零，因此它们只作用在该作用的地方，而不会把整幅画面一起抬起或压下。
4. **Saturation 与 Color Boost**：围绕亮度做缩放；Color Boost 是一种 vibrance，按每个像素已有的饱和度加权，因此提升那些寡淡的颜色，而不去动本来就浓的颜色。
5. **Color Space / Gamma**：若其中任一与节点所处的空间不同，就经由 XYZ 做一次转换，与 Color Space Transform 完全一致；否则图像按进入时的曲线重新编码。
6. **色域**：编码前的最后一步。落在输出空间之外的颜色不是一种风格，而是在那里无法存在的信号——一盏饱和的舞台 LED 从 S-Gamut3.Cine 转到 Rec.709，实测为 R −0.125、G −0.292——而任何色调控件都修不好它，因为压制对三个通道乘以的是同一个**正**系数。每个通道与消色轴的距离被压向一条永远达不到的渐近线，而那条线恰好就是该通道归零的位置：**节点不可能输出负通道**。在色域之内它什么都不做——不是"改动很小"，而是完全不动：色域内的颜色位于阈值之下，进来什么样就原样输出。

传递函数遵循公开定义：**S-Log、S-Log2 与 S-Log3** 来自索尼技术文档，另有 **DaVinci Intermediate**、**ACEScct**、**Rec.709**（BT.709 OETF）、**sRGB** 以及纯 gamma 2.2 / 2.4 / 2.6。色域矩阵（含各自的逆矩阵）覆盖 DaVinci Wide Gamut、Rec.709、Rec.2020、P3 D65/D60/DCI、S-Gamut、S-Gamut3、S-Gamut3.Cine、ACES AP0 与 AP1（如索尼文档所述，S-Gamut3 与 S-Gamut 使用相同的基色）。

这些计算集中在一个文件 `DevelopMath.h` 中，由 `tools/build_math.py` 生成，并**同时**编译为 C++ 与 **Metal** 内核，因此 GPU 与 CPU 两条路径不可能各走各的。渲染在 Metal 上运行，并提供 CPU 回退。

当相机没有记录色温时（例如 a6300），数值会由它确实记录下来的光源预设推得（Daylight 5600 K、Cloudy 6500 K、Shade 7500 K、Incandescent 3200 K、Fluorescent 4000 K，其余为 5600 K），并在状态行和拍摄数据中标注为估算值。

### 已完成的验证

- 在 FX6、FX30 和 a6300 上，与 Catalyst Browse **逐字段比对**标签与数值。
- **三套实现互相吻合。** Python 参考模型、C++ 代码与 Metal 内核在参数与色彩空间的随机扫描下，差异在 **2·10⁻⁴** 以内。
- **在 Resolve 内部**：从节点导出的 LUT 与同一模型比对，误差低于 **0.0003**。
- **一个微型 OpenFX 宿主**（`tests/host_test.cpp`）加载编译好的插件，执行 Resolve 会执行的动作——加载、描述、两个上下文、在真实片段上构建节点——使节点面板的崩溃暴露在这里，而不是在 Resolve 中。
- 合计 25 项自动化测试：解析器、显影模型、C++、Metal、OpenFX 宿主、插件参数。

---

## 从源码编译

```bash
make -C ofx/SLogMetaRaw                     # arm64 + x86_64 通用插件（需要 Xcode）
./install.sh --dev                          # 安装脚本与插件，指向当前目录
python3 -m unittest discover -s tests       # 25 项测试
./packaging/build_installer.sh              # 生成 dist/SLogMetaRaw-x.y.z.dmg
python3 -m slogmetaraw 文件夹或文件           # 命令行下的 Catalyst 风格视图
python3 -m slogmetaraw --cache clip.MP4     # 只写入节点所读取的 JSON 记录
```

```
slogmetaraw/         mp4、mxf、rtmd、nrt、codec 解析器 · 写入 Resolve · 脚本窗口
resolve_script/      Workspace › Scripts 的启动器
ofx/SLogMetaRaw/     OpenFX 插件（C++、Metal）；DevelopMath.h 由 tools/build_math.py 生成
tools/               色域矩阵、生成脚本、图标
tests/               测试（示例素材不在仓库中）
packaging/           安装程序：安装包、PDF 指南、卸载脚本
```

---

## 已知限制

- Resolve **真正的** Camera Raw 面板与**陀螺仪稳定**无法在 MP4 上启用：两者都取决于 Resolve 内部的解码器（索尼仅限 MXF，陀螺仪仅限 Blackmagic 相机）。S-Log MetaRaw 是色彩控制方面的等价方案，而不是一把打开它们的钥匙。
- 需要 **S-Log2 或 S-Log3**。使用其他描述文件时，节点保持中性并给出提示。
- 部分机型不记录色温：数值会依据光源预设估算，并标注出来。
- **S-Log2：** 公式遵循索尼技术文档（18% 灰对应码值 347）。Resolve 自带的 S-Log2 曲线约有 0.15 档差异，因此两者落点并不完全一致。
- 有待用更多文件验证：XAVC HS（HEVC）、HLG 与 S-Cinetone、电动变焦、GPS。
- **独立的业余项目**，按现状分发，不提供任何担保，对专业用途不承担任何责任。代码是开放的：任何人都可以阅读、测试和修改。

---

## 致谢

**Ivan Mazzone + Claude** — [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m)。

与 **Claude Opus 5**（Anthropic）共同编写：1.0 版日期为 2026 年 9 月 19 日，1.0.1 为次日，1.1.0 为 2026 年 9 月 22 日。更新日志见 [RELEASE_NOTES.md](RELEASE_NOTES.md)。

索尼标签的参考资料：SMPTE RDD 18、[ExifTool](https://exiftool.org)（Sony.pm）以及 AdrianEddy 的
[telemetry-parser](https://github.com/AdrianEddy/telemetry-parser)（MIT）。标签表的一部分来自后者。

Sony、XAVC 和 Catalyst 是 Sony Group Corporation 的商标；DaVinci Resolve 是 Blackmagic Design 的商标。本项目为独立项目，与上述两家公司均无从属关系，也未获其认可。

## 许可证

[GNU General Public License v3.0 或更高版本](LICENSE)。自由软件：你可以使用、研究、修改和再分发；任何人再分发时（无论是否修改），都必须采用同一许可证并提供源代码。不提供任何形式的担保。

OpenFX SDK 归 The Open Effects Association 所有（三条款 BSD），索尼标签表的一部分来自 telemetry-parser（MIT）：两者都与 GPL-3 兼容。
