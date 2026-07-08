# WU-CLI-SMOKE-01 cancel retry regression review — AgentDS

## 审查结论：PASS_WITH_FINDINGS

修复动机与方向与总控裁决一致。awaiting lifecycle 已从 LLM-facing memory 中彻底移除；SEC cancel propagation 已贯穿全部公开 downloader 方法与 collection/SC13/filing/persistence 路径。测试覆盖根因场景。所有 findings 均为 LOW 严重性（docstring 遗漏、死代码残留），不影响正确性。

---

## 审查维度 1：Host memory 是否彻底避免 TOOL_AWAITING 进入 LLM-facing memory

### 1.1 durable consumer event filter — PASS

`dayu/host/durable/memory.py:96-100` — `_EVENT_TYPE_FILTER` 已移除 `_EVENT_TYPE_TOOL_AWAITING`。`conversation_memory_projection_event_filter()` 产出的 `ProjectionEventFilter` 不再订阅 TOOL_AWAITING canonical fact。

`dayu/host/durable/memory.py:92` — `_EVENT_TYPE_TOOL_AWAITING` 常量定义已删除。

**验证**：`tests/host/test_memory_projection.py:1311-1313` 断言 `"TOOL_AWAITING" not in event_types`。

### 1.2 projection 函数 — PASS

`dayu/host/memory.py:1251-1252` — `TOOL_AWAITING` 分支改为 `pass`，不再调用 `_selected_awaiting_item` 或修改 `selected_recent_window` / `recent_evidence`。

`dayu/host/memory.py:1700-1733` — `_selected_awaiting_item`、`_selected_awaiting_text`、`_accepted_arguments_mapping` 三个函数已删除。

`dayu/host/memory.py:80-83` — `_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS`、`_PAYLOAD_FIELD_ACCEPTED_ARGUMENTS_SOURCE_DIGEST`、`_PAYLOAD_FIELD_NORMALIZED_ARGUMENTS_DIGEST`、`_PAYLOAD_FIELD_TOOL_NAME` 四个常量已删除。

**验证**：`tests/host/test_memory_projection.py:337-389` 测试 `test_tool_awaiting_does_not_project_llm_facing_memory` 断言：
- selected_recent_window 只有 USER role，无 EVIDENCE role
- evidence == ()
- memory_text 不包含 "等待"、"awaiting"、"外部工具"、"任务"、"启动"、"取消"、"abandoned"、"poll"、"已接受"
- memory_text 不包含 "start_fins_download"、"CRCL"
- diagnostics == ()

### 1.3 隐性泄漏路径检查 — PASS

检查了以下可能泄漏 awaiting 语义的路径，均无问题：

- `dayu/host/read_api.py:102,1091` — Host activity projection 仍引用 TOOL_AWAITING 用于 activity view（非 memory projection），属于 Host/CLI 运行时展示，不进入 LLM-facing memory schema。
- `dayu/host/tool_trace.py:81,208` — Tool trace 仍消费 TOOL_AWAITING 用于 provider request 关联与 timing metadata，属于 tool trace diagnostic（非 memory projection）。
- `dayu/host/engine_ingest.py` — TOOL_AWAITING 仍由 Engine ingest 处理（Host wait/resume state machine），不进入 memory projection。
- `dayu/host/waiting.py` — TOOL_AWAITING accept/ack/reject/abandon 属于 Host durable wait governance，不进入 memory projection。
- `dayu/host/run_input.py:1223` — Memory projection consumer 通过 `conversation_memory_projection_event_filter()` 取 filter，该 filter 已排除 TOOL_AWAITING。

**结论**：TOOL_AWAITING 仅在 Host activity view、tool trace、wait governance、engine ingest 中使用，这些都不是 LLM-facing memory 消费路径。Memory projection 两条防线（filter 排除 + projection 函数 pass）确保 awaiting 不进入模型上下文。

### Finding 1.1 — 死代码残留

