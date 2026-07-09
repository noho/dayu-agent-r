# WU-CLI-SMOKE-01 Fins Cancel / Memory Root Cause

## 结论

本次问题是真实 blocking bug，不是单纯的“合作式取消慢”。用户取消第一轮 `start_fins_download` 后，Host durable truth 已正确收口为 cancelled，且 wait poller 对 Fins observation 做了 best-effort abandon；但 Fins 后台 observation 仍在同进程线程里继续执行，SEC downloader 又复用了绑定旧 `asyncio.run(...)` 事件循环的 owned `httpx.AsyncClient`，导致第二轮同类下载进入 `Event loop is closed`。同时 Conversation Memory 没有投影第一轮已接受的 `TOOL_AWAITING.accepted_arguments={"ticker":"CRCL"}`，第二轮模型缺少“Circle -> CRCL 已确认参数”的 LLM-facing continuity，只能重新查 ticker。

修复方向不是把 Fins download / preprocess / upload 强塞进普通 process-backed ToolRuntime。Host truth 继续不依赖 provider physical cancel 成功；Fins awaiting 长事务仍走 `ToolAwaitingOutcome(EXTERNAL_JOB)`、Host awaiting accept、activation adapter、wait poller 和 best-effort observation lifecycle。修复点放在 Fins runtime / downloader 自身取消检查、SEC owned async client 生命周期，以及 Host memory 对已接受 awaiting 参数的安全投影。

## 直接证据

- Host control doc 将 `WU-TOOLS-CANCEL-01` 标为 completed，但对应 scope 是 Tool/provider blocking I/O hardening。`dayu/host/README.md` 当前实现也写明 process-backed 覆盖 Doc、Fins read、Web blocking tools；长事务工具返回 `ToolAwaitingOutcome` 后进入 Host waiting，而 Fins wait adapter 对 cancel 使用 `ABANDON` 语义做 best-effort observation cancel / cleanup。
- `dayu/fins/README.md` 的 Fins awaiting 路径明确：download / preprocess / upload awaiting tools 只 prepare process-local observation，Host awaiting accept 后 activation 提交后台 executor；后台 submit 后取消是 operation-scoped cancellation state / checker 的 cooperative cancel。
- `dayu/fins/ingestion_runtime.py` 中 observed operation record 存在 `_observations` 进程内字典；`cancel_observation()` 只设置 cancellation state；`abandon_observation()` pop record 并 best-effort request_cancel，不 join 或 kill 已提交线程。
- 原 SEC download 路径的取消检查主要在 ticker / filing 外层和文档边界；用户取消后已进入的单 filing 仍能继续跑到“美股下载完成 ticker=CRCL total=3 downloaded=3”。
- `dayu/fins/pipelines/sec_pipeline.py` 的 sync facade 通过 `asyncio.run(...)` 执行异步 SEC 下载；`SecDownloader` 原来在实例初始化时创建并长期复用 owned `httpx.AsyncClient`。同一 downloader 跨多次 `asyncio.run(...)` 使用时，client 内部资源可能绑定上一轮已关闭 event loop，这是第二轮 `Event loop is closed` 的直接代码根因。
- `dayu/host/memory.py` 原来只投影 `USER_INPUT_ACCEPTED`、`RUN_SUCCEEDED`、`TOOL_RESULT_ACCEPTED`、`CONTEXT_COMPACTED`；`dayu/host/durable/memory.py` filter 也不包含 `TOOL_AWAITING`。因此第一轮 accepted awaiting tool args 没进入 selected recent / recent evidence，第二轮 LLM 看不到已接受参数 continuity。
- CN/HK download 中 Docling convert 通过 `asyncio.to_thread(...)` 调同步第三方转换函数。线程运行期间第三方同步调用无法观察 cancellation token；可行边界是进入 convert 前、返回后、后续 blob/source/processed 写入前后的 checkpoint。强中断需要 process-backed / subprocess 隔离与 timeout。

