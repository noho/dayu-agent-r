# WU-TOOLS-01-F01-02 Cancellation Propagation Plan

## 1. Goal / Motivation / Success Signal

### Goal

为当前已迁移的 Fins / Web / Doc tools 补齐 `CancellationToken` 传递审计与协作式取消响应，保证工具执行边界能观察 Host 传入的取消信号；其中长事务工具必须在本 WU 内实现取消响应。

### Motivation

问题真实存在，且严重性成立。

第一性原理判断：Host 是 cancel 治理真源，Engine / ToolRuntime / tool callable 只应观察 Host 投影出的 token 或 Host wait adapter 的 durable cancel 事实。若迁移工具丢弃 `BatchToolExecutionContext`，或没有声明 execution context 注入，那么 Host 已经作出的取消治理无法进入工具业务入口。结果是工具可能继续执行阻塞 I/O、CPU / 文件处理或 durable external job start，造成资源浪费、等待记录与外部 job 生命周期不一致，严重时在 awaiting outcome 被 Host accept 前形成 orphan job 窗口。

### Success Signal

- 所有已迁移 Fins / Web / Doc tools 均有明确审计结论：token 是否进入业务入口、在哪些阻塞 / 循环 / 外部资源边界检查、哪些风险 deferred 以及 owner / destination。
- Fins download / preprocess awaiting tools 不再丢弃 `BatchToolExecutionContext`；Host token 在 job start 前被观察，启动后若 Host token 已取消则桥接到 Fins durable job cancel，并返回取消 outcome 或 cancelled job 事实，不引入工具私有 cancel 状态。
- Fins ingestion runtime 继续以 job store 的 `request_cancel` / `claim_running_or_cancelled` / `save_succeeded_or_cancelled` 作为 Fins job cancel 真源，不新增第二套状态机。
- Web `fetch_web_page` 的现有 token 传递路径由测试覆盖；Web `search_web` 补齐 execution context 注入与 provider 路径 checkpoint。
- Doc tools 与 Fins read tools 至少把 token 传入业务入口，并按目录遍历、文件读取、processor / search / XBRL 风险补充 checkpoint。
- 本 WU 不默认扩展 Host wait adapter / Fins runtime contract 做两阶段启动；若评估后 deferred，必须给 owner / destination / residual risk。

## 2. Non-Goals / Scope Boundary

- 不改变 Host cancel durable truth、Run / Attempt / EventLog 状态机、wait record schema 或 Engine public cancellation contract。
- 不用工具私有 cancel 状态替代 Host durable cancel；工具只观察 `CancellationToken`，Fins awaiting job 只通过已有 Fins job store cancel 字段表达 job cancel。
- 不重写 legacy adapter 为通用 `ToolCancelledOutcome` 投影框架；本 WU 只在具体迁移工具声明中使用已支持的 `execution_context_param_name`。
- 不实现真实 SEC / CN / HK download adapter 的物理 revoke；外部 job 物理取消仍属于 WU-WAIT-03 / 后续 Fins production runtime owner。
- 不实现 awaiting accept 前 orphan job 窗口的两阶段启动，除非 plan review / 用户明确批准扩大 Host wait adapter / Fins runtime contract。本 plan 评估后建议 deferred。
- 不修改 README、控制文档、设计文档；本 WU 的实现若触发 README 规则，implementation gate 再按 AGENTS.md 检查并更新。

## 3. Design Document Alignment

- `docs/host/design.md` 定义 Host 是 Session / Run / Attempt / EventLog / cancel / tool governance 的治理真源，ToolRuntime 负责工具治理，Engine 不拥有 Host 状态。计划只让工具观察 Host 传入的 token，不把工具状态提升为 Host truth。
- `docs/engine/design.md` 定义 `AgentRunRequest.cancellation_token` 是 Engine 输入，Engine 在可中断边界观察取消；`BatchToolExecutionContext.timeout_seconds` 只是 `AgentPolicy.tool_execution_timeout_seconds` 投影，工具执行环境协作使用。计划沿用该模型，token 从 ToolRuntime / adapter 传到 tool callable。
- Engine 设计明确工具内部超时、后台任务治理、长事务监控或恢复调度不属于 Engine；Fins awaiting job cancel 仍由 Fins runtime + Host wait adapter 处理，不要求 Engine 理解 Fins job。
- Fins 文档存取必须通过 `dayu.fins.storage`；本 WU 不绕过仓储，只在 read runtime / processor / storage 调用前后加入 token checkpoint。

