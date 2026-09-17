# OCR 引擎 A/B 实测报告：rapidocr PP-OCRv6 vs Apple Vision（ocrmac）

- 日期：2026-09-16
- 执行：实施 Agent（本报告仅记录事实性观察，质量优劣裁决由 controller 与用户做出）
- 原始产物：`workspace/tmp/ab-ocr/`（两臂 JSON + `ab-summary.md` 汇总）
- 脚本：`utils/ab_ocr_convert.py`（单臂转换）、`utils/ab_ocr_compare.py`（指标汇总）

## 1. 实验设计

| 项 | Arm R | Arm V |
|---|---|---|
| 环境 | `workspace/tmp/venv-docling2127`（无 ocrmac） | `workspace/tmp/venv-docling2127-vision`（+ ocrmac 1.0.1） |
| OCR 引擎 | rapidocr 3.9.2（torch 后端，PP-OCRv6） | ocrmac 1.0.1（Apple Vision） |
| 其余栈 | 两臂均为 docling 2.127.0 / docling-core 2.96.0 / torch 2.14.0 / transformers 5.16.1，唯一变量为 ocrmac 是否存在 |

- 转换路径与生产一致：`dayu.documents.docling_runtime` 的
  `build_docling_pdf_converter` + `convert_pdf_bytes_with_docling`（`do_ocr=True` 默认、
  backend docling-parse、设备 auto/MPS）。
- OcrAutoOptions 行为已核实（`docling/models/stages/ocr/auto_ocr_model.py`）：
  darwin 平台无条件优先 ocrmac，未安装则跳过并落至 rapidocr。
- 样本：5 份扫描件/图重财报（按文本层从少到多：1 页 579 字符、2 页 1153 字符、
  8 页 7585 字符、11 页 5139 字符、13 页 8063 字符）+ 1 份有文本层对照（29 页约 3 万字符）。
- 文本抽取方式（两臂一致）：全量 TextItem 按 `iterate_items()` 阅读顺序拼接（换行分隔）；
  历史基线文本 = 样本库内 `*_docling.json`（docling 2.90 产物）顶层 `texts` 数组的
  `text` 字段按序拼接。
- 数字保真：正则 `-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?` 抽取数字 token 多重集合；
  交集率 = Dice 系数 `2*|A∩B| / (|A|+|B|)`（多重集交集取逐 token 最小计数）。
- 相似度：`difflib.SequenceMatcher.ratio()`。

## 2. OCR 真实运行的证据

1. 引擎选择（docling 日志，逐样本捕获）：
   - Arm R 6/6：`ocrmac cannot be used because ocrmac is not installed.` →
     `Auto OCR model selected rapidocr with torch.`
   - Arm V 6/6：`Auto OCR model selected ocrmac.`
2. do_ocr=False 对照（在 s01、s04 两样本执行，量化 OCR 层贡献）：

   | 样本 | 臂 | do_ocr=True | do_ocr=False | OCR 层贡献 |
   |---|---|---|---|---|
   | s01 | R | 618 字符 / 20 数字 | 598 / 20 | +20 字符 |
   | s01 | V | 619 / 21 | 598 / 20 | +21 字符 / +1 数字 |
   | s04 | R | 1823 / 44 | 1429 / 32 | +394 字符 / +12 数字 |
   | s04 | V | 1685 / 48 | 1429 / 32 | +256 字符 / +16 数字 |

   s04 的两臂 no-ocr 输出完全一致（1429/32）——非 OCR 路径两臂零差异，隔离有效性成立。

## 3. 每样本指标

