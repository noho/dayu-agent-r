# Plan Review: WU-CLI-DOWNLOAD-01 Slice 3 Standalone Amendment

- **Review target**: `docs/gateflow/wu-cli-download-01-slice3-plan-amendment-20260810-045002.md`
- **Base plan**: `docs/gateflow/wu-cli-download-01-plan-20260809.md`
- **Baseline HEAD**: `5c09609946d7e5628ce8dbc1ea856439668a82a9`
- **Branch**: `codex/download-oracle`
- **Review type**: Adversarial plan review（只审计划，不修改 artifact）
- **Reviewer**: AgentDS
- **Timestamp**: 2026-08-10 04:55 UTC

---

## 1. Review Scope & Method

本次 review 仅审 Slice 3 standalone amendment artifact。不审基础计划（已通过两路 review 并裁决），不修改产品代码、测试或 amendment。

Review 方法：
1. 通读 amendment 全部章节，提取关键 claims 与 assumptions。
2. 对每个 claim 用 `rg`/AST 仓库级穷举 + 源码直接阅读做独立核验。
3. 对 6 个用户指定挑战维度逐一压测。
4. 区分 blocking / non-blocking findings，附直接证据。

---

## 2. Assumptions Tested

| # | Amendment Claim | 核验方式 | 结果 |
|---|---|---|---|
| A1 | 仓库级 `CnPipeline(...)` 共 15 个直接构造 + 1 个子类 | `rg` + AST 双扫描 | **证实**。精确匹配 15+1 |
| A2 | `test_cn_pipeline.py` 中 4 个构造点使用旧 callable injection | 直接读源码 lines 332-336, 398-402, 450-454, 523-527 | **证实**。四处均传 `convert_pdf_to_docling_json=converter` |
| A3 | `test_cn_pipeline.py` 中 6 个构造点为 upload/default，无需修改 | 直接读源码 lines 376, 559, 618, 668, 721, 777 | **证实**。均为 upload 测试或仅验证默认 client 类型 |
| A4 | download 完整事件序列仅两处精确断言 | `rg 'DownloadEventType\.' tests` | **证实**。仅 `test_cn_pipeline.py:468-477` 与 `test_cn_download_workflow.py:944-952` |
| A5 | upload tests 使用不同 enum（UploadFilingEventType / UploadMaterialEventType），不会被误改 | 直接读源码 lines 581-587, 686-691 | **证实**。upload 事件序列使用独立 enum 类型 |
| A6 | 无 alias import、动态构造或间接 factory | `rg 'import.*CnPipeline|from.*cn_pipeline import'` | **证实**。全部使用原名直接 import |
| A7 | `dayu/runtime/interruptible_process.py` 公开 API 为 `start()`，无 `spawn()` | 直接读源码 line 313 | **证实**。public method 为 `start()`，不存在 `spawn()` |
| A8 | production 中 `asyncio.to_thread(convert_pdf...)` 仅在 `cn_download_filing_workflow.py:331` | `rg 'asyncio\.to_thread'` + 直接阅读 | **证实**。仅此一处，为基础计划 Slice 3 production 修改目标 |
| A9 | `service_runtime.py:519` 构造为 upload pipeline，无需修改 | 直接读源码 lines 510-527 | **证实**。变量名为 `cn_upload_pipeline`，不传 conversion 参数 |
| A10 | `cn_pipeline.py:1868,1917` 为 adapter factory，不传 conversion | 直接读源码 | **证实**。`build_cn_download_adapter` / `build_hk_download_adapter` 均不传 conversion |

---

## 3. 六维度压测结果

### 3.1 仓库级 call-site 穷举 — allowlist 外是否真只缺 `test_cn_pipeline.py`

**结论：证实。** 独立核验确认：

