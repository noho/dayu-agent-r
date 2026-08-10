# WU-CLI-DOWNLOAD-01 Aggregate Deep Review — AgentMiMo

- 基线：`bad90963abad48d29b5571d44a1cd9a80e0e2d77`（main HEAD）
- 审查范围：`codex/download-oracle` branch, 115 files, +27100/-3509
- 审查维度：DL-F01..DL-F11 adversarial closure、分层/反向依赖、semantic ownership drift、取消/terminal race、storage atomicity/concurrency、secret/contact 泄露、过度设计、observation infra expansion、测试是否在 owner contract 上
- 结论：**PASS**

---

## 0. 方法论

独立从 baseline diff 和 production 代码出发，逐项检查 DL-F01..DL-F11 的 accepted behavior 是否从 owner boundary 闭合。不依赖已有 reviewer 结论，直接查代码证据。对每个 finding 给出：直接代码位置、root cause 是否被正确修复、是否有 regression 或 scope drift。

---

## 1. DL-F01：静态输入验证发生得过晚

**Accepted behavior**：CLI 能从 argv 独立判定的 ticker/forms/date/limit/range 错误必须在 Service/Fins storage 装配前失败，exit 2，workspace 零副作用。

**直接证据**：

- `dayu/cli/commands/fins.py:224`：`_prevalidate_download_request(args)` 在 `_resolve_workspace_root`（:225）和 `FINS_DIRECT_SERVICE_FACTORY`（:226）之前调用。
- `fins.py:601`：`build_direct_download_request(...)` → `download_contract.py:596` `build_fins_download_request(...)`。
- `download_contract.py:622`：`_parse_single_ticker` 校验空/过长/CSV/无法识别。
- `download_contract.py:623`：`_parse_form_types` 校验数量/长度/空项/业务取值。
- `download_contract.py:624-625`：`_parse_date_bound` 校验格式/有效日期。
- `download_contract.py:545`：`FinsDownloadDateRange.__post_init__` 校验 `start > end`。
- `fins.py:195`：`FinsDownloadUsageError` 被捕获并返回 `EXIT_USAGE_ERROR`（exit 2）。

**不变量验证**：factory 未调用、workspace 未解析、storage 未构造。测试（`test_fins_commands.py`）对 factory 未调用、workspace 不存在和 exit 2 同时断言。

**判定**：**PASS**。root cause（validation 发生在 runtime 构造之后）已从 owner boundary 修复。状态顺序固定为 `RAW_ARGV → VALIDATED_REQUEST → WORKSPACE → SERVICE → STREAM`。

---

## 2. DL-F02：单 ticker 参数静默截断 CSV

**Accepted behavior**：`AAPL,MSFT` 必须 exit 2；重复 `--ticker` 保持 last-wins。

**直接证据**：

- `download_contract.py:659`：`if "," in ticker or "，" in ticker: raise FinsDownloadUsageError(...)`。
- `fins.py:224`：`_prevalidate_download_request` 只读 `args.ticker` 最终值（argparse last-wins）。
- `fins.py:599`：`args.ticker is None` 检查确保非空。

**边界确认**：`_parse_ticker_csv`（fins.py:1044）仍用于 upload/process 等非 download 命令，其 CSV 语义不改。download 专用路径完全绕过它。

**判定**：**PASS**。download 命令的 ticker 输入 contract 与 upload/process 独立，CSV 被显式拒绝。

---

## 3. DL-F03：显式日期窗口被 SC13 补拉扩大

**Accepted behavior**：用户显式 start/end 是硬边界；SC13 retry/browse 只能扩展默认 lookback。

**直接证据**：

- `download_contract.py:523-526`：`FinsDownloadDateRange` 携带 `start_is_explicit`/`end_is_explicit` typed 事实。
- `ingestion_runtime.py` diff：`FinsSourceDownloadAdapterRequest` 新增 `date_range: FinsDownloadDateRange`，从 request 同源传入。
- `sec_pipeline.py:660`：`download_stream` 签名新增 `start_is_explicit: bool`，透传到 `run_download_stream_impl`。
- `sec_download_workflow.py:309`：`run_download_stream_impl` 签名新增 `start_is_explicit`。
- `sec_pipeline.py:1315-1355`：`_retry_sc13_if_empty` 使用 `start_is_explicit` 决定是否扩展。
- `sec_download_workflow.py:515-535`：`_filter_filings_to_windows` 在 SC13 retry 前后各执行一次，使用 `form_windows`（由 typed request 的 inclusive bounds 派生）作为硬边界。

