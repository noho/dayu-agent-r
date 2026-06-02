# WU-TOOL-01 Attempt-scoped Duplicate Governance Plan

## 1. Gate / Role / Baseline

- Gate：planning。
- Role：planning specialist；只产出 code-generation-ready plan，不改 source、tests、README，不 commit / push / PR，不进入 implementation gate。
- Repo：`/Users/leo/workspace/dayu-agent-r`。
- Branch：`fix/wu-tool-01-attempt-scoped-duplicate-governance`。
- Preflight：`git branch --show-current` 返回目标分支；`git status --short` 显示 controller 输入文档存在未提交变更：`docs/host/design.md`、`docs/host/host-core-followup-implementation-control.md`、`docs/reviews/wu-tool-01-discussion-code-inspection-20260601.md`。

## 2. Goal / Motivation

WU-TOOL-01 的动机成立。当前代码把 duplicate governance 绑定到 Run 级内存 registry，duplicate key 不包含 `attempt_id`，并把 duplicate 治理消息写死在执行路径里。这会让同一 Run 的 resume / steer / recovery / reactive compact recovery 新 Attempt 继承旧 Attempt duplicate index，违背 Host 设计中“旧 Attempt 不 resume，新执行必须创建新 Attempt”的治理边界。

本 work unit 的目标是把 duplicate governance 收敛为 attempt-scoped in-memory capability：

- duplicate key / index scope 必须包含当前 `attempt_id`。
- 同一 Attempt 内同工具同 args 的并发 duplicate 必须先经同一个 in-flight claim 串行化，避免未治理的重复真实执行；首个 accepted fact 产生后，后续调用按 typed duplicate policy 进入 `reuse` / `hint` / `require_justification` / `hard_stop` / `allow`。
- 跨 Attempt 不继承 duplicate index；resume、steer、recovery、compact recovery 创建的新 Attempt 中，同 tool + 同 args 默认是新的工具请求。
- 删除 run-scoped duplicate registry 路径，不保留 run-scope 与 attempt-scope 两套兼容行为。
- `TOOL_CALL_GOVERNED` 与 tool trace diagnostic 必须表达 duplicate scope 是当前 Attempt，并记录当前 Attempt 内 prior event refs。
- duplicate policy、治理消息、justification 参数名必须来自 typed policy 配置传入 ToolRuntime，不在执行路径硬编码。

对 `allow` 的实施解释：`allow` 是显式 policy decision，表示 duplicate 命中后仍允许再次真实执行；它不能被实现成隐式 reuse。并发保护的 invariant 是“同 key 同 Attempt 的后续调用必须等首个 in-flight owner 产生 accepted fact 或 durable 缺失诊断后再按 policy 决策”，不是让 `allow` 丧失语义。

## 3. Non-goals / Scope Boundary

- 不引入 durable duplicate ledger。
- 不从 EventLog 重建 duplicate index。
- 不跨 Attempt / Run / Session 复用历史工具结果。
- 不引入 tool freshness、行情/汇率当前性、side-effect 幂等策略。
- 不改变 accepted evidence、ToolResult accepted canonical fact、wait record 或 memory projection 语义。
- 不改 ToolsDiscovery、ScenePrepare、ConfigLoader、scene/config assembly。
- 不把 duplicate governance 移入 Engine、RemoteStub、Service 或业务工具包。
- 不做兼容 re-export / wrapper / facade；旧 run-scoped symbol 和测试必须删除或重命名为 attempt-scoped 真源。

## 4. Direct Evidence

