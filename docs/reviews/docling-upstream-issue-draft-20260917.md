# 上游 Issue 草稿（英文正文）：TableFormer accurate 退化导致表格数据行丢失

- 日期：2026-09-17
- 状态：**草稿，尚未发布**（发布动作由用户/controller 执行）
- 来源报告：`docs/reviews/docling-regression-8492e128-rootcause.md`
  （根因定位）、`docs/reviews/docling-table-mode-ab-20260917.md`（40 份 A/B）
- 材料包（已脱敏，可直接附）：`workspace/tmp/docling-regression/upstream-issue/`
- 合规核验：材料包不含本机路径、主机名、凭据或任何私有数据；复现样例为
  **公开年报**（Pop Mart International Group Limited 2025 年年度报告，第 330 页，
  页码为报告内印刷页码）。所有路径/主机名已从 JSON 材料中剔除（核验见第 4 节）。

## 1. 建议标题

```
TableFormer (accurate) generates degenerate OTSL at max_steps cap → cell matcher drops table data rows (regression in 2.118.0+)
```

## 2. Issue 正文（英文，可直接粘贴）

````markdown
### Summary

With `TableFormerMode.ACCURATE`, some financial-report tables lose **all of their data
rows** while keeping the surrounding frame (title/header/label cells). The table is still
emitted with the same table count, but the merged digit text is gone.

Root cause on our side of the boundary: the TableFormer token generator emits a
**degenerate OTSL sequence that runs to `predict.max_steps` (1023 of 1024 steps) with
zero content tokens**, producing an all-empty grid; `MatchingPostProcessor` then drops
98 of 174 page cells as "matched neither a row nor a column band".

This is a **regression introduced in docling 2.118.0** (2.117.0 is good, 2.118.0 is bad,
with an identical `docling-ibm-models` 3.15.0 and `docling-parse` 7.20.0 on both sides).

### Environment

- docling: **2.127.0**
- docling-ibm-models: **4.0.2**
- docling-core: 2.96.0
- docling-parse: 7.20.0
- Python 3.11, macOS arm64 (Apple Silicon), CPU/MPS
- TableFormer artifacts revision: `v2.3.0` (`docling-project/docling-models`)

### Minimal reproduction

Single page extracted from a public annual report (Pop Mart International Group
Limited, 2025 Annual Report, page 330). Attached: `popmart-2025-annual-report-p331.pdf`.

```python
from docling.datamodel.accelerator_options import AcceleratorOptions, AcceleratorDevice
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.document_converter import DocumentConverter, PdfFormatOption

pipeline_options = PdfPipelineOptions()
pipeline_options.do_ocr = True
pipeline_options.do_table_structure = True
pipeline_options.accelerator_options = AcceleratorOptions(device=AcceleratorDevice.AUTO)
pipeline_options.table_structure_options.mode = TableFormerMode.ACCURATE
pipeline_options.table_structure_options.do_cell_matching = True

converter = DocumentConverter(
    format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
)
result = converter.convert("popmart-2025-annual-report-p331.pdf")
print(result.document.export_to_dict()["tables"][0]["data"]["table_cells"])
```

**Expected:** the "Movements in issued and fully paid ordinary shares" table contains its
data rows, e.g. `1,348,243,150`, `5,300,000`, `(4,700,000)`, `(10,468)`.

**Actual (2.127.0):** only framework cells are emitted (`USD'000 RMB'000`,
`普通股面值 普通股面值 庫存股數目 （附註`, `27 ）`, ...). The data values are absent from
both `texts` and `table_cells`.

**Control:** with `table_structure_options.mode = TableFormerMode.FAST` on the same page
and same version, all data cells are recovered.

### Version bisect (same single page, same pipeline options)

| docling | docling-ibm-models | docling-parse | result |
|---|---|---|---|
| 2.110.0 | 3.15.0 | 7.20.0 | good — 18 cells incl. all data rows |
| 2.115.0 | 3.15.0 | 7.20.0 | good |
| 2.117.0 | 3.15.0 | 7.20.0 | good |
| **2.118.0** | 3.15.0 | 7.20.0 | **bad** — 19 framework-only cells |
| 2.120.3 | 4.0.2 | 7.20.0 | bad |
| 2.126.0 | 4.0.2 | 7.20.0 | bad |
| 2.127.0 | 4.0.2 | 7.20.0 | bad |

Note the good/bad boundary sits inside docling itself, **not** in `docling-ibm-models`:
2.117.0 and 2.118.0 both resolve `docling-ibm-models==3.15.0` and
`docling-parse==7.20.0`.

### Isolation evidence (2.117.0 vs 2.118.0, instrumented `TFPredictor.multi_table_predict`)

| observed | 2.117.0 (good) | 2.118.0 (bad) |
|---|---|---|
| TableFormer weights revision | v2.3.0 | v2.3.0 (same) |
| input word tokens | 174 (91 unique texts) | 174 (same texts, same order, same bboxes) |
| table crop passed in (2x coords) | [138, 282, 1086, 1222] | [138, 282, 1088, 1222] (2pt wider on the right) |
| generated `rs_seq` length | 1023 | 1023 (both at the `max_steps` cap) |
| resulting grid / cells | 16×12 → 18 cells incl. data rows | 14×16 → 19 framework-only cells |

