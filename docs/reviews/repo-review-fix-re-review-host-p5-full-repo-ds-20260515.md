# PR 54 Full-Repo Accepted Fix Re-Review (AgentDS)

## Verdict: PASS

当前 workspace changes 完整修复了 controller adjudication accepted items A1-A10，且未实现任何 rejected / deferred / needs-design 项。可进入 controller final adjudication。

## Scope

- Mode: current changes (uncommitted workspace) re-review
- Branch: feat/host-phase5-local-dispatch
- Source adjudication: `docs/reviews/repo-review-controller-adjudication-20260515.md`
- Source fix artifact: `docs/reviews/repo-review-fix-host-p5-full-repo-codex-20260515.md`
- Source review artifacts: `docs/reviews/repo-review-20260515-1338.md`, `docs/reviews/repo-review-20260515-1346.md`
- Output file: `docs/reviews/repo-review-fix-re-review-host-p5-full-repo-ds-20260515.md`
- Review date: 2026-05-15 14:28

## Accepted Fix Coverage A1-A10

### A1 — runtime lane CancelledError 保持取消语义

**入口**: `LaneController._try_claim_once` (lane.py:539-571), `_release_token` (lane.py:698-728), `_release_untracked_claim` (lane.py:741-770)

**验证**:

1. `_try_claim_once` (line 549-571): shield claim → catch CancelledError → 读取 claim 结果 → 若 claim 已写入 DB 则 try `_release_untracked_claim` → release 失败时 `_LOGGER.exception` + `raise cancelled`（保持 CancelledError 传播）。✓

2. `_release_token` (line 706-728): 若 token 已 release 直接返回 → shield `release_task` → catch CancelledError → 再次 `await asyncio.shield(release_task)` 等待 DB release 完成 → 成功则 `self._mark_token_released(token)`（同步更新 `token.released=True`、`_held_tokens.pop`、`_wake_waiters`）后 `raise`（重新抛出 CancelledError）→ 失败则 log + `raise cancelled`。✓

3. `_release_untracked_claim` (line 755-770): 同 `_release_token` 的 CancelledError handler 模式，但 release 成功后直接 `raise`（无需标记内存状态，因为 token 未登记到 `_held_tokens`）。✓

**测试覆盖**:
- `test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails` (test_lane.py:467-520): 模拟 claim 成功后 release 失败，断言最终异常为 `CancelledError` 且日志含 "untracked claim release failed"。✓
- `test_release_token_waits_for_shielded_release_after_outer_cancel` (test_lane.py:523-567): 模拟外层取消后 release，断言 `token.released is True`、DB claim row 已删除、可重新 acquire。✓
- `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` (test_lane.py:570-612): 模拟 untracked release 在外层取消后失败，断言最终异常为 `CancelledError` 且日志含 "untracked claim release failed"。✓

**结论**: PASS。三条路径 CancelledError 语义完整，内存/DB 一致性正确，测试覆盖了成功 release、release 失败和外层取消路径。

### A2 — dispatch _drain_loop 不提前退出

**入口**: `HostDispatchScheduler._drain_loop` (dispatch.py:451-463)

**验证**:

修复前:
```python
if self._queue.empty():
    await asyncio.sleep(...)
    if self._queue.empty():
        return  # 提前退出，遗留 wakeup
await self.drain_once()
```

修复后:
```python
if self._queue.empty():
    await asyncio.sleep(...)
await self.drain_once()  # 不检查 empty，直接 drain（drain_once 内处理空队列）
```
循环仅由 `while not self._closed` 控制，持续轮询直到 scheduler close。✓

**测试覆盖**:
- `test_drain_loop_continues_when_dispatch_arrives_during_empty_window` (test_dispatch_scheduler.py:473-492): `_EnqueueOnSecondEmptyQueue` 在第二次 `empty()` 调用时注入 record 并返回 True，模拟 sleep 窗口入队 race；断言 worker 被创建（factory.created == 1）且队列最终为空。✓

**结论**: PASS。drain loop 不再提前退出，测试覆盖了 sleep 窗口 race。

### A3 — BatchToolExecutionRequest 拒绝重复 tool_call_id

**入口**: `BatchToolExecutionRequest.__post_init__` (tool_call.py:133-151)

**验证**: 遍历 `calls`，用 `seen_tool_call_ids` set 检测重复；命中时 raise `ValueError` 含 "unique" 关键词。✓

