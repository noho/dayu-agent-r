# WU-TOOLS-01-F01-02-R1 Plan

## 1. Goal / Motivation / Success Signal

目标：修复 Fins awaiting download / preprocess / upload 工具的 submit-before-accept 窗口。工具 callable 只 prepare 并登记可观察长事务，不提交后台 executor；Host ToolRuntime 在 awaiting accept ack durable 成立后，通过最小 activation hook 触发 Fins activate / submit。

动机成立。当前 Fins awaiting 工具在返回 `ToolAwaitingOutcome` 前已经调用 `runtime.start_observed_*`，而 `FinsIngestionRuntime._start_observed_stream(...)` 会立即 `executor.submit(...)`。Host wait record、`TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 只会在 `ToolRuntime._accept_awaiting(...)` 的 Host awaiting accept path 成功后写入。因此 accept rejected、timeout、stale execution 或 pre-accept cancellation 时，外部长事务已经可能启动，违反 Host 是 wait truth owner 的设计。

成功信号：

- awaiting accept 成功前，download / preprocess / upload 均不会调用 Fins background executor。
- awaiting accept rejected、timeout、stale execution、pre-accept cancellation 均不会 activate prepared operation。
- accepted wait 后 activation 成功进入当前 Fins observation / poll / resolve path。
- activation retry 幂等，同一 prepared operation 不会 double-submit。
- prepared operation 被取消或 abandon 时不启动后台执行。
- activation failure after accepted wait 被 Fins observation 映射为 failed / lost / diagnostic，不让 Run 永久卡在不可解释的 WAITING。
- focused Host / Fins tests 与 pyright 在 implementation 阶段通过。

## 2. Non-goals / Scope Boundary

- 不改变 Engine awaiting 公共模型、`ToolAwaitingOutcome` shape、`ToolExecutor.execute(...)` handshake 或 Engine event 顺序。
- 不让 Engine 拥有 activation、wait record、external job lifecycle truth 或 cancellation truth。
- 不把 activation、execution context、cancellation token、Host governance id、wait id 或 adapter 内部状态暴露到 LLM-facing tool schema。
- 不实现 Issue 89 callback endpoint / auth / replay。
- 不实现 Issue 90 production poller loop / backoff / fencing / retry。
- 不实现 Issue 92 external job physical cancel / revoke / abandon 全量能力。
- 不用 Fins-only workaround 绕过 Host awaiting accept barrier。
- 不新增 durable follower ledger、跨 Attempt duplicate table、通用 wait alias schema、通用 lifecycle supervisor 或跨 provider activation 平台。

## 3. Design Document Alignment

Host design 对齐：

- Host 是 Session / Run / Attempt / EventLog / wait record / cancel / resume 的治理真源。
- Tool awaiting accepted 的状态迁移是 `Run RUNNING / Attempt RUNNING -> Run WAITING / Attempt SUSPENDED`，由 ToolRuntime Host accept transaction 写入 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED` 和 wait record。
- cancel-first 场景下，迟到 `TOOL_AWAITING` / `run_suspended` 不得创建 active wait record。
- wait poller 只读取 Host durable active poll waits，在 transaction 外调用 adapter，再通过 `resolve_wait` 收口 ready / lost。

Engine design 对齐：

- Engine 只通过 `ToolExecutor.execute(BatchToolExecutionRequest)` 做 bounded handshake。
- Engine 不托管工具内部任务或外部长事务生命周期。
- Engine 收到 awaiting outcome 后只产出 `tool_awaiting` / `run_suspended`，不等待、轮询、持久化或恢复外部长事务。
- 因此 activation 和 wait truth 必须留在 Host / ToolRuntime / Fins runtime 边界内，不能修改 Engine public awaiting model。

## 4. First-principles Judgment and Direct Code Evidence

第一性原理判断：

- 外部长事务一旦启动，就已经产生副作用或资源占用；如果 Host 尚未 durable 接受 wait record，系统没有可恢复、可取消、可审计的 truth 来解释这个副作用。
- 正确 barrier 必须在 Host awaiting accept ack 成立之后，而不是 Fins tool callable 内部自行启动。
- 当前问题不是 poller 观察不及时，也不是 wait adapter 缺失；根因是 submit 发生在 Host accept 之前。

直接代码证据：

