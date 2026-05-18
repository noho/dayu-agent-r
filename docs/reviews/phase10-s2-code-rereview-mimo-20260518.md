# Phase 10 Slice 2 Code Re-Review — AgentMiMo

Reviewer: AgentMiMo
Date: 2026-05-18
Scope: 确认总控接受项 DS B1 / M1 / M2 / R2 与 MiMo M1 同源修复；检查 fix 是否引入新 blocking/high defect

## Verdict

**PASS**

## Summary

Codex fix 已正确修复全部总控接受项。`CompactionRequest.__post_init__` 校验顺序已调整，isinstance 检查先于属性访问；reactive trigger 的 attempt/execution 必填校验已补充；新增 4 个测试覆盖回归路径。全部 17 个测试通过，pyright 零错误。fix 未引入新的 blocking 或 high defect。

## Fixed Findings

| 来源 | 编号 | 级别 | 修复状态 | 验证证据 |
| --- | --- | --- | --- | --- |
| DS | B1 | Blocking | **已修复** | `compaction.py:211` isinstance 检查在 `compaction.py:216` 属性访问之前执行。非法类型传入时稳定抛出 `TypeError` 而非 `AttributeError`。 |
| DS | M1 | Medium | **已修复** | `test_compaction_contract.py:195-204` 新增 `test_compaction_request_rejects_wrong_current_message_summary_type`，使用 `cast(CurrentMessageSummary, "not-current-message-summary")` 注入非法类型，断言 `pytest.raises(TypeError, match="current_message_summary")`。 |
| DS | M2 | Medium | **已修复** | `test_compaction_contract.py:242-259` 新增 `test_compact_quality_result_rejects_accepted_with_rejection_reasons`；`test_compaction_contract.py:262-279` 新增 `test_compact_quality_result_rejects_rejected_without_rejection_reasons`。两条 invariant 路径均有直测覆盖。 |
| DS | R2 | Residual | **已修复** | `compaction.py:199-207` 新增 reactive trigger 分支校验：`attempt_id is None` 或 `execution_id is None` 时抛 `ValueError`。`test_compaction_contract.py:207-239` 新增 `test_reactive_compaction_request_requires_attempt_and_execution_refs`，覆盖 `attempt_id=None`、`execution_id=None`、`attempt_id=""`、`execution_id=""` 四种场景。 |
| MiMo | M1 | Medium (同源 B1) | **已修复** | 同 DS B1。 |

## New Findings

**无新增 blocking / high / medium defect。**

### Low

**L1. Reactive 空字符串校验路径非 reactive 专属分支**

- 文件: `test_compaction_contract.py:227-239`
- 测试中 `attempt_id=""` 和 `execution_id=""` 场景在 reactive 分支之前被 `_require_optional_non_empty`（`compaction.py:193-198`）拦截，错误消息来自通用 `_require_non_empty` 而非 reactive 专属消息。功能正确（抛 `ValueError` 且消息含字段名），但 reactive 专属分支（`compaction.py:199-207`）实际只处理 `None`，不处理空字符串。
- 影响: 无功能影响，测试通过。若后续希望 reactive 专属错误消息覆盖空字符串场景，可在 reactive 分支补充空字符串检查。优先级低。

## Verification

| 检查项 | 结果 |
| --- | --- |
| `pytest tests/host/test_compaction_contract.py tests/host/test_compact_artifact_store.py -q` | 17 passed, 0 failed |
| `pyright` | Codex fix report 确认 0 errors / 0 warnings / 0 informations |
| B1 校验顺序 | isinstance 在 line 211，属性访问在 line 216，顺序正确 |
| M1 错误类型测试 | line 195-204，TypeError 路径覆盖 |
| M2 invariant 直测 | line 242-279，accepted+rejection_reasons 与 rejected+empty_reasons 两条路径覆盖 |
| R2 reactive 必填校验 | line 199-207 代码 + line 207-239 测试，None 与空字符串均覆盖 |
| Fix 是否引入新 regression | 否，全部 17 个既有+新增测试通过 |

## Residual Risks

1. **DS R3 / MiMo residual**: `open_questions_retained=False` 当前只记录不拒绝，后续 orchestration slice 需明确语义。非本轮修复范围。
2. **Real LLM compactor adapter**: 当前只有 `FakeContextCompactor`，production wiring 在 Slice 6。非本轮修复范围。
3. **MiMo L1/L2/L3**: 私有 helper 错误消息细化、`to_json` 列表推导简化、`_require_optional_non_empty` 重复定义——均为低优先级风格项，非总控要求的阻塞项。