**测试覆盖**:
- `test_batch_tool_execution_request_rejects_duplicate_tool_call_id` (test_tool_call.py:192-214): 两个 tool_call_id="id-1" 的 call → `pytest.raises(ValueError, match="unique")`。✓

**结论**: PASS。

### A4 — is_retriable assert_never 穷尽守卫

**入口**: `is_retriable` (error_classifier.py:121-148)

**验证**:
```python
match error_code:
    case (RATE_LIMIT_EXCEEDED | SERVER_ERROR | NETWORK_ERROR | TIMEOUT):
        return True
    case (CLIENT_ERROR | CONTEXT_LENGTH_EXCEEDED | UNKNOWN_HTTP_STATUS):
        return False
    case _:
        assert_never(error_code)
```
- `CONTEXT_LENGTH_EXCEEDED` 显式落入不可重试分支（修复前隐式返回 None/falsy）。✓
- `case _: assert_never(error_code)` 确保新增枚举成员时 pyright 静态报错。✓

**测试覆盖**:
- `test_is_retriable_branches` (test_http_error_classification.py:87-104): 遍历所有 7 个枚举成员（含 CONTEXT_LENGTH_EXCEEDED），断言 retriable/not_retriable 分类正确。✓

**结论**: PASS。

### A5 — ToolCancelledOutcome 拒绝空 hint

**入口**: `ToolCancelledOutcome.__post_init__` (tool_outcome.py:125-126)

**验证**:
```python
if self.hint is not None and self.hint.strip() == "":
    raise ValueError("ToolCancelledOutcome.hint must be non-empty")
```
空字符串和纯空白均被拒绝。✓

**测试覆盖**:
- `test_cancelled_rejects_empty_or_whitespace_hint` (test_tool_outcome_exhaustive.py:190-200): 覆盖 `""`、`"   "`、`"\t"`、`"\n"`、`"  \t  \n"`。✓

**结论**: PASS。

### A6 — wait_for_or_cancel docstring 修正

**入口**: `wait_for_or_cancel` docstring (cancellation.py:173-176)

**验证**: `:raises Exception:` 段明确说明 "``pending`` 完成分支会读取 ``pending.result()``，因此 pending task 中抛出的异常会从本 helper 直接传播给调用方"。与代码 `cancellation.py:196`（`return WaitCompleted(value=pending.result())`）一致。✓

**结论**: PASS。

### A7 — _HostCancellationToken 显式实现 CancellationToken Protocol

**入口**: `_HostCancellationToken` (dispatch.py:209)

**验证**: `class _HostCancellationToken(CancellationToken):` — 显式声明实现 Protocol。与 `dispatch.py:683` 的 `token: CancellationToken = cancellation_token` 赋值一致，pyright 可静态校验签名。✓

**结论**: PASS。

### A8 — EventLog payload helper 抽取

**文件**: `dayu/host/_event_payload.py` (新建)

**验证**:
- `payload_object(event: EventLogRow) -> Mapping[str, JsonValue]` — JSON 解析 + Mapping 校验。✓
- `required_payload_text(payload, *, field_name) -> str` — 必填文本字段读取。✓
- `run_input.py` 和 `engine_ingest.py` 均导入 `_event_payload` 的两个函数，删除了各自重复实现。✓
- 错误类型使用 `HostDurableError`，未泄漏到 `dayu.runtime`。✓
- 文件标记为 `_event_payload.py`（模块级私有），不进入 Host 公共 API。✓

**结论**: PASS。

### A9 — public validation helper 抽取

**文件**: `dayu/host/_public_validation.py` (新建)

**验证**:
- `require_non_empty(value, *, field_name)` — 必填字符串非空校验。✓
- `require_optional_non_empty(value, *, field_name)` — 可选字符串非空校验。✓
- `api.py` 导入 `require_non_empty as _require_non_empty, require_optional_non_empty as _require_optional_non_empty`，替换了模块内的重复实现。✓
- `tooling.py` 同模式导入。✓
- 文件标记为 `_public_validation.py`（模块级私有），不进入 Host 公共 API。✓

**结论**: PASS。

### A10 — run_input.py 死导入清理

**入口**: `run_input.py` import block (lines 9-59)

