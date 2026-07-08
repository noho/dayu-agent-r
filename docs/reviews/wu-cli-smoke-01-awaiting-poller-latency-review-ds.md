# Code Review — awaiting poller latency fix (AgentDS)

## Scope

- Mode: current changes
- Branch: `phase/host-issues-control`
- Base: `main`
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-review-ds.md`
- Included scope: `dayu/host/wait_adapter.py`, `dayu/host/durable/state.py`, `tests/host/test_wait_adapter_polling.py`, `tests/host/test_wait_poller_runtime.py`, `docs/host/design.md`, `dayu/host/README.md`, `tests/README.md`
- Excluded scope: 无
- Parallel review coverage: 无（单 reviewer 全链路走读）
- Background artifact: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-fix-codex.md`

## Review 要点覆盖

| # | 审查项 | 结论 |
|---|--------|------|
| 1 | Root cause 是否由直接证据支撑 | 是。日志/DB/代码三源对齐 |
| 2 | 通用 poll path correctness（无 callback/wakeup） | 成立。claim SQL 的 `poll_next_observe_at <= now` 是唯一 eligibility 条件 |
| 3 | Idle 是否真的减少 DB 空查 | 是。idle_interval=5s vs poll_interval=1s，额外 `_next_poll_delay_seconds` SELECT 被长间隔摊薄 |
| 4 | Next due sleep 计算/时区安全 | 正确。ISO 8601 UTC 字符串 SQL 可比序；`max(delay, 0.0)` 防负延迟；idle cap 防长睡 |
| 5 | Wakeup race-safe，不丢信号不忙循环 | race-safe。唯一丢失场景是冗余 wakeup；不会 busy loop |
| 6 | Backoff 边界保留 | 全部 8 个错误路径保留 `_release_with_backoff`；仅 not_ready 改为 `_release_not_ready` |
| 7 | Tests/pyright/README 充分性 | pyright 0 err；tests 35 passed；README 更新准确。存在 test gap |

## Findings

### F-1-未修复-中-caller 有活动时固定用 poll_interval_seconds sleep，不读取 durable next_observe_at 做精确睡眠

- **入口/函数**: `_next_loop_interval_seconds` → `_sleep_until_next_poll`
- **文件(行号)**: `dayu/host/wait_adapter.py:1541-1558`
- **输入场景**: `poll_once()` 返回有活动结果（如 `not_ready=1`），但 `not_ready_observe_interval_seconds` 与 `poll_interval_seconds` 独立配置且值不同。
- **实际分支**: `_poll_result_has_activity(result)` 返回 `True` → 直接返回 `policy.poll_interval_seconds`，不读取 `result.next_poll_delay_seconds` 也不查询 durable next_observe_at。
- **预期行为**: 有活动时也应取 `min(poll_interval_seconds, 实际 next_due_delay)` 避免超过 next_observe_at 的无意义睡眠，或至少在不匹配时使用 next_due 对齐。
- **实际行为**: 固定 sleep `poll_interval_seconds`。
  - 若 `not_ready_observe_interval_seconds < poll_interval_seconds`：sleep 比实际下次可观察时间更长，延迟下一次 observe。
  - 若 `not_ready_observe_interval_seconds > poll_interval_seconds`：提前醒来发现 nothing claimable，产生一次额外的空 DB 查询后才进入 idle sleep。
- **直接证据**:
  - `_next_loop_interval_seconds` 第 1551-1558 行：`if not _poll_result_has_activity(result):` 分支做精确计算，但 `else` 分支（第 1558 行）直接返回 `policy.poll_interval_seconds`。
  - `_release_not_ready` 第 1218-1222 行写入 `next_observe_at = now + _not_ready_delay_seconds(self._policy)`，此值在 `_next_loop_interval_seconds` 的有活动分支中完全未被消费。
  - 当前默认值 `poll_interval_seconds = 1.0` 与 `not_ready_observe_interval_seconds = 1.0` 碰巧相等，掩盖了此问题。
