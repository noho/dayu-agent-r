# WU-STRESS-01 Slice 3 Code Review

## Gate

- **Gate**: code-review
- **Work Unit**: WU-STRESS-01 Host Production Stress Suite
- **Review role**: AgentMiMo code review specialist
- **Review target**: 工作区未提交的 Slice 3 diff (`tests/host/stress_support.py`, `tests/host/test_host_production_stress.py`)
- **Plan**: `docs/host/wu-stress-01-host-production-stress-suite-plan.md`
- **Implementation artifact**: `docs/reviews/wu-stress-01-implementation-slice3-codex-20260601.md`

## Reviewed Target

Slice 3 实现 diff：`tests/host/stress_support.py`（新增 `enqueue_run_behavior`、`consume_terminals`、`close_host_event_iterator`、`read_latest_event_sequence`、`read_event_log_count`、`read_session_terminal_sequences`）和 `tests/host/test_host_production_stress.py`（新增 `test_sustained_watch_slow_consumer_reconnect_stress`、`Slice3WatchDiagnostics`、多个 private helper）。

## Conclusion

**PASS (with findings)**。Slice 3 实现正确覆盖了 3 sessions / 18 mixed terminal runs 的持续 watch stress；primary watcher 观察所有 terminal；secondary reconnect 只要求后续 terminal 不要求 replay gap；consumer cancel 四步验证真实；watch lag 计算有意义且最终 drain；outbox gap diagnostic 可信。存在 2 个 medium findings 和 2 个 low findings，无 blocking issues。

## Findings

### F01-未修复-MEDIUM-set_run_behavior-after-submit 存在潜在调度竞态

**位置**: `tests/host/test_host_production_stress.py:845-848`, `861-864`, `920-923`

**问题**: 三处 `set_run_behavior` 在 `await _submit_followup(...)` 之后调用。Plan §3 明确要求使用 `enqueue_run_behavior` 在 submit 之前入队，以确保 deterministic behavior 分配。当前写法依赖 scheduler dispatch 不在 `submit_followup` 返回和 `set_run_behavior` 之间触发，这是一个隐式时序假设。

**证据**: `_submit_scripted_followup` helper 已正确使用 `enqueue_run_behavior` 先入队后提交；但 `session1_failed_run_id`、`session1_second_failed_run_id`、`session2_tail_failed_run_id` 三处使用了 `set_run_behavior` after submit 模式。

**影响**: 测试通过（scheduler dispatch poll interval 10ms 提供了足够缓冲），但不是 deterministic 保证。若 scheduler 行为变化（如 dispatch 在 submit 内触发），这些 run 可能获得默认 FINAL 行为而非 FAILED。

**建议**: 改为 `_submit_scripted_followup(..., StressWorkerBehavior.FAILED)` 保持一致性。

### F02-未修复-MEDIUM-close_host_event_iterator 重复实现

**位置**: `tests/host/stress_support.py:581-592` vs `tests/host/recovery_support.py:524-531`

**问题**: `close_host_event_iterator` 在 `stress_support.py` 中完整复制了 `recovery_support.py` 的实现（含 `cast(AsyncGenerator, iterator).aclose()`）。Plan §5 要求"不得复制 recovery_support.py 中已有多进程 owner / marker / stale liveness 逻辑的大段实现。若只需要语义微调，应写薄 wrapper"。虽然该函数只有 3 行，但它没有 docstring 说明与 `recovery_support` 的复用关系和增量职责。

**影响**: 两处独立维护同一实现，未来修改可能不一致。测试文件 import 从 `recovery_support` 切换到 `stress_support`，但 `test_recovery_multiprocess.py` 仍从 `recovery_support` import。

**建议**: 添加 docstring 说明复用关系，或改为从 `recovery_support` re-export 薄 wrapper。

### F03-未修复-LOW-reconnect_ok 和 gap_diagnostics_ok 使用魔法数字

**位置**: `tests/host/test_host_production_stress.py:482`, `509`

**问题**:
- `reconnect_ok`: `len(self.secondary_first_events) >= 2 and len(self.secondary_reconnect_events) >= 1` 中的 2 和 1 是魔法数字，应从 `_SLICE3_*` 常量派生。
- `gap_diagnostics_ok`: `self.outbox_gap_run_count >= 3` 中的 3 是魔法数字，应与 `gap_run_ids` 长度关联。

**影响**: 维护性风险。若测试规模变化，这些硬编码阈值需要手动同步。

### F04-未修复-LOW-tuple([...]) 语法冗余

**位置**: `tests/host/test_host_production_stress.py:755-760`, `986`

**问题**: `tuple([await ... for ...])` 应简化为 `tuple(await ... for ...)`。列表推导式创建了不必要的中间 list。

**影响**: 微小的性能和代码风格问题。

## Validation Results

| 命令 | 结果 |
|------|------|
| `pytest -o addopts="" -m stress tests/host/test_host_production_stress.py -k sustained_watch -q` | 1 passed, 2 deselected (0.72s) |
| `pytest tests/host/test_recovery_multiprocess.py tests/host/test_watch_session_events.py -q` | 8 passed (2.79s) |
| `python -m pyright dayu/ tests/ utils/` | 0 errors, 0 warnings, 0 informations |