## 4. First-Principles Judgment And Direct Code Evidence

### 判断

当前 root cause 不是缺全新 Host cancel 状态机，也不是 Fins runtime 没有 cancel 状态。直接根因是迁移工具到业务入口之间的 token 桥接不完整：

- Fins download / preprocess current callable 收到 context 但丢弃，导致 Host token 不能影响 durable job start。
- Fins read tools 与 Doc tools 使用 legacy adapter，但工具声明未要求注入 execution context，业务函数拿不到 token。
- Web fetch path 已有 token 注入和 checkpoint，但 Web search path 未声明 execution context，provider 检索路径拿不到 token。

### Direct Evidence

- `dayu/fins/tools/download_tools.py:47-70`：`FinsDownloadToolCallable.__call__` 接收 `BatchToolExecutionContext`，但 `line 66` `del context`，随后直接 `self.runtime.start_download(request)`。
- `dayu/fins/tools/preprocess_tools.py:46-69`：`FinsPreprocessToolCallable.__call__` 同样 `del context` 后直接 `self.runtime.start_preprocess(request)`。
- `dayu/fins/ingestion_runtime.py:1008-1051` 与 `1053-1095`：`start_download` / `start_preprocess` 在创建 queued job 后立即 `executor.submit(...)`；当前没有 token 参数，也没有 prepare / activate 分离。
- `dayu/fins/ingestion_runtime.py:1114-1128`、`1196-1256`、`1324-1327`、`1392-1409`：runtime 已有 `request_cancel`、运行前 claim、循环中与终态前 cancel 检查，证明 Fins job cancel 状态机已存在。
- `dayu/fins/ingestion/wait_adapter.py:127-141`：Host abandon wait 会调用 `runtime.request_cancel(job_id)`；`282-300` 已把 Fins `CANCELLED` 投影为 `ToolCancelledOutcome`。
- `dayu/tools/_legacy_adapter/definition_adapter.py:90-114`：legacy adapter 已支持 `execution_context_param_name` 注入，说明不需要改 adapter public contract。
- `dayu/tools/web/web_tools.py:1149-1189`：`fetch_web_page` 声明 `execution_context_param_name="execution_context"`，并从 context 解析 token。
- `dayu/tools/web/web_tools.py:1224-1285`：fetch path 把 token 传给 Playwright fallback、warmup、probe、fetch convert，并在阶段间 checkpoint。
- `dayu/tools/web/web_tools.py:1070-1106` 与 `dayu/tools/web/web_search_providers.py:134-149`：`search_web` 没有 execution context 参数，`search_public_web` 也没有 token 参数。
- `dayu/tools/doc_tools.py:620-685`：`search_files` 递归遍历目录、创建 processor、读取文件并搜索，但没有 context / token 参数。
- `dayu/fins/tools/fins_tools.py:165-210` 等 read tool factory：Fins read tool 声明没有 `execution_context_param_name`，业务入口直接调用 `FinsReadRuntime`。

## 5. Affected Files / Modules

Implementation gate 允许修改下列模块；未列出的生产模块不得修改，除非 plan review 明确批准：

- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/search_engine.py`（仅当 `FinsReadRuntime.search_document` checkpoint 必须下沉）
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_search_providers.py`
- `dayu/tools/doc_tools.py`
- 相关测试：
  - `tests/fins/test_fins_ingestion_tools.py`
  - `tests/fins/test_fins_ingestion_runtime.py`
  - `tests/fins/test_fins_storage_provider.py`
  - `tests/tools/web/test_web_tools_provider.py`
  - `tests/tools/test_doc_tools_provider.py`
  - `tests/tools/test_combined_tools_acceptance.py`

不允许修改：

- Host durable schema、EventLog、Run / Attempt 状态机。
- Engine `AgentRunRequest` / `BatchToolExecutionContext` contract。
- `dayu/tools/_legacy_adapter/definition_adapter.py`，除非实现时发现 adapter 当前注入逻辑有直接 bug；当前证据显示不需要。

## 6. Contract / Schema / State Machine / Public Interface Changes

### Contract Changes

