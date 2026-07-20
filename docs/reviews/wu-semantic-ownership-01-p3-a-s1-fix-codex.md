# WU-SEMANTIC-OWNERSHIP-01 P3-A S1 fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 P3-A`
- Slice: `S1 fix`
- Gate: code review accepted findings fix only
- Agent: AgentCodex
- Artifact: `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`

本次只修复 controller adjudication 接受的 S1 findings，未实施 S2/S3 consumer migration，未 code review，未 commit / push，未进入 re-review gate。

## First-principles judgment

S1-F01 的动机成立，但 root cause 不是 durable Attempt terminal truth 错误。`AttemptStatus.SUSPENDED` 与 `AttemptStatus.STEERED` 仍然是 durable Attempt 终态；问题是 lifecycle event owner 缺少 Run / Attempt 联合 terminal closeout 支持子集，后续 S2 迁移者可能把所有 durable Attempt terminal status 都当成 closeout-supported status。

修复边界应落在 `dayu.host.lifecycle_events` 这个 Host lifecycle event type owner，而不是 S2/S3 producer、durable schema 或下游 projection。

## Changed files

- `dayu/host/lifecycle_events.py`
- `tests/host/test_lifecycle_events.py`
- `tests/host/test_state_schema.py`
- `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`

`dayu/host/durable/state.py` 本次 fix 未继续修改；当前工作区中该文件已有 S1 implementation 变更。

## Fixed findings

### S1-F01 - fixed

- Added `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES`.
- Added `closeout_attempt_terminal_event_type_for_status(status)`.
- Kept `attempt_terminal_event_type_for_status(status)` as the durable terminal helper covering `SUCCEEDED / FAILED / CANCELLED / SUSPENDED / STEERED / LOST`.
- Made `SUSPENDED` and `STEERED` explicit durable terminal event types but excluded them from the closeout-supported subset.
- Added tests proving `SUSPENDED` and `STEERED` map through the durable helper and fail-fast through the closeout helper.

### S1-F02 - fixed

- Added explicit tests named `test_is_terminal_run_status_covers_all_members` and `test_is_terminal_attempt_status_covers_all_members`.
- The predicate coverage no longer depends on tests whose names only describe row-rule derivation.

### S1-F03 - fixed

- Added focused assertion for `serialized_run_status_values(frozenset({RunStatus.LOST, RunStatus.SUCCEEDED}))`.
- The test now proves unordered `frozenset` input is serialized in `RunStatus` definition order.

### S1-F04 - fixed

- Updated `lifecycle_events.py` module docstring to include Host Attempt terminal event type ownership and closeout-supported subset ownership.
- Clarified `HostAttemptEventType` is terminal-only for P3-A and non-terminal Attempt event ownership remains outside this slice.
- Clarified `HOST_ATTEMPT_TERMINAL_EVENT_TYPES` includes durable terminal events that are not all closeout-supported.

## Propagation audit

- Durable Attempt terminal fact owner: `dayu.host.lifecycle_events.HostAttemptEventType` and `HOST_ATTEMPT_TERMINAL_EVENT_TYPES` now represent all durable Attempt terminal event types, including `ATTEMPT_SUSPENDED` and `ATTEMPT_STEERED`.
- Closeout-supported subset owner: `CLOSEOUT_SUPPORTED_ATTEMPT_TERMINAL_EVENT_TYPES` and `closeout_attempt_terminal_event_type_for_status` define the only Attempt terminal statuses S2 may feed into Run / Attempt joint terminal closeout.
- Durable status truth remains in `dayu.host.durable.state.TERMINAL_ATTEMPT_STATUSES`, derived from row rules; no schema or producer migration was required.
- Tests prevent S2 from accidentally treating `SUSPENDED` or `STEERED` as closeout-supported while preserving their durable terminal status.

## README decision

- Read `dayu/host/README.md`: no update needed because this fix adds internal owner helpers and tests only; it does not change public Host behavior, durable schema, documented execution path, or Service-facing contract.
- Read `tests/README.md`: no update needed because `tests/host/test_lifecycle_events.py` and `tests/host/test_state_schema.py` remain within the existing Host owner-level test scope.

## Validation

```text
source .venv/bin/activate && pytest tests/host/test_lifecycle_events.py tests/host/test_state_schema.py -q
  -> 59 passed in 0.55s

source .venv/bin/activate && python -c "from dayu.host.lifecycle_events import HostRunEventType, HostAttemptEventType, run_terminal_event_type_for_status, attempt_terminal_event_type_for_status; import dayu.host.durable.state; import dayu.host.durable.run_transition; import dayu.host.engine_ingest; print('import-ok')"
  -> import-ok

source .venv/bin/activate && pyright
  -> 0 errors, 0 warnings, 0 informations

git diff --check
  -> passed
```

## Residual risks / next handoff

- Covered by later approved slice: S2 still needs to migrate terminal event consumers in `run_transition.py` / `engine_ingest.py` to use lifecycle event owner helpers. S2 must use the closeout-supported Attempt helper for joint terminal closeout paths and keep `SUSPENDED` / `STEERED` on their waiting / steer-specific lifecycle routes.
- Covered by later approved slice: S2 still needs to migrate remaining SQL/status consumers to durable state owner helpers.
- No S1 accepted finding remains intentionally deferred by this fix.

## Completion report

- status: completed
- changed files: `dayu/host/lifecycle_events.py`, `tests/host/test_lifecycle_events.py`, `tests/host/test_state_schema.py`, `docs/reviews/wu-semantic-ownership-01-p3-a-s1-fix-codex.md`
- fixed findings: S1-F01, S1-F02, S1-F03, S1-F04
- next handoff: S1 re-review gate, if the controller chooses to proceed
