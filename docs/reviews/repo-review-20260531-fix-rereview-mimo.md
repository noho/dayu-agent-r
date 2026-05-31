# repo-review-fix Re-Review (AgentMiMo)

## 输入

- 原始 MiMo review：`docs/reviews/repo-review-20260531-165913.md`
- 原始 DS review：`docs/reviews/repo-review-20260531-165918.md`
- 修复说明：`docs/reviews/repo-review-20260531-fix-codex.md`
- Re-review 日期：2026-05-31

## 结论

**PASS**

## 已修复项逐项核验

### MiMo 001 / DS-equivalent：幂等写入 INSERT IntegrityError 回读

- **核验文件**：`dayu/host/durable/idempotency.py:157-193`
- **代码证据**：INSERT 外包 `try/except sqlite3.IntegrityError`，捕获后调 `read_idempotency_record` 回读；digest 相同返回既有记录，不同抛 `HostIdempotencyConflictError`，`existing_after_conflict is None` 时 re-raise 原始异常。逻辑与 `event_log.append_event` 模式完全对齐。
- **测试证据**：`tests/host/test_idempotency_store.py:268-301` — `test_integrity_error_with_same_digest_returns_concurrent_record`（fake transaction 首次 fetchone 返回 None、execute 抛 IntegrityError、冲突后 fetchone 返回既有 row，断言 `result_ref == "event-existing"` 且 `fetchone_calls == 2`）和 `test_integrity_error_with_different_digest_raises_conflict`（断言抛 `HostIdempotencyConflictError`）。
- **结论**：PASS。回读语义正确，两种冲突路径均有测试覆盖。

### DS 2：non_stream 非 dict tool_calls fatal/diagnostic

- **核验文件**：`dayu/engine/runners/openai/non_stream_parser.py:438-474`
- **代码证据**：非 dict 元素不再静默 `continue`，改为追加 `RunnerProtocolErrorData(error_code="non_stream_tool_call_not_object")` 到 warnings；循环结束后若 `valid_raw_count == 0`，追加 fatal error `non_stream_tool_calls_empty_after_filter`；返回结果包含 `fatal_errors` 和 `warnings` 两个独立元组。
- **测试证据**：`tests/engine/runners/openai/test_non_stream_response.py:374-416` — `test_non_stream_all_non_dict_tool_calls_emit_protocol_error`：输入 `[None, "bad"]`，断言产出 3 条 protocol error（2 条 not_object + 1 条 empty_after_filter），provider_request_id 正确传播，最后事件为 `RUNNER_DONE` 且 `finish_reason=ERROR`。另有 `test_non_stream_tool_call_index_ignores_non_dict_elements`（332 行）覆盖混合合法/非法元素场景。
- **结论**：PASS。全非法时 fatal 收口，混合时 warning + 正常处理合法元素。

### DS 4：dispatch drain durable retry exhausted active cancel

- **核验文件**：`dayu/host/dispatch.py:1847-1853`
- **代码证据**：`HostTransactionRetryExhaustedError` 分支中，`self._closed = True` 之后、`_best_effort_mark_host_instance_stopped` 之前，新增 `self._active_registry.cancel_all(_DRAIN_LOOP_DURABLE_RETRY_EXHAUSTED_REASON)`。与 heartbeat exit 路径（line 1736-1744）和 scheduler `close()` 的 active cancel 语义对齐。
- **测试证据**：`tests/host/test_dispatch_scheduler.py:1463-1520` — 注册一个 active token，构造 `_RetryExhaustedDrainLoopScheduler` 使 `drain_once` 抛 `HostTransactionRetryExhaustedError`，断言 `active_token.is_cancelled() is True` 且 `cancel_reason() == "drain_loop_durable_retry_exhausted"`。
- **结论**：PASS。fail-close 路径现在完整取消活跃任务。

### DS 5：open_host 启动失败 projection catch-up

- **核验文件**：`dayu/host/open_host.py:686-689,731-755`
- **代码证据**：异常处理块中，`scheduler.close()` 之后、`durable_store.close()` 之前，调用 `_best_effort_catch_up_projection_on_open_failure(close_projection_catchup_port, ...)`。该 helper 对 `None` 端口直接返回；`catch_up_projection()` 失败时只记录 warning 不吞原始异常。
- **测试证据**：`tests/host/test_open_host_runtime.py:557-606` — monkeypatch `StartupRecoveryScanner.scan` 抛 RuntimeError，monkeypatch `_CompositeProjectionCatchupPort.catch_up_projection` 记录调用次数，断言 `catch_up_calls == 1` 且原异常正确传播。
- **结论**：PASS。启动失败路径现在 best-effort flush projection。

### DS 6：Content-Type 缺失时 stream 分流

- **核验文件**：`dayu/engine/runners/openai/runner.py:122-137,584-589`
- **代码证据**：`_is_sse_response` 新增 `if content_type.strip() == "": return False` 分支，对空 Content-Type 保守走非流式解析。调用方 `_do_attempt` 中（line 584-589）对 `stream=True` 且空 Content-Type 记录 warning 诊断。
- **测试证据**：`tests/engine/runners/openai/test_streaming_capability_and_content_type.py:354-391` — `test_stream_true_missing_content_type_uses_non_stream_parser`：构造无 Content-Type 响应、JSON body，断言走 `ContentCompleted + Done` 路径而非 SSE，且 `"runner.http.missing_content_type" in caplog.text`。
- **结论**：PASS。缺失 Content-Type 时保守降级为非流式。