- `dayu/host/tool_runtime.py`：`_execute_one(...)` 先调用业务 callable，拿到 `ToolAwaitingOutcome` 后才进入 `_accept_awaiting(...)`；`_accept_awaiting(...)` 在 `ToolAwaitingAcceptedAck` 时返回 awaiting outcome，在 rejected / timeout 时返回 governed failure。
- `dayu/host/waiting.py`：`DefaultHostToolAwaitingAcceptPort.accept_tool_awaiting(...)` 在单个 write transaction 内写入 `TOOL_AWAITING`、`RUN_WAITING`、`ATTEMPT_SUSPENDED`、wait record，并把 Run / Attempt 标记为 `WAITING` / `SUSPENDED`。
- `dayu/host/wait_adapter.py`：`WaitPoller.poll_once(...)` 已有 active poll wait 读取、cancelled wait abandon、`WaitPollNotReady`、ready / lost 经 `resolve_wait` 收口。
- `dayu/fins/tools/download_tools.py`、`preprocess_tools.py`、`upload_tools.py`：三个 tool callable 当前直接调用 `runtime.start_observed_download/preprocess/upload(...)` 后构造 `ToolAwaitingOutcome`。
- `dayu/fins/ingestion_runtime.py`：`start_observed_*` 调用 `_start_observed_stream(...)`；`_start_observed_stream(...)` 注册 observation 后立即 `self.executor.submit(...)`。
- `dayu/fins/ingestion/observation_handle.py`：当前 observation 状态已有 `PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED / LOST`，`PENDING` 可表达 prepared-but-not-active 的非 terminal 状态；不需要给 LLM 或 Engine 增加新状态。
- `dayu/fins/ingestion/wait_adapter.py`：Fins poll adapter 当前把 `PENDING / RUNNING` 映射为 `WaitPollNotReady`，terminal snapshot 映射为 Host resolve outcome；可复用 prepared polling 行为。
- `tests/host/test_toolruntime_executor.py`：已有 awaiting accepted ack、rejected、timeout、retry exhausted 和 duplicate awaiting fanout 测试；implementation 需在这些测试上加 activation 断言。
- `tests/fins/test_fins_ingestion_tools.py`：现有 download / preprocess / upload awaiting tool 测试只断言返回 external job awaiting outcome；其中上传测试当前还断言 executor 已提交，implementation 必须改为 accepted activation 后才提交。
- `tests/fins/test_fins_ingestion_runtime.py`：已有 queued job cancel / claim running cancel race 等测试；implementation 可复用 `_HoldingExecutor` / fake executor 证明 prepare 不 submit、activate 幂等。

## 5. Affected Files / Modules

Host:

- `dayu/host/tool_runtime.py`
- `dayu/host/wait_adapter.py`
- `dayu/host/tooling.py`
- `dayu/host/dispatch.py`
- Host tests: `tests/host/test_toolruntime_executor.py`，必要时 `tests/host/test_phase7_waiting_integration.py`

Fins:

- `dayu/fins/ingestion/observation_handle.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/upload_tools.py`
- Fins tests: `tests/fins/test_fins_ingestion_tools.py`、`tests/fins/test_fins_ingestion_runtime.py`

Service wiring:

- `dayu/service/host_assembly.py`
- Service / assembly tests only if existing tests fail or a focused wiring assertion is needed.

Docs in implementation stage:

- `docs/host/design.md`
- `dayu/host/README.md`
- `dayu/fins/README.md`
- `tests/README.md` only if the target README's update constraints say the changed tests alter test organization or required validation practice.

## 6. Contract / Schema / State-machine / Public-interface Changes

Engine contract:

- No change.

LLM-facing tool schema:

- No change to tool names, descriptions, parameter schema, enum descriptions, error texts shown to LLM, or prompt material.
- Activation, cancellation token, Host governance ids and wait ids remain internal and are not projected to the model.

Host internal contract:

- Add a minimal Host-layer activation adapter contract in `dayu.host.wait_adapter`, keyed by existing `WaitAdapterKey`.
- Proposed shape:
  - `WaitActivationRequest`: frozen dataclass with `tool_name: str`, `await_spec: ToolAwaitSpec`, `accepted_ack: ToolAwaitingAcceptedAck`.
  - `WaitActivationAdapter` protocol with `activate_accepted_wait(request: WaitActivationRequest) -> None`.
  - `WaitActivationRegistry` resolving `WaitAdapterKey -> WaitActivationAdapter`.
- This is not a new public await contract. It is construction-time ToolRuntime wiring, parallel to existing wait adapter registry, and exists only to run provider-specific activation after Host wait accept.

ToolRuntime build contract:

