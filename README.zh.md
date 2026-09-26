<p align="center"><img src="assets/icon_1024.png" width="140" alt="S-Log MetaRaw"></p>

<h1 align="center">S-Log MetaRaw</h1>
<p align="center"><b>为 DaVinci Resolve 21 提供索尼摄影机元数据与场景线性显影控制</b><br>
Ivan Mazzone + Claude · <a href="https://github.com/ivan-94m">github.com/ivan-94m</a> · <a href="https://instagram.com/ivan_94m">@ivan_94m</a></p>

<p align="center">
<a href="README.md">English</a> · <a href="README.it.md">Italiano</a> · <a href="README.es.md">Español</a> · <a href="README.pt.md">Português</a> · <b>简体中文</b>
</p>

---

## 这是什么

索尼摄影机会把拍摄设置写进每个文件：以开尔文表示的白平衡、色调（Tint）、EI、镜头、光圈、快门、色彩配置。Resolve
会读取 FX6、FX9 的 MXF 文件中的这些数据，并为其提供 *Camera Raw* 面板；但对于 FX30、FX3、a7 或 a6000 系列的 MP4
文件，它会忽略这些数据。

S-Log MetaRaw 读取并使用这些数据，由三部分组成：

| | 位置 | 作用 |
|---|---|---|
| **脚本** | Workspace › Scripts › S-Log MetaRaw | 读取项目中所有片段的元数据并写入媒体池 |
| **S-Log MetaRaw** 节点 | Color › OpenFX | 以拍摄时的数值为起点显影单个片段：白平衡、曝光、色彩空间、分区影调、伪色 |
| **S-Log MetaRaw Detail** 节点 | Color › OpenFX | 创意节点：局部影调恢复、Texture、Clarity、Dehaze |

不转码任何文件，也从不写入任何原始文件。

### 坦诚地说，能期待什么

**它不是 RAW。** Log MP4 已经过去马赛克和压缩，8 或 10 位，通常为 4:2:0，并且已烘焙了机内降噪。任何插件都无法找回摄影机丢弃的信息。

节点所做的，是严谨地应用色彩科学。曝光和白平衡在线性光中工作，以摄影机记录的数值为起点，遵循公开的曲线和色域；影调以档（stop）为单位移动画面。这样处理后，Log 画面**的表现会让人联想到 RAW 文件**：白平衡移动干净，曝光像一档光那样变化，高光平滑过渡而不是断裂。

但在大幅度调整时，仅靠色彩科学是不够的。一旦超出摄影机的极限，画面中缺失的信息就会显现：天空出现色带，提亮的阴影出现噪点，过曝的高光依然过曝，颜色在压缩通道中崩散。请在拍摄时正确曝光。S-Log MetaRaw 帮你充分利用已有的信息，但无法创造不存在的信息。

---

## 安装

1. 从 **Releases** 下载 `SLogMetaRaw-2.1.1.dmg` 并打开。
2. 双击 **Installa S-Log MetaRaw.pkg**。安装包未使用 Apple 证书签名：第一次请右键点击并选择**打开**。因为插件要放入系统文件夹，安装时会要求输入 Mac 密码。
3. 重启 DaVinci Resolve。

安装程序还会删除 Resolve 的插件缓存（`OFXPluginCacheV2.xml`），Resolve 会在下次启动时重建。否则 Resolve 会继续显示旧面板，也看不到 Detail 节点。

| 安装内容 | 路径 |
|---|---|
| 两个节点（同一个 bundle） | `/Library/OFX/Plugins/SLogMetaRaw.ofx.bundle` |
| Python 库 | `/Library/Application Support/SLogMetaRaw/lib/slogmetaraw` |
| 菜单脚本 | `…/DaVinci Resolve/Fusion/Scripts/Utility/S-Log MetaRaw.py` |

运行时，它会在 `~/Library/Application Support/SLogMetaRaw/cache` 中为每个片段保存一个小的 JSON 记录。磁盘映像中还有三页的意大利语和英语指南。

