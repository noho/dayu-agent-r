# Phase 6 Aggregate Fix: Run-local Duplicate Governance

## Root Cause

P6-S5 的 duplicate governance 名义上是 run-local，但 accepted duplicate 索引由 `InMemoryRunLocalDuplicateGovernance` 直接挂在单个 `ToolRuntime` 构造实例内。`HostDispatchScheduler` 每次 tool-enabled dispatch 都重新构造 `ToolRuntimeHandle`，因此同一 Run、同一 Host 进程内的多个 Attempt / 多个 ToolRuntime handle 无法共享已 accepted 的 duplicate fact。

这个问题是真实 blocker：Phase 6 exit standard 要求同 Run、同进程的多 ToolRuntime handle 共享重复治理记忆；但 P6 不能引入 durable duplicate ledger，也不能承诺 crash / restart recovery。

## Files Changed

- `dayu/host/tool_runtime.py`
- `dayu/host/dispatch.py`
- `tests/host/test_toolruntime_duplicate_governance.py`
- `tests/host/test_dispatch_scheduler.py`
- `dayu/host/README.md`
- `docs/reviews/host-phase6-aggregate-fix-run-local-duplicate-governance-20260515.md`

## Behavior After Fix

- 新增 `RunScopedDuplicateGovernanceRegistry` typed protocol 与 `InMemoryRunScopedDuplicateGovernanceRegistry` 实现。
- registry 按 `run_id` 持有进程内短生命周期 duplicate accepted 索引；同一 Run 的多个 ToolRuntime handle 通过同一 registry 共享 accepted fact。
- `InMemoryRunLocalDuplicateGovernance` 仍是 `DuplicateGovernancePort`，但其 accepted 索引 state 可由 Run-scoped registry 注入；policy 仍由每个 ToolRuntime build request 提供。
- 不同 `run_id` 使用不同内存 state，不共享 duplicate 记忆。
- `HostDispatchScheduler` 拥有一个进程内 Run-scoped duplicate registry，并在构造 tool-enabled `ToolRuntimeBuildRequest` 时注入。
- scheduler 在 worker terminal closeout accepted / duplicate 时清理对应 Run 的 duplicate state；`scheduler.close()` 会清理 registry 全部 state，避免 scheduler 生命周期内无界保留。
- 没有新增 durable duplicate table、ledger、recovery path 或 restart 恢复承诺。

## Tests Run

- `source .venv/bin/activate && pytest tests/host/test_toolruntime_duplicate_governance.py tests/host/test_dispatch_scheduler.py -q`
  - Result: `28 passed in 0.41s`
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no whitespace errors

## Residual Risks

- P6 仍没有 durable duplicate ledger；Host 进程崩溃、重启或跨进程 dispatch 不会恢复 duplicate memory。这是本 phase 的明确边界。
- scheduler 的精确 cleanup 依赖本地 worker event stream 进入 terminal closeout path；异常 close / scheduler close 会走 `clear_all()`，粒度更粗但不会泄漏 registry state。
