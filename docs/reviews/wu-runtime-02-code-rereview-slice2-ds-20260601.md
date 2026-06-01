# Code Re-Review

## Scope

- **Mode**: re-review (role-scoped handoff)
- **Branch**: `fix/wu-runtime-02-lane-clock-cancellation`
- **Work Unit**: WU-RUNTIME-02 Slice 2
- **Gate**: code re-review
- **Output file**: `docs/reviews/wu-runtime-02-code-rereview-slice2-ds-20260601.md`
- **Fix artifact**: `docs/reviews/wu-runtime-02-fix-slice2-codex-20260601.md`
- **Original reviews**:
  - `docs/reviews/wu-runtime-02-code-review-slice2-mimo-20260601.md`
  - `docs/reviews/wu-runtime-02-code-review-slice2-ds-20260601.md`
- **Controller accepted findings**: 001, 002
- **Controller rejected finding**: 003
- **Re-review target**:
  - Verify 001 fix (observer `except Exception`)
  - Verify 002 fix (`raise cancelled from exc` + `__cause__` assertion)
  - Assess 003 rejection for correctness risk
  - Detect new blocking issues
- **Reviewed files**:
  - `dayu/runtime/lane.py` (unstaged diff)
  - `tests/runtime/test_lane.py` (unstaged diff)

## Per-Finding Verification

### 001 — observer 捕获 Exception（Accepted Fix）：PASS

**修复内容复核**：

三个 `_consume_abandoned_*_task` 函数均已从 `except RuntimeLaneError` 改为 `except Exception`：

- `_consume_abandoned_claim_task` (line 1231): `except Exception:` — 消费 `task.result()` 抛出的非 `RuntimeLaneError` 异常，记录 error 日志后 safe return。✓
- `_consume_abandoned_release_task` (line 1290): `except Exception:` — 同上 pattern。✓
- `_consume_abandoned_refresh_task` (line 1340): `except Exception as exc:` — 记录 warning 日志 + `exc_info=True` + `error_type`。✓

`task.cancelled()` 分支在所有三个函数中优先于 `except Exception`，因此 `CancelledError` 不会被 `except Exception` 吞掉。`BaseException`（`KeyboardInterrupt` / `SystemExit`）仍不被捕获——符合 controller 裁决："KeyboardInterrupt / SystemExit 不应被 runtime logger 吞掉"。

**测试复核**：

`test_abandoned_release_observer_logs_non_runtime_exception`:
- 构造以 `ValueError`（非 `RuntimeLaneError`）失败的 abandoned release task
- 注册 observer，yield 两次事件循环
- 断言 `task.done() is True`
- 断言日志包含 `_ABANDONED_RELEASE_FAILED_LOG_FRAGMENT` 与 `"ValueError"` ✓

**未覆盖项**：仅 release observer 有独立非 `RuntimeLaneError` 测试；claim 和 refresh observer 使用相同 `except Exception` pattern 但无独立测试。三个函数代码结构一致，从代码走读角度不影响 correctness 结论，属于 minor test gap，不阻塞。

---

### 002 — release cancel 路径异常链修复（Accepted Fix）：PASS

**修复内容复核**：

- `_release_token` (line 849): `raise cancelled from exc` — 原为 `raise cancelled`，现已补齐异常链。✓
- `_release_untracked_claim` (line 929): `raise cancelled from exc` — 同上。✓

全文件所有 cancel 路径的 `raise cancelled` 现已统一为 `raise cancelled from exc`：

| 函数 | 行号 | 分支 | 状态 |
|---|---|---|---|
| `_try_claim_once` | 626, 628, 637 | `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` / claim release fail | ✓ (已有) |
| `_refresh_token` | 729, 741, 750 | `RuntimeLaneClaimLostError` / `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` | ✓ (已有) |
| `_release_token` | 840, 849 | `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` | ✓ (已修复) |
| `_release_untracked_claim` | 923, 929 | `_OuterCancellationCleanupTimeoutError` / `RuntimeLaneError` | ✓ (已修复) |

唯一例外是 `_refresh_token` line 752：`token.expires_at = expires_at` 后 `raise cancelled`——这是在成功获取结果后重新抛出取消，无异常可链，语义正确。

**测试复核**：

`test_release_token_failure_after_outer_cancel_preserves_cause`（新增）:
- 模拟 tracked release 慢操作后以 `RuntimeLaneError` 失败
- 断言 `CancelledError.__cause__` 为 `RuntimeLaneError`，消息为 `_RELEASE_FAILED_MESSAGE` ✓
- 断言 `token.released is False` ✓