## Correctness / Stability 逐项检查

### 3 sessions / 18 mixed terminal runs

**PASS**。`_SLICE3_SESSION_COUNT=3`、`_SLICE3_RUNS_PER_SESSION=6`、`_SLICE3_RUN_COUNT=18`。Session 0: probe(BLOCKING_FINAL) + initial-final(FINAL) + 3 gap runs(FAILED/FINAL/FAILED) + reconnect-final(FINAL) = 6。Session 1: active(BLOCKING_FINAL) + cancelled + failed + final + second-failed + tail-final = 6。Session 2: final + failed + active(BLOCKING_FINAL) + cancelled + tail-final + tail-failed = 6。总 18。

### Primary watcher 观察所有 terminal

**PASS**。`primary_observed_all_terminals` 属性比较 primary_events 的 run_id 集合与 durable_observations 的 run_id 集合。`scheduler_drained` 要求 `len(self.primary_events) == _SLICE3_RUN_COUNT`。

### Secondary reconnect 只要求后续 terminal

**PASS**。`reconnect_ok` 要求 `secondary_first_events >= 2`（断开前的 2 个 terminal）和 `secondary_reconnect_events >= 1`（重连后新提交的 1 个 terminal）。不要求 replay gap。

### Consumer cancel 四步验证

**PASS**。
1. `event_log_count_before_cancel = read_event_log_count(tmp_path)`（fresh short read）
2. `cancel_probe_consumer.cancel()` + `suppress(CancelledError)`
3. `probe_after_consumer_cancel = await host.get_run(probe_run_id)` → `assert not _is_terminal_status(...)`，`worker_cancel_count_after_consumer_cancel = len(factory.cancel_reasons)` == 0
4. `event_log_count_after_cancel = read_event_log_count(tmp_path)` → `consumer_cancel_ok` 检查 count 不变

### Watch lag 计算有意义且最终 drain

**PASS**。`_record_watch_lag_sample` 通过 `_drain_observed_event_queue` 提取 primary 最大 event_sequence，与 `read_latest_event_sequence` 的 fresh short read 比较。`compute_watch_lag = max(0, latest - last_seen)`。最终 drain 在所有 primary_tasks 完成后执行，`final_watch_lag` 应为 0。`watch_lag_ok` 要求 `max(samples) < latest_event_sequence` 和 `final_watch_lag <= 0`。

### Outbox/durable gap diagnostic 可信

**PASS**。`_read_outbox_gap_run_count` 通过 public `read_outbox_terminal_items` API 读取 session 0 的 terminal items，与 `gap_run_ids` 交集计数。`gap_diagnostics_ok` 要求覆盖 >= 3（3 个 gap run）。同时 durable_observations 和 primary_events 也覆盖这些 run。

### 异步测试是否 flaky 或用不可控 sleep

**PASS（有条件）**。所有 poll loop 使用 `asyncio.sleep(0.01)` 配合 5 秒 deadline。`consume_terminals` 使用 `asyncio.sleep(delay_seconds)` where `delay_seconds=0.035` 作为慢消费模拟。无不可控 sleep。但 F01 的 `set_run_behavior` after submit 模式依赖隐式调度时序。

### Diagnostics/helper 是否 god function/god dataclass

**PASS**。`Slice3WatchDiagnostics` 是 frozen+slots dataclass，12 个字段，每个 property 单一职责。模块级 private helper（`_submit_scripted_followup`、`_cancel_run`、`_wait_run_status` 等）职责单一。无 god function/god dataclass。

### 无 production code 越界

**PASS**。diff 只修改 `tests/host/stress_support.py` 和 `tests/host/test_host_production_stress.py`。未修改 `dayu/host/**`、`dayu/engine/**` 等 production code。`recovery_support.py` 无变更。

### 未实现 Slice 4-5

**PASS**。Implementation artifact 明确声明"Slice 3 implementation complete. No Slice 4 or Slice 5 implementation performed."

### Docstring / 强类型 / 禁止 Any-object-裸 dict

**PASS**。所有新增函数和 dataclass 有完整中文 docstring（参数、返回值、异常）。所有参数和返回值有类型注解。无 `Any`、`object`、裸 `dict`/`list`。`AsyncIterator[HostEvent]` 通过 `cast(AsyncGenerator[HostEvent, None], ...)` 处理 aclose。

## Open Questions / Residual Risk

1. **F01 竞态风险**: `set_run_behavior` after submit 在当前 scheduler 实现下稳定，但不是 deterministic 保证。建议 Slice 4/5 统一使用 `enqueue_run_behavior`。
2. **F02 维护风险**: `close_host_event_iterator` 双份实现。建议后续 slice 统一复用路径。
3. **测试规模**: 3 sessions / 18 runs / 0.72s 是小规模 deterministic stress。不覆盖慢盘、高延迟、大规模场景。

## Controller Decision Status

- **Decision**: PASS with findings
- **Blocking**: 无
- **Findings requiring fix before merge**: F01 (medium, 竞态风险), F02 (medium, 重复实现)
- **Findings for follow-up**: F03, F04 (low, 维护性)

## Artifact Path

`docs/reviews/wu-stress-01-code-review-slice3-mimo-20260601.md`