## Root Cause

1. Coverage gap: `WU-TOOLS-CANCEL-01` 完成的是 process-backed blocking tools 的 hard interrupt。Fins download / preprocess / upload 被有意保留为 awaiting `EXTERNAL_JOB` 长事务，不属于 process-backed ToolRuntime capsule 覆盖范围。Host-side cancellation correctness 已满足：旧 wait result 不恢复旧 Run，provider lifecycle cleanup 是 best-effort；但 Fins 自身后台线程仍必须在业务步骤中足够频繁地观察取消。

2. SEC implementation bug: `SecDownloader` owned `httpx.AsyncClient` 跨 `asyncio.run(...)` 事件循环复用。第一轮取消后底层线程自然跑完并关闭其 loop，第二轮复用同一 AsyncClient 时触发旧 loop 资源访问，表现为 `Event loop is closed`。

3. Cancel checkpoint gap: SEC、CN/HK、Fins runtime producer 在进入长事务或单 filing 内部耗时步骤前后的检查点不足。用户取消后，旧 observation 仍可能启动后续 adapter、HTTP、PDF read/write、Docling convert 或 blob/source 写入步骤；这会延迟 cancelled summary，并增加旧后台执行污染第二轮观测的机会。

4. Memory continuity gap: Host EventLog 已有 `TOOL_AWAITING.accepted_arguments` 和 digest，但 Conversation Memory 不消费该 canonical fact。第二轮同类请求只能看到两条用户输入“下载Circle财报”，看不到第一轮已接受的 `ticker=CRCL`。

## 已实施修复

- `dayu/fins/ingestion_runtime.py`
  - download / preprocess / upload direct producer 在发出 preparing progress 后、进入业务执行前检查 cancellation checker；已取消 observation 即使后来被 executor 调度，也直接产出 cancelled result，不再启动下载 adapter / 预处理 / 上传 runner。

- `dayu/fins/downloaders/sec_downloader.py`
  - 增加 `SecDownloadCancelledError` 与 HTTP / 文件下载取消检查点。
  - 在 filing 文件列表、HEAD / GET、限流等待、重试退避、文件循环、落盘前后检查取消；取消命中停止后续文件，不生成 failed file。
  - owned `httpx.AsyncClient` 按当前 running event loop identity 刷新，避免同一 downloader 跨 `asyncio.run(...)` 复用绑定已关闭 loop 的 client。

- `dayu/fins/pipelines/sec_download_workflow.py`
- `dayu/fins/pipelines/sec_download_filing_workflow.py`
- `dayu/fins/pipelines/sec_pipeline.py`
  - 将 cancel checker 传入单 filing 下载、SEC 文件列表和文件下载流；取消命中时停止当前 filing 流，不把用户取消计为 failed filing。

- `dayu/fins/pipelines/cn_download_workflow.py`
  - 在 CN/HK discovery、company meta、candidate list、overwrite clear 和 outer summary 聚合阶段增加取消检查；捕获 `CnDownloadCancelledError` 后产出 cancelled summary，而不是落入 generic exception 变成 failed。

- `dayu/fins/pipelines/cn_download_filing_workflow.py`
  - 在单 filing 内增加取消检查点：reset/staging source 写入前后、asset 下载后、PDF bytes read 前后、PDF blob 写入前后、staging source 更新前后、Docling convert 前后、Docling blob 写入前后、最终 source commit 前。
  - `CnDownloadCancelledError` 不再被 PDF / Docling general exception handler 包装成 failed filing。
  - 已完成的原子落盘保持一致；取消后不启动后续耗时步骤。

- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
  - memory filter 纳入 `TOOL_AWAITING`。
  - 只在 `accepted_arguments_source_digest == normalized_arguments_digest` 且内容 digest 校验通过时，把 tool name 与 LLM-safe accepted args 投影为 selected recent / recent evidence continuity。
  - 不投影 hidden thinking、payload ref、event id、digest、wait id 或调度状态；文本明确禁止把等待/取消/调度状态当业务事实。

