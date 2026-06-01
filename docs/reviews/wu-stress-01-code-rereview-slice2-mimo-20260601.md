# WU-STRESS-01 Slice 2 Code Re-Review

## Gate

- **Gate**: deepreview (re-review after fix)
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 2 — Repeated startup / recovery / crash E2E stress
- **Review role**: AgentMiMo, code review specialist
- **Date**: 2026-06-01

## Reviewed Target

- Controller adjudication: `docs/reviews/wu-stress-01-code-controller-adjudication-slice2-20260601.md`
- Fix artifact: `docs/reviews/wu-stress-01-fix-slice2-codex-20260601.md`
- Current workspace diff (uncommitted, post-fix) on branch `test/host-stress-suite` vs HEAD (`11d00cc`)
- Changed files:
  - `tests/host/stress_support.py` (unchanged from first review; fix only touches test file)
  - `tests/host/test_host_production_stress.py` (major refactor: diagnostics dataclasses, exception handling, placeholder semantics)
- Original review: `docs/reviews/wu-stress-01-code-review-slice2-mimo-20260601.md`

## Conclusion

**PASS**

All five ADJ findings are correctly handled. The fix eliminates the dual-truth-source problem, replaces the 15-parameter god function with focused typed dataclasses, properly documents placeholder semantics, and fixes exception handling. No new god dataclass, no duplicated judgment, no scope creep, no test instability.

## Per-Finding Status

### ADJ-S2-01: `_slice2_failure_boundary` 参数过多

**Status**: RESOLVED

15 参数 keyword-only 函数已替换为 5 个 frozen+slots dataclass：

- `Slice2LiveOwnerDiagnostics`（3 字段 + `probe_ok`、`attempt_count_ok` 谓词）
- `Slice2RecoveryDiagnostics`（4 字段 + `event_counts_ok`、`liveness_stale_detected`、`worker_accepted_once`、`attempts_changed` 谓词）
- `Slice2TerminalDiagnostics`（7 字段 + `terminal_dedupe_ok`、`count_ok`、`crashed_public_terminals_succeeded`、`terminal_statuses_succeeded` 谓词）
- `Slice2AttemptDiagnostics`（1 字段 + `crashed_attempt_counts_ok` 谓词）
- `Slice2StressDiagnostics`（4 子 dataclass 聚合 + `failure_boundary`、`scheduler_drained` 等委托属性）

无裸 `dict`、`Any`、`object` 引入。每个 dataclass 职责单一，字段数量合理。

**一致性验证**: `Slice2StressDiagnostics.failure_boundary` 的判断顺序与原 `_slice2_failure_boundary` 完全对应：
- live owner probe / attempt → "liveness"
- recovery / lost event counts → "recovery"
- terminal dedupe / count → "durable"
- crashed public terminals → "recovery"
- terminal statuses → "durable"
- worker accepted once → "worker_accept"
- attempts changed → "recovery"
- crashed attempt counts → "durable"

注：原实现中 `live_attempt_count != _EXPECTED_LIVE_ATTEMPT_COUNT` → "liveness" 检查已移至 `scheduler_drained` 属性（通过 `live_owner.attempt_count_ok` 委托），不再单独贡献 failure boundary。这在语义上合理：live owner attempt count 不符合预期时，scheduler_drained 为 False，`assert_summary_ok` 会捕获该失败。

### ADJ-S2-02: 断言逻辑双真源

**Status**: RESOLVED

- `HostStressSummary.failure_boundary` 赋值来自 `diagnostics.failure_boundary`（第 534 行）
- `_assert_slice2_diagnostics_ok` 断言 `diagnostics.failure_boundary is None`（第 639 行）
- `assert_summary_ok` 断言 `summary.failure_boundary is None`（来自 `stress_support.py:540`）

三者共享同一 `Slice2StressDiagnostics.failure_boundary` 谓词链。旧实现中独立的 12 行 `assert all(...)` 块已完全移除，不再存在分歧风险。

### ADJ-S2-03: summary 未测量字段需要语义收口

**Status**: RESOLVED