**验证**: 原 `json`、`cast` 死导入已移除。JSON 解析现在由 `_event_payload.payload_object` 内部处理。`read_event_by_id` 保留（仍被 `DurableCurrentRunFactProvider._load_current_run_facts_tx` 通过 `EventLogStore` 间接使用）。✓

**结论**: PASS。

## Rejected / Deferred / Needs-Design 验证

逐一确认以下项目**未被实现**：

| 来源 | 项目 | 验证点 | 状态 |
| --- | --- | --- | --- |
| 1338 F2 | executor CancelledError → ToolCancelledOutcome | `_failed_record_from_cancelled` (agent.py:531) 仍返回 `ToolFailedOutcome` | 未改 ✓ |
| 1338 F4 | idempotency SELECT-then-INSERT 竞态 | `idempotency.py` 无 `INSERT ... ON CONFLICT` | 未改 ✓ |
| 1338 F8 | _consume_worker_events 检查 cancellation token | dispatch.py `_consume_worker_events` 的 while 循环内无 `is_cancelled()` 调用 | 未改 ✓ |
| 1338 F9 | DefaultLocalEngineWorker.cancel no-op | local_proxy.py:115 仍为 `del reason` | 未改 ✓ |
| 1346 F001 | runner injection / AsyncOpenAIRunner 硬编码 | agent.py:109 仍 `from dayu.engine.runners.openai.runner import AsyncOpenAIRunner` | 未改 ✓ |
| 1338 F6 | HTTP 错误诊断信息丢失 | agent.py `_consume_runner_event` 仍只提取 error_code + message | 未改 ✓ |
| 1338 F10 | God module/class 拆分 | 无大规模重构 | 未改 ✓ |
| 1338 F15 | SSE parser usage 畸形终结流 | SSE parser 未修改 | 未改 ✓ |
| 1346 F014 | schema DDL 事务包裹 | schema.py bootstrap 仍逐条执行 DDL | 未改 ✓ |
| 1346 F013 | CANCELLED terminal payload 分支 | `run_transition.py` `_attempt_terminal_payload` 无 CANCELLED 分支 | 未改 ✓ |

**结论**: 所有 rejected / deferred / needs-design 项均未被实现，严格遵守 controller adjudication 边界。

## Blocking Findings

无。

## Non-blocking Observations

### N1 — _release_token 双重取消边缘情况未建模

在 `_release_token` 的 CancelledError handler (lane.py:713-727) 中，第二次 `await asyncio.shield(release_task)` 若也被外层取消，`CancelledError` 会穿透 `except RuntimeLaneError` 向上传播，此时 `_mark_token_released` 不会被调用。token 会残留在 `_held_tokens` 中，由 heartbeat loop 的 `_mark_token_lost` 最终回收。

这与 codex fix artifact 记录的 residual risk 一致："Repeated external cancellation while waiting for the release task is not separately modeled in tests." 当前行为可接受（最终一致性依赖 heartbeat），但建议后续在测试中补充双重取消场景。

### N2 — _drain_loop 空闲 scheduler 保持一个 sleeping task

修复后 `_drain_loop` 持续轮询直到 `close()`。空闲 scheduler 将保持一个 `asyncio.sleep` 中的 task。这是 design intent，不构成资源泄漏，但建议在 `HostDispatchScheduler` 文档中说明。

## Open Questions

无。

## Residual Risk

1. **A1 双重取消边缘情况**（owner: 后续 Engine/lane cancellation precision cleanup）: `_release_token` 的 CancelledError handler 中第二次 `asyncio.shield` 若被取消，内存状态更新会被跳过，依赖 heartbeat 最终一致性。
2. **A1 release 失败 leak**（owner: 现有 TTL 机制）: untracked release 失败时的 DB claim row 依赖 TTL 过期回收，codex fix artifact 已记录。
3. **A2 空闲 scheduler task**（owner: Host dispatch）: 空闲 scheduler 保持一个 sleeping drain task 直到 `close()`，非资源问题但需文档化。
4. **测试聚合验证**（owner: CI）: AgentCodex 报告的 `741 passed` 测试和 `0 errors, 0 warnings` pyright 未由本 Agent 独立复跑，建议 controller final adjudication 前复跑验证。

## Controller Final Adjudication Ready

本 re-review 确认 A1-A10 全部正确修复，rejected/deferred/needs-design 项未被实现。可以进入 controller final adjudication，回写 `docs/host/implementation-control.md` 并推送 PR 54。
