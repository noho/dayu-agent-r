# PR 55 Deepreview: Host Phase 6 ToolRuntime governance

## Scope

- Mode: PR
- PR: 55, https://github.com/noho/dayu-agent-r/pull/55
- Title: Host Phase 6 ToolRuntime governance
- Author: noho
- Branch: `feat/host-phase-6-toolruntime`
- Base: `main`
- Output file: `docs/reviews/pr-55-deepreview-mimo-20260515.md`
- Included scope: 61 files changed, 14883 insertions, 94 deletions — Host Phase 6 ToolRuntime boundary implementation and Run-scoped duplicate governance fix
- Excluded scope: Engine code, Remote transport, business tool implementations, Phase 7+ capabilities
- Parallel review coverage: 无

## Design Truth And Control Docs

- `docs/host/design.md` — Phase 6 design write-back for run-scoped cursors, duplicate governance, ack timeout behavior, effective ToolBundle terminology
- `docs/host/implementation-control.md` — Phase 6 slice completion records, residual risk tracking
- `docs/reviews/host-phase6-aggregate-review-*.md` — aggregate review PASS
- `docs/reviews/host-phase6-aggregate-fix-run-local-duplicate-governance-20260515.md` — P6-AGG-F1 fix documentation
- `docs/reviews/host-phase6-aggregate-re-review-mimo-20260515.md` — re-review PASS after fix

## Commands And Files Inspected

- `gh pr view 55` — PR metadata
- `gh pr checks 55` — no checks reported (CI not configured for this branch)
- `git diff --stat main...HEAD` — 61 files changed, 14883 insertions, 94 deletions
- `git log --oneline main..HEAD` — 18 commits
- `source .venv/bin/activate && python -m pyright dayu/host tests/host` — 0 errors, 0 warnings, 0 informations
- `source .venv/bin/activate && pytest tests/host -q` — 349 passed in 4.45s
- `git diff --check` — clean

### Production code

- `dayu/host/tool_runtime.py` (NEW, ~4648 lines) — core ToolRuntime implementation
- `dayu/host/dispatch.py` (+151 lines) — scheduler tool-enabled wiring and cleanup
- `dayu/host/run_input.py` (+275 lines) — tool execution mode, same-source validation
- `dayu/host/api.py` (+21 lines) — HostLocalExecutionOptions tooling fields
- `dayu/host/README.md` — updated ToolRuntime boundary documentation
- `dayu/README.md` — updated architecture overview

### Test code

- `tests/host/test_toolruntime_effective_bundle.py` (NEW, 254 lines)
- `tests/host/test_toolruntime_accept_barrier.py` (NEW, 590 lines)
- `tests/host/test_toolruntime_executor.py` (NEW, 596 lines)
- `tests/host/test_toolruntime_truncation_fetch_more.py` (NEW, 556 lines)
- `tests/host/test_toolruntime_duplicate_governance.py` (NEW, 716 lines)
- `tests/host/test_toolruntime_diagnostics.py` (NEW, 449 lines)
- `tests/host/test_phase6_toolruntime_integration.py` (NEW, 853 lines)
- Modified: `tests/host/test_dispatch_scheduler.py`, `tests/host/test_run_input_builder.py`, `tests/host/test_engine_ingest_mapping.py`

### Docs

- `docs/host/design.md` — Phase 6 design write-back
- `docs/host/implementation-control.md` — slice completion records
- `docs/host/phase6-toolruntime-truncation-fetch-more-plan.md` (NEW, 699 lines)

## Required Checks

### 1. Run-scoped duplicate governance: same-Run sharing, cross-Run isolation

**PASS.**