- 不改 Host / Engine public contract。
- direct Fins awaiting callable 的返回类型 `ToolExecutionOutcome` 已合法包含 `ToolCancelledOutcome`。因此 download / preprocess callable 在观察到 Host token 已取消时可以直接返回 cancelled outcome；这不是 callable 协议变更，也不需要修改 Host / Engine contract。
- Fins ingestion runtime 可新增朴素参数：
  - `start_download(self, request: FinsDownloadRequest, *, cancellation_token: CancellationToken | None = None)`.
  - `start_preprocess(self, request: FinsPreprocessRequest, *, cancellation_token: CancellationToken | None = None)`.
  - 或更保守地新增 private helper，并让 tool callable 在 start 前后桥接 `runtime.request_cancel(start.job_id)`。implementation review 应优先选择最小、类型清晰、测试可验证的方案。
- Fins read runtime 与 Doc/Web legacy tools 可新增 keyword-only `execution_context: BatchToolExecutionContext | None = None` 或 `cancellation_token: CancellationToken | None = None` 参数；这些参数不得进入 LLM-facing schema。

### Schema Changes

无 durable schema 变更。无 tool JSON schema 参数变更。`execution_context_param_name` 是 adapter 注入 metadata，不暴露给 LLM。

### State Machine Changes

无 Host 状态机变更。Fins ingestion job 状态机不新增状态，只复用 `QUEUED / RUNNING / CANCELLING / CANCELLED`。

### 两阶段启动评估

候选方案：`prepare durable job -> Host awaiting accept 成功 -> activate/submit background job`。

实现代价与契约影响：

- Fins runtime 需要拆分 `start_download/start_preprocess` 为 prepare 与 activate，且要保证 activate 幂等、重复 activate 不重复 submit、prepare 后未 activate 的 job 可被 abandon / cleanup。
- Fins `ToolAwaitingOutcome` 目前只携带 wait spec / snapshot，无法表达“Host accept 成功后回调 activate”的 side effect contract。
- Host ToolRuntime accept barrier / wait adapter 需要新增 awaiting accepted hook 或 adapter activation contract，否则 Fins 工具无法在 durable accept 后可靠启动后台 job。
- 新 contract 需要定义 activate 失败时 Host 已 accepted awaiting fact 的修复语义、poller 看到 prepared-but-not-active 的行为、Host cancel 发生在 prepared 与 activate 之间的收口语义。
- 该变化会跨 Host wait adapter、Fins runtime、测试 smoke 和 recovery / orphan 语义，超出本 WU 的 token 传递审计与协作式取消响应目标。

Plan 裁决：本 WU 不实现两阶段启动。将 residual risk 记为 deferred，owner / destination 为 WU-WAIT-03 或独立 WU-TOOLS-01-F01-02-follow-up（由总控决定），设计真源需先补 Host awaiting accepted activation contract 后才能实现。

本 WU 内的 mitigation：

- Fins tool start 前观察 token，若已取消则不创建 job。
- Fins tool start 后、返回 awaiting outcome 前再次观察 token；若已取消，立即 `runtime.request_cancel(job_id)` 并返回 `ToolCancelledOutcome` 或保证 job record 进入 cancelling/cancelled 可由 wait adapter 收口。
- Fins runtime 执行前、循环中、终态前已有 durable cancel check；本 WU 补测试证明 start 后 cancel 能桥接到 durable job。

## 7. Implementation Decisions

- 使用 `CancellationToken | None` 作为传递形状；不使用 `object`、`Any` 或 extra payload。
- 为每个工具族提供模块级私有 helper，例如 `_cancellation_token_from_context(...)`、`_raise_if_cancelled(...)` 或 `_cancelled_outcome(...)`；不新增 god helper。
- legacy Web / Doc / Fins read tools 因 adapter 当前会把异常投影为 `ToolFailedOutcome`，实现时优先沿用现有 Web `tool_cancelled` 业务错误模式，避免本 WU 改造 legacy adapter outcome 投影。
- direct Fins awaiting callable 可以直接返回 `ToolCancelledOutcome`，因为它不经过 legacy exception projection；该返回值已经属于 `ToolExecutionOutcome` 联合类型，不需要修改 callable 协议、Host contract 或 Engine contract。
- checkpoint 位置按风险排序：
  - 阻塞外部 I/O 前后：Web provider HTTP、Web fetch requests、Playwright fallback、Fins download adapter。
  - 长循环：Doc `rglob`、Fins read search / tables / facts、Fins preprocess documents、download documents / rejected artifacts。
  - CPU / 文件处理：Doc processor creation / list / search / read_section，Fins processor / XBRL / search engine。
  - 终态边界：Fins awaiting start 后返回 awaiting outcome 前。
