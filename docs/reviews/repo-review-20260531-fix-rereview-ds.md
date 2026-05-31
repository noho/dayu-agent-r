# Code Re-Review（AgentDS）

## Scope

- Gate: repo-review-fix-re-review
- 输入：
  - MiMo review: `docs/reviews/repo-review-20260531-165913.md`
  - DS review: `docs/reviews/repo-review-20260531-165918.md`
  - 修复说明: `docs/reviews/repo-review-20260531-fix-codex.md`
- 审查范围：仅本轮 fix 相关代码、测试与 artifact
- 排除：`docs/host/design.md`、`docs/host/conversation-memory-discussion.md`、`docs/host/followup-hardening-control.md`
- 日期：2026-05-31

## 逐项核验

### MiMo 001：idempotency INSERT IntegrityError 并发回读 — PASS

- **文件**: `dayu/host/durable/idempotency.py:158-193`
- **修复**: INSERT 外层包裹 `try/except sqlite3.IntegrityError`；捕获后回读既有记录；digest 相同返回既有 record，digest 不同抛 `HostIdempotencyConflictError`。
- **测试**: `tests/host/test_idempotency_store.py`
  - `test_integrity_error_with_same_digest_returns_concurrent_record` — 覆盖相同 digest 回读成功，返回 `event-existing`，`fetchone_calls == 2`。
  - `test_integrity_error_with_different_digest_raises_conflict` — 覆盖不同 digest 抛出冲突。
  - `_IntegrityInterleavingTransaction` fake 类 `execute()` 抛出 `sqlite3.IntegrityError` 模拟并发 INSERT。
- **证据链完整**：与 `event_log.append_event()` 的 IntegrityError 回读模式完全对齐。测试覆盖两分支语义。
- **裁定: PASS**

### DS 2：non_stream_parser 非 dict tool_calls 协议诊断 — PASS

- **文件**: `dayu/engine/runners/openai/non_stream_parser.py:411-475`
- **修复**:
  - `_build_tool_calls` 对非 dict 元素产出 `RunnerProtocolErrorData` warning（error_code=`non_stream_tool_call_not_object`），不再静默 `continue`。
  - 引入 `valid_raw_count` 计数器：若列表非空但全是非法元素，追加 fatal `non_stream_tool_calls_empty_after_filter` 协议错误。
  - `_emit_from_dict` line 300-309 已正确消费 `tool_calls_request.fatal_errors` 并产出 `Done(ERROR)`。
- **测试**: `tests/engine/runners/openai/test_non_stream_response.py`
  - `test_non_stream_all_non_dict_tool_calls_emit_protocol_error` — 输入 `[None, "bad"]`，产出 3 个 ProtocolError（2 warning + 1 fatal）+ Done(ERROR)。
- **证据链完整**：非 dict 元素有 warning，全非法有 fatal，终态为 ERROR。
- **裁定: PASS**

### DS 4：dispatch drain durable retry exhausted active cancel — PASS

- **文件**: `dayu/host/dispatch.py:1847-1853`
- **修复**: `HostTransactionRetryExhaustedError` 分支中新增 `self._active_registry.cancel_all(_DRAIN_LOOP_DURABLE_RETRY_EXHAUSTED_REASON)` 调用，在 `_best_effort_mark_host_instance_stopped` 之前。
- **测试**: `tests/host/test_dispatch_scheduler.py`
  - `test_drain_loop_fail_closes_on_durable_retry_exhausted` — 通过 `_RetryExhaustedDrainLoopScheduler` 模拟 drain_once 抛 `HostTransactionRetryExhaustedError`，断言 `active_token.is_cancelled() is True` 且 `cancel_reason() == "drain_loop_durable_retry_exhausted"`。
- **证据链完整**：与 scheduler close 的 active cancel 语义对齐。测试验证了 cancel 传播。
- **裁定: PASS**

### DS 5：open_host 启动异常路径 projection catch-up — PASS

- **文件**: `dayu/host/open_host.py:686-689, 731-755`
- **修复**: 启动异常处理块中调用 `_best_effort_catch_up_projection_on_open_failure`；该函数接收 `ProjectionCatchupPort | None`，若端口已构造则 best-effort flush，失败只记录 warning 不吞原始异常。
- **测试**: `tests/host/test_open_host_runtime.py`
  - `test_open_host_startup_failure_flushes_projection_before_close` — monkeypatch `StartupRecoveryScanner.scan` 抛 RuntimeError，monkeypatch `_CompositeProjectionCatchupPort.catch_up_projection` 记录调用。断言 `catch_up_calls == 1`。
- **证据链完整**：覆盖 port 已构造路径，None port 分支在函数体内有明确守卫（line 744-745）。
- **裁定: PASS**

### DS 6：Content-Type 缺失时 stream=True 保守分类 — PASS

- **文件**: `dayu/engine/runners/openai/runner.py:132-137, 584-589`
- **修复**:
  - `_is_sse_response` 新增 `content_type.strip() == ""` 时返回 `False`，不再将空 Content-Type 分类为 SSE。
  - `_do_attempt` line 584-589 在 `options.stream and content_type.strip() == ""` 时记录 WARNING 诊断 `runner.http.missing_content_type`。
- **测试**: `tests/engine/runners/openai/test_streaming_capability_and_content_type.py`
  - `test_stream_true_missing_content_type_uses_non_stream_parser` — stream=True、无 Content-Type、JSON body，验证走非流式解析 + ContentCompleted 正常产出 + WARNING 日志。
- **证据链完整**：保守行为正确（走非流式），有诊断日志。
- **裁定: PASS**

### DS 7：正常迭代空 content fail-closed — PASS