- 所有 15 个 `CnPipeline(...)` 构造与 1 个 `_RecordingPipeline(CnPipeline)` 子类 `super().__init__` 已穷举。
- conversion injection（`convert_pdf_to_docling_json=`）共出现在 10 个位置：
  - Production 3 处（protocol 定义 + facade 构造/属性 + workflow 透传），均在基础计划 Slice 3 allowlist。
  - Test 7 处：`test_cn_download_runtime.py` 2 处、`test_cn_download_workflow.py` 3 处（均在原 allowlist）；`test_cn_pipeline.py` 4 处（**不在原 allowlist，为本 amendment 新增目标**）。
- 不存在 alias、factory indirection、动态名称构造或间接 import。

### 3.2 `test_cn_pipeline.py` 是否为 CnPipeline facade owner contract

**结论：是。** 证据：

- 模块 docstring（line 1）：`"""CnPipeline download facade 行为测试。"""`
- `test_download_stream_runs_cn_workflow_with_injected_discovery_client`（line 433）直接构造真实 `CnPipeline`、调用 `download_stream`、断言完整公开事件顺序——这正是 facade 级 contract proof。
- `_PipelineDownloadFakeConverter` 是 facade conversion dependency 的确定性替身，其签名必须与 `CnPipeline` 的 typed injection contract 一致。
- 若不在该文件迁移，则 production 只能保留旧 callable 兼容路径，违反 semantic ownership 与 no-compat 约束。

**应迁移而非生产兼容**：正确。amendment 裁决与项目约束一致。

### 3.3 精确允许的 4 处 typed runner 注入、事件序列与 cancel 边界

**3.3.1 4 处 typed runner 注入**

| 位置 | 当前写法 | 迁移目标 | 验证 |
|---|---|---|---|
| `:332-335` | `convert_pdf_to_docling_json=converter` | `docling_conversion_runner=runner` | ✓ |
| `:398-401` | `convert_pdf_to_docling_json=converter` | `docling_conversion_runner=runner` | ✓ |
| `:450-453` | `convert_pdf_to_docling_json=converter` | `docling_conversion_runner=runner` | ✓ |
| `:523-526` | `convert_pdf_to_docling_json=converter` | `docling_conversion_runner=runner` | ✓ |

**3.3.2 download 事件序列**

当前 sequence（line 468-477）：`... FILE_DOWNLOADED -> CONVERSION_STARTED -> FILING_COMPLETED ...`

Amendment 要求在 `CONVERSION_STARTED` 与 `FILING_COMPLETED` 之间加入 `CONVERSION_COMPLETED`。该新增 enum member 需同时加入 `DownloadEventType`（`dayu/fins/pipelines/download_events.py`），此项为基础计划 Slice 3 production 修改范围。

**3.3.3 completed-after-cancel owner test 边界**

Amendment §5.2 明确：`CONVERSION_COMPLETED` 后的 cancellation checkpoint owner proof 留在 `test_cn_download_workflow.py`（已在原 allowlist），使用 deterministic cancellation state。不得将该语义塞进 facade fake 或 fixture side effect。**边界正确。**

**3.3.4 不会误改 upload**

已验证：upload 事件序列使用 `UploadFilingEventType.CONVERSION_STARTED`（line 583）和 `UploadMaterialEventType.CONVERSION_STARTED`（line 688），属于独立 enum 类型，与 `DownloadEventType.CONVERSION_STARTED` 无交叉。Amendment §5.2(4) 明确禁止修改 upload 区域。Amendment §3.4 显式区分 upload conversion 与 download conversion。

### 3.4 遗漏检查：constructor / subclass / alias / pyright / fixture / 事件消费者