- 取消响应必须保持幂等：重复 cancel 不重复写错误，不影响 terminal job，Fins job store 现有 `request_cancel` 语义可复用。

## 8. Small Implementation Slices

### Slice 1: Fins Awaiting Tools Token Bridge

Allowed files / modules:

- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/ingestion_runtime.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Exact changes:

- 在 download / preprocess tool callable 中删除 `del context`，读取 `context.cancellation_token`。
- start 前若 token 已取消，返回 `ToolCancelledOutcome(reason=TOOL_CANCELLED_REASON_HOST_CANCELLED, ...)`，不创建 durable job。
- 调用 runtime start 时传入 token，或在 start 返回后立即 checkpoint；若 start 后 token 取消，调用 `runtime.request_cancel(start.job_id)` 并返回取消 outcome。若 `request_cancel` 因 job 已终态返回 terminal，按 runtime 返回事实处理，不抛异常。
- 在 `FinsIngestionRuntime.start_download/start_preprocess` 的关键边界加入可选 token：
  - normalize / request_summary 后、create job 前 checkpoint。
  - durable job create 后、后台 `executor.submit` 前必须做同步 token checkpoint；若 checkpoint 命中 cancel，必须调用 `runtime.request_cancel(job_id)` 并不得 submit 后台 job。
  - create / checkpoint / submit 决策必须满足同一个不可破坏时序：实现可以扩展 `_start_lock` 范围覆盖 durable create、同步 checkpoint 与 submit 决策，也可以在锁释放后、submit 前做二次同步 checkpoint；无论采用哪种方案，都不得留下“checkpoint 已看到取消但仍 submit 后台 job”的窗口。
  - submit 后不再用 token 作为 truth；后台 job 继续通过 job store durable cancel 观察。
- 如需新增 helper，只放在 `ingestion_runtime.py` 模块级私有函数，docstring 中文完整。

Call paths / data flow:

`ToolRuntime -> BatchToolExecutionContext.cancellation_token -> FinsDownloadToolCallable/FinsPreprocessToolCallable -> FinsIngestionRuntime.start_* -> job_store.request_cancel / executor.submit -> wait_adapter.poll_wait/abandon_wait`.

Error handling:

- 参数错误仍返回现有 invalid_argument failed outcome。
- job 创建失败仍返回现有 start_failed failed outcome。
- cancel checkpoint 不吞掉 OSError；若 start 后 request_cancel 因 OSError 失败，返回 failed outcome，hint 指向 Fins workspace 存储权限。

Invariants:

- token cancelled before start must not create a job.
- token cancelled between create and submit must leave job durable cancelling/cancelled and must not submit background operation.
- durable job create 后、后台 submit 前的取消检查必须是同步 checkpoint；命中取消后必须先桥接到 `runtime.request_cancel(job_id)`，再返回 cancelled outcome 或可收口的 cancelled job 事实。
- token not cancelled preserves existing awaiting outcome behavior.
- Host cancel truth remains Host token / Host wait abandon; Fins job truth remains job store.

Tests:

- `test_download_tool_cancelled_before_start_returns_cancelled_without_job`
- `test_preprocess_tool_cancelled_before_start_returns_cancelled_without_job`
- `test_download_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`
- `test_preprocess_start_cancel_between_create_and_submit_marks_job_cancelled_and_does_not_submit`
- Existing awaiting outcome tests must still pass.

### Slice 2: Web Search Token Propagation And Fetch Coverage

Allowed files / modules:

- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_search_providers.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/test_combined_tools_acceptance.py`

Exact changes:

- Add `execution_context_param_name="execution_context"` to `search_web` decorator.
- Add `execution_context: BatchToolExecutionContext | None = None` to `search_web`.
- Resolve token with existing `_resolve_execution_cancellation_token`.
- Add pre-call checkpoint before `search_public_web`.
- Add `cancellation_token: CancellationToken | None = None` to `search_public_web` and checkpoint:
  - after query/domain normalization;
  - at the start of each provider fallback loop iteration, before each candidate provider attempt;
  - after provider result returns and before filtering / returning.
- Pass token into provider-specific helper only if necessary for additional pre-request checkpoint. Do not attempt to cancel in-flight `requests` beyond existing timeout; requests is synchronous and already bounded by timeout budget.
- Keep `fetch_web_page` behavior but add tests proving token reaches Playwright / fetch kwargs and pre-cancel projects to `tool_cancelled`.

Call paths / data flow:

`ToolRuntime -> legacy adapter context injection -> search_web(execution_context) -> search_public_web(cancellation_token) -> provider selection / requests`.

Error handling:

- For legacy Web tools, cancellation continues to project as `ToolBusinessError(code="tool_cancelled")`, which adapter converts to `ToolFailedOutcome` with stable error code. Do not change adapter-wide cancellation outcome in this WU.
- Provider failures remain fallback across providers unless token is cancelled; cancellation must stop provider fallback and return `tool_cancelled`.
- If token cancellation is observed before a provider attempt, `search_public_web` must not try that provider or any later fallback provider.

Invariants:

- `execution_context` is not part of LLM-facing schema.
- Cancelled search must not try later fallback providers.
- Provider fallback loop checks token before every attempt; cancellation after one provider failure must prevent subsequent fallback attempts.
- Existing fetch safety policy and private network behavior unchanged.

Tests:

- `test_search_web_receives_execution_context_and_passes_cancellation_token`
- `test_search_web_cancelled_before_provider_returns_tool_cancelled`
- `test_search_web_cancelled_between_provider_attempts_stops_fallback`
- Existing `test_fetch_playwright_cancel_projects_to_cancelled_failure` remains passing; add assertion that token object is the execution context token.

### Slice 3: Doc Tools Context Injection And Checkpoints

Allowed files / modules:

- `dayu/tools/doc_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/tools/test_combined_tools_acceptance.py`

Exact changes:

- Import `BatchToolExecutionContext` and `CancellationToken`.
- Add module-level helpers:
  - `_resolve_doc_cancellation_token(execution_context: BatchToolExecutionContext | None) -> CancellationToken | None`
  - `_raise_if_doc_cancelled(cancellation_token: CancellationToken | None) -> None`
  - `_raise_doc_cancelled(...)` using `ToolBusinessError` or an existing adapter-compatible business exception with `code="tool_cancelled"`.
- Add `execution_context_param_name="execution_context"` and optional `execution_context` parameter to all five Doc tools.
- Add checkpoints:
  - `list_files`: before glob, inside file iteration, before return.
  - `get_file_sections`: before processor creation, after processor list, before fallback full read / markdown extraction.
  - `search_files`: before `rglob`, inside each file iteration, before processor search / line scan, before return.
  - `read_file`: before each encoding attempt, after `readlines`, before range extraction.
  - `read_file_section`: before processor creation, before `processor.read_section`, before child traversal.
- Keep path validation in provider / adapter; do not add path policy inside tool function.

Call paths / data flow:

`ToolRuntime -> legacy adapter context injection -> doc tool function -> filesystem / processor helpers`.

Error handling:

- Cancellation returns stable `tool_cancelled` failure through legacy adapter.
- Existing `FileAccessError`, `ToolArgumentError`, `FileNotFoundError` behavior unchanged.

Invariants:

- No write capability added.
- No LLM-facing schema changes.
- Directory/file traversal stops promptly after checkpoint sees cancel.

Tests:

- Pre-cancel each tool returns `tool_cancelled`.
- `search_files` cancelled during iteration stops before scanning later files.
- `read_file` cancelled before fallback encoding / after first failed encoding is observed.
- Existing chaining tests still pass.

### Slice 4: Fins Read Tools Context Injection And Checkpoints

Allowed files / modules:

- `dayu/fins/tools/fins_tools.py`
- `dayu/fins/tools/read_runtime.py`
- `dayu/fins/tools/search_engine.py` only if needed for inner loop checkpoint
- `tests/fins/test_fins_storage_provider.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/tools/test_combined_tools_acceptance.py`

Exact changes:

- Import `BatchToolExecutionContext` and `CancellationToken` in `fins_tools.py`.
- Add execution context injection to all Fins read tool decorators:
  - `list_documents`
  - `get_document_sections`
  - `read_section`
  - `search_document`
  - `list_tables`
  - `get_table`
  - `get_page_content`
  - `get_financial_statement`
  - `query_xbrl_facts`
- Add optional `execution_context` parameter to tool functions and pass `cancellation_token` to `FinsReadRuntime` methods.
- Add optional `cancellation_token` keyword-only parameter to corresponding `FinsReadRuntime` methods.
- Checkpoint density decision:
  - Instant read methods whose work is bounded to one repository metadata/blob access or one direct processor read only need an entry checkpoint plus a checkpoint before the single high-risk call when applicable.
  - Methods involving search, XBRL facts, processor traversal, directory/file loops, table/fact filtering loops, or large result assembly need checkpoints inside the loop or immediately before and after the high-risk boundary.
- Add checkpoints at method entry and before/after high-risk work:
  - repository list / meta / blob reads;
  - processor creation / section/table reads;
  - search engine query loops;
  - XBRL fact query / filtering loops;
  - large table / statement result assembly loops.
- If `read_section` currently has `**_kwargs`, remove avoidable compatibility if implementation can do so safely; do not keep compatibility solely for old tests. If removal expands scope due schema validator behavior, leave as is but do not use it for token.

Call paths / data flow:

`ToolRuntime -> legacy adapter context injection -> Fins read tool function -> FinsReadRuntime(cancellation_token) -> repository / processor / search helpers`.

Error handling:

- Fins read tool cancellation should project as stable `tool_cancelled` failure through legacy adapter unless implementation chooses to add a typed Fins cancellation business error already compatible with adapter.
- Existing Fins `ToolArgumentError` and not-supported result behavior unchanged.

Invariants:

- Fins read tools remain read-only.
- Financial document access remains through `dayu.fins.storage` protocols.
- No read runtime private cancel state is stored between calls.

Tests:

- At least one direct test per risk class:
  - `list_documents` pre-cancel returns `tool_cancelled`.
  - `search_document` cancellation during search stops before completing all candidates.
  - `read_section` cancellation before processor read returns `tool_cancelled`.
  - `query_xbrl_facts` cancellation during filtering stops promptly.
- Provider declaration tests assert all Fins read declarations have execution context injection metadata.
- Combined tools acceptance still confirms no LLM-facing schema pollution.

### Slice 5: Audit Matrix, README Decision, And Validation Closeout

Allowed files / modules:

- Tests listed above.
- README files only if AGENTS.md trigger check says the change belongs to that README responsibility.
- No control document update in implementation slice unless current gate explicitly asks.

Exact changes:

- Add an audit matrix test or explicit assertions in provider tests:
  - Web: `search_web` and `fetch_web_page` have expected context handling.
  - Doc: all five tools have context injection.
  - Fins read: all nine read tools have context injection.
  - Fins awaiting: direct callables consume context and do not `del context`.
- Add source-level guard tests only if behavior tests cannot directly observe a boundary; prefer behavior tests.
- Run affected test commands and pyright.
- Check README triggers:
  - `dayu/fins/` touched -> inspect `dayu/fins/README.md` agent update constraint and update only if cancellation semantics are in scope.
  - `tests/` touched -> inspect `tests/README.md` if present.
  - `dayu/tools/` has no explicit AGENTS README trigger, but if combined tool assembly public behavior changed, inspect top-level `dayu/README.md` only if boundary changed. Expected decision: no design README change because no public schema / architecture boundary changes.

Invariants:

- No test should assert old no-context behavior.
- pyright must not gain or hide errors.

Tests:

See section 9.

## 9. Tests / Validation Commands And Expected Assertions

Implementation gate must run:

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py tests/fins/test_fins_storage_provider.py -q
```