- **文件/行号**：`dayu/host/memory.py:75`（常量 `_EVENT_TYPE_TOOL_AWAITING`），`dayu/host/memory.py:1251-1252`（`elif event.event_type == _EVENT_TYPE_TOOL_AWAITING: pass`）
- **严重性**：LOW
- **证据**：durable consumer event filter 已排除 TOOL_AWAITING，`project_conversation_memory_event` 永远不会收到该 event type，分支为死代码。常量 `_EVENT_TYPE_TOOL_AWAITING` 仅被此死分支引用。
- **影响**：无功能影响（defense-in-depth），但违反 "禁止兼容性代码" 的编码硬约束精神。若保留，建议加注释说明是 defense-in-depth。
- **建议**：可保留为 defense-in-depth（推荐），或删除常量与分支。删除需同步移除 `dayu/host/durable/memory.py` 对 `_EVENT_TYPE_TOOL_AWAITING` 的原来定义处的注释残留（已无）。

---

## 审查维度 2：SEC cancel propagation 覆盖完整性

### 2.1 公开 downloader 方法 — PASS

所有公开方法均已添加 `cancellation_checker: Optional[Callable[[], bool]] = None` 参数并传递给底层 HTTP helper：

| 方法 | 行号 | 传递到 |
|------|------|--------|
| `resolve_company` | `sec_downloader.py:945-951` | `_http_get_json` (ticker map), `_resolve_company_via_browse_edgar_ticker` |
| `_resolve_company_via_browse_edgar_ticker` | `sec_downloader.py:992-996` | `_http_get_bytes` (browse-edgar), `fetch_submissions` |
| `fetch_submissions` | `sec_downloader.py:1062-1068` | `_http_get_json` |
| `fetch_json` | `sec_downloader.py:1088-1091` | `_http_get_json` |
| `fetch_browse_edgar_filenum` | `sec_downloader.py:1110-1114` | `_http_get_bytes` |
| `resolve_primary_document` | `sec_downloader.py:1141-1144` | `_http_get_json` (index.json) |
| `fetch_sc13_party_roles` | `sec_downloader.py:1173-1176` | `_http_get_bytes` (index-headers) |
| `fetch_file_bytes` | `sec_downloader.py:1222-1225` | `_http_download` |

### 2.2 内部 helper 方法 — PASS

| 方法 | 行号 | 传递到 |
|------|------|--------|
| `_try_fetch_index_items` | `sec_downloader.py:1891-1895` | `_http_get_json` |
| `_try_fetch_index_header_documents` | `sec_downloader.py:1928-1931` | `_http_get_bytes` |
| `_try_fetch_primary_linked_html_files` | `sec_downloader.py:1971-1974` | `_http_get_bytes` |

### 2.3 HTTP 核心链路 — PASS

所有内部 HTTP 方法 (`_http_get_json`, `_http_get_bytes`, `_http_download`, `_http_head`) 均接受 `cancellation_checker` 并传递给 `_execute_sec_request`。`_execute_sec_request` 在每次重试循环开始时（line 1625）、rate limit 前后（lines 1628, 1630）、以及 rate limit 等待期间（`_rate_limit` → `_sleep_with_cancel_check`）检查取消。

### 2.4 collection 阶段取消 — PASS

`dayu/fins/pipelines/sec_download_workflow.py:353-398` — `run_download_stream_impl` 中 company resolve、submissions fetch、filter/extend/retry 三个阶段各自 try/except `SecDownloadCancelledError`，命中后 yield `_cancelled_pipeline_completed_event` 并 return，不进入 filing 循环。

`dayu/fins/pipelines/sec_pipeline.py` — `_filter_filings`、`_extend_with_browse_edgar_sc13`、`_retry_sc13_if_empty`、`_should_keep_sc13_direction` 均接受并传递 `cancel_checker`：
- `_filter_filings` 中 history submissions fetch 传递 `cancel_checker`（line 1164）
- `_extend_with_browse_edgar_sc13` 中 browse-edgar fetch 传递 `cancel_checker`（line 1267）
- `_retry_sc13_if_empty` 中递归调用传递 `cancel_checker`（line 1321）

### 2.5 SC13 filtering 取消 — PASS

