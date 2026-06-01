# WU-STRESS-01 Slice 2 Code Re-Review Artifact

## Gate

- **Gate**: re-review (post controller adjudication + fix)
- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Review role**: AgentDS, code review specialist
- **Review target**: 修复后工作区 diff（implementation + fix）
- **Accepted plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Controller adjudication**: `docs/reviews/wu-stress-01-code-controller-adjudication-slice2-20260601.md`
- **Fix artifact**: `docs/reviews/wu-stress-01-fix-slice2-codex-20260601.md`
- **Original review**: `docs/reviews/wu-stress-01-code-review-slice2-ds-20260601.md`
- **Re-review artifact**: `docs/reviews/wu-stress-01-code-rereview-slice2-ds-20260601.md`

## Reviewed target

| File | Change type |
|------|-------------|
| `tests/host/stress_support.py` | Slice 2 实现 + ADJ-S2-04 fix（terminate 异常路径） |
| `tests/host/test_host_production_stress.py` | Slice 2 实现 + ADJ-S2-01/02/03 fix（diagnostics 重构 + dual path 归一化 + scheduler_drained 推导 + watch lag placeholder） |

未修改其他文件。Production code 无变更。

## Conclusion: PASS

所有 5 个 controller adjudication 项目中，4 个要求修复的（ADJ-S2-01 到 ADJ-S2-04）均已正确实现，1 个延期项（ADJ-S2-05）按裁决不处理。修复未引入新 god dataclass、重复判断、scope 越界或测试不稳定。

Remaining findings: **0**（原 4 个全部 resolved，无新增）。不阻塞 Slice 3 推进。

## Per-finding status

### Finding 001 (原 DS-001): `_slice2_failure_boundary` god function → ADJ-S2-01

**裁决**: accepted，要求改为 typed diagnostics dataclass 或 per-boundary helpers。

**修复**: 将 15 参数函数替换为 4 个聚焦的 `frozen/slots` dataclass + 1 个聚合 `Slice2StressDiagnostics`：

| 新类型 | 字段数 | Predicate 属性 | 职责 |
|--------|--------|---------------|------|
| `Slice2LiveOwnerDiagnostics` | 3 | `probe_ok`, `attempt_count_ok` | live owner 防误恢复 |
| `Slice2RecoveryDiagnostics` | 4 | `event_counts_ok`, `liveness_stale_detected`, `worker_accepted_once`, `attempts_changed` | recovery 事件与 worker accept |
| `Slice2TerminalDiagnostics` | 7 | `terminal_dedupe_ok`, `count_ok`, `crashed_public_terminals_succeeded`, `terminal_statuses_succeeded` | terminal 去重与终态 |
| `Slice2AttemptDiagnostics` | 1 | `crashed_attempt_counts_ok` | attempt 计数 |
| `Slice2StressDiagnostics` (aggregate) | 4 | `terminal_duplicate_count`, `terminal_dedupe_ok`, `liveness_stale_detected`, `scheduler_drained`, `failure_boundary` | 跨诊断聚合 + summary 字段 |

**验证**:
- 无 `Any`、`object`、裸 `dict` ✓
- 所有 dataclass 均为 `frozen=True, slots=True` ✓
- 每个 dataclass 职责聚焦，非 god object ✓
- `Slice2StressDiagnostics.failure_boundary` 成为唯一 predicate 真源 ✓

**状态**: **RESOLVED** ✓

### Finding 002 (原 DS-002): 双重断言路径 → ADJ-S2-02

**裁决**: accepted，要求归一化断言逻辑。

**修复**: 
- 旧代码中 12 行逐个 `assert recovery_count == ...` / `assert attempt_lost_count == ...` 的独立断言块已移除。
- 替换为 `_assert_slice2_diagnostics_ok(diagnostics, summary_json)`，其唯一操作是 `assert diagnostics.failure_boundary is None`。
- `summary.failure_boundary` 同样来自 `diagnostics.failure_boundary`（行 534: `failure_boundary=diagnostics.failure_boundary`）。
- `assert_summary_ok(summary)` 保留作为 defense-in-depth（检查 `failure_boundary is None` + `terminal_dedupe_ok` + `terminal_duplicate_count == 0`），其断言的三个条件都是 `failure_boundary` 已覆盖的子集，不构成独立真源。

**验证**:
- 测试断言与 summary 均从 `Slice2StressDiagnostics.failure_boundary` 单一入口取值 ✓
- 不存在可独立分歧的第二套条件 ✓

**状态**: **RESOLVED** ✓

### Finding 003 (原 DS-003): summary 硬编码字段 → ADJ-S2-03

**裁决**: accepted as clarification，要求 `scheduler_drained` 由 Slice 2 diagnostics 推导，watch lag 写明为 placeholder。

**修复**:
- `scheduler_drained` 改为 `diagnostics.scheduler_drained`（行 530），由 `Slice2StressDiagnostics.scheduler_drained` 属性计算。
- `scheduler_drained` 属性（行 313-333）综合检查 terminal coverage + public succeeded terminals + tonic statuses + worker accept + attempt replacement + attempt counts，docstring 明确标注 "Slice 2 不做 Slice 4 的 scheduler long-run cleanup 证明"。
- 新增 `_slice2_watch_lag_placeholder()` 函数（行 609-620），docstring 明确 "Slice 2 只验证 repeated startup/recovery/crash E2E，不测量 Slice 3 的 watch lag"。
- 模块级常量 `_SLICE2_WATCH_LAG_PLACEHOLDER` 和 `_SLICE2_WATCH_LAG_SAMPLES_PLACEHOLDER` 清晰标记占位语义。

