# WU-CLI-SMOKE-01 Cancel/Retry Regression Fix — Re-review

- **Reviewer**: AgentMiMo
- **Date**: 2026-07-08
- **Branch**: `phase/host-issues-control`
- **Scope**: 16 files changed, +777 / -214
- **前序 review**: `wu-cli-smoke-01-cancel-retry-regression-review-mimo.md`
- **Verdict**: **PASS_WITH_FINDINGS**

---

## 维度 1：durable/memory.py 是否不再订阅 TOOL_AWAITING

### 结论：PASS

**证据**：

1. `dayu/host/durable/memory.py:89-101` — `_EVENT_TYPE_TOOL_AWAITING` 常量已删除；`_EVENT_TYPE_FILTER` tuple 不含 `TOOL_AWAITING`，仅保留 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`、`CONTEXT_COMPACTED`。
2. `conversation_memory_projection_event_filter()` 返回的 `ProjectionEventClassFilter.event_types` 不含 `TOOL_AWAITING`。
3. `test_conversation_memory_consumer_uses_shared_projection_event_filter` (`tests/host/test_memory_projection.py:1385-1394`) 断言 `consumer.event_filter.class_filters[0].event_types` 不含 `"TOOL_AWAITING"`。

**生产路径验证**：`ConversationMemoryProjectionConsumer.__init__` 调用 `conversation_memory_projection_event_filter()` 构造 filter，EventLog 读取时按此 filter 过滤，TOOL_AWAITING 事件不会到达 `project_conversation_memory_event`。

---

## 维度 2：memory.py 是否不再识别或投影 TOOL_AWAITING

### 结论：PASS

**证据**：

1. `dayu/host/memory.py:73-75` — `_EVENT_TYPE_TOOL_AWAITING` 常量已删除。
2. `dayu/host/memory.py:1244-1254` — `project_conversation_memory_event` 的 if/elif 链直接从 `RUN_SUCCEEDED` 跳到 `TOOL_RESULT_ACCEPTED`，无 `TOOL_AWAITING` 分支。
3. `_selected_awaiting_item`、`_selected_awaiting_text`、`_accepted_arguments_mapping` 三个函数已完全删除（原 1703-1776 行），无残留引用。
4. `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS`、`_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS_SOURCE_DIGEST`、`_PAYLOAD_FIELD_NORMALIZED_ARGUMENTS_DIGEST`、`_PAYLOAD_FIELD_TOOL_NAME` 四个 payload field 常量已删除。

**死分支检查**：`project_conversation_memory_event` 的 `else` 分支（line 1272-1275）会对未知 event_type 生成 `_unsupported_event_type_diagnostic`。但生产路径中 TOOL_AWAITING 被 durable filter 拦截，不会到达此函数。无死分支。

---

## 维度 3：测试是否覆盖有无 TOOL_AWAITING 的 memory 等价性

### 结论：PASS

**证据**：

1. **`test_tool_awaiting_does_not_project_llm_facing_memory`** (`tests/host/test_memory_projection.py:360-408`) — 验证 TOOL_AWAITING event 不产生 selected item、不产生 evidence item，且 memory_text 不含 awaiting/等待/取消/poll/abandoned 等 fragment。

2. **`test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics`** (`tests/host/test_memory_projection.py:411-467`) — **精确覆盖验收准则**：
   - 构造两组事件序列：
     - `ordinary_events`: USER_INPUT_ACCEPTED → TOOL_RESULT_ACCEPTED → RUN_SUCCEEDED
     - `with_awaiting_events`: USER_INPUT_ACCEPTED → TOOL_AWAITING → TOOL_RESULT_ACCEPTED → RUN_SUCCEEDED
   - 断言 `_llm_facing_memory_text_view(with_awaiting_snapshot) == _llm_facing_memory_text_view(ordinary_snapshot)`
   - 补充断言 with_awaiting snapshot 的 memory_text 不含 `TOOL_AWAITING`、`start_fins_download`、`CRCL`

3. **`_llm_facing_memory_text_view`** (`tests/host/test_memory_projection.py:207-227`) — 提取 `(role, text)` tuple 作为 LLM-facing 等价视图，只比较 role 和 text，不比较 event_id/sequence/run_id/source_refs 等 Host 内部字段。这是正确的等价性抽象。

**等价性机制说明**：`build_conversation_memory_snapshot_from_events` 直接调用 `project_conversation_memory_event`，不经过 event filter。但 TOOL_AWAITING 在 `project_conversation_memory_event` 中无对应分支，落入 `else` 生成 diagnostic。等价性测试比较的是 `_llm_facing_memory_text_view`（只含 selected + evidence 的 role/text），diagnostics 不在比较范围内。两组 snapshot 的 selected recent window 和 evidence 完全一致，满足验收准则。

---

## 维度 4：SEC 下载取消检查点覆盖

### 结论：PASS

**用户复现路径分析**：用户复现的 root cause 是 cancel 后 SEC 下载仍继续滚屏，具体路径包括：
- company resolve（ticker map + browse-edgar fallback）
- submissions / history fetch
- filing collection（filter_filings + extend_browse_edgar + retry_sc13）
- per-filing file list + download

**检查点覆盖**：

| 路径 | cancellation_checker 传播 | SecDownloadCancelledError 不吞 | 证据 |
|------|--------------------------|-------------------------------|------|
| `resolve_company` → `_http_get_json` | ✅ | N/A | sec_downloader.py:964 |
| `_resolve_company_via_browse_edgar_ticker` → `_http_get_bytes` | ✅ | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1020 |
| `_resolve_company_via_browse_edgar_ticker` → `fetch_submissions` | ✅ | ✅（SecDownloadCancelledError 不继承 RuntimeError） | sec_downloader.py:1046-1050 |
| `fetch_submissions` → `_http_get_json` | ✅ | N/A | sec_downloader.py:1081 |
| `fetch_json` → `_http_get_json` | ✅ | N/A | sec_downloader.py:1103 |
| `fetch_browse_edgar_filenum` → `_http_get_bytes` | ✅ | N/A | sec_downloader.py:1131 |
| `resolve_primary_document` → `_http_get_json` | ✅ | N/A | sec_downloader.py:1159 |
| `fetch_sc13_party_roles` → `_http_get_bytes` | ✅ | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1209 |
| `fetch_file_bytes` → `_http_download` | ✅ | N/A | sec_downloader.py:1237 |
| `list_filing_files` → `_raise_if_download_cancelled` | ✅ | ✅ 多处 checkpoint | sec_downloader.py:1275+ |
| `_try_fetch_index_items` → `_http_get_json` | ✅ | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1919 |
| `_try_fetch_index_header_documents` → `_http_get_bytes` | ✅ | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1960 |
| `_try_fetch_primary_linked_html_files` → `_http_get_bytes` | ✅ | ✅ `except SecDownloadCancelledError: raise` | sec_downloader.py:1998 |
| `classify_6k_remote_candidates` → `fetch_file_bytes` | ✅ | N/A | sec_filing_collection.py:190 |

**Pipeline 层传播**：

| 路径 | cancel_checker | SecDownloadCancelledError 处理 |
|------|---------------|------------------------------|
| `run_download_stream_impl` — resolve_company + fetch_submissions | ✅ | ✅ catch → `_cancelled_pipeline_completed_event` + return |
| `run_download_stream_impl` — filter/extend/retry | ✅ | ✅ catch → log + `_cancelled_pipeline_completed_event` + return |
| `run_download_stream_impl` — per-filing loop | ✅ 已有 `cancel_checker()` 检查 | ✅ 设置 `cancelled=True` |
| `run_download_single_filing_stream` — 6-K prefilter | ✅ | N/A（通过内部传播） |
| `run_download_single_filing_stream` — persist_rejected | ✅ | ✅ `except SecDownloadCancelledError: return` |
| `persist_rejected_filing_artifact` | ✅ `_raise_if_cancelled` | ✅ 多处 checkpoint |
| `should_keep_sc13_direction` | ✅ | ✅ `except SecDownloadCancelledError: raise` |
| `extend_with_browse_edgar_sc13` | ✅ | ✅ `except SecDownloadCancelledError: raise` |

**Protocol 签名同步**：所有 Protocol（`_DownloadWorkflowDownloader`、`SecDownloadWorkflowHost`、`SecDownloadFilingWorkflowHost`、`SecSc13WorkflowHost`、`_Sc13WorkflowDownloader`）均已同步添加 `cancellation_checker` / `cancel_checker` 参数。

**分层约束**：`SecDownloadCancelledError` 定义在 `dayu/fins/downloaders/sec_downloader.py`（Fins 域），被同层 pipeline 模块引用。无跨层依赖。`_cancelled_pipeline_completed_event` 和 `_raise_if_cancelled` 均为模块级私有函数，符合架构约束。

**测试覆盖**：`test_download_stream_cancel_stops_during_collection_before_filing_requests` 验证 `cancel_checker=lambda: True` 在 history fetch 阶段命中后 pipeline 终态为 `cancelled`，且 `list_filing_files` 不被调用。

---

## 维度 5：前序 findings 闭环

| ID | 前序状态 | 当前状态 | 说明 |
|----|---------|---------|------|
| F1 | LOW — 测试仅覆盖 collection 阶段取消 | **仍然存在** | 无新增 filing 处理阶段取消的端到端测试。不影响修复正确性，建议后续补充。 |
| F2 | INFO — `_cancelled_pipeline_completed_event` 签名风格 | **仍然存在** | 无代码变更，纯风格观察，不影响正确性。 |
| F3 | LOW — 缺少有无 awaiting 的等价性测试 | **已闭环** | `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics` 精确覆盖验收准则。 |

---

## Findings 汇总

| ID | 严重性 | 维度 | 文件:行号 | 描述 | 可验证证据 |
|----|--------|------|----------|------|-----------|
| F1 | LOW | 测试覆盖 | `tests/fins/test_sec_pipeline_download_stream.py:530` | 无 filing 处理阶段取消的端到端测试（collection 后、单 filing 下载中途取消） | 当前仅 `test_download_stream_cancel_stops_during_collection_before_filing_requests` 覆盖 collection 阶段 |
| F4 | INFO | 测试质量 | `tests/host/test_memory_projection.py:360-408` | `test_tool_awaiting_does_not_project_llm_facing_memory` 不检查 `snapshot.diagnostics`；TOOL_AWAITING 经 `build_conversation_memory_snapshot_from_events`（不过 filter）到达 `project_conversation_memory_event` 时会落入 `else` 生成 `_unsupported_event_type_diagnostic` | `dayu/host/memory.py:1272-1275` 的 `else` 分支；测试无 `diagnostics` 断言 |

**F4 说明**：这不是生产 bug — 生产路径中 `ConversationMemoryProjectionConsumer` 的 event filter 不含 `TOOL_AWAITING`，事件不会到达 `project_conversation_memory_event`。但测试直接调用 `build_conversation_memory_snapshot_from_events` 绕过了 filter，导致 TOOL_AWAITING 事件到达投影函数并生成 diagnostic。测试不检查 diagnostic 所以通过了，但 snapshot 实际上不干净。建议在测试中补充 `assert snapshot.diagnostics == ()` 或改用 consumer 路径投递事件。

---

## 结论

**PASS_WITH_FINDINGS**

实现正确解决了两个回归：

1. **Host memory awaiting 泄漏** — TOOL_AWAITING 从 durable filter、memory projection 常量、投影分支、helper 函数四个层面彻底清除。无隐性泄漏路径。
2. **SEC cancel propagation 不完整** — cancellation_checker 贯穿公司解析、submissions/history、filing 选择、browse-edgar、index/headers/candidate 收集、单 filing 文件处理全部路径。`SecDownloadCancelledError` 在所有 `except RuntimeError` 块中正确传播。

验收准则"有无 TOOL_AWAITING 第二轮 memory 语义一致"已由 `test_tool_awaiting_presence_does_not_change_llm_facing_memory_semantics` 精确覆盖。

四个 findings 均为 LOW/INFO 级别，不影响修复正确性。
