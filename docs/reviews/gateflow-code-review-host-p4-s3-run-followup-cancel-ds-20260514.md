# Gateflow Code Review Artifact: Host P4-S3 Run Follow-up Cancel (Adversarial)

- gate: Phase 4 implementation
- slice: P4-S3 Run Admission, Follow-up Queue, Cancel Run And Cancel Session Runs Subset
- review type: independent adversarial review (not AgentMiMo)
- baseline: P4-S2 accepted slice commit `190d905`
- accepted plan: `docs/host/phase4-public-api-command-path-plan.md` Slice P4-S3
- design truth: `docs/host/design.md`
- implementation artifact: `docs/reviews/gateflow-implementation-host-p4-s3-run-followup-cancel-20260514.md`
- status: accepted / no blocking finding

## 1. Scope Enforcement

### P4-S4 read/event stream residual check

- `dayu/host/command.py`: No `get_run` or `stream_run_events` function definition or export. `__all__` excludes both. `cancel_run` return path uses `run_snapshot_from_row` for snapshot construction, which is a narrow durable row→snapshot helper in `state.py`, not a public read facade.
- `dayu/host/__init__.py`: Exports `start_run`, `submit_followup`, `cancel_run`, `cancel_session_runs`. No `get_run` or `stream_run_events` in imports or `__all__`.
- `dayu/host/command.py` grep: `get_run` only appears in `target_run_id` field name in `submit_followup` and `_submit_followup_public_semantic_digest`; `stream_run_events` does not appear.

**Conclusion**: P4-S3 scope is clean. Zero P4-S4 read/event stream residual. No blocking finding.

## 2. Public Facade Correctness

### 2.1 `start_run(host, request) -> RunSnapshot`

`command.py:281-294`: Delegates to `HostAdmissionService.start_run()` with semantic digest computed from `_start_run_public_semantic_digest(request)` that includes session_id, input_digest, execution_target, queue_policy, and call_context_digest. Returns `run_snapshot_from_row(result.run)`. Supports all admission policies (direct running, queue, reject, attach_active) through existing internal admission.

### 2.2 `submit_followup(host, session_id, request) -> FollowupSnapshot`

`command.py:297-343`:
- Validates `session_id == request.session_id` → `INVALID_STATE` on mismatch
- `behavior=STEER` → `UNSUPPORTED_OPERATION`, `retryable=False`, no EventLog append
- `behavior=QUEUE` → delegates to `HostAdmissionService.submit_followup_queue()`
- `FollowupSnapshot` construction correctly sets `queued_run_id` to `accepted_run_id` only when `accepted_run_status == QUEUED`, otherwise `None`
- `behavior` always `QUEUE` in snapshot (steer never reaches this path)
- `target_run_id` always `None`

### 2.3 `cancel_run(host, run_id, request) -> RunSnapshot`

`command.py:346-377`:
- Delegates to `HostAdmissionService.cancel_run()`
- Intercepts `INVALID_STATE` errors and runs deferred state check via `_is_deferred_cancel_state()` in a separate read transaction
- Only converts genuinely deferred states (`WAITING`, `CANCELLING`, `RECOVERING`, and dispatch-past-pre-dispatch `RUNNING`) to `UNSUPPORTED_OPERATION`
- `NOT_FOUND` passes through unchanged (code check is `INVALID_STATE`)
- Terminal and other invalid states remain `INVALID_STATE`
- Idempotency replay returns latest durable snapshot

### 2.4 `cancel_session_runs(host, session_id, request) -> SessionSnapshot`

`command.py:380-406`: Delegates to `HostAdmissionService.cancel_session_runs()` with semantic digest. Returns `result.snapshot`.

**Conclusion**: Public facade request/session id/digest/idempotency behavior matches plan. No blocking finding.

## 3. submit_followup Execution Target Analysis

`command.py:82`: `_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"`

Used at `command.py:326-329` as `resolved_execution_target` in `SubmitFollowupQueueAdmissionInput`.

**Analysis**:
- `SubmitFollowupRequest` has no public `resolved_execution_target` field; `start_run` path carries `request.execution_target` explicitly.
- No policy provider integration exists in current Phase 4 scope.
- The constant is module-level (not scattered literal), is named, and is semantically clear.
- Both the implementation artifact and Host README explicitly document this as a residual risk with a planned policy-provider replacement path.
- The string is stored as execution_target in durable Run rows, making it observable and replaceable when policy provider integration lands.

