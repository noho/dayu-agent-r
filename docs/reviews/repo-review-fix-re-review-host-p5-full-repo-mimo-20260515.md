# PR 54 Full-Repo Accepted-Fix Re-Review

## Scope

- Mode: current changes (re-review of accepted-fix gate)
- Branch: feat/host-phase5-local-dispatch
- Base: main
- Output file: docs/reviews/repo-review-fix-re-review-host-p5-full-repo-mimo-20260515.md
- Review date: 2026-05-15 14:24
- Source adjudication: docs/reviews/repo-review-controller-adjudication-20260515.md
- Source fix artifact: docs/reviews/repo-review-fix-host-p5-full-repo-codex-20260515.md
- Included scope: workspace unstaged changes in 17 files (12 production, 5 test/doc)
- Excluded scope: .venv/, .git/, docs/ (except fix artifact), workspace/

## Verdict

**PASS** — 所有 accepted-current A1-A10 已完整修复，未实现 rejected/deferred 项，测试与 pyright 均通过。可进入 controller final adjudication。

## Findings

未发现实质性问题。

## Accepted Fix Coverage: A1-A10

### A1: runtime lane CancelledError 取消语义 — PASS

**审查范围**: `dayu/runtime/lane.py` diff, `tests/runtime/test_lane.py` 新增 4 个测试

**修复事实**:

1. `_try_claim_once` (lane.py:554-571): `except asyncio.CancelledError as cancelled` 块内用 `try/except RuntimeLaneError` 包裹 `_release_untracked_claim`，release 失败时 `_LOGGER.exception(...)` 记录后 `raise cancelled`，CancelledError 语义不被吞噬。
2. `_release_token` (lane.py:708-728): 取消后再次 `await asyncio.shield(release_task)` 等待 DB release 完成；成功时调用 `_mark_token_released(token)` 更新 `token.released`、`_held_tokens.pop`、`_wake_waiters`；失败时记录并 `raise cancelled`。
3. `_release_untracked_claim` (lane.py:755-770): 同一 shield-retry 模式，release 失败时记录并 `raise cancelled`。
4. `_mark_token_released` (lane.py:730-739): 抽取为独立方法，统一 token 释放后的内存状态更新。

**测试覆盖**:

- `test_cancel_during_successful_claim_preserves_cancelled_error_when_cleanup_fails` (line 467): claim 已写入 + release 失败 → CancelledError 透传 + 日志记录。
- `test_release_token_waits_for_shielded_release_after_outer_cancel` (line 524): tracked release 被外层取消 → DB release 完成 + `token.released=True` + claim count=0。
- `test_untracked_release_failure_after_outer_cancel_preserves_cancelled_error` (line 571): untracked release 取消后失败 → CancelledError 透传 + 日志记录。

**层边界**: `dayu.runtime.lane` 未 import `dayu.host` / `dayu.engine`，新增 `_LOGGER` 使用标准 `logging.getLogger(__name__)`。无层边界违反。

**Residual risk**: 单次外层取消后 shielded release 收口正确。重复外层取消（release task 等待期间再次 cancel）不在此修复范围内，匹配 controller adjudication 接受的残余风险。

### A2: dispatch drain_loop wakeup 丢失 — PASS

**审查范围**: `dayu/host/dispatch.py` diff, `tests/host/test_dispatch_scheduler.py` 新增测试

**修复事实**:

`_drain_loop` (dispatch.py:458-463): 移除了 sleep 后的 `if self._queue.empty(): return` 提前退出。现在 drain loop 持续轮询直到 `self._closed`，empty 时 sleep 一次后直接 `drain_once()`。

```python
# 修复后
while not self._closed:
    if self._queue.empty():
        await asyncio.sleep(...)
    await self.drain_once()
```

**测试覆盖**:

`test_drain_loop_continues_when_dispatch_arrives_during_empty_window` (line 473): 使用 `_EnqueueOnSecondEmptyQueue` 在第二次 empty check 时注入 record，验证 drain loop 不提前退出，record 被处理（`factory.created == 1`）。

**层边界**: `_HostCancellationToken` 现显式声明 `class _HostCancellationToken(CancellationToken):` (dispatch.py:209)，Protocol 实现完整性由 pyright 静态守护。无层边界违反。