- `docs/host/design.md:2077-2088` 明确第一版 duplicate governance 只治理同一 Attempt，duplicate key 至少包含 `attempt_id`，新 Attempt 不继承旧 Attempt index，不引入 durable ledger。
- `docs/host/design.md:2098-2106` 要求 duplicate policy、模型可见提示、justification 参数名来自 typed 配置或 Attempt snapshot，并且 `TOOL_CALL_GOVERNED` 至少包含 duplicate key、决策、scope、reason、prior event refs。
- `docs/host/design.md:2264` 与 `docs/host/design.md:2327` 明确 WAITING resume 是新 Attempt，duplicate governance 不跨 Attempt 复用或阻断。
- `docs/host/host-core-followup-implementation-control.md:416-421` 将 WU-TOOL-01 目标固定为 attempt-scoped key/index、同 Attempt 并发 duplicate 治理、清理 run-local 路径、diagnostic 表达 Attempt scope、typed policy/prompt/justification。
- `docs/host/host-core-followup-implementation-control.md:432-437` 验收信号要求同 Attempt 并发测试、跨 Attempt 不继承、worker/Host restart 不继承、diagnostic 区分 scope 和 durable 缺失、删除或改写 run-scope 测试。
- `docs/reviews/wu-tool-01-discussion-code-inspection-20260601.md` 裁决当前风险真实存在：`DuplicateGovernanceRequest` 无 `attempt_id`、`_duplicate_key()` 不含 `attempt_id`、`InMemoryRunScopedDuplicateGovernanceRegistry` 按 `run_id` 共享 state、dispatch 按 run 注入 registry、duplicate message 硬编码。
- `dayu/host/tool_runtime.py:1-9` 模块概览仍称 duplicate governance 为 run-scoped。
- `dayu/host/tool_runtime.py:934-948` 的 `DuplicateGovernanceRequest` 只有 tool identity、args、semantic key，没有 `attempt_id`。
- `dayu/host/tool_runtime.py:1123-1180` 的 `DuplicateGovernancePort` / `RunScopedDuplicateGovernanceRegistry` docstring 明确“同 Run”。
- `dayu/host/tool_runtime.py:1635-1805` 的 `_RunLocalDuplicateGovernanceState`、`InMemoryRunLocalDuplicateGovernance`、`InMemoryRunScopedDuplicateGovernanceRegistry` 按 Run 持有 shared state。
- `dayu/host/tool_runtime.py:2478-2487` 构造 duplicate request 时没有传入 `attempt_id`。
- `dayu/host/tool_runtime.py:2914-2919` diagnostic message 写死为 run-local ToolRuntime index。
- `dayu/host/tool_runtime.py:3124-3132` factory 使用 `duplicate_governance_for_run(run_id=...)` 或 `InMemoryRunLocalDuplicateGovernance`。
- `dayu/host/tool_runtime.py:4859-4873` `_duplicate_key()` 只 hash tool name、identity digest、normalized args digest、semantic key，不包含 `attempt_id`。
- `dayu/host/tool_runtime.py:4876-4925` `_policy_decision_from_duplicate()` 调用 `_duplicate_message()`，后者在执行路径硬编码消息。
- `dayu/host/dispatch.py:185-190`、`dayu/host/dispatch.py:735`、`dayu/host/dispatch.py:2694-2696`、`dayu/host/dispatch.py:2972`、`dayu/host/dispatch.py:3170` 显示 scheduler 持有 run-scoped registry、按 run 注入和清理。
- `tests/host/test_toolruntime_duplicate_governance.py:1` 文件 docstring 仍是 run-local；`tests/host/test_toolruntime_duplicate_governance.py:532-568` 断言同 Run 多 handle 共享 duplicate index；`tests/host/test_toolruntime_duplicate_governance.py:571-604` 断言不同 Run 隔离。
- `tests/host/test_dispatch_scheduler.py:2108`、`tests/host/test_dispatch_scheduler.py:2890-2894`、`tests/host/test_dispatch_scheduler.py:4040-4066` 直接访问 `_duplicate_governance_registry.active_run_count()` 并依赖 run registry 生命周期。

## 5. Affected Files / Modules

Production:

- `dayu/host/tool_runtime.py`
- `dayu/host/dispatch.py`
- `dayu/host/tooling.py`
- `dayu/host/tool_trace.py`
- 新增必选模块：`dayu/host/tool_duplicate_governance.py`

Tests:

- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_tooling_options.py`

Docs:

- `dayu/host/README.md`
- `tests/README.md`

## 6. Contract / Schema / State-machine / Public-interface Changes

Contract changes:

- Add required Host-layer neutral typed module `dayu/host/tool_duplicate_governance.py`. It must carry duplicate governance typed contracts only; it must not contain dispatch, scheduler, accept barrier, tool callable execution, or Engine integration logic. Required exports:
  - `DuplicateDecisionKind`
  - `DuplicateGovernanceScope`
  - `DuplicateGovernanceRequest`
  - `DuplicateDecision`
  - `DuplicateAcceptedEntry`
  - `DuplicateDurableMissingReason`
  - `DuplicateGovernanceMessages`
  - `DuplicateGovernancePolicy`
  - attempt-local in-flight state helper types if they are needed by `InMemoryAttemptDuplicateGovernance`
- Do not keep compatibility re-exports in `tool_runtime.py`; callers must import duplicate governance typed contracts from `dayu.host.tool_duplicate_governance`.
- `DuplicateGovernanceScope` is a frozen typed dataclass with:
  - `kind: Literal["attempt"]`
  - `attempt_id: str`
  - `__post_init__` validates `attempt_id` is a non-empty string.
- `DuplicateGovernancePolicy` must include:
  - `default_duplicate_decision: DuplicateDecisionKind`
  - `decisions_by_tool_name: Mapping[str, DuplicateDecisionKind]`
  - `justification_argument_names_by_tool_name: Mapping[str, str]`
  - `messages: DuplicateGovernanceMessages = field(default_factory=DuplicateGovernanceMessages)`
- `DuplicateGovernanceMessages` must expose typed fields, not untyped payload:
  - `allow: str`
  - `reuse: str`
  - `hint: str`
  - `require_justification: str`
  - `hard_stop: str`
  - `attempt_scope_diagnostic: str`
  - `prior_accept_missing: str`
  - `message_for(kind: DuplicateDecisionKind) -> str`
- `DuplicateGovernanceMessages` fields must have default values whose zero-config semantics are equivalent to the current `_duplicate_message()` behavior. `__post_init__` must reject empty or whitespace-only strings for every message field.
- `HostToolingOptions` must accept `duplicate_governance_policy: DuplicateGovernancePolicy = field(default_factory=DuplicateGovernancePolicy)` so production dispatch can pass typed policy into every Attempt ToolRuntime.
- `ToolRuntimeBuildRequest.duplicate_governance_policy` remains typed and becomes the only production duplicate policy input to ToolRuntime. If the policy class is moved to the new module, update imports; do not keep compatibility re-export in `tool_runtime.py`.
- `DuplicateGovernanceRequest` must carry `scope: DuplicateGovernanceScope` instead of a bare `attempt_id`; construction at ToolRuntime call sites must derive it from `ToolRuntimeExecutionScope.attempt_id`.
- `DuplicateDecision` must carry enough context for diagnostics:
  - existing `kind`, `duplicate_key`, `prior_event_refs`, `prior_outcome`
  - `scope: DuplicateGovernanceScope`
  - `reason_code: str` or an equivalent typed reason enum for durable-missing decisions
- `DuplicateGovernancePort` changes from a sync Protocol to an async Protocol:
  - `async def decide_duplicate(request: DuplicateGovernanceRequest) -> DuplicateDecision`
  - `async def record_accepted(request: DuplicateGovernanceRequest, accepted_entry: DuplicateAcceptedEntry) -> None`
  - `async def record_durable_missing(request: DuplicateGovernanceRequest, reason: DuplicateDurableMissingReason) -> None`
  - all ToolRuntime callers must `await` the port methods.
- `TOOL_CALL_GOVERNED` payload must add machine-readable duplicate scope:
  - `duplicate_scope: {"kind": decision.scope.kind, "attempt_id": decision.scope.attempt_id}`
  - keep `attempt_id` top-level because it is already part of canonical event identity.
- Tool trace summary must preserve `duplicate_scope` when present.

Schema changes:

- No SQLite schema change.
- No EventLog table shape change.
- Event payload JSON shape changes for `TOOL_CALL_GOVERNED` only; this is an additive payload field in fresh/current behavior, not a migration.

State-machine changes:

- No Run / Attempt status transition change.
- Duplicate governance lifecycle changes from run registry to attempt-local in-memory index.
- Attempt terminal / scheduler close cleanup no longer clears duplicate registry by run. Attempt-local state is owned by ToolRuntime handle lifetime; scheduler must not use run-scoped cleanup as correctness boundary.

Public interface:

- `HostToolingOptions` is construction-time Host typed input; adding `duplicate_governance_policy` is a public Host construction contract change and must be documented in `dayu/host/README.md`.
- Do not add per-run `SubmitFollowupRequest` fields.
- Do not add raw config dict, profile id, callback, factory, or extra payload field for duplicate policy.

## 7. Implementation Decisions

1. Duplicate scope source of truth is `ToolRuntimeExecutionScope.attempt_id`.
2. `_duplicate_key()` must hash `attempt_id`, `tool_name`, `tool_identity_digest`, `normalized_arguments_digest`, and `semantic_duplicate_key`. It must still exclude `index_in_iteration`.
3. Delete `RunScopedDuplicateGovernanceRegistry`, `InMemoryRunScopedDuplicateGovernanceRegistry`, `_RunLocalDuplicateGovernanceState`, and `InMemoryRunLocalDuplicateGovernance` naming. Replace with attempt-scoped naming:
   - `_AttemptDuplicateGovernanceState`
   - `InMemoryAttemptDuplicateGovernance`
   - no scheduler-wide run registry.
4. ToolRuntime factory must create a fresh `InMemoryAttemptDuplicateGovernance` for each `ToolRuntimeBuildRequest` with execution scope. Because dispatch builds one ToolRuntime handle per Attempt, this naturally prevents cross-Attempt inheritance.
5. Same Attempt concurrent same-key protection must be inside `_AttemptDuplicateGovernanceState`, not in dispatcher or tests. `DuplicateGovernancePort` is async because waiters must await the owner in-flight record without blocking the event loop.
6. In-flight claim state machine:
   - `decide_duplicate()` computes the attempt-scoped duplicate key under the state lock.
   - If an accepted entry already exists for the key, `decide_duplicate()` immediately returns the typed policy decision for that accepted entry.
   - If no accepted entry and no in-flight record exists, `decide_duplicate()` creates an in-flight record in `owner_running` state, returns `DuplicateDecision(kind=ALLOW, scope=...)` for the owner, and marks that caller as the only caller allowed to execute the real tool for this window.
   - If an in-flight record exists, `decide_duplicate()` records the caller as a waiter for that existing record and waits for the record to reach terminal state. A waiter must never execute the real tool while the owner is running.
   - When owner Host accept succeeds, `record_accepted()` stores the accepted entry, sets the in-flight record to `accepted`, notifies waiters, and releases the in-flight map entry. Waiters that already hold the record re-evaluate policy against the accepted entry and return `reuse` / `hint` / `require_justification` / `hard_stop` / policy-driven `allow`.
   - When owner is cancelled, tool callable raises before an accepted ack, Host accept is rejected, or Host accept times out, ToolRuntime must call `record_durable_missing()` from a `finally` path before propagating the owner cancellation/exception to the owner caller. `record_durable_missing()` sets the in-flight record to `durable_missing`, notifies waiters, and releases the in-flight map entry without writing an accepted entry.
   - Waiters observing `durable_missing` return a governed durable-missing decision using `DuplicateGovernancePolicy.messages.prior_accept_missing`; they must not receive the owner `CancelledError` / tool exception / accept exception and must not start a second real tool call in the same in-flight window.
   - After the in-flight map entry is released, a later caller that did not already hold the old in-flight record sees no accepted entry and no in-flight entry, receives fresh `ALLOW`, and may become a new owner.
7. Locking boundaries:
   - The state lock or condition lock may only protect claim creation, accepted-entry reads/writes, terminal state updates, waiter registration, notifications, and in-flight map release.
   - Tool callable execution and Host accept must never run while holding the duplicate governance lock or condition lock.
   - Notification happens after terminal status is written and before or while releasing the map entry; waiters must hold a typed in-flight record reference so removing the map entry cannot make a notified waiter create a fresh owner.
8. `allow` after a prior accepted entry means “policy explicitly allows a second execution” and may execute only after the first call is no longer in-flight. Tests must distinguish this from ungoverned parallel duplicate execution.
9. Duplicate governed candidates and reuse candidates receive prior refs only from `_AttemptDuplicateGovernanceState` accepted entries created in the same `DuplicateGovernanceScope`. This work unit must not read EventLog to validate prior refs. Cross-Attempt refs cannot be produced by attempt-local state; future cross-Attempt retrieval, if ever introduced, must define a separate validation contract.
10. `_policy_decision_from_duplicate()` must read messages from `DuplicateGovernancePolicy.messages`, not from `_duplicate_message()` hardcoded branches.
11. Diagnostic emitter message for duplicate must use `policy.messages.attempt_scope_diagnostic` and include a structured metadata path if `ToolTraceDiagnosticRecord` already supports only reason/message; if it does not support metadata, the EventLog `TOOL_CALL_GOVERNED` payload is the canonical machine-readable scope and diagnostic message must be human-readable attempt-scoped text from typed messages.
12. `HostToolingOptions.duplicate_governance_policy` is the production typed config entry. Dispatch passes `tooling_options.duplicate_governance_policy` into `ToolRuntimeBuildRequest`.
13. Remove scheduler `_duplicate_governance_registry` field and all `clear_run` / `clear_all` calls. Scheduler tests must stop inspecting private active run count.
14. Do not modify truncation run-scoped cursor semantics in this work unit; `run-scoped truncation` references are unrelated and remain allowed.

## 8. Implementation Slices

### Slice 1 - Typed Policy And Attempt-scoped Duplicate State

Objective:

- Replace run-local duplicate policy/message/key/state with typed, attempt-scoped equivalents inside ToolRuntime.

Allowed files:

- `dayu/host/tool_runtime.py`
- `dayu/host/tool_duplicate_governance.py`
- `tests/host/test_toolruntime_duplicate_governance.py`

Exact changes:

- Add `dayu/host/tool_duplicate_governance.py` and move duplicate governance typed contracts there: `DuplicateDecisionKind`, `DuplicateGovernanceScope`, `DuplicateGovernanceRequest`, `DuplicateDecision`, `DuplicateAcceptedEntry`, `DuplicateDurableMissingReason`, `DuplicateGovernanceMessages`, `DuplicateGovernancePolicy`, and any private typed in-flight helper dataclasses/enums needed by `InMemoryAttemptDuplicateGovernance`.
- Remove duplicate governance compatibility re-exports from `tool_runtime.py`; all Host modules must import these typed contracts from `dayu.host.tool_duplicate_governance`.
- Add complete Chinese docstrings for every new class/function and no `Any` / `object` / untyped signatures.
- Add `scope: DuplicateGovernanceScope` to `DuplicateGovernanceRequest`; update all call sites to pass `DuplicateGovernanceScope(kind="attempt", attempt_id=execution_scope.attempt_id)`.
- Add `scope: DuplicateGovernanceScope` to `DuplicateDecision`; governed event and diagnostic paths must consume this typed scope instead of rebuilding scope from loose strings.
- Give `DuplicateGovernanceMessages` default values equivalent to current `_duplicate_message()` behavior, reject empty/whitespace messages in `__post_init__`, and set `DuplicateGovernancePolicy.messages = field(default_factory=DuplicateGovernanceMessages)`.
- Make `DuplicateGovernancePort` async and update all ToolRuntime callers to await `decide_duplicate()`, `record_accepted()`, and `record_durable_missing()`.
- Rename run-local classes/protocols to attempt-local equivalents and remove run-scoped registry protocol.
- Implement in-flight duplicate claim state:
  - use typed private dataclasses for accepted entry and in-flight result;
  - protect state with one concurrency primitive such as `asyncio.Condition`;
  - follow section 7 owner/waiter state machine exactly, including terminal `accepted` / `durable_missing` states, notify timing, and map-entry release timing;
  - do not execute tool callable or Host accept while holding the duplicate governance lock or condition lock;
  - do not use ad hoc dict values with heterogeneous untyped shapes.
- Update `ToolRuntimeExecutor._execute_one()` to await the duplicate decision if the port becomes async.
- Update owner cleanup in `_execute_one()` so cancel, tool exception, Host accept rejection, and Host accept timeout call `record_durable_missing()` in a `finally` path before the owner path re-raises or returns its own governed failure.
- Ensure `_duplicate_key()` includes `attempt_id`.
- Delete `_duplicate_message()` or reduce it to a typed policy method; no hardcoded execution-path prompt branches.
- Update tests:
  - `test_duplicate_key_normalizes_arguments_deterministically` still passes and asserts equal key for same attempt and args.
  - Add `test_duplicate_key_includes_attempt_id`.
  - Rename file/module docstring to attempt-scoped.
  - Replace run-scoped registry tests with same Attempt / different Attempt tests using separate ToolRuntime handles and explicit `attempt_id`.
  - Add a controllable fake accept port with accepted, rejected, and timed-out modes; do not depend on durable store timing to force accept outcomes.
  - Add true concurrent same Attempt tests with a slow `_CountingTool`, `asyncio.Event`, and two `asyncio.create_task(...)` calls against the same key. Use events to ensure owner claims before waiter starts, waiter is blocked while owner runs, and second real execution cannot begin before owner terminal notification.
  - For `reuse` policy with accepted fake accept, assert tool call count is 1, second result returns prior accepted outcome, second candidate has same-scope prior refs, and no waiter bypassed in-flight governance.
  - For rejected fake accept and timed-out fake accept, assert waiter returns governed durable-missing decision / diagnostic, does not receive owner exception, and tool call count remains 1 inside the same in-flight window.
  - For owner cancellation or tool callable exception before accept, assert waiter receives governed durable-missing decision / diagnostic and tool call count remains 1 inside the same in-flight window.
  - After each owner failure window, issue a later third caller with the same Attempt/key and assert it receives fresh `ALLOW` and executes the real tool as a new owner because no accepted entry exists.
  - Add `allow` policy concurrent test: same Attempt/key, owner accepted first, waiter resumes after owner terminal notification, decision is policy-driven `ALLOW`, and the second real execution starts only after owner completion.
  - Add `allow` policy post-owner-completion test: first call completes, second same Attempt/key call is policy-driven `ALLOW`, tool call count becomes 2, and assertions show this is not a pre-governance parallel duplicate.
  - Run `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host/tool_runtime.py tests/host/test_toolruntime_duplicate_governance.py` after Slice 1 edits; remaining matches are only allowed if they refer to unrelated truncation wording or direct evidence in comments that implementation removes.

Expected outcome:

- ToolRuntime unit tests prove key scope includes attempt and in-flight duplicate is governed.
- No run-scoped duplicate class or protocol remains in `tool_runtime.py` or `__all__`.

Stop condition:

- Stop if implementing in-flight waiting requires storing untyped task/outcome payloads or exposing Engine-specific state through duplicate governance; report back for design review.

### Slice 2 - Production Dispatch Wiring And HostToolingOptions Contract

Objective:

- Make production scheduler pass typed duplicate policy into per-Attempt ToolRuntime and remove run-scoped scheduler registry lifecycle.

Allowed files:

- `dayu/host/tooling.py`
- `dayu/host/dispatch.py`
- `dayu/host/tool_runtime.py`
- `tests/host/test_tooling_options.py`
- `tests/host/test_dispatch_scheduler.py`

Exact changes:

- Add `duplicate_governance_policy` to `HostToolingOptions`.
- Validate the policy is a `DuplicateGovernancePolicy` instance if the policy class is not guaranteed by dataclass construction.
- Import `DuplicateGovernancePolicy` from `dayu.host.tool_duplicate_governance`, not from `tool_runtime.py`.
- Update dispatch import list: remove `InMemoryRunScopedDuplicateGovernanceRegistry`.
- Remove `self._duplicate_governance_registry` from `HostDispatchScheduler`.
- Remove scheduler calls to `clear_all()` and `clear_run()`.
- In `_run_input_builder_for_attempt` / equivalent dispatch builder path, pass `duplicate_governance_policy=tooling_options.duplicate_governance_policy` to `ToolRuntimeBuildRequest`.
- Do not add per-run request duplicate policy fields.
- Update scheduler tests:
  - remove private active_run_count assertions;
  - replace `test_reactive_recovery_does_not_clear_duplicate_registry` with a behavior test that reactive recovery accepts a second snapshot with a new `attempt_id` and a duplicate tool call in the second snapshot executes as a new request rather than reusing the old Attempt;
  - update close cleanup tests to assert active worker/lane cleanup, not duplicate registry cleanup.
- Update `test_tooling_options.py` to cover default policy, custom message policy, custom justification parameter policy, and validation of empty message/argument names.
- `test_tooling_options.py` must assert `DuplicateGovernancePolicy()` can be constructed without explicitly passing messages and receives a non-empty default `DuplicateGovernanceMessages` instance through `default_factory`.

Expected outcome:

- Production ToolRuntime no longer receives a run-scoped registry.
- Each Attempt gets a fresh attempt-local duplicate governance object.
- Host construction typed policy can configure duplicate action/messages/justification.

Stop condition:

- Stop if adding duplicate policy to `HostToolingOptions` still creates an import cycle after moving policy types to `dayu/host/tool_duplicate_governance.py`; do not use lazy import or compatibility re-export as the workaround.

### Slice 3 - Governed Event / Diagnostic / Trace Scope

Objective:

- Make durable diagnostics and trace distinguish attempt-scoped duplicate decisions and prior refs.

Allowed files:

- `dayu/host/tool_runtime.py`
- `dayu/host/tool_trace.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_tool_trace_projection.py`
- `tests/host/test_toolruntime_duplicate_governance.py`

Exact changes:

- Add `duplicate_scope` payload to `TOOL_CALL_GOVERNED` event append:
  - `{"kind": decision.scope.kind, "attempt_id": decision.scope.attempt_id}`
- Include `duplicate_scope` in any duplicate decision JSON helper if that is the existing path for EventLog or diagnostics.
- Update `_diagnostic_refs_for_duplicate()` to use typed policy message for attempt-scope diagnostic.
- Update validation for duplicate governed candidate:
  - still requires prior refs for `reuse` / `hint` / `require_justification` / `hard_stop`;
  - reason code must match decision kind;
  - message must match `DuplicateGovernancePolicy.messages.message_for(kind)`;
  - prior refs must come from the attempt-local accepted entry attached to `DuplicateDecision.scope`.
- Do not add EventLog reads to validate prior refs. The same-Attempt invariant is guaranteed by `_AttemptDuplicateGovernanceState` only storing accepted entries for its own `DuplicateGovernanceScope`.
- Update `tool_trace.py` constants/extractors/summary builder to carry `duplicate_scope`.
- Tests:
  - accept barrier test asserts `TOOL_CALL_GOVERNED` payload has `duplicate_scope.kind == "attempt"` and `duplicate_scope.attempt_id == candidate.attempt_id`.
  - accept barrier test asserts prior refs in governed/reuse payload are produced from the same attempt-local accepted entry; it must not mock a cross-Attempt EventLog lookup path.
  - diagnostic test asserts configured duplicate message appears in policy decision and diagnostic message.
  - tool trace projection test asserts `trace_summary["duplicate_scope"]` is present for governed duplicate.

Expected outcome:

- EventLog and trace can explain duplicate scope and prior refs without inspecting run-local implementation details.

Stop condition:

- Stop if existing `ToolTraceDiagnosticRecord` lacks structured metadata and adding metadata would expand tool trace contract broadly. In that case, keep diagnostic message typed/configured and rely on `TOOL_CALL_GOVERNED.payload.duplicate_scope` as the machine-readable source.

### Slice 4 - Regression Matrix, README Sync, Type Check

Objective:

- Close all run-scope references in tests/docs and run affected validation.

Allowed files:

- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_dispatch_scheduler.py`
- `tests/host/test_toolruntime_diagnostics.py`
- `tests/host/test_toolruntime_accept_barrier.py`
- `tests/host/test_tool_trace_projection.py`
- `dayu/host/README.md`
- `tests/README.md`

