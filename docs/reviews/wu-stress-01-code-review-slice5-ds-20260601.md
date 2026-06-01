# Code Review

## Scope

- Mode: current changes
- Branch: test/host-stress-suite
- Base: main
- Output file: docs/reviews/wu-stress-01-code-review-slice5-ds-20260601.md
- Review date: 2026-06-01
- Review role: AgentDS independent code review specialist
- Included scope: `tests/host/stress_support.py` (unstaged), `tests/host/test_host_production_stress.py` (unstaged)
- Excluded scope: committed slices 1-4 (reviewed separately), `docs/reviews/wu-stress-01-implementation-slice5-codex-20260601.md` (implementation artifact, not code)
- Parallel review coverage: 无
- Sources: `docs/host/design.md`, `docs/host/wu-stress-01-host-production-stress-suite-plan.md` Slice 5, `docs/reviews/wu-stress-01-implementation-slice5-codex-20260601.md`

## Review Pass/Fail

**PASS**

The Slice 5 implementation correctly fulfills all plan requirements. No production code is modified, no public contract or schema is changed. All validations pass (stress tests, package export tests, import boundary tests, pyright). The deterministic fault injection scenario covers all required fault types, the summary JSON on failure works correctly, and the RUN_LOST proof is structurally sound.

## Findings

### 1-未修复-低-Slice5MixedHostDiagnostics 对 `_SLICE5_PRIMARY_TERMINAL_COUNTS` 的硬编码依赖缺少一致性校验

- **入口/函数**: `test_mixed_host_stress_deterministic_fault_injection` / `consume_terminals`
- **文件(行号)**: `tests/host/test_host_production_stress.py:122`, `tests/host/test_host_production_stress.py:356`
- **输入场景**: 当后续维护者修改 fault script（增删 session 内的 Run）但忘记同步更新 `_SLICE5_PRIMARY_TERMINAL_COUNTS = (4, 5, 4)` 时。
- **实际分支**: `consume_terminals` 按 `expected_count=_SLICE5_PRIMARY_TERMINAL_COUNTS[index]` 消费，若实际 terminal 数不等于期望值，会 TimeoutError 或提前完成但预期数未达标。
- **预期行为**: 硬编码值与实际 fault script 产生的非 LOST terminal 数一致。
- **实际行为**: 当前一致（session 0=4, session 1=5, session 2=4），但没有运行时校验来检测偏离。
- **直接证据**: `tests/host/test_host_production_stress.py:122` 定义常量，`tests/host/test_host_production_stress.py:356` 消费；两者之间无自动推导或校验。
- **影响**: 维护者修改 fault script 后测试可能 TimeoutError（有 summary JSON）或产生误报的 watch lag 断言失败。不会静默通过——失败有结构化消息，但根因定位需要手动计算 terminal 数。
- **建议改法和验证点**: 在 `_SLICE5_PRIMARY_TERMINAL_COUNTS` 附近加注释说明每项对应哪个 session 的哪些 Run 类型；或在 consume_terminals 的 TimeoutError 处理中附加 `expected_count` 与已消费数。当前实现已有 summary JSON 兜底，不需要结构性改动。
- **修复风险（低）**: 注释级改动，不影响行为。
- **严重程度（低）**: 当前值正确，失败时有 summary JSON 定位；属于可维护性提升，非正确性缺陷。

### 2-未修复-低-`_slice5_timeout_summary` 中 `terminal_dedupe_ok=False` 与 `terminal_duplicate_count=0` 语义不一致

- **入口/函数**: `_slice5_timeout_summary`
- **文件(行号)**: `tests/host/test_host_production_stress.py:2086-2111`
- **输入场景**: 内部 deadline 触发 `TimeoutError`，进入 `_slice5_timeout_summary` 构造失败摘要。
- **实际分支**: `terminal_duplicate_count=0`（表示无重复），但 `terminal_dedupe_ok=False`（表示去重检查未通过）。
- **预期行为**: `terminal_duplicate_count=0` 通常意味着 `terminal_dedupe_ok` 应为 `True`。在 timeout 场景下两者都应为"未知"语义，而非相互矛盾。
- **实际行为**: 两个字段值在逻辑上冲突——无重复却标记去重失败。但 `failure_boundary="unknown"` 已明确表达"状态未知"语义，且该摘要只在 timeout 失败路径使用，不会被误读为成功。
- **直接证据**: `tests/host/test_host_production_stress.py:2108-2109`。
- **影响**: 仅影响 timeout 失败时的诊断可读性；不影响正常路径。阅读 summary JSON 时可能困惑为何 `terminal_duplicate_count=0` 但 `terminal_dedupe_ok=false`。
- **建议改法和验证点**: 将 `terminal_dedupe_ok` 改为 `True` 与 `terminal_duplicate_count=0` 保持一致，或改为 `False` 且 `terminal_duplicate_count` 改为 `-1` 表示未知。当前实现可接受，不需要阻塞 merge。
- **修复风险（低）**: 仅改 timeout 路径占位值。
- **严重程度（低）**: 仅影响 timeout 失败路径的诊断一致性；`failure_boundary="unknown"` 已是最重要的诊断信号。

