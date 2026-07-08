# Code Review — WU-CLI-SMOKE-01 Fins Cancel / Memory

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-fins-cancel-memory-review-mimo.md`
- Included scope: `dayu/fins/downloaders/sec_downloader.py`, `dayu/fins/ingestion_runtime.py`, `dayu/fins/pipelines/cn_download_filing_workflow.py`, `dayu/fins/pipelines/cn_download_workflow.py`, `dayu/fins/pipelines/sec_download_filing_workflow.py`, `dayu/fins/pipelines/sec_download_workflow.py`, `dayu/fins/pipelines/sec_pipeline.py`, `dayu/host/durable/memory.py`, `dayu/host/memory.py`, `dayu/fins/README.md`, `dayu/host/README.md`, and corresponding tests
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

### 01-未修复-低-SEC `_refresh_owned_client_for_current_loop` 测试直接访问私有属性

- **入口/函数**: `tests/fins/test_sec_downloader.py::test_owned_client_refreshes_across_asyncio_run_boundaries`
- **文件(行号)**: `tests/fins/test_sec_downloader.py` (约 923-935 行)
- **输入场景**: 测试 SEC downloader owned HTTP client 跨 `asyncio.run()` 边界的刷新行为
- **实际分支**: 测试直接访问 `downloader._refresh_owned_client_for_current_loop()`、`downloader._client` 和 `downloader._client_loop_identity`
- **预期行为**: 测试应通过公共行为验证 client 刷新，而非直接访问私有方法和属性
- **实际行为**: 测试依赖私有 API，若内部重构（如改用不同标识机制）会导致测试假阳性失败
- **直接证据**: `downloader._refresh_owned_client_for_current_loop()`、`downloader._client_loop_identity` 均为私有成员
- **影响**: 测试与实现过度耦合，重构时需要同步修改测试；不影响正确性
- **建议改法和验证点**: 可通过在两个不同 `asyncio.run()` 边界中分别执行下载操作并验证第二次不触发 `Event loop is closed` 来间接测试；当前形式可接受但标记为 fragile test
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 02-未修复-低-SEC `_execute_sec_request` 每次重试都调用 `_refresh_owned_client_for_current_loop`

- **入口/函数**: `SecDownloader._execute_sec_request`
- **文件(行号)**: `dayu/fins/downloaders/sec_downloader.py` (约 1557-1559 行)
- **输入场景**: SEC HTTP 请求重试循环
- **实际分支**: `while attempt_index < self._max_retries` 循环内每次迭代都调用 `_refresh_owned_client_for_current_loop()`
- **预期行为**: 同一 `asyncio.run()` 内的重试不需要刷新 client，因为 event loop 不变
- **实际行为**: 每次重试都执行 `id(asyncio.get_running_loop())` 和 `self._client_loop_identity` 比较，identity 相同时直接 return
- **直接证据**: `_refresh_owned_client_for_current_loop()` 在 `_execute_sec_request` 的 while 循环体内（行 1559）
- **影响**: 轻微性能开销（两次 `id()` 调用和一个 `None` 比较），不影响正确性；在高频重试场景下开销可忽略
- **建议改法和验证点**: 可将 `_refresh_owned_client_for_current_loop()` 移到 while 循环外（首次调用前），因为同一 `asyncio.run()` 内 event loop 不变。但当前实现的 identity check 已经短路，实际开销极小
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

### 03-未修复-低-CN/HK `company_info` 在取消路径下可能为空字典

- **入口/函数**: `run_cn_download_stream_impl`
- **文件(行号)**: `dayu/fins/pipelines/cn_download_workflow.py` (约 203 行)
- **输入场景**: CN/HK 下载在公司信息解析前被取消
- **实际分支**: `company_info: JsonObject = {}` 初始化后，若在 `discovery.resolve_company(query)` 或 `upsert_company_meta_for_cn_download(...)` 前触发取消
- **预期行为**: 取消 summary 应包含已解析的公司信息或明确为空
- **实际行为**: `company_info` 为空字典 `{}`，取消 summary 的 `company_info` 字段为空对象
- **直接证据**: 行 203 `company_info: JsonObject = {}`，行 364 `company_info=company_info`
- **影响**: 取消 summary 的 `company_info` 为空对象，CLI 展示时 company name 缺失；不影响数据一致性，因为取消本身就是非正常终止
- **建议改法和验证点**: 当前行为可接受——取消发生在公司解析前时，确实没有公司信息可展示。若需改进，可在 CLI 层对空 `company_info` 做 fallback 展示
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## 重点 Review 维度结论

### 1. SEC owned httpx.AsyncClient 按 event loop 刷新

**PASS**。`_refresh_owned_client_for_current_loop` 使用 `id(asyncio.get_running_loop())` 作为 event loop identity，正确区分不同 `asyncio.run()` 边界。`contextlib.suppress(Exception)` 处理旧 client 关闭失败是合理的 best-effort cleanup。`_owns_client` 和 `isinstance(self._client, httpx.AsyncClient)` 的 guard 避免了非 owned client 场景的误刷新。`close()` 方法正确地将 `_client_loop_identity` 置为 `None`。测试覆盖了跨 `asyncio.run()` 边界的刷新场景。无资源泄漏或并发竞态。

### 2. Fins observed operation cancel/abandon 后第二轮 observation 隔离

**PASS**。`test_abandoned_observation_does_not_pollute_repeat_download_observation` 验证了完整隔离链路：第一轮 observation activate → cancel → abandon → 第二轮 prepare → activate → executor.run_all() → 第二轮 succeeded。adapter 只收到一个 request（来自第二轮），确认旧 observation 不污染新 run。`cancel_observation` 设置 cancellation state，`abandon_observation` pop record 并 best-effort request_cancel，不 join 已提交线程；但第二轮 observation 的 `prepare_observed_download` 注册了独立的 handle，executor 调度时检查 cancellation checker 后直接 emit cancelled result，不启动 adapter。

### 3. SEC/CN/HK 单 filing 取消检查点

**PASS**。取消检查点覆盖充分：

- **SEC**: filing 选择、文件列表获取、HTTP 限流/退避等待、HEAD/GET 请求、文件循环、落盘前后。`SecDownloadCancelledError` 被捕获后 generator return，不产出 `file_failed` 事件。
- **CN/HK ticker 级**: discovery、company meta、candidate selection、overwrite clear、outer summary 聚合。`CnDownloadCancelledError` 被捕获后产出 cancelled summary。
- **CN/HK 单 filing 级**: reset/staging source 写入前后、asset 下载后、PDF bytes read 前后、PDF blob 写入前后、staging source 更新前后、Docling convert 前后、Docling blob 写入前后、最终 source commit 前。`CnDownloadCancelledError` 不被 PDF/Docling general exception handler 包装为 failed filing。

用户取消不会被误计为 failed。已完成的原子落盘（如 PDF blob 已写入、staging source 已更新）保持一致，取消后不启动后续耗时步骤。

### 4. Docling convert 的 cancel 边界

**PASS（含 documented residual risk）**。Docling convert 通过 `asyncio.to_thread(...)` 调用同步第三方转换函数，线程运行期间不能观察 cancellation checker。当前实现保证：进入 convert 前检查取消、convert 返回后检查取消、写入 Docling blob 前后检查取消。README 明确记录了这一限制："需要在转换过程本身做到强中断时，应把 convert 隔离到 process-backed / subprocess 边界并配置 timeout"。这不是 blocker，而是已知的 cooperative cancellation 边界。

### 5. Memory 投影 TOOL_AWAITING.accepted_arguments

**PASS**。`_selected_awaiting_text` 生成的 LLM-facing 文本为：

> 已接受一个等待完成的外部工具步骤。工具：start_fins_download。已确认参数：{"ticker":"CRCL"}。这些参数来自已接受的工具调用，可用于后续同类请求的引用连续性；不要把等待状态、取消状态或调度状态当成业务事实。

该文本：
- 自解释，不依赖内部术语
- 只暴露工具名和业务参数，不泄漏 wait id、digest、event id、payload ref 或调度状态
- 明确禁止模型把等待/取消/调度状态当业务事实
- `_accepted_arguments_mapping` 通过 `source_digest == normalized_digest` 和 `sha256_digest_json` 双重校验确保参数完整性
- 测试验证 `"sha256:" not in text` 和 `"awaiting-1" not in text`

### 6. 类型/docstring/README 触发/测试覆盖

**PASS**。
- 所有新增/修改函数均有完整中文 docstring，包含参数、返回值、异常
- `dayu/fins/README.md` 和 `dayu/host/README.md` 已按 README 触发规则更新
- 测试覆盖：SEC cancel（`test_download_files_stream_cancel_stops_without_failed_event`）、SEC client refresh（`test_owned_client_refreshes_across_asyncio_run_boundaries`）、Fins observation 隔离（`test_abandoned_observation_does_not_pollute_repeat_download_observation`）、CN/HK cancel（`test_cn_download_cancel_after_pdf_download_does_not_start_docling`、`test_cn_download_cancel_after_docling_convert_skips_source_commit`）、Memory projection（`test_tool_awaiting_accepted_arguments_project_to_recent_evidence`）
- pyright: `0 errors, 0 warnings, 0 informations`
- focused pytest: `93 passed`

## Open Questions

- 无。

## Residual Risk

- Fins awaiting 长事务不是 process-backed ToolRuntime capsule。Host truth 不依赖 physical cancel 成功；已提交的 provider 线程只能在业务代码 checkpoint 或自然返回时停止。
- SEC 单个 in-flight `httpx` request 不能被 cooperative checker 从外部强杀；需要更强中断时应设计 source-specific subprocess/process boundary 或显式 request timeout。
- CN/HK Docling convert 在线程内运行同步第三方调用，转换过程中不能观察 cancellation checker；当前保证 convert 前后的 checkpoint，不保证 convert 运行中强中断。
- `_refresh_owned_client_for_current_loop` 测试直接访问私有属性，重构时可能需要同步修改。

## Tests Reviewed

- `tests/fins/test_sec_downloader.py::test_download_files_stream_cancel_stops_without_failed_event` — 验证 SEC 文件循环取消后停止且不产出 failed 事件
- `tests/fins/test_sec_downloader.py::test_owned_client_refreshes_across_asyncio_run_boundaries` — 验证 owned HTTP client 跨 asyncio.run() 边界刷新
- `tests/fins/test_fins_ingestion_runtime.py::test_abandoned_observation_does_not_pollute_repeat_download_observation` — 验证旧 observation abandon 后第二轮独立成功
- `tests/fins/test_cn_download_workflow.py::test_cn_download_cancel_after_pdf_download_does_not_start_docling` — 验证 PDF 后取消不启动 Docling
- `tests/fins/test_cn_download_workflow.py::test_cn_download_cancel_after_docling_convert_skips_source_commit` — 验证 Docling 后取消不提交完成态 source
- `tests/host/test_memory_projection.py::test_tool_awaiting_accepted_arguments_project_to_recent_evidence` — 验证 TOOL_AWAITING 已接受参数进入 memory 且不泄漏 digest/event id
- broader affected tests: `316 passed`

## Verdict

**PASS**。未发现 blocker。所有 6 个 review 维度均通过。3 个低严重度 finding 均为 maintainability / style 级别，不影响正确性、稳定性或安全性。修复方向正确，root cause 与直接证据同源，测试覆盖关键行为和 failure paths，README 同步完整。
