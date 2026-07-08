# Code Review

## Scope

- Mode: current changes (workspace diff, unstaged changes)
- Branch: phase/host-issues-control
- Base: main (staged diff already committed to branch)
- Output file: docs/reviews/wu-cli-smoke-01-fins-cancel-memory-review-ds.md
- Included scope: 17 unstaged files — SEC downloader cancel/client refresh, ingestion_runtime producer cancel checks, CN/HK single-filing cancel checkpoints, CN/HK download workflow cancel handling, SEC single-filing/workflow/pipeline cancel checker wiring, Host durable memory filter extension, Host memory TOOL_AWAITING projection, test coverage, README sync
- Excluded scope: staged/committed changes on this branch (271 files, WU-CLI-SMOKE-01 aggregate); legacy job-store paths; real SEC/CN/HK network calls
- Parallel review coverage: 无。本 review 由 AgentDS 单人沿代码路径逐行走读，覆盖上述全部 17 个变更文件。

## Findings

### F-1-未修复-中-SEC downloader owned AsyncClient 的 loop identity 依赖 `id()` 可能碰撞

- **入口/函数**: `SecDownloader._refresh_owned_client_for_current_loop()` → `SecDownloader._execute_sec_request()`
- **文件(行号)**: `dayu/fins/downloaders/sec_downloader.py:1627-1654`
- **输入场景**: `SecDownloader.__init__(client=None)` 默认 owned client，跨多次 `asyncio.run()` 调用（例如旧 `SecPipeline.download()` facade 或 legacy job 路径）。第一轮 `asyncio.run()` 结束后其 event loop 对象被 GC 回收；第二轮 `asyncio.run()` 创建新的 event loop 时，CPython 分配器可能复用同一内存地址。
- **实际分支**: `_refresh_owned_client_for_current_loop()` 行 1644 用 `id(asyncio.get_running_loop())` 作为 loop identity。若新旧 loop 地址碰撞（`id()` 值相同），行 1648 `if self._client_loop_identity == current_loop_identity:` 为 `True`，直接 `return`，不刷新 client。
- **预期行为**: 凡当前 event loop 与上次注册的不同，即替换 owned client，无论 `id()` 是否碰撞。
- **实际行为**: 当 `id()` 碰撞时，旧 client（其内部 transport 绑定已关闭的旧 loop）被复用，导致 `Event loop is closed`。
- **直接证据**:
  - 行 1644: `current_loop_identity = id(asyncio.get_running_loop())` — `id()` 是 CPython 内存地址，语义上不是稳定 identity。
  - 行 1648: `if self._client_loop_identity == current_loop_identity: return` — 碰撞时直接复用旧 client。
  - 行 1650-1654: 只有 `!=` 时才会创建新 client 并尝试关闭旧 client。
- **影响**: 第二轮同类下载（特别是 `SecPipeline.download()` sync facade）可能偶发 `Event loop is closed`。触发概率低但真实存在，且在 CPython 大压力或特定分配模式下概率升高。
- **建议改法和验证点**: 至少增加一层防御：用 `(id(loop), loop.is_closed())` 或生成计数器（如 `object()` sentinel）作为 identity；或在创建新 client 前先尝试探测当前 client 是否可用。若认为 `id()` 碰撞在实际 workload 下不构成产品风险，应在代码注释中记录决策和取舍。
- **修复风险（低）**: 增加 `is_closed()` 检查或生成计数器不改变当前正向路径；需验证旧 client close 路径不因刷新频率增加而抛出非预期异常。
- **严重程度（中）**:

### F-2-未修复-低-SEC downloader 的 `_refresh_owned_client_for_current_loop` 在每重试循环内被调用但已在首次请求中完成刷新