Exact changes:

- Remove tests that assert same Run cross-Attempt sharing.
- Add cross-Attempt resume/recovery-style regression:
  - first ToolRuntime scope: same `run_id`, `attempt_id="attempt-old"` accepts a result;
  - second ToolRuntime scope: same `run_id`, `attempt_id="attempt-new"` same tool/args;
  - assert second tool callable executes and duplicate decision is `ALLOW` before any local accepted entry exists.
- Add worker/Host restart behavior test at unit level by constructing a fresh `InMemoryAttemptDuplicateGovernance` for same Attempt id and documenting in test name that in-memory index is not durable; assert no old prior refs are reused.
- Update README:
  - `dayu/host/README.md` must replace run-scoped duplicate registry wording with attempt-local in-memory duplicate governance and mention construction-time `HostToolingOptions.duplicate_governance_policy` if added.
  - `tests/README.md` must replace run-scoped duplicate registry coverage with attempt-scoped duplicate/in-flight/cross-Attempt coverage.
- Run terminology grep before marking Slice 4 complete:
  - `rg "run-local|run-scoped|RunScoped|RunLocal|同 Run" dayu/host tests/host dayu/host/README.md tests/README.md`
  - duplicate governance production, tests, and README wording must be attempt-scoped.
  - unrelated truncation run-scoped wording is allowed and should be called out in the slice report instead of changed.