- `InMemoryRunScopedDuplicateGovernanceRegistry.duplicate_governance_for_run()` (`tool_runtime.py:1665-1682`) looks up or creates `_RunLocalDuplicateGovernanceState` by `run_id` under `RLock`, passes it to `InMemoryRunLocalDuplicateGovernance(policy, state=state)`.
- Multiple calls with same `run_id` receive same state instance (`self._states_by_run_id.get(run_id)` at line 1678).
- `InMemoryRunLocalDuplicateGovernance.decide_duplicate()` reads via `self._state.find()` (`tool_runtime.py:1587`); `record_accepted()` writes via `self._state.record()` (`tool_runtime.py:1612`).
- `HostDispatchScheduler._run_input_builder_for_dispatch()` passes `self._duplicate_governance_registry` into `ToolRuntimeBuildRequest` (`dispatch.py:733`).
- `DefaultToolRuntimeFactory.create_tool_runtime()` calls `request.duplicate_governance_registry.duplicate_governance_for_run(...)` when registry provided (`tool_runtime.py:2600-2604`); falls back to instance-private governance when `None` (`tool_runtime.py:2606-2608`).
- Test `test_same_run_runtime_handles_share_duplicate_index` verifies same-Run sharing.
- Test `test_different_runs_do_not_share_duplicate_index` verifies cross-Run isolation.

### 2. No durable duplicate ledger or crash/restart recovery

**PASS.**

- `_RunLocalDuplicateGovernanceState` stores `_entries_by_key` in a plain `dict` in instance memory (`tool_runtime.py:1522`). No file, database, or durable storage.
- `InMemoryRunScopedDuplicateGovernanceRegistry` stores `_states_by_run_id` in a plain `dict` in instance memory (`tool_runtime.py:1663`). No durable storage.
- Protocol docstring: "不提供 durable ledger、跨进程恢复或重启恢复语义" (`tool_runtime.py:1058-1059`).
- Implementation docstring: "不写 durable ledger，不承诺进程崩溃、重启或跨进程恢复" (`tool_runtime.py:1652-1653`).

### 3. Scheduler owns/cleans registry without leaking unbounded Run state

**PASS.**

Three cleanup paths verified:

1. **Terminal closeout**: `_consume_worker_events()` sets `run_terminal_closed` flag when `_ingest_closed_run(result)` returns True (`dispatch.py:958, 971, 992, 1002`); `finally` block calls `self._duplicate_governance_registry.clear_run(record.run_id)` when flag is true (`dispatch.py:1005-1006`).
2. **Dispatch cancellation**: `_close_run()` calls `self._duplicate_governance_registry.clear_run(record.run_id)` (`dispatch.py:908`).
3. **Scheduler shutdown**: `close()` calls `self._duplicate_governance_registry.clear_all()` (`dispatch.py:468`).

`_ingest_closed_run()` helper (`dispatch.py:1016-1026`) correctly identifies terminal closeout: `result.terminal_closeout and result.status in (ACCEPTED, DUPLICATE)`.

Test `test_scheduler_uses_toolruntime_when_tooling_is_configured` asserts `active_run_count() == 1` after dispatch and `active_run_count() == 0` after `scheduler.close()`.

### 4. Same-source tool schema/executor wiring

**PASS.**

- `_validate_tool_enabled_snapshot()` (`run_input.py:1182-1209`) enforces:
  - `tool_snapshot.tool_runtime_handle` must not be None (line 1200-1201)
  - `tool_snapshot.tool_runtime_handle.tool_schemas` must be `tool_snapshot.tool_schemas` — identity check via `!=` (line 1202-1205)
  - `tool_snapshot.tool_runtime_handle.tool_executor` must be `tool_executor` — identity check via `is not` (line 1206-1209)
- `ToolRuntimeHandle` is constructed by `DefaultToolRuntimeFactory.create_tool_runtime()` which bundles schemas and executor from the same `EffectiveToolBundle` — single source of truth.
- Test `test_toolruntime_effective_bundle.py` verifies same-source construction.

### 5. No-tool mode guard

**PASS.**

- `ToolExecutionMode` enum (`run_input.py`) dispatches between `TOOL_ENABLED`, `NO_TOOL_REPLAY`, `NO_TOOL_DISABLED`.
- `PolicySnapshot.__post_init__` no longer rejects `allow_tool_calls=True` — tool-enabled mode is now valid.
- `_validate_tool_mode_snapshot()` dispatches to `_validate_tool_enabled_snapshot()` or `_validate_no_tool_snapshot()` based on mode.
- `DefaultHostToolFactAcceptPort.decide_tool_call()` rejects tool calls when `execution_scope.allow_tool_calls` is False (`tool_runtime.py:1186-1191`).
- `ToolRuntimeExecutor._execute_one()` checks `_request_context_matches_scope()` and overrides policy to `GOVERNED_ERROR` on mismatch (`tool_runtime.py:2251-2256`).

