# Phase 10 Slice 1 Code Review — AgentMiMo

- Date: 2026-05-18
- Reviewer: AgentMiMo
- Scope: Phase 10 Context Governance / Compaction — Slice 1
- Commit base: 31615df (accepted plan)
- Files reviewed: `dayu/host/context_policy.py`, `dayu/host/context_budget.py`, `dayu/host/api.py`, `dayu/host/durable/event_log.py`, `tests/host/test_context_budget.py`, `tests/host/test_public_contracts.py`, `tests/host/test_engine_ingest_mapping.py`

## Verdict

**PASS**

## Findings

### Medium

#### M1 — DEFAULT_INPUT_SOFT_THRESHOLD_RATIO 未参与计算逻辑，仅用于 digest

- File: `dayu/host/context_budget.py:29`, `dayu/host/context_budget.py:362`
- `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = 0.8` 被定义、导出、写入 estimator digest（line 474），但 `_soft_threshold_tokens` 实际计算使用 `1 - policy.safety_margin_ratio`（line 362）。两者在默认配置下等价（`1 - 0.2 = 0.8`），但如果有人修改 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 而不改 `DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`，digest 会变但计算结果不变，或反之。
- 建议：要么让 `_soft_threshold_tokens` 直接引用 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO`（当 policy 使用默认 ratio 时），要么从 `__all__` 和 digest 中移除该常量以消除歧义。当前状态不是 bug，但增加了维护风险。

#### M2 — validation helpers 重复实现

- File: `dayu/host/context_policy.py:201-246`, `dayu/host/context_budget.py:515-560`
- `_require_positive_int`、`_require_non_negative_int` 在两个模块中各自实现了一遍（逻辑相同）。`context_budget.py` 还额外定义了 `_require_utc_datetime` 和 `_require_tuple_items`。
- 项目编码硬约束要求"数据处理、存储、工具调用职责必须分离，重复逻辑必须抽取"。
- 建议：将通用 int/float/datetime 校验 helper 抽取到 `dayu/host/_public_validation.py` 或同层共享模块。`context_policy.py` 已 import `_public_validation.require_non_empty`，说明该模块是已有的 validation 共享点。

#### M3 — minimum_protection_tokens 允许零值但语义存疑

- File: `dayu/host/context_policy.py:85-88`
- `_require_non_negative_int` 允许 `minimum_protection_tokens = 0`，但 plan 规定默认值为 256 且 hard threshold 为 `input_budget_tokens - minimum_protection_tokens`。零值意味着 hard threshold 等于 input budget，无保护余量。
- 当前无测试覆盖 `minimum_protection_tokens = 0` 的边界。
- 建议：考虑使用 `_require_positive_int` 或至少补充一个测试断言零值行为。

### Low

#### L1 — test_context_budget.py 未覆盖 safety_margin_ratio 边界

- File: `tests/host/test_context_budget.py`
- 无测试覆盖 `safety_margin_ratio = 0.0`（无安全余量）或 `safety_margin_ratio` 接近 1.0 的边界。`_require_ratio` 校验范围为 `[0, 1)`，但无测试验证。
- 建议：补充 parametrize 测试覆盖 ratio 边界。

#### L2 — estimator 只估算 message/json/tool_schema，compact_artifact_refs 未参与估算

- File: `dayu/host/context_budget.py:292-306`
- `estimate_context_budget` 只累加 `message_fragments`、`json_fragments`、`tool_schema_fragments` 的 token 估算，`compact_artifact_refs` 不参与 token 估算。这在 Slice 1 是合理的（compact artifact 尚未接入），但 `BudgetEstimateInput.compact_artifact_refs` 字段存在却未被消费，后续 slice 接入时需确保估算器扩展。
- 不阻塞，作为 residual risk 记录。

#### L3 — EventLog helper import context_policy 跨层耦合

- File: `dayu/host/durable/event_log.py:20`
- `dayu/host/durable/event_log.py` import `dayu.host.context_policy.ContextCompactionTriggerSource`。durable 层依赖 host policy 层的 StrEnum。
- 当前可接受：`ContextCompactionTriggerSource` 是纯 StrEnum，无业务逻辑依赖；且 durable 层需要校验 trigger_source payload。但如果后续 durable 层被复用到非 host 场景，该耦合可能需要重构为 durable 层自己的枚举。
- 不阻塞，记录为架构 residual risk。

### Info

#### I1 — 测试覆盖充分

- 73 tests passed，覆盖有效 policy、无效 policy、soft/hard threshold、显式 hard threshold、usage observation 不动态调整阈值、EventLog per-run trigger count、public contract typed 接收与拒绝。
- `test_engine_ingest_mapping.py` 新增断言确认 `USAGE_REPORTED` payload 未扩展（无 `policy_ref`/`estimator_digest`），`CONTEXT_COMPACTION_REQUESTED` 未写入 canonical fact。

#### I2 — Host budget 真源边界正确

- `ContextBudgetPolicy` 只从 `context_window_size` 和 `reserved_output_tokens` 计算，不读取 Engine spec、metadata、extra payload 或 provider overflow。
- `HostLocalExecutionOptions.context_budget_policy` 使用 `ContextBudgetPolicy | None = None`，Slice 1 仅暴露 composition boundary。
- `__post_init__` 校验拒绝非 `ContextBudgetPolicy` 类型。

#### I3 — EventLog helper fail-closed 行为正确

- `count_committed_events_by_run_and_type` 在 `trigger_source` 非 None 时，对每条匹配 row 的 payload 做 JSON 解析 + StrEnum 校验；payload 损坏或 trigger_source 非法时抛出 `HostDurableError`，不返回错误计数。
- 测试验证了 proactive/reactive 两种 trigger_source 的过滤与计数。

#### I4 — README 决策合理

- Slice 1 未改变用户可执行 workflow、CLI 命令或 production dispatch 行为，不更新 README 符合触发规则。

#### I5 — docstring 和类型签名合规

- 所有新增模块和函数提供完整中文 docstring，包含参数、返回值、异常。
- 无 `Any`、`object` 弱类型签名。
- 无 `getattr`/`hasattr` 滥用。
- 无兼容 wrapper / re-export。
- dataclass 均为 `frozen=True, slots=True`。

## Residual Risks

1. **Conservative estimator 精度**：第一版 char-to-token 估算偏保守，可能触发不必要的 compact。后续 tokenizer adapter 需作为独立能力接入，不能改变本 slice 的 Host policy 真源边界。
2. **compact_artifact_refs 未参与估算**：Slice 1 的 `BudgetEstimateInput.compact_artifact_refs` 字段存在但未被估算器消费。Slice 2+ 接入 compact artifact 后需扩展估算逻辑。
3. **validation helper 重复**：`context_policy.py` 和 `context_budget.py` 的 `_require_positive_int`/`_require_non_negative_int` 重复。后续 slice 应抽取到共享模块，避免两处修改不一致。
4. **durable 层对 policy 层的依赖**：`event_log.py` import `ContextCompactionTriggerSource`。当前可接受，但若 durable 层被复用到非 host 场景需重构。