So: identical model weights, identical inference package, identical parse backend, and
token-for-token identical model input — yet different post-processing outcome. The only
difference we can see is a 2pt-wider table crop (and whatever layout/pipeline changes
produce it) between 2.117.0 and 2.118.0, plus a differing interpretation of the same
1023-step sequence.

### Mechanism detail (2.127.0 / docling-ibm-models 4.0.2)

The generator's OTSL sequence for this table:

- length 1023 (cap is `predict.max_steps = 1024` in the accurate `tm_config.json`)
- token histogram: `lcel` 691, `fcel` 115, `nl` 110, `ecel` 107
- **zero content tokens** — the sequence is structurally degenerate, and it does not
  terminate early

Decoding this sequence yields an all-empty grid. `MatchingPostProcessor` then logs:

```
MatchingPostProcessor WARNING  98 of 174 pdf cells matched neither a row nor a
column band of the 111x5 grid and were dropped from the table
```

i.e. all real content (including every data-row value) is discarded, and the survivors
are compressed into the 19 framework cells that appear in the output.

### Impact

Multi-page financial statements lose entire data rows while the table frame survives,
so downstream consumers read a structurally valid but numerically empty table — arguably
worse than a missing table, because nothing signals the loss. We found this in production
document processing (250-document corpus); the single page above reproduces it exactly.

Two related observations from a 40-document A/B (accurate vs fast) that may help scope
the issue: `fast` recovers the affected table completely on this sample, but we did
observe a small number of *reverse* losses on scanned pages with `fast`, so this is not
a simple "use fast instead" recommendation — the accurate path's handling of
max-steps-capped sequences looks like the thing to fix.

### Attachments

- `popmart-2025-annual-report-p331.pdf` — single page, public annual report
- `p331-text-layer.txt` — raw text layer of that page (shows the values are real text,
  not OCR/bitmap artifacts)
- `tableformer-probe-2.127.json` — instrumented `multi_table_predict` input (174 tokens
  with bboxes) and output (rs_seq stats, cell list) on 2.127.0
- `tf-input-comparison-2117-vs-2118.json` — the same instrumentation on 2.117.0 vs
  2.118.0, showing identical tokens and the differing outcome
- `bisect-results.md` — version bisect table
- `p331-rendered-216dpi.png` — rendered page for visual reference
````


## 3. 材料清单

| 文件（`workspace/tmp/docling-regression/upstream-issue/`） | 内容 | 说明 |
|---|---|---|
| `popmart-2025-annual-report-p331.pdf` | 单页 PDF（公开年报第 330 页） | 最小复现输入 |
| `p331-text-layer.txt` | 该页原始文本层 | 证明数值是真实文本，非 OCR/图形 |
| `tableformer-probe-2.127.json` | 2.127.0 插桩输入输出 | 174 tokens + bbox、rs_seq 统计、cell 列表 |
| `tf-input-comparison-2117-vs-2118.json` | 2.117 vs 2.118 插桩对比 | 输入逐项相同（含 `tokens_identical_text_order_bbox: true`），输出不同 |
| `bisect-results.md` | 版本二分表 | 7 个版本 |
| `p331-rendered-216dpi.png` | 页面渲染图 | 视觉参考 |

## 4. 合规核验（Tier-0，程序化扫描）

对材料包全部文本类产物做正则扫描，检查四类敏感模式：

| 文件 | 本机绝对路径 | 主机名/用户名 | 内网地址 | token/密钥 |
|---|---|---|---|---|
| `tableformer-probe-2.127.json` | 0 | 0 | 0 | 0 |
| `tf-input-comparison-2117-vs-2118.json` | 0 | 0 | 0 | 0 |
| `bisect-results.md` | 0 | 0 | 0 | 0 |
| `p331-text-layer.txt` | 0 | 0 | 0 | 0 |

- 产物来源：原始 `bisect-*.json` / `probe_dump.json` 曾含本机路径
  （`/Users/...` 与仓库名，来自 stdout 尾部捕获），**已重建为脱敏版本**，
  上述扫描为对脱敏产物的复核。
- 样例内容：Pop Mart International Group Limited 2025 年年度报告公开披露页，
  含公司名称、审计报告附注正文与财务数字——均为公开信息，可引用。
- 材料中不含：客户数据、内部系统信息、凭据、未公开财务数据、本机/组织标识。

## 5. 发布前检查清单（给发布者）

1. 确认目标仓库与 issue 模板（建议 `docling-project/docling`，Labels: `bug`,
   `table-structure`；如判定属 models 侧可改投 `docling-ibm-models`）。
2. 附材料包 6 个文件；确认附件不含本机路径（本报告第 4 节已扫描）。
4. 发布后回填 issue 链接到 `docs/reviews/docling-regression-8492e128-rootcause.md`
   第 8 节候选处置。
