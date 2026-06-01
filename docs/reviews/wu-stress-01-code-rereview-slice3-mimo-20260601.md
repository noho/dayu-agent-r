# WU-STRESS-01 Slice 3 Re-Review (AgentMiMo)

## Scope

- **Mode**: current changes (re-review after fix)
- **Branch**: test/host-stress-suite
- **Base**: main
- **Output file**: docs/reviews/wu-stress-01-code-rereview-slice3-mimo-20260601.md
- **Included scope**: tests/host/stress_support.py, tests/host/test_host_production_stress.py (Slice 3 path only), Slice 3 artifacts
- **Excluded scope**: Slice 1/2/4/5 behavior, production code (dayu/**), non-Slice 3 helpers
- **Parallel review coverage**: 无

## Result

**PASS**

未发现实质性问题。所有 controller-accepted findings 均已关闭，fix 实现正确，无 Slice 4/5 行为侵入，无生产代码变更，中文 docstring 和类型合规。

## Controller-Accepted Findings Validation

### MIMO-F01 / DS-F02: post-submit `set_run_behavior` race — CLOSED

- **验证**: `set_run_behavior` 在 Slice 3 测试路径中零调用。所有行为绑定均通过 `_submit_scripted_followup` 实现，该函数先调用 `factory.enqueue_run_behavior(behavior)` 再调用 `_submit_followup`。
- **证据**:
  - `stress_support.py:432-444` 新增 `enqueue_run_behavior`，行为入队到 `_queued_behaviors`。
  - `stress_support.py:446-465` `behavior_for_run` 查找顺序：显式 run 行为 → 队列行为 → 默认行为。
  - `test_host_production_stress.py:1103-1125` `_submit_scripted_followup` 先 enqueue 再 submit 再 wait accepted。
  - 所有 18 个 Slice 3 Run 均通过 `_submit_scripted_followup` 或 `_submit_followup_waiting_for_accept` 提交，无 post-submit 行为赋值。
- **结论**: deterministic 行为绑定在 submit 前完成，调度窗口竞态已消除。

### DS-F01: `behavior_for_run` docstring — CLOSED

- **验证**: docstring 已更新，明确记录查找顺序。
- **证据**: `stress_support.py:446-458` docstring 写明："查找顺序固定为：显式 run_id 行为、预提交的下一次 accept 队列行为、factory 默认行为"。

### MIMO-F02: `close_host_event_iterator` ownership docstring — CLOSED

- **验证**: docstring 已更新，明确 stress helper 归属和边界。
- **证据**: `stress_support.py:587-598` docstring 写明："本 helper 镜像 recovery 测试中的 watch iterator 清理语义，但归属 WU-STRESS-01 stress helper：它不是兼容 wrapper，不是生产生命周期抽象，也不表达 Host close 治理。"

### MIMO-F03: named thresholds — CLOSED

- **验证**: 所有硬编码阈值已替换为命名常量。
- **证据**:
  - `test_host_production_stress.py:91` `_SLICE3_SECONDARY_FIRST_TERMINAL_COUNT = 2`
  - `test_host_production_stress.py:92` `_SLICE3_SECONDARY_RECONNECT_TERMINAL_COUNT = 1`
  - `test_host_production_stress.py:93` `_SLICE3_DISCONNECT_GAP_RUN_COUNT = 3`
  - `test_host_production_stress.py:94` `_SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT = _SLICE3_RUN_COUNT`
  - `Slice3WatchDiagnostics.reconnect_ok` 和 `disconnect_gap_terminal_truth_ok` 均引用这些常量。

### DS-F03: `gap_diagnostics_ok` rename/split — CLOSED

- **验证**: 原 predicate 已拆分为两个精确 predicate。
- **证据**:
  - `outbox_gap_coverage_ok` (`test_host_production_stress.py:512-519`): 仅检查 Outbox 覆盖，`failure_boundary` 映射为 `"projection"`。
  - `disconnect_gap_terminal_truth_ok` (`test_host_production_stress.py:521-542`): 检查 primary/public/outbox/durable 四路证明，`failure_boundary` 映射为 `"watch"`。
  - `failure_boundary` 属性 (`test_host_production_stress.py:562-583`) 先检查 `outbox_gap_coverage_ok` 返回 `"projection"`，再检查 `disconnect_gap_terminal_truth_ok` 返回 `"watch"`，优先级正确。

### DS-F04: per-session watch lag samples — CLOSED

- **验证**: lag 诊断已按 session 独立采集，仅在 summary 填充时拍平。
- **证据**:
  - `Slice3WatchDiagnostics.watch_lag_samples_by_session: tuple[tuple[int, ...], ...]` (`test_host_production_stress.py:416`)
  - `_record_all_watch_lag_samples` (`test_host_production_stress.py:1268-1310`) 按 session 独立读取 terminal count 并追加到 `samples_by_session[index]`。
  - `watch_lag_ok` (`test_host_production_stress.py:491-509`) 验证每个 session 有样本、最大 lag 在阈值内、最终 lag drain。
  - summary 填充使用 `_flatten_int_groups(diagnostics.watch_lag_samples_by_session)` (`test_host_production_stress.py:1075`)。
  - lag 计算基于 per-session terminal count watermark，非全局 EventLog sequence，避免跨 session 误膨胀。

### MIMO-F04: redundant `tuple([...])` — CLOSED

- **验证**: diff 中移除了多处 `tuple([...])` 改为 `tuple(...)` 或直接构造。
- **证据**: 多处格式化变更，无语义变化。

## Additional Checks

### No Slice 4/5 behavior — PASS

- Slice 3 测试仅覆盖 sustained watch / slow consumer / consumer cancel / reconnect / disconnect gap 诊断。
- 未引入 `InspectableStressWorkerFactory`、`wait_all_runs_terminal`、`read_host_instances`、`verify_lane_released` 等 Slice 4 helper。
- 未引入 `HostStressScenario`、`test_mixed_host_stress_deterministic_fault_injection` 等 Slice 5 结构。

### No production code changes — PASS

- `git diff --stat HEAD -- dayu/` 无输出，确认无生产代码变更。

### Chinese docstrings and types — PASS

- 所有新增函数、dataclass、方法均有完整中文 docstring，包含参数、返回值、异常说明。
- 所有参数和返回值均有类型注解，无 `Any`、`object`、裸 `dict`/`list`。
- `cast(AsyncGenerator[HostEvent, None], iterator)` 用于 `close_host_event_iterator` 中类型转换，理由充分（`AsyncIterator` 无 `aclose`，需转为 `AsyncGenerator`）。

### Validation results — PASS

- `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q`: 1 passed, 2 deselected
- `pytest tests/host/test_watch_session_events.py tests/host/test_public_event_stream.py -q`: 20 passed
- `python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

- `read_latest_event_sequence` 在 `stress_support.py` 中定义（line 603）但当前未被任何测试文件导入或使用。它是 per-session lag 计算方法引入前的全局 lag helper，当前被 `read_session_terminal_sequences` 取代。不影响正确性，未来 Slice 可能使用，也可考虑移除。
- `_SLICE3_WATCH_LAG_EVENT_TOTAL_LIMIT` 设为 `_SLICE3_RUN_COUNT`（18），但 per-session 最大 lag 上界为 `_SLICE3_RUNS_PER_SESSION`（6），因此该阈值实质上不会被触发。命名常量满足 controller 要求，但阈值偏宽松。
- stress 场景仍为 deterministic bounded，不覆盖 randomized fuzz 或长时间真实压力。