- Extend `ToolRuntimeBuildRequest` and internal `_ToolRuntimeExecutor` with `wait_activation_registry: WaitActivationRegistry | None`.
- `HostToolingOptions` and dispatch wiring pass the registry from Service assembly to `ToolRuntimeBuildRequest`.

Fins runtime contract:

- Replace awaiting tool usage of `start_observed_download/preprocess/upload` with prepare / activate two-phase:
  - `prepare_observed_download(request, cancellation_token) -> FinsObservationHandle`
  - `prepare_observed_preprocess(request, cancellation_token) -> FinsObservationHandle`
  - `prepare_observed_upload(request, cancellation_token) -> FinsObservationHandle`
  - `activate_observation(handle) -> None`
- Prepared state is represented by an observation record with `status=FinsObservationStatus.PENDING` plus an internal activated/submitted flag. No durable job schema migration is required.
- Activation must be idempotent under the observation lock: already activated, already terminal, already cancelled, or missing handle must not double-submit.

State-machine changes:

- Before implementation:
  - callable -> Fins `executor.submit` -> returns `ToolAwaitingOutcome` -> Host accept wait.
- After implementation:
  - callable -> Fins prepare observation only -> returns `ToolAwaitingOutcome` -> Host accept wait -> ToolRuntime activation hook -> Fins `executor.submit`.
- Rejected / timeout / stale / pre-accept cancellation:
  - callable may have prepared a local observation, but ToolRuntime does not activate it.
  - prepared observation must not start executor; cleanup, if any, is limited by the process-local prepared-but-unaccepted rules below.
- Accepted wait + activation failure:
  - Fins activation is the primary owner for recording terminal observable state. After Host wait accept has succeeded, every activation failure path must leave the prepared observation terminal `FAILED` or `LOST` when the observation handle can identify a record; ToolRuntime exception handling is only a safety net for bounded diagnostics.
  - If the activation request cannot identify a valid observation handle, the existing Fins wait adapter must map the same invalid or missing observation to `LOST` rather than leaving Host wait polling in `PENDING`.
  - poller later maps failed/lost to existing Host resolve outcome.

Schema changes:

- No durable Host schema change.
- No Fins durable job schema change.
- No Engine schema change.

## 7. Implementation Decisions

Host activation hook placement:

- Place activation in `ToolRuntime._accept_awaiting(...)` after `_accept_awaiting_with_retry(candidate)` returns `ToolAwaitingAcceptedAck`.
- Activation runs after durable wait truth exists and before returning the awaiting outcome to Engine.
- Activation does not run before accept, and does not run for rejected ack, timeout, missing adapter binding, missing external job ref, duplicate fanout waiter, duplicate governed failure, policy rejection, callable exception, runtime timeout, or stale execution rejected by Host accept.

Host activation call timing:

- On accepted ack:
  1. Record duplicate awaiting accepted marker best-effort exactly as today.
  2. Recheck `context.cancellation_token.is_cancelled()` immediately before activation.
  3. Resolve activation adapter by `binding.adapter_key`.
  4. If adapter exists and token is not cancelled, call `activate_accepted_wait(...)`.
  5. If token is cancelled, call no activation. The prepared operation remains non-started and must be cancellable/abandonable by Fins adapter behavior.
  6. Return original `ToolAwaitingOutcome` to Engine.

Activation failure收口:

- Fins activation adapter / runtime must treat terminal observation recording as the primary failure handling path. It must wrap the full activation path that can fail after a prepared observation is identified, including unexpected exceptions before or during submit, and record terminal `FAILED` or `LOST` on that observation before re-raising or returning.
- `executor.submit` failure, unexpected producer construction failure, unexpected stored context failure, or any other activation exception after accepted wait must not leave the observation in `PENDING`.
- Failure messages recorded for the observation must be bounded and business-readable, and must not leak raw provider internals, local paths, Host ids, wait ids, trace ids, or exception reprs into LLM-facing output.
- ToolRuntime should catch unexpected activation adapter exceptions, emit bounded diagnostic through existing diagnostic emitter, and still return awaiting outcome because Host wait truth has already been accepted. This catch is only a safety net; implementation must not rely on ToolRuntime catch as the primary mechanism that makes the Fins observation terminal.
- No new Host terminal event is introduced for activation failure.

Idempotency:

- Host activation may be retried if accept idempotency returns an existing ack or if tests call activation twice. Fins `activate_observation(handle)` must be idempotent and guarded by a per-observation submitted/activated flag.
- Double activation must not call `executor.submit` more than once.