- **入口/函数**: `SecDownloader._execute_sec_request()`
- **文件(行号)**: `dayu/fins/downloaders/sec_downloader.py:1557-1559`
- **输入场景**: 正常 HTTP 请求重试路径（非跨 `asyncio.run()` 边界）。
- **实际分支**: 重试循环内每次 iteration 都调用 `_refresh_owned_client_for_current_loop()`（行 1559）。但同一 `asyncio.run()` 内的 HTTP 请求不会切换 event loop，该调用在首次请求后恒为 no-op（行 1648 检查通过直接 return）。
- **预期行为**: 无功能错误，仅轻微性能噪音（一次 `asyncio.get_running_loop()` + `id()` + `isinstance` + 比较）。
- **实际行为**: 同上，无功能影响。
- **直接证据**: 行 1558-1559：重试循环 `while attempt_index < self._max_retries:` 内每次执行 `_refresh`。同 loop 内恒为 no-op。
- **影响**: 仅性能噪音。不造成错误行为。
- **建议改法和验证点**: 可选优化：在 `_execute_sec_request` 入口刷新一次，不在重试循环内重复调用。当前实现已正确，属低优先级清理。
- **修复风险（低）**:
- **严重程度（低）**:

### F-3-未修复-低-SEC download workflow 终态 status="cancelled" 依赖二次查询 cancel_checker 存在 TOCTOU

- **入口/函数**: `run_download_stream_impl()` (SEC)
- **文件(行号)**: `dayu/fins/pipelines/sec_download_workflow.py:537-538`
- **输入场景**: filing 循环因 `cancel_checker() == True` 在行 436 `break` 退出，随后在行 537-538 构造 `final_result` 时再次调用 `cancel_checker()`。
- **实际分支**: 行 436 的 `cancel_checker()` 返回 `True` → break。行 538：`status="cancelled" if cancel_checker is not None and cancel_checker() else "ok"`。若两次调用之间取消状态被清除（理论上不可能，因为 cancel 是 monotonic），status 会误为 `"ok"`。
- **预期行为**: 若取消状态是 monotonic（只从 False→True，不反向），二次查询无风险。但代码结构上把同一语义事实查询两次，增加理解成本。
- **实际行为**: 在 Fins observation 的 `_DirectCancellationChecker` 中，取消状态 monotonic 增长，不会回退，因此当前实现安全。
- **直接证据**: 行 436-441 用 `cancel_checker()` break；行 538 再次用 `cancel_checker()` 判断 status。
- **影响**: 当前无功能影响，但代码结构上同一事实两次查询，未来若取消检查器语义变化（例如 per-filing 重置），可能导致 status 矛盾。
- **建议改法和验证点**: 引入 `cancelled` 布尔标志在 break 处记录，行 538 只读标志，避免重复查询。
- **修复风险（低）**: 标志变量引用透明，不影响任何现有行为。
- **严重程度（低）**:

### F-4-未修复-低-测试 `test_owned_client_refreshes_across_asyncio_run_boundaries` 直接调用私有方法 `_refresh_owned_client_for_current_loop`

- **入口/函数**: `test_owned_client_refreshes_across_asyncio_run_boundaries`
- **文件(行号)**: `tests/fins/test_sec_downloader.py:926-939`
- **输入场景**: 测试直接用 `_run(downloader._refresh_owned_client_for_current_loop())` 调用私有方法。
- **实际分支**: 该测试绕过 public API 直接访问 `_refresh_owned_client_for_current_loop()` 和 `_client` / `_client_loop_identity` 内部字段。
- **预期行为**: 测试应通过 public API（如 `_execute_sec_request` 或 `download_files_stream`）间接触发 client refresh，而非直接调用私有方法。
- **实际行为**: 测试直接依赖私有方法签名和内部字段名，未来重构 `_refresh_owned_client_for_current_loop` 或改名 `_client` 时测试会误报失败，但测试本身证明的行为（跨 `asyncio.run()` 边界 client 刷新）是正确的回归保护。
- **直接证据**: 行 929: `_run(downloader._refresh_owned_client_for_current_loop())`；行 930: `first_client = downloader._client`；行 931: `first_loop_identity = downloader._client_loop_identity`。
- **影响**: 低。测试仍然有效，但增加了未来重构的维护成本。当前该测试保护的回归场景（`Event loop is closed`）价值高于私有方法访问的维护风险。
- **建议改法和验证点**: 可接受当前实现。如需降低维护耦合，可改为通过 `download_files_stream` 在跨 `asyncio.run()` 边界后验证不抛 `Event loop is closed`。
- **修复风险（低）**: 若改为 public API 测试需更复杂的 mock 链路。
- **严重程度（低）**:

