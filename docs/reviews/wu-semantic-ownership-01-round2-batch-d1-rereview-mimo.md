# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch D1 Re-Review (AgentMiMo)

## Scope

- Mode: Current Changes (re-review of review-fix)
- Branch: `phaseflow/host-issues-control`
- Base: HEAD (workspace uncommitted changes)
- Timestamp: 20260711-192643
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-rereview-mimo.md`
- Included scope: DS-D1-01 closure verification
- Excluded scope: Batch D2, Batch E

## Re-Review Context

- Original review finding: `DS-D1-01` (DS code review) — `test_force_answer_empty_and_tool_call_are_fail_closed` 未断言 force-answer 失败消息中保留原始 fallback trigger 语义。
- Controller adjudication: accepted，要求增加 focused assertions。
- Review-fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-review-fix-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-review-fix-controller-validation.md`（436 passed, pyright 0 errors）

## DS-D1-01 Closure Verification

### 原始 Finding 诉求

`test_force_answer_empty_and_tool_call_are_fail_closed` 应断言 force-answer 失败时在 `RunFailedData.message` 中保留原始 fallback trigger error code（如 `trigger=max_iterations_exceeded`），覆盖 force-answer 空内容和 tool-call 失败两条路径。

### Fix 实现验证

**生产代码变更** — `dayu/engine/agent.py`：

1. 新增 `_FallbackTriggerReason` 结构化触发原因（L705-715），封装 `error_code` 和 `message`。
2. 新增 `_fallback_trigger()` 辅助函数（L382-395）构造 `_FallbackTriggerReason`。
3. 新增 `_fallback_failure_message()` 辅助函数（L398-412）拼接 `failure_message; trigger=<error_code>` 格式。
4. `_fallback_after_tools` 参数从 `error_code: EngineRunErrorCode` 改为 `trigger: _FallbackTriggerReason`（L2247-2253），RAISE_ERROR 路径使用 `trigger.error_code` 和 `trigger.message`。
5. `_run_force_answer` 新增 `trigger: _FallbackTriggerReason` 参数（L2299-2300），在三处失败路径使用 `_fallback_failure_message(trigger=trigger, failure_message=...)`：
   - tool-call-not-enabled 路径（L2358-2364）
   - decision 为 `RunFailedData(error_code=tool_call_not_enabled)` 路径（L2374-2383）
   - force-answer-empty 路径（L2388-2394）

**测试变更** — `tests/engine/test_agent_phase3_tool_call.py`：

1. L1984: `assert "trigger=max_iterations_exceeded" in empty_failure.message` — 覆盖 force-answer 空内容 + max_iterations trigger。
2. L2010: `assert "trigger=max_iterations_exceeded" in force_tool_failure.message` — 覆盖 force-answer tool-call 失败 + max_iterations trigger。
3. L2017-2040: 新增 `consecutive_failed_tool_batches` trigger 路径测试，断言 `assert "trigger=consecutive_failed_tool_batches" in failed_batch_failure.message`。

### 证据链

| 验证项 | 结果 | 证据 |
|--------|------|------|
| force-answer empty + max_iterations trigger 保留 | ✅ | test L1984 断言 `trigger=max_iterations_exceeded` in message |
| force-answer tool-call + max_iterations trigger 保留 | ✅ | test L2010 断言 `trigger=max_iterations_exceeded` in message |
| force-answer empty + consecutive_failed_tool_batches trigger 保留 | ✅ | test L2036-2040 断言 `trigger=consecutive_failed_tool_batches` in message |
| 生产代码通过 `_fallback_failure_message` 拼接 trigger | ✅ | agent.py L2358-2364, L2374-2383, L2388-2394 |
| `_fallback_after_tools` 传递结构化 trigger 而非 raw error_code | ✅ | agent.py L2247, L2263, L2286 |
| 测试通过 | ✅ | `1 passed in 0.12s` |
| Controller validation 通过 | ✅ | 436 passed, pyright 0 errors |

### 超出原始 Finding 的改进

Review-fix 不仅补齐了测试断言，还发现并修复了生产代码中的直接 mismatch：

- **问题**：`_run_force_answer` 的 tool-call-not-enabled 路径之前使用硬编码 `_TOOL_CALL_NOT_ENABLED_MESSAGE`，未通过 `_fallback_failure_message` 保留原始 trigger。
- **修复**：`_run_force_answer` 接收 `trigger` 参数，所有失败路径统一通过 `_fallback_failure_message` 拼接 trigger。
- **评估**：修复范围最小化，仅触及 Engine Agent owner 内部，未扩散到其他模块，符合 controller 要求的"不改变生产行为除非测试暴露 direct mismatch"原则。

## Findings

未发现实质性问题。

DS-D1-01 的 fix 完整覆盖了原始 finding 的所有诉求：
- 测试断言覆盖三条 force-answer 失败路径的 trigger 语义保留。
- 生产代码修复确保 `_fallback_failure_message` 在所有 force-answer 失败路径生效。
- fix 范围收敛在 Engine Agent owner 内部，无 scope creep。

## Open Questions

无。

## Residual Risk

- trigger 语义仍通过 `RunFailedData.message` 字符串暴露，未引入结构化 `trigger_error_code` 字段。当前无已知消费者需要程序化解析 trigger，与 D1 accepted contract 一致。
- `_fallback_failure_message` 使用分号分隔格式（`failure_message; trigger=<error_code>`），若 failure_message 本身含分号可能产生歧义。当前所有 failure_message 均为硬编码常量且不含分号，风险可接受。

## Conclusion

- **结论**: DS-D1-01 已关闭。review-fix 完整覆盖原始 finding 诉求，测试断言和生产代码修复均到位。
- **Findings count**: 0
- **Accepted findings closed**: DS-D1-01 ✅
- **Artifact**: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-rereview-mimo.md`
- **Residual risk**: trigger 仍为 message 字符串格式，与 D1 contract 一致；无新风险。
- **No code changes confirmation**: 确认，本 re-review 未修改任何代码。
