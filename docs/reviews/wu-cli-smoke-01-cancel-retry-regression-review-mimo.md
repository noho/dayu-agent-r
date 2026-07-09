# WU-CLI-SMOKE-01 Cancel/Retry Regression Fix — Code Review

- **Reviewer**: AgentMiMo
- **Date**: 2026-07-08
- **Branch**: `phase/host-issues-control`
- **Scope**: 16 files changed, +777 / -214
- **Artifacts reviewed**:
  - `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-root-cause-codex.md`
  - `docs/reviews/wu-cli-smoke-01-cancel-retry-regression-fix-codex.md`
- **Verdict**: **PASS_WITH_FINDINGS**

---

## 审查维度 1：Host Memory 是否彻底避免 TOOL_AWAITING 进入 LLM-facing memory

### 结论：PASS

**证据**：

1. **`dayu/host/memory.py:1251-1252`** — `TOOL_AWAITING` 分支已改为 `pass`，不再构造 `_selected_awaiting_item`，不向 `selected` 或 `recent_evidence` 写入任何内容。
2. **`dayu/host/memory.py`** — `_selected_awaiting_item`、`_selected_awaiting_text`、`_accepted_arguments_mapping` 三个函数已完全删除（原 1703-1776 行），无残留引用。
3. **`dayu/host/durable/memory.py:96-101`** — `_EVENT_TYPE_FILTER` 不再包含 `TOOL_AWAITING`，`conversation_memory_projection_event_filter()` 返回的 filter 只覆盖 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`、`CONTEXT_COMPACTED`。
4. **`dayu/host/durable/memory.py:92`** — `_EVENT_TYPE_TOOL_AWAITING` 常量已删除。

**验证**：
- `test_tool_awaiting_does_not_project_llm_facing_memory` 验证 TOOL_AWAITING event 不产生 selected item、不产生 evidence item，且 memory_text 不含任何 awaiting/等待/取消/poll/abandoned 等 fragment。
- `test_conversation_memory_consumer_uses_shared_projection_event_filter` 验证 consumer 的 event_types 不含 `TOOL_AWAITING`。

**隐性路径检查**：
- `dayu/host/read_api.py` 中的 `_tool_awaiting_activity` 是 Host activity projection（面向 Host 内部诊断/审计），不进入 LLM-facing memory schema，属于正常治理代码。
- `dayu/host/tool_trace.py:208` 中的 `_EVENT_TYPE_TOOL_AWAITING` 是 Tool Trace 投影，属于 Host 内部 trace/debug 通道，不进入 conversation memory。
- `dayu/host/waiting.py`、`dayu/host/engine_ingest.py`、`dayu/host/tool_runtime.py` 中的大量 `TOOL_AWAITING` 引用均为 Host awaiting 生命周期治理代码，不涉及 memory projection。

**无隐性泄漏路径**。

---

## 审查维度 2：SEC Cancel Propagation 覆盖度

### 结论：PASS_WITH_FINDINGS

**覆盖的路径**：

| 路径 | cancellation_checker 传播 | SecDownloadCancelledError 不吞 | 证据 |
|------|--------------------------|-------------------------------|------|
| `resolve_company` | ✅ 传入 `_http_get_json` | N/A（无 try/except） | sec_downloader.py:964-976 |
| `_resolve_company_via_browse_edgar_ticker` | ✅ 传入 `_http_get_bytes` + `fetch_submissions` | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1020-1021 |
| `fetch_submissions` | ✅ 传入 `_http_get_json` | N/A | sec_downloader.py:1081 |
| `fetch_json` | ✅ 传入 `_http_get_json` | N/A | sec_downloader.py:1103 |
| `fetch_browse_edgar_filenum` | ✅ 传入 `_http_get_bytes` | N/A | sec_downloader.py:1131 |
| `resolve_primary_document` | ✅ 传入 `_http_get_json` | N/A | sec_downloader.py:1159 |
| `fetch_sc13_party_roles` | ✅ 传入 `_http_get_bytes` | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1209-1210 |
| `fetch_file_bytes` | ✅ 传入 `_http_download` | N/A | sec_downloader.py:1237 |
| `list_filing_files` | ✅ 已有 `_raise_if_download_cancelled` | ✅ 多处 checkpoint | sec_downloader.py:1275+ |
| `_try_fetch_index_items` | ✅ 传入 `_http_get_json` | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1919 |
| `_try_fetch_index_header_documents` | ✅ 传入 `_http_get_bytes` | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1960 |
| `_try_fetch_primary_linked_html_files` | ✅ 传入 `_http_get_bytes` | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1998 |
| `classify_6k_remote_candidates` | ✅ 传入 `fetch_file_bytes` | N/A | sec_filing_collection.py:190 |

**Pipeline 层传播**：

| 路径 | cancel_checker 传播 | SecDownloadCancelledError 处理 |
|------|--------------------|-----------------------------|
| `run_download_stream_impl` — resolve_company + fetch_submissions | ✅ | ✅ catch → `_cancelled_pipeline_completed_event` + return |
| `run_download_stream_impl` — filter_filings / extend / retry | ✅ 传入 cancel_checker | ✅ catch → log + `_cancelled_pipeline_completed_event` + return |
| `run_download_stream_impl` — per-filing loop | ✅ 已有 `cancel_checker()` 检查 | ✅ 设置 `cancelled=True` |
| `run_download_single_filing_stream` — 6-K prefilter | ✅ 传入 cancel_checker | N/A（通过 `_http_get_bytes` 内部传播） |
| `run_download_single_filing_stream` — persist_rejected | ✅ 传入 cancel_checker | ✅ `except SecDownloadCancelledError: return` |
| `persist_rejected_filing_artifact` | ✅ `_raise_if_cancelled` checkpoint | ✅ 多处 checkpoint |
| `filter_sc13_by_direction` | ✅ 传入 cancel_checker | N/A（通过 should_keep 传播） |
| `should_keep_sc13_direction` | ✅ 传入 downloader + persist | ✅ `except SecDownloadCancelledError: raise` |
| `extend_with_browse_edgar_sc13` | ✅ 传入 cancel_checker | ✅ `except SecDownloadCancelledError: raise` |
| `retry_sc13_if_empty` | ✅ 传入 cancel_checker | N/A（通过 extend/filter 传播） |

**Protocol 签名同步**：
- `_DownloadWorkflowDownloader` — ✅ `resolve_company`、`fetch_submissions` 已加 `cancellation_checker`
- `SecDownloadWorkflowHost` — ✅ `_filter_filings`、`_extend_with_browse_edgar_sc13`、`_retry_sc13_if_empty` 已加 `cancel_checker`
- `SecDownloadFilingWorkflowHost` — ✅ `_pre_screen_6k_remote_candidates`、`_persist_rejected_filing_artifact` 已加 `cancel_checker`
- `SecSc13WorkflowHost` — ✅ `_filter_filings`、`_extend_with_browse_edgar_sc13`、`_should_keep_sc13_direction`、`_persist_rejected_filing_artifact` 已加 `cancel_checker`
- `_Sc13WorkflowDownloader` — ✅ `fetch_browse_edgar_filenum`、`resolve_primary_document`、`fetch_sc13_party_roles`、`list_filing_files` 已加 `cancellation_checker`

**测试覆盖**：
- `test_download_stream_cancel_stops_during_collection_before_filing_requests` — 验证 collection 阶段取消后 `list_filing_files` 不被调用，pipeline 终态为 `cancelled`。

#### Finding F1: 测试仅覆盖 collection 阶段取消，缺少 filing 处理阶段取消的端到端测试

- **严重性**: LOW
- **文件**: `tests/fins/test_sec_pipeline_download_stream.py:530`
- **证据**: 当前 `test_download_stream_cancel_stops_during_collection_before_filing_requests` 只验证了 `cancel_checker=lambda: True` 在 collection 阶段（history fetch）命中后停止。但没有测试覆盖：(1) collection 完成后、进入单 filing 下载时的取消；(2) 单 filing 文件处理中途取消后产出 cancelled 而非 failed 的终态。
- **建议**: 补充一个测试用 `CancelAwareCollectionDownloader` 的变体，在 `list_filing_files` 或 `download_single_filing_stream` 阶段触发取消，验证终态为 `cancelled` 且已完成的 filing 不被误报为 `failed`。

#### Finding F2: `_cancelled_pipeline_completed_event` 使用空 tuple 默认值语义略有歧义

- **严重性**: INFO
- **文件**: `dayu/fins/pipelines/sec_download_workflow.py:617-685`
- **证据**: `_cancelled_pipeline_completed_event` 接受 `warnings: tuple[str, ...]` 和 `filing_results: tuple[dict[str, JsonValue], ...]`，两处调用均传入 `()`。这是正确的——取消时无已完成 filing。但函数签名上 `filing_results` 的类型注解暗示可能有内容，实际语义是"可能为空的已完成结果"。这是风格层面的观察，不影响正确性。
- **建议**: 无需修改，当前实现正确。如有后续扩展（如取消前已完成部分 filing），此函数天然支持。

---

## 审查维度 3：新 Helper / Protocol 签名 / Tests 是否符合 AGENTS.md 要求

### 结论：PASS

**类型约束**：
- 所有新增 `cancellation_checker` 参数均为 `Optional[Callable[[], bool]]`，无 `Any`、无 `object`。
- `_cancelled_pipeline_completed_event` 所有参数均有明确类型注解。
- `_raise_if_cancelled` 参数类型为 `Callable[[], bool] | None`。

**Docstring 约束**：
- 所有新增/修改的 public 方法均有完整中文 docstring，包含 Args、Returns、Raises。
- `_cancelled_pipeline_completed_event` docstring 完整覆盖所有参数。
- `_raise_if_cancelled` docstring 完整。

**架构边界**：
- `SecDownloadCancelledError` 定义在 `dayu/fins/downloaders/sec_downloader.py`，被 `sec_download_workflow.py`、`sec_download_persistence.py`、`sec_sc13_filtering.py` 引用。这是合理的——它是 Fins 域内的取消语义异常。
- `_cancelled_pipeline_completed_event` 定义在 `sec_download_workflow.py` 模块级私有函数，符合模块级私有辅助函数约束。
- `_raise_if_cancelled` 定义在 `sec_download_persistence.py` 模块级私有函数，同上。

**兼容性**：
- 无兼容性 wrapper / facade / re-export。
- 所有 `cancellation_checker` 参数均有默认值 `None`，向后兼容。

---

## 审查维度 4：测试是否真的覆盖根因

### 结论： PASS_WITH_FINDINGS

**Memory projection 测试**：
- `test_tool_awaiting_does_not_project_llm_facing_memory` — 覆盖根因：TOOL_AWAITING event 不产生 LLM-facing memory。测试不仅验证 evidence 为空，还验证 selected_recent_window 不含 awaiting 语义 fragment。这是正确的根因覆盖。
- `test_conversation_memory_consumer_uses_shared_projection_event_filter` — 补充验证 filter 真源不含 TOOL_AWAITING。

**Cancel propagation 测试**：
- `test_download_stream_cancel_stops_during_collection_before_filing_requests` — 覆盖 collection 阶段取消根因。

#### Finding F3: 缺少 "有无 awaiting 的第二轮对话 memory 语义一致" 的端到端断言

- **严重性**: LOW
- **文件**: `tests/host/test_memory_projection.py:337`
- **证据**: 总控裁决要求"有无 awaiting 的第二轮对话，LLM 拿到的 memory 语义应一致"。当前测试验证了 TOOL_AWAITING event 不产生 memory，但没有构造一个对比场景：同样的 user input + tool result，一组中间有 TOOL_AWAITING event、一组没有，验证两者 memory snapshot 一致。这是裁决要求的精确语义验证。
- **建议**: 补充一个参数化测试，对比有/无 TOOL_AWAITING event 时的 memory snapshot，断言两者 selected_recent_window 和 evidence 完全一致。

---

## 审查维度 5：README 更新是否符合触发规则且未过度扩写

### 结论： PASS

**`dayu/host/README.md`**：
- 删除了 `TOOL_AWAITING` 的 memory projection 描述（原"把已接受等待工具调用中的 LLM-safe 参数投影为 recent evidence"）。
- 新增一段明确声明 Memory 不消费 Host waiting lifecycle 事件，列举了 `TOOL_AWAITING`、`RUN_WAITING`、`CANCEL_REQUESTED`、`RUN_CANCELLED`、wait record、poller outcome、abandon。
- 触发条件：`dayu/host/` 修改 → 检查 `dayu/host/README.md`。✅ 命中。
- 内容范围：Memory projection 行为变更属于 Host README 职责。✅ 属于。
- 未过度扩写：只修改了 Memory 事件列表相关段落，未扩展其他章节。

**`dayu/fins/README.md`**：
- 更新了 SEC 下载取消检查点描述，新增"公司解析、submissions / history 拉取、Browse EDGAR 补选、index / headers / candidate 文件收集"。
- 触发条件：`dayu/fins/` 修改 → 检查 `dayu/fins/README.md`。✅ 命中。
- 内容范围：SEC 下载取消行为变更属于 Fins README 职责。✅ 属于。
- 未过度扩写：只更新了取消检查点列表。

**`tests/README.md`**：
- 新增两段：一段描述 SEC pipeline 取消测试覆盖，一段描述 memory projection 测试覆盖。
- 触发条件：`tests/` 修改 → 检查 `tests/README.md`。✅ 命中。
- 内容范围：新增测试的覆盖描述属于 tests README 职责。✅ 属于。
- 未过度扩写：只新增了对应的覆盖描述段落。

---

## Findings 汇总

| ID | 严重性 | 维度 | 文件 | 描述 |
|----|--------|------|------|------|
| F1 | LOW | Cancel Propagation | `tests/fins/test_sec_pipeline_download_stream.py:530` | 测试仅覆盖 collection 阶段取消，缺少 filing 处理阶段取消的端到端测试 |
| F2 | INFO | Cancel Propagation | `dayu/fins/pipelines/sec_download_workflow.py:617-685` | `_cancelled_pipeline_completed_event` 签名风格观察，不影响正确性 |
| F3 | LOW | 测试根因覆盖 | `tests/host/test_memory_projection.py:337` | 缺少"有无 awaiting 第二轮 memory 语义一致"的对比断言 |

---

## 总结

本次修复正确解决了两个回归问题：

1. **Host memory 泄漏 awaiting 语义**：TOOL_AWAITING event 不再产生 LLM-facing memory，durable memory consumer 不订阅 awaiting 事件，三个 awaiting 专属 helper 函数已删除。无隐性泄漏路径。

2. **SEC cancel propagation 不完整**：cancellation_checker 已贯穿公司解析、submissions/history 拉取、filing 选择、browse-edgar 补选、index/headers/candidate 文件收集、单 filing 文件处理等全部路径。SecDownloadCancelledError 在所有 try/except RuntimeError 块中均通过 `except SecDownloadCancelledError: raise` 正确传播。Pipeline 层在 collection 阶段和 filing 处理阶段均有 catch → cancelled 终态的处理。

三个 findings 均为 LOW/INFO 级别，不影响修复正确性，建议作为后续改进项。
