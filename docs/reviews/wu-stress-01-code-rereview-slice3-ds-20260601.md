# WU-STRESS-01 Slice 3 Code Re-Review (AgentDS)

## Gate

- **Gate**: re-review (controller fix verification gate)
- **Review role**: AgentDS independent code re-review specialist
- **Review artifact path**: `docs/reviews/wu-stress-01-code-rereview-slice3-ds-20260601.md`

## Reviewed Target

- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 3 — Sustained watch stress with slow consumer and reconnect
- **Base**: `main`
- **Branch**: `test/host-stress-suite`
- **Scope**: Uncommitted changes in `tests/host/stress_support.py` and `tests/host/test_host_production_stress.py`
- **Plan reference**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md` (Slice 3 节)
- **Design reference**: `docs/host/design.md`
- **Prior review artifacts**:
  - `docs/reviews/wu-stress-01-code-review-slice3-ds-20260601.md` (original DS review)
  - `docs/reviews/wu-stress-01-code-review-slice3-mimo-20260601.md` (original MiMo review)
  - `docs/reviews/wu-stress-01-code-controller-adjudication-slice3-20260601.md` (controller adjudication)
  - `docs/reviews/wu-stress-01-fix-slice3-codex-20260601.md` (fix artifact)
- **Excluded scope**: Production code, Slice 1/2/4/5 behavior, `docs/` changes, review artifacts themselves
- **Parallel review coverage**: 无（单 reviewer 全量走读）

## Controller-Adjudicated Finding Closure Verification

### MIMO-F01 / DS-F02: post-submit `set_run_behavior` race → ACCEPTED, CLOSED

- **Decision**: Replace post-submit `factory.set_run_behavior(...)` with pre-submit `_submit_scripted_followup(..., behavior)`.
- **Verification**: 遍历 Slice 3 测试体中所有非默认行为的 Run 提交：
  - `probe_run_id` → `_submit_scripted_followup(..., BLOCKING_FINAL)` ✓
  - `session1_active_run_id` → `_submit_scripted_followup(..., BLOCKING_FINAL)` ✓
  - `session1_failed_run_id` → `_submit_scripted_followup(..., FAILED)` ✓
  - `session1_second_failed_run_id` → `_submit_scripted_followup(..., FAILED)` ✓
  - `session2_failed_run_id` → `_submit_scripted_followup(..., FAILED)` ✓
  - `session2_active_run_id` → `_submit_scripted_followup(..., BLOCKING_FINAL)` ✓
  - `session2_tail_failed_run_id` → `_submit_scripted_followup(..., FAILED)` ✓
  - gap_run_ids (3 个) → 全部使用 `_submit_scripted_followup` 或 `_submit_followup_waiting_for_accept` ✓
  - 无残留 `set_run_behavior` 调用在 Slice 3 路径中 ✓
- **Closure evidence**: `tests/host/test_host_production_stress.py:1024-1046` (`_submit_scripted_followup` 定义)，所有脚本化提交均经此路径，`enqueue_run_behavior` 在 `_submit_followup` 之前调用。
- **Status**: **CLOSED**。

### DS-F01: `behavior_for_run` docstring → ACCEPTED, CLOSED

- **Decision**: 更新中文 docstring 描述三级查找顺序。
- **Verification**: `tests/host/stress_support.py:446-457`，docstring 明确写 "查找顺序固定为：显式 run_id 行为、预提交的下一次 accept 队列行为、factory 默认行为"，并附使用指引。
- **Status**: **CLOSED**。

### MIMO-F02: `close_host_event_iterator` ownership docstring → ACCEPTED, CLOSED

- **Decision**: 保留在 `stress_support.py`，更新 docstring 声明所有权。
- **Verification**: `tests/host/stress_support.py:587-599`，docstring 明确写 "本 helper 镜像 recovery 测试中的 watch iterator 清理语义，但归属 WU-STRESS-01 stress helper：它不是兼容 wrapper，不是生产生命周期抽象，也不表达 Host close 治理。"
- **Status**: **CLOSED**。

### MIMO-F03: magic thresholds → ACCEPTED, CLOSED

- **Decision**: 引入命名常量。
- **Verification**: `tests/host/test_host_production_stress.py:91-94`：
  - `_SLICE3_SECONDARY_FIRST_TERMINAL_COUNT = 2` ✓
  - `_SLICE3_SECONDARY_RECONNECT_TERMINAL_COUNT = 1` ✓
  - `_SLICE3_DISCONNECT_GAP_RUN_COUNT = 3` ✓
  - `_SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT = _SLICE3_RUN_COUNT` ✓
  - 所有先前硬编码的 magic number 已在 `reconnect_ok`、`disconnect_gap_terminal_truth_ok`、`watch_lag_ok` 中替换为命名常量。
- **Status**: **CLOSED**。

### DS-F03: `gap_diagnostics_ok` → ACCEPTED, CLOSED

- **Decision**: 拆分/重命名 predicate，`failure_boundary="projection"` 仅用于 Outbox 维度。
- **Verification**:
  - `outbox_gap_coverage_ok` (`test_host_production_stress.py:511-519`): 仅检查 Outbox 覆盖率，映射到 `failure_boundary="projection"` ✓
  - `disconnect_gap_terminal_truth_ok` (`test_host_production_stress.py:521-542`): 覆盖 primary watcher、public snapshot、durable terminal observation 与 Outbox 四维证明 ✓
  - 旧 `gap_diagnostics_ok` 已移除 ✓
- **Status**: **CLOSED**。

### DS-F04: global `watch_lag_samples` → ACCEPTED, CLOSED

- **Decision**: 保留 per-session lag 诊断，仅在 `HostStressSummary` 中 flatten。
- **Verification**:
  - `Slice3WatchDiagnostics.watch_lag_samples_by_session: tuple[tuple[int, ...], ...]` (`test_host_production_stress.py:416`) ✓
  - `watch_lag_ok` 检查每个 session 有样本且最终 lag drain (`test_host_production_stress.py:490-509`) ✓
  - `_record_all_watch_lag_samples` 按 session 独立采样 (`test_host_production_stress.py:1268-1310`) ✓
  - `_compute_final_watch_lags_by_session` 按 session 独立计算最终 lag (`test_host_production_stress.py:1313-1346`) ✓
  - 仅在填充 `HostStressSummary.watch_lag_samples` 时调用 `_flatten_int_groups` (`test_host_production_stress.py:1075`) ✓
- **Status**: **CLOSED**。

### MIMO-F04: redundant `tuple([...])` → ACCEPTED, CLOSED

- **Decision**: 移除冗余中间列表。
- **Verification**: `rg 'tuple\(\[' tests/host/` 在 `tests/host/` 下无匹配 ✓
- **Status**: **CLOSED**。

## Cross-Cutting Verification

### No Slice 4/5 behavior

Slice 4 (scheduler/liveness long-run stress) 和 Slice 5 (terminal dedupe redesign) 在 diff 中无实现：
- 无 scheduler long-run cleanup、active task/registry 残留验证
- 无 `InspectableStressWorkerFactory` 或 Slice 4 特有 helper
- 无 Slice 5 terminal dedupe 重设计
- `failure_boundary` 值 `"active_cleanup"` 和 `"scheduler_close"` 在 `StressFailureBoundary` 类型中已定义但 Slice 3 不使用 ✓

### No production code changes

```text
git diff --name-only → tests/host/stress_support.py
                       tests/host/test_host_production_stress.py