### F-5-未修复-低-CN/HK download workflow 中 `_is_cancel_requested` 对 `CnDownloadCancelledError` 的语义处理与 `_raise_if_cancelled` 不一致

- **入口/函数**: `_is_cancel_requested()` vs `_raise_if_cancelled()` (CN/HK workflow)
- **文件(行号)**: `dayu/fins/pipelines/cn_download_workflow.py:402-454`
- **输入场景**: `cancel_checker()` 抛出 `CnDownloadCancelledError`（而非返回 `True`）。
- **实际分支**: `_is_cancel_requested()` 行 418-420：捕获 `CnDownloadCancelledError` 后返回 `True`。`_raise_if_cancelled()` 行 448-454：不捕获 `CnDownloadCancelledError`，而是依赖 `_is_cancel_requested()` 的返回值 —— 如果 `_is_cancel_requested` 返回 `True`，则 raise `CnDownloadCancelledError`。但在模块级 `_raise_if_cancelled`（行 425）内同样调用 `_is_cancel_requested`。因此如果一个 `cancel_checker()` 抛出 `CnDownloadCancelledError`，会被 `_is_cancel_requested` 捕获转成 `True`，然后 `_raise_if_cancelled` 再抛出新的 `CnDownloadCancelledError`。两个函数的异常转换方向一致，但 traceback 会改变。
- **预期行为**: 无功能错误。但 traceback 改变会妨碍调试。
- **实际行为**: 原始异常被吞并重新抛出，丢失原始调用栈。
- **直接证据**: 行 418-420: `except CnDownloadCancelledError: return True`；行 448-454: `if not _is_cancel_requested: return` → `raise CnDownloadCancelledError(...)`。
- **影响**: 调试困难。取消检查器自身抛出的 `CnDownloadCancelledError` 的原始 traceback 被吞。
- **建议改法和验证点**: `_is_cancel_requested` 中捕获 `CnDownloadCancelledError` 时，用 `raise` 重新抛出而不是返回 `True` 再构造新异常；或者文档化该行为并接受。
- **修复风险（低）**: 改动行为明确，不改变取消语义。
- **严重程度（低）**:

## Open Questions

1. **`id()` 碰撞的实际触发概率**: CPython 中 `asyncio.run()` 创建的 event loop 对象在函数返回后是否被立即回收、新 loop 是否可能复用同一地址，取决于 GC 行为和内存分配器。在典型 workload 下概率极低；但若上层 `SecPipeline.download()` 在短时间窗口内被多次调用（例如测试脚本、自动化 pipeline），碰撞概率可能升高。是否需要更稳健的 identity 方案取决于生产环境中 `SecPipeline.download()` sync facade 的实际调用频率。详见 F-1。

2. **Fins observation abandon 后旧后台线程对 storage 的影响**: `abandon_observation()` pop 了 process-local record 并设置取消状态，但如果旧 executor 线程在 abandon 之前已经提交但尚未开始执行（例如 executor 内部有排队），线程可能在 abandon 之后才开始执行 producer。当前测试 `test_abandoned_observation_does_not_pollute_repeat_download_observation` 用了 `_HoldingExecutor`（可控执行器），不覆盖真实 daemon thread executor 的竞态窗口。不过由于 producer 内部在 `_produce_direct_download` 行 2704 检查 `context.cancellation_checker()`，取消状态已设置的情况下 producer 会立即产出 cancelled result 并 return，不执行业务逻辑。因此即使线程在 abandon 后启动，也不会执行业务下载——只要 `cancellation_state.request_cancel()` 在 `abandon_observation` 中先于 producer 的 cancel check 执行。在真实 daemon thread 场景下，`abandon_observation` 持有 `_observation_lock` 并设置取消状态，然后 `activate_observation` 在同一锁内检查取消状态。这是一个正确的锁保护，不会遗漏。