**关键逻辑**：`_filter_filings_to_windows`（sec_download_workflow.py:974-1004）对每个 filing 检查 `lower_bound <= filing_date <= end_date`。`form_windows` 来自 `start_bound` 的 ISO 文本展开，不因 SC13 retry 改变。二次 filter 确保即使 retry 返回窗口外 candidate 也会被排除。

**判定**：**PASS**。显式边界事实从 typed request 同源传入，不从日期值反推。

---

## 4. DL-F04：普通 download 隐式删除旧 filing

**Accepted behavior**：普通 download 不删除本轮未选择的既有 source。

**直接证据**：

- `sec_download_workflow.py` diff：`_CleanupStaleFilingDirs` Protocol 被完全删除。
- `sec_download_workflow.py:316-325`：`run_download_stream_impl` 签名中 `cleanup_stale_filing_dirs` 参数被删除。
- `sec_pipeline.py:707-718`：`_run_old_download_stream` 不再传 `cleanup_stale_filing_dirs`。
- `rg` 确认 `cleanup_stale_filing_dirs` 在 production 代码中无残留调用。

**判定**：**PASS**。root cause（workflow 越权拥有 prune）已从 owner boundary 删除。不新增 prune API。

---

## 5. DL-F05：`--rebuild` 被错误映射到 processed 治理

**Accepted behavior**：`download --rebuild` 仅重建本地 meta/manifest；不修改 processed/reprocess 状态。

**直接证据**：

- `ingestion_runtime.py` diff：`FinsDownloadRequest` 从 `ingestion_runtime.py` 删除，迁移到 `download_contract.py:575-593`。新 request 使用 `rebuild_local_artifacts: bool`，不含 `rebuild_processed`。
- `ingestion_runtime.py` diff：`FinsSourceDownloadAdapterRequest` 使用 `rebuild_local_artifacts`，不含 `rebuild_processed`。
- `sec_rebuild_workflow.py` diff：`SecRebuildWorkflowHost._processed_repository` property 被删除。`rebuild_download_artifacts` 和 `rebuild_single_local_filing` 签名中 `processed_repository` 参数被删除。`mark_processed_reprocess_required` 调用被删除。
- `cn_download_rebuild.py` diff：`host.processed_repository.get_processed_meta` 和 `mark_processed_reprocess_required` 调用被删除。
- `sec_pipeline.py:1856`：adapter 传 `rebuild=request.rebuild_local_artifacts`。
- `ingestion_runtime.py` diff：`mark_downloaded_processed_rebuild_required` 从 `sec_pipeline.py` 导入中删除。

**判定**：**PASS**。`rebuild_processed` 语义从 download request、adapter request、SEC/CN rebuild workflow 完整删除。rebuild 只改 local meta/manifest。

---

## 6. DL-F06：CN/HK missing period 被计为 discovered/skipped

**Accepted behavior**：请求 period 无 provider candidate 时不计入 discovered/skipped。

**直接证据**：

- `cn_download_workflow.py:194`：`FinsDownloadResultSummary` 构造时 `missing_periods` 独立传入。
- `cn_download_workflow.py:237`：`missing_periods = _resolve_missing_periods(periods.target_periods, selected)`。
- `cn_download_workflow.py:564`：`_resolve_missing_periods` 计算请求 period 中无 candidate 的差集。
- `download_contract.py:294`：`missing_periods` 默认 `()`，不计入 `discovered_count`。
- `download_contract.py:330-331`：`discovered_count == sum(counts[1:])` 只计 downloaded+skipped+rejected+failed。

**关键不变量**：`FinsDownloadResultSummary.__post_init__` 强制 `discovered = downloaded + skipped + rejected + failed`，missing_periods 独立于 discovered。测试验证 missing period 不出现在 discovered 计数中。

**判定**：**PASS**。missing period 不再构造 synthetic filing result/progress event。

---

## 7. DL-F07：动态失败、SEC User-Agent 与日志隐私

**Accepted behavior**：未配置 UA 时首次 HTTP 前失败；日志不回显联系值；同一 warning 去重。

**直接证据**：

- `sec_downloader.py:2294-2320`：`_resolve_user_agent` 返回 `tuple[SecUserAgentState, str | None]`。未配置时返回 `UNCONFIGURED, None` 并打一次 warning。
- `sec_downloader.py:2335-2336`：`_build_headers` 检查 `UNCONFIGURED` 状态并抛 `SecUserAgentConfigurationError`，不构造 fallback header。
- `sec_downloader.py:1104`：构造时日志只写 `configured=true/false`，不写 UA 原文。
- `download_contract.py:137-158`：`SecUserAgentConfigurationError` 继承 `FinsDownloadProviderError`，`transport_category=UNCONFIGURED`，`safe_message` 不含联系值。
- `sec_downloader.py:1098`：UA resolution 在 downloader composition 中只执行一次（构造时），`configure` 不重新 warning。

