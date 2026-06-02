# WU-TOOL-02 PR Follow-up RR-TOOL-03 / RR-TOOL-04 Code Review — AgentMiMo

## Review Scope

仅审查本次 follow-up fix：`tests/host/test_toolruntime_accept_barrier.py` 新增测试是否真实关闭 RR-TOOL-03 与 RR-TOOL-04，以及是否违反 AGENTS.md 编码硬约束。

## Findings

### Non-blocking: `ToolAcceptDuplicateGovernance` negative test 只覆盖 `ALLOW` 决策

- **证据**: `test_tool_accept_duplicate_governance_rejects_invalid_fields` (L787–L819) 三次 `pytest.raises` 均使用 `duplicate_decision=DuplicateDecisionKind.ALLOW`。但生产代码 `_validate_tool_accept_duplicate_governance` (L4025–L4037) 对 `REUSE`/`HINT`/`REQUIRE_JUSTIFICATION`/`HARD_STOP`/`DURABLE_MISSING` 额外要求 `duplicate_key is not None`，该分支未被直接测试。
- **影响**: 不阻塞 RR-TOOL-04 关闭。`duplicate_key` 校验属于更细粒度的决策组合覆盖，当前测试已证明 `duplicate_scope`、`duplicate_decision_message` 空值拒绝与 `reuse_prior_event_refs` 类型拒绝均正常工作。`duplicate_key` 校验在现有 `test_event_sequence_monotonic_and_reuse_has_canonical_governance_only` 等集成测试中间接覆盖。
- **建议**: 无需本次修复。若后续需要提升单文件覆盖率，可补一条 `REUSE` 决策 + `duplicate_key=None` 的负例。

### No blocking findings

其余所有新增测试与生产代码 validator 逻辑完全对齐，无阻塞问题。

## RR-TOOL-03 Closure Judgment

**已关闭。**

`test_lost_tool_fact_kind_fails_fast_as_unsupported` (L692–L709) 通过 `dataclasses.replace(base, tool_fact_kind=ToolFactKind.LOST)` 构造 LOST 候选，断言 `ValueError("unsupported tool_fact_kind")`。生产代码 `ToolFactAcceptCandidate.__post_init__` (L614–L615) 的 `else: raise ValueError("unsupported tool_fact_kind")` 分支精确匹配。测试证明 LOST 不会被误当作 accepted result/reuse/governed fact，而是在 candidate 构造期 fail-fast。

## RR-TOOL-04 Closure Judgment

**已关闭。**

新增 7 个子结构直接 validator 负例，覆盖 handoff 要求的全部场景：

| 子结构 | 测试行号 | 覆盖场景 | 生产 validator 对齐 |
|--------|----------|----------|---------------------|
| `ToolAcceptIdentity` | L712–L746 | 4 个空字段拒绝 | `_validate_tool_accept_identity` (L3936) |
| `ToolAcceptCall` | L749–L764 | 非法 digest 拒绝 | `_validate_tool_accept_call` (L3953) |
| `ToolAcceptResult` | L767–L784 | payload digest 不一致拒绝 | `_validate_tool_accept_result` (L3979) |
| `ToolAcceptDuplicateGovernance` | L787–L819 | 缺 scope/message、非法 prior ref | `_validate_tool_accept_duplicate_governance` (L4002) |
| `ToolAcceptGovernance` | L822–L834 | 非 `ToolPolicyDecision` 拒绝 | `_validate_tool_accept_governance` (L4043) |
| `ToolAcceptIdempotency` | L837–L848 | 非法 semantic digest 拒绝 | `_validate_tool_accept_idempotency` (L4063) |
| `ToolAcceptDiagnostics` | L851–L861 | 非 `ToolTraceDiagnosticRef` 拒绝 | `_validate_tool_accept_diagnostics` (L4081) |

所有 `pytest.raises(ValueError, match=...)` 的 pattern 均与生产 validator 抛出的消息精确匹配。类型逃避场景（`ToolAcceptGovernance` 非法 `policy_decision`、`ToolAcceptDuplicateGovernance` 非法 `reuse_prior_event_refs`、`ToolAcceptDiagnostics` 非法 `diagnostic_refs`）均使用 `typing.cast` 而非 `Any`/`object`，符合 AGENTS.md 编码硬约束。

## AGENTS.md Compliance

- **中文 docstring**: 所有新增测试函数均有完整中文 docstring，含 `:returns:` 与 `:raises:`。
- **禁止 `Any`/`object`**: 未使用 `Any` 或 `object`。类型逃避使用 `typing.cast` 到目标类型。
- **禁止跨文件共享 builder**: 未引入跨文件 helper；新增测试复用本文件已有 `_completed_candidate` 等局部 helper。
- **禁止魔法数字/字符串**: 测试数据使用具名常量或语义化字符串。

## README / Doc Sync Judgment

本次只补测试覆盖，不修改 production 接口、CLI、配置、schema、架构边界或用户可见行为。按 README 触发规则，无需更新任何 README 或文档。

## Validation Coverage Judgment

- `pytest tests/host/test_toolruntime_accept_barrier.py`: 24 passed。
- `pyright tests/host/test_toolruntime_accept_barrier.py dayu/host/tool_runtime.py`: 0 errors, 0 warnings, 0 informations。
- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_duplicate_governance.py tests/host/test_toolruntime_diagnostics.py`: 56 passed。

验证充分，无遗漏。

## Final Verdict

**pass**
