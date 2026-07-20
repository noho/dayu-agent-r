# Code Review — WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch D1

## Scope

- Mode: current changes (workspace diff relative to HEAD)
- Branch: `phaseflow/host-issues-control`
- Base: HEAD (workspace uncommitted changes)
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-code-review-ds.md`
- Included scope: 24 changed files — Engine RunnerEvent contract, AgentPolicy fallback_mode contract, Agent final answer blankness, Engine Agent tests, OpenAI runner adapter reuse, Host ingest blankness removal, runtime scene_prepare/config_loader/assembly convergence, service host_assembly convergence, README updates.
- Excluded scope: Batch D2 (Host terminal/status, tool outcome codec, compaction evidence, memory projection), Batch E (Fins typing/runtime hygiene).
- Parallel review coverage: 无（单 reviewer 全量走读）。

## Findings

### 1-未修复-低-test_force_answer_empty_and_tool_call_are_fail_closed 未断言 fallback 失败消息中的 trigger 语义

- **入口/函数**: `test_force_answer_empty_and_tool_call_are_fail_closed` 中的 force-answer 空内容和 tool_call 失败断言
- **文件(行号)**: `tests/engine/test_agent_phase3_tool_call.py:1982-2013`
- **输入场景**: force-answer Runner 产出空内容或继续产出 tool calls
- **实际分支**: 测试成功断言 `error_code == "force_answer_empty"` 和 `error_code == "tool_call_not_enabled"`，但未检查 `message` 字段
- **预期行为**: Engine 在 force-answer 失败时通过 `_fallback_failure_message()` 在 message 中附加 `; trigger=<原始错误码>` 前缀（如 `trigger=max_iterations_exceeded`）。这是本批次明确要求的语义：force-answer trigger 语义不应只存在于 error_code（此时 error_code 已经是 force-answer 自身的失败码），trigger 原因为何要从 message 中解析。
- **实际行为**: 测试仅验证了 force-answer 的终态 error_code（`force_answer_empty` / `tool_call_not_enabled`），未验证消息中保留了原始 trigger error_code（`max_iterations_exceeded` / `consecutive_failed_tool_batches`）。若 `_fallback_failure_message` 被意外移除或 trigger prefix 出错，测试不会捕获。
- **直接证据**: `dayu/engine/agent.py:2382-2386` 调用 `_fallback_failure_message(trigger=trigger, failure_message=...)` 构造消息；`dayu/engine/agent.py:396-403` `_fallback_failure_message` 在 failure_message 后拼接 `; trigger=<error_code>`。但 `test_agent_phase3_tool_call.py:1982-1986` 只断言 `empty_failure.error_code`，不断言 `empty_failure.message` 包含 trigger 前缀。
- **影响**: 低。error_code 字段仍承载 force-answer 自身的失败类型，trigger 丢失仅影响人类可读诊断消息中的溯源能力，不影响结构化错误码判断。
- **建议改法和验证点**: 在 empty_runner 分支增加 `assert "trigger=max_iterations_exceeded" in empty_failure.message`；在 tool_call_runner 分支增加 `assert "trigger=max_iterations_exceeded" in force_tool_failure.message`。同时考虑对 `consecutive_failed_tool_batches` 路径的 force-answer 失败也覆盖 trigger 语义。
- **修复风险（低）**: 纯测试增强，不改生产代码。
- **严重程度（低）**: 消息级溯源缺失，不导致错误行为。

## Open Questions

- 无。

## Residual Risk

- **force-answer trigger 仅在 message 字符串中暴露**：`RunFailedData.error_code` 在 force-answer 失败时为 `force_answer_empty` / `tool_call_not_enabled`，原始 trigger（如 `max_iterations_exceeded`）仅通过 message 的 `trigger=` 前缀间接暴露。未来若下游需要程序化消费 trigger，可能需要引入结构化字段。当前影响低，因没有已知消费者需要程序化解析 trigger。
- **`dayu/engine/contracts/agent_policy.py` 对 `AgentFallbackMode` 的 re-export** 目前被 `agent.py`、`_execution_config_projection.py` 及若干测试文件直接消费（`from dayu.engine.contracts.agent_policy import AgentFallbackMode`）。这是 companion type 的共置模式（`AgentPolicy` 与 `AgentFallbackMode` 在同一模块），不是仅保持旧路径的兼容 re-export。若后续所有消费者统一走 `dayu.contracts`，可将 engine 层 re-export 移除；当前状态合理。
- **D2 未覆盖区域**（本批复核确认未触及）：Host terminal/status projection、tool outcome codec、compaction evidence owner、memory projection owner、Host public API runtime-resolvable 注解 — 均待下一批次。
- **测试未覆盖的 fallback path**：`_fallback_after_tools` 的 `assert_never(mode)` 分支（line 2293）在 `AgentFallbackMode` 包含所有合法值时不可达；`AgentPolicy.__post_init__` 的 `isinstance` 校验确保非法 mode 不会到达此处。未直接覆盖但由构造期校验保障。

## Conclusion

Batch D1 实现准确收敛了 5 个语义所有权问题，未发现 scope creep、兼容 shim 或弱类型违规：

1. **RunnerEvent type/data 配对**：Engine contract 拥有 `RUNNER_EVENT_TYPE_TO_DATA` 真源 + `runner_event_type_for_data()` 派生 helper + `validate_runner_event_pairing()` 构造期校验；两个 OpenAI adapter 复用同一 helper；`test_malformed_runner_event_pairing_fails_closed` 证明 malformed Runner 不会被解释为成功。

2. **final answer 空白判定**：Engine `_classify_iteration` 使用 `.strip()` 拒绝空白内容；force-answer 路径在两处（`_classify_iteration` 的 `reject_empty_final_content` 与手动的 `decision.content.strip()` check）都使用同源谓词；Host `_final_answer_plan` 不再独立判空；`_REASON_EMPTY_FINAL_ANSWER` 已删除。

3. **AgentFallbackMode 收敛**：定义移至 `dayu.contracts.agent_policy`，`AGENT_FALLBACK_MODES` 从枚举值派生（消除 divergent string set 可能）；runtime `_agent_policy_constants.py` 已删除；`SceneAgentFallbackMode` 已删除；`AgentPolicy.__post_init__` 增加 `isinstance` 校验。

4. **Engine Agent 测试不再导入 OpenAI runner 内部实现**：`test_agent_phase3_tool_call.py` 改为直接使用 fake RunnerEvent；`test_import_boundary.py` 新增 AST 扫描守卫。

5. **continuation/fallback trigger 语义收敛**：`_FallbackTriggerReason` 封装触发原因，force-answer 失败消息保留 `trigger=` 前缀；不再由多个 owner 各自推导或复制触发语义。

- findings count: 1（低严重度，测试增强建议）
- artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-code-review-ds.md`
- residual risk: 见上方 Residual Risk 节
- no code changes confirmation: 确认，本 review 未修改任何代码。
