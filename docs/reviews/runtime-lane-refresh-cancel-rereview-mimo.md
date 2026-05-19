# Code Review

## Scope

- Mode: current changes
- Branch: feat/host-p10-5-public-contract-freeze
- Base: main
- Output file: docs/reviews/runtime-lane-refresh-cancel-rereview-mimo.md
- Included scope: dayu/runtime/lane.py (uncommitted diff), tests/runtime/test_lane.py (uncommitted diff), tests/README.md (uncommitted diff), docs/reviews/runtime-lane-refresh-cancel-fix-codex.md (existing artifact)
- Excluded scope: 无
- Parallel review coverage: 无

## Findings

未发现实质性问题。

### 详细走读

#### 1. Root cause 修复验证

`_refresh_token()` (lane.py:647-683) 新增 `except asyncio.CancelledError` 分支 (line 663)，调用 `_await_task_after_outer_cancellation(refresh_task)` 等待底层线程 task 完成。这直接修复了原始问题：外层 `CancelledError` 时 `asyncio.shield` 的 wrapper 被取消，但底层 `to_thread` task 仍在运行；原实现没有 await 该 task，导致 orphan task 和 unhandled `RuntimeLaneError`。

`_await_task_after_outer_cancellation()` (lane.py:993-1014) 通过循环 `await asyncio.shield(task)` + `task.done()` 检查，确保底层 task 完成后才返回。若底层 task 以异常结束，`task.result()` 会重新抛出该异常，由调用方的 `except` 分支捕获。

外层 `CancelledError` 始终被保留并重新抛出：三个 cleanup 分支均使用 `raise cancelled` (line 668, 677) 或裸 `raise` (line 679，等价于 `raise cancelled`)。

#### 2. 三分支状态更新验证

**成功分支** (line 678-679):
- `expires_at = await _await_task_after_outer_cancellation(refresh_task)` — 底层 refresh 成功返回新过期时间
- `token.expires_at = expires_at` — 正确更新 token 状态
- `raise` — 重新抛出原始 `CancelledError`

**Claim lost 分支** (line 666-668):
- `_await_task_after_outer_cancellation` 抛出 `RuntimeLaneClaimLostError`
- `self._mark_token_lost(token)` — 正确标记 `token._lost = True`、`token.released = True`，从 `_held_tokens` 移除，唤醒 waiter
- `raise cancelled` — 重新抛出原始 `CancelledError`

**Runtime error 分支** (line 669-677):
- `_await_task_after_outer_cancellation` 抛出 `RuntimeLaneError`
- `_LOGGER.exception(...)` — 正确记录结构化错误日志，包含 `lane_name` 和 `claim_id`
- `raise cancelled` — 重新抛出原始 `CancelledError`，不吞掉外层取消

三个分支均不修改 `token.released`（除 claim lost 外），不泄漏 claim，不引入新状态不一致。

#### 3. Orphan task / 未收口 exception / claim 泄漏检查

- **Orphan task**: `_await_task_after_outer_cancellation` 确保底层 `to_thread` task 被 await 完成，不留 orphan。
- **未收口 exception**: 底层 `RuntimeLaneClaimLostError` 和 `RuntimeLaneError` 均在 `CancelledError` handler 内被捕获并收口（标记 lost 或记录日志），不会变成 unhandled task exception。`CancelledError` 本身始终被重新抛出。
- **Claim 泄漏**: 成功分支更新 `expires_at` 但不释放 claim（正确，refresh 是续期不是释放）；claim lost 分支标记 lost；runtime error 分支不修改 claim 状态（claim 依赖后续 heartbeat / TTL cleanup 收口，与 release 取消 cleanup 语义一致）。

#### 4. 测试确定性验证

三个新测试均使用 `threading.Event` 做同步控制：

1. `test_refresh_waits_for_shielded_success_after_outer_cancel` (test_lane.py:358-403):
   - `refresh_started` → 确认底层已进入阻塞等待
   - `finish_refresh` → 控制底层何时完成
   - `refresh_finished` → 确认底层已完成
   - 测试先 `await _wait_for_thread_event(refresh_started)` 再 `cancel()`，确保取消发生在 shield 保护期内
   - `assert refresh_finished.is_set()` 在状态断言前，确保 cleanup 已完成

2. `test_refresh_cancel_cleanup_marks_lost_after_claim_lost` (test_lane.py:406-450):
   - 同样的 Event 同步模式
   - `_delete_claim` 在底层线程内执行，`refresh_finished` 确认删除已完成

3. `test_refresh_cancel_cleanup_logs_runtime_error_and_preserves_cancel` (test_lane.py:453-501):
   - 同样的 Event 同步模式
   - `caplog` 验证错误日志已记录

三个测试均不依赖 `asyncio.sleep` 或时序竞争，通过 Event 实现确定性同步。

#### 5. Runtime 层边界检查

修复只使用标准库 `asyncio` 原语和 `dayu.runtime.lane` 内部类型（`RuntimeLaneClaimLostError`、`RuntimeLaneError`），不引入 `dayu.host` / `dayu.engine` / `dayu.service` 语义。`_mark_token_lost` 是 controller 内部状态管理，`_LOGGER.exception` 使用中性消息常量 `_LOG_REFRESH_FAILED_AFTER_CANCEL`。Runtime 层保持 layer-neutral。

#### 6. README / artifact 准确性

- `tests/README.md` diff (line 73): 把 "shielded claim / release" 改为 "shielded claim / refresh / release"，准确反映新增 refresh cancellation cleanup 覆盖。
- `docs/reviews/runtime-lane-refresh-cancel-fix-codex.md`: 现有 artifact 准确描述了修复动机、实现和残余风险。

## Open Questions

无。

## Residual Risk

- `RuntimeLaneError` 分支中 claim 状态未清理，依赖后续 heartbeat / release / TTL cleanup 收口。这与 claim / release 的取消 cleanup 语义一致，但如果后续 heartbeat 也遇到相同错误，claim 可能在 TTL 过期前一直占容量。风险低，因为 heartbeat loop 会捕获 `RuntimeLaneError` 并调用 `_record_heartbeat_error` 关闭 controller。
- `_await_task_after_outer_cancellation` 的无限循环在极端情况下（task 永不完成）会阻塞。但 `to_thread` 包裹的同步函数不会永不返回（除非死锁），且 SQLite 有 busy timeout 保护。风险极低。

## Conclusion

**PASS**

Root cause 已真正修复：`_refresh_token()` 的 `CancelledError` handler 通过 `_await_task_after_outer_cancellation` 等待底层 task 完成，三分支状态更新正确（成功更新 `expires_at`、claim lost 标记 lost、runtime error 记录日志），所有分支均重新抛出原始 `CancelledError`。不引入 orphan task、未收口 exception 或 claim 泄漏。测试通过 Event 同步实现确定性，不依赖 race。Runtime 层保持 layer-neutral。README / artifact 准确。