### DS 7：正常 final 空 content fail-closed

- **核验文件**：`dayu/engine/agent.py:1404,1499-1505,1990-1996`
- **代码证据**：`_classify_iteration` 新增 `reject_empty_final_content: bool = True` 参数；line 1499 `if reject_empty_final_content and content == ""` 拒绝空 content 并返回 `runner_empty_final_content` 错误码。force-answer 调用点（line 1990-1996）显式传 `reject_empty_final_content=False`，保留原有 `force_answer_empty` 错误码。
- **测试证据**：`tests/engine/test_agent_phase3_tool_call.py:1860-1872` — `test_normal_final_empty_content_is_fail_closed`：构造空 content final script，断言 terminal 为 `RUN_FAILED` 且 `error_code == "runner_empty_final_content"`。原有 `test_force_answer_empty_and_tool_call_are_fail_closed`（line 1821-1856）仍验证 `force_answer_empty` 错误码。
- **结论**：PASS。两条路径均有独立错误码，行为一致 fail-closed。

### DS 8：sqlite_errorcode no type-ignore

- **核验文件**：`dayu/host/durable/transaction.py:73-80,470-487`
- **代码证据**：定义 `_SQLiteErrorCodeCarrier(Protocol)` 声明 `sqlite_errorcode: int`；`_sqlite_error_code` 使用 `cast(_SQLiteErrorCodeCarrier, error).sqlite_errorcode` 替代 `error.sqlite_errorcode  # type: ignore[attr-defined]`，外层 `try/except AttributeError` + `isinstance(code, int)` 守卫不变。
- **验证**：修复说明声明 pyright 0 errors。
- **结论**：PASS。运行时行为等价，类型检查不再需要 ignore。

### DS 9：filelock release failure 状态

- **核验文件**：`dayu/runtime/filelock.py:98-115`
- **代码证据**：`release()` 在 `except` 分支中 `self.released = True` 后再 `raise RuntimeFileLockError`，避免调用方绕过异常后二次释放。marker restore 失败改为 `_LOGGER.debug` 诊断。
- **测试证据**：`tests/runtime/test_filelock.py:267-284` — `test_release_failure_marks_token_released_to_prevent_retry`：使用 `_FailingThirdPartyLock`，断言异常后 `token.released is True`，二次 `token.release()` 幂等且底层只调用一次。另有 `test_release_marks_released_after_underlying_release_before_marker_failure`（line 240-264）覆盖 marker restore 失败场景。
- **结论**：PASS。release 失败后状态正确，不会二次释放。

## 未修复项裁定核验

| DS# | 问题 | 裁定 | 核验 |
|---|---|---|---|
| 1 | God function 13 处 | 维护性大重构，不纳入本轮 | 合理。行为正确，拆分需大范围回归 |
| 3 | purge replay artifact cleanup | tombstone schema 不足以正确修复 | 合理。`deleted_refs_digest` 是 digest 不可反解析 paths |
| 10 | purge precondition 距离 | BEGIN IMMEDIATE 保证安全 | 合理。同一写事务内，无竞态证据 |
| 11 | scheduler close EOF 分类 | 终态语义变更需独立设计 | 合理。改 terminal 语义影响面大 |
| 12 | cancel deferred check | 需要 public API 时序设计 | 合理。低概率幂等问题 |
| 13 | elapsed_seconds 硬编码 | 需扩展调用链参数 | 合理。非表面修 |
| 15 | scene system prompt 校验 | 配置策略变更 | 合理。不属于 bugfix |
| 16-18 | runner 诊断质量 | 低风险诊断项 | 合理。避免扩大 Runner 清理路径改动面 |
| 19 | SSE tool_calls delta 非 dict | 需独立设计 | 合理。SSE 路径涉及流式聚合契约 |
| 20 | continuation 空 content | 与 continuation 策略相关 | 合理。需独立设计 |
| 21 | cancellation 吞异常 | racy 小窗口诊断透明度 | 合理。低概率 |
| 22-23 | contracts 校验增强 | 可能影响现有调用方 | 合理。不属于 bugfix |
| 24-27 | 事务参数/DDL/tombstone/log | 低风险维护性问题 | 合理 |
| 28 | 测试函数命名 | 提示级 | 合理 |

所有未修项裁定理由充分，不构成本轮 blocker。

## 排除文件确认

- `docs/host/design.md`、`docs/host/conversation-memory-discussion.md`、`docs/host/followup-hardening-control.md` 未被本轮修改触碰。

## 残余风险确认

与修复说明一致：
1. purge replay artifact cleanup 需要 schema 或 GC 设计。
2. God function 拆分、SSE 非 dict tool_calls、continuation 空 content、contracts 校验增强需独立计划。
3. 本轮未运行全仓 pytest，已运行受影响测试 44 passed + pyright 0 errors。
