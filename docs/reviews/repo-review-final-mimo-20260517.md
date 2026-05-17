# Code Review — P9 All-Repository Final Re-Review

## 结论：PASS

**理由：** DS 15:21 报告的 4 个严重阻塞项中，F1、F2、F4 已通过代码修复和测试验证关闭；F3 已由 controller 裁决为后续 schema/design debt，不作为 P9 blocking。当前 workspace snapshot 未引入新问题。

---

## Scope

- **Mode**: all repository (final re-review)
- **Branch**: `feat/host-p9-conversation-memory`
- **Base**: `main`
- **Output file**: `docs/reviews/repo-review-final-mimo-20260517.md`
- **Review date/time**: 2026-05-17 (final re-review after controller fix pass)
- **Reviewer**: AgentMiMo
- **Gate**: P9 all-repository final re-review after controller fix pass
- **Included**: DS 15:21 阻塞项 F1、F2、F4 复核；F3 确认无新问题引入
- **Excluded**: DS 15:21 中已由 controller 裁决的非 blocking findings

---

## Findings

未发现实质性问题。

---

## DS 15:21 阻塞项复核

### F1 — SSE 已 yield 事件后 retriable read/idle failure 不得跨 attempt retry

**状态：已关闭**

**代码证据**（`dayu/engine/runners/openai/runner.py:295-353`）：
- `attempt_yielded_event = False` 在每次 attempt 开始时设置（第 295 行）
- 当事件被 yield 时，`attempt_yielded_event = True`（第 300 行）
- 当 `_AttemptFailedRetriable` 被捕获时，检查 `if attempt_yielded_event:`（第 329 行）
- 如果已经 yield 了事件，直接发出 HTTP error event + Done(ERROR) 然后 return（第 341-353 行）
- 只有未 yield 事件时才进入重试决策逻辑（第 354-397 行）

**测试证据**（`tests/engine/runners/openai/test_http_error_event.py:412-447`）：
- `test_stream_read_failure_after_event_does_not_retry` 测试了两种异常场景：
  - `aiohttp.ClientError` → `NETWORK_ERROR`
  - `asyncio.TimeoutError` → `TIMEOUT`
- 断言 `len(session.calls) == 1`（只调用了一次，未重试）
- 断言 `attempt=1, retried=False`
- 断言事件序列正确：`CONTENT_DELTA → HTTP_ERROR → Done(ERROR)`

**验证**：测试通过，pyright 无报错。

---

### F2 — SSE tool_calls 最终 Done finish_reason 必须为 TOOL_CALLS

**状态：已关闭**

**代码证据**（`dayu/engine/runners/openai/sse_parser.py:545-549`）：
```python
finish = (
    FinishReason.TOOL_CALLS
    if self._tool_calls_seen
    else self._finish_reason or FinishReason.STOP
)
```
- 当 `self._tool_calls_seen` 为 `True` 时，finish reason 强制为 `FinishReason.TOOL_CALLS`
- 无论 provider 返回的 `_finish_reason` 是 `stop` 还是其他值

**测试证据**（`tests/engine/runners/openai/test_sse_tool_call_stream.py:106-124`）：
- `test_tool_call_done_finish_reason_prefers_tool_calls_over_stop` 测试了 provider 返回 `finish_reason:stop` 但携带 tool_calls 的场景
- 断言 `done[0].data.finish_reason is FinishReason.TOOL_CALLS`

**补充测试**（`tests/engine/runners/openai/test_sse_tool_call_stream.py:19-70`）：
- `test_tool_call_aggregated_across_chunks` 测试了正常的 tool_calls 聚合场景
- 断言最终 Done 事件的 `finish_reason is FinishReason.TOOL_CALLS`

**验证**：测试通过，pyright 无报错。

---

### F3 — minimal read model consumer isolation

**状态：已由 controller 裁决为后续 schema/design debt，不作为 P9 blocking**

**Controller 裁决**（`docs/reviews/p9-all-repo-review-controller-adjudication-20260517.md`）：
> - `reset_minimal_read_model_projection` clears global minimal read model tables:
>   - Current minimal read model tables are global single-consumer read views and do not carry `consumer_id`.
>   - Adding consumer-scoped reset requires schema design, not a local patch.
>   - Owner: future read model multi-consumer schema work.

**复核确认**：
- 当前 workspace snapshot 中 `reset_minimal_read_model_projection` 未被修改
- 其他 projection 相关改动（`advance_projection_checkpoint` CAS hardening）不涉及 consumer isolation
- 未发现当前 fix 引入与 F3 相关的新问题

---

### F4 — RuntimeFileLock.__exit__ release 失败后不得留下 stale active token

**状态：已关闭**

**代码证据**（`dayu/runtime/filelock.py:198-203`）：
```python
token = self._active_token
if token is not None:
    try:
        token.release()
    finally:
        self._active_token = None
```
- 使用 `try/finally` 确保无论 `token.release()` 是否成功，`self._active_token` 都会被设置为 `None`
- 即使 release 失败抛出 `RuntimeFileLockError`，active token 也被清理
- 下次 `acquire()` 不会因 stale token 永久抛 `RuntimeFileLockError("already active")`

**测试证据**（`tests/runtime/test_filelock.py:130-152`）：
- `test_context_manager_release_failure_clears_active_token_and_allows_reacquire` 测试了 release 失败场景
- 注入 `_FailingReleaseToken`（release 始终抛 `RuntimeFileLockError`）
- 断言 `lock._active_token is None`（active token 已清理）
- 断言 `lock.acquire(timeout_seconds=0)` 成功（可重新获取锁）

**验证**：测试通过，pyright 无报错。

---

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `pytest tests/engine/runners/openai/test_http_error_event.py` | 14 passed |
| `pytest tests/engine/runners/openai/test_sse_tool_call_stream.py` | 3 passed |
| `pytest tests/runtime/test_filelock.py` | 13 passed |
| `pyright dayu tests` | 0 errors, 0 warnings, 0 informations |

---

## Open Questions

无。

---

## Residual Risk

DS 15:21 中除 F1-F4 外的其他 findings（F5-F22）已由 controller 裁决为 accepted fixes 或 deferred findings，不作为 P9 blocking。详见 `docs/reviews/p9-all-repo-review-controller-adjudication-20260517.md`。