`dayu/fins/pipelines/sec_sc13_filtering.py`：
- `filter_sc13_by_direction` 接受并传递 `cancel_checker`（line 377）
- `should_keep_sc13_direction` 接受 `cancel_checker`，传递给 `fetch_sc13_party_roles`（line 443）、`list_filing_files`（line 469）。`SecDownloadCancelledError` 显式 re-raise（line 470-471）。
- `extend_with_browse_edgar_sc13` 接受 `cancel_checker`，传递给 `fetch_browse_edgar_filenum`（line 553）、`should_keep_sc13_direction`（line 595）、`resolve_primary_document`（line 610）。`SecDownloadCancelledError` 在 browse-edgar fetch 和 resolve_primary_document 两处显式 re-raise（lines 556-557, 614-615）。
- `retry_sc13_if_empty` 接受并传递 `cancel_checker`（line 648）。

所有 Protocol 签名也已同步更新：
- `_Sc13WorkflowDownloader` Protocol（lines 109-148）
- `SecSc13WorkflowHost` Protocol（lines 186-237）

### 2.6 单 filing 处理取消 — PASS

`dayu/fins/pipelines/sec_download_filing_workflow.py:345-358` — `run_download_single_filing_stream` 中 rejected artifact persistence 的 `except SecDownloadCancelledError: return` 正确捕获取消并提前返回，外循环通过 `cancel_checker()` 观测到取消后 break。

`dayu/fins/pipelines/sec_pipeline.py:1705` — `_apply_6k_prescreening` 中 `classify_6k_remote_candidates` 传递 `cancel_checker`。

`dayu/fins/pipelines/sec_filing_collection.py:193-197` — `classify_6k_remote_candidates` 中 `fetch_file_bytes` 传递 `cancellation_checker`。

### 2.7 rejected artifact 持久化取消 — PASS

`dayu/fins/pipelines/sec_download_persistence.py:205-207` — `persist_rejected_filing_artifact` 接受 `cancellation_checker`。

新增 `_raise_if_cancelled` helper（line 306-322），在三个边界检查取消：
- 进入下载前（line 242）
- stream 路径下载完成后（line 255）
- legacy 路径下载完成后（line 267）

### 2.8 SecDownloadCancelledError 继承层次 — PASS

`dayu/fins/downloaders/sec_downloader.py:157` — `class SecDownloadCancelledError(Exception):` — 继承自 `Exception`，非 `RuntimeError`。因此代码库中所有 `except RuntimeError` 捕获块不会误吞取消异常，取消信号可安全穿透整个调用栈。

### Finding 2.1 — `_resolve_company_via_browse_edgar_ticker` docstring 遗漏异常声明

- **文件/行号**：`dayu/fins/downloaders/sec_downloader.py:1008-1009`
- **严重性**：LOW
- **证据**：docstring 写 `Raises: 无。`，但函数在 line 1020-1021 显式 re-raise `SecDownloadCancelledError`，且 `fetch_submissions`（line 1046-1051）可传播同一异常。
- **建议**：将 `Raises: 无。` 改为 `Raises: SecDownloadCancelledError: 取消检查点命中时抛出。`

### Finding 2.2 — 多个公开方法 docstring 遗漏 `SecDownloadCancelledError`

- **文件/行号**：
  - `sec_downloader.py:957` (`resolve_company` Raises 未列出 `SecDownloadCancelledError`)
  - `sec_downloader.py:1074` (`fetch_submissions` Raises 未列出 `SecDownloadCancelledError`)
  - `sec_downloader.py:1097` (`fetch_json` Raises 未列出 `SecDownloadCancelledError`)
  - `sec_downloader.py:1149` (`resolve_primary_document` Raises 未列出 `SecDownloadCancelledError`)
  - `sec_downloader.py:1225` (`fetch_file_bytes` Raises 未列出 `SecDownloadCancelledError`)
  - `sec_filing_collection.py:171` (`classify_6k_remote_candidates` Raises 只写了 `RuntimeError`)
- **严重性**：LOW
- **证据**：这些方法现在通过 `cancellation_checker` 参数可传播 `SecDownloadCancelledError`，但 Raises 段未声明。
- **建议**：补充 `SecDownloadCancelledError: 取消检查点命中时抛出。`