**Residual risk**: idle scheduler 保持一个 sleeping task 直到显式 `close()`，匹配 controller adjudication 接受的行为变更。

### A3: BatchToolExecutionRequest duplicate tool_call_id — PASS

**审查范围**: `dayu/contracts/tool_call.py` diff, `tests/contracts/test_tool_call.py` 新增测试

**修复事实**:

`__post_init__` (tool_call.py:144-151): 新增 `seen_tool_call_ids: set[str]` 去重检查，重复时抛 `ValueError` 含具体 duplicated id。

**测试覆盖**:

`test_batch_tool_execution_request_rejects_duplicate_tool_call_id` (line 192): 构造两个相同 `tool_call_id="id-1"` 的 `ToolCallRequest`，断言 `ValueError` 匹配 `"unique"`。

**层边界**: 纯 contracts 层校验，无跨层依赖。

### A4: is_retriable assert_never 穷尽守卫 — PASS

**审查范围**: `dayu/engine/runners/openai/error_classifier.py` diff, `tests/engine/runners/openai/test_http_error_classification.py`

**修复事实**:

`is_retriable` (error_classifier.py:146-147): match 末尾新增 `case _: assert_never(error_code)`。同时 `CONTEXT_LENGTH_EXCEEDED` 已在 not-retriable 分支中覆盖。

**测试覆盖**:

`test_is_retriable_branches` (line 87): 遍历所有 `RunnerHTTPErrorCode` 成员，断言 retriable 集合（RATE_LIMIT_EXCEEDED / SERVER_ERROR / NETWORK_ERROR / TIMEOUT）返回 True，not-retriable 集合（CLIENT_ERROR / CONTEXT_LENGTH_EXCEEDED / UNKNOWN_HTTP_STATUS）返回 False。新增枚举成员时 pyright 会在 `assert_never` 处报错。

**层边界**: Engine runner 内部模块，无跨层依赖。

### A5: ToolCancelledOutcome hint 空字符串校验 — PASS

**审查范围**: `dayu/contracts/tool_outcome.py` diff, `tests/contracts/test_tool_outcome_exhaustive.py` 新增测试

**修复事实**:

`__post_init__` (tool_outcome.py:125-126): 新增 `if self.hint is not None and self.hint.strip() == "": raise ValueError(...)`。归一化 `hint=""` 为非法输入，消除 `None` 与空字符串双重无提示状态。

**测试覆盖**:

`test_cancelled_rejects_empty_or_whitespace_hint` (line 190): 遍历 `("", "   ", "\t", "\n", "  \t  \n")` 五种无效 hint，断言 `ValueError`。

**层边界**: 纯 contracts 层校验，无跨层依赖。

### A6: wait_for_or_cancel docstring 修正 — PASS

**审查范围**: `dayu/runtime/cancellation.py` diff

**修复事实**:

docstring (cancellation.py:173-175): 修正为 `pending 完成分支会读取 pending.result()，因此 pending task 中抛出的异常会从本 helper 直接传播给调用方`。与实际代码 line 196 `return WaitCompleted(value=pending.result())` 一致。

**层边界**: `dayu.runtime` 公共 helper，无跨层依赖。

### A7: _HostCancellationToken Protocol 声明 — PASS

**审查范围**: `dayu/host/dispatch.py` diff

**修复事实**:

`_HostCancellationToken` (dispatch.py:209): 从 `class _HostCancellationToken:` 改为 `class _HostCancellationToken(CancellationToken):`。类已实现所有 Protocol 方法，此变更仅添加显式声明，pyright 可静态守护签名一致性。

**层边界**: Host 层内部类实现 runtime contracts Protocol，依赖方向正确（Host → runtime contracts）。

### A8: EventLog payload helper 抽取 — PASS

**审查范围**: `dayu/host/_event_payload.py` (新增), `dayu/host/run_input.py` diff, `dayu/host/engine_ingest.py` diff

**修复事实**:

1. 新增 `dayu/host/_event_payload.py`，包含 `payload_object(event: EventLogRow) -> Mapping[str, JsonValue]` 和 `required_payload_text(payload, *, field_name) -> str`。
2. `run_input.py` 删除重复实现，改为 `from dayu.host._event_payload import payload_object as _payload_object, required_payload_text as _required_payload_text`。
3. `engine_ingest.py` 同样删除重复实现，改为从 `_event_payload` 导入。
4. 错误类型使用 `HostDurableError`，保持 Host 层语义，未向 `dayu.runtime` 泄漏。