### 6. Side-effect/paid tool policy

**PASS.**

- `ToolRuntimePolicyPort.decide_tool_call()` (`tool_runtime.py:1192-1201`) checks: if tool has no idempotency key AND `side_effect_kind` is `SIDE_EFFECT` or `PAID`, returns `GOVERNED_ERROR` with reason `tool_idempotency_key_required`.
- `ToolSideEffectPolicyView.__post_init__()` (`tool_runtime.py:558-563`) validates that `SIDE_EFFECT`/`PAID` tools must have `idempotency_key_argument_name` bound.
- `_tool_idempotency_key()` extracts the idempotency key from tool call arguments using the policy-defined argument name.

### 7. Truncation/fetch_more scope guard

**PASS.**

- `TruncationManager._validate_cursor()` (`tool_runtime.py:1421-1466`) validates five invariants:
  1. Run scope: `session_id`, `run_id`, `attempt_id` must match (lines 1435-1445)
  2. Token digest: `scope_token_digest` must match `_scope_token_digest(request.scope_token)` (lines 1446-1450)
  3. TTL: `datetime.now(UTC) > cursor.expires_at` check (lines 1451-1455)
  4. Single-use: `cursor.single_use and cursor.used_at is not None` (lines 1456-1460)
  5. Remainder digest: `_remainder_digest_matches(cursor.remaining_ref)` (lines 1461-1465)
- `FetchMoreToolCallable` is injected as an ordinary framework tool, goes through normal ToolRuntime/accept/EventLog path.
- `TruncationManager` is run-scoped, short-lived, ToolRuntime-local.

### 8. Phase 7 wait/resolve_wait deferral

**PASS.**

- `_normalize_runtime_outcome()` (`tool_runtime.py:2427-2452`) converts `ToolAwaitingOutcome` to `ToolFailedOutcome` with `GOVERNED_ERROR` and reason `unsupported_awaiting`.
- Diagnostic emitted: `ToolTraceDiagnosticRecord(reason_code="unsupported_awaiting", message="ToolAwaitingOutcome is unsupported in Phase 6")`.
- Guard at accept path: `_tool_fact_accept_candidate()` raises `TypeError("ToolAwaitingOutcome must be normalized before accept")` (`tool_runtime.py:4298-4299`).
- Guard at digest path: raises `TypeError("ToolAwaitingOutcome must be normalized before digest")` (`tool_runtime.py:4474-4475`).
- No `WAITING` status, no wait record written, no `resolve_wait` tool injected.

### 9. ToolRuntimeExecutor main pipeline

**PASS.**

`_execute_one()` (`tool_runtime.py:2222-2322`) orchestrates:

1. Compute identity/argument digests (lines 2232-2238)
2. Duplicate governance decision (line 2247-2249)
3. Policy decision (line 2250)
4. Scope mismatch override (lines 2251-2256)
5. Duplicate-governed override (lines 2257-2266)
6. REUSE fast path — returns prior accepted outcome without calling business callable (lines 2267-2276)
7. GOVERNED_ERROR path — returns failure outcome (lines 2277-2278)
8. Normal dispatch path (line 2280)
9. Runtime outcome normalization — Phase 7 deferral (line 2281-2283)
10. Truncation (lines 2284-2289)
11. Accept barrier — write canonical facts (lines 2291-2305)
12. Record duplicate accepted on success (lines 2306-2313)
13. Return accepted or governed failure record (lines 2306-2322)

Pipeline is correct: duplicate check before dispatch, policy gate before callable, truncation after outcome, accept barrier as final gate.

### 10. Thread safety

**PASS.**

- `_RunLocalDuplicateGovernanceState` uses `RLock` for thread-safe state access (`tool_runtime.py:1521`).
- `InMemoryRunScopedDuplicateGovernanceRegistry` uses `RLock` for registry-level operations (`tool_runtime.py:1662`).
- `TruncationManager` is ToolRuntime-local, not shared across threads.
- `FetchMoreToolCallable` binds manager per-ToolRuntime instance.