- README
  - `dayu/fins/README.md` 补充当前 SEC/CN/HK 取消检查语义与 Docling convert 的线程取消限制。
  - `dayu/host/README.md` 补充 `TOOL_AWAITING` accepted arguments 的 memory projection 语义。

## 测试计划与覆盖

- SEC path:
  - `tests/fins/test_sec_downloader.py::test_download_files_stream_cancel_stops_without_failed_event`
  - `tests/fins/test_sec_downloader.py::test_owned_client_refreshes_across_asyncio_run_boundaries`
  - 既有 SEC downloader / pipeline download tests 覆盖 304、overwrite、zero-byte、failure 聚合不回归。

- Fins observation / repeat interactive-style path:
  - `tests/fins/test_fins_ingestion_runtime.py::test_abandoned_observation_does_not_pollute_repeat_download_observation`
  - 覆盖第一轮 observed download activation 后 cancel + abandon，旧已提交 operation 后续被 executor 调度也不启动 adapter；第二轮同类 observed download 独立成功。

- CN/HK path:
  - `tests/fins/test_cn_download_workflow.py::test_cn_download_cancel_after_pdf_download_does_not_start_docling`
  - `tests/fins/test_cn_download_workflow.py::test_cn_download_cancel_after_docling_convert_skips_source_commit`
  - 覆盖单 filing 内 PDF 后取消不启动 Docling、Docling convert 后取消不提交完成态 source，summary 为 cancelled 且 failed=0。

- Memory projection:
  - `tests/host/test_memory_projection.py::test_tool_awaiting_accepted_arguments_project_to_recent_evidence`
  - 覆盖 `TOOL_AWAITING.accepted_arguments={"ticker":"CRCL"}` 进入 selected recent / recent evidence，且不泄漏 digest / event id。

- 必跑验证：
  - focused pytest: `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py::test_abandoned_observation_does_not_pollute_repeat_download_observation tests/fins/test_sec_downloader.py tests/fins/test_cn_download_workflow.py tests/host/test_memory_projection.py -q`，`93 passed`。
  - broader affected pytest: `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py tests/fins/test_sec_downloader.py tests/fins/test_sec_pipeline_download_stream.py tests/fins/test_sec_pipeline_download.py tests/fins/test_cn_download_workflow.py tests/fins/test_cn_pipeline.py tests/fins/test_cn_download_runtime.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`，`316 passed`。
  - pyright: `source .venv/bin/activate && pyright`，`0 errors, 0 warnings, 0 informations`。
  - `git diff --check`: passed。

## README 触发

- 修改 `dayu/fins/`，已按 README 触发规则检查并更新 `dayu/fins/README.md`。
- 修改 `dayu/host/`，已按 README 触发规则检查并更新 `dayu/host/README.md`。
- 修改 `tests/`，未发现 `tests/README.md` 需要同步的测试分层或运行契约变化。

## Residual Risk / Controller Decision

- Fins awaiting 长事务仍不是 process-backed ToolRuntime capsule。Host truth 不依赖 physical cancel 成功；旧 wait result 不恢复旧 Run，但已提交的 provider线程只能在业务代码 checkpoint 或自然返回时停止。
- SEC HTTP 请求已在请求前后、限流和退避中检查取消，但单个 in-flight `httpx` request 本身不能被这个 cooperative checker 从外部强杀；需要更强中断时应设计 source-specific subprocess/process boundary 或显式 request timeout 策略。
- CN/HK Docling convert 在线程内运行同步第三方调用，转换过程中不能观察 cancellation checker；当前修复保证不在已取消后开始新 convert，并在 convert 返回后停止后续写入。若产品要求 convert 运行中也能强中断，需要 controller 决策新增 process-backed / subprocess 隔离和 timeout，不应把线程内同步调用伪装成可强制取消。
