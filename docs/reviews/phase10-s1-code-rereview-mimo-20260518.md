# Phase 10 Slice 1 Code Re-Review — AgentMiMo

- Date: 2026-05-18
- Reviewer: AgentMiMo
- Scope: Phase 10 Context Governance / Compaction — Slice 1 post-fix re-review
- Inputs:
  - `docs/reviews/phase10-s1-code-review-mimo-20260518.md`
  - `docs/reviews/phase10-s1-code-review-ds-20260518.md`
  - `docs/reviews/phase10-s1-code-review-fix-codex-20260518.md`
  - 当前工作树 diff（Slice 1 相关文件）

## Verdict

**PASS**

---

## Fixed Findings Table

| Finding | 来源 | 修复方式 | 验证结果 |
| --- | --- | --- | --- |
| DS H1：`event_log.py` 跨层导入 `ContextCompactionTriggerSource` | DS HIGH | 移除 `dayu.host.context_policy` 导入；新增 `EventPayloadTextEqualsFilter`（durable-neutral payload 文本字段过滤），`count_committed_events_by_run_and_type` 接收 `payload_filter: EventPayloadTextEqualsFilter | None`；trigger_source 语义由调用方通过 `field_name`、`expected_value`、`allowed_values` 显式传入。 | PASS — `event_log.py` 仅导入 `dayu.host.durable._validation`、`dayu.host.durable.artifact`、`dayu.host.durable.codec`、`dayu.host.durable.errors`、`dayu.host.durable.payload`、`dayu.host.durable.schema`、`dayu.host.durable.transaction` 与标准库，无向上依赖。 |
| MiMo/DS M1：`_require_positive_int` / `_require_non_negative_int` 跨模块重复 | MiMo MEDIUM / DS MEDIUM | 扩展 `dayu.host._public_validation` 为 Host 层公共标量校验真源（新增 `require_positive_int`、`require_non_negative_int`、`require_optional_non_empty`）；`context_policy.py` 与 `context_budget.py` 均改为从 `_public_validation` 导入，删除两处重复 helper。 | PASS — 两个模块不再定义 `_require_positive_int` / `_require_non_negative_int`，均从 `_public_validation` 导入。 |
| DS M3：`DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 与 `DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO` 潜在漂移 | DS MEDIUM | 改为 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = 1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO` 推导，消除双真源。 | PASS — `context_budget.py:33` 现为 `1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`；测试断言 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO == 1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`（`test_context_budget.py:75-77`）。 |
| DS M2：`count_committed_events_by_run_and_type` fail-closed 边界未覆盖测试 | DS MEDIUM | 补三类受损 payload 测试：`{}`（missing trigger_source）、`{"trigger_source":"manual"}`（非法 enum）、`{"trigger_source":""}`（空字符串）。测试通过 `_append_compaction_requested` 写入合法事件后 `_replace_inline_payload_json` 在测试 transaction 中替换 payload，不放宽生产 append validation。 | PASS — `test_context_budget.py:341-384` 覆盖三类 parametrize case，均断言 `HostDurableError` with `match="payload filter field"`。 |
| L1：`StaticContextBudgetProvider` 未测试 | DS LOW | 补 `test_static_context_budget_provider_returns_configured_policy`（返回同一 policy）与 `test_static_context_budget_provider_rejects_invalid_policy`（拒绝非 ContextBudgetPolicy 输入）。 | PASS — `test_context_budget.py:81-99`。 |
| L2/L3：`safety_margin_ratio` 边界与 `minimum_protection_tokens=0` 未测试 | DS LOW / MiMo LOW | 补 `test_minimum_protection_tokens_zero_allows_hard_threshold_at_input_budget`（`safety_margin_ratio=0.0, minimum_protection_tokens=0`，断言 soft=hard=input_budget, safety_margin=0）与 `test_safety_margin_ratio_near_one_keeps_positive_soft_threshold`（`safety_margin_ratio=0.999`，断言 soft_threshold=1 即 `_MIN_SOFT_THRESHOLD_TOKENS` 保底）。 | PASS — `test_context_budget.py:204-248`。 |
| L4：tool schema overhead 无独立测试 | DS LOW | 补 `test_tool_schema_estimation_adds_schema_overhead`，断言单个空 JSON tool schema fragment 估算结果等于 `DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS + 1`。 | PASS — `test_context_budget.py:250-271`。 |

---

## New Findings

无 blocking 或 high findings。

无 medium findings。

### Low

#### NL1 — `_require_ratio` 仍为 `context_policy.py` 模块级私有 helper

`context_policy.py:205-218` 的 `_require_ratio` 校验 `[0, 1)` 范围，未被抽取到 `_public_validation`。当前仅 `ContextBudgetPolicy.__post_init__` 一处调用，不构成重复，但若后续 slice 在 `context_budget.py` 或其它模块也需要 ratio 校验，需回抽。

**风险等级:** Low。单调用点，不阻塞。

---

## Residual Risks

1. **Conservative estimator 精度**：Slice 1 的 char-to-token 估算常量（`CHARS_PER_TOKEN=3`、`JSON_BYTES_PER_TOKEN=3`、`MESSAGE_OVERHEAD_TOKENS=12`）偏保守，可能在真实多轮场景中触发不必要的 compact。后续 tokenizer adapter 需作为独立能力接入，不改变 Host policy 真源边界。
2. **`compact_artifact_refs` 未参与估算**：`BudgetEstimateInput.compact_artifact_refs` 字段存在但未被估算器消费，是 Slice 1 已知后续接入点。
3. **EventLog payload filter 只验证 JSON 文本字段和可选 allowed values**：不承载 context policy 语义；上层必须继续显式传入字段名和 allowed values，避免把业务枚举重新下沉到 durable 层。

---

## Verification Summary

| 检查项 | 状态 |
| --- | --- |
| DS H1 跨层导入已消除 | PASS |
| MiMo/DS M1 重复校验 helper 已抽取 | PASS |
| DS M3 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 已推导消除漂移 | PASS |
| DS M2 fail-closed 测试已补齐 | PASS |
| L1-L4 低成本测试已补齐 | PASS |
| 修复未引入新的 blocking/high defect | PASS |
| 81 tests passed | PASS |
| pyright 0 errors | PASS |
| README 已同步更新 | PASS |