- `watch_lag_max` / `watch_lag_samples` 通过 `_slice2_watch_lag_placeholder()` 返回固定占位值（第 521 行）
- 占位函数 docstring 明确声明"Slice 2 不测量 watch lag，值仅为 schema placeholder"（第 609-618 行）
- 模块级常量 `_SLICE2_WATCH_LAG_PLACEHOLDER` 和 `_SLICE2_WATCH_LAG_SAMPLES_PLACEHOLDER` 有类型注解（第 53-54 行）
- `scheduler_drained` 不再是硬编码 `True`，而是从 Slice 2 diagnostics 推导（第 325-333 行），覆盖：terminal 覆盖、public succeeded、terminal statuses、worker accepted once、attempts changed、crashed attempt counts、live attempt count

### ADJ-S2-04: terminate 异常路径应保留原始上下文

**Status**: RESOLVED

两处修复均已验证：

1. `start_and_crash_owner_for_stress`（`stress_support.py:748-754`）：
   - 正常路径：`terminate_process` 在 try 块内完成（第 739 行），异常路径不再重复 terminate
   - 异常路径：`except BaseException as original_error` + `if owner_process.is_alive()` 守卫，避免对已终止进程冗余调用
   - cleanup 失败时：`raise cleanup_error from original_error` 保留原始异常链

2. `_run_live_owner_probe`（`test_host_production_stress.py:600-606`）：
   - 正常路径：owner process 已通过 `join` + `assert_process_exited_successfully` 退出，不再调用 `terminate_process`
   - 异常路径：同上 `is_alive()` 守卫 + 异常链保留模式

### ADJ-S2-05: terminal_duplicate_count 混合场景语义

**Status**: DEFERRED (as expected)

Controller 裁决 deferred-with-owner，归属 Slice 5。本次 fix 未修改 `terminal_duplicate_count` 实现，符合预期。

## Additional Checks

### 无新 god dataclass

5 个 diagnostics dataclass 字段数分别为 3、4、7、1、4（子引用），总计 15 个独立字段。每个 dataclass 有明确单一职责和对应谓词。`Slice2StressDiagnostics` 作为聚合层只有 4 个子引用加委托属性，不是 god bag。

### 无重复判断

原实现中 `_slice2_failure_boundary` 的 15 行条件判断和测试函数中的 12 行 `assert all(...)` 是双真源。修复后两者统一为 `Slice2StressDiagnostics.failure_boundary` 一个真源。`_assert_slice2_diagnostics_ok` 只做 `assert diagnostics.failure_boundary is None` 一行断言。

### 无 scope 越界

- `stress_support.py` 未修改（fix 只涉及 test file）
- 新增 dataclass 全部在 `test_host_production_stress.py` 内，是 slice-local 测试类型
- 无 production code 变更
- 无 Slice 3-5 实现混入

### 测试稳定性

- 运行时间 3.27s（vs 修复前 3.28s），无显著变化
- Recovery multiprocess tests: 3 passed（无回归）
- Pyright: 0 errors, 0 warnings, 0 informations

### Docstring / 强类型

- 所有新增 dataclass 有完整中文 docstring（参数、返回值、异常）
- 所有新增 property 有完整中文 docstring
- 无 `Any`、`object`、裸 `dict`/`list` 注解

## Residual Risks / Open Questions

1. **ADJ-S2-05 后续**: `terminal_duplicate_count` 的 OR 语义在 Slice 5 混合终态场景中的适用性仍待验证，已由 controller 指派 Slice 5 owner。

2. **`scheduler_drained` 语义演进**: Slice 2 的 `scheduler_drained` 基于 terminal/recovery drain 推导，与 Slice 4 的 scheduler long-run cleanup 证明不同。后续 slice 需确认 `HostStressSummary.scheduler_drained` 的跨 slice 语义是否需要更明确的分层。

3. **`failure_boundary` 检查顺序**: 当前 `Slice2StressDiagnostics.failure_boundary` 按优先级返回第一个失败边界。如果多个边界同时失败，只报告第一个。这是合理的 fail-fast 语义，但 summary JSON 中不会体现次要失败。

## Artifact Path

`docs/reviews/wu-stress-01-code-rereview-slice2-mimo-20260601.md`
