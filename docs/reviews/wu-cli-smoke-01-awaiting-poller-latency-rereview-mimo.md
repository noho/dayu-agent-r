# Code Review — awaiting poller latency re-review (AgentMiMo)

## Scope

- Mode: current changes (re-review of narrow re-fix)
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-rereview-mimo.md`
- Included scope: `dayu/host/wait_adapter.py`, `dayu/host/durable/state.py`, `tests/host/test_wait_poller_runtime.py`
- Excluded scope: 无
- Parallel review coverage: 无（单 reviewer 全链路走读）
- Background artifacts:
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-review-ds.md`
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-refix-codex.md`

## DS Finding 状态

| # | DS Finding | Codex 声称状态 | 实际状态 |
|---|-----------|--------------|---------|
| F-1 | 有活动时不消费 next due 的配置契约断层 | 已修复 | **已关闭** |
| F-2 | ManualClock 与真实 sleep 混用的测试脆弱性 | 已修复 | **未关闭** |
| F-3 | 空轮询 next-due 额外 DB 读 | defer | **defer 合理** |

## Findings

### F-1-未修复-中-test_background_loop_uses_not_ready_due_before_poll_interval 偶发失败（~60%）

- **入口/函数**: `test_background_loop_uses_not_ready_due_before_poll_interval`
- **文件(行号)**: `tests/host/test_wait_poller_runtime.py:683-690`
- **输入场景**: `not_ready_observe_interval_seconds=0.01`, `poll_interval_seconds=0.5`, 使用 `_RealtimeUtcClock` 和 background thread。
- **实际分支**: `_wait_until(lambda: adapter.poll_count == 2, timeout_seconds=0.3)` 返回后，background thread 的 `poll_once()` 已完成 `adapter.poll_wait()` 调用（`poll_count` 递增），但 `_resolve_claimed_wait()` 尚未提交 durable write。
- **预期行为**: 测试应等待 resolve 完成后再断言 `wait_record.status is WaitRecordStatus.RESOLVED`。
- **实际行为**: 测试在 `poll_count == 2` 后立即读 DB，此时 status 仍为 `WAITING`，断言失败。10 次运行中 6 次失败。
- **直接证据**:
  - 第 685 行 `_wait_until(lambda: adapter.poll_count == 2, timeout_seconds=0.3)` — `poll_count` 在 `poll_wait()` 返回时递增（`_SequenceAdapter` 第 240 行），此时 resolve 尚未执行。
  - 第 690 行 `assert wait_record.status is WaitRecordStatus.RESOLVED` — 在 resolve 提交前读 DB。
  - 10 次运行结果：4 passed, 6 failed。
- **影响**: 测试不稳定，CI 中会偶发失败。这正是 DS F-2 指出的同类问题 — background thread 与 test thread 的时间推进不同步。
- **建议改法和验证点**:
  - 方案 A（推荐）：用 `_wait_until(lambda: _read_wait(host._transaction_runner(), seeded.wait_id).status is WaitRecordStatus.RESOLVED)` 替代 `poll_count` 检查，直接等待目标状态。
  - 方案 B：在 `poll_count == 2` 后增加 `_wait_until(lambda: adapter.poll_count == 2 and _read_wait(...).status is WaitRecordStatus.RESOLVED)` 合并条件。
  - 验证点：10 次连续运行全部通过。
- **修复风险（低）**: 测试修复，不涉及生产代码。
- **严重程度（中）**: 测试不稳定会阻碍 CI 和后续开发。DS F-2 的核心问题（两种时间源不同步）未被彻底解决。

### F-2-已关闭-低-DS F-1 配置契约断层

- **入口/函数**: `_next_loop_interval_seconds`
- **文件(行号)**: `dayu/host/wait_adapter.py:1577-1596`
- **修复验证**: `_release_not_ready` 返回 `_ReleaseNotReadySummary(next_poll_delay_seconds=delay_seconds)`，`poll_once` 通过 `_min_optional_delay_seconds` 累积最短 delay，`_next_loop_interval_seconds` 在有活动分支（第 1594-1595 行）消费 `result.next_poll_delay_seconds`。
- **配置不等场景验证**: `not_ready_observe_interval_seconds=0.01`, `poll_interval_seconds=0.5` 时，not_ready 后 `next_poll_delay_seconds=0.01`，`_next_loop_interval_seconds` 返回 0.01 而非 0.5。✓
- **单线程测试**: `test_pure_poll_observes_ready_after_not_ready_policy_cadence` 使用 `drain_once_for_test()` + `_ManualClock`，断言 `first.next_poll_delay_seconds == pytest.approx(0.03)`，验证配置不等时 delay 正确传播。✓
- **结论**: DS F-1 已关闭。

## 重点检查项

### 1. not_ready_observe_interval_seconds 与 poll_interval_seconds 不等时是否按 next due sleep

**成立。** `_release_not_ready` 写入 `next_observe_at = now + not_ready_observe_interval_seconds` 并返回 `next_poll_delay_seconds = not_ready_observe_interval_seconds`。`_next_loop_interval_seconds` 在有活动分支消费此值：

```
wait_adapter.py:1594-1595:
if result.next_poll_delay_seconds is not None:
    return max(result.next_poll_delay_seconds, 0.0)