| 样本 | 类型 | 臂 | 文本长度 | 数字 token | 引擎证据 | 耗时(s) | V vs R 相似度 | V vs R 数字 Dice | R vs 基线 | V vs 基线 |
|---|---|---|---|---|---|---|---|---|---|---|
| s01（1页） | 扫描件 | R | 618 | 20 | rapidocr torch | 6.7 | 0.9911 | 0.9756 | 0.9836 / 1.0 | 0.9827 / 0.9756 |
| | | V | 619 | 21 | ocrmac | 6.4 | | | | |
| s02（2页） | 扫描件 | R | 1217 | 38 | rapidocr torch | 6.7 | 1.0 | 1.0 | 0.991 / 0.9744 | 0.991 / 0.9744 |
| | | V | 1217 | 38 | ocrmac | 6.3 | | | | |
| s03（8页） | 扫描件 | R | 2656 | 57 | rapidocr torch | 12.1 | 1.0 | 1.0 | 0.8912 / 0.8507 | 0.8912 / 0.8507 |
| | | V | 2656 | 57 | ocrmac | 12.5 | | | | |
| s04（11页） | 扫描件 | R | 1823 | 44 | rapidocr torch | 48.0 | **0.8244** | **0.8478** | 0.5471 / 0.2897 | 0.5609 / 0.3061 |
| | | V | 1685 | 48 | ocrmac | 24.5 | | | | |
| s05（13页） | 扫描件 | R | 5518 | 150 | rapidocr torch | 13.7 | 1.0 | 1.0 | 0.9756 / 0.9585 | 0.9756 / 0.9585 |
| | | V | 5518 | 150 | ocrmac | 13.7 | | | | |
| c01（29页） | 文本层对照 | R | 18976 | 847 | rapidocr torch | 29.8 | 1.0 | 1.0 | 0.9812 / 0.9832 | 0.9812 / 0.9832 |
| | | V | 18976 | 847 | ocrmac | 33.2 | | | | |

（R vs 基线 / V vs 基线列格式：全文相似度 / 数字 Dice）

## 4. 事实性观察

1. **6 份样本中 5 份（s02、s03、s05、c01 逐字符一致；s01 差 1 处小差异）两臂输出
   实质一致**：s02/s03/s05/c01 的 V vs R 全文相似度与数字 Dice 均为 1.0。这些样本上
   无法从输出区分 OCR 引擎（layout-driven OCR 仅在无文本层区域运行；两臂在这些
   区域的输出恰好一致，或该区域未触发 OCR）。
2. **s04 是唯一两臂输出产生实质差异的样本**（V vs R 相似度 0.8244、数字 Dice 0.8478）。
   差异摘录显示：V 臂（ocrmac）在该样本的扫描资产负债表页输出乱码块
   （如 `¿Ẽ##@:·Э#ŒŒü÷®4®`、`2021$98308`），R 臂（rapidocr）对应区域输出正常中文
   （"编制单位：美的集团股份有限公司 / 合并及公司资产负债表 / 2021年9月30日"）。
   该差异完全来自 OCR 层（no-ocr 对照两臂一致）。
3. **s01 上 V 臂多出一个疑似 OCR 幻觉数字**："Trip.com Group" 1879""（R 臂无此数字），
   导致 V vs R 数字 Dice=0.9756、V vs 基线=0.9756（R vs 基线=1.0）。
4. **s04 上两臂与历史基线的相似度均显著低于其他样本**（R 0.5471、V 0.5609；
   其余样本 0.89-0.99）：该样本以扫描页为主，docling 2.90 时代的 OCR 覆盖策略与
   2.127 的 layout-driven OCR 策略差异在该样本上放大。这属于"新引擎 vs 历史基线"
   的整体性观察，不是两臂之间的差异。
5. 两臂转换耗时同量级（s04 上 R 48.0s vs V 24.5s，为最大差距样本；其余样本差异
   在 1-3s 内）。耗时受模型缓存与并行执行影响，仅作参考。

## 5. 原始产物

- 两臂 12 份转换产物：`workspace/tmp/ab-ocr/{r,v}/fil_cn_*.json`（含全文、数字
  多重集合、引擎证据、耗时）
- no-ocr 对照产物：`workspace/tmp/ab-ocr/{r,v}/fil_cn_*-noocr.json`（s01、s04）
- 指标汇总：`workspace/tmp/ab-ocr/ab-summary.md`

## 6. 残余限制

- do_ocr=False 对照仅在 s01、s04 执行；s02/s03/s05/c01 的 OCR 执行强度未单独量化
  （引擎选择日志确认已选引擎，但执行区域/页数未统计）。
- 样本库真正的无文本层纯扫描件稀缺（最小文本层 579 字符），本实验的"扫描件"
  多为图重/局部扫描；纯扫描页的引擎对比仅 s04 的少数页面提供证据。