Expected assertions:

- Fins awaiting pre-cancel does not create / submit job.
- Fins start cancellation after durable create marks job cancelling/cancelled and does not submit background job.
- Existing Fins wait adapter cancel / poll behavior remains passing.
- Fins read provider tests prove context injection and cancellation response.

```bash
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/tools/test_combined_tools_acceptance.py -q
```

Expected assertions:

- Web search receives execution context token and stops provider fallback on cancel.
- Web fetch existing Playwright / HTTP cancellation behavior remains passing.
- Doc tools return stable `tool_cancelled` on pre-cancel and stop long loops.
- Combined provider assembly still has no schema pollution.

```bash
source .venv/bin/activate && pyright
```

Expected assertions:

- No new or expanded pyright errors.

Optional focused validation if pyright full repo is too noisy due pre-existing errors:

```bash
source .venv/bin/activate && pyright dayu/fins dayu/tools tests/fins tests/tools
```

This optional command may supplement but must not replace the project-required pyright unless the implementation report explicitly documents pre-existing full-repo blockers.

## 10. Docs Decision

Plan gate writes only this artifact.

Implementation gate expected docs decision:

- No `docs/host/design.md` / `docs/engine/design.md` update for token propagation and checkpoints, because existing design already defines Host as cancel truth and Engine/tool cancellation observation contract.
- No control doc update during implementation unless the gate asks for bookkeeping.
- README update only if README-specific “Agent更新约束” says cancellation behavior belongs there. Likely no README update if implementation only changes internal tool execution behavior and tests.
- If two-stage startup is promoted from deferred to current scope, design docs must be updated before code because it changes Host wait adapter / Fins runtime contract.