### Finding 2.3 — `run_download_single_filing_stream` 内层 catch + 外层 re-check 存在微效冗余

- **文件/行号**：`sec_download_filing_workflow.py:358-359`（内层 `except SecDownloadCancelledError: return`）与 `sec_download_workflow.py:493-494`（外层 `if cancel_checker and cancel_checker(): cancelled = True; break`）
- **严重性**：LOW
- **证据**：内层 catch 后 return 不抛出，外层循环在下一轮迭代时通过 `cancel_checker()` 再检测到取消并 break。功能正确，但多了一轮不必要的循环迭代和 `cancel_checker()` 调用。
- **影响**：仅当 `cancel_checker` 为一次性 token（用后即焚）时才会出错——但当前实现均为持久状态检查，无此风险。
- **建议**：无需修改。若未来重构可考虑内层 catch 后 raise（而不是 return），让外层 `except SecDownloadCancelledError: cancelled = True; break` 直接捕获，减少一次循环迭代。

---

## 审查维度 3：新 helper / Protocol 签名 / tests 合规性

### 3.1 类型标注 — PASS

所有新增参数均有完整类型标注 `Optional[Callable[[], bool]]` / `Callable[[], bool] | None`。

### 3.2 中文 docstring — PASS

所有新增函数（`_cancelled_pipeline_completed_event`、`_raise_if_cancelled`）和所有修改方法均已提供完整中文 docstring，包含 Args、Returns、Raises。

### 3.3 Protocol 签名同步 — PASS

以下 Protocol 签名已同步：
- `_DownloadWorkflowDownloader`（`sec_download_workflow.py:36-46`）
- `SecDownloadWorkflowHost`（`sec_download_workflow.py`）
- `_Sc13WorkflowDownloader`（`sec_sc13_filtering.py:109-148`）
- `SecSc13WorkflowHost`（`sec_sc13_filtering.py:186-237`）
- `SecDownloadFilingWorkflowHost`（`sec_download_filing_workflow.py:89-108`）

### 3.4 架构边界 — PASS

- `SecDownloadCancelledError` 定义在 `dayu.fins.downloaders.sec_downloader`（下载器层），被 pipeline 层 import 使用，符合自下而上的依赖方向。
- `_cancelled_pipeline_completed_event` 为模块级私有函数，访问 `host._resolve_form_windows` / `host._build_result`（均为 Protocol 已定义方法），不破坏封装。
- `_raise_if_cancelled` 为 `sec_download_persistence` 模块级私有函数。
- 无反向依赖、无跨层泄漏。

### 3.5 测试替身签名同步 — PASS

- `tests/fins/test_sec_downloader.py` — monkeypatch lambda 全部增加了 `cancellation_checker=None` 参数
- `tests/fins/test_sec_pipeline_download.py` — `StubDownloader` 和 `RebuildOnlyDownloader` 的方法签名同步真实 `SecDownloader` 边界
- `tests/fins/test_sec_pipeline_download_stream.py` — `StreamStubDownloader`、`StreamXbrlStubDownloader` 签名同步

### Finding 3.1 — 测试替身中有"吞掉 cancellation_checker"的用例注释不充分

- **文件/行号**：`tests/fins/test_sec_pipeline_download.py:170` (`StubDownloader.resolve_company` 中 `del ticker, cancellation_checker`)
- **严重性**：LOW
- **证据**：测试替身 `del cancellation_checker` 仅表明"我收到了参数但不需要使用"，但未通过 assertion 验证 cancellation_checker 确实被传入。部分测试可能未能检测到 cancellation_checker 参数在调用链中被意外丢失的回归。
- **建议**：在关键路径（如 `CancelAwareCollectionDownloader.fetch_json`）已有 cancellation_checker 断言；其他 stub 的 `del` 模式可接受，但建议在测试 docstring 中说明省略原因。

---

## 审查维度 4：测试是否真的覆盖根因

### 4.1 Memory 根因覆盖 — PASS

