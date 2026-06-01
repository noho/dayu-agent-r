# WU-STRESS-01 Slice 3 Code Review

## Gate

- **Gate**: code review (implementation review gate)
- **Review role**: AgentDS code review specialist
- **Review artifact path**: `docs/reviews/wu-stress-01-code-review-slice3-ds-20260601.md`

## Reviewed Target

- **Work Unit**: WU-STRESS-01 Host Crash / Recovery / Watch Production Stress Suite
- **Slice**: Slice 3 — Sustained watch stress with slow consumer and reconnect
- **Plan reference**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md` (Slice 3 节)
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice3-codex-20260601.md`
- **Reviewed files**:
  - `tests/host/stress_support.py` (+150 lines approx)
  - `tests/host/test_host_production_stress.py` (+360 lines approx)
- **Diff baseline**: 当前工作区未提交 diff (对比 `HEAD`)
- **Verification**:
  - `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q`: **1 passed, 2 deselected** (0.73s)
  - `python -m pyright tests/host/stress_support.py tests/host/test_host_production_stress.py`: **0 errors, 0 warnings, 0 informations**

## Conclusion

**PASS** — 4 LOW severity findings, 0 MEDIUM, 0 HIGH, 0 BLOCKING.

Slice 3 实现正确地建立了 sustained watch stress 场景，覆盖 3 sessions / 18 mixed terminal runs，primary watcher 观察所有 terminal，secondary reconnect 不要求 replay disconnect gap，consumer cancel 四步验证真实有效，watch lag 计算有意义且最终 drain 到 0，outbox/durable gap diagnostic 可信。无生产代码越界。未实现 Slice 4-5。强类型、docstring 满足项目约束。

现存问题集中在：部分 FAILED behavior 分配存在理论竞态窗口（但实际确定性环境未触发）；watch_lag_samples 为全局而非按 session 采样（plan 要求但实现覆盖的总量等价）；辅助断言存在弱条件。上述均不阻塞代码合并，但应在 Slice 5 或后续 cleanup 中修复。

## Findings

### F-01 · 未修复 · LOW · `behavior_for_run` docstring 未反映 queue 行为变更

**位置**: `tests/host/stress_support.py:446-452`

`behavior_for_run` 方法在 Slice 3 新增了 `_queued_behaviors` 队列检查分支（先查 `_run_behaviors` dict，再查 `_queued_behaviors` 队列，最后回退 `_default_behavior`）。但其 docstring 仍写"未配置时返回默认行为"，未提及队列回退语义。

**Why LOW**: 代码行为正确，仅 docstring 滞后；不影响测试正确性。

### F-02 · 未修复 · LOW · 部分 FAILED behavior 使用 race-prone `set_run_behavior` 而非 `enqueue_run_behavior`

**位置**: `tests/host/test_host_production_stress.py:840-865`

在 `test_sustained_watch_slow_consumer_reconnect_stress` 中，3 处在 `await _submit_followup(...)` 返回后再调用 `factory.set_run_behavior(run_id, FAILED)` 的场景（`session1_failed_run_id`、`session1_second_failed_run_id`、`session2_tail_failed_run_id`）。submit 返回后、`set_run_behavior` 完成前，scheduler 可能在另一个 asyncio task 中 dispatch 并 accept worker，此时 `behavior_for_run` 会回退到 default (FINAL) 而非 FAILED。

对比 `session2_failed_run_id` 使用了安全的 `_submit_scripted_followup`（先 `enqueue_run_behavior` 再 submit），正确避免了竞态。

**Why LOW**: 当前确定性测试环境（lane_capacity=3、多个 BLOCKING_FINAL 占 lane）下实际不发生竞态；即使发生，测试结果会体现为 terminal_statuses 缺少 FAILED 从而被后续断言捕获。但建议统一为 `_submit_scripted_followup` 模式。

### F-03 · 未修复 · LOW · `gap_diagnostics_ok` 命名与实际检查内容不匹配

**位置**: `tests/host/test_host_production_stress.py:501-509`

