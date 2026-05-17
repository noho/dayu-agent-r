# Code Review — DS P9 All-Repository Final Re-Review

## 结论：PASS

**理由：** 前次 DS review（`repo-review-ds-20260517-1521.md`）提出的 F1（SSE 已 yield 事件后跨 attempt retry）、F2（SSE tool_calls 最终 Done finish_reason 非 TOOL_CALLS）、F4（RuntimeFileLock.__exit__ release 失败后 stale active token）三项严重问题已全部关闭。F3（minimal read model consumer isolation）已由 controller 裁决为后续 schema design debt，当前 fix 未引入新问题。所有变更均有直接测试覆盖，966 测试全部通过，pyright 零错误。

---

## Scope

- **Mode**: all repository（final re-review after controller fix pass）
- **Branch**: `feat/host-p9-conversation-memory`
- **Output file**: `docs/reviews/repo-review-final-ds-20260517.md`
- **Review date/time**: 2026-05-17 16:05 CST
- **Reviewer**: DS (DeepSeek) — 主 reviewer 单线程逐路径走读
- **Included scope**: `dayu/contracts/tool_outcome.py`、`dayu/engine/agent.py`、`dayu/engine/contracts/runner_spec.py`、`dayu/engine/runners/openai/runner.py`、`dayu/engine/runners/openai/sse_parser.py`、`dayu/engine/runners/openai/non_stream_parser.py`、`dayu/host/dispatch.py`、`dayu/host/durable/projection.py`、`dayu/host/durable/schema.py`、`dayu/host/memory.py`、`dayu/host/wait_adapter.py`、`dayu/runtime/cancellation.py`、`dayu/runtime/filelock.py`、`tests/` 下所有相关测试
- **Excluded scope**: `dayu/config/`、`dayu/render/`、`utils/`、`.venv/`、`__pycache__/`、docs/reviews/ 中非本次变更的 review artifact
- **Parallel review coverage**: 无（本次为针对性 final re-review，由主 reviewer 逐路径走读）

---

## Findings

### F1 复核 — SSE 已 yield 事件后跨 attempt retry：已关闭

- **入口/函数**: `AsyncOpenAIRunner._call_impl`
- **文件(行号)**: `dayu/engine/runners/openai/runner.py:286-353`
- **修复方式**: 在 `_call_impl` 的 while 循环内引入 `attempt_yielded_event` 标志（L295 初始化为 `False`，L300 首次 yield 事件时置 `True`）；当 `_AttemptFailedRetriable` 在 `attempt_yielded_event == True` 时被捕获（L329），不再计算 retry decision，直接产出 `HTTP_ERROR` + `Done(ERROR)` 并 return。
- **直接证据**: 走读路径 L295→L300→L329-L353；若 SSE 已产出 content_delta/tool_call_delta 等事件后 `readany()` 或 idle timeout 触发 `_AttemptFailedRetriable`，L329 分支命中，执行 L341-L353 的错误收口。
- **测试验证**: `test_stream_read_failure_after_event_does_not_retry`（`tests/engine/runners/openai/test_http_error_event.py:404-438`）参数化覆盖 `ClientError`（NETWORK_ERROR）与 `TimeoutError`（TIMEOUT），断言 `len(session.calls) == 1`（不重试），事件流为 `CONTENT_DELTA → HTTP_ERROR → Done(ERROR)`，`provider_request_id` 保持一致。
- **判定**: 已关闭。

### F2 复核 — SSE tool_calls 最终 Done finish_reason 为 TOOL_CALLS：已关闭

- **入口/函数**: `SSEParser._finalize_success`
- **文件(行号)**: `dayu/engine/runners/openai/sse_parser.py:545-549`
- **修复方式**: 在 `_finalize_success` 中，`finish` 变量的计算改为先检查 `_tool_calls_seen` 标志：为 `True` 时强制 `FinishReason.TOOL_CALLS`，否则 fallback 到 `self._finish_reason or FinishReason.STOP`（L545-L549）。非流式路径（`non_stream_parser.py:317-318`）同步加固：`tool_calls_emitted` 为 True 时强制覆盖 `finish_reason = FinishReason.TOOL_CALLS`。
- **直接证据**: SSE 路径 L357 `self._tool_calls_seen = True` 在任何 tool_calls delta 被处理时置位；L545-L549 消费该标志。非流式路径 `_emit_from_dict` L291 `tool_calls_emitted = True` → L317-L318 覆盖。
- **测试验证**: `test_tool_call_done_finish_reason_prefers_tool_calls_over_stop`（`tests/engine/runners/openai/test_sse_tool_call_stream.py:1859-1877`）验证 SSE provider 返回 `finish_reason=stop` 且存在 tool_calls 时 Done 为 `TOOL_CALLS`。`test_non_stream_tool_calls_with_stop_finish_reason_done_as_tool_calls` 与 `test_non_stream_tool_calls_without_finish_reason_done_as_tool_calls`（`tests/engine/runners/openai/test_non_stream_response.py`）覆盖非流式路径。
- **判定**: 已关闭。

### F4 复核 — RuntimeFileLock.__exit__ release 失败后 stale active token：已关闭

