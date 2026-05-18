# Phase 10 Slice 1 Code Re-Review — AgentDS

- Date: 2026-05-18
- Reviewer: AgentDS
- Task: Re-review of Phase 10 Slice 1 review fixes (Codex fix commit)
- Inputs:
  - `docs/reviews/phase10-s1-code-review-mimo-20260518.md`
  - `docs/reviews/phase10-s1-code-review-ds-20260518.md`
  - `docs/reviews/phase10-s1-code-review-fix-codex-20260518.md`

## Verdict: **PASS**

所有总控接受的 findings 均已修复，未引入新的 blocking 或 high defect。

---

## Fixed Findings

| Finding | 原始判定 | 修复验证 |
| --- | --- | --- |
| **DS H1**: `event_log.py` 跨层 import `ContextCompactionTriggerSource` | HIGH | **FIXED** — `event_log.py` 不再 import `dayu.host.context_policy`。新增 `EventPayloadTextEqualsFilter` (line 150-188)，纯 durable-neutral payload 字段过滤。`count_committed_events_by_run_and_type` 签名改为接收 `payload_filter: EventPayloadTextEqualsFilter \| None`。调用方在 test 层显式传入 `field_name`、`expected_value`、`allowed_values`，不把业务枚举下沉到 durable 层。 |
| **MiMo/DS M1**: `_require_positive_int` / `_require_non_negative_int` 重复 | MEDIUM | **FIXED** — `_public_validation.py` 已扩展为 Host 层公共标量校验真源（line 23-52），新增 `require_positive_int`、`require_non_negative_int`、`require_optional_non_empty`。`context_policy.py` (line 15-19) 和 `context_budget.py` (line 17-26) 均从 `_public_validation` import 复用，两处原有重复 helper 已删除。 |
| **MiMo/DS M3**: `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 与实际计算潜在漂移 | MEDIUM | **FIXED** — `context_budget.py:33` 改为 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = 1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`，消除双真源。测试 `test_default_policy_computes_budget_thresholds_and_digest` (line 75-77) 断言两者数学关系 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO == 1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`。digest 仍保留 `default_input_soft_threshold_ratio` 字段，但其值现在由 safety margin 推导。 |
| **DS M2**: EventLog fail-closed 边界未覆盖测试 | MEDIUM | **FIXED** — `test_count_committed_context_compaction_events_fail_closed_for_bad_payload` (line 341-384) parametrize 覆盖三类受损 row：`payload_json` 缺失 `trigger_source`（`{}`）、非法 `trigger_source`（`"manual"`）、空 `trigger_source`（`""`）。每类均先通过 `append_event` 写入合法事件，再在测试 transaction 中通过 `_replace_inline_payload_json` 直接替换 `payload_json`，不放宽生产 append validation。所有 case 均断言 `HostDurableError` 并匹配 `"payload filter field"`。 |
| **L1**: `StaticContextBudgetProvider` 未测试 | LOW | **FIXED** — `test_static_context_budget_provider_returns_configured_policy` (line 81-90) 断言 provider 返回装配时传入的同一 policy；`test_static_context_budget_provider_rejects_invalid_policy` (line 93-99) 断言拒绝非 `ContextBudgetPolicy` 类型输入。 |
| **L2/L3**: `safety_margin_ratio` 边界 | LOW | **FIXED** — `test_minimum_protection_tokens_zero_allows_hard_threshold_at_input_budget` (line 204-225) 覆盖 `safety_margin_ratio=0.0, minimum_protection_tokens=0` 边界，验证 hard threshold 等于 input budget 的允许语义。`test_safety_margin_ratio_near_one_keeps_positive_soft_threshold` (line 228-247) 覆盖 `safety_margin_ratio=0.999` 边界，验证 `_MIN_SOFT_THRESHOLD_TOKENS=1` 保护生效，soft threshold 保持正数。 |
| **L4**: Tool schema overhead 无独立测试 | LOW | **FIXED** — `test_tool_schema_estimation_adds_schema_overhead` (line 250-271) 独立断言空 message + 空 json + 单 tool schema fragment 时 `estimated_input_tokens == DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS + 1`（+1 为 `{}` 的 canonical JSON bytes 估算）。 |

---

## New Findings

无新增 blocking 或 high defect。无新增 medium defect。

### 无新增缺陷的验证要点

1. **`EventPayloadTextEqualsFilter` 设计正确** — `event_log.py:150-188`：仅承载 `field_name`、`expected_value`、`allowed_values` 三个 durable-neutral 字段，`__post_init__` 校验 expected_value 必须在 allowed_values 中（当 allowed_values 非空时）。不承载 context policy、Engine 或任何上层语义。

2. **`count_committed_events_by_run_and_type` 逻辑无回归** — `event_log.py:525-581`：无 filter 时行为不变（直接返回 len(rows)）；有 filter 时逐 row 解析 payload JSON 并校验字段，fail-closed 行为保持一致。

3. **测试隔离正确** — 新 fail-closed 测试通过 `_replace_inline_payload_json` 仅在测试 transaction 中模拟受损 payload，不污染 EventLog append 的生产校验路径。

4. **`_public_validation.py` 未引入业务语义** — 新增的 `require_positive_int`、`require_non_negative_int`、`require_optional_non_empty` 均为层中立标量校验，不承载 Host policy 或 durable 语义。

5. **`DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 推导正确** — `context_budget.py:33` 的赋值与 `context_policy.py:21` 的 `DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO = 0.2` 保持数学一致，测试断言了该关系。

