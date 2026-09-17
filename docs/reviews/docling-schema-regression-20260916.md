# docling 2.90.0 → 2.127.0 schema 层样本回归报告

- 日期：2026-09-17（2.1 先导 gate 于 2026-09-16 通过）
- 执行：实施 Agent
- 方案：`docs/plans/docling-2-127-upgrade.md` 步骤 2.1 / 2.2
- 脚本：`utils/docling_schema_regression.py`（pyright 0 errors）
- 产物：`workspace/tmp/docling-regression/`（每样本结果 JSON + `summary.json`）
- 样本库只读，未写入任何文件。

## 1. 2.1 先导冒烟 gate（5 份：2 表格密集 + 1 扫描件 + 1 小文档 + 1 文本层对照）

| 样本 | 类型 | closed JSON | 新产出可解析 | 基线可解析 | 顶层 key diff | version 新/旧 | 计数 新 vs 旧（texts/tables/pictures） |
|---|---|---|---|---|---|---|---|
| fil_cn_dd1c9ce2… | 表格密集（基线 255 表） | ✓ | ✓ | ✓ | 无 | 1.10.0 / 1.10.0 | 3247/256/3 vs 3278/255/3 |
| fil_cn_95d26c81… | 表格密集（基线 247 表） | ✓ | ✓ | ✓ | 无 | 1.10.0 / 1.10.0 | 3422/248/3 vs 3432/247/3 |
| fil_cn_9c9acd3c… | 扫描件（1 页公告） | ✓ | ✓ | ✓ | 无 | 1.10.0 / 1.10.0 | 15/0/0 vs 14/0/0 |
| fil_cn_9acddd54… | 小文档（基线 5 表） | ✓ | ✓ | ✓ | 无 | 1.10.0 / 1.10.0 | 78/5/0 vs 77/5/0 |
| fil_cn_11502836… | 文本层对照（29 页） | ✓ | ✓ | ✓ | 无 | 1.10.0 / 1.10.0 | 181/21/1 vs 180/21/1 |

gate 结论：**全部通过**，进入全量。

## 2. 2.2 schema 层全量（250 份）

转换：生产入口 `dayu.documents.docling_runtime`（`do_ocr=True`、backend docling-parse、
设备 auto/MPS），4 worker 并行，分两批（2 worker 试跑 20 份 + 4 worker 全量续跑）。

| 断言 | 结果 |
|---|---|
| 转换错误 | **0 / 250** |
| closed-JSON 校验（`_is_closed_json_value` 真源） | **250 / 250 通过** |
| 新产出可解析（`DoclingDocument.model_validate_json`） | **250 / 250 通过** |
| 历史基线可解析（docling-core 2.96 `load_from_json` 反序列化 2.90 旧 json） | **250 / 250 通过** |
| 顶层 key 集合 diff | **0 / 250 有差异**（全部与历史基线 key 集一致） |
| schema version | **250 / 250 均为 1.10.0**（与基线一致，无 version 变化） |
| 计数完全一致份数 | 21 / 250 |

### 2.1 计数变化分布（229 份有差异）

| 字段 | 增加 | 减少 | 持平 | delta 范围 | 中位 |
|---|---|---|---|---|---|
| texts | 120 | 109 | 0 | [-454, +653] | +1 |
| tables | 86 | 1 | 142 | [-1, +7] | 0 |
| pictures | 2 | 11 | 216 | [-2, +1] | 0 |

### 2.2 差异模式分类

1. **schema version 变化**：无（250/250 均为 1.10.0）。
2. **顶层 key 增删**：无（key 集合零差异）。
3. **计数变化**：
   - texts：229 份均有差异但高度对称（120 增 / 109 减，中位 +1），大部分为 ±1 级别的
     text item 切分差异；少数大变化（-454 ~ +653）集中在少数文档，属解析粒度差异，
     待步骤 2.3 语义层判定是否影响 LLM 消费。
   - tables：86 份 +1~+7（表格结构识别增强，与 v2.113 原生图表解析 / 表格修复方向一致），
     仅 1 份 -1。
   - pictures：11 份 -1~-2、2 份 +1，变化面小。

## 3. 结论（schema 层）

- docling-core 2.96 对 2.90 产出的全部 250 份历史 json **反序列化兼容**（本层核心断言）。
- 新产出 schema 契约与历史基线完全同构：顶层 key 集、version 字段均无变化；
  差异仅存在于 texts/tables/pictures 计数分布（无契约破坏）。
- 无转换失败、无 closed-JSON 失败、无解析失败。

## 4. 产物与残余

- 产物：`workspace/tmp/docling-regression/results/*.json`（250 份逐样本断言明细）、
  `summary.json`、`full-run.log`。
- 残余限制：
  - 未做文档级内容 diff（text/table 内容语义变化属步骤 2.3 语义层职责）。
  - 新产出 json 未落盘（仅记录断言与计数），样本库零写入。
  - 步骤 2.5 PPTX/DOCX 冒烟、2.4 Linux docker rapidocr 回归为独立任务，不在本报告范围。
