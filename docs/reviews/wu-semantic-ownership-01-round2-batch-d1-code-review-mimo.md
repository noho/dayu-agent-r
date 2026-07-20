# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch D1 Code Review (AgentMiMo)

## Scope

- Mode: Current Changes
- Branch: `phaseflow/host-issues-control`
- Base: `HEAD` (workspace uncommitted changes)
- Timestamp: 20260711-191454
- Output file: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-code-review-mimo.md`
- Included scope: Batch D1 实现 — Engine RunnerEvent / AgentPolicy / Agent state public contract ownership
- Excluded scope: Batch D2 (Host terminal/status, tool outcome codec, compaction evidence, memory projection), Batch E (Fins typing)

## Review Context

- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round2-batch-d1-controller-validation.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-round2-controller-adjudication.md`
- Validation result: 436 passed, pyright 0 errors, git diff --check pass

## Findings

未发现实质性问题。

所有 D1 scope 内的 owner corrections 已正确实现，无违反 AGENTS.md 或架构硬约束的情况。

## Implementation Verification

### 1. RunnerEvent.type/data pairing (144159-02 / 145711-13)

**验证结果：✅ 通过**

- `dayu/engine/contracts/runner_events.py:314-368` 新增 `RUNNER_EVENT_TYPE_TO_DATA` 映射、`runner_event_type_for_data` 和 `validate_runner_event_pairing`，type/data 配对真源归 Engine contract。
- `RunnerEvent.__post_init__` (L386-394) 构造时调用 `validate_runner_event_pairing`，malformed pairing 在构造边界 fail fast。
- OpenAI SSE parser (`sse_parser.py:492-493`) 和 non-stream parser (`non_stream_parser.py:459`) 复用 `runner_event_type_for_data`，删除了各自的 match/assert_never 映射。
- 测试覆盖：`test_runner_event_contract.py` 新增 `test_runner_event_constructs_all_valid_pairings` 和 `test_runner_event_rejects_invalid_pairing`；`test_agent_phase2.py` 新增 `test_malformed_runner_event_pairing_fails_closed` 确保 custom Runner malformed event 不被解释成成功 final。
- `__all__` 正确导出新符号。

### 2. Final answer blankness single Engine owner (143516-01)

**验证结果：✅ 通过**

- `dayu/engine/agent.py:1838` 使用 `content.strip() == ""` 判定空白 final answer，Engine 拥有该语义。
- `dayu/engine/agent.py:2379` force-answer 路径同样使用 `decision.content.strip() == ""` 判定，错误消息通过 `_fallback_failure_message` 保留原始 trigger error code。
- `dayu/host/engine_ingest.py` 删除了 `_REASON_EMPTY_FINAL_ANSWER` (L253 删除) 和 `_final_answer_plan` 中的独立空白检查 (L4962-4973 删除)，Host 不再用另一套谓词修补 Engine final answer。
- 测试覆盖：`test_agent_phase2.py` 新增 `test_whitespace_only_final_answer_fails_closed` 验证纯空白 `" \n\t "` 被 Engine 拒绝；`test_engine_ingest_mapping.py` 更新为测试 Engine-owned `RUNNER_EMPTY_FINAL_CONTENT` 失败映射；`test_watch_session_events.py` 更新为测试 Engine-owned 空 final 失败投影为 failed HostEvent。
- README 更新：`dayu/engine/README.md` 和 `dayu/host/README.md` 同步更新语义描述。

### 3. AgentFallbackMode shared lower-level contract (144159-08)

**验证结果：✅ 通过**