| 检查项 | 结果 | 证据 |
|---|---|---|
| CnPipeline 构造穷举 | 无遗漏 | `rg '\bCnPipeline\s*\('` 全覆盖 |
| 子类 super().__init__ | 仅 1 个，已在原 allowlist | `_RecordingPipeline` at `test_cn_download_runtime.py:268` |
| alias import | 无 | 全部 import 使用原名 |
| pyright 影响 | 受控 | 新增 `CONVERSION_COMPLETED` enum member 后，match 语句如有 exhaustive check 会触发；amendment 未显式提及 match exhaustiveness，但在基础计划 Slice 3 affected union 覆盖范围内 |
| fixture 遗漏 | 无 | `_build_pipeline` helper 在 `test_cn_download_workflow.py:731`，已在原 allowlist |
| 事件消费者遗漏 | 无 | `cn_pipeline.py:221`（`_emit_adapter_download_progress`）消费 `CONVERSION_STARTED`，为基础计划 production 修改范围；adapter progress sink 是否新增 `CONVERSION_COMPLETED` handler 由基础计划决定 |
| SEC download tests | 不受影响 | SEC tests 不引用 `CONVERSION_STARTED`，仅用 `FILING_STARTED`/`FILING_COMPLETED`/`FILING_FAILED`/`PIPELINE_COMPLETED` |

### 3.5 验证可执行性

| 验证项 | 可执行性 | 评价 |
|---|---|---|
| Owner tests + affected union（§6.1） | 可执行 | 命令完整，文件列表明确 |
| 5 次防 flaky（§6.1） | 可执行 | 限定在 process/cancellation deterministic owner set；正确排除了 `test_cn_pipeline.py`（纯 deterministic fake） |
| 单文件 coverage（§6.2） | 可执行 | `--fail-under=80` 仅对修改的 production 文件；本 amendment 不修改 production，故不触发 |
| AST scans（§6.3） | 可执行 | 10 项 scan 均明确、可自动化 |
| runtime helper 只读（§6.3(5)） | 可执行 | `git diff --exit-code -- dayu/runtime/interruptible_process.py` |
| Stop conditions（§7） | 可执行 | 7 项 stop condition 均具体、有判定标准、可自动检查 |

**NB-01（非阻塞）：match exhaustiveness 未显式提及。** 当前 `_emit_adapter_download_progress`（`cn_pipeline.py:192-249`）对 `DownloadEventType` 使用 `if/elif` 链而非 `match` 语句，新增 `CONVERSION_COMPLETED` enum member 不会触发 exhaustive check 失败。但若基础计划实现中任何位置使用了 `match event.event_type` 穷举，则需同步更新。此项为基础计划 Slice 3 implementation 关注点，不构成 amendment 缺陷。

### 3.6 Production scope 与语义所有权漂移

**结论：无漂移，无 scope 扩大。**

- Amendment §5.3 明确"基础计划列出的全部 production allowlist 原样保持，不新增 production 文件"。
- Amendment 仅新增一个 test file 到 allowlist。
- 语义所有权裁决（§4）与基础计划 §5 一致：`CnDoclingConversionRunner` Protocol owner 在 `cn_download_protocols.py`，production runner owner 在 `cn_docling_process.py`，facade contract owner 在 `cn_pipeline.py`，事件顺序 owner 在 `cn_download_filing_workflow.py` + `download_events.py`。
- `test_cn_pipeline.py` 作为 facade owner contract test，随 owner 迁移是正确做法，不是 scope creep。

---

## 4. Findings

### NB-01 — 非阻塞 — `CONVERSION_COMPLETED` 在 production filing workflow 中的精确插入位置未在 amendment 中重申

- **位置**: Amendment §5.2(3) 仅描述测试端事件序列变更，未引用 production 端插入位置
- **问题类型**: 不可直接实施（对只看 amendment 的 implementation agent）
- **当前写法**: "仅在 `CONVERSION_STARTED` 后加入 `DownloadEventType.CONVERSION_COMPLETED`"
- **反例/失败场景**: Implementation agent 若只看 amendment 不看基础计划 §5.5，可能不清楚 `CONVERSION_COMPLETED` 在 `cn_download_filing_workflow.py:356-368`（conversion 成功后、`_commit_cn_filing_assets_batch` 前、cancellation checkpoint 通过后）的精确插入位置
- **为什么有问题**: amendment 定位为 standalone，但实际依赖基础计划 §5.5 的 production 状态顺序定义
- **直接证据**: `cn_download_filing_workflow.py:356-409`（当前 conversion success → commit → FILING_COMPLETED，中间无 CONVERSION_COMPLETED 事件）；基础计划 §5.5 定义了 `PDF_READY -> CONVERSION_STARTED -> CONVERSION_COMPLETED -> PUBLICATION_ELIGIBLE` 顺序
- **影响**: implementation agent 跑偏（概率低，因为 amendment §1 声明基础计划保持不修改并作为上下文）
- **建议改法和验证点**: 在 §5.2(3) 增加对基础计划 §5.5 production 状态顺序的交叉引用；或保持现状，因为 §1 已声明基础计划为上下文
- **修复风险**: 低
- **严重程度**: 低