- `test_tool_awaiting_does_not_project_llm_facing_memory` — 直接断言 TOOL_AWAITING 不产生 LLM-facing memory text，覆盖了根因描述中的"awaiting lifecycle 泄漏进 LLM-facing memory"。
- `test_conversation_memory_consumer_uses_shared_projection_event_filter` — 断言 durable consumer event filter 不订阅 TOOL_AWAITING，覆盖了防止未来 regression 的防线。

### 4.2 SEC cancel 根因覆盖 — PASS

- `test_download_stream_cancel_stops_during_collection_before_filing_requests` — 通过 `CancelAwareCollectionDownloader` 在 `fetch_json`（history submissions 补拉）中命中取消，断言 status="cancelled" 且 `list_filing_files_called is False`。直接覆盖了根因描述中的"history submissions 补拉未传播 cancel_checker，导致继续进入 filing 文件请求"。

### 4.3 变更覆盖度 — PASS

变更文件中每个新增/修改的函数均有对应测试路径：

| 变更 | 测试覆盖 |
|------|----------|
| `project_conversation_memory_event` TOOL_AWAITING pass | `test_tool_awaiting_does_not_project_llm_facing_memory` |
| Durable consumer filter 排除 TOOL_AWAITING | `test_conversation_memory_consumer_uses_shared_projection_event_filter` |
| `run_download_stream_impl` collection 阶段取消 | `test_download_stream_cancel_stops_during_collection_before_filing_requests` |
| Downloader stub 签名同步 | 所有现有测试通过（122 passed） |

### 4.4 未覆盖的边界 — NOTE

以下边界未被本次测试直接覆盖，但属于合作式取消的固有约束：
- 单个 HTTP 请求已发出后的取消 — 无法伪装中断，由 `_execute_sec_request` 的 per-attempt `_raise_if_download_cancelled` 在请求返回后检查，不会继续发起后续请求。
- `_sleep_with_cancel_check` 中 sleep slice 内的取消延迟 — 最多 `_CANCEL_CHECK_SLEEP_SLICE_SECONDS` 延迟。

这些是合作式取消的已知约束，已在 fix artifact 中声明为剩余风险。

---

## 审查维度 5：README 更新

### 5.1 `dayu/host/README.md` — PASS

`dayu/host/README.md:659` — 新增段落准确描述 Memory projection 不消费 Host waiting lifecycle 事件的边界，与代码变更一致。无过度扩写。

### 5.2 `dayu/fins/README.md` — PASS

`dayu/fins/README.md:719` — 扩展 SEC 取消检查点描述，增加了"公司解析、submissions / history 拉取、Browse EDGAR 补选、index / headers / candidate 文件收集"，与代码变更一致。无过度扩写。

### 5.3 `tests/README.md` — PASS

`tests/README.md:185` — 新增 SEC pipeline 取消覆盖说明，精确对应新增测试。`tests/README.md:201` — 新增 memory projection 覆盖说明，与测试一致。无过度扩写。

---

## 附录 A：审查方法论

1. **逐文件 diff 阅读**：读取全部 16 个变更文件的完整 diff。
2. **调用链追踪**：从公开 API → 内部 helper → HTTP 核心 `_execute_sec_request` 逐层验证 `cancellation_checker` 传递。
3. **异常传播分析**：验证 `SecDownloadCancelledError(Exception)` 可穿透所有 `except RuntimeError` 屏障。
4. **LLM-facing 泄漏扫描**：grep 确认 `TOOL_AWAITING` 不在 memory projection / durable consumer event filter 中消费。
5. **测试根因对齐**：逐条对比测试断言与 root cause artifact 中列出的根因。

## 附录 B：未审查范围

- `docs/reviews/wu-cli-smoke-01-docling-async-research-codex.md` — 确认未被本次变更破坏（文件为独立 research artifact）。
- 真实 `asciinema` 交互 smoke — 不在本次审查范围；fix artifact 已声明为剩余风险。
- `dayu/host/engine_ingest.py` / `dayu/host/waiting.py` / `dayu/host/read_api.py` / `dayu/host/tool_trace.py` 中 TOOL_AWAITING 相关逻辑 — 确认不进入 memory projection 路径即可，不审查其内部正确性。