- `dayu/contracts/agent_policy.py` 新建层中立 `AgentFallbackMode` 枚举和 `AGENT_FALLBACK_MODES` frozenset。
- `dayu/contracts/__init__.py` 正确导出 `AgentFallbackMode` 和 `AGENT_FALLBACK_MODES`。
- `dayu/engine/contracts/agent_policy.py` 删除本地 `AgentFallbackMode` 定义，改为从 `dayu.contracts.agent_policy` 导入；`AgentPolicy.__post_init__` 新增 `isinstance(self.fallback_mode, AgentFallbackMode)` 类型校验。
- `dayu/runtime/_agent_policy_constants.py` 整个删除，`dayu/runtime/assembly.py` 和 `dayu/runtime/config_loader.py` 改为从 `dayu.contracts` 导入。
- `dayu/runtime/scene_prepare.py` 删除 `SceneAgentFallbackMode`，`SceneAgentPolicyOverride.fallback_mode` 直接使用 `AgentFallbackMode`。
- `dayu/service/host_assembly.py` 改为从 `dayu.contracts` 导入 `AgentFallbackMode`。
- 测试覆盖：`test_agent_phase3_tool_call.py` 新增 `test_agent_policy_rejects_invalid_values` 中的 `TypeError` 校验；`test_assembly_helpers.py` 和 `test_host_assembly.py` 更新为使用共享枚举。
- 无 divergent string sets 残留。

### 4. Engine Agent tests import boundary (143516-02)

**验证结果：✅ 通过**

- `test_import_boundary.py` 新增 `_iter_engine_agent_test_files` 收集 `tests/engine/` 下排除 `runners/openai` 子树的文件。
- `test_engine_agent_tests_do_not_import_openai_runner_internals` 扫描这些文件，断言不导入 `dayu.engine.runners.openai` 或其子模块。
- `test_agent_phase3_tool_call.py` 删除 `from dayu.engine.runners.openai.non_stream_parser import parse_non_stream_response` 和 `from tests.engine.runners.openai._sse_helpers import make_no_thought_hook`，测试改用构造 `RunnerEvent` 而非解析 OpenAI 协议。

### 5. Fallback trigger reason single owner (144330-21 / 144330-22)

**验证结果：✅ 通过**

- `dayu/engine/agent.py:382-410` 新增 `_FallbackTriggerReason` 结构化触发原因和 `_fallback_trigger` / `_fallback_failure_message` 辅助函数。
- `_fallback_after_tools` (L2242-2293) 接收 `trigger: _FallbackTriggerReason` 而非 raw `error_code`。
- RAISE_ERROR 路径使用 `trigger.error_code` 和 `trigger.message`。
- FORCE_ANSWER 路径将 `trigger` 传递给 `_run_force_answer`。
- `_run_force_answer` (L2295-2390) 在 tool-call-not-enabled 和 force-answer-empty 失败路径中使用 `_fallback_failure_message(trigger=trigger, failure_message=...)` 保留原始 trigger error code。
- 错误消息格式 `"failure_message; trigger=<error_code_value>"` 用于诊断目的，不用于下游解析（下游使用 `error_code` 字段）。

### 6. No scope creep / compatibility shim / weak typing

**验证结果：✅ 通过**

- 无 Batch D2/E 范围文件修改。
- 无兼容性 re-export、wrapper 或 facade。
- 无 `object`、`Any`、无类型参数。
- 所有新增函数和类提供完整中文 docstring。
- 无魔法数字/字符串（schema/contract 字面量除外）。

## Open Questions

无。

## Residual Risk

- D2 范围仍保留：Host terminal/status、tool outcome codec、compaction evidence、memory projection 未在本轮修复。
- `_fallback_failure_message` 使用分号分隔的 trigger error code，格式非结构化；当前仅用于诊断消息，不用于下游解析，风险可接受。若未来需要结构化 trigger 纪录，应考虑在 `RunFailedData` 中增加 `trigger_error_code` 字段。
- `runner_event_type_for_data` 使用线性扫描 `isinstance` 匹配 10 种类型；当前 RunnerEvent 构造频率低，无性能风险。

## Conclusion

Batch D1 实现正确，所有 accepted findings 的 owner corrections 已到位，无违反架构硬约束、编码硬约束或语义所有权规则的情况。建议进入 controller decision 阶段。