```

当 `not_ready_observe_interval_seconds=0.01 < poll_interval_seconds=0.5` 时，loop 按 0.01s 唤醒，不被 0.5s poll_interval 拖慢。

### 2. 纯 poll correctness 是否仍成立

**成立。** claim SQL 的 `poll_next_observe_at <= now` 是唯一 eligibility 条件（`durable/state.py` claim 操作未变）。`_release_not_ready` 写入的 `backoff_attempt=0` 重置退避计数，`next_observe_at` 按 `not_ready_observe_interval_seconds` 短间隔设置。空轮询时 `_next_poll_delay_seconds` 查询 `read_next_wait_record_poll_due_at` 返回的最早 due time 用于 sleep 计算。

### 3. wakeup/idle/backoff 语义是否未回退

**未回退。**
- **wakeup**: 新增 `supervisor.wakeup()` 方法设置 `_wakeup_event`，`_sleep_until_next_poll` 使用 `_wakeup_event.wait(interval_seconds)` 支持即时打断。close 和异常路径也设置 wakeup event。✓
- **idle**: 无活动时 `_next_loop_interval_seconds` 返回 `min(next_poll_delay_seconds, idle_poll_interval_seconds)` 或 `idle_poll_interval_seconds`。✓
- **backoff**: 错误路径（`_release_with_backoff`）返回 `int` 而非 `_ReleaseNotReadySummary`，`next_poll_delay_seconds` 保持 `None`，`_next_loop_interval_seconds` 回退到 `policy.poll_interval_seconds`。✓

### 4. 测试是否稳定且覆盖配置不等场景

**部分不稳定。**
- `test_pure_poll_observes_ready_after_not_ready_policy_cadence`: 使用 `drain_once_for_test()` 单线程验证，稳定。✓
- `test_background_loop_uses_not_ready_due_before_poll_interval`: 使用 background thread + `_RealtimeUtcClock`，~60% 偶发失败。✗（见 F-1）
- `test_background_loop_uses_idle_interval_after_empty_round`: 5/5 通过。✓
- `test_wakeup_interrupts_idle_after_new_wait_is_created`: 通过。✓

### 5. pyright/README 是否仍充分

- **pyright**: `0 errors, 0 warnings, 0 informations`。✓
- **README**: Codex artifact 记录已检查 `dayu/host/README.md` 和 `tests/README.md`，本轮只是让实现符合既有文档语义，不需要新增 README 文本。✓

## F-3 Defer 评估

DS F-3（空轮询 next-due 额外 DB 读）defer 合理：
- 当前净 QPS 从 ~1 降到 ~0.4（idle interval 从 1s 拉长到 5s），单轮查询数翻倍但总负载下降。
- 不影响正确性。
- 后续可优化为 claim miss 时携带 next_due 信息，合并为单次查询。

## Open Questions

1. **`_release_not_ready` 无条件写入 `backoff_attempt=0`**（`wait_adapter.py:1254`）：沿用 DS 原始 Open Question。adapter error → not_ready 振荡会反复重置退避。当前风险极低。

2. **`_SequenceAdapter.poll_started_at` 非线程安全**：background thread 写入 `list.append()`，test thread 读取索引。CPython GIL 下通常安全，但严格来说是 data race。见 F-1 根因。

## Residual Risk

- **背景时序测试不稳定**：见 F-1。需修复后重新验证。
- **真实 SEC / Fins 网络 smoke 仍未执行**：沿用上一轮风险。
- **`_next_poll_delay_seconds` 中 `now` 与 claim 阶段 `now` 可能不同**：两次 `self._clock.now()` 调用之间有时间差，计算出的 delay 可能略短。`max(delay, 0.0)` 防止负值。

## 结论

**Pass with findings.**

DS F-1 配置契约断层已关闭：`_next_loop_interval_seconds` 在有活动分支正确消费 `result.next_poll_delay_seconds`，`not_ready_observe_interval_seconds < poll_interval_seconds` 时按短间隔唤醒。单线程 drain 测试稳定覆盖此场景。

DS F-2 未完全关闭：原 ManualClock 混用问题的单线程测试修复正确，但新增的 background 时序测试 `test_background_loop_uses_not_ready_due_before_poll_interval` 存在 race condition（~60% 偶发失败），与 DS F-2 指出的同类问题本质相同。需修复测试等待条件后方可 ship。

DS F-3 defer 合理，不阻塞本轮。
