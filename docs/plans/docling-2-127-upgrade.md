# Docling 2.90.0 → 2.127.0 升级方案

- 日期：2026-09-16
- 状态：已通过两路 plan review（MiMo + DS），修订闭环，待用户批准后实施
- Review artifacts：
  - `docs/reviews/plan-review-20260916-105307.md`（AgentDS，fail → 已修订）
  - `docs/reviews/plan-review-20260916-105857.md`（AgentMiMo，pass-with-risks → 已修订）

## 1. 背景与目标

项目当前锁定 docling 2.90.0（2026-04-17 发布），最新版本 2.127.0（2026-09-14 发布），
期间 37 个版本包含大量与财报 PDF/PPT/DOCX 解析直接相关的修复与增强：

- PPT 形状按视觉阅读顺序处理（v2.118.0）、原生图表解析（v2.113.0）
- PDF heading 层级推断不再扁平化（v2.106.0 / v2.109.0 / v2.120.0）
- DOCX 页眉页脚保留（v2.118.0）、Strict OOXML 支持（v2.109.0）
- 表格单元格内图片保留（v2.118.1）、行尾连字符处理（v2.122.0）

目标：升级 docling 全链路到 2.127.0，同时保证三平台（Linux x64 / Windows x64 /
macOS arm64）Python 3.11 环境可安装可运行，且 docling json 输出 schema 与语义
无破坏性回归。

已确认的平台与决策基线（2026-09-16）：
- **放弃 macOS x64**：PyTorch 官方 2.3.0 起停止发布该平台 wheel；transformers 5.x
  要求 torch>=2.5 后该平台彻底出局。
- **macOS 下限收紧到 14+**（torch 2.14.0 wheel 要求 macosx_14_0_arm64）。
- **升级窗口冻结财报上传**（用户裁决），窗口内不产生新写入的 docling json。
- **Linux 验证环境为 docker**（用户裁决），rapidocr 路径回归在容器内执行。
- **语义 diff 由 LLM 判定 + 人工抽查 10%**（用户裁决）。
- **min-py311.txt 保持"最低边界验证"使命，内容按新声明下界重写**（用户裁决）。

## 2. 评估结论

### 2.1 依赖冲突盘点（逐包对比 PyPI 元数据与官方 uv.lock）

**必须升级 — docling 生态：**