```
仅测试文件 ✓

### Chinese docstrings/types compliance

全部新增函数、类、dataclass、property 均有完整中文 docstring：
- `consume_terminals` ✓
- `close_host_event_iterator` ✓
- `read_latest_event_sequence` ✓
- `read_event_log_count` ✓
- `read_session_terminal_sequences` ✓
- `Slice3WatchDiagnostics` 及全部 property ✓
- `_submit_scripted_followup` ✓
- `_submit_followup_waiting_for_accept` ✓
- `_submit_followup` ✓
- `_cancel_run` ✓
- `_wait_accepted_count` ✓
- `_wait_run_status` ✓
- `_wait_run_terminal` ✓
- `_consume_until_cancelled` ✓
- `_record_all_watch_lag_samples` ✓
- `_compute_final_watch_lags_by_session` ✓
- `_latest_session_terminal_count` ✓
- `_drain_observed_event_count` ✓
- `_read_outbox_gap_run_count` ✓
- `_flatten_events` ✓
- `_flatten_int_groups` ✓
- `_run_ids_from_events` ✓
- `_run_ids_from_observations` ✓
- `_is_terminal_status` ✓

类型标注完整，无 `Any`、`object`、裸 `dict`/`list` 注解 ✓

### Validation results

| Command | Result |
|---------|--------|
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q` | 1 passed, 2 deselected (0.71s) |
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` | 3 passed (3.81s, includes Slice 1 & 2 regression) |
| `pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q` | 20 passed (0.63s) |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Findings

### F-01 · 未修复 · LOW · `consumer_cancel_ok` property docstring 声称"四步验证"但仅检查 2/4 条件

- **入口/函数**: `Slice3WatchDiagnostics.consumer_cancel_ok` property
- **文件(行号)**: `tests/host/test_host_production_stress.py:464-475`
- **输入场景**: 读取 `consumer_cancel_ok` 属性判断 consumer cancel 验证是否通过。
- **实际分支**: property 仅检查 `event_log_count_before == event_log_count_after` 且 `worker_cancel_count == 0`。
- **预期行为**: docstring 写"consumer cancel 四步验证"，但 property 内只覆盖 2 步。另 2 步（active run 在 cancel 后仍非终态、释放后正常 terminal）由测试体中的显式 `assert not _is_terminal_status(...)` 和 `_wait_run_status(..., SUCCEEDED)` 完成。
- **实际行为**: 整体验证覆盖完整 4 步，但 property 自身不表达完整验证，`failure_boundary` 以该 property 判断"watch"边界时只依赖 2/4 条件。
- **直接证据**: `test_host_production_stress.py:464-475` property 体 vs `test_host_production_stress.py:830-841` 测试体中的补充断言。
- **影响**: property 自身语义不完整；若未来测试复用 `consumer_cancel_ok` 而不重现测试体的显式断言，会漏检 steps b/d。
- **建议改法和验证点**: 将 docstring 改为"consumer cancel 二步验证（EventLog count 不变 + worker 未收到 cancel）"或在 property 中内联全部 4 步。若选后者，需将 active run status 和 terminal 验证作为参数传入。
- **修复风险（低）**: docstring 修改无风险；property 扩展需调整调用方。
- **严重程度（低）**: 当前测试体中 4 步全部覆盖，不阻塞 Slice 3 合入。

### F-02 · 未修复 · LOW · primary watcher try/finally 双关

- **入口/函数**: `test_sustained_watch_slow_consumer_reconnect_stress` finally 块
- **文件(行号)**: `tests/host/test_host_production_stress.py:1042-1054`
- **输入场景**: try 块正常路径中已关闭全部 `primary_watchers`（行 1028-1029），finally 块再次遍历关闭。
- **实际分支**: finally 块无条件执行 `close_host_event_iterator(watcher)` 并以 `suppress(Exception)` 抑制异常。
- **预期行为**: 正常路径应负责关闭，finally 仅做兜底。双关路径对已关闭 generator 的 `aclose()` 是 no-op（PEP 525），行为正确但掩盖 try 块中部分 watcher 未关闭的 bug。
- **直接证据**: `test_host_production_stress.py:1028-1029`（try 块关闭）与 `test_host_production_stress.py:1052-1054`（finally 块关闭）。
- **影响**: 当前无功能影响。若未来 try 块中 watcher 关闭被条件跳过或异常中断，finally 的 `suppress(Exception)` 会静默吞掉重复关闭异常，使清理不完整变得不可观测。
- **建议改法和验证点**: 用 flag 跟踪哪些 watcher 已在 try 块关闭，finally 中仅关闭未关闭的；或将正常路径的关闭移到 finally 块之前但在 try 块外部。
- **修复风险（低）**: 重构清理逻辑范围小，风险可控。
- **严重程度（低）**: 不影响当前测试正确性，已在原始 DS review 的 Open Question #2 中记录。

## Open Questions

1. **`watch_lag_ok` 中 `max(flattened) < _SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT` 是弱断言**: `_SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT = _SLICE3_RUN_COUNT = 18`，但每个 session 最多 6 个 terminal，per-session watermark-based lag 不可能超过 6。`max(lag) < 18` 永真，实际有效约束来自 `final_watch_lags_by_session` 的 drain-to-0 检查。该上限不提供额外判别力，但可作为未来 scale-up 的预留闸门。

2. **`reconnect_ok` 仅检查 terminal 计数，不验证 run_id 归属**: secondary watcher 重连后消费 `expected_count=1` 条 terminal，断言仅验证 `len(events) >= 1`，不验证该事件的 `run_id` 确实是 `reconnect_run_id`。在当前确定性场景下安全（重连后仅提交一个 run），但若未来场景在重连后提交多个 run，计数断言可能漏检错位事件。

## Residual Risk

- **Slice 2 regression**: 已通过 `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -q` 验证 Slice 1/2/3 共 3 个 stress tests 全部通过。Slice 2 的 `test_repeated_startup_recovery_crash_stress` 未受 Slice 3 改动破坏。
- **`compute_watch_lag` 参数语义偏移**: Slice 3 将 `compute_watch_lag(latest_sequence, last_seen_sequence)` 用于 terminal-count watermarks 而非 sequence numbers。函数体 `max(0, a - b)` 对两者语义等价，但参数名 `latest_sequence` / `last_seen_sequence` 对 count 用法有误导性。不会导致错误行为，但未来维护者可能误解意图。
- **`_drain_observed_event_count` 类型安全边界**: 该函数假设 `observed_events` Queue 中仅包含 terminal HostEvent（由 `consume_terminals` 保证）。若未来调用方将非 terminal 事件写入队列，计数会膨胀。当前无此风险，但队列合约是隐式的。
- **测试覆盖范围**: Slice 3 是一个 deterministic stress scenario，验证了 watch/reconnect/cancel/dedupe/lag 的 plan 约定行为。它不是随机 fuzzing，不覆盖极端时序、高并发竞态或资源耗尽场景。

## Conclusion

**PASS** — 7/7 controller-accepted findings verified CLOSED。No BLOCKING/HIGH/MEDIUM findings。2 LOW severity findings（docstring accuracy + try/finally double-close），均为已知或非阻塞项。

所有验证命令通过（3 stress tests, 20 watch/event-stream tests, pyright 0 errors）。无生产代码变更，无 Slice 4/5 越界行为。中文 docstring 和类型标注满足项目约束。
