# Phase 15 Slice P15-S5 Code Review Artifact

## Gate / Scope

- Gate: Phase 15 Slice P15-S5 code review (AgentDS).
- Approved plan: `docs/host/phase15-retention-purge-production-hardening-plan.md` Slice P15-S5.
- Implementation artifact: `docs/reviews/phase15-s5-implementation-codex-20260529.md`.
- Output artifact: `docs/reviews/phase15-s5-code-review-ds-20260529.md`.
- Role: review only; no code changes, no commit, no push, no PR.

## Changed Files Audit

| File | Change | Lines |
| --- | --- | --- |
| `dayu/host/durable/projection.py` | Added `ProjectionResetResult`, `reset_projection_refs_for_deleted_events`, 5 private helpers | +192 |
| `dayu/host/durable/purge.py` | Replaced 4 purge-local private helpers with 1 call to new projection owner helper; removed unused imports | +8 / -86 |
| `dayu/host/recovery.py` | Added Session row existence recheck in `_classify_run` | +3 |
| `dayu/host/dispatch.py` | Added Session checks in `_read_startable_run` and `_is_dispatchable_recheck` | +11 |
| `tests/host/test_projection_checkpoint.py` | Added 2 helper tests for rebuildable-only checkpoint/failure reset | +123 |
| `tests/host/test_projection_read_model.py` | Added 1 rebuild test: purge + repair excludes purged Session, preserves others | +193 |
| `tests/host/test_recovery_scan.py` | Added 1 missing-Session guard test + 2 helpers | +78 |
| `tests/host/test_purge_session.py` | Added 1 independent-process multiprocess smoke test + protocol/helpers | +185 |

## Review Findings

Findings ordered by severity (no blocker).

---

### Finding 1 [PASS] projection reset helper: caller-provided EventLog ids only, rebuildable consumers only, projection not used as truth

**Checked**: `dayu/host/durable/projection.py:357-411` — `reset_projection_refs_for_deleted_events`.

**Evidence**:

1. The public helper accepts `event_ids: tuple[str, ...]` — these are **caller-provided** (from purge's own EventLog scan of the target Session), never read from projection tables.
2. The `rebuildable_consumer_ids` parameter is an allow-list of consumer identities (string constants), not derived from projection data.
3. Before any DELETE is executed, `_raise_for_unsupported_projection_reset_refs` queries BOTH `host_projection_checkpoints` AND `host_projection_failures` for any non-whitelisted consumer referencing the target EventLog ids, and raises `HostDurableError` if found (projection.py:380-392).
4. Only after passing the allow-list check does `_delete_allowed_projection_reset_refs` execute the DELETE with `consumer_id IN (rebuildable_consumer_ids)` guard (projection.py:394-411).
5. The docstring explicitly states: "调用方必须已经用 Session / Run / Attempt / EventLog 真源完成 purge 前置判定。本 helper 只精确处理传入 EventLog ids 上的 projection-local rows，并拒绝不在白名单内的 consumer，避免把 projection cursor 当成治理事实。"

**Conclusion**: The helper cleanly separates concerns — it processes projection rows but never decides purge eligibility. Purge precondition truth remains in Session/Run/Attempt/EventLog governance rows. The allow-list/reject-before-delete pattern prevents non-rebuildable consumers from being reset accidentally.

---

### Finding 2 [PASS] purge.py migration: clean ownership transfer, no precondition truth change

**Checked**: `dayu/host/durable/purge.py:1444-1450` — `_delete_session_matrix` projection reset call site.

**Evidence**:

1. Four private helper calls removed: `_raise_for_unsupported_projection_reset_refs(checkpoints)`, `_raise_for_unsupported_projection_reset_refs(failures)`, `_delete_allowed_projection_reset_refs(checkpoints)`, `_delete_allowed_projection_reset_refs(failures)`.
2. Replaced with single call to `reset_projection_refs_for_deleted_events(transaction, event_ids=event_ids, rebuildable_consumer_ids=_PURGE_REBUILDABLE_PROJECTION_CONSUMER_IDS)`.
3. The `event_ids` tuple is the same one collected earlier from `_collect_event_log_refs` — derived from the target Session's EventLog governance rows, not projection data.
4. The rebuildable consumer IDs are: `host.minimal-read-model`, `host.memory.session.v1`, `host.audit-log-jsonl`, `host.tool-trace`, `host.outbox-terminal` (purge.py:131-137). These match the plan's allowed set.
5. Deleted counts flow through `projection_reset.deleted_checkpoints` / `projection_reset.deleted_failures` → `PurgeDeleteCounts` → tombstone (purge.py:1498-1499).
6. Removed unused imports `TABLE_HOST_PROJECTION_CHECKPOINTS` and `TABLE_HOST_PROJECTION_FAILURES` from purge.py (lines 46-47 removed).
7. Removed 66 lines of private helpers (`_raise_for_unsupported_projection_reset_refs`, `_delete_allowed_projection_reset_refs`) whose SQL logic is now the responsibility of projection.py.

**Conclusion**: Clean migration. Purge precondition truth (Session closed, all Runs terminal, no active waits) is unchanged. The projection helper is called after governance truth checks are complete, as a consumer of already-collected EventLog ids.

---

### Finding 3 [PASS] minimal read model rebuild: excludes purged Session, preserves other Sessions

**Checked**: `tests/host/test_projection_read_model.py:1080-1173` — `test_rebuild_after_purge_replays_remaining_eventlog_only`.

**Evidence**:

1. Creates two Sessions: `purged_session_id` and `preserved_session_id`, each with one Run, terminal events, and terminal Run governance status.
2. Both are closed and initial read models are built.
3. `purge_session` deletes the purged Session's EventLog, state, projection, and read model rows.
4. All minimal read model rows (both sessions) are deleted, and the projection checkpoint is cleared — simulating a worst-case rebuild.
5. `repair_minimal_read_models` replays from remaining EventLog rows.
6. Assertions:
   - `repair.failures == 0` — repair succeeds cleanly
   - `purged_result is None` — purged Session's RunResult is NOT rebuilt
   - `purged_timeline == ()` — purged Session's timeline is empty
   - `preserved_result is not None` and `preserved_result.run_id == preserved_run.run_id` — preserved Session's data is correctly rebuilt
   - `preserved_texts == ("preserved input",)` — preserved Session's user input is recovered

**Conclusion**: The rebuild correctly excludes purged Session data (whose EventLog rows are gone) and correctly rebuilds preserved Session data from remaining EventLog. This directly proves the plan assertion: "Rebuild from remaining EventLog excludes purged Session and preserves other Sessions."

---

### Finding 4 [PASS] recovery missing-Session guard: prevents reanimation, no state machine change

**Checked**: `dayu/host/recovery.py:242-243` — `_classify_run` early return.

**Evidence**:

1. Guard inserted at the **entry point** of `_classify_run`, before any status classification, queue promotion, or pending dispatch registration.
2. `read_session_by_id(transaction, run.session_id) is None` → returns `StartupRecoveryDecision.NOT_FOUND` with reason `"session_missing"`.
3. No run status mutation, no EventLog append, no queue promotion side effects.
4. All `read_non_terminal_runs` results pass through this guard — covers ACCEPTED, QUEUED, WAITING, RUNNING, CANCELLING, RECOVERING Run statuses uniformly.
5. Test `test_scan_skips_non_terminal_run_when_session_row_is_missing` (test_recovery_scan.py:316-343) proves:
   - Decision is `NOT_FOUND`, reason is `"session_missing"`
   - Run status remains `RUNNING` (not mutated to LOST or RECOVERING)
   - No `ATTEMPT_LOST` events created
   - No `RUN_RECOVERING` events created
6. The test uses `PRAGMA foreign_keys=OFF` + direct Session/Slot deletion to simulate the anomalous residual-Run scenario that the guard is designed to harden against. This is a valid defensive test pattern for a scenario that normal purge (with FK ON) would prevent.

**Conclusion**: Narrow guard at the right layer. No recovery state machine changes. The `NOT_FOUND` decision prevents `execute_actions` from creating recovery facts. Does not change `StartupRecoveryScanner.scan()` contract or `StartupRecoveryPolicy` semantics.

---

### Finding 5 [PASS] dispatch missing-Session guard: two checkpoints, no state machine change

**Checked**: `dayu/host/dispatch.py:3167-3168` (`_read_startable_run`) and `dayu/host/dispatch.py:2166-2169` + `dayu/host/dispatch.py:3082` (`_is_dispatchable_recheck`).

**Evidence**:

1. **Guard 1 — queue promotion candidate read** (`_read_startable_run`, line 3167):
   - `read_session_by_id(transaction, session_id) is None` → returns `None`
   - Session check happens before any Run query, so no accepted/queued Run is returned for a missing Session
   - One caller (`_promote_earliest_startable`, line 890), correctly handles `None` return

2. **Guard 2 — lane-acquired dispatch recheck** (`_is_dispatchable_recheck`, line 3082):
   - New `session_exists: bool` parameter added
   - Checked alongside existing `run is not None`, `attempt is not None`, `dispatch_record is not None` in the recheck conjunction
   - Computed at the call site (line 2166-2169): `run is not None and read_session_by_id(transaction, run.session_id) is not None`
   - One caller (`_try_dispatch_after_lane`, line 2170), correctly propagates to the recheck

3. Both guards are **before** state mutation:
   - Guard 1 prevents queue promotion (no `mark_queued_after_lane_row` call)
   - Guard 2 prevents dispatching mark (no `mark_dispatching_after_lane_row` call)

4. No new public parameters, no dispatch state machine changes, no `HostDispatchScheduler` API changes.

**Conclusion**: Two narrow, correctly placed Session-existence rechecks. They prevent dispatch from operating on purged Session residual Run rows without changing the dispatch state machine.

---

### Finding 6 [PASS] local multiprocess smoke: independent processes, separate SQLite connections

**Checked**: `tests/host/test_purge_session.py:2918-2962` — `test_public_purge_is_observed_by_independent_process_read_paths`.

**Evidence**:

1. Uses `multiprocessing.Process` — each process is an independent Python interpreter, not a thread or same-process handle.
2. Process A (`_purge_in_independent_process`): opens its own `open_host(options)` → calls `purge_session(session_id, request)` → writes result JSON to `purge_marker`.
3. Process B (`_read_after_purge_in_independent_process`): opens its own `open_host(options)` → tests `get_session`, `get_run`, `retry_run`, `replay_run`, `watch_session_events` → writes observed error codes to `read_marker`.
4. Each process creates a separate SQLite connection via `open_host()` — the underlying `open_host_durable_store` creates independent file connections.
5. Process A is joined before Process B starts — ensures purge transaction is committed and visible to Process B.
6. Assertions:
   - `purge_result["purged"] is True` — purge succeeded
   - `purge_result["tombstone_ref"]` is a string — tombstone created
   - All 5 read paths in Process B return `NOT_FOUND` — fail-closed behavior confirmed
7. No remote worker, no wire protocol, no same-process multi-handle. Uses `allow_tool_calls=False` and `deterministic_runner_spec` to keep the test focused.

**Conclusion**: Genuinely independent-process smoke with separate SQLite connections. Verifies the plan requirement: "actual local multiprocess read/replay/watch after purge returns not_found/conflict as designed."

---

### Finding 7 [PASS] pyright and test results

**Command**: `pytest tests/host/test_projection_checkpoint.py tests/host/test_projection_runner.py tests/host/test_projection_read_model.py tests/host/test_recovery_scan.py tests/host/test_recovery_multiprocess.py tests/host/test_admission_multiprocess.py tests/host/test_purge_session.py -q`

**Result**: `74 passed in 6.01s`

**Command**: `python -m pyright dayu/host tests/host`

**Result**: `0 errors, 0 warnings, 0 informations`

---

### Finding 8 [INFO] README decision: correct deferral to S6

**Evidence**: P15-S5 changes are local hardening and tests. They do not change user-facing commands, public API shape, `OpenHostOptions`, configuration, or stable Host architecture text. The plan explicitly assigns documentation updates for implemented purge semantics to P15-S6. The implementation artifact correctly states this rationale.

**Conclusion**: Not implementing S6 docs in P15-S5 is correct and plan-compliant.

---

### Finding 9 [INFO] `_in_clause` / `_placeholders` code duplication between projection.py and purge.py

**Evidence**: Both modules have module-private copies of `_in_clause` and `_placeholders`. Projection.py's versions accept `tuple[str, ...]` (since event_ids and consumer_ids are always strings). Purge.py's versions accept `tuple[str | int, ...]` (since it also handles event_sequences).

**Analysis**: This is architecturally correct. Projection.py is a durable module that should not import private helpers from purge.py. The type narrowing is appropriate for each module's use case. This is not code smell — it follows the project constraint "模块间依赖最小化".

**Conclusion**: No action needed.

---

### Finding 10 [MINOR] test docstring completeness

**Evidence**: New test functions have one-line Chinese docstrings:

```python
def test_reset_refs_for_deleted_events_deletes_only_rebuildable_consumers(
    tmp_path: Path,
) -> None:
    """projection reset 只删除引用目标 EventLog 的白名单 consumer rows。"""
```

**Analysis**: CLAUDE.md requires "完整中文 docstring，至少包含参数、返回值、异常". The new test docstrings are one-liners without explicit params/returns/raises sections. However, this is consistent with existing test patterns in the same files — some tests in `test_projection_checkpoint.py` have no docstrings at all (e.g., `test_failure_row_increments_and_clear_removes_it`). The new tests are an improvement over existing ones.

**Classification**: Minor, pre-existing inconsistency in the codebase, not introduced by S5.

---

### Finding 11 [PASS] no Engine / Service / UI / Fins / Remote changes

**Evidence**: Grep of `from dayu.(engine|service|ui|fins)` in changed production files returns no matches. Dispatch and recovery only import from `dayu.host.durable.state` (existing dependency). Projection.py only imports from `dayu.host.durable.schema` and `dayu.host.durable.transaction` (existing dependencies).

---

## Adversarial Failure Pass

### Pass 1: Can recovery reanimate purged Session facts?

**Scenario**: Non-terminal Run row exists but Session is purged. Recovery scanner reads non-terminal runs, encounters the orphan Run.

**Defense**: `_classify_run` returns `NOT_FOUND` with `session_missing` before any state mutation. No recovery/lost events are created. Run status remains unchanged. **Passed**.

### Pass 2: Can dispatch queue or promote a purged Session's Run?

**Scenario**: A queued Run exists for a purged Session. Dispatch scheduler reads `_read_startable_run`.

**Defense 1**: `_read_startable_run` checks `read_session_by_id` first and returns `None` — no queue promotion. **Passed**.

**Defense 2**: Even if a Run reached lane acquisition, `_is_dispatchable_recheck` requires `session_exists=True` — dispatch is skipped. **Passed**.

### Pass 3: Can projection checkpoint/failure reset be used to prove purge preconditions?

**Scenario**: A caller attempts to use `reset_projection_refs_for_deleted_events` to determine whether purge is allowed.

**Defense**: The helper only accepts `event_ids` and `rebuildable_consumer_ids` from the caller. It neither reads Session/Run/Attempt governance state nor returns any precondition information. Its only output is `ProjectionResetResult(deleted_checkpoints, deleted_failures)`. **Passed**.

### Pass 4: Can a non-rebuildable consumer's projection rows be deleted?

**Scenario**: A checkpoint row exists for `host.recovery-governance` (non-rebuildable) referencing a target EventLog id.

**Defense**: `_raise_for_unsupported_projection_reset_refs` queries for non-whitelisted consumers referencing target EventLog ids and raises `HostDurableError` before any DELETE executes. The test `test_reset_refs_for_deleted_events_rejects_non_rebuildable_consumer` proves the checkpoint row is preserved intact. **Passed**.

### Pass 5: Can minimal read model rebuild resurrect purged Session data?

**Scenario**: Read model rows deleted, rebuild triggered from remaining EventLog.

**Defense**: Purge deletes the target Session's EventLog rows. Rebuild scans remaining EventLog by `MIN(event_sequence)` ascending. Purged Session events are absent, so no RunResult or timeline items are created. The test `test_rebuild_after_purge_replays_remaining_eventlog_only` proves this. **Passed**.

### Pass 6: Can multiprocess test have same-process handles?

**Scenario**: Process A and Process B share the same Python process memory space.

**Defense**: `multiprocessing.Process` spawns independent Python interpreters. Each process creates its own `open_host()` → `open_host_durable_store` with separate SQLite `sqlite3.connect()`. No shared in-process state. **Passed**.

---

## Constraint Compliance

| Constraint | Status |
| --- | --- |
| 禁止修改 `dayu/engine/**` | PASS |
| 禁止修改 `dayu/service/**`, `dayu/ui/**`, `dayu/fins/**` | PASS |
| 禁止修改 RemoteProxy / RemoteStub / wire protocol | PASS |
| 禁止修改 `OpenHostOptions` 字段 | PASS |
| 禁止修改 Host public method shape | PASS |
| 禁止用 projection/audit/outbox/memory 证明 purge 前置条件 | PASS |
| 禁止新增 public error code | PASS (uses existing NOT_FOUND) |
| 中文 docstring（新增生产函数） | PASS |
| 禁止 `object` / `Any` / 无类型参数 | PASS |
| 禁止 `hasattr` / `getattr` 逃避类型 | PASS |
| 禁止魔法数字/字符串 | PASS (uses module constants) |
| 禁止反向依赖 | PASS |
| 模块间依赖最小化 | PASS |
| pyright 0 errors | PASS |
| 测试覆盖率（触及模块） | PASS (74 tests, focused coverage) |

---

## Residual Risks

| Risk | Classification | Owner |
| --- | --- | --- |
| RemoteProxy / RemoteStub multiprocess purge behavior | Out of scope, deferred | Issue 73 |
| Multiprocess race within purge transaction (no artificial sleeps in test) | Covered by SQLite transaction/CAS ordering; test asserts post-commit visibility | Accepted |
| Recovery test uses FK-disabled helper to create anomalous state — not a realistic purge scenario | Defensive hardening test, not standard purge path | Accepted |
| Test docstrings not fully meeting CLAUDE.md spec | Pre-existing inconsistency, not worsened by S5 | Deferred to S6 or separate cleanup |

---

## Overall Verdict

**PASS — NO BLOCKER**

All plan-required assertions are verified:
- Projection reset helper does not use projection as truth and only operates on caller-provided EventLog ids with rebuildable consumer allow-list.
- Purge.py migration is clean, precondition truth unchanged.
- Minimal read model rebuild from remaining EventLog correctly excludes purged Session and preserves other Sessions.
- Recovery guard prevents reanimation without changing the recovery state machine.
- Dispatch guards prevent queue promotion and dispatch for missing Sessions without state machine changes.
- Multiprocess smoke uses genuine independent processes with separate SQLite connections.
- No Engine, Remote, Service, UI, or Fins changes.
- Pyright 0 errors, 74 tests pass.
- README update correctly deferred to S6.

Ready for P15-S6 or controller closeout.