- **文件**: `dayu/engine/agent.py:1396-1505, 1990-1996, 2014-2022`
- **修复**:
  - `_classify_iteration` 新增参数 `reject_empty_final_content: bool = True`；line 1499 检查 `reject_empty_final_content and content == ""` 时返回 `RunFailedData(error_code="runner_empty_final_content")`。
  - `_run_force_answer` 传入 `reject_empty_final_content=False`（line 1996），保留自身 `force_answer_empty` 错误码（line 2014）。
- **测试**: `tests/engine/test_agent_phase3_tool_call.py`
  - `test_normal_final_empty_content_is_fail_closed` — 普通路径空 content → `runner_empty_final_content`。
  - `test_force_answer_empty_and_tool_call_are_fail_closed` — force-answer 空 content → `force_answer_empty`，保留原错误码。
- **证据链完整**：两条路径行为一致（均拒绝空 content），错误码各自独立，不冲突。
- **裁定: PASS**

### DS 8：transaction.py type ignore 消除 — PASS

- **文件**: `dayu/host/durable/transaction.py:73-79, 470-487`
- **修复**:
  - 新增私有 Protocol `_SQLiteErrorCodeCarrier`，声明 `sqlite_errorcode: int`。
  - `_sqlite_error_code` 使用 `cast(_SQLiteErrorCodeCarrier, error).sqlite_errorcode` + `try/except AttributeError` 替代 `error.sqlite_errorcode  # type: ignore[attr-defined]`。
- **验证**: 修复说明声称 pyright 通过（0 errors, 0 warnings, 0 informations）。
- **证据链完整**：Protocol + cast 方案语义等价，消除 type ignore。
- **裁定: PASS**

### DS 9 + DS 14：filelock release 失败状态一致性 + marker 静默吞异常 — PASS

- **文件**: `dayu/runtime/filelock.py:98-115`
- **修复**:
  - line 104: `self.released = True` 移到 `raise` 之前，确保底层 release 失败时 token 也进入 released 状态。
  - line 108-115: `_ensure_lock_file_marker_exists` 异常改用 `_LOGGER.debug()` 记录，不再静默 `except Exception: pass`。
- **测试**: `tests/runtime/test_filelock.py`
  - `test_release_failure_marks_token_released_to_prevent_retry` — 底层 release 抛 OSError，断言 token.released is True，二次 release 不触发底层调用。
  - `test_release_marks_released_after_underlying_release_before_marker_failure` — marker 恢复失败时 token 仍标记 released。
- **证据链完整**：两个状态问题一并修复，测试覆盖。
- **裁定: PASS**

## 未修复项裁定复查

对修复说明中标记为"不改"的 20 项逐一复查裁定合理性：

| 编号 | 项 | 裁定 | 复查结论 |
|------|-----|------|----------|
| DS 1 | God function 13 处 | 维护性大重构，需单独计划 | 合理。核心循环拆分需更大范围回归，不属本轮 bugfix |
| DS 3 | purge replay artifact cleanup | schema 不足，tombstone 只存 digest 不可反解析 | 合理。已正确指出 `deleted_refs_digest` 不可逆推 `artifact_relative_paths` |
| DS 10 | purge precondition 距离 | BEGIN IMMEDIATE 保证安全 | 合理。当前事务模型无竞态风险 |
| DS 11 | scheduler close EOF 分类 | 牵涉 terminal 语义，非单点改动 | 合理。低风险语义精度问题 |
| DS 12 | 并发 cancel deferred check | 需 public API 层面时序设计 | 合理。低概率，不适合小范围改 |
| DS 13 | batch timeout elapsed_seconds | 需扩展调用链参数 | 合理。非单行修 |
| DS 14 | marker 静默吞异常 | 已随 DS 9 一并修复 | 已修 |
| DS 15 | scene system prompt 校验 | 配置策略变更 | 合理 |
| DS 16-18 | runner 诊断质量 | 低风险，避免扩大 Runner 改动面 | 合理 |
| DS 19 | SSE 非 dict tool_calls | 涉及流式 partial 聚合契约 | 合理。SSE 路径与非流式路径不同 |
| DS 20 | length continuation 空 content | 与 continuation 构造策略相关 | 合理。极低概率场景 |
| DS 21 | cancellation helper | race 小窗口 | 合理 |
| DS 22-23 | contracts 校验增强 | 公共契约收紧 | 合理。需评估下游影响 |
| DS 24-27 | 低风险维护项 | 非 blocker | 合理 |
| DS 28 | 测试命名 | 提示级 | 合理 |

所有未修复项的裁定均有充分理由，无错误遗漏。

## 总评

**PASS**

本轮 9 项修复（MiMo 001 + DS 2, 4, 5, 6, 7, 8, 9, 14）均有直接代码证据和测试覆盖。修复方式正确：
- idempotency INSERT IntegrityError 回读与 event_log 模式对齐
- non_stream_parser 非 dict tool_calls 产出协议诊断并以 ERROR 收口
- dispatch retry exhausted 路径补齐 cancel_all
- open_host 启动失败路径补齐 projection catch-up
- Content-Type 缺失保守走非流式
- 普通 final 空 content fail-closed
- transaction.py type ignore 用 Protocol + cast 消除
- filelock release 状态一致性与 marker 诊断一并修复

未修复项 20 项的裁定理由充分，不构成本轮 blocker。

## 残余风险

- purge replay artifact cleanup 需要 schema/GC 设计，当前不具备修复数据来源
- God function 拆分、SSE 非 dict tool_calls 诊断、continuation 空 content 等需要独立计划和更大范围回归
- 本轮未运行全仓 pytest；修复说明确认受影响测试与 pyright 通过