- **影响**: 配置独立调优时（例如将 `not_ready_observe_interval_seconds` 缩短到 0.5s 以实现更快的 ready 检测），poller 实际仍按 1.0s 轮询，达不到预期精度。对于默认配置无实际影响。
- **建议改法和验证点**:
  - 在有活动分支中复用 `result.next_poll_delay_seconds` 逻辑（当前仅在无活动分支使用），或直接从刚写入的 `next_observe_at` 计算 sleep。
  - 验证点：`not_ready_observe_interval_seconds = 0.3`, `poll_interval_seconds = 1.0` 时，not_ready 后的下一次 poll 应在 ~0.3s 内发生，而非 ~1.0s。
- **修复风险（低）**: 改动仅影响 sleep 计算，不涉及 claim/release/resolve 语义。需确保 `next_poll_delay_seconds` 在有活动且 observed>0 时也能返回有效值（当前第 1047 行 `observed > 0` 直接返回 `None`）。
- **严重程度（中）**: 当前默认配置无影响，但属于配置契约断层 — policy 字段 `not_ready_observe_interval_seconds` 的语义承诺（"下一次观察间隔"）在 sleep 层被 `poll_interval_seconds` 覆盖。

### F-2-未修复-低-test_pure_poll_observes_ready_after_not_ready_policy_cadence 混用 ManualClock 与真实 sleep

- **入口/函数**: `test_pure_poll_observes_ready_after_not_ready_policy_cadence`
- **文件(行号)**: `tests/host/test_wait_poller_runtime.py:703-741`
- **输入场景**: 测试使用 `_ManualClock` 模拟时间，但 background thread 的 `_sleep_until_next_poll` 内部是真实 `threading.Event.wait(interval_seconds)`。
- **实际分支**: `_ManualClock.advance(0.03)` 只在 test thread 中推进模拟时钟；background thread 的 `_wakeup_event.wait()` 依赖真实时间流逝。
- **预期行为**: 模拟时钟与真实 sleep 应被显式消除竞态，或使用纯模拟时钟的 sleep 机制。
- **实际行为**: 测试通过 `_wait_until` (deadline 1.0s, poll 0.005s) 吸收竞态。当 `_wakeup_event.wait(0.03)` 在 `clock.advance(0.03)` 之前返回时，background thread 会多做一次空 poll round（`observed=0`），随后再次 `_sleep_until_next_poll`。测试只检查 `adapter.poll_count == 2` 和最终 `RESOLVED` 状态，不检查 poll_rounds 精确值，所以仍通过。
- **直接证据**:
  - 第 730 行 `clock.advance(0.03)` — 仅在 test thread 执行。
  - 第 625-626 行 `supervisor.open()` 启动 background thread，其 `_sleep_until_next_poll`（`wait_adapter.py:1462`）使用 `_wakeup_event.wait()` 真实阻塞。
  - 这两个时间源不同步，构成测试脆弱性。
- **影响**: 测试可能在极端负载或调度延迟下偶发失败。当前通过 35/35，但不可靠。
- **建议改法和验证点**:
  - 将 `_sleep_until_next_poll` 的等待机制也抽象为可注入端口（如 `WaitPollSleeper` protocol），测试注入模拟 sleeper。
  - 或使用 `drain_once_for_test` 替代 background thread，在 test thread 中手动推进时间和 poll 步进。
- **修复风险（低）**: 测试重构，不涉及生产代码。
- **严重程度（低）**: 不影响生产正确性，仅测试可维护性。

### F-3-未修复-低-空轮询时 `_next_poll_delay_seconds` 额外 DB 读增加单轮查询数

