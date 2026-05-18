# Phase 10 Slice 1 Code Review Fix — AgentCodex

- Date: 2026-05-18
- Scope: Phase 10 Context Governance / Compaction Slice 1 review fixes
- Inputs:
  - `docs/reviews/phase10-s1-code-review-mimo-20260518.md`
  - `docs/reviews/phase10-s1-code-review-ds-20260518.md`

## Finding 处理表

| Finding | 裁决 | 处理结果 |
| --- | --- | --- |
| DS H1：`event_log.py` 不得 import `ContextCompactionTriggerSource` | 必须修复 | 已移除 durable 层对 `dayu.host.context_policy` 的导入。新增 `EventPayloadTextEqualsFilter`，`count_committed_events_by_run_and_type` 只接收 durable-neutral payload 文本过滤条件；trigger_source 语义由调用方通过字段名、期望值和 allowed values 显式传入。 |
| MiMo/DS M1：`_require_positive_int` / `_require_non_negative_int` 重复 | 必须修复 | 已扩展 `dayu.host._public_validation` 为 Host 层公共标量校验真源，`context_policy.py` 与 `context_budget.py` 均复用该实现，删除两处重复 helper。 |
| DS/MiMo M3：`DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 与实际计算潜在漂移 | 应修复 | 已改为 `1.0 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO` 推导，保留 digest 字段但消除双真源；测试断言默认 soft ratio 与 safety margin 的数学关系。 |
| DS M2：补 EventLog fail-closed 测试 | 应修复 | 已补 `payload_json` 缺失 `trigger_source`、非法 `trigger_source`、空 `trigger_source` 三类受损 row 测试。测试先经 `append_event` 写入合法事件，再仅在测试 transaction 中直接替换 `payload_json`，不放宽生产 append validation。 |
| L1：`StaticContextBudgetProvider` 未测试 | 低成本补齐 | 已补 provider 返回同一 policy 与拒绝非法 policy 的 focused assertions。 |
| L2/L3：`safety_margin_ratio` 边界 | 低成本补齐 | 已补 `minimum_protection_tokens=0` + `safety_margin_ratio=0.0` 允许 hard threshold 等于 input budget 的边界说明测试；同时修复并测试 `safety_margin_ratio` 接近 1 时 soft threshold 保持正数。 |
| L4：tool schema overhead 无独立测试 | 低成本补齐 | 已补 tool schema fragment 估算包含 `DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS` 的 focused assertion。 |

## 验证结果

| 命令 | 结果 |
| --- | --- |
| `source .venv/bin/activate && pytest tests/host/test_context_budget.py tests/host/test_public_contracts.py tests/host/test_engine_ingest_mapping.py -q` | PASS，81 passed in 0.41s |
| `source .venv/bin/activate && pyright` | PASS，0 errors, 0 warnings, 0 informations |
| `git diff --check` | PASS |

## README 同步

已按触发规则检查 `dayu/host/README.md`。本次 Host 开发手册只同步当前已实现事实：`HostLocalExecutionOptions` 的 context budget policy typed 边界、EventLog committed fact payload filter 统计能力，以及对应测试覆盖范围。

## 剩余风险

1. Conservative estimator 仍使用 Slice 1 的启发式 token 估算常量，后续 tokenizer adapter 接入时需要保持 Host policy 真源边界不变。
2. `compact_artifact_refs` 当前仍只进入 estimator digest，不参与 token 估算；这是 Slice 1 范围内的已知后续接入点。
3. EventLog payload filter 只验证 JSON 文本字段和可选 allowed values，不承载 context policy 语义；上层必须继续显式传入字段名和 allowed values，避免把业务枚举重新下沉到 durable 层。
