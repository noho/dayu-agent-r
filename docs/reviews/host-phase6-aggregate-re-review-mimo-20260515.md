# Host Phase 6 Aggregate Re-Review: P6-AGG-F1 Fix

## Scope

- Mode: current changes (re-review)
- Branch: `feat/host-phase-6-toolruntime`
- Base: uncommitted fix on top of `203a69a`
- Previous artifact: `docs/reviews/host-phase6-aggregate-review-mimo-20260515.md`
- Controller adjudication: `docs/reviews/host-phase6-aggregate-review-controller-adjudication-20260515.md`
- Fix artifact: `docs/reviews/host-phase6-aggregate-fix-run-local-duplicate-governance-20260515.md`
- Output file: `docs/reviews/host-phase6-aggregate-re-review-mimo-20260515.md`
- Included scope: P6-AGG-F1 fix and any regressions introduced by it
- Excluded scope: Engine code, Remote transport, business tool implementations, Phase 7+ capabilities
- Parallel review coverage: 无

## Commands And Files Inspected

- `git diff --stat` — 5 files changed, 286 insertions, 25 deletions
- Production code: `dayu/host/tool_runtime.py`, `dayu/host/dispatch.py`
- Test code: `tests/host/test_toolruntime_duplicate_governance.py`, `tests/host/test_dispatch_scheduler.py`
- Documentation: `dayu/host/README.md`
- `python -m pyright dayu/host tests/host` — 0 errors
- `pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py -q` — 28 passed
- `pytest tests/host -q` — 349 passed
- `git diff --check` — clean

## Required Checks

### 1. Same-Run, same-process multiple ToolRuntime handles now share duplicate accepted memory

**PASS.**

- `InMemoryRunScopedDuplicateGovernanceRegistry.duplicate_governance_for_run()` (`tool_runtime.py:1665-1682`) looks up or creates a `_RunLocalDuplicateGovernanceState` by `run_id` under `RLock`, then passes it to `InMemoryRunLocalDuplicateGovernance(policy, state=state)`.
- Multiple calls with the same `run_id` receive the same `_RunLocalDuplicateGovernanceState` instance (`self._states_by_run_id.get(run_id)` at line 1678).
- `InMemoryRunLocalDuplicateGovernance.decide_duplicate()` reads via `self._state.find(duplicate_key)` (`tool_runtime.py:1587`); `record_accepted()` writes via `self._state.record(...)` (`tool_runtime.py:1612`).
- `HostDispatchScheduler._run_input_builder_for_dispatch()` passes `self._duplicate_governance_registry` into `ToolRuntimeBuildRequest` (`dispatch.py:733`).
- `DefaultToolRuntimeFactory.create_tool_runtime()` calls `request.duplicate_governance_registry.duplicate_governance_for_run(...)` when registry is provided (`tool_runtime.py:2600-2604`).
- Test `test_same_run_runtime_handles_share_duplicate_index` (`test_toolruntime_duplicate_governance.py`) creates two executors with the same `run_id` and shared `InMemoryRunScopedDuplicateGovernanceRegistry`; first executor accepts a tool call, second executor with identical tool identity/arguments gets `REUSE` decision and returns prior accepted outcome without calling business callable.

### 2. Different Runs remain isolated

**PASS.**

- `InMemoryRunScopedDuplicateGovernanceRegistry` stores `_RunLocalDuplicateGovernanceState` keyed by `run_id` (`tool_runtime.py:1663`). Different `run_id` values get different state objects.
- Test `test_different_runs_do_not_share_duplicate_index` (`test_toolruntime_duplicate_governance.py`) creates two executors with different `run_id` values sharing the same registry; second executor's tool is actually called (not reused), confirming no cross-Run duplicate memory.

### 3. No durable duplicate ledger or crash/restart recovery promise was introduced

**PASS.**

- `_RunLocalDuplicateGovernanceState` stores `_entries_by_key` in a plain `dict` in instance memory (`tool_runtime.py:1522`). No file, database, or durable storage.
- `InMemoryRunScopedDuplicateGovernanceRegistry` stores `_states_by_run_id` in a plain `dict` in instance memory (`tool_runtime.py:1663`). No durable storage.
- Protocol docstring explicitly states: "不提供 durable ledger、跨进程恢复或重启恢复语义" (`tool_runtime.py:1058-1059`).
- Implementation docstring explicitly states: "不写 durable ledger，不承诺进程崩溃、重启或跨进程恢复" (`tool_runtime.py:1652-1653`).

### 4. Scheduler owns/cleans registry without leaking unbounded Run state

**PASS.**