**干净安装与卸载。** 每次安装都从干净状态开始：安装程序会完整替换之前的插件和库，并移除开发版安装，不会留下旧版本的任何文件。磁盘映像中的 **Disinstalla S-Log MetaRaw.command**（第一次请右键 › 打开）会移除所有已安装的版本（包括 1.x 和 2.x）以及缓存、设置和日志。它在动手之前会列出全部内容，要求你关闭 Resolve，并询问是否同时删除导出的 CSV。已经写入 Resolve 项目的元数据属于项目本身，会保留。

**系统要求：** macOS 12 或更高版本，Apple 芯片或 Intel，以及 DaVinci Resolve 21。**仅在 macOS 上的 Resolve Studio 21.1 中测试过。**

**片段：** `.MP4` 或 `.MXF` 格式的索尼 XAVC。脚本全部可以读取。节点可显影 **S-Log3**（S-Gamut3.Cine 或 S-Gamut3）、**S-Log2** 和 **S-Log**（S-Gamut）。遇到其他配置时节点保持中性并给出提示。

---

## 快速上手

1. 导入素材。**Workspace › Scripts › S-Log MetaRaw**：先点 **1 · 读取元数据**，再点 **2 · 写入 Resolve**。
2. 在 Color 页面把 **S-Log MetaRaw** 放在**第一个节点**。它会取得片段的 EI、开尔文值和色调，在这些数值下画面不变。
3. 在节点中校正白平衡和曝光，伪色视图会有帮助。
4. 用 **Toni**（影调）塑造影调。需要局部恢复、Texture、Clarity 或 Dehaze 时，在其后添加 **S-Log MetaRaw Detail** 节点。
5. 然后再接你的 CST、LUT 或 DRT。

```
S-Log MetaRaw  →  S-Log MetaRaw Detail  →  CST / LUT / DRT  →  其余调色
```

---

## 脚本

窗口有一行按钮、一行选项和片段列表，界面语言跟随 Resolve（简体中文、英语、意大利语、西班牙语、葡萄牙语）。节点面板为意大利语，下文在其标签后附有中文说明。

- 用菜单选择片段：*整个媒体池*或*媒体池中选中的片段*。
- **1 · 读取元数据**：每个片段一行，显示摄影机、镜头、光圈、快门、EI、白平衡、色彩空间和数据电平。*状态*列显示 `已读取`、拍摄过程中变化的参数（光圈、对焦……）或跳过片段的原因。点击某一行即可查看读取到的全部数据，分组方式与 Catalyst Browse 相同。
- **2 · 写入 Resolve**：填写媒体池字段（元数据面板、列、用于智能素材箱的关键词、数据叠印），并修正 Resolve 从 MXF 中读错的值，例如 FX6 上的 *Camera Aperture* `F53343`。
- **导出 CSV**：以 Resolve 自己的元数据 CSV 格式导出 Resolve 没有对应字段的数值（EI、色调、白平衡模式、对焦距离、拍摄伽马……）。
- 选项：
  - **相机标签**（关）：把摄影机、伽马和原色加入关键词。
  - **覆盖元数据**（开）：替换 Resolve 已填写的值；关闭时只填写空字段。
  - **修正数据电平**（开）：按伽马的需要把每个片段的 *Data Level* 设为 Full 或 Video。原因见 [docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)。
  - **同时设置 Input Color Space**（关）：用于色彩管理项目。脚本无法把它改回 *Project*，只能手动改回。
- 点击右下角的版本号即可检查 GitHub 上的更新。

读取很快，因为不解码任何内容：每个片段最多读取元数据轨道的 24 个样本，时间上限为一秒。停止响应的卷只会被跳过一次并给出提示，而不会卡住列表。

---

## S-Log MetaRaw 节点

该节点是逐点处理的：每个像素只取决于它自身。它不会产生光晕，**Generate LUT** 可以导出它（建议 65 点）。