## Open Questions

无。

## Residual Risk

- `pytest-timeout` 全局超时（120s）与内部 deadline（`_SLICE5_CONSUME_TIMEOUT_SECONDS=40s`, `_SLICE5_WAIT_TIMEOUT_SECONDS=25s`）之间无协调机制。若 event loop 被全局阻塞（例如 SQLite WAL 检查点在 pytest tmp_path 的慢文件系统上卡死），`pytest-timeout` 会直接 SIGTERM 整个测试进程，此时 `_slice5_timeout_summary` 不会执行，summary JSON 不会写入 `record_property`。这是 `pytest-timeout` 的固有局限，不是本实现的缺陷。
- `max(summary_watch_lag_samples)` 在 `summary_watch_lag_samples` 为空 tuple 时会抛出 `ValueError`。当前代码结构中，`_record_all_watch_lag_samples` 在 summary 构造前至少被调用了 4 次，每次至少追加 3 个样本（每 session 一个），因此不会触发。但如果未来重构改变了采样调用顺序，这个路径可能暴露。建议在 `_flatten_int_groups` 或调用点增加空集合保护。
- 与 Slice 4 相同的 residual risk：`terminal_events_for_runs()` 不覆盖 `RUN_LOST` 对应的 public terminal observation（`HostEventKind` / `HostTerminalStatus` 当前不建模 lost），因此 terminal 去重证明只能用 `all_terminal_event_count == len(public_snapshots)` 这种跨层计数对账方式，而不能直接检查 `RUN_LOST` 是否有重复 durable event。这是 Host public contract 的设计约束，不是测试缺陷。

## Validation

```text
# Slice 5 individual test
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k mixed_host_stress -q
→ 1 passed, 4 deselected in 1.40s

# Full stress suite
pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q
→ 5 passed in 5.83s

# Package export / import boundary / weak typing guard
pytest tests/host/test_package_exports.py tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q
→ 25 passed in 1.49s

# Type checking
python -m pyright dayu/ tests/ utils/
→ 0 errors, 0 warnings, 0 informations
```

## Plan Coverage Matrix

| Plan Requirement | Status | Evidence |
|---|---|---|
| `HostStressScenario` dataclass | 完成 | `stress_support.py:155-175` |
| Fixed scenario: 3 sessions, 5 runs/session, 15 total | 完成 | `test_host_production_stress.py:111-117` |
| Fault script: final, failed, queued cancel, active cancel, stream exception, owner crash/recovery, watch reconnect | 完成 | 测试主体覆盖全部 fault 类型 |
| Primary watchers for all 3 sessions | 完成 | `test_host_production_stress.py:1093-1107` |
| Secondary watcher disconnect/reconnect | 完成 | `test_host_production_stress.py:1108-1185` |
| Summary assertions (session_count, run_count, crash_count, recovery_count, watch_lag, scheduler_drained, liveness_stale_detected, terminal dedupe) | 完成 | `test_host_production_stress.py:1400-1413` |
| Summary JSON on assertion failure | 完成 | 所有 assert 第二个参数为 `summary_json` |
| TimeoutError → AssertionError with summary JSON | 完成 | `test_host_production_stress.py:1350-1354` |
| `record_property` + `tmp_path` JSON file | 完成 | `test_host_production_stress.py:1397-1398` |
| `_slice5_timeout_summary` helper | 完成 | `test_host_production_stress.py:2086-2111` |
| RUN_LOST proof (all_terminal_event_count == len(public_snapshots)) | 完成 | `Slice5MixedHostDiagnostics.terminal_dedupe_ok` |
| Scheduler drain + clean close proof | 完成 | `Slice5MixedHostDiagnostics.scheduler_drained` |
| Lane release proof | 完成 | `verify_lane_released` |
| Handle close/cancel cleanup | 完成 | `Slice5MixedHostDiagnostics.cleanup_ok` |
| No production code modified | 完成 | diff 仅包含 `tests/host/` |
| No public contract/schema change | 完成 | 仅有测试层新增 |