**验证**:
- `scheduler_drained` 有真实诊断逻辑支撑 ✓
- watch lag 占位语义明确，不会误导后续 slice ✓

**状态**: **RESOLVED** ✓

### Finding 004 (原 DS-004): terminate 异常路径丢失上下文 → ADJ-S2-04

**裁决**: accepted，要求保留原始异常链，避免不必要的重复 terminate。

**修复**:
- `start_and_crash_owner_for_stress`（行 748-754）: 
  ```python
  except BaseException as original_error:
      if owner_process.is_alive():
          try:
              terminate_process(owner_process)
          except BaseException as cleanup_error:
              raise cleanup_error from original_error
      raise
  ```
  - 仅对仍存活进程调用 terminate ✓
  - 使用 `raise cleanup_error from original_error` 保留异常链 ✓
- `_run_live_owner_probe`（行 600-606）: 同模式 ✓
- `_run_live_owner_probe` 正常路径（行 593-594）使用 `owner_process.join()` + `assert_process_exited_successfully` 替代 terminate，不再对已正常退出的进程强制 terminate ✓

**验证**:
- 异常路径仅 terminate 存活进程 ✓
- 原始异常上下文通过 `from` 链保留 ✓
- 正常路径不做多余 terminate ✓

**状态**: **RESOLVED** ✓

### Finding ADJ-S2-05 (deferred): terminal_duplicate_count 混合场景语义

**裁决**: deferred-with-owner，归于 WU-STRESS-01 Slice 5。

**修复**: 按裁决不处理。`terminal_duplicate_count` 保持一致语义不变。

**状态**: **DEFERRED** — Slice 5 重新评估

## Additional re-review observations

### 无新 god dataclass

4 个诊断 dataclass 职责聚焦（最大 7 字段的 `Slice2TerminalDiagnostics` 仍限定在 terminal 诊断单一领域内）。`Slice2StressDiagnostics` 作为聚合层，每个属性都是对子 dataclass predicate 的薄委托或组合，不构成 god object。

### `Slice2TerminalDiagnostics.terminal_statuses` 字段是修复中的正确增量

原始 `_slice2_failure_boundary` 未检查 terminal observation 的 `terminal_status`（仅检查 `crashed_terminal_kinds`），导致该检查仅存在于旧断言块中（双重路径的不完全一致性）。新版 `Slice2TerminalDiagnostics` 将 `terminal_statuses` 纳入字段，`Slice2StressDiagnostics.failure_boundary` 中增加了 `terminal.terminal_statuses_succeeded` 检查（行 351-352）。此前仅存在于独立断言块的逻辑现已统合进单一 predicate。

### `Slice2AttemptDiagnostics` 体量单薄但合理

该 dataclass 仅 1 字段 + 1 predicate。形式上可并入 `Slice2RecoveryDiagnostics`，但保持独立更符合 controller 要求的 "per-boundary typed diagnostics" 分解策略，且为 Slice 4/5 的 attempt 诊断扩展预留了清晰边界。

### 测试稳定性无退化

崩溃循环、live owner probe、watcher 消费逻辑均未改变。Diagnostics 重构是纯 predicate 重组，不改变运行时行为。60s timeout 保持不变。

### 无 scope 越界

所有修改在 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py` 内，无 production code 变更，无 Slice 3-5 实现。

## Residual risks / open questions

1. **ADJ-S2-05 deferred 项**: `terminal_duplicate_count` 在混合终态场景（同一 run 先 FAILED 后 recovery SUCCEEDED 的 durable event 序列）下的语义未验证。Slice 5 implementation/review 必须重新评估。当前 Slice 2 仅覆盖 per-run 单 terminal 场景，无风险。

2. **`_slice2_watch_lag_placeholder` 的 sentinel 值 (0, (0,))**: 与 Slice 3 真实测量结果无法区分（如果 Slice 3 确实测出 lag=0）。但是：Slice 2 和 Slice 3 是独立测试函数，各自构造自己的 summary，不会混淆。该风险仅在跨 slice 比较 summary JSON 时需注意，不影响单 slice 正确性。

3. **`Slice2StressDiagnostics.scheduler_drained` 语义**: 当前定义为 Slice 2 recovery/terminal drain 收口，非 Slice 4 的 scheduler close cleanup 完整证明。docstring 已明确标注。Slice 4 实施时需确保 `scheduler_drained` 的赋值逻辑升级为 Slice 4 的 host instance / lane / handle close 完整诊断，而非累加 Slice 2 条件。

## Verification checklist

| Check | Result |
|-------|--------|
| ADJ-S2-01: god function 消除 | RESOLVED — 4× focused dataclass + aggregate |
| ADJ-S2-02: 双重断言归一化 | RESOLVED — `failure_boundary` 为单一 predicate 真源 |
| ADJ-S2-03: scheduler_drained 推导 | RESOLVED — 由 diagnostics 计算；watch lag 为显式 placeholder |
| ADJ-S2-04: terminate 异常路径修复 | RESOLVED — alive check + `from` chain |
| ADJ-S2-05: terminal dedupe 延期 | DEFERRED — 归 Slice 5 |
| 无新 god dataclass | PASS |
| 无新重复判断 | PASS |
| 无 scope 越界 | PASS |
| 无 production code 变更 | PASS |
| 类型安全（无 Any/object/裸 dict） | PASS |
| docstring 完整 | PASS |
| 修复 artifact 声明与代码一致 | PASS |
| 已有 recovery 测试未回归 | 修复 artifact 报告 3 passed |
| pyright clean | 修复 artifact 报告 0 errors |