**Warning 去重确认**：`_resolve_user_agent` 只在 `SecDownloader.__init__` 中调用一次（:1098）。`Log.warning` 只在 UNCONFIGURED 分支触发（:2316-2318）。多次构造同一 workspace 的 downloader 会重复 warning，但这是 per-downloader-instance 行为，同一 command 只构造一次。

**判定**：**PASS**。UA 配置检查在首次 HTTP 前，不发送匿名 fallback。

---

## 8. DL-F08：同 ticker 并发被仓储 batch fail-fast 当作业务错误

**Accepted behavior**：同 ticker 允许并发；storage 只短暂串行 publication，不能 fail-fast。

**直接证据**：

- `_fs_storage_infra.py:1503-1512`：`_acquire_ticker_lock` 使用 `blocking=True`（旧代码 `blocking=False` + `RuntimeError`）。
- `_fs_storage_infra.py:449-450`：`threading.Condition()` + `_reserved_batch_tickers: set[str]`。
- `_fs_storage_infra.py:1256-1263`：`_reserve_batch_ticker` 使用 `while` + `Condition.wait()` 阻塞等待。
- `_fs_storage_infra.py:1300-1329`：`_close_active_batch` 的 `finally` 块释放 file lock、清除 reservation 并 `notify_all`。
- `_fs_storage_infra.py:1877`：recovery 的 `_try_acquire_recovery_ticker_lock` 保持 `blocking=False`，正确区分正常 writer 与孤儿恢复。

**并发状态机验证**：`LOCAL_RESERVATION → BLOCKING_WRITER → STAGING → PUBLICATION → COMMIT → RELEASE/NOTIFY`。所有 terminal 路径（commit/rollback/exception）统一通过 `_close_active_batch` 的 `finally` 释放。

**SEC throttle**：`sec_downloader.py:2344-2370`：`_reserve_global_request_slot` 使用 workspace-shared state file + file lock。CN/HK 不增加 SEC 式限流。

**判定**：**PASS**。fail-fast 已改为 blocking wait。SEC throttle 保持在 SEC downloader owner。

---

## 9. DL-F09：Ctrl+C 没有等待 canonical cancellation

**Accepted behavior**：一次 Ctrl+C → CLI 等待 Fins cancelled terminal → exit 130。Docling 在可 terminate/join/drain 的独立进程边界。

**直接证据**：

CLI 取消流程（`fins.py:755-809`）：
- `sigint_monitor.install()` 安装 SIGINT 观察。
- `event_task = asyncio.create_task(_consume_fins_direct_events(events))` 创建 consumer。
- 首次 SIGINT：`cancellation_token.request_cancel("keyboard_interrupt")` + `render_fins_direct_cancel_requested()`。**不调用** `event_task.cancel()`。
- 继续 `await event_task`，等待 Fins owner 产出 terminal。

Runtime 取消仲裁（`ingestion_runtime.py` diff）：
- `_DirectStreamCancellationState` 新增 `_terminal_status: FinsResultStatus | None`。
- `request_cancel()` 返回 `bool`：只有在 terminal 未提交前首次生效才返回 `True`。
- producer 在 terminal gate 检查取消状态：已取消则写 CANCELLED，已 success 则不因晚到 SIGINT 改写。

Docling 进程边界（`cn_docling_process.py`）：
- `InterruptibleProcessHandle.start()` 启动独立子进程。
- `_wait_for_conversion` 以 50ms 轮询 cancellation checker。
- 取消时 `terminate(grace=2.0s)` → `kill(grace=1.0s)` → `close()` 有界升级。
- `finally` 块清理 temp tree，handle close 完成后才发 terminal。
- `CnDownloadCancelledError` 传播到 workflow 层，触发 canonical cancelled terminal。

**Race 分析**：CLI `event_task.cancel()` 只在 `_cancel_and_drain_fins_event_task`（:812-840）的 `BaseException` handler 中调用，用于 consumer task 清理。这是 owner-initiated cancel 用于收回执行资源，不创造业务 RESULT。CLI 无权调用 runtime cancel。

**判定**：**PASS**。CLI 不再抢先设置 terminal 或 cancel event_task。runtime 是唯一 terminal owner。Docling 在可 terminate/join/drain 的独立进程边界。

---