### 11. Protocol / interface boundaries

**PASS.**

- `RunScopedDuplicateGovernanceRegistry` is a clean `Protocol` (`tool_runtime.py:1055-1088`) with three methods: `duplicate_governance_for_run`, `clear_run`, `clear_all`.
- `DuplicateGovernancePort` protocol satisfied by `InMemoryRunLocalDuplicateGovernance`.
- `ToolRuntimeBuildRequest.duplicate_governance_registry` field is `RunScopedDuplicateGovernanceRegistry | None` with default `None` — backward compatible.
- `__all__` exports updated with `RunScopedDuplicateGovernanceRegistry` and `InMemoryRunScopedDuplicateGovernanceRegistry`.

### 12. Tests, pyright, README/doc synchronization

**PASS.**

- pyright: 0 errors, 0 warnings, 0 informations.
- pytest: 349 passed (includes 7 new ToolRuntime test files + modified existing tests).
- `git diff --check`: clean.
- `dayu/host/README.md`: updated paragraph describing duplicate governance from instance-local to Run-scoped in-memory with explicit no-durable-ledger statement.
- `dayu/README.md`: updated architecture overview.
- `docs/host/design.md`: Phase 6 design write-back.
- `docs/host/implementation-control.md`: slice completion records through aggregate PASS.
- PR body correctly describes scope, validation results, and review state.

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- **No CI checks**: `gh pr checks 55` reports no checks configured for this branch. pyright and test verification done locally but no automated gate on PR merge.
- **No durable duplicate ledger**: Phase 6 boundary. Host process crash, restart, or cross-process dispatch will not recover duplicate memory. Documented and intentional.
- **TruncationManager state not durable**: cursor state lives in-process memory only. Process restart loses all cursors. Consistent with Phase 6 scope.
- **`_ingest_closed_run` only triggers cleanup for ACCEPTED/DUPLICATE terminal closeout**: REJECTED terminal closeout does not trigger `clear_run()`. Non-issue because `close()` calls `clear_all()` as safety net, and REJECTED terminal closeout is an abnormal end where preserving duplicate state is acceptable.
- **No size bound on `_RunLocalDuplicateGovernanceState._entries_by_key`**: dict grows unboundedly within a Run's lifetime. Mitigated by short Run lifecycle and `clear_run()`/`clear_all()` cleanup paths. Not a practical concern for current Run durations.
- **`FetchMoreToolCallable._manager` is initially None**: calling `fetch_more` before `bind_manager()` would fail. Mitigated by `DefaultToolRuntimeFactory` binding manager immediately after construction. No external caller can reach the callable before binding.

## Conclusion

**PASS.**

PR 55 正确实现了 Host Phase 6 ToolRuntime 边界。核心实现包括：

1. **Run-scoped duplicate governance**: `InMemoryRunScopedDuplicateGovernanceRegistry` 按 `run_id` 持有进程内短生命周期 state，同一 Run 的多个 ToolRuntime handle 共享 accepted fact，不同 Run 互相隔离，无 durable ledger。
2. **Same-source wiring**: `_validate_tool_enabled_snapshot()` 强制 tool schemas 和 executor 来自同一 `ToolRuntimeHandle`。
3. **Accept barrier**: `DefaultHostToolFactAcceptPort` 写入 `TOOL_CALL_REQUESTED` → `TOOL_CALL_GOVERNED` → `TOOL_RESULT_ACCEPTED` canonical facts。
4. **Truncation/fetch_more**: `TruncationManager` 提供 run-scoped cursor 校验（scope、token、TTL、single-use、remainder digest），`FetchMoreToolCallable` 作为普通 framework tool 注入。
5. **Side-effect/paid policy**: `SIDE_EFFECT`/`PAID` 工具必须携带 idempotency key。
6. **Phase 7 deferral**: `ToolAwaitingOutcome` 转为 `governed_error`，不写 wait record。
7. **Scheduler cleanup**: 三条路径覆盖 terminal closeout、dispatch cancel、scheduler close。

pyright 0 errors，349 tests passed，README/docs 同步更新。无架构、类型或测试回归。