- Run validations listed in section 9.

Expected outcome:

- No production/test/doc wording treats duplicate governance as run-scoped, except unrelated truncation cursor wording.

Stop condition:

- Stop if README update would require describing future config assembly or ToolsDiscovery behavior; keep README limited to current typed Host construction behavior.

## 9. Tests / Validation Commands / Expected Assertions

Run from repo root:

```bash
source .venv/bin/activate
python -m pytest tests/host/test_toolruntime_duplicate_governance.py
python -m pytest tests/host/test_toolruntime_diagnostics.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_tool_trace_projection.py
python -m pytest tests/host/test_dispatch_scheduler.py tests/host/test_tooling_options.py
pyright
```

Expected assertions:

- Same Attempt same tool/args concurrent duplicate under `reuse` executes callable once and second result references prior accepted event refs.
- Same Attempt same tool/args concurrent duplicate tests use a controllable fake accept port to cover accepted, rejected, and timed-out owner accept paths.
- Same Attempt owner cancellation/tool exception/accept rejection/accept timeout: waiter returns governed durable-missing decision/diagnostic, does not receive owner exception/cancellation, and does not execute a second real tool call inside the same in-flight window.
- After an owner failure window is released, a later same Attempt/key caller receives fresh `ALLOW` and executes as a new owner.
- Same Attempt same tool/args concurrent duplicate under `allow` is policy-driven after owner completion: second real execution starts only after owner accepted notification, not as an ungoverned parallel duplicate.
- Same Run different Attempt same tool/args executes as a fresh request and does not reuse old Attempt refs.
- Duplicate key changes when only `attempt_id` changes.
- `allow` policy remains explicit allow; if it executes a second time, test name and assertions must show it is policy-driven after in-flight owner completion, not a parallel ungoverned duplicate.
- `DuplicateGovernanceMessages` zero-config defaults are non-empty and equivalent to the current duplicate governance messages; empty or whitespace-only custom messages are rejected.
- Configured duplicate messages replace default messages in `ToolPolicyDecision.message`, governed failure outcome, and diagnostic message.
- Configured justification argument name controls `require_justification`; no hardcoded argument name remains.
- `TOOL_CALL_GOVERNED.payload.duplicate_scope.kind == "attempt"` and `.attempt_id` equals current Attempt.
- Tool trace summary includes duplicate scope and prior refs.
- Scheduler no longer exposes or clears `_duplicate_governance_registry`.
- `pyright` has no new or expanded type errors.