## 10. DL-F10：source integrity mismatch 无法自动修复

**Accepted behavior**：physical/meta mismatch 时自动重新获取并原子修复；失败保留旧目标。

**直接证据**：

- `source_integrity.py` 全模块：`SourceIntegrityStatus`（MISSING/COMPLETE/REPAIR_REQUIRED）、`SourceIntegrityReason`、`SourceIntegrityClassification`。
- `repository_protocols.py:575-642`：Protocol 定义 `classify_source_integrity` 和 `list_source_integrity`。
- `sec_download_workflow.py:556-595`：`classify_source_integrity_preflight` whole-ticker preflight → stable partition repair-first。
- `sec_download_workflow.py` diff：repair target 排在所有其它 accepted filing 前执行。
- `_fs_source_document_core.py:508-555`：`list_source_integrity` 在单次 publication guard 内枚举全部 document ID。

**Phase A/B identity-first**：SEC/CN filing workflow 在 begin_batch 后首个 target operation 调用 staged classification。Phase A（short read）→ Phase B（writer revalidation）→ identity-first decision。最多 3 轮 revision churn 后抛 `SourceIntegrityRevisionConflictError`。

**判定**：**PASS**。storage 提供 typed integrity classification；source workflow 根据 classification 强制 repair。

---

## 11. DL-F11：screen/final summary 不足以让用户验收实际结果

**Accepted behavior**：final summary 展示 resolved source、canonical ticker、effective filters、bounded document rows、artifact locator、rejection reason、missing details、omitted count。

**直接证据**：

- `direct_events.py:345-436`：`FinsDownloadPublicSummary` 包含 source、canonical_ticker、effective_filters、counts、document_rows、missing_periods、omitted_count、terminal_disposition。
- `direct_events.py:256-341`：`FinsDownloadPublicDocument` 包含 document_id、form_or_period、filing_date、report_date、disposition、reason_category、reason_message、artifact_locator。
- `direct_events.py:564-639`：`FinsResultSummary` 携带 `download: FinsDownloadPublicSummary | None` 和 `failure: FinsPublicFailure | None`。
- `cn_download_filing_workflow.py:329-337`：CN Docling conversion 后发 `CONVERSION_COMPLETED` event。
- `output.py:410-464`：`_print_terminal_business_summary` → `_print_download_summary` 投影 source、ticker、forms、start/end、overwrite、rebuild、counts、document rows、missing periods。
- `output.py:466-488`：`_download_document_line` 投影 document_id、form_or_period、filing_date、report_date、disposition、reason_category、reason_message、artifact_locator。

**Count 守恒**：`FinsDownloadPublicSummary.__post_init__`（:387-429）强制 `discovered = downloaded + skipped + rejected + failed`，`document_rows + omitted_count = discovered_count`。

**判定**：**PASS**。CLI renderer 从同一 typed public object 投影，不扫描私有 storage。

---

## 12. 分层与反向依赖

| 检查项 | 判定 |
|---|---|
| `download_contract.py` 不 import `ingestion_runtime`/`host`/`service`/`ui` | PASS |
| `source_integrity.py` 不 import 上层模块 | PASS |
| `cn_docling_process.py` 只依赖 `runtime.interruptible_process` 和 `fins.pipelines.cn_download_models` | PASS |
| `fins_direct.py`（Service）不 import CLI 模块 | PASS |
| `fins.py`（CLI）import Service 但不 import runtime/ingestion 直接 | PASS |
| `ingestion_runtime.py` 不 import CLI/Service | PASS |
| `dayu.runtime.interruptible_process` 未被修改 | PASS |

---

## 13. Semantic Ownership Drift

| 检查项 | 判定 |
|---|---|
| `FinsDownloadRequest` 从 `ingestion_runtime` 迁移到 `download_contract`，无 compat re-export | PASS |
| `FinsDownloadResultSummary` 同上 | PASS |
| `rebuild_processed` 从 download request/adapter/rebuild workflow 完整删除 | PASS |
| CN fiscal-period alias 解析迁移到 `domain/filing_semantics.py` | PASS |
| `_parse_ticker_csv` 保留用于 upload/process，download 使用 `_parse_single_ticker` | PASS |
| SEC `_UNCONFIGURED_USER_AGENT` 常量被删除，替换为 typed `SecUserAgentState.UNCONFIGURED` | PASS |

---

## 14. Storage Atomicity/Concurrency

