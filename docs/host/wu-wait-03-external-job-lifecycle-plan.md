# WU-WAIT-03 External Job Lifecycle Plan

## Goal / Motivation / Success Signal

Goal: 为 `WAITING` Run 被取消后的 external job physical cancel / revoke / abandon 形成 code-generation-ready plan。Host durable cancellation correctness 必须只依赖 Host 状态机；外部 job lifecycle 动作只能是 best-effort diagnostic，不得 reopen、resume 或改写已 `CANCELLED` 的 Run。

Motivation: 当前 Host 已能把 `WAITING -> CANCELLED` 和 active wait record `waiting -> cancelled` 持久化，也已能在 poller 看到 cancelled wait 后调用 `WaitPollAdapter.abandon_wait(...)`。但现有 adapter contract 只有 `None` / exception，无法区分 provider 支持物理取消、provider 不支持、已本地释放、临时失败等结果；Host / tests 也没有把 “cancel / revoke / abandon 是 best-effort lifecycle，而不是 Run correctness 前置条件” 固化为实现边界。

Success signal:

- `cancel_run` / `cancel_session_runs` 取消 `WAITING` Run 后仍立即返回 `RunStatus.CANCELLED`，不等待外部 provider。
- Production wait poller 观察到 `cancelled` wait 后，按 adapter contract 尝试 best-effort lifecycle；支持和不支持物理取消的 adapter 都有测试。
- Adapter 临时失败只写 poll backoff / diagnostic state，并允许后续重试；unsupported / no-op / success 都会停止重复 lifecycle 尝试。
- late callback / poll / manual result 仍只能通过 common `resolve_wait(...)` path，被 `WAIT_LATE_RESULT_REJECTED` diagnostic 拒绝，不创建 resume Attempt，不追加 canonical tool result。

## Non-goals / Scope Boundary

- 不实现代码；本 gate 只写本 plan artifact。
- 不修改 Engine awaiting public model；Engine 不拥有等待、取消、轮询、恢复或 external job lifecycle。
- 不把 `external_job_id` 变成 Host durable primary key；Host 仍以 wait record 为 durable truth。
- 不要求所有 provider 支持 physical cancel / revoke。
- 不绕过 `resolve_wait(...)` 或 late-result rejection。
- 不创建 issue-87 之外的第二套 watchdog/runtime；复用现有 `WaitPoller` / `WaitPollerSupervisor`。
- 不做 WU-WAIT-04 UI / Service production-grade awaiting E2E smoke。
- 不在 Host cancel transaction 或 command path 内执行 provider I/O。

## Design Document Alignment

Host design alignment:

- `docs/host/design.md` 规定 Host 是 Session / Run / Attempt / EventLog / wait record 的治理真源，Engine / provider 不能拥有 Host 状态。
- `WAITING` Run 取消时，Host 必须 append `CANCEL_REQUESTED`、CAS 标记 active wait records 为 `cancelled`、append `RUN_CANCELLED`，不创建 resume Attempt。
- 外部 job actual cancel / revoke / abandon 属于 adapter best-effort，不能影响 Host terminal correctness。
- `resolve_wait(...)` 是 poll / callback / manual 等待结果唯一治理入口；非 `waiting` wait record 的迟到结果不得进入 canonical fact，必须按 late-result diagnostic 拒绝。
- wait poller 是 background trigger / adapter，只能调用 `resolve_wait(...)` 或更新自身 poll/backoff diagnostic state，不直接写 Run / Attempt terminal truth。

Engine design alignment:

- `docs/engine/design.md` 规定 Engine 只执行单次 `AgentRunRequest`，不持久化 wait record，不轮询 job，不托管外部长事务生命周期。
- `ToolExecutor.execute` timeout / cancellation 只约束 Engine 和工具执行环境的 bounded handshake，不证明外部线程、子进程、HTTP 请求或远端 job 已停止。
- Awaiting suspension 的事实由 Engine 产出后交给 Host 接收；恢复必须由调用方构造新 `AgentRunRequest`，不能恢复旧 Agent / Runner。

## First-principles Judgment And Direct Code Evidence