Failure paths that must be tested or explicitly reported:

- In-flight owner accepts no durable fact because owner cancellation, tool exception, accept rejection, or accept timeout occurs: waiter must not start a second true execution in the same concurrent window and must return governed durable-missing diagnostic.
- `require_justification` without configured argument name: continue current semantics of downgrading to `hint`, but the downgrade must be policy-driven and covered by tests.
- Prior refs must be produced from attempt-local accepted entries; this work unit must not add EventLog reads just to validate prior refs.
- Terminology grep must show no duplicate-governance `run-local` / `run-scoped` / `RunScoped` / `RunLocal` / `同 Run` wording remains outside unrelated truncation wording.

## 10. README Decision

README update is required after implementation because:

- `dayu/host/` production code changes trigger `dayu/host/README.md`.
- `tests/` changes trigger `tests/README.md`.

Do not update root `README.md` unless implementation changes user-facing CLI/open-host usage outside Host construction options. Do not update `dayu/README.md` unless implementation changes global layering or UI / Service / Host / Engine boundaries. This plan does not require either.

## 11. Review Gates

Plan review must verify:

- No run-scoped duplicate compatibility path remains.
- Attempt scope is machine-readable in key and governed event payload.
- Typed policy/message/justification does not use extra payload or raw dict.
- In-flight duplicate coordination is not implemented as a god object or untyped bag.
- Slice boundaries are small and each has tests.