- 未做 Windows/Linux 平台对照（ocrmac 仅 darwin 可用；Linux 回归走 rapidocr 路径，
  见步骤 2.4 方案）。

## 7. 补充：s04 乱码的核验与根因修正（2026-09-17）

**证据等级说明**：本补充小节全部证据均为 **Tier-0（程序化证据）**——两臂转换
产物的文本对比、探针捕获图像上的双引擎程序化 OCR 转录、语言偏好对照实验。
本会话未执行目视读图（Tier-1 缺失）；「页面实际内容」的判定依据是程序化 OCR
转录与两臂产物对比，**不包含任何模型目视抄写的数字**。

### 7.1 核验方法（Tier-0）

s04（`fil_cn_f151c6b703769c8efa62974b24e47c8a302c1d1a`，美的集团 2021 年三季报）
V 臂乱码页经定位为第 5 页（合并及公司资产负债表）与第 9 页（调整情况说明资产负债表）。
两页均用 pypdfium2 以 scale 2.0 渲染为 PNG 后双引擎程序化转录复核；另有探针脚本
（`workspace/tmp/spot-check/probe_ocrmac_image.py`）捕获 docling+ocrmac 管道实际
喂给 Vision 的 region 图像（`workspace/tmp/spot-check/v-probe/`）逐张复读。

### 7.2 页面实际内容（Tier-0：程序化 OCR 转录）

- 第 5 页渲染图 rapidocr（PP-OCRv6，torch）转录：`合并及公司资产负债表 /
  编制单位：美的集团股份有限公司 / 2021年9月30日 / 单位：人民币千元` 及完整科目数字，
  与 R 臂输出一致。
- 第 5 页渲染图 Vision（`language_preference=["zh-Hans","en-US"]`）转录同样内容。
- 两引擎在"读同一张干净渲染图"条件下的程序化转录一致 → 页面实际内容就是
  R 臂输出的内容，V 臂管道输出（`¿Ẽ##@:·Э#ŒŒü÷®4®` 等）与页面不符。
  （均为机器转录结果对比，非目视判断。）

### 7.3 乱码根因：Vision 语言偏好未配置（Tier-0；修正第 4.2 节表述）

探针捕获的 region-0 图像（1470×1860，含整张资产负债表）分别用三种条件复读：

| 条件 | Vision 输出（前 10 行） |
|---|---|
| 无语言偏好（与管道一致） | `2021$98308`、`2021#9,9308`、`2020#12A31E`、`Да`…（复现乱码） |
| `["en-US"]` | 同上（复现乱码） |
| `["zh-Hans","en-US"]` | `合并及公司资产负债表`、`编制单位：美的集团股份有限公司`…（正常） |

- docling 2.127 的 OCR 选项 `lang` 默认为空列表，ocrmac 管道以
  `language_preference=None` 调用 Vision → Vision 按英文偏好识别中文扫描页，
  汉字退化为符号乱码。第 9 页同机制复现（无偏好乱码 / zh+en 正常）。
- 图像本身无质量问题：同一张图 zh+en 条件下 Vision 与 rapidocr 输出一致且正确。
- 因此 s04 的 V 臂乱码**不是 Vision 引擎能力缺陷，而是 OCR 语言偏好未配置中文**
  导致的管道配置问题。rapidocr 臂不受影响是因为其默认模型集含中文、不依赖
  语言偏好。第 4.2 节"该差异完全来自 OCR 层"应更精确地理解为"来自 OCR 层对
  语言配置的敏感度差异"。

### 7.4 对生产的影响评估

- 当前生产 venv 未安装 ocrmac（auto OCR 落 rapidocr），本问题不影响现行生产输出。
- 但 docling 的 auto OCR 在 darwin 上**无条件优先 ocrmac**：一旦生产环境（macOS）
  安装了 ocrmac 或未来依赖变化引入，中文财报扫描页即会以英文偏好被 Vision 识别，
  出现同类乱码。dayu 的 `docling_runtime` 目前不设置 OCR 语言。
- 建议（另行裁决）：dayu 在构造 pipeline 时显式设置 `ocr_options.lang`（含中文），
  或在产品声明中禁用 ocrmac 引擎。本补充仅记录事实，不改生产代码。