Judgment: 目标成立，但严重性应限定在 external lifecycle diagnostic / provider cleanup，不是 Host cancellation correctness 缺陷。Host 取消 correctness 已由 durable state machine 保证；缺口是 cancelled wait 到 provider lifecycle 动作之间的 contract 不够自解释、结果不可分类、unsupported provider 无测试。

Direct code evidence:

- `dayu/host/admission.py` 的 `_cancel_waiting(...)` 和 `_cancel_waiting_target(...)` 只调用 `cancel_waiting_run_in_transaction(...)`，返回 `RunStatus.CANCELLED` 路径没有 adapter 调用；这是正确的 command-path 边界。
- `dayu/host/durable/run_transition.py` 的 `cancel_waiting_run_in_transaction(...)` 在同一 transaction 内读取 active wait records、调用 `cancel_active_wait_records_for_run(...)`、append `RUN_CANCELLED`，payload 只包含 `wait_ids`，不包含 provider lifecycle result；这证明 Host terminal truth 与 provider action 已解耦。
- `dayu/host/wait_adapter.py` 的 `WaitPoller.poll_once()` 会 claim `waiting` 或 `cancelled` poll wait；遇到 `WaitRecordStatus.CANCELLED` 时调用 `_abandon_cancelled_wait(...)`，成功后写 `poll_abandoned_at`，失败后写 `ABANDON_ERROR` backoff。该路径是 external lifecycle 最小落点。
- `WaitPollAdapter.abandon_wait(...) -> None` 只能用 exception 表示失败，不能表达 `unsupported`、`no-op`、`cancel requested`、`revoked` 或 `abandoned`，导致 contract 与 #92 的 cancel / revoke / abandon 目标不自解释。
- `dayu/fins/ingestion/wait_adapter.py` 的 `FinsIngestionWaitPollAdapter.abandon_wait(...)` 已顺序调用 `runtime.cancel_observation(...)` 与 `runtime.abandon_observation(...)`；`dayu/fins/ingestion_runtime.py` 的 `cancel_observation(...)` 明确 best-effort，不承诺中断不可取消 blocking call。这是 Fins provider cleanup 能力的直接实现基础。
- `tests/host/test_wait_cancel_late_result.py` 已覆盖 cancel 后 late result 只写一次 `WAIT_LATE_RESULT_REJECTED` diagnostic 且不创建 resume Attempt；该行为必须保持。
- `tests/host/test_wait_adapter_polling.py` 已覆盖 cancelled wait abandon once、abandon failure retry、CAS conflict retry；需要在同一测试边界上增强 result classification。

Root cause: 数据上，durable wait record 只有 `status=cancelled`、`poll_last_outcome`、`poll_abandoned_at` 等 poll diagnostic 字段；逻辑上，adapter contract 把 provider lifecycle 成功、unsupported 与本地 no-op 全部压缩成 `None`。因此 issue-92 应修复 adapter lifecycle contract 与 poller diagnostic 分类，而不是改变 Run cancel 状态机。

## Affected Files / Modules

Implementation may touch:

- `dayu/host/wait_adapter.py`
- `dayu/host/durable/state.py`
- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/ingestion_runtime.py` only if Fins runtime needs a clearer typed return or docstring for existing best-effort cancel / abandon behavior.
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/host/test_wait_cancel_late_result.py`
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`

Files to read but not necessarily modify:

- `dayu/host/admission.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/open_host.py`
- `tests/host/test_open_host_runtime.py`
- `dayu/host/README.md`, `dayu/fins/README.md`, `tests/README.md` for README trigger checks after implementation.

## Contract / Schema / State-machine / Public-interface Changes

Public Engine contract: no change.

Host public API: no change to `cancel_run(...)`, `cancel_session_runs(...)`, `resolve_wait(...)`, `OpenHostOptions`, or `HostToolingOptions`.

Durable DB schema: no table or column change. Additive enum value changes in `WaitPollLastOutcome` are allowed because this work unit starts from the current schema as truth and does not need legacy-db compatibility.

Host internal adapter contract:

- Introduce typed lifecycle result dataclasses in `dayu/host/wait_adapter.py`:
  - `WaitExternalJobLifecycleAction(StrEnum)`: `CANCEL`, `REVOKE`, `ABANDON`.
  - `WaitExternalJobLifecycleApplied`: fields `action: WaitExternalJobLifecycleAction`, `message: str | None`.
  - `WaitExternalJobLifecycleUnsupported`: fields `reason: str`.
  - `WaitExternalJobLifecycleNoop`: fields `reason: str`.
  - `WaitExternalJobLifecycleResult` union of the three dataclasses.
- Change `WaitPollAdapter.abandon_wait(wait_record)` to return `WaitExternalJobLifecycleResult`.
- Method semantics: adapter receives the Host wait record snapshot, chooses the strongest provider-supported best-effort action it actually took, and returns a typed diagnostic result. `CANCEL` means the provider requested physical or cooperative stop. `REVOKE` means the provider can invalidate future delivery/result without necessarily stopping already-running physical work. `ABANDON` means the provider/adapter released local or remote lifecycle tracking and will not deliver the job through this wait path. Current Fins adapter returns `ABANDON` because it requests cooperative cancel and then releases the local observation handle. Ordinary exceptions mean transient adapter failure and must be retried with backoff.
- Add these `WaitPollLastOutcome` values for durable diagnostic precision:
  - `ABANDON_UNSUPPORTED`
  - `ABANDON_NOOP`
  Existing `ABANDONED` remains the success/applied terminal lifecycle marker.
- `WaitPollLastOutcome` remains a `StrEnum`; serialization continues to store `enum.value`, deserialization continues to validate through the enum member set, and row validation must accept rows decoded with the new enum members. Tests must cover serialize/deserialize roundtrip and wait row validation for `ABANDON_UNSUPPORTED` and `ABANDON_NOOP`.

State-machine changes:

- `cancel_waiting_run_in_transaction(...)`: no state-machine change.
- `WaitPoller` cancelled wait path:
  - applied result -> mark `poll_abandoned_at`, `poll_last_outcome=ABANDONED`.
  - unsupported result -> mark `poll_abandoned_at`, `poll_last_outcome=ABANDON_UNSUPPORTED`.
  - noop result -> mark `poll_abandoned_at`, `poll_last_outcome=ABANDON_NOOP`.
  - exception -> release claim with `ABANDON_ERROR` backoff; no `poll_abandoned_at`.
- Parameterize existing durable mutation `mark_wait_record_poll_abandoned(...)` instead of adding a second terminal marker mutation. New signature must add keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED` and keep the current CAS predicate and return semantics. Unsupported and noop terminal results call the same mutation with `ABANDON_UNSUPPORTED` or `ABANDON_NOOP`; setting `poll_abandoned_at` is required to prevent re-claim.
- `WaitPollOnceResult.abandoned` counts cancelled wait records whose terminal lifecycle marker was durably written. Applied, unsupported, and noop results all increment `abandoned` after the CAS write succeeds. Do not add a new counter in this work unit.
- `resolve_wait(...)` late-result rejection remains unchanged and remains the only path for external completion/callback/poll result after cancellation.

LLM-facing text: no tool schema, prompt, memory, compact, evidence, or user-visible LLM-facing content should change. If any implementation accidentally touches LLM-facing text, it must be self-explanatory and must not expose bare internal ids as business facts.

## Implementation Decisions

- Use existing `WaitPoller` / `WaitPollerSupervisor` as the lifecycle trigger. This follows #87 / #90 and avoids a second watchdog runtime.
- Do not call provider adapter inside `cancel_run(...)` or `cancel_session_runs(...)`. Provider I/O can block, fail, or retry; Host command path must stay short and durable.
- Do not add durable schema columns for physical cancel. Current wait row already has `status=cancelled`, claim/backoff fields, `poll_last_outcome`, and `poll_abandoned_at`; the missing part is result classification.
- Do not add provider capability registry. Adapter can return `Unsupported`; central Host does not need to know provider-specific physical cancel APIs.
- Do not make `external_job_id` a lookup key. Adapter receives `WaitRecordRow`, including `external_job_ref` if available, and remains responsible for provider-specific interpretation.
- Keep late results on common `resolve_wait(...)`. This preserves idempotency, conflict handling, diagnostic dedupe, and no-resume invariant.
- Keep implementation in 2 slices. This is a small cross Host/Fins contract cleanup with one state-machine-adjacent path and one provider adapter path. More slices would add gate cost without isolating meaningful rollback risk.