Fins prepare / activate API:

- Prepare registers the observation record and returns the same opaque `FinsObservationHandle` currently used as resume token.
- Prepare performs existing request normalization and start-cancel validation, then stores producer/context/cancellation state on the observation record without submitting executor.
- `activate_observation(handle)` and `cancel_observation(handle)` must coordinate through the same observation lock used by current observation mutation, i.e. the implementation must not introduce a separate activation-only lock or rely on an unlocked status check.
- Activate must, while holding that same observation lock, look up the observation by handle, check cancellation state, terminal status and submitted flag, then atomically mark the record submitted before any executor submit can occur.
- Executor submit may run outside the lock after the submitted mark, but every failure after the mark must transition the observation to terminal `FAILED` or `LOST` through the same observation state path.
- If activation sees a cancelled or terminal prepared record, it must not submit.
- If `executor.submit` fails, activation writes a failed observation state with a bounded business-readable message.

Prepared state / poller behavior:

- Prepared-but-not-active observations use `FinsObservationStatus.PENDING`.
- `FinsIngestionWaitPollAdapter.poll_wait(...)` continues mapping `PENDING` to `WaitPollNotReady`; no new Host poll result type is needed.
- If a prepared observation is abandoned because Host wait is cancelled, `abandon_wait(...)` uses existing `cancel_observation(...)` and `abandon_observation(...)` behavior and must not activate.

Pre-activation cancel:

- ToolRuntime rechecks cancellation before activation.
- Fins runtime `cancel_observation(handle)` on a prepared observation marks it cancelled and prevents later activation submit.
- Fins activation checks cancellation / terminal / submitted state and marks submitted under the same observation lock used by `cancel_observation(handle)`, so cancel-vs-activate ordering is deterministic.

Prepared-but-unaccepted observations:

- For accept rejected, accept timeout, stale execution rejected by Host accept, or cancellation before a wait is accepted, ToolRuntime must not activate the prepared observation.
- These paths must not introduce a durable cleanup ledger, public cleanup contract, new Host wait state, or new ToolAwaitingOutcome field.
- A prepared-but-unaccepted observation has no Host wait record, has not submitted executor work, and is process-local to the Fins runtime. It is therefore harmless if it remains as an unreachable process-local orphan until runtime teardown.
- Implementation may add only narrowly scoped best-effort process-local abandon if the existing prepared handle is already available without changing public contracts. If no safe existing handle path is available, leaving the harmless process-local orphan is the intended behavior for this WU.

Fanout:

- Duplicate awaiting fanout waiter returns the owner's prior awaiting outcome and must not call business callable or activation. Existing #111 semantics remain the base behavior.

Why this is not overdesigned:

- It adds one Host-layer activation adapter keyed by existing `WaitAdapterKey`; it does not add a lifecycle supervisor, provider platform, durable activation ledger, follower ledger, duplicate table, callback server, production retry loop, or new public await lifecycle.
- It reuses existing Host wait accept barrier, existing wait adapter registry pattern, existing observation handle, existing `PENDING` poll semantics, existing wait poller, existing resolve_wait path, and existing duplicate fanout governance.
- The contract is construction-time internal wiring only. Engine and LLM-facing schemas remain unchanged.
- The separate `WaitActivationRegistry` is an intentional boundary choice for this WU: executable provider activation remains construction-time Host wiring instead of being added to the public wait binding metadata.

## 8. Small Implementation Slices

Slice count: 3. This respects the control doc Slice 切分原则 because the work has three semantic closure points: Host post-accept activation contract, Fins prepare/activate behavior, and production assembly plus end-to-end validation. It does not split by file count. Fewer than 3 slices would mix Host contract review, provider runtime state machine review, and Service wiring validation into one large review surface; more than 3 would create process cost without isolating additional failure domains.

### Slice 1: Host accepted-wait activation hook

Objective:

- Add minimal Host ToolRuntime activation hook that only runs after accepted awaiting ack.

Allowed files/modules:

- `dayu/host/wait_adapter.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_phase7_waiting_integration.py` only if needed for production-like wiring assertion.

Exact allowed changes:

- Add `WaitActivationRequest`, `WaitActivationAdapter`, `WaitActivationRegistry` in `dayu.host.wait_adapter`.
- Extend `ToolRuntimeBuildRequest` and `_ToolRuntimeExecutor` with `wait_activation_registry`.
- Extend Host test fixture / harness construction in `tests/host/test_toolruntime_executor.py` to inject `wait_activation_registry` and spy/stub activation adapters, so tests can assert exact activation call counts without production Fins wiring.
- In `_accept_awaiting(...)`, after `ToolAwaitingAcceptedAck` and before returning awaiting outcome, resolve activation adapter by `binding.adapter_key` and call it only if the context cancellation token is not cancelled.
- Ensure no activation call occurs for:
  - awaiting accept rejected,
  - awaiting accept timeout / retry exhausted,
  - missing wait adapter binding,
  - missing external job ref for poll binding,
  - pre-cancelled context before callable,
  - duplicate awaiting fanout waiter,
  - stale execution rejected by Host accept.
- Add bounded diagnostic for unexpected activation adapter exceptions without exposing raw provider/job internals.
- Do not modify Engine, `ToolAwaitingOutcome`, or tool schema.

Tests / validation commands:

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py -q`
- If touched: `source .venv/bin/activate && pytest tests/host/test_phase7_waiting_integration.py -q`

Expected assertions:

- accepted ack triggers exactly one activation call.
- rejected / timeout / missing adapter / missing external job ref trigger zero activation calls.
- cancellation observed before activation triggers zero activation calls.
- duplicate awaiting fanout triggers zero activation calls for waiter.
- activation adapter exception is diagnostic-only and awaiting outcome remains returned after accepted wait.
- Host tests use a spy/stub activation adapter injected through the extended fixture, not production Fins runtime, to prove activation call count and non-activation paths.

Completion signal:

- Host focused tests pass and activation hook is code-generation-ready for Fins adapter use.

Stop condition:

- Stop if implementing activation requires changing Engine public contracts or adding durable Host schema. That would violate this WU boundary.

### Slice 2: Fins prepare / activate two-phase runtime and tools

Objective:

- Convert Fins download / preprocess / upload awaiting tools from immediate submit to prepare-only, with accepted-wait activation submitting the existing direct stream producer.

Allowed files/modules:

- `dayu/fins/ingestion/observation_handle.py`
- `dayu/fins/ingestion_runtime.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/tools/download_tools.py`
- `dayu/fins/tools/preprocess_tools.py`
- `dayu/fins/tools/upload_tools.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Exact allowed changes:

- Update `FinsObservationRuntime` protocol to expose prepare methods and `activate_observation(handle)`.
- Change `FinsIngestionRuntime` observed stream path:
  - prepare registers observation and stores queue/context/producer/cancellation state without `executor.submit`;
  - activate uses the same observation lock as cancellation, checks cancellation / terminal / submitted state under that lock, marks submitted under that lock, and submits once;
  - activation after cancellation or terminal state does not submit;
  - activation submit failure and unexpected activation exceptions after a prepared observation is identified record terminal failed/lost observation snapshots before surfacing the failure.
- Keep direct `start_download`, `start_preprocess`, `start_upload` durable job APIs behavior unchanged unless tests reveal a shared helper needs extraction.
- Change download / preprocess / upload tool callables to call `prepare_observed_*` and return the same `ToolAwaitingOutcome` shape based on observation handle.
- Add Fins activation adapter implementation in `dayu/fins/ingestion/wait_adapter.py`, keyed by `FINS_INGESTION_WAIT_ADAPTER_KEY`, parsing the existing resume token and calling `runtime.activate_observation(handle)`.
- Add builder, for example `build_fins_wait_activation_registry(...)`, parallel to existing wait adapter registry builder but only for activation wiring.
- Do not add a durable Fins prepared job status. Use process-local observation record state and existing `PENDING` snapshot.

Tests / validation commands:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_runtime.py -q`

Expected assertions:

- download / preprocess / upload tool callable returns `ToolAwaitingOutcome` without executor submit.
- activation submits exactly once for each operation.
- repeated activation does not double-submit.
- prepared cancellation before activation prevents submit and yields cancelled/pending-to-cancel observable behavior.
- deterministic cancel/activate ordering test proves cancellation and activation share one observation lock, using a barrier, holding executor, or equivalent deterministic fixture rather than timing sleeps.
- activation submit failure is observable as failed/lost through existing wait adapter mapping.
- unexpected activation exception after a prepared observation exists is observable as terminal failed/lost and cannot remain indefinitely `PENDING`.
- existing opaque observation resume token rules remain unchanged: no job id, cursor, sidecar, storage path or `.dayu` text.

Completion signal:

- Fins focused tests pass, and all three awaiting tools use prepare / activate directly.

Stop condition:

- Stop if Fins activation requires exposing local paths, job ids, storage refs or Host ids in resume token or LLM-facing schema.

### Slice 3: Service wiring, docs, and final focused validation

Objective:

- Wire Fins activation registry through production Host assembly and update required docs, then run focused integration validation and pyright.

Allowed files/modules:

- `dayu/service/host_assembly.py`
- `dayu/host/tooling.py`
- `dayu/host/dispatch.py`
- `tests/host/test_toolruntime_executor.py`
- `tests/host/test_phase7_waiting_integration.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `docs/host/design.md`
- `dayu/host/README.md`
- `dayu/fins/README.md`
- `tests/README.md` only if its own update constraints require it.