- **入口/函数**: `WaitPoller.poll_once` → `_next_poll_delay_seconds`
- **文件(行号)**: `dayu/host/wait_adapter.py:985-988, 1036-1056`
- **输入场景**: 单轮 poll 无 claimable wait record（`observed=0, claim_conflicts=0`）。
- **实际分支**: 第 987 行 `observed=0 and claim_conflicts=0` → 调用 `_next_poll_delay_seconds` → 第 1050-1052 行执行 `run_read(_ReadNextPollDueAtOperation(...))`。
- **预期行为**: 理想情况下空轮询不额外增加查询数。
- **实际行为**: 空轮询从旧代码的 1 query/round（仅 claim SELECT）变为 2 queries/round（claim SELECT + next_due SELECT）。但由于 idle interval 从 1s 拉长到 5s，总 QPS 从 ~1 降到 ~0.4，净效果仍是降低。
- **直接证据**: 第 1050-1052 行 `self._transaction_runner.run_read(_ReadNextPollDueAtOperation(...))`。
- **影响**: 净 DB 负载降低（~60%），但单轮查询数翻倍。对于有大量 active wait 但均未到期的场景，影响稍大。
- **建议改法和验证点**: 可将 `_next_poll_delay_seconds` 的 DB 读与 claim SELECT 合并为一个查询（在 `claim_wait_record_for_poll` 返回 `NOT_FOUND` 时携带 next_due 信息）。当前改动可接受，后续可优化。
- **修复风险（低）**: 性能优化，不影响正确性。
- **严重程度（低）**: 当前净效果为正（减少总 DB 负载）。

## Open Questions

1. **`_release_not_ready` 无条件写入 `backoff_attempt=0`**（`wait_adapter.py:1224`）：若 wait record 此前因 adapter 临时异常被写入 `backoff_attempt=3`，随后 adapter 恢复并返回 `not_ready`，backoff counter 被重置为 0。这是设计意图（正常运行中不累计错误退避），但若 adapter 在 error 与 not_ready 之间振荡，可能导致退避被反复重置。当前看风险极低，因为 adapter error 通常是持续性的（网络不可达等），不会突然变为 not_ready。

2. **`_wakeup_event` 未在 `open()` 中 clear**（`wait_adapter.py:1291-1316`）：若 `close()` 后立即 `open()`（当前 `open()` 在 `FAILED` 或已 `_opened` 状态拒绝重开，所以不会发生），但若后续支持 reopen，需注意。当前无影响。

## Residual Risk

- **真实 SEC 下载 smoke 未跑**：Codex artifact 中建议的真实 interactive smoke 未执行，修复只在单元测试和集成测试层面验证。
- **`poll_interval_seconds` 与 `not_ready_observe_interval_seconds` 独立配置导致的非最优 sleep**：见 F-1。当前默认值协调，生产使用默认值无影响。
- **没有 adversarial test 覆盖以下场景**：
  - `_next_poll_delay_seconds` 返回的 delay 来自另一个 poller 的 `claim_expires_at` 而非本 poller 的 `next_observe_at`。
  - `_release_not_ready` 的 CAS 冲突路径（第 1231-1233 行的 `return 1`）。
  - 连续快速 `wakeup()` 调用（>10次/s）下的行为。
  - `poll_next_observe_at` 恰好等于 `now` 的边界条件（`<=` vs `<`）。
- **`_next_poll_delay_seconds` 中 `now` 与 claim 阶段 `now` 可能不同**：由于两次 `self._clock.now()` 调用之间有时间差（在 claim batch loop 中多次调用 vs 在 `_next_poll_delay_seconds` 中单独调用），计算出的 delay 可能略短于实际。`max(delay, 0.0)` 防止负值，但无法防止偏短导致的提前唤醒。

## 结论

**Pass with findings.**

Root cause 证据充分（日志 30s/60s 间隔精确匹配指数退避公式，DB 记录确认，代码路径可追踪）。修复方向正确：not_ready 改为短间隔复查而非错误退避，idle 拉长 sleep 间隔，空轮询抑制日志。Backoff 边界全部保留。Pyright 零错误，35 个测试通过。

主要 finding F-1（有活动时固定用 poll_interval_seconds 而非精确 next_due sleep）在默认配置下无影响，但属于 `not_ready_observe_interval_seconds` 配置项的契约断层，建议后续修复。其余 findings 为低严重度。