| 包 | 当前锁定 | 目标版本 | 触发原因 |
|---|---|---|---|
| docling | 2.90.0 | 2.127.0 | 目标升级 |
| docling-slim | 无（新包） | 2.127.0 | docling 2.127 起为 meta-package，实质代码在该包 |
| docling-core | 2.74.0 | **2.96.0** | docling-slim[standard] 要求 >=2.94.1；官方 uv.lock 精确版本。2.96.1 超出官方 lock，其两项修复对项目无影响（DCLX 序列化项目不用；requests 依赖声明遗漏因项目已直接依赖 requests 而无实际影响） |
| docling-parse | 5.9.0 | **7.20.0** | docling-slim 要求 >=7.16.0。官方 uv.lock 锁 7.19.0 是 docling 2.127 发布时刻（09-14）的解析快照；其后官方发布的 7.19.1（PostScript 颜色操作符污染修复，[#347](https://github.com/docling-project/docling-parse/issues/347)，09-11 已发布未纳入 lock）与 7.20.0（shape 几何查询坐标系修复，[#344](https://github.com/docling-project/docling-parse/issues/344)）为质量修复，7.20.0 的 page-range 为增量 feature 不影响现有行为。**取 7.20.0 为"官方 lock 版本系列 + 后续 bugfix"，偏离官方 lock 的理由见本列**（要求 docling-core>=2.95.0，2.96.0 满足） |
| docling-ibm-models | 3.13.0 | 4.0.2 | docling-slim 要求 >=4.0.2 |
| pydantic-settings | 2.13.1 | 2.15.0 | docling-core 2.94+ 要求 >=2.14.0 |
| rapidocr | 3.8.1 | 3.9.2 | docling 2.127 硬性运行时检查（见 OCR 栈） |

**必须升级 — 模型推理栈（对齐 docling 官方 uv.lock 在 py3.11 的验证基线）：**

官方 uv.lock（2026-09）在 py3.11 锁定：darwin 为 torch 2.14.0 + torchvision 0.29.0
+ transformers 5.16.1；linux/win32 为 torch 2.14.0 + torchvision 0.29.0 +
transformers 5.17.0。项目锁定的 torch 2.4.1 / transformers 4.57.6 落后官方验证
环境约两年，属官方从未验证的组合；torch 2.4.1 的 MPS 后端缺 2.5~2.14 间大量
精度/稳定性修复。

| 包 | 当前锁定 | 目标版本 | 触发原因 |
|---|---|---|---|
| torch | 2.4.1 | 2.14.0 | 官方 lock 验证基线（三平台 py3.11 统一） |
| torchvision | 0.19.1 | 0.29.0 | 配套 torch 2.14 |
| transformers | 4.57.6 | 5.16.1（darwin）/ 5.17.0（linux、win32） | 官方 lock 验证基线 |
| huggingface-hub | 0.36.2 | 1.31.0 | transformers 5.16.1 要求 >=1.5.0（跨 major） |
| hf-xet | 1.4.3 | >=1.5.2 | huggingface-hub 1.31.0 在 arm64/x64 强制要求 |
| tokenizers | 0.22.2 | 0.23.2 | transformers 5.16.1 要求 >=0.23.1,<0.24.0 |
| safetensors | 0.7.0 | 0.8.0 | transformers 5.16.1 要求 >=0.8.0 |
| accelerate | 1.13.0 | 1.15.0 | 官方 lock 对齐 |
| numpy | 2.4.4 | 2.4.6 | 官方 darwin/linux py3.11 lock 对齐（patch 级，低风险） |

**OCR 栈：**

| 包 | 当前锁定 | 目标版本 | 触发原因 |
|---|---|---|---|
| rapidocr | 3.8.1 | 3.9.2 | docling 2.127 硬性运行时检查：rapid_ocr_model.py 报错信息明确要求 "rapidocr>=3.9.1,<4.0.0"；3.8.1 缺 PP-OCRv6 模型集与 `rapidocr.utils.typings.OCRVersion` 类型，会直接失败 |

OCR 栈无需变动：ocrmac 1.0.1（已最新，docling 集成只用 `ocrmac.OCR`）；
opencv-python 4.13/4.10（rapidocr 3.9 要求 >=4.5.1.48 满足）；easyocr /
onnxruntime / tesserocr / nemotron-ocr 未安装，`OcrAutoOptions` 自动跳过。

**新增依赖：**

| 包 | 目标版本 | 来源 |
|---|---|---|
| doclang | 0.7.3 | docling-core 基础依赖（>=0.7,<0.8） |
| langcodes | 3.5.1 | docling-slim 基础依赖（>=3.5.0） |
| python-oxmsg | 0.0.2 | docling-slim[standard]（email 格式支持） |
| mail-parser | 4.6.5 | docling-slim[standard] |

**已满足、无需变动（已验证）**：pandas 3.0.2、pypdfium2 5.7.0、python-docx 1.2.0、
python-pptx 1.0.2、scipy、pillow 12.2.0、pydantic 2.13.2、tree-sitter 系列、
semchunk、omegaconf、shapely、regex 2026.4.4、typer 0.21.2（transformers 5.16.1
基础依赖，项目已锁定，盘点补录）、requests 2.33.1（docling-core 2.96.0 无
requests 依赖，不升级）。

### 2.2 API 兼容性（docling 与 docling-core 双包验证）

**docling 包**（基于 2.127.0 wheel 逐项验证，全部兼容）：

| 项目用法 | 2.127.0 状态 |
|---|---|
| `DocumentConverter(allowed_formats=..., format_options=...)` | 签名一致 ✓ |
| `PdfFormatOption(pipeline_options=..., backend=...)` | 字段一致 ✓ |
| `PdfPipelineOptions.do_ocr / do_table_structure / accelerator_options / table_structure_options` | 字段一致 ✓ |
| `TableFormerMode.ACCURATE / FAST` | 枚举一致 ✓ |
| `table_structure_options.mode / do_cell_matching` | 字段一致 ✓（类名 TableFormerOptions→TableStructureOptions，项目经 Protocol 访问无感） |
| `AcceleratorOptions(device=AcceleratorDevice(...))` | 存在 ✓（基类变为 BaseSettings，显式传参优先于环境变量） |
| `DoclingParseDocumentBackend` / `PyPdfiumDocumentBackend` | 存在 ✓ |
| `InputFormat / DocumentStream / FormatToExtensions` | 存在 ✓ |
| `ConversionResult.document.export_to_dict()` | 存在 ✓ |

注意：2.127.0 中 `PdfFormatOption.backend` 默认值改为 `ThreadedDoclingParseDocumentBackend`
（v2.123 起全局默认），项目显式传入 `DoclingParseDocumentBackend`，不受默认切换影响。

**docling-core 包**（基于 2.96.0 wheel 实测验证，MiMo 02 闭环）：

项目 `dayu/documents/processors/docling_processor.py` 重度使用 docling-core 类型 API
（`from docling_core.types.doc.document import DoclingDocument, TextItem`、
`DoclingDocument.load_from_json()`、`document.iterate_items()`）。docling-core 自
v2.87.0 起将 document.py 拆分为子模块，但 2.96.0 的 document.py 保留 re-export：

- `TextItem`（document.py:146，re-export 自 items.text）✓
- `NodeItem`（document.py:107，re-export 自 items.node）✓
- `TableItem`（document.py:138，re-export 自 items.table.table）✓
- `DoclingDocument.load_from_json()`（document.py:3603）✓
- `DoclingDocument.iterate_items()`（document.py:3296）✓

结论：import 路径与调用面均兼容，代码层无需改动。`load_from_json` 对旧版
（2.90 生成、version 1.10.0）json 的反序列化兼容性仍列入回归验证（见步骤 2）。

### 2.3 平台可行性评估

**Python 3.11**：docling 2.127 / docling-core 2.96.0 / docling-parse 7.20.0 /
docling-ibm-models 4.0.2 / torch 2.14.0 / transformers 5.16.1 的 requires_python
均覆盖 3.11 ✓

**macOS arm64**（回归主执行平台）：
- torch 2.14.0 有 `cp311-macosx_14_0_arm64` wheel ✓；macOS 下限 14+（本机
  macOS 26.6.2 满足）
- transformers 5.16.1（官方 darwin lock 版本），避开 docling-slim 在 darwin 上
  排除的 5.0~5.3、5.9~5.15 等版本 ✓
- OCR auto 选择优先 ocrmac（Apple Vision）✓

**Linux x64**（docker 验证环境）：
- torch 2.14.0 在 Linux 无条件声明 CUDA pip 依赖链，**逐包体积已量化
  （合计约 5.5GB）**：nvidia-cudnn-cu13 1541MB、triton 2714MB、
  nvidia-cusparselt-cu13 522MB、nvidia-nccl-cu13 411MB、cuda-bindings 266MB、
  nvidia-nvshmem-cu13 115MB（cuda-toolkit 本体另计，总量 5-10GB 级）。
  CPU 推理同样安装；成本由 Linux docker 镜像体积承担。
- **CPU-only index 评估结论（已评估，不采用）**：torch 官方
  `download.pytorch.org/whl/cpu` 源与项目 constraints 单 index 锁定机制冲突
  （constraints 锁版本不锁来源，多 index 会使锁文件语义失效）；默认走 PyPI，
  镜像内安装，接受体积成本。
- transformers 5.17.0（官方 linux lock 版本）✓

**Windows x64**：torch 2.14.0 cp311 win wheel 存在 ✓；transformers 5.17.0 ✓；
本轮仅安装冒烟级验证（见步骤 3 平台验证矩阵，登记残余风险）。

**OCR 行为**：v2.116 起重构为 layout-driven OCR pipeline，`ocr_options` 默认
`OcrAutoOptions()`；rapidocr 3.9.2 提供 PP-OCRv6 模型集（Linux/Windows OCR 主力）；
macOS 上 auto 优先 ocrmac。

### 2.4 行为变化风险（升级后必须回归验证的点）

1. **docling json 反序列化兼容性 + LLM 投影语义（最高优先级）**：docling-core
   2.74→2.96 跨 22 个 minor 后，`DoclingDocument.load_from_json()` 对旧版
   （2.90 生成）`export_to_dict()` 输出的解析兼容性、以及 LLM 透传消费的
   文本/表格/heading 内容是否退化。程序级 schema 破坏由
   `docling_process_converter._is_closed_json_value` 显性兜底，真实破坏面在
   `docling_processor` 解析与 LLM 语义消费（MiMo 03 修正风险定位）。
2. **docling-parse 5.9 → 7.20（跨 v6/v7 两代）**：PDF 文本/坐标/表格输出差异。
3. **layout-driven OCR pipeline（v2.116.0）**：`do_ocr=True` 路径的 OCR 覆盖
   区域与识别质量变化；rapidocr 升级后 PP-OCRv6 模型集生效。
4. **PDF heading 层级推断（v2.106/2.109/2.120）**：文档 heading 结构变化。
5. **模型栈升级**：torch 2.4.1→2.14.0、transformers 4.57.6→5.16/5.17 引起
   推理数值级变化；**docling-ibm-models 3.13→4.0 跨 major 可能伴随模型权重
   revision/架构变化**（单列为风险清单独立项，实施前先导核对）。
6. 其余质量修复（表格/图片/列表等）属预期收益，需在样本 diff 中确认无意外退化。

## 3. 实施步骤

### 步骤 1：更新 constraints 锁定与 pyproject

- `constraints/lock-common-py311.txt`：
  - 升级 docling 生态 7 个包（docling、docling-core、docling-parse、
    docling-ibm-models、pydantic-settings）+ rapidocr
  - 升级模型栈公共包：huggingface-hub、hf-xet、tokenizers、safetensors、
    accelerate、numpy
  - 新增 5 个包（docling-slim、doclang、langcodes、python-oxmsg、mail-parser）
- `constraints/min-py311.txt`（**保持"最低边界验证"使命，内容按新声明下界重写**，
  用户裁决）：
  - docling==2.127.0、docling-core==2.96.0（pyproject 新下界）
  - transformers==5.16.1（pyproject 新下界）
  - torch==2.5.1、torchvision==0.20.1（transformers 5.x torch extra 声明
    >=2.5 的最低稳定 patch；2.2.2 已不可解）
  - rapidocr==3.9.1（docling 硬性下界）、tokenizers==0.23.1、
    huggingface_hub==1.5.0（声明下界）
  - 注释补充："下界由 pyproject 声明定义；torch 下界由 transformers 5.x 声明抬高"
- 平台 lock 文件：
  - `lock-macos-arm64-py311.txt`：torch 2.4.1→2.14.0、torchvision 0.19.1→0.29.0、
    transformers 4.57.6→5.16.1；numpy 2.4.4→2.4.6；ocrmac 不变
  - `lock-linux-x64-py311.txt` / `lock-windows-x64-py311.txt`：torch→2.14.0、
    torchvision→0.29.0、transformers→5.17.0、numpy→2.4.6；Linux 平台补充锁定
    CUDA pip 依赖链（**补全 extras 列表**：cuda-toolkit[cublas,cudart,cufft,
    cufile,cupti,curand,cusolver,cusparse,nvjitlink,nvrtc,nvtx]==13.0.3、
    cuda-bindings>=13.0.3、nvidia-cudnn-cu13==9.24.0.43、
    nvidia-cusparselt-cu13==0.8.1、nvidia-nccl-cu13==2.30.7、
    nvidia-nvshmem-cu13==3.4.5、triton~=3.8.0）
  - **删除 `constraints/lock-macos-x64-py311.txt`**（平台不再支持）
- `pyproject.toml`：
  - **docling 约束收紧**：`>=2.90.0,<3.0.0` → `>=2.127.0,<3.0.0`；
    docling-core `>=2.74.0,<3.0.0` → `>=2.96.0,<3.0.0`（新基线即新下界，
    与 min-py311 使命一致）
  - `transformers` 约束 `>=4.57.6,<5.0.0` → `>=5.16.1,<6.0.0`（darwin 可用版本
    由 docling-slim 排除列表收窄，平台 lock 分别锁 5.16.1/5.17.0）
  - 更新依赖注释：删除"受支持的 macOS x64"表述（平台已放弃）
  - requests、pandas 约束不变（2.33.1 与 3.0.2 均满足目标版本）

### 步骤 2：样本库输出回归

样本库：`/Users/leo/Documents/_2我的投资/workspace`（只读访问）。
**已核实特征（DS F12 修正）**：250 份 A 股/港股中文财报 PDF（`fil_cn_*.pdf`），
全部与旧版 `*_docling.json` 成对（旧 json 全部 version 1.10.0，同基线）。
美股公司目录（TSM/GOOGL 等）全为 SEC `.htm` 且不经过 docling 转换，
不计入本回归样本。样本库无 PPTX/DOCX（覆盖缺口见 2.5）。

**2.1 先导冒烟 gate（F11）**：选 5 份样本（含 2 份含表格、1 份扫描件）：
可 import + 单样本转换成功 + 顶层 schema diff + `load_from_json` 解析成功。
任一失败即停止，修复后重跑，不进入全量。

**2.2 schema 层（250 份全量）**：
- 用项目 docling 转换入口批量执行（脚本入 `utils/`）
- diff 脚本对比：顶层 key 集合 + closed-JSON 校验 + 新旧 json 的
  `DoclingDocument.load_from_json` 解析成功（**反序列化兼容性是本层核心断言**）

**2.3 语义层（分层抽样）**：
- 抽样规模：每公司 ≥2 份 + 全部 31 份扫描件 + 按表格密度分层补足
  （tables>=10 的 216 份中抽约 43 份），合计约 100 份
- 判定粒度：文档级聚合判定
- 判定清单：数字保真（表格单元格数值）、表格结构、heading 层级、阅读顺序、
  文本完整性
- 判定人（用户裁决）：AgentMiMo/AgentDS 按判定 prompt 执行 LLM 判定，
  人工抽查 10%；判定报告入 `docs/reviews/`
- 退化且配置层无法适配的分支：明确决策条件——单档数字保真/表格结构退化
  即触发根因定位；确认为 docling 上游回归时回滚或 pin 候选中间版本

**2.4 Linux docker rapidocr 路径回归（F02，用户裁决 docker）**：
- 容器内对扫描件子集（≥10 份）跑 rapidocr 3.9.2 + PP-OCRv6 路径新旧对比
- 对比基准：旧基线 `*_docling.json`（2.90 生成；旧版 rapidocr 3.8.1 的
  OCR 输出与新版 PP-OCRv6 的差异按"引擎升级预期收益"判定）

**2.5 PPTX/DOCX 覆盖缺口（F06 修订）**：
- 单元测试项**撤销**（现有测试为 monkeypatch，不执行真实转换，空转）
- 改为真实转换冒烟脚本（utils/）：自建样本 ≥5 份，覆盖复杂合并单元格表格/
  多图表/分栏/页眉页脚；判定标准 = 转换成功 + 表格数字保真 + schema 有效
- 人工抽检量化：升级后首批 10 份真实上传，抽检维度清单（表格数字/阅读顺序/
  图片保留），结果记录入 `docs/reviews/`
- 可选：从公开渠道获取 2-3 份真实财报 PPT/DOCX 入样本库

### 步骤 3：平台验证矩阵（F01 修订：CI 不存在，改写为手动清单）

仓库无 CI（`.github/` 不存在），"CI 冒烟"表述作废，改为手动验证矩阵：

| 平台 | 验证方式 | 执行者 | 内容 |
|---|---|---|---|
| macOS arm64 | 本机 | 实施 Agent | 全量安装 + 单测 + 步骤 2 全量回归 |
| Linux x64 | docker 容器 | 实施 Agent | 安装冒烟 + 可 import + 扫描件子集 rapidocr 回归（2.4） |
| Windows x64 | 手动清单交付 | 用户 | 安装冒烟 + 单样本转换；本轮无人执行的部分登记残余风险 |

验证前置项：模型下载依赖 HF 网络可达性（国内环境需镜像/代理，安装冒烟前确认）。

### 步骤 4：回归通过后收尾

- **根 README.md（F08）**：删除 transformers 5.x 禁令说明与 macOS Intel lock
  引用、更新三平台 lock 文件列表、补充 macOS 14+ 最低版本要求
- 按 README 触发规则检查 `dayu/README.md`、`dayu/fins/README.md` 是否需要更新

## 4. 不做的事（非目标）

- 不切换默认 PDF backend 为 threaded docling-parse：保持项目显式
  `DoclingParseDocumentBackend` 策略，默认后端切换作为独立议题评估。
- 不引入 VLM pipeline / nemotron-ocr / docling service client。
- 不在本轮处理 `_docling.json` 历史资产的批量重建：历史 250 份靠
  `load_from_json` 向后兼容消费（步骤 2.2 的验证断言成立则成立）。
- **HTML 格式本轮不回归**（显式声明）：当前 SEC `.htm` 文件不经过 docling
  转换；若未来启用 docling HTML 后端需单独安排回归。

## 5. 回退方案（F03 + MiMo 04 修订：三层回退）

1. **git 层**：回滚本轮全部提交——constraints 三文件 + min-py311 + pyproject
   （含可能的 `dayu.documents.docling_runtime` 配置适配代码）；`git restore`
   `lock-macos-x64-py311.txt`。
2. **环境层**：按回滚后的 constraints 重建环境。
3. **资产层**：升级窗口冻结上传（用户裁决）→ 窗口内无新写入 docling json；
   历史 250 份旧 json 由 2.90 环境正常消费（其生成基线即 2.90），无混合问题。
   若未来出现未冻结的写入，需显式声明处理策略后方可继续。

## 6. 风险清单

| 风险 | 等级 | 缓解 |
|---|---|---|
| `load_from_json` 对旧版 docling json 反序列化失败或 LLM 投影语义退化 | 高 | 步骤 2.1 冒烟 gate + 2.2 全量解析断言 + 2.3 语义判定 |
| **docling-ibm-models 3.13→4.0 跨 major 模型权重/架构变化**（决定 diff 量级） | 高 | 实施前先导核对两版本模型 revision/架构差异；据差异量级调整语义抽样下限 |
| docling-parse 跨代升级的解析质量退化（表格/中文文本） | 中 | 步骤 2.3 文档级判定清单 |
| 模型栈升级（torch/transformers）引起表格结构识别数值级变化 | 中 | 步骤 2.3 含表格样本分层；对齐官方 lock 组合可对照官方行为 |
| rapidocr PP-OCRv6 路径仅 Linux docker 子集回归（Windows 未覆盖） | 中 | 2.4 子集回归 + Windows 登记残余风险 + 上线首周抽检 |
| PPTX / DOCX 回归无真实财报样本覆盖 | 中 | 真实转换冒烟脚本（自建样本）+ 首批 10 份人工抽检量化 |
| Linux docker 镜像体积 5.5GB+（CUDA 依赖链） | 中 | 已量化；CPU-only index 已评估不采用（与 constraints 机制冲突）；镜像分层缓存 |
| huggingface-hub 0.x→1.x 跨 major 的兼容影响 | 低 | 项目代码不直接使用（grep 无命中）；模型下载冒烟验证 |
| 新增依赖（doclang 等）与项目现有依赖树冲突 | 低 | 已逐包核对 requires_dist；安装冒烟兜底 |
| macOS 下限收紧到 14+ 的用户影响 | 低 | 产品决策已确认；根 README 同步 |

## 7. Review 闭环记录

| Finding | 来源 | 裁决 | 落地位置 |
|---|---|---|---|
| 版本偏离官方 lock（2.96.1/7.20.0） | MiMo 01 | docling-core 改 2.96.0（官方 lock 精确）；docling-parse 改 7.20.0（官方 lock 系列 + 后续 bugfix，如实说明偏离理由）；requests 不升级 | 2.1、步骤 1 |
| docling-core API 未验证 | MiMo 02 | 已实测 2.96.0 wheel 补验证 | 2.2 |
| export_to_dict 风险定位错 | MiMo 03 | 重定位为 load_from_json + LLM 语义 | 2.4、步骤 2.2 |
| 回退细节遗漏 | MiMo 04 | 三层回退 | 第 5 节 |
| CUDA 体积未量化 | MiMo 05 / DS F09 | 逐包量化 5.5GB；CPU-only 评估不采用；docker 承担 | 2.3 |
| 回归缺执行细节 | MiMo 06 / DS F05 | 抽样分层/判定清单/判定人/产出物规格化 | 步骤 2 |
| CI 不存在 | DS F01 | 手动验证矩阵 + 残余风险登记 | 步骤 3 |
| 回归平台单一 | DS F02 | Linux docker 子集回归（用户裁决） | 步骤 2.4 |
| 回退矛盾 + 资产混合 | DS F03 | 三层回退 + 冻结上传（用户裁决） | 第 5 节 |
| 模型权重变化未列风险 | DS F04 | 单列高风险 + 先导核对 | 2.4、风险清单 |
| PPTX/DOCX 缓解空转 | DS F06 | 撤销单元测试项，改真实转换冒烟 + 抽检量化 | 步骤 2.5 |
| min-py311 语义冲突 | DS F07 | 保持使命下界重写（用户裁决） | 步骤 1 |
| 根 README 遗漏 | DS F08 | 步骤 4 增加 | 步骤 4 |
| typer 盘点遗漏 | DS F10 | 补录已满足清单 | 2.1 |
| 缺快速冒烟 gate | DS F11 | 步骤 2.1 先导 gate | 步骤 2.1 |
| 美股样本声明不实 + HTML 缺口 | DS F12 | 修正描述；HTML 非目标显式声明 | 步骤 2、第 4 节 |