| 控件 | 作用 |
|---|---|
| **版本**（顶部） | `v2.1.1`。每天最多向 GitHub 查询一次最新版本。若有新版本，显示 **🟢 v2.1.1 → 2.x.y**，点击会在浏览器中打开 DMG 下载。它自己从不安装任何东西 |
| **Camera** · **Rileggi metadata** | 读取到的摄影机。*Rileggi*（重新读取）会重新读取片段，把所有控件恢复为摄影机数值，并把该片段的元数据写入媒体池 |
| **Decode Using** | *Clip* 可以修改控件；*Camera metadata* 把控件锁定为拍摄值 |
| **White Balance** · **Color Temp** · **Tint** | As shot 或预设。从摄影机记录的白点出发，在线性光中进行 Bradford 色适应 |
| **Exposure** | 曝光指数：EI 翻倍 = +1 档 |
| **False color** | 色温、色调和曝光；见下文 |
| **Color Space** · **Gamma** | 输出，类似 Color Space Transform；*Timeline* 不做转换 |
| **Toni**（影调） | Contrast、Highlights、Shadows、Whites、**Bianco**（白点，单位为档）、Blacks、Vibrance、Saturation（−100…+100） |
| **Zone**（分区，默认收起） | Black、Shadow、Light、Specular 分区，各有 Exp（档）、Sat、Range、Falloff；Contrast Pivot；Soft Clip；*Zone* 伪色 |
| **Avanzate**（高级） | 节点输入、数据电平校正、状态、**Sblocca controlli senza metadata**（无元数据时解锁） |
| **Dati di ripresa**（拍摄数据） | 只读：镜头、焦距、光圈、对焦、快门、EI、白平衡、帧率、ND、机内 LUT |

**Highlights 是胶片式肩部。** 向负方向调节时，它以向上逐渐平缓的斜率压缩高光，就像胶片、ACES 2.0 和 AgX 一样。在 −100 时，摄影机记录到的最亮值（S-Log3 中约为中灰以上 +6 档）正好落在 **Bianco** 上：没有灰雾，也没有剪切。中灰及以下保持不动，+1 档的肤色最多移动 0.05 档。压缩最多的高光会平缓地趋向白色而不改变色相。向正方向调节时，高光更有力度，斜率有上限。**Bianco** 是这个最大值（以及 Soft Clip 顶部）所在的位置：2.5 档是不带色调映射的 CST 下的 Rec.709 白。如果节点之后有 DRT（ACES、AgX、DaVinci），请调到 4–5，否则高光会被压缩两次。

**分区影调。** Shadows、Whites 和各分区是对一段影调范围、以档为单位的曝光调整：Shadows 作用于 −1 档以下，Whites 从 +3.5 档开始。Blacks 是一层线性薄雾，移动黑位而不移动中灰。在分区内部，画面像曝光一样整体移动，因此纹理得以保留；压缩只发生在声明的过渡带中。任何滑块组合都不会产生色调分离（solarise）。坦白说逐点节点的代价是：它压缩的部分，纹理也一起被压缩。正因如此，局部恢复放在单独的节点中。公式与用法：[docs/TONE_MAPPING.md](docs/TONE_MAPPING.md)。

**伪色。** 每个控件一个视图，位于它所服务的滑块上方：
- **曝光**：以 18% 灰为中心按档分带，采用 ARRI 风格。绿色是中灰，粉色高一档（肤色），黄色接近过曝，红色为过曝，蓝色和紫色为暗部底端。
- **色温**和**色调**：与 CineMatch 相同。画面变为灰色，偏色显示为橙/蓝或绿/品红，接近中性的偏色最多放大 8 倍以便看清。移动滑块，直到应为中性的区域保持灰色。每个视图只响应自己的滑块。

伪色视图会替换画面：渲染前请关闭。[docs/FALSE_COLOR.md](docs/FALSE_COLOR.md)