- **入口/函数**: `RuntimeFileLock.__exit__`
- **文件(行号)**: `dayu/runtime/filelock.py:198-203`
- **修复方式**: `__exit__` 中 `token.release()` 调用被 `try/finally` 包裹；`finally` 块内 `self._active_token = None` 确保无论 release 是否抛异常都会清理 active token（L200-L203）。
- **直接证据**: L198-L203 走读：`token = self._active_token` → `if token is not None:` → `try: token.release()` → `finally: self._active_token = None`。release 失败 → RuntimeFileLockError 传播给 caller → finally 执行 → `_active_token` 为 None → 下次 `acquire()` 不会命中 L153 的 "already active" 检查。
- **测试验证**: `test_context_manager_release_failure_clears_active_token_and_allows_reacquire`（`tests/runtime/test_filelock.py:2263-2285`）验证 release 失败后 `_active_token is None` 且可成功重新 acquire。
- **判定**: 已关闭。

### F3 复核 — minimal read model consumer isolation：deferred，未引入新问题

- **入口/函数**: `reset_minimal_read_model_projection`
- **文件(行号)**: `dayu/host/durable/read_model.py:280-301`
- **判定**: controller 已裁决为后续 schema design debt，不在本 P9 处理。本次变更中 `advance_projection_checkpoint` 的 CAS 加固（`projection.py:162-197`）对所有 consumer（包括 minimal read model consumer）统一生效，不会加剧 F3 的多 consumer 数据冲突。无新问题引入。

---

### 本次变更中无新增严重或高严重性 finding。

以下记录本次变更中值得注意但非 blocking 的观察：

#### N1 — `_rewake_dispatch_after_current_drain` 使用 `call_soon` 的调度语义

- **入口/函数**: `HostDispatchScheduler._rewake_dispatch_after_current_drain`
- **文件(行号)**: `dayu/host/dispatch.py:555-564`
- **观察**: 使用 `asyncio.get_running_loop().call_soon(self._queue.put_nowait, record)` 将重排项延迟到当前 event loop tick 之后入队。由于 `_queue` 为无界 `asyncio.Queue()`（L334），`put_nowait` 不会因队列满而失败。`call_soon` 确保回调在当前 drain 迭代让出控制权后执行。代码正确，但语义依赖 event loop 调度顺序，未来若 drain loop 重构为 `get_nowait()` 批量消费，需确认 requeue 在清空检查前可见。
- **严重程度**: 低（当前实现正确，仅作为 maintainability 观察记录）。

#### N2 — `assert_never(data)` 替换 fallback `failure_candidate` 赋值

- **入口/函数**: `_AsyncAgent._handle_runner_event`（推断）
- **文件(行号)**: `dayu/engine/agent.py:1332`
- **观察**: 原代码在 match 未命中时赋值 `state.failure_candidate = RunFailedData(...)`；现改为 `assert_never(data)`。这是正确的 strictness 提升：若 `RunnerEventData` 联合新增变体而未更新 match，将在运行时由 `assert_never` 触发 `AssertionError`（类型检查时 pyright 也会报错），而不是静默记录一个模糊的 failure candidate。该变更不改变正常路径行为。
- **严重程度**: 低（类型安全性提升，无功能风险）。

#### N3 — content/reasoning fallback 重构为 `or` 链

- **入口/函数**: `_AsyncAgent._classify_iteration`
- **文件(行号)**: `dayu/engine/agent.py:1395-1415`
- **观察**: tool_calls content/reasoning 的 fallback 逻辑从显式 if-else 链重构为 `or` 短路链。空字符串 `""` 在 `or` 链中为 falsy，等价于旧代码 `if content == "": content = None` 的效果。所有三个来源（`tool_calls_content`、`completed_content`、`content_chunks` join）均为 `""` 的极端边缘情况行为从旧代码的 `None` 变为 `""`，但该情形在生产中几乎不可能出现，且 `""` 与 `None` 在下游 `AssistantMessage` 构造中语义等价。
- **测试验证**: `test_tool_call_iteration_empty_tool_content_falls_back_to_completed_content`（`tests/engine/test_agent_phase3_tool_call.py:994-1026`）覆盖 `tool_calls_content=""` 时正确 fallback 到 `completed_content="先说明"`。
- **严重程度**: 低（等价重构，边缘行为差异无实际影响）。

---

## Open Questions

无。

---

## Residual Risk

| 风险 | 缓解状态 |
|------|---------|
| SSE 重试数据损坏（F1） | 已修复 |
| SSE/非流式 finish_reason 不一致（F2） | 已修复 |
| 文件锁死锁（F4） | 已修复 |
| 投影 consumer 隔离缺失（F3） | Controller deferred，owner: future read model multi-consumer schema |
| Schema migration 策略缺失（F10） | Controller deferred，owner: schema hardening |
| 孤儿 Run（F11） | Controller deferred，owner: Phase 11 |
| 其他 DS 初审中/低严重性 finding（F5-F21） | 部分已修复（F16 position fallback、F18 weak typing guard、F19 usage malformed 处理、F20 unsupported event diagnostic reason）；其余 deferred 或为非 blocking |
| 本次 `call_soon` requeue 语义（N1） | 当前正确，作为 maintainability 观察 |
| RunnerSpec / BatchToolExecutionOutcome 边界校验 | 已修复，测试覆盖 |

---

## 验证

- `pytest -q`: 966 passed
- `pyright dayu tests`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: 通过