**Judgment**: Acceptable residual risk for P4-S3. Not a design gap — it's a knowingly deferred policy resolution concern with a visible placeholder constant. The plan's P4-S3 stop conditions do not trigger on this item. Non-blocking.

## 4. cancel_run Deferred State Mapping

`command.py:683-719` (`_is_deferred_cancel_state`):

| Durable state | Internal admission result | `_is_deferred_cancel_state` | Public error |
|---|---|---|---|
| `NOT_FOUND` (run missing) | `NOT_FOUND` | `False` (run is None → return False) | `NOT_FOUND` ✅ |
| `QUEUED` | Handled internally, returns `CANCELLED` | Not reached | N/A ✅ |
| `RUNNING` + pre-dispatch `STARTING` | Handled internally, returns `CANCELLED` | Not reached | N/A ✅ |
| `RUNNING` + dispatch NOT pre-dispatch | `INVALID_STATE` | `True` (status RUNNING, not pre-dispatch) | `UNSUPPORTED_OPERATION` ✅ |
| `WAITING` | `INVALID_STATE` | `True` | `UNSUPPORTED_OPERATION` ✅ |
| `CANCELLING` | `INVALID_STATE` | `True` | `UNSUPPORTED_OPERATION` ✅ |
| `RECOVERING` | `INVALID_STATE` | `True` | `UNSUPPORTED_OPERATION` ✅ |
| Terminal (`SUCCEEDED`, `FAILED`, `LOST`, `CANCELLED`) | `INVALID_STATE` | `False` (not in WAITING/CANCELLING/RECOVERING, not RUNNING) | `INVALID_STATE` ✅ |

The mapping correctly preserves:
- True `NOT_FOUND` as `NOT_FOUND`
- Terminal invalid preconditions as `INVALID_STATE`
- Only genuinely deferred states convert to `UNSUPPORTED_OPERATION`

There is a minor TOCTOU window between the failed internal cancel (write transaction) and `_is_deferred_cancel_state` (read transaction), but the error mapping is conservative: a false negative (deferred state changed to terminal) re-raises `INVALID_STATE` which is acceptable; a false positive (terminal state changed to deferred) is effectively impossible in practice. No blocking finding.

## 5. cancel_session_runs Atomicity

`admission.py:1081-1136` (`_CancelSessionRunsOperation.__call__`):

Execution order within single `run_write` transaction:
1. Compute semantic digest, idempotency scope
2. Check existing idempotency record → replay if found
3. Read Session (validation)
4. **`_read_supported_targets_or_raise(transaction)`** — walks all non-terminal runs, calls `_session_cancel_target_for_run` for each
5. If ANY run is unsupported → `raise HostApiError(UNSUPPORTED_OPERATION)` **before any cancel fact is appended**
6. Only if ALL runs are in supported subset → iterate targets and cancel each

Because steps 4–6 occur within the same write transaction, and the check-before-mutate pattern raises before any `cancel_queued_in_transaction` or `cancel_predispatch_starting_in_transaction` call:

- Zero EventLog append when unsupported non-terminal exists ✅
- Zero state mutation when unsupported non-terminal exists ✅
- Zero partial cancel ✅

`test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation` (`tests/host/test_public_cancel_session_runs.py:262-287`) confirms this: marks an active attempt as `RUNNING` (simulating Phase 5), verifies queued runs remain untouched after `UNSUPPORTED_OPERATION`, and verifies EventLog count unchanged.

No blocking finding.

## 6. cancel_session_runs Idempotent Replay

### 6.1 Scope

`admission.py:1094-1098`: Idempotency scope is `(operation="cancel_session_runs", scope_id=session_id, idempotency_key=request.client_request_id)`. Matches plan. ✅

### 6.2 Semantic digest excludes dynamic run list

`admission.py:2181-2206` (`_cancel_session_runs_semantic_digest`): Digest includes `session_id`, `reason`, `mode`, `caller_semantic_digest`, and `call_context_digest`. Does NOT include current run list. ✅

### 6.3 Same key replay does not cancel post-first-operation runs

`admission.py:1768-1800` (`_idempotent_session_cancel_result`): Reads current Session snapshot from durable truth. Returns `cancelled_run_count=0`. Does not iterate or cancel any runs.

`test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run` confirms this: after first `cancel_session_runs`, a new `submit_followup` creates a RUNNING run, and replay returns the running run as active without cancelling it. ✅

### 6.4 Empty supported set creates idempotency without cancel events