Why this is not over-designed:

- It adds a closed typed union at the existing adapter boundary instead of new runtime, new service, new queue, new durable table, or provider registry.
- It reuses existing poll/backoff fields and supervisor lifecycle.
- It improves testability of the real ambiguity: success vs unsupported vs no-op vs transient failure.

## Implementation Slices

### Slice 1: Host Lifecycle Contract And Poller Diagnostics

Objective: Make Host wait poller cancelled-wait lifecycle explicit, typed, retryable on transient failure, and terminal on applied / unsupported / noop results.

Allowed files:

- `dayu/host/wait_adapter.py`
- `dayu/host/durable/state.py`
- `tests/host/test_wait_adapter_polling.py`
- `tests/host/test_wait_poller_runtime.py`
- `tests/host/test_wait_cancel_late_result.py`

Exact changes:

- Add lifecycle action/result dataclasses and union in `dayu/host/wait_adapter.py`, with complete Chinese docstrings and strict typed fields.
- Update `WaitPollAdapter.abandon_wait(...)` return type and docstring.
- Update all Host test adapters to return a typed result.
- Add `WaitPollLastOutcome.ABANDON_UNSUPPORTED` and `WaitPollLastOutcome.ABANDON_NOOP` in `dayu/host/durable/state.py`; keep StrEnum value-based serialization/deserialization and update tests so both new values roundtrip and pass row validation.
- Parameterize `mark_wait_record_poll_abandoned(...)` with keyword-only `last_outcome: WaitPollLastOutcome = WaitPollLastOutcome.ABANDONED`; keep existing callers valid through the default and use the parameter for unsupported/noop terminal markers.
- Update `_abandon_cancelled_wait(...)`:
  - Resolve missing adapter exactly as today: warning + `MISSING_ADAPTER` backoff.
  - On adapter exception: warning + `ABANDON_ERROR` backoff.
  - On `WaitExternalJobLifecycleApplied`: call `mark_wait_record_poll_abandoned(..., last_outcome=ABANDONED)`, mark lifecycle complete, return `abandoned=1` after CAS success, and stop retrying.
  - On `WaitExternalJobLifecycleUnsupported`: call `mark_wait_record_poll_abandoned(..., last_outcome=ABANDON_UNSUPPORTED)`, mark lifecycle terminal diagnostic, return `abandoned=1` after CAS success, and stop retrying.
  - On `WaitExternalJobLifecycleNoop`: call `mark_wait_record_poll_abandoned(..., last_outcome=ABANDON_NOOP)`, mark lifecycle terminal diagnostic, return `abandoned=1` after CAS success, and stop retrying.
  - Do not call `resolve_wait(...)` from this path.
- Keep `cancel_waiting_run_in_transaction(...)` unchanged unless tests reveal it needs no-op docstring clarification.

State transitions:

- Run: `WAITING -> CANCELLED` remains owned by existing cancel transition.
- Wait record: `waiting -> cancelled` remains owned by existing cancel transition.
- Poller claim: `cancelled + unclaimed + poll_abandoned_at is null -> claimed -> lifecycle result -> unclaimed terminal poll diagnostic`.
- No `RUNNING`, `WAITING`, `RESUME_REQUESTED`, `ATTEMPT_STARTED`, or canonical tool result may be written by lifecycle action.

Error handling:

- Adapter ordinary exception is transient and retryable via existing backoff.
- Missing adapter is retryable because registry may be fixed after restart.
- Unsupported / noop are non-error lifecycle terminal diagnostics.
- CAS conflict after adapter returns does not rerun immediately in the same poll round; wait remains retryable unless terminal mark succeeded. This applies identically to applied, unsupported, and noop terminal marker writes.

Invariants:

- Host cancellation result never depends on adapter result.
- `resolve_wait(...)` remains the only entry for external completion results.
- `poll_abandoned_at` is the terminal lifecycle marker for applied, unsupported, and noop cancelled-wait lifecycle results, and only applies to `status=cancelled`.
- Poller close gate still skips lifecycle action before adapter call and releases with shutdown backoff.
- No `Any`, `object`, untyped parameters, or untyped returns are introduced.

Tests / validation:

- Update existing cancelled wait tests to assert typed applied result still marks lifecycle complete once, writes `poll_abandoned_at`, writes `poll_last_outcome=ABANDONED`, and increments `poll_once().abandoned`.
- Add test for unsupported adapter: `poll_once().abandoned` must increment, `poll_last_outcome=ABANDON_UNSUPPORTED`, `poll_abandoned_at` is set, wait must not be observed again, and no `resolve_wait` call occurs.
- Add test for no-op adapter, especially wait without usable external ref: `poll_once().abandoned` must increment, `poll_last_outcome=ABANDON_NOOP`, `poll_abandoned_at` is set, wait must not be observed again, and no `resolve_wait` call occurs.
- Add CAS conflict tests for unsupported and noop terminal marker writes: after adapter returns, a lost CAS reports claim conflict, does not count as `abandoned`, and leaves the wait retryable for a later poll.
- Keep `test_failed_cancelled_wait_abandon_is_retried_next_poll` proving exception path remains retryable.
- Keep `test_late_result_after_cancel_writes_bounded_diagnostic` unchanged in behavior.

Completion signal:

- Host focused tests pass.
- Pyright reports no new errors.
- Review can see a closed typed lifecycle contract and no state-machine rewrite.

Stop condition:

- Stop if implementation requires new durable columns, new public `OpenHostOptions`, or invoking adapter from cancel command path. That would exceed this plan and require design-source update.

### Slice 2: Fins Adapter/Runtime Mapping And Provider-focused Tests

Objective: Map Fins process-local observation cleanup to the new Host lifecycle result contract and prove Fins cancel/abandon remains best-effort.

Allowed files:

- `dayu/fins/ingestion/wait_adapter.py`
- `dayu/fins/ingestion_runtime.py` only for docstring or typed return clarification required by the mapping below.
- `tests/fins/test_fins_ingestion_tools.py`
- `tests/fins/test_fins_ingestion_runtime.py`
- `tests/host/test_wait_adapter_polling.py` only if a Fins-like fake is needed for cross-boundary assertion.

Exact changes:

- Update `FinsIngestionWaitPollAdapter.abandon_wait(...)` to return `WaitExternalJobLifecycleResult`.
- Current Fins behavior should map as:
  - Valid observation handle: call `cancel_observation(handle)` then `abandon_observation(handle)`, return `WaitExternalJobLifecycleApplied(action=ABANDON, message=...)`. Do not return `CANCEL` for current Fins because the adapter also releases the local observation handle after requesting cooperative cancellation.
  - Corrupt / unparsable token: return `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`; do not call runtime.
  - Observation missing / runtime returns LOST: return `WaitExternalJobLifecycleNoop(reason="observation_missing")`, because there is no live local observation handle left to cancel or abandon.
  - Non-transient observation error during cancel or abandon: return `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`, where `<error_kind>` is the stable enum value. This records that Fins cleanup cannot do more for the current handle without making Host cancellation depend on provider cleanup.
  - `TRANSIENT_UNAVAILABLE`: re-raise so Host poller writes `ABANDON_ERROR` and retries.
- Do not expose Host wait ids, adapter keys, tool call ids, or observation handle ids in LLM-facing text. These may appear only in internal diagnostics/tests.
- If `ingestion_runtime.py` is touched, only clarify docstrings for `cancel_observation(...)` / `abandon_observation(...)`; do not change Fins durable job schema unless direct failing evidence requires it.

State transitions:

- Fins observation `PENDING` can become `CANCELLED` before activation.
- Submitted/running observation receives cooperative cancellation request and is removed from process-local observation registry by abandon.
- Fins durable job may still finish according to existing cooperative checkpoints; Host Run remains cancelled regardless.

Error handling:

- Fins runtime missing/corrupt handle and non-transient observation errors must not raise; they map to `WaitExternalJobLifecycleNoop` with the reasons specified above.
- Transient runtime unavailability remains retryable through Host poller backoff.
- Fins storage side effects already committed are not deleted by abandon.

Invariants:

- Fins adapter never writes Host EventLog or wait record directly.
- Fins adapter never treats observation handle / external job id as Host primary key.
- Fins adapter does not require all source-specific providers to support physical remote cancel.

