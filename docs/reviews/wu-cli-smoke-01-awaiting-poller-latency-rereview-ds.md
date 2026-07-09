# Code Review — awaiting poller latency narrow re-fix re-review (AgentDS)

## Scope

- Mode: current changes (narrow re-fix re-review)
- Branch: `phase/host-issues-control`
- Base: `main`（re-fix 基于已合并到分支的原始 fix，本次只审 unstaged working tree changes）
- Output file: `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-rereview-ds.md`
- Input artifacts:
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-review-ds.md`（DS 原始 review）
  - `docs/reviews/wu-cli-smoke-01-awaiting-poller-latency-refix-codex.md`（Codex re-fix 记录）
- Included scope（仅 unstaged changes）:
  - `dayu/host/wait_adapter.py`
  - `dayu/host/durable/state.py`
  - `tests/host/test_wait_poller_runtime.py`
  - `tests/host/test_wait_adapter_polling.py`
  - `dayu/host/README.md`
  - `tests/README.md`
  - `docs/host/design.md`
- Excluded scope: 原 fix 已合并到分支的 committed changes，以及无关的 unstaged 文件
- Parallel review coverage: 无

## Review 要点覆盖

| # | 审查项 | 结论 |
|---|--------|------|
| 1 | DS F-1：有活动时 `next_poll_delay_seconds` 是否被消费 | 已修复。`_release_not_ready` → `_next_poll_delay_seconds` → `_next_loop_interval_seconds` 完整链路已通 |
| 2 | `not_ready_observe_interval_seconds` < `poll_interval_seconds` 时按 next due sleep | 成立。drain_once 测试精确验证 `next_poll_delay_seconds=0.03`，background 测试验证实际 sleep < 0.3s |
| 3 | `not_ready_observe_interval_seconds` > `poll_interval_seconds` 时避免空查 | 成立。next_due 被返回而不是 poll_interval，避免提前唤醒后的空 DB 查询 |
| 4 | 纯 poll correctness（claim eligibility 仍由 durable 决定） | 成立。claim SQL 的 `poll_next_observe_at <= now` 条件未变更；sleep 只影响何时尝试 claim，不影响 claim 资格判断 |
| 5 | Backoff 边界未回退 | 成立。全部 8 个错误/异常路径仍走 `_release_with_backoff`；仅 not_ready 走 `_release_not_ready` |
| 6 | Idle 语义未回退 | 成立。无活动时 `idle_poll_interval_seconds` 为默认 sleep；next_due 可将其缩短但不超过 idle cap |
| 7 | Wakeup 机制完备 | 成立。`wakeup()` 打断 `_wakeup_event.wait()`；close 和异常路径均设置 wakeup_event 确保不挂起 |
| 8 | 测试稳定性（F-2） | 已修复。drain_once 测试纯单线程、纯 ManualClock；background 测试用单一 RealtimeUtcClock |
| 9 | 测试覆盖配置不等场景 | 覆盖。drain_once 测试 not_ready=0.03 vs poll=0.2；background 测试 not_ready=0.01 vs poll=0.5 |
| 10 | pyright / README | pyright 0 错误；README/design 均已更新 not-ready/idle/wakeup/空日志抑制语义 |
| 11 | F-3 defer 是否合理 | 合理。空轮询多一次 DB 读是低优优化；当前 idle interval 已使净 QPS 下降 |

## Findings

### F-R1-未修复-低-含 not-ready 活动轮次中 `known_delay_seconds` 覆盖其它 wait 的更早 DB next_due

- **入口/函数**: `WaitPoller._next_poll_delay_seconds` → `_next_loop_interval_seconds`
- **文件(行号)**: `dayu/host/wait_adapter.py:1072-1073, 1594-1595`
- **输入场景**: 单轮 poll 同时 claim 到 not-ready wait（写入 `known_delay_seconds`）和另一个已在 DB 中有更早 `next_observe_at` 的 backoff wait（但本轮未 claim 到该 backoff wait，例如因 claim batch 满或该 backoff 记录恰好被其他 poller 持有 claim）。
- **实际分支**: `_next_poll_delay_seconds` 第 1072 行 `known_delay_seconds is not None` → 直接返回 `max(known_delay_seconds, 0.0)`，不查询 DB next_due。
- **预期行为**: 应取 `min(known_delay_seconds, DB next_due_delay)` 确保不在更早 due 的 backoff 记录上延迟。
- **实际行为**: sleep 长度为 not-ready delay，可能超过另一个 backoff wait 的 next_observe_at，导致该 backoff wait 被延迟观察。
- **直接证据**: 第 1072-1073 行 `if known_delay_seconds is not None: return max(known_delay_seconds, 0.0)` — 短路返回，不执行第 1076-1083 行的 DB 查询。
- **影响**: 在以下条件同时满足时才可能触发：(1) 单轮 claim batch 满或存在 claim 冲突，(2) 未 claim 到的 wait 的 `next_observe_at` 比 not-ready delay 更早，(3) 该 wait 的 claim 由其他 poller 持有且未过期。默认 `claim_batch_size=100` 极大降低概率；即使触发，延迟上限为 `not_ready_observe_interval_seconds`（默认 1.0s），下一轮 claim 会自然补齐。实际风险极低。
- **建议改法和验证点**: 可在 `_next_poll_delay_seconds` 中当 `known_delay_seconds is not None` 时仍查询 DB next_due 并取 `min`。但这会增加每轮一次 DB 查询，且当前 `claim_batch_size=100` 使触发概率可忽略。建议保持当前实现，在 `known_delay_seconds is not None` 时不额外查询 DB。
- **修复风险（低）**: 如要修，改动仅影响 `_next_poll_delay_seconds` 内部逻辑。
- **严重程度（低）**: 触发条件苛刻，延迟上限小，自动恢复。

## Open Questions

1. **`_wakeup_event` 在 `open()` 中未显式 clear**：`open()` 第 1320-1321 行创建新的 `threading.Event()`，初始状态为 unset，等价于 clear。若后续支持 reopen（当前 `_opened` 检查拒绝），需注意旧 event 状态。当前无影响。

2. **`not_ready_observe_interval_seconds` 无上限约束**：与 `idle_poll_interval_seconds` 不同，`_next_loop_interval_seconds` 在有活动且 `next_poll_delay_seconds` 非 None 时不施加任何上限。若配置为极大值（如 3600s），poller 将长时间不 poll。但有 `wakeup()` 和 `close()` 作为 escape hatch，且这是显式策略配置。当前可接受。

## Residual Risk

- **真实 SEC / Fins 网络 smoke 未跑**：沿用上轮 risk，narrow re-fix 范围是 Host poller sleep 计算，不影响 adapter 行为，风险不增。
- **空轮询 next-due 额外 DB 读**：F-3 已 defer，当前净 QPS 下降，非 blocker。
- **background timing 测试仍依赖线程调度**：`test_background_loop_uses_not_ready_due_before_poll_interval` 使用 `_RealtimeUtcClock` 消除了时钟源不一致，但断言 `elapsed_seconds < 0.3` 仍依赖本机线程调度公平性。阈值 0.3s 相对 `poll_interval_seconds=0.5` 和 `not_ready_observe_interval_seconds=0.01` 留有充足余量；主要 correctness 断言由单线程 drain_once 测试覆盖。
- **`test_poll_adapter_empty_round_does_not_log_poll_summary` 仅检查空轮询不输出 claimed/done 日志**：未覆盖有活动时的日志输出验证。但有活动时的日志输出路径简单（`_poll_result_has_activity` 直接 guard），风险低。

## 结论

**Pass.**

DS F-1 已通过完整链路修复：`_release_not_ready` → `_ReleaseNotReadySummary.next_poll_delay_seconds` → `_min_optional_delay_seconds` 累积 → `_next_poll_delay_seconds(known_delay_seconds=...)` → `WaitPollOnceResult.next_poll_delay_seconds` → `_next_loop_interval_seconds` 在有活动时消费。`not_ready_observe_interval_seconds` 与 `poll_interval_seconds` 不等时，无论孰大孰小，sleep 均按 next due 对齐。

DS F-2 已修复：原混用 ManualClock 与真实 sleep 的测试改为纯单线程 `drain_once_for_test()` + ManualClock，新增 background 测试使用统一 `_RealtimeUtcClock` 消除时钟源不一致。

F-3 defer 合理：空轮询额外 DB 读是低优性能优化，当前 idle interval 已使净 QPS 下降约 60%，非 correctness blocker。

Backoff 全部 8 个错误路径保留；idle / wakeup 语义正确；空轮询日志抑制；pyright 0 错误；36 个测试通过；README 与 design doc 已更新。