## 11. Risks / Open Questions / Residual Risks

| ID | Risk / Question | Decision | Owner / Destination |
|---|---|---|---|
| R1 | Awaiting accept 前 orphan job 窗口无法被 token checkpoint 完全关闭：job 可能已 submit，但 awaiting outcome 尚未被 Host durable accept。 | Deferred；本 WU 只做 start 前/后 checkpoint 与 durable cancel bridge。两阶段启动需先设计 Host awaiting accepted activation contract。 | 总控转入 WU-WAIT-03 或新 WU-TOOLS-01-F01-02A；设计真源 `docs/host/design.md` / `docs/engine/design.md` 先行。 |
| R2 | synchronous `requests` / filesystem / processor 调用无法被 token 强制中断，只能在调用前后 checkpoint。 | Accepted residual limitation；使用 timeout budget + checkpoint，避免假装可抢占式取消。 | 当前 WU implementation report 记录；若需要物理 abort，转 WU-WAIT-03 / provider-specific runtime owner。 |
| R3 | Legacy adapter 把 `ToolBusinessError(code="tool_cancelled")` 投影为 failed outcome，而不是 `ToolCancelledOutcome`。 | 本 WU 不改 adapter-wide contract，避免扩大 blast radius；只保持 stable error code 和 prompt hint。 | 若需要统一 cancelled outcome，后续独立 tool adapter contract WU。 |
| R4 | Fins read runtime 内部 search / XBRL helper 是否需要深层 checkpoint 需 implementation 时用直接代码证据裁决。 | 当前 plan 要求按风险补 checkpoint；如果 helper 深改过大，可在 implementation report 标注具体 owner。 | 当前 WU implementation owner；未完成项必须带 owner/destination。 |

Blocking questions: none for code-generation-ready plan. Two-stage startup is not blocking current WU because it is explicitly deferred with owner / destination.

## 12. Completion Report Format

Implementation agent 完成后按以下格式报告：

```text
改动：
- Fins awaiting: ...
- Web: ...
- Doc: ...
- Fins read: ...

验证：
- <command> -> PASS / FAIL，关键断言...
- pyright -> PASS / pre-existing blocker...

README / docs：
- 检查了 <README path> 的 Agent更新约束，结论...

Residual risks：
- R1 -> deferred owner / destination...
- 新增风险：...

未覆盖项：
- ...
```

## 13. Why This Is Not Over-Designed

- 不新增 Host / Engine public contract，不新增 durable schema，不新增状态机。
- 复用已有 `CancellationToken`、`BatchToolExecutionContext`、legacy adapter `execution_context_param_name`、Fins job store `request_cancel`。
- 按工具风险分级，只在阻塞 I/O、外部资源、CPU / 文件处理和长循环边界加 checkpoint。
- 两阶段启动虽能更彻底关闭 orphan 窗口，但需要跨 Host wait adapter 与 Fins runtime contract；本 plan 明确 deferred，不把大契约变更伪装成 bug fix。
- 测试覆盖按行为闭环组织，不靠兼容 wrapper 或 source-only 断言保旧行为。