Tests / validation:

- Update `test_fins_wait_poll_adapter_abandon_cancels_and_cleans_observation` to assert returned lifecycle result and existing cancel + abandon calls.
- Update corrupt token test to assert `WaitExternalJobLifecycleNoop(reason="invalid_observation_handle")`.
- Add missing observation / LOST test to assert `WaitExternalJobLifecycleNoop(reason="observation_missing")`.
- Add non-transient observation error test to assert `WaitExternalJobLifecycleNoop(reason="observation_error:<error_kind>")`; keep `TRANSIENT_UNAVAILABLE` test asserting re-raise and Host retry/backoff behavior.
- Add or update runtime test proving prepared observation cancel + abandon before activation still prevents submit and releases the local observation handle.
- Add or update runtime test proving abandon of running/submitted observation requests cooperative cancellation and removes local observation handle without deleting already durable job artifacts.

Completion signal:

- Fins focused tests pass.
- Host focused tests still pass after adapter protocol change.
- Pyright reports no new errors.

Stop condition:

- Stop if Fins requires provider-specific physical remote cancel APIs that do not exist in current runtime. That belongs to provider-specific follow-up under #92/#87, not this shared Host/Fins contract cleanup.

## Tests / Validation Commands And Expected Assertions

Required implementation validation:

```bash
source .venv/bin/activate && pytest tests/host/test_wait_cancel_late_result.py tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py
```

Expected assertions: WAITING cancel remains terminal; cancelled wait lifecycle applied / unsupported / no-op / exception paths are classified; late result still writes bounded diagnostic and never resumes.

```bash
source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py
```

Expected assertions: Fins adapter maps cancel + abandon to typed lifecycle result; corrupt token, missing observation, and non-transient observation errors return no-op with the specified reason; prepared observation cancel + abandon still prevents activation submit and releases the local handle; cooperative cancellation remains best-effort.

```bash
source .venv/bin/activate && pyright
```

Expected assertions: 0 new or expanded type errors. If touched files intersect existing pyright errors, implementation must fix the touched boundary rather than hide or ignore the error.

Optional implementation validation if `open_host` wiring is touched unexpectedly:

```bash
source .venv/bin/activate && pytest tests/host/test_open_host_runtime.py
```

Expected assertions: wait poller open / close lifecycle remains intact and no second runtime is introduced.

## Docs Decision

This plan artifact is the only document modified in plan gate.

For implementation gate:

- If `dayu/host/` code changes, implementer must first read `dayu/host/README.md` Agent update constraints and decide whether internal wait adapter lifecycle contract changes belong there.
- If `dayu/fins/` code changes, implementer must first read `dayu/fins/README.md` Agent update constraints and decide whether Fins observation lifecycle changes belong there.
- If tests change, implementer must first read `tests/README.md` Agent update constraints and decide whether test boundary updates are needed.
- Root `README.md` and `dayu/README.md` should not change unless implementation changes user-visible CLI / Web / Service workflow, install/init behavior, or layer boundaries. This plan expects no such change.

## Risks / Open Questions

Blocking open questions: none.

Residual risks:

- Some real providers may not support physical cancel. Owner/destination: provider-specific Fins/source adapter owners under GitHub issue #92 / #87; shared Host must represent `Unsupported` and keep cancellation correctness independent.
- Poller disabled deployments will not perform external lifecycle action until a production poller is configured. Owner/destination: Service/composition deployment and WU-WAIT-04 production-grade E2E smoke; Host correctness remains covered by durable cancel.
- Running Fins operations may only observe cooperative cancellation at checkpoints. Owner/destination: Fins provider/runtime owners; current WU records best-effort request and does not promise hard preemption.
- Tool trace projection may later want richer lifecycle diagnostics. Owner/destination: future tool trace / diagnostic projection work; current WU uses wait poll diagnostic fields and does not add new EventLog canonical facts.

## Completion Report Format

Implementation closeout must report:

1. Artifact path(s) created or updated.
2. Whether the implemented slice remained code-generation-ready or needed plan deviation.
3. Slice number and summary.
4. Validation commands run and observed results.
5. Blocking open questions, if any.
6. Residual risks / owners.
7. Whether files outside the approved slice were modified, with reason.