**层边界**: `_event_payload.py` 只 import `dayu.contracts.json_value`、`dayu.host.durable.errors`、`dayu.host.durable.event_log`，依赖方向正确（Host 内部 → contracts + durable）。

### A9: public string validation helper 抽取 — PASS

**审查范围**: `dayu/host/_public_validation.py` (新增), `dayu/host/api.py` diff, `dayu/host/tooling.py` diff

**修复事实**:

1. 新增 `dayu/host/_public_validation.py`，包含 `require_non_empty(value, *, field_name)` 和 `require_optional_non_empty(value, *, field_name)`。
2. `api.py` 删除重复实现，改为 `from dayu.host._public_validation import require_non_empty as _require_non_empty, require_optional_non_empty as _require_optional_non_empty`。
3. `tooling.py` 同样删除重复实现，改为从 `_public_validation` 导入。

**层边界**: `_public_validation.py` 无任何 import（纯函数），Host 层内部共享，未向 `dayu.runtime` 泄漏。

### A10: run_input.py 死导入清理 — PASS

**审查范围**: `dayu/host/run_input.py` diff

**修复事实**:

删除 `import json` 和 `from typing import cast`（A8 抽取后不再需要）。同时 `from dayu.host.durable.event_log import ... read_event_by_id ...` 保留（`DurableCurrentRunFactProvider` 仍在使用模块级 `read_event_by_id`）。

**层边界**: 无跨层影响。

## Rejected / Deferred 项确认未实现

逐项核对 diff，确认以下 controller 裁决为 rejected / deferred 的项均未被实现：

| 项目 | 状态 | diff 中是否出现 |
| --- | --- | --- |
| F2 executor CancelledError -> ToolCancelledOutcome | rejected | 否 |
| F4 idempotency INSERT refactor | rejected-needs-evidence | 否 |
| F8 _consume_worker_events cancellation token | rejected-current | 否 |
| F9 DefaultLocalEngineWorker.cancel no-op | rejected-current | 否 |
| F013 CANCELLED terminal payload branch | rejected-current | 否 |
| Engine runner injection | needs-design | 否 |
| _make_final_after_close 命名 | non-blocking | 否 |
| HTTP diagnostic contract | non-blocking | 否 |
| lane heartbeat 全局关闭 | needs-design | 否 |
| God module split | non-blocking | 否 |
| engine/contracts 测试覆盖 | non-blocking | 否 |
| _is_sse_response fallback | needs-evidence | 否 |
| non-stream parser dict 查表 | non-blocking | 否 |
| _make_tool_timeout_terminal_with_close 竞态 | non-blocking | 否 |
| unknown RunnerEvent 日志 | non-blocking | 否 |
| filelock marker 恢复 | non-blocking | 否 |
| schema DDL 事务 | non-blocking | 否 |
| EventLogStore DI | non-blocking | 否 |

## Validation

```bash
# Targeted affected tests
pytest tests/runtime/test_lane.py tests/contracts/test_tool_call.py tests/contracts/test_tool_outcome_exhaustive.py tests/engine/runners/openai/test_http_error_classification.py tests/host/test_dispatch_scheduler.py -q
# Result: 70 passed in 0.72s

# Aggregate tests
pytest tests/host tests/runtime tests/contracts tests/engine -q
# Result: 741 passed in 6.82s

# Type check
python -m pyright dayu/ tests/ utils/
# Result: 0 errors, 0 warnings, 0 informations

# Whitespace check
git diff --check
# Result: passed
```

## Residual Risks

| 风险 | Owner | 说明 |
| --- | --- | --- |
| A1 repeated outer cancellation during shielded release wait | runtime | 单次取消已正确收口；重复取消时 memory state 可能与 DB 不一致，依赖 heartbeat loop 修复。匹配 controller adjudication。 |
| A2 idle scheduler sleeping task | host | drain loop 持续轮询直到 close()，idle scheduler 保持一个 sleeping task。匹配 controller adjudication 的设计意图。 |

## 结论

**PASS**。所有 accepted-current A1-A10 已完整修复，实现正确，测试充分，pyright 通过，无层边界违反，未触及 rejected/deferred 项。可进入 controller final adjudication。