`test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error`（更新）:
- 原测试仅断言 `CancelledError` 被抛出
- 新增断言 `__cause__` 为 `RuntimeLaneError`，消息为 `_RELEASE_FAILED_MESSAGE` ✓

---

### 003 — claim.acquired=False 静默消费（Rejected Finding）：无 Correctness Risk

**复核结论：controller 裁决合理，不引入正确性风险。**

理由验证：

1. **不持有资源**：`claim.acquired=False` 意味着 `_try_claim_once_sync` 因 capacity full 未在 DB 中创建 claim 行。无 claim_id、无 DB 行、无资源占用，不需要任何形式的 release 或 TTL fallback。
2. **observer 无遗漏**：done callback 已注册并成功消费了 late task（`task.result()` 正常返回，`claim.acquired=False`）。异常路径被 `except Exception` 覆盖，acquired=True 路径被 `_LOG_ABANDONED_CLAIM_ACQUIRED_TTL_FALLBACK` 覆盖。`acquired=False` 是唯一剩余的正常分支，且不需要任何动作。
3. **不会误导运维**：如果记录 debug 日志，在 capacity full 的竞争场景下会产生大量"abandoned claim task did not acquire"噪音。controller 选择避免低价值日志是合理的信噪比优化。
4. **无静默数据丢失**：不存在"task 已经成功获取 claim 但被误判为未获取"的路径——`claim.acquired` 直接来自 `_ClaimAttempt` 的返回值，是真源字段。

---

## 新增 Blocking 问题检查

沿 `_await_task_after_outer_cancellation` → observer 注册 → observer 消费 的主链路逐行走读，未发现新增 blocking 问题。

逐项检查：

- **observer 闭包引用泄漏**：所有 lambda 仅捕获字符串 primitive（`lane_name`、`claim_id`）或常量字符串（`operation`），不捕获 task/token/controller 等可循环对象。✓
- **`_await_task_after_outer_cancellation` deadline 逻辑**：monotonic deadline 计算正确，`remaining_seconds <= 0` 在循环入口和 `CancelledError` 分支均有检查。✓
- **`_await_task_after_outer_cancellation` 中 `task.done() and task.cancelled()` 双真场景**：若 inner task 同时 done 且 cancelled，`task.result()` 会 raise `CancelledError`。此异常穿透 `except RuntimeLaneError` 向上传播，最终 caller 仍收到 `CancelledError`——取消语义被保留。概率极低，行为正确。✓
- **cleanup timeout 后底层线程不取消**：测试 `test_await_task_after_outer_cancellation_times_out_without_cancelling_task` 验证了 `target.done() is False`，且释放 Event 后 task 正常完成。符合 approved plan。✓
- **`_OuterCancellationCleanupTimeoutError` 不进入 public API**：私有类，`__all__` 未导出。✓
- **runtime import boundary**：无新增 `dayu.engine/host/service/ui/fins` 导入。✓
- **pyright**：fix artifact 报告 0 errors / 0 warnings / 0 informations。✓
- **架构分层**：所有变更在 `dayu/runtime/lane.py` 内，属于 `dayu.runtime` 包的自包含扩展，未跨层穿透。✓

### 次要观察（非 Blocking）

1. **observer 日志级别不一致**：`_consume_abandoned_claim_task` 和 `_consume_abandoned_release_task` 使用 `_LOGGER.exception()`（ERROR 级别），而 `_consume_abandoned_refresh_task` 使用 `_LOGGER.warning()` + `exc_info=True`（WARNING 级别）。功能上等价（均记录完整 traceback），但级别不一致可能给日志告警配置带来微小困惑。不影响 correctness，不作为 finding 报告。

## Open Questions

无。

## Residual Risk

- `_consume_abandoned_claim_task` 和 `_consume_abandoned_refresh_task` 对非 `RuntimeLaneError` 异常的测试覆盖依赖与 `_consume_abandoned_release_task` 的代码 pattern 一致性，无独立测试。三个函数结构相同，风险极低。
- 其他 residual risks 与 original review（DS 20260601）保持一致：cleanup timeout 后底层线程继续运行（approved plan 设计），late tracked release 不更新 `token.released`（TTL stale cleanup 兜底）。

## Conclusion: PASS

Accepted fixes 001 和 002 实现正确，测试覆盖充分。Rejected finding 003 不引入 correctness risk。未发现新增 blocking 问题。
