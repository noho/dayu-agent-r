# Code Re-Review

## Scope

- Mode: current changes
- Branch: test/host-stress-suite
- Base: main
- Output file: docs/reviews/wu-stress-01-code-rereview-slice5-mimo-20260601.md
- Review date: 2026-06-01
- Review role: AgentMiMo re-review after focused fix
- Included scope: `tests/host/stress_support.py` (unstaged), `tests/host/test_host_production_stress.py` (unstaged)
- Excluded scope: 生产代码、public contract、durable schema
- Parallel review coverage: 无
- Sources:
  - `docs/reviews/wu-stress-01-code-controller-adjudication-slice5-20260601.md`
  - `docs/reviews/wu-stress-01-fix-slice5-codex-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice5-mimo-20260601.md`
  - `docs/reviews/wu-stress-01-code-review-slice5-ds-20260601.md`

## Review Pass/Fail

**PASS**

## DS Low Findings Verification

### DS-01: `_SLICE5_PRIMARY_TERMINAL_COUNTS` needs maintenance explanation

**Status: CLOSED**

Controller 要求：在 `_SLICE5_PRIMARY_TERMINAL_COUNTS` 附近添加中文注释，解释每个 tuple entry 和 `RUN_LOST` 排除原因。

验证证据（`tests/host/test_host_production_stress.py:122-126`）：

```python
# session0 有 5 个 Run，但 crash/recovery 的 RUN_LOST 只进入 durable/public
# snapshot，不作为 HostEvent 发给 watcher；session1 无 lost，session2 的
# stream exception 同理不发 HostEvent，因此 primary 期望为 (4, 5, 4)。
_SLICE5_PRIMARY_TERMINAL_COUNTS: tuple[int, ...] = (4, 5, 4)
```

注释清晰解释了：
1. 每个 session 的 Run 数量与 primary watcher 期望的差异原因
2. `RUN_LOST` 不作为 `HostEvent` 发给 watcher 的设计事实
3. `(4, 5, 4)` 的推导逻辑

满足 controller 要求。

### DS-02: `_slice5_timeout_summary` dedupe fields are internally inconsistent

**Status: CLOSED**

Controller 要求：使 timeout summary placeholder 值内部一致。优选 `terminal_duplicate_count=0` 和 `terminal_dedupe_ok=True`。

验证证据（`tests/host/test_host_production_stress.py:2108-2109`）：

```python
terminal_duplicate_count=0,
terminal_dedupe_ok=True,
```

已修复为内部一致：`terminal_duplicate_count=0` 与 `terminal_dedupe_ok=True` 语义匹配。`failure_boundary="unknown"` 仍作为失败信号保留。

满足 controller 要求。

## New Issue Check

未发现新问题。fix 只涉及：
1. 添加注释（DS-01）
2. 修改 timeout summary placeholder 值（DS-02）

两者都不改变运行时行为，不引入新的逻辑路径或边界条件。

## Production Code Check

**无生产代码修改**。diff 仅包含：
- `tests/host/stress_support.py`：新增 `HostStressScenario` dataclass（测试层）
- `tests/host/test_host_production_stress.py`：新增 Slice 5 测试、诊断类、timeout summary helper

所有修改都在 `tests/` 目录下。

## Contract/Schema Change Check

**无 contract 或 schema 变更**。新增的 `HostStressScenario` 和 `Slice5MixedHostDiagnostics` 都是测试层内部类型，不进入 public API、durable schema 或 Host contract。

## Residual Risk

与初始 review 一致，无新增 residual risk：
- `pytest-timeout` 全局超时可以在 event loop 全局阻塞时终止进程，此时 `_slice5_timeout_summary` 不会执行
- `max(summary_watch_lag_samples)` 在空 tuple 时会抛出 `ValueError`，但当前代码结构保证不会触发

## Conclusion

DS 两项 low finding 均已正确修复。fix 范围最小化，只触及注释和 placeholder 值，不改变运行时行为。无新问题、无生产代码修改、无 contract/schema 变更。Slice 5 通过 re-review。