3. **CN/HK Docling convert 的 subprocess 隔离是否应作为 blocker**: README 和代码注释明确 Docling convert 在 `asyncio.to_thread()` 内运行同步第三方调用，期间不能观察取消。这是一个文档化的 residual risk，不是实现遗漏。当前修复确保不进入 convert 后取消不产生 failed filing。若产品要求运行中强中断能力，需独立设计 process-backed / subprocess 方案和 timeout 策略。详见 `dayu/fins/README.md` 行 721-723。

## Tests Reviewed

| 测试 | 文件 | 覆盖目标 | 结论 |
|---|---|---|---|
| `test_owned_client_refreshes_across_asyncio_run_boundaries` | `tests/fins/test_sec_downloader.py:926` | SEC owned AsyncClient 跨 `asyncio.run()` 刷新 | 通过；覆盖了 `id()` 变化路径；直接调用私有方法（见 F-4） |
| `test_download_files_stream_cancel_stops_without_failed_event` | `tests/fins/test_sec_downloader.py:733` | SEC 文件循环取消检查点 | 通过；验证取消后停止后续下载、不产生 failed 事件 |
| `test_abandoned_observation_does_not_pollute_repeat_download_observation` | `tests/fins/test_fins_ingestion_runtime.py:2241` | Fins observation abandon 后第二轮隔离 | 通过；验证旧 observation LOST、新 observation 独立 SUCCEEDED |
| `test_cn_download_cancel_after_pdf_download_does_not_start_docling` | `tests/fins/test_cn_download_workflow.py:545` | CN/HK PDF 后取消不启动 Docling | 通过；验证 cancelled status、failed=0、Docling 未调用 |
| `test_cn_download_cancel_after_docling_convert_skips_source_commit` | `tests/fins/test_cn_download_workflow.py:595` | CN/HK Docling 后取消跳过 source commit | 通过；验证 cancelled status、failed=0、staging 保留、ingest_complete=False |
| `test_tool_awaiting_accepted_arguments_project_to_recent_evidence` | `tests/host/test_memory_projection.py:337` | Memory TOOL_AWAITING 投影 | 通过；验证 selected/evidence 角色、文本不泄漏 digest/event_id |
| 既有 SEC downloader / pipeline 测试 | `tests/fins/test_sec_downloader.py`, `tests/fins/test_sec_pipeline_download.py`, `tests/fins/test_sec_pipeline_download_stream.py` | 304、overwrite、zero-byte、failure 聚合不回归 | 通过（163 passed） |
| 既有 memory projection 测试 | `tests/host/test_memory_projection.py` | USER_INPUT_ACCEPTED / RUN_SUCCEEDED / TOOL_RESULT_ACCEPTED / CONTEXT_COMPACTED 投影 | 通过 |

**测试运行结果**: `163 passed, 3 warnings`（edgar deprecation warnings 仅）。Pyright: `0 errors, 0 warnings, 0 informations`。

### 未覆盖区域

- SEC `_refresh_owned_client_for_current_loop` 的 `id()` 碰撞场景未测试（难以在单元测试中可靠触发）。
- Fins observation abandon 与真实 daemon thread executor 的竞态窗口未测试（当前只用 `_HoldingExecutor` 控制执行顺序）。
- CN/HK download 中 `cancel_checker()` 自身抛出 `CnDownloadCancelledError` 的异常转换路径未测试。
- SEC pipeline `cancel_checker` 在 `_filter_filings` / `_extend_with_browse_edgar_sc13` / `_retry_sc13_if_empty` 内部的取消检查点尚未增加（这些函数在 `run_download_stream_impl` 的 filing 循环之前执行，不支持中间取消；如果需要，应作为后续增强）。

## Verdict

**PASS** — 无 blocker。

### 评审维度总结

1. **SEC owned httpx.AsyncClient 按 event loop 刷新**: 总体正确。`_refresh_owned_client_for_current_loop()` 在每次 `_execute_sec_request` 入口刷新 owned client，覆盖所有 HTTP 路径（GET/HEAD/JSON/bytes/条件下载）。关闭旧 client 用 `contextlib.suppress(Exception)` 安全收口。`id()` 作为 loop identity 存在理论碰撞窗口（F-1），但在典型 workload 下触发概率极低。测试覆盖了跨 `asyncio.run()` 刷新行为，但依赖私有方法。