Exact allowed changes:

- Extend `HostToolingOptions` with `wait_activation_registry`.
- In `dayu/service/host_assembly.py`, build Fins wait adapter registry and Fins activation registry from the same enabled Fins awaiting provider configs and the same single absolute workspace root.
- In `dayu/host/dispatch.py`, pass `tooling_options.wait_activation_registry` into `ToolRuntimeBuildRequest`.
- Add focused production-wiring test if no existing test exercises Service assembly -> HostToolingOptions -> ToolRuntimeBuildRequest for Fins awaiting tools.
- Update Host design to document accepted-wait activation hook and Engine non-ownership.
- Update Host / Fins README only within their documented update constraints.
- Do not update control doc in implementation slice unless controller explicitly asks after plan acceptance.

Tests / validation commands:

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_executor.py tests/host/test_phase7_waiting_integration.py tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
- If Service assembly test added or touched: `source .venv/bin/activate && pytest tests/service -q` or the exact focused service test file.
- `source .venv/bin/activate && pyright`

Expected assertions:

- production ToolRuntime wiring has both wait adapter registry and activation registry when Fins awaiting providers are enabled.
- accepted wait activation starts Fins observation in production-like path.
- no Engine contract tests need changes.
- pyright reports no new or expanded type errors.

Completion signal:

- Focused tests and pyright pass; docs reflect the Host/Fins internal two-phase activation design.

Stop condition:

- Stop if README update constraints conflict with this WU scope, or if pyright exposes pre-existing unrelated errors outside touched areas that require controller decision.

## 9. Docs Decision

Implementation stage should update:

- `docs/host/design.md`: yes. Host design needs a short statement that ToolRuntime may invoke an internal activation adapter only after awaiting accept ack; Engine remains non-owner.
- `dayu/host/README.md`: check its update constraints after Host files change; likely yes if it documents ToolRuntime / wait adapter responsibilities.
- `dayu/fins/README.md`: check its update constraints after Fins runtime/tool behavior changes; likely yes if it documents awaiting ingestion behavior.
- `tests/README.md`: check after test changes; update only if its constraints say new validation organization or commands must be documented.

Implementation stage should not update:

- `docs/engine/design.md`: no Engine behavior or contract changes.
- Root `README.md`: no user-visible install, CLI/Web/WeChat workflow, command arguments, output channel, log location, workspace file location or end-user troubleshooting change.
- `dayu/README.md`: no UI / Service / Host / Engine boundary change beyond existing Host-owned awaiting governance; if implementation reviewers consider the new internal activation adapter a boundary documentation change, they must explicitly require it.
- Tool schema / prompt docs: no LLM-facing schema or prompt change.

Plan gate current write decision:

- Only this plan artifact is written in this gate.

## 10. Risks / Open Questions

Blocking open questions: none.

Residual risks with owner / destination:

- Production poller scheduling, backoff, fencing and retry are not solved here; owner remains GitHub Issue #90.
- External provider physical cancel / revoke / abandon is not solved here; owner remains GitHub Issue #92.
- Callback endpoint / auth / replay is not solved here; owner remains GitHub Issue #89.
- Process-local observation still cannot survive Host process loss as a production-grade durable external job ledger; this is already consistent with the current lightweight observation design and remains owned by #90 / #92 as applicable.
- If future non-Fins providers need activation, they must add their own adapter keyed by existing `WaitAdapterKey`; no cross-provider platform is created in this WU.

## 11. Completion Report Format for Implementation

Implementation closeout must report:

- changed files,
- slice id completed,
- tests run and exact result,
- pyright result,
- docs updated or intentionally skipped with README constraint evidence,
- residual risks mapped to owner / destination,
- confirmation that no Engine public awaiting model or LLM-facing tool schema changed.