When targets is empty (`_read_supported_targets_or_raise` returns empty tuple):
- `first_cancel_event_id` remains `None`
- `idempotency_store.record_idempotent_result(..., created_event_id=None, created_event_sequence=None)`
- No cancel events appended

`test_cancel_session_runs_no_supported_run_records_idempotency_without_event` confirms: EventLog count unchanged, consecutive calls with same key return identical snapshot. ✅

No blocking finding.

## 7. cancel_session_runs Does Not Trigger Queue Promotion

`admission.py:501-535` (`HostAdmissionService.cancel_session_runs`):
- Calls `self.transaction_runner.run_write(_CancelSessionRunsOperation(...))`
- Returns result directly — **no call to `_promote_after_release`**

Compare with `cancel_run` (`admission.py:453-499`) which DOES call `_promote_after_release(service=self, session_id=result.run.session_id)` when `result.released_active_slot is True`.

The transaction body (`_CancelSessionRunsOperation.__call__`) cancels pre-dispatch `STARTING` active runs (which frees the active slot internally through state mutation), but the outer service method does not trigger promotion after the transaction commits. This matches the plan's requirement: "Do not trigger queue promotion during session-scope cancel; the operation is cancelling the session's current non-terminal subset, not freeing a slot to start more work." ✅

No blocking finding.

## 8. State Helper Narrowness

### 8.1 `read_non_terminal_runs_for_session`

`state.py:826-878`: Pure data access:
- Reads `QUEUED`, `RUNNING`, `WAITING`, `CANCELLING`, `RECOVERING` rows for a session
- Returns `tuple[RunRow, ...]` ordered by `accepted_event_sequence ASC, run_id ASC`
- No command facade semantics, no projection truth, no policy decisions

The caller (`_CancelSessionRunsOperation._read_supported_targets_or_raise`) interprets which runs are in the Phase 4 supported subset. The state helper only provides raw data. ✅

### 8.2 `run_snapshot_from_row`

`state.py:1814-1832`: Pure data conversion:
- Maps `RunRow` → `RunSnapshot`
- Sets `terminal_result_summary=None` (terminal summary extraction is P4-S4 concern)
- Sets `outbox_summary=None` (outbox projection is not implemented)
- Computes `event_cursor` from `_run_event_cursor(run)` which takes max of all known event sequences

Does NOT read attempt, dispatch, or EventLog rows. Does NOT carry command facade semantics. ✅

No blocking finding.

## 9. Test Sufficiency for API-level Race Conditions

`tests/host/test_public_run_api.py:371-429` (`test_public_cancel_and_promotion_race_preserves_run_invariants`):
- Creates two handles pointing to the same DB (`create_host_command_handle(options)`)
- Submits cancel_active and cancel_queued concurrently via `ThreadPoolExecutor`
- Each thread creates its own handle (simulating multi-process access through SQLite)
- Asserts both cancellations succeed and durable state reflects `CANCELLED` for both runs
- This is a proper API-level race test, not merely reusing internal durable tests