Code review must verify:

- No `Any`, `object`, untyped parameters/returns, lazy import, compatibility wrapper/re-export.
- All new functions/classes have complete Chinese docstrings with 参数、返回值、异常.
- Duplicate state does not cross Attempt through scheduler, registry, module singleton, or shared mutable default.
- No durable ledger, EventLog reconstruction, freshness, side-effect idempotency, or config assembly expansion slipped into scope.
- Tests assert behavior, not only private implementation details.

Aggregate deepreview should run after all implementation slices and fixes per controller workflow.

## 12. Stop Conditions

Implementation must stop and report to controller if:

- Attempt-local in-flight duplicate cannot be implemented without changing Engine `ToolExecutor` contract.
- Correct handling of in-flight owner failure requires a new public tool outcome contract rather than existing governed error outcome.
- Adding typed duplicate policy to `HostToolingOptions` forces broader public config/profile/scene assembly changes.
- Moving duplicate governance typed contracts to `dayu/host/tool_duplicate_governance.py` still cannot avoid an import cycle without lazy imports or compatibility re-exports.
- Existing design proves `allow` must mean “never execute duplicate” rather than “explicitly allow repeat execution”; that would require design clarification because it collapses `allow` into `reuse`.
- Pyright exposes pre-existing errors in touched files that cannot be fixed within WU-TOOL-01 scope.
- Tests require modifying README responsibilities outside `dayu/host/README.md` or `tests/README.md`.