### NB-02 — 非阻塞 — `_RecordingPipeline` 子类的 migration 未在 amendment checklist 中显式列出

- **位置**: Amendment §3.2 提到"1 个子类"，§5.2 精确变更列表只覆盖 `test_cn_pipeline.py`
- **问题类型**: 文档完整性
- **当前写法**: §3.2 表格中"1 个子类 `super().__init__(...)`"未具名
- **反例/失败场景**: Implementation agent 可能不确定 `_RecordingPipeline`（`test_cn_download_runtime.py:268`）是否需要在本 amendment 中处理
- **为什么有问题**: `_RecordingPipeline.__init__` 调用 `super().__init__(..., convert_pdf_to_docling_json=_RuntimeFakeConverter())`，当 constructor 参数名从 `convert_pdf_to_docling_json` 改为 `docling_conversion_runner` 时，此调用会失败。但该文件已在原 Slice 3 allowlist 中，由基础计划覆盖
- **直接证据**: `test_cn_download_runtime.py:284-295`
- **影响**: 短暂困惑（不影响正确实施，因文件已在 allowlist）
- **建议改法和验证点**: 在 §5.2 或 §5.3 中加一句明确 `_RecordingPipeline` 由基础计划 Slice 3 覆盖、本 amendment 不重复
- **修复风险**: 低
- **严重程度**: 低

---

## 5. Open Questions

无。所有关键事实已通过源码直接核验确认。

---

## 6. Residual Risks

| Risk | Classification | Disposition |
|---|---|---|
| 基础计划 Slice 3 implementation 中若 `DownloadEventType` 出现 `match` exhaustive check，新增 `CONVERSION_COMPLETED` 会触发遗漏 | deferred to base plan implementation | 基础计划 Slice 3 implementation agent 需检查。当前 production 代码无 `match` exhaustive check（均为 `if/elif`） |
| `_emit_adapter_download_progress` 是否需要新增 `CONVERSION_COMPLETED` handler | deferred to base plan Slice 3 | 非本 amendment 范围；进度投影是 production concern |
| `test_cn_pipeline.py` 的新 fake（实现 `CnDoclingConversionRunner` Protocol）在同步测试上下文中的 async 调用兼容性 | deferred to implementation | deterministic fake 的 `async def` 方法在 `pipeline.download()`（同步包装 `asyncio.run`）中可正常 await |

---

## 7. Final Conclusion: **PASS**

本 amendment 动机成立、穷举充分、边界精确、可执行。未发现 blocking finding。

**核心确认**：
- `test_cn_pipeline.py` 的 4 处旧 callable injection 是 allowlist 外的唯一遗漏——仓库级双扫描证实。
- 该文件是 `CnPipeline` facade owner contract test——迁移是正确做法，不应做生产兼容。
- 4 处 typed runner 注入、download 事件序列、completed-after-cancel owner test 边界均正确且不会误改 upload。
- 无 constructor/subclass/alias/pyright/fixture/事件消费者遗漏。
- 全部验证步骤（tests、5x 防 flaky、coverage、AST scans、runtime helper 只读、stop conditions）可执行。
- 无 production scope 扩大或语义所有权漂移。

**两处 non-blocking findings（NB-01, NB-02）建议采纳但不阻塞进入 implementation。**

下一合法动作：等待另一路独立 planreview 完成，两路均 accepted 后进入 Slice 3 implementation。