**数据电平。** 如果 Resolve 用错误的码值范围解码片段，节点会在 Log 曲线之前进行校正。脚本的*修正数据电平*选项可以为整个项目修正。[docs/DATA_LEVELS.md](docs/DATA_LEVELS.md)

**没有元数据时。** 外部记录器录制的 ProRes 或无法读取的片段会让节点保持中性。勾选 *Avanzate › Sblocca controlli senza metadata* 并输入拍摄时的 EI、开尔文值和色调：控件随即启用，节点从中性状态开始。

**速度。** 打开项目时不会读取任何文件。打开面板最多等待半秒；慢速磁盘会在后台完成读取，上限 15 秒。*Rileggi* 最多约 2 秒内响应。

---

## S-Log MetaRaw Detail 节点

这是创意节点。它在保留边缘的基础层上**按区域**工作，调整大块区域而不压平细节。这正是 Lightroom 的 Highlights 和 Shadows 中逐点节点无法复制的部分。

| 分组 | 控件 |
|---|---|
| **Gamma dinamica**（动态范围） | Local Contrast、Local Highlights、Local Shadows；*增益*和*基础层*视图。Local Highlights 压缩大面积的明亮区域，同时保留甚至加强细节纹理：天空变深，云层保持细节。主节点的 Highlights 则像胶片一样柔化高光纹理 |
| **Presenza**（质感） | Texture、Clarity、Dehaze |
| **Zone locali**（局部分区） | 主节点的分区，作用于区域 |
| **Avanzate**（高级） | 细节保留、半径、边缘与噪声阈值、Clarity 中心、Local Highlights 的 **Bianco**、节点输入 |
| **Velo**（雾霭） | Dehaze 去除的雾霭的亮度和颜色：由你设定，从不逐帧估计 |

- 把它放在 S-Log MetaRaw **之后**、CST、LUT 或 DRT 之前。它把接收到的画面解码为线性光，再按相同编码写回，因此必须放在任何转换之前：请让主节点的 Color Space 和 Gamma 保持为 Timeline。
- 它是**空间**处理的，因此 Generate LUT 会排除它及其所在节点的其余调整。请把它放在单独的节点中。
- 半径随画面高度缩放。全分辨率、代理和检视器中的效果一致。不做逐帧统计，因此不会闪烁。
- 在 Metal 上处理一帧 UHD 约需 6–18 毫秒（在 Apple 芯片上测得）。CPU 备用路径要慢得多。

**它的局限（实测）。** Local Highlights 为 −100 时，边缘暗侧的光晕低于台阶的 3%。Local Shadows 或局部分区为 ±100 时，一档的硬边缘处光晕约为台阶的 12%，2–3 档的边缘约为 4–6%。如果看到光晕，请降低 *Soglia bordi*（边缘阈值）。Texture 不会提升低于噪声阈值的颗粒，但在强边缘附近颗粒可能增大 1.25–1.7 倍。Dehaze 需要画面中真的有雾霭可去。[docs/DETAIL.md](docs/DETAIL.md)

---

## 更新与隐私

- **节点**每天最多在后台向 GitHub 查询一次本项目的最新版本。请求中只包含程序版本（`User-Agent: SLogMetaRaw/2.1.1`）。如需关闭，请创建空文件 `~/Library/Application Support/SLogMetaRaw/no_update_check`。
- **脚本**只在你点击其版本号时检查。
- 点击只会打开本项目 GitHub 发布页中的下载链接。未经你的操作，不会安装任何东西。

---

## 工作原理（简述）