2. **Fins observed operation cancel/abandon 后第二轮隔离**: 正确。`abandon_observation()` pop 旧 record 并设置取消状态；`cancel_observation()` 在锁内将未提交的 prepared observation 直接置为 `CANCELLED`；新 observation 使用独立 `_FinsObservedOperationRecord`（独立 queue、独立 cancellation_state）。producer 在执行业务逻辑前检查 `context.cancellation_checker()`，已取消 observation 立即产出 cancelled result 不启动 adapter。测试覆盖了第二轮独立成功的路径。

3. **SEC/CN/HK 单 filing 取消检查点**: 足够。SEC 在 `list_filing_files`（行 1214, 1220, 1225, 1242, 1259）和 `download_files_stream`（行 1314, 1338, 1379, 1387, 1405, 1413, 1423）设置了充足检查点。CN/HK 在 `run_cn_download_single_filing_stream` 的每个阶段边界（reset、staging write、PDF download、PDF read、blob write、Docling convert 前后、source commit 前）设置了检查点。取消命中后 `CnDownloadCancelledError` 被正确捕获，不包装成 failed filing；已完成的原子落盘保持一致。SEC 的 `_filter_filings` 和 SC13 补齐阶段是 filing 循环前的批量网络操作，暂未增加取消检查点——这些阶段在典型下载中耗时可控。

4. **Docling convert 的 cancel 边界**: 实现与 README 一致。`asyncio.to_thread()` 调用同步第三方转换函数，线程运行期间不能观察取消。修复确保：进入 convert 前有检查点（`cn_download_filing_workflow.py:436-438`），convert 返回后有检查点（行 480、488），convert 异常被正确分类（`CnDownloadCancelledError` 重新抛出，其他异常包装为 failed filing）。取消后不启动后续耗时步骤（blob write、source commit）。README 明确记录这是 cooperative checkpoint 而非强制中断，需要强中断时应使用 process-backed / subprocess 隔离。

5. **Memory 投影 TOOL_AWAITING LLM-facing 自解释**: 正确。`_selected_awaiting_text()` 产出的文本只包含工具名（`start_fins_download`）和已确认参数（`{"ticker":"CRCL"}`），不含 wait id、digest、event_id、调度状态。文本明确指示"不要把等待状态、取消状态或调度状态当成业务事实"。`_accepted_arguments_mapping()` 做了三层校验：类型检查、`source_digest == normalized_digest` 一致性、内容 digest 重算校验。`_EVENT_TYPE_FILTER` 已包含 `TOOL_AWAITING`。测试覆盖了 selected recent window 和 recent evidence 双通道投影，以及 digest/event_id 不泄漏。

6. **类型、docstring、AGENTS.md 约束、README 触发、测试覆盖**: 通过。新增函数均有完整中文 docstring。类型标注精确（`Callable[[], bool] | None` 用于 cancel_checker）。pyright 零错误。`dayu/fins/README.md` 和 `dayu/host/README.md` 按触发规则同步。测试覆盖了 6 个新增行为，外加既有回归保护。

## Residual Risk

- **F-1 `id()` 碰撞**: 低概率但真实存在的理论风险。建议记录为 known risk，或在后续版本中增加 `loop.is_closed()` 辅助判断。
- **SEC `_filter_filings` / SC13 补齐阶段无取消检查**: 这些阶段在 filing 循环之前执行，涉及批量 HTTP 请求。若用户在此阶段取消，需等待自然完成。当前 `cancel_checker` 只在 filing 循环边界（`sec_download_workflow.py:436`）检查，不在 `_filter_filings`（行 391-400）或 `_extend_with_browse_edgar_sc13`（行 401-411）内部传播。
- **Docling convert 强中断**: 文档化的 residual risk，需独立设计 process-backed / subprocess 方案。不是本次修复的范围。
- **Fins observation 真实 daemon thread 竞态**: 当前 `_observation_lock` 保护了 `cancellation_state` 和 `submitted` 标志的读写，使得 abandon → activate 的竞态窗口被正确关闭。但 `executor.submit()` 之后线程执行时间和 abandon 之间的竞态无法用锁消除——这是 cooperative cancel 的固有限制，已文档化。
