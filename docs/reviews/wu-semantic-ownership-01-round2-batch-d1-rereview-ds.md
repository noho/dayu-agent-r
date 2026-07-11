# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch D1 Re-review (AgentDS)

## Scope

- Re-review target: `DS-D1-01` only
- Mode: current changes (workspace diff relative to HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: HEAD
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-rereview-ds.md`
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-review-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-review-fix-controller-validation.md`
- Included scope: Engine Agent `_run_force_answer` production fix + `test_force_answer_empty_and_tool_call_are_fail_closed` test assertions
- Excluded scope: All other D1 changes (unchanged since MiMo/DS first review), D2, E

## Re-review Method

按以下顺序沿真实代码路径走读：

1. `_fallback_after_tools` → 构造 `_FallbackTriggerReason` → 传递到 `_run_force_answer`
2. `_run_force_answer` 内三个 force-answer 失败分支（`_ToolCallsDecision`、`RunFailedData` guard、`_FinalDecision` 空内容）
3. 每个失败分支的 `_fallback_failure_message` 调用链
4. 测试断言覆盖上述三条分支及两种 trigger error_code

## Findings

### DS-D1-01 关闭确认

原始 finding 描述：`test_force_answer_empty_and_tool_call_are_fail_closed` 未断言 force-answer 失败消息中保留了原始 fallback trigger 语义（`trigger=` 前缀）。

Review-fix 期间发现此问题从测试 gap 升级为直接生产 mismatch：`_run_force_answer` 的 tool-call-not-enabled 路径直接用 `_TOOL_CALL_NOT_ENABLED_MESSAGE` 构造 `RunFailedData.message`，未调用 `_fallback_failure_message(trigger=...)` 附加 trigger 前缀。force-answer-empty 路径同样缺失。

#### 生产代码修复验证

**`_run_force_answer` (agent.py:2295-2408) 三个失败分支**：

| 分支 | 行号 | trigger 是否保留 | 证据 |
|------|------|-----------------|------|
| `_ToolCallsDecision` (force-answer 产出 tool calls) | L2357-2371 | ✅ | `_fallback_failure_message(trigger=trigger, failure_message=_TOOL_CALL_NOT_ENABLED_MESSAGE)` |
| `RunFailedData` 且 `error_code == _ERROR_TOOL_CALL_NOT_ENABLED` (classify 阶段拒绝 tool calls) | L2373-2384 | ✅ | 同上前缀，且正确保留 `provider_request_id`、`recoverable`、`client_correlation_id` |
| `_FinalDecision` 且 `content.strip() == ""` (force-answer 空内容) | L2389-2404 | ✅ | `_fallback_failure_message(trigger=trigger, failure_message=_FORCE_ANSWER_EMPTY_MESSAGE)` |

**trigger 传递链完整性**：

1. `_fallback_after_tools` (L2244) 接收 `trigger: _FallbackTriggerReason` → 传递给 `_run_force_answer` (L2289) ✅
2. `_fallback_after_tools` 调用方 (L1041-1044, L1052-1055) 通过 `_fallback_trigger()` 构造 trigger ✅
3. `_fallback_failure_message` (L392-403) 格式：`{failure_message}; trigger={trigger.error_code.value}` ✅

**RAISE_ERROR 路径**：`_fallback_after_tools` 中 RAISE_ERROR 分支 (L2266-2277) 使用 `trigger.error_code` 和 `trigger.message`，不涉及 force-answer 路径，不在 DS-D1-01 scope 内。当前行为正确。

**未覆盖的边界**：
- `_run_force_answer` 中 `state is None` 分支 (L2326-2343) 使用 `_MISSING_TERMINAL_MESSAGE` 无 trigger 前缀。这是内部 invariant violation，不是正常 force-answer 失败，无需 trigger 语义。
- `_classify_iteration` 在 `reject_empty_final_content=False` (L2355) 时不拒绝空内容，空内容判断由 L2390 手动完成以保证 trigger 前缀注入。设计正确。

#### 测试覆盖验证

**`test_force_answer_empty_and_tool_call_are_fail_closed` (test_agent_phase3_tool_call.py:1962-2040)**：

| 测试场景 | trigger error_code | force-answer 失败类型 | 断言 |
|----------|-------------------|----------------------|------|
| `empty_runner` | `max_iterations_exceeded` | `force_answer_empty` | `assert "trigger=max_iterations_exceeded" in empty_failure.message` (L1984) ✅ |
| `tool_call_runner` | `max_iterations_exceeded` | `tool_call_not_enabled` | `assert "trigger=max_iterations_exceeded" in force_tool_failure.message` (L2010) ✅ |
| `failed_batch_runner` (新增) | `consecutive_failed_tool_batches` | `force_answer_empty` | `assert "trigger=consecutive_failed_tool_batches" in failed_batch_failure.message` (L2037-2039) ✅ |

三个场景覆盖了两种 trigger error_code × 两种 force-answer 失败类型（empty / tool-call）的组合。

#### 语义所有权确认

- **trigger error_code 的 owner**：Engine Agent（`_FallbackTriggerReason.error_code` 由 `_fallback_trigger()` 在 `_fallback_after_tools` 入口构造）。
- **force-answer 失败消息的 owner**：Engine Agent（`_run_force_answer` 内 `_fallback_failure_message()` 是唯一构造点）。
- **Host 不参与 trigger 语义**：Host `engine_ingest.py` 仅消费 `RunFailedData.error_code`（结构化字段），不解析 message 中的 `trigger=` 前缀。符合"trigger 仅用于人类可读诊断"的设计约定。
- **测试的 owner**：测试断言 Engine Agent 的 contract 行为（`RunFailedData.message` 包含 trigger 前缀），不依赖 Host 或下游消费者。

## Open Questions

无。

## Residual Risk

- `consecutive_failed_tool_batches` + `tool_call_not_enabled` 组合无直接测试覆盖（仅覆盖了 `consecutive_failed_tool_batches` + `force_answer_empty`）。但 `tool_call_not_enabled` 路径的 trigger 注入已在 `max_iterations_exceeded` 场景下验证，且 `_fallback_failure_message` 的 trigger 拼接逻辑与 trigger 值无关，风险极低。
- `_fallback_failure_message` 仍使用字符串拼接（`; trigger=` 前缀），非结构化字段。此设计在当前 contract 下已接受（见原 DS review Residual Risk），不在 DS-D1-01 scope 内。
- 验证结果确认：436 passed, pyright 0 errors。

## Conclusion

- conclusion: **DS-D1-01 已关闭。** 生产代码 `_run_force_answer` 的三个 force-answer 失败分支均已通过 `_fallback_failure_message(trigger=...)` 在 `RunFailedData.message` 中保留原始 fallback trigger error_code。测试覆盖了 `max_iterations_exceeded` 和 `consecutive_failed_tool_batches` 两种 trigger，以及 `force_answer_empty` 和 `tool_call_not_enabled` 两种 force-answer 失败类型。语义所有权收敛到 Engine Agent，Host 不参与 trigger 构造或消费。
- findings count: 0（无新增 finding）
- accepted findings closed: 1 (DS-D1-01)
- artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-rereview-ds.md`
- residual risk: 见上方 Residual Risk 节
- no code changes confirmation: 确认，本 re-review 未修改任何代码。