| 检查项 | 判定 |
|---|---|
| 同 ticker 阻塞等待（blocking=True + Condition） | PASS |
| recovery try-lock 保持 non-blocking | PASS |
| 所有 terminal 路径统一 release/notify | PASS |
| begin_batch 注册与 reservation 清理无双重释放 | PASS |
| publication guard 独立于 writer lock | PASS |
| integrity classify 在单次 publication guard 内完成 | PASS |

---

## 15. Secret/Contact 泄露

| 检查项 | 判定 |
|---|---|
| SEC UA 日志只写 `configured=true/false` | PASS |
| `FinsPublicFailure.safe_message` 不含 URL/contact/raw payload | PASS |
| `_validate_safe_text` 检查 URL 模式、绝对路径、job_id 等 | PASS |
| `_validate_public_text`（download_contract.py:801-837）检查 `://`、绝对路径、raw payload | PASS |
| Docling cleanup warning 只记 error_type，不含 temp path/PDF content | PASS |

---

## 16. 过度设计与 Observation Infra Expansion

| 检查项 | 判定 |
|---|---|
| 不新增 `--source` option | PASS |
| 不新增 multi-ticker | PASS |
| 不新增显式 prune | PASS |
| 不新增 Host Run/EventLog/SQLite for download | PASS |
| 不新增 sleep/测试后门/private timing hook | PASS |
| Docling process 使用现有 `InterruptibleProcessHandle`，不新增 `spawn()` wrapper | PASS |
| `_CnDoclingProcessTarget` 是可 pickle 的最小目标，不引入新框架 | PASS |

---

## 17. 测试 Owner Contract 验证

| 检查项 | 判定 |
|---|---|
| `test_fins_commands.py` 对 factory 未调用、workspace 不存在和 exit 2 同时断言 | PASS |
| `test_fins_storage_atomicity.py` 使用 Event/Barrier 替代 sleep | PASS |
| `test_cn_docling_process.py` 使用 deterministic fake runner | PASS |
| `test_sec_pipeline_download.py` 验证 SC13 window enforcement | PASS |
| `test_cn_download_workflow.py` 验证 missing period 不计入 discovered | PASS |
| 新测试不固化偶然行为（如旧 import path、旧 field name） | PASS |

---

## 18. Findings（未闭合问题）

无 correctness/stability findings。

### 18.1 低严重性观察（不阻塞 PASS）

**OBS-1**：`sec_downloader.py:2316-2318` 的 `Log.warning` 在每次 `SecDownloader` 构造时触发。如果同一 command 因 retry 或 factory 重建 downloader，warning 会重复。当前架构中同一 command 只构造一次 downloader，因此实际不触发。若未来架构变化需注意。

**OBS-2**：`_fs_storage_infra.py:1512` 的 `blocking=True` 无显式超时。底层 OS file lock 永久 I/O 卡死仍是 residual，符合 DL-F08 明确接受的"底层文件系统/OS lock 永久 I/O 卡死仍是 residual"。

**OBS-3**：`cn_docling_process.py:121` 的 `tempfile.mkdtemp` 在 SIGKILL parent 时会残留 system-temp 目录。plan 明确接受此为"明确 residual，不在 workspace 增加 stale scavenger"。

---

## 19. 总结

DL-F01..DL-F11 全部从 owner boundary 闭合。核心设计决策落地：

| Finding | Root Cause 修复位置 | 判定 |
|---|---|---|
| DL-F01 | CLI `_prevalidate_download_request` 在 workspace/service 前 | PASS |
| DL-F02 | `download_contract._parse_single_ticker` 拒绝 CSV | PASS |
| DL-F03 | `start_is_explicit` typed fact + `_filter_filings_to_windows` 双重 guard | PASS |
| DL-F04 | `_CleanupStaleFilingDirs` 从 SEC workflow 完整删除 | PASS |
| DL-F05 | `rebuild_processed` 从 request/adapter/rebuild workflow 删除 | PASS |
| DL-F06 | `missing_periods` 独立于 `discovered_count` | PASS |
| DL-F07 | `SecUserAgentState.UNCONFIGURED` + `_build_headers` fail-closed | PASS |
| DL-F08 | `blocking=True` + `Condition` reservation + unified release/notify | PASS |
| DL-F09 | CLI 不抢先 terminal；Docling 在 `InterruptibleProcessHandle` 边界 | PASS |
| DL-F10 | `SourceIntegrityClassification` + preflight + Phase A/B identity-first | PASS |
| DL-F11 | `FinsDownloadPublicSummary` + `FinsDownloadPublicDocument` typed projection | PASS |

分层无反向依赖。semantic ownership drift 已清理。storage concurrency 正确。无 secret/contact 泄露。无过度设计。测试在 owner contract 上。