`tests/host/test_public_cancel_session_runs.py`:
- `test_cancel_session_runs_cancels_queued_and_predispatch_subset`: Verifies cross-session isolation (other session's run unaffected)
- `test_cancel_session_runs_idempotent_replay_does_not_cancel_new_run`: Verifies idempotency boundary
- `test_cancel_session_runs_unsupported_non_terminal_has_no_partial_mutation`: Verifies atomicity
- `test_cancel_session_runs_no_supported_run_records_idempotency_without_event`: Verifies empty-set idempotency

Sufficient coverage for API-level cancel/promotion race and session-scope cancel semantics. No blocking finding.

## 10. Subsequent Phase Reminders

| Location | Content |
|---|---|
| `dayu/host/command.py:387-389` (cancel_session_runs docstring) | "Phase 4 只覆盖 queued 与 pre-dispatch STARTING；dispatching / active worker、WAITING、RECOVERING 分别由 Phase 5、Phase 7、Phase 11 负责。" |
| `dayu/host/admission.py:507-511` (cancel_session_runs docstring) | "本方法只取消 queued Run 与 pre-dispatch STARTING Run；dispatching / active worker、WAITING 与 RECOVERING 由后续 phase 负责。" |
| `dayu/host/README.md:40` | "dispatching / active worker、WAITING、RECOVERING 等后续 owner 能力映射为 UNSUPPORTED_OPERATION" |
| `dayu/host/README.md:55` | "Phase 5 负责 dispatching / active worker cancel，Phase 7 负责 WAITING cancel，Phase 11 负责 RECOVERING cancel。" |
| `dayu/host/README.md:127` | "当前未实现：... dispatching / active worker cancel propagation、wait cancellation、recovery classifier" |

All locations clearly state Phase 5/7/11 ownership. ✅

No blocking finding.

## 11. Code Quality: Docstrings, Types, Anti-patterns

### 11.1 Chinese docstrings

- All new public functions in `command.py` have complete Chinese docstrings with params, returns, raises ✅
- All new private functions in `command.py` have Chinese docstrings ✅
- All new functions in `admission.py` have Chinese docstrings ✅
- All new functions in `state.py` have Chinese docstrings ✅
- New dataclasses (`_SupportedSessionCancelTarget`, `_CancelSessionRunsOperation`, `SessionCancelResult`, `_IsDeferredCancelStateOperation`) have Chinese docstrings ✅

### 11.2 Strict typing

- No `Any`, `object`, untyped parameters or returns in new code ✅
- No untyped generics ✅
- pyright: 0 errors, 0 warnings, 0 informations ✅

### 11.3 hasattr / getattr

- `command.py`: Zero occurrences ✅
- `admission.py`: Zero occurrences ✅

### 11.4 Magic strings

- `_PUBLIC_FOLLOWUP_DEFAULT_EXECUTION_TARGET = "host-public-followup-default"` — module-level named constant ✅
- All operation names (`_OPERATION_START_RUN`, etc.) are module-level constants ✅
- Digest field names are inline literals but are schema-defining JSON keys (per CLAUDE.md: "工具 schema 例外，schema 内允许直接写字面量字符串") ✅

### 11.5 Compatibility wrappers / god bags

- No compatibility re-exports ✅
- No compatibility wrappers/facades ✅
- No god dataclass, god function, or god bag ✅

### 11.6 Reverse dependencies

- No imports from `dayu.engine`, `dayu.fins`, `dayu.service`, `dayu.ui` ✅
- `command.py` depends on `admission.py` (correct: facade → internal service) ✅
- `admission.py` depends on `durable/state.py`, `durable/run_transition.py`, etc. (correct: internal service → durable foundation) ✅

No blocking finding.

## 12. README Accuracy

### 12.1 Host README

- States Run command facade covers only "Phase 1-3 admission 可闭环路径" ✅
- Documents `cancel_session_runs` as Phase 4 subset with explicit Phase 5/7/11 ownership ✅
- Notes `submit_followup(queue)` default execution target limitation ✅
- Lists deferred items without claiming final cancel semantics ✅
- No "未来设计" or speculative claims ✅

### 12.2 Tests README

- Describes current test layers factually ✅
- Mentions "public run API" coverage accurately ✅
- Does not overstate Phase 4 cancel as final semantics ✅

No blocking finding.

## 13. Non-blocking Observations

### 13.1 `_input_digest` duplication

`command.py:893-906` and `admission.py:2246-2259` have identical `_input_digest` implementations. This is architecturally intentional (public facade and internal service maintain independent digest computation boundaries), and the duplication is only ~6 lines of immutable logic. The layer separation constraint outweighs DRY for this small helper. Not a bug, not a risk.

### 13.2 TOCTOU in cancel_run deferred state check

`cancel_run` uses a separate read transaction for `_is_deferred_cancel_state` after the internal admission write transaction rolls back/commits. The theoretical worst case is a false negative (deferred run became terminal between cancel failure and check), which results in the original `INVALID_STATE` being re-raised — an acceptable error. A false positive would require a terminal run to transition back to a non-terminal deferred state, which is architecturally impossible. No practical risk.

## 14. Validation Results

```
source .venv/bin/activate && pytest tests/host/test_public_run_api.py tests/host/test_public_cancel_session_runs.py tests/host/test_admission_queue.py tests/host/test_admission_multiprocess.py -q
→ 37 passed

source .venv/bin/activate && python -m pyright dayu/host tests/host
→ 0 errors, 0 warnings, 0 informations

git diff --check
→ clean
```

## 15. Conclusion

**accepted / no blocking finding**

The P4-S3 implementation is clean, well-scoped, and correctly implements the plan. Scope enforcement is strict (zero P4-S4 residual). Public facade idempotency, digest, and error mapping behaviors match the plan. `cancel_session_runs` atomicity, idempotent replay, and no-promotion invariants are all verified. State helpers are narrow. Tests cover API-level races. Phase reminders are present in code and README. All type checks, tests, and diff format pass.

Blocking findings: 0