- **元数据。** 解析器为纯 Python，无任何依赖。它们逐帧读取 SMPTE RDD 18 采集元数据（MP4 的 `rtmd` 轨道、MXF 的 ST 436 数据包）、索尼的 NonRealTimeMeta XML、H.264/HEVC 的 SPS 以及 MXF 图像描述符。一个数 GB 的片段只需读取约 100 KB。
- **从脚本到节点。** 每个片段在缓存中有一条 JSON 记录。节点通过 Resolve 提供的源文件路径找到文件，读取该记录；若记录缺失，则在后台生成。
- **色彩数学。** 处理链为：解码摄影机曲线，按 EI 比例调整，从普朗克轨迹出发进行 Bradford 白平衡（色调在 CIE 1960 uv 中垂直于轨迹），然后以像素各通道范数计算的单一增益处理影调（色度保持不变），再处理色彩，最后输出。全部在线性光中进行，使用索尼公开的曲线与色域。
- **一套数学，三种实现。** 数学代码位于 `ofx/SLogMetaRaw/math`，同时编译为 C++ 和 Metal。一个 Python 参考模型对两者进行校验：CPU 与 GPU 的差异在 2·10⁻⁴ 以内，所有路径均禁用 FMA。
- **测试。** 322 项自动化测试：解析器、参考模型、C++、Metal、一个像 Resolve 一样加载两个节点的微型 OpenFX 宿主，以及面板的 golden 文件。

---

## 从源码构建

```bash
make -C ofx/SLogMetaRaw                     # 通用插件，arm64 + x86_64（需要 Xcode）
make -C ofx/SLogMetaRaw test-bins           # 测试程序
python3 -m unittest discover tests          # 运行测试
./install.sh --dev                          # 让脚本和插件指向当前文件夹
./packaging/build_installer.sh              # 生成 dist/SLogMetaRaw-<版本>.dmg
python3 -m slogmetaraw clip.MP4             # 命令行中以 Catalyst 风格显示
```

```
slogmetaraw/         解析器、写入 Resolve、脚本窗口、更新检查
resolve_script/      Workspace › Scripts 的启动器
ofx/SLogMetaRaw/     math/（CPU/Metal 共用）、src/（common、develop、detail）、metal/
tools/               矩阵、图标和图表生成器
tests/               测试与参考模型（示例片段不在仓库中）
packaging/           安装程序、指南、卸载程序
docs/                TONE_MAPPING、DETAIL、FALSE_COLOR、DATA_LEVELS
```

---

## 已知限制

- Resolve 自带的 Camera Raw 面板和陀螺仪稳定无法为 MP4 解锁：它们位于 Resolve 的解码器内部。S-Log MetaRaw 重建的是色彩控件，并不是打开 Resolve 内部的某扇门。
- 部分摄影机（包括 a6300）不记录开尔文值：此时根据光源预设估算，并加以标注。
- S-Log2 按照索尼文档实现。Resolve 自带的 S-Log2 曲线与之相差约 0.15 档。
- 尚需在更多文件上验证：XAVC HS（HEVC）、HLG、S-Cinetone、电动变焦。
- **独立的业余项目**，按现状分发，不提供任何担保，也不对专业用途承担责任。代码开源：欢迎阅读、测试和修改。

---

## 致谢与许可

**Ivan Mazzone + Claude** · [github.com/ivan-94m](https://github.com/ivan-94m) · [@ivan_94m](https://instagram.com/ivan_94m)。
与 Claude（Anthropic）共同编写：1.0 于 2026 年 9 月 19 日，1.1.0 于 9 月 22 日，2.0.0 于 2026 年 9 月 23 日。完整历史见 [RELEASE_NOTES.md](RELEASE_NOTES.md)（意大利语）。

索尼标签参考：SMPTE RDD 18、[ExifTool](https://exiftool.org) 以及 AdrianEddy 的 [telemetry-parser](https://github.com/AdrianEddy/telemetry-parser)（MIT），部分标签表来自后者。

[GNU GPL v3.0 或更高版本](LICENSE)。OpenFX SDK 版权归 The Open Effects Association 所有（BSD-3）。Sony、XAVC 和 Catalyst 是 Sony Group Corporation 的商标；DaVinci Resolve 是 Blackmagic Design 的商标。本项目为独立项目，与上述两家公司无隶属关系，也未获其认可。