- `HostDispatchScheduler.__init__` creates `self._duplicate_governance_registry = InMemoryRunScopedDuplicateGovernanceRegistry()` (`dispatch.py:332-334`).
- `HostDispatchScheduler.close()` calls `self._duplicate_governance_registry.clear_all()` (`dispatch.py:468`) — cleans all Run state on scheduler shutdown.
- `HostDispatchScheduler._close_run()` calls `self._duplicate_governance_registry.clear_run(record.run_id)` (`dispatch.py:908`) — cleans Run state on dispatch cancellation.
- `HostDispatchScheduler._consume_worker_events()` sets `run_terminal_closed` flag when ingest result indicates terminal closeout (`dispatch.py:958, 971, 992, 1002`), and the `finally` block calls `self._duplicate_governance_registry.clear_run(record.run_id)` when flag is true (`dispatch.py:1005-1006`).
- `_ingest_closed_run()` helper (`dispatch.py:1016-1026`) correctly identifies terminal closeout: `result.terminal_closeout and result.status in (ACCEPTED, DUPLICATE)`.
- All three exit paths (normal terminal closeout, clean EOF without terminal, worker stream error/ingest exception) are covered. Non-terminal exits (EOF without terminal, cancelled) do not call `clear_run`, but `close()` still calls `clear_all()` as final safety net.
- Test `test_scheduler_uses_toolruntime_when_tooling_is_configured` (`test_dispatch_scheduler.py`) asserts `active_run_count() == 1` after dispatch and `active_run_count() == 0` after `scheduler.close()`.

### 5. Tests and README were updated consistently

**PASS.**

- `test_same_run_runtime_handles_share_duplicate_index`: replaces old `test_new_runtime_does_not_inherit_duplicate_index` — now correctly asserts same-Run sharing.
- `test_different_runs_do_not_share_duplicate_index`: new test verifying cross-Run isolation.
- `_executor` helper updated with `run_id` and `duplicate_governance_registry` optional parameters.
- `test_dispatch_scheduler.py`: added `active_run_count()` assertions before and after scheduler close.
- `dayu/host/README.md`: updated paragraph describing duplicate governance from "索引只存在于当前 ToolRuntime 实例内" to "InMemoryRunScopedDuplicateGovernanceRegistry 在同一 Host 进程内按 Run 持有短生命周期 duplicate 记忆，使同一 Run 的多个 ToolRuntime handle 可共享 accepted fact；不同 Run 互相隔离，且不写 durable duplicate ledger，不承诺 crash / restart recovery".

### 6. Check for new architecture/type/test regressions caused by the fix

**PASS.**

- `RunScopedDuplicateGovernanceRegistry` is a clean `Protocol` (`tool_runtime.py:1055-1088`) with three methods: `duplicate_governance_for_run`, `clear_run`, `clear_all`. Implementation `InMemoryRunScopedDuplicateGovernanceRegistry` satisfies it.
- `ToolRuntimeBuildRequest.duplicate_governance_registry` field is `RunScopedDuplicateGovernanceRegistry | None` with default `None` (`tool_runtime.py:2118`) — backward compatible; existing callers without registry get instance-private governance.
- `DefaultToolRuntimeFactory.create_tool_runtime()` falls back to `InMemoryRunLocalDuplicateGovernance(policy)` when `request.duplicate_governance_registry is None` (`tool_runtime.py:2606-2608`) — preserves existing behavior.
- `_RunLocalDuplicateGovernanceState` uses `RLock` for thread safety (`tool_runtime.py:1521`); `InMemoryRunScopedDuplicateGovernanceRegistry` also uses `RLock` (`tool_runtime.py:1662`).
- `InMemoryRunLocalDuplicateGovernance` still satisfies `DuplicateGovernancePort` protocol — `decide_duplicate` and `record_accepted` signatures unchanged.
- `__all__` exports updated: `RunScopedDuplicateGovernanceRegistry` and `InMemoryRunScopedDuplicateGovernanceRegistry` added (`tool_runtime.py:4608, 4633`).
- pyright: 0 errors, 0 warnings, 0 informations.
- Full test suite: 349 passed (was 348 before fix — the +1 is the new `test_different_runs_do_not_share_duplicate_index`).
- No regressions in existing test behavior.

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- P6 仍没有 durable duplicate ledger；Host 进程崩溃、重启或跨进程 dispatch 不会恢复 duplicate memory。这是 Phase 6 的明确边界。
- scheduler 的精确 cleanup 依赖本地 worker event stream 进入 terminal closeout path；异常 close / scheduler close 走 `clear_all()`，粒度更粗但不会泄漏 registry state。
- `InMemoryRunLocalDuplicateGovernance.__init__` 的 `state` 参数为可选，未注入时仍创建实例私有 state — 保留了非 registry 场景的灵活性，但调用方需注意不通过 registry 创建的 governance 实例不会共享 duplicate 记忆。

## Conclusion

**PASS.**

P6-AGG-F1 fix 正确实现了 Run-scoped in-memory duplicate governance。`InMemoryRunScopedDuplicateGovernanceRegistry` 按 `run_id` 持有进程内短生命周期 `_RunLocalDuplicateGovernanceState`，同一 Run 的多个 ToolRuntime handle 通过共享 state 共享 accepted duplicate 记忆。不同 Run 互相隔离。没有引入 durable ledger 或 crash/restart recovery 承诺。scheduler 在 worker terminal closeout、dispatch cancel 和 scheduler close 三个路径清理 registry state，不会泄漏无界内存。测试覆盖了 same-Run sharing、different-Run isolation、scheduler lifecycle cleanup。README 已同步更新。无架构、类型或测试回归。