```python
@property
def gap_diagnostics_ok(self) -> bool:
    return self.outbox_gap_run_count >= 3
```

该属性名为 `gap_diagnostics_ok`，暗示覆盖"断开窗口 terminal 的 primary/public/outbox/durable 证明"。但实际只检查 outbox 覆盖率（≥3）。disconnect gap 的 primary/public/durable 证明分别由 `primary_observed_all_terminals`、`public_snapshots_terminal`、`terminal_dedupe_ok` 在其他 predicate 中覆盖。这导致 `failure_boundary` 中 `gap_diagnostics_ok` 失败会映射到 `"projection"` 边界，但实际上只反映 outbox 维度。

**Why LOW**: gap proof 被分布在多个 property 中合起来完整覆盖，单独这个 property 不够全面不影响正确性；命名和边界映射可优化。

### F-04 · 未修复 · LOW · `watch_lag_samples` 为全局跨 session 而非按 session 采样

**位置**: `tests/host/test_host_production_stress.py:739-741` (采样点), `tests/host/test_host_production_stress.py:1000` (lag 计算)

Plan 要求"记录每个 session watch_lag_samples"。当前实现使用一个共享 `asyncio.Queue` 汇总所有 3 个 primary watcher 的观测，`_record_watch_lag_sample` 读取的是跨 session 全局最新 observed sequence 与全局 EventLog latest sequence 的差值。`watch_lag_samples` 是标量 tuple，无法区分 per-session lag。

**Why LOW**: 3 个 session 各 6 个 terminal，并发消费且延迟相同，全局 lag 近似等于 per-session lag。final_watch_lag drain 到 0 的结论不受影响。但若未来场景中 session 间 terminal 速率不均，全局采样会掩盖单个 session lag 异常。

## Open Questions / Residual Risk

1. **Secondary reconnect 无 explicit negative assertion**: 测试通过 `consume_terminals(expected_count=1)` 隐式证明 reconnect watcher 只看到 reconnect 后提交的 terminal（否则 `expected_count=1` 会在看到 gap event 后提前返回，导致 reconnect task 返回不包含 reconnect-final 的事件）。但缺少显式断言如 "reconnect events 中不包含 gap run ids"。当前依赖 timeout/expected_count 约束间接保证，可读性不如显式否定断言。

2. **Double-close in try/finally**: `primary_watchers` 在 try 块正常路径中被 `close_host_event_iterator` 关闭，finally 块中再次 `close`（通过 `suppress(Exception)` 抑制）。Python async generator 的 `aclose()` 对已关闭 generator 是 no-op（PEP 525），因此无害，但清理逻辑双写是代码异味，可能掩盖 try 块中部分 watcher 未正确关闭的 bug。

3. **`watch_lag_ok` 中 `max(watch_lag_samples) < latest_event_sequence` 是弱断言**: `latest_event_sequence` 在全部 terminal drain 后读取，包含所有终端事件的序号总数。中间采样点的 `latest_event_sequence` 必然更小，因此 `max(lag_samples)` 几乎一定小于最终 `latest_event_sequence`。更强的断言是检查各采样点 lag 值单调递减或最终 drain。当前条件仅在 EventLog 被异常清空或 watcher 看到未来序号时才失败——这两种情况都不可能发生。

4. **Stress suite 1 passed / 2 deselected**: 当前 `test_sustained_watch_slow_consumer_reconnect_stress` 是 Slice 3 唯一的新增 stress case。Slice 1 sentinel 和 Slice 2 crash 测试在 `-k sustained_watch` 过滤下被正确 deselect。需要独立验证 Slice 2 测试未被 Slice 3 改动破坏。

## Controller Decision Status

- **Decision**: `PENDING_CONTROLLER_REVIEW`
- **Recommended action**: ACCEPT — findings 均为 LOW，无需修复即可合并 Slice 3。
- **Blocking**: NO

## Artifact Path

`docs/reviews/wu-stress-01-code-review-slice3-ds-20260601.md`