## 13. Risks / Open Questions

Blocking questions for controller：none.

Non-blocking risks:

- `allow` semantics can be misread as violating the “only once” phrasing. Working assumption: `allow` remains explicit permission to execute a duplicate after in-flight governance has observed the prior accepted fact. Signal to revisit: plan review rejects this interpretation or design source changes `allow` semantics.
- Moving duplicate policy types to the required `dayu/host/tool_duplicate_governance.py` module may touch many imports. This is acceptable because it avoids `tooling.py` depending on ToolRuntime implementation details and because compatibility re-exports are explicitly forbidden.
- Async in-flight coordination must not deadlock if owner task is cancelled, raises, or Host accept rejects/times out. Implementation must complete terminal state update, notify waiters, and release the in-flight map entry in `finally` paths; waiters receive governed durable-missing rather than the owner failure.
- Tool trace diagnostic record may not support structured metadata. If so, EventLog payload carries machine-readable duplicate scope and diagnostic message remains typed/configurable text.

## 14. Implementation Completion Report Format

Each implementation slice report must include:

```markdown
## WU-TOOL-01 Slice <id> Completion

- Gate: implementation
- Approved plan: docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md
- Slice: <id/name>
- Changed files:
- Implemented plan items:
- Tests run:
- Pyright run:
- README decision:
- Residual risks:
- Stop conditions hit: yes/no
- Plan gaps or controller decisions needed:
```

Final implementation closeout must explicitly state:

- What changed.
- What was verified.
- README updates.
- Remaining risks / owners.
- Confirmation that no source/test/README compatibility path preserves run-scoped duplicate governance.
