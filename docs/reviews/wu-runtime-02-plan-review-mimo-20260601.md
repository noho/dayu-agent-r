# WU-RUNTIME-02 Plan Review

- **Reviewed target**: `docs/host/wu-runtime-02-lane-clock-cancellation-plan.md`
- **Review scope**: code-generation-readiness，按 design doc、总控文档与项目约束裁决
- **Review timestamp**: 20260601-065336

## Assumptions Tested

| # | Assumption | 验证方式 | 结论 |
|---|---|---|---|
| A1 | `_LaneClock.now()` 用 monotonic elapsed 推导 UTC 参与跨进程 TTL 判断 | 代码 `lane.py:327-334`，`_try_claim_once_sync:595`，`_refresh_token_sync:696` | 成立 |
| A2 | `_await_task_after_outer_cancellation` 无上限等待 | 代码 `lane.py:1002-1024`，`while True` + `asyncio.shield` + 无 deadline | 成立 |
| A3 | 现有多进程 TTL 测试覆盖 crash stale cleanup | `test_lane_multiprocess.py` 已有 `test_crashed_holder_is_cleaned_by_ttl_and_other_process_can_acquire` | 成立 |
| A4 | 现有 cancellation 测试覆盖 repeated cancel、release cancel、refresh cancel | `test_lane.py` 已有 `test_repeated_task_cancel_during_claim_cleanup_releases_inserted_claim`、`test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails`、`test_refresh_cancel_cleanup_marks_lost_after_claim_lost` 等 | 成立 |
| A5 | `lane.py` 不 import Host / Engine / Service / UI / Fins | 代码 `lane.py:24` 只 import `dayu.contracts.cancellation.CancellationToken` | 成立 |
| A6 | `LaneClaimToken.released` 是 public field | 代码 `lane.py:211`，dataclass 无 leading underscore；设计文档 `design.md:166` 明确列出 `released: bool` | 成立 |

## Findings

无 blocking finding。

### F1-未修复-低-cleanup timeout helper 返回/抛出语义需明确

- **位置**: Design Decision 2，`_await_task_after_outer_cancellation` timeout 后行为
- **问题类型**: 契约不够具体
- **当前写法**: "timeout 时抛出私有 runtime lane cleanup timeout 错误，或返回封闭的私有 timeout outcome；不得新增 public API。"
- **反例/失败场景**: "或"字让 implementation agent 需要在两种语义间自行决定。现有调用方 `_try_claim_once`、`_refresh_token`、`_release_token` 都在 `await _await_task_after_outer_cancellation(...)` 之后 catch `RuntimeLaneError` 子类；如果 helper 改为返回 timeout outcome，所有调用方需新增 isinstance 判断分支，改变 control flow 结构。
- **为什么有问题**: 不是 blocking，但 implementation agent 可能选择与现有 catch 模式不一致的方案，导致调用方 control flow 比 plan 设想的更复杂。
- **直接证据**: `lane.py:570-584`（`_try_claim_once` catch pattern）、`lane.py:664-680`（`_refresh_token` catch pattern）、`lane.py:742-757`（`_release_token` catch pattern）
- **影响**: 低。两种方案都可实现，但 plan 应固定一种以减少 implementation agent 判断负担。
- **建议改法和验证点**: 建议 plan 选定一种语义（推荐：抛出私有 `_OuterCancellationCleanupTimeoutError(RuntimeLaneError)`，调用方现有 catch pattern 自然兼容），删除"或"字。若选择返回 outcome，需明确调用方新增的判断分支。
- **修复风险（低/中/高）**: 低
- **严重程度（低/中/高/严重）**: 低

## Open Questions

无 blocking open questions。

Non-blocking：

1. **observer 对 late acquired claim 的处理**：plan 说"对 late acquired claim 记录 claim id / lane name，并说明将依赖 TTL cleanup"。这是日志级 diagnostic，不影响正确性（TTL 兜底），但 implementation agent 需确认 observer callback 是 done callback (`task.add_done_callback`) 还是其它机制。plan 已足够明确，不阻塞。

2. **`LaneClaimToken.released` public field**：plan 明确不处理，deferred to public contract 裁决。总控文档 non-goals 一致。不阻塞本 WU。

## Residual Risks

| # | 风险 | 跟踪目的地 |
|---|---|---|
| R1 | 系统 wall clock 被大幅手动调快/调慢仍影响 runtime capacity availability | design source "clock skew 只影响 runtime capacity availability，不影响 Host truth"；当前 phase 可接受 |
| R2 | cleanup timeout 后底层 thread 可能稍后成功或失败 | plan 要求 observer 消费 late result/exception + TTL cleanup 兜底；实现后需验证 |
| R3 | `LaneClaimToken.released` public field 收缩 | deferred to public contract 裁决，不在本 WU 范围 |

## Conclusion: PASS

Plan 对 `_LaneClock` root cause 的识别准确，Option A（Python 真实 UTC wall clock per SQLite transaction）是当前 phase 最小、可维护、可测试的修复。bounded cancellation cleanup 的语义清晰、可实现、可测：timeout 计算公式正确（`busy_timeout_seconds + 0.25`），timeout 后不假装 release/lost、保留 held token、依赖 TTL 兜底，observer 消费 late result/exception。slices 大小合理，allowed files、non-goals、stop conditions、tests 可直接交给 implementation agent。pyright、README 触发判断、runtime import boundary、中文 docstring 等项目约束均已覆盖。

F1 为低严重度的契约清晰度问题，不阻塞 implementation。