---

## Residual Risks

1. **Conservative estimator 精度**（沿用 Slice 1 设计）：启发式常量 `CHARS_PER_TOKEN=3`、`JSON_BYTES_PER_TOKEN=3`、`MESSAGE_OVERHEAD_TOKENS=12` 为保守上界，真实多轮场景可能过度触发 compaction。后续 tokenizer adapter 接入时必须保持 Host policy 真源边界不变。

2. **`compact_artifact_refs` 未参与估算**：`BudgetEstimateInput.compact_artifact_refs` 字段仅进入 digest，不参与 token 估算。这是 Slice 1 范围内的已知接入点。

3. **`api.py` 中的 `_require_positive_int` / `_require_non_negative_int` 仍独立存在**（`api.py:72-101`）：与 `_public_validation.py` 实现相同但未统一。`api.py` 的这些 helper 是 Slice 1 之前既有的，不在本次 fix scope 内。后续若统一，需确保 `api.py` 模块的 import 拓扑不引入新的反向依赖。

4. **`_require_utc_datetime` 在两处独立定义**（`api.py:205-218`、`context_budget.py:520-533`）：均为模块级私有 helper，调用点仅在本模块内。当前不构成维护风险，但若未来第三个模块需要相同校验，应抽取到 `_public_validation.py`。

5. **`_require_ratio` 接受 `int` 类型**（`context_policy.py:215`）：`isinstance(value, int | float)` 允许 `int` 通过，但 `ContextBudgetPolicy.safety_margin_ratio` 字段类型标注为 `float`。pyright 可在调用侧捕获，运行时防御略宽松。不影响正确性。

---

## 验证摘要

| 检查项 | 状态 |
| --- | --- |
| DS H1 跨层导入已移除 | PASS |
| MiMo/DS M1 校验 helper 重复已消除 | PASS |
| MiMo/DS M3 常量双真源已消除 | PASS |
| DS M2 fail-closed 测试已补齐 | PASS |
| L1 StaticContextBudgetProvider 测试已补 | PASS |
| L2/L3 safety_margin_ratio 边界测试已补 | PASS |
| L4 tool schema overhead 测试已补 | PASS |
| 81 tests passed | PASS |
| pyright 0 errors, 0 warnings | PASS |
| 无新增 blocking/high/medium defect | PASS |
| EventPayloadTextEqualsFilter 设计无语义泄漏 | PASS |
