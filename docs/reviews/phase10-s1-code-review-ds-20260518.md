# Phase 10 Slice 1 Code Review — AgentDS

- Date: 2026-05-18
- Reviewer: AgentDS
- Accepted plan: `docs/host/phase10-context-governance-plan.md` Slice 1
- Reviewed implementation artifact: `docs/reviews/phase10-s1-context-budget-implementation-20260518.md`
- Scope: `dayu/host/context_policy.py`, `dayu/host/context_budget.py`, `dayu/host/api.py`, `dayu/host/durable/event_log.py`, `tests/host/test_context_budget.py`, `tests/host/test_public_contracts.py`, `tests/host/test_engine_ingest_mapping.py`

## Verdict: PASS

Slice 1 实现与 accepted plan 对齐良好，无 blocking findings。预算真源完全来自 typed `ContextBudgetPolicy`，未从 Engine、metadata、extra payload 或 provider overflow 回填。`UsageObservation` 未改变 `USAGE_REPORTED` EventLog payload 且不参与阈值动态调整。`count_committed_events_by_run_and_type` 在同一 transaction 内 fail-closed 统计 per-run compact facts。所有函数与类均有中文 docstring，无 `Any`/`object` 弱类型签名，无 `getattr`/`hasattr`/lazy import 或兼容 wrapper。

---

## Findings

### HIGH

#### H1 — `dayu/host/durable/event_log.py:21` 跨层导入 context_policy 类型

`dayu/host/durable/event_log.py` 第 21 行导入 `ContextCompactionTriggerSource` from `dayu.host.context_policy`。按架构分层，`durable/` 是 Host 下层基础设施，`context_policy.py` 是 Host 上层 typed contract 模块。此导入形成 `durable → host-policy` 的向上依赖，违反"禁止反向依赖"约束。

**证据:**

```python
# dayu/host/durable/event_log.py:21
from dayu.host.context_policy import ContextCompactionTriggerSource
```

`ContextCompactionTriggerSource` 使用点在 `count_committed_events_by_run_and_type` 的签名和 payload 解析逻辑中（第 492、511-512、537 行）。

**缓解因素:** accepted plan 明确将 `trigger_source: ContextCompactionTriggerSource | None` 放在该 helper 签名中，并推荐放在 `dayu/host/durable/event_log.py`。`ContextCompactionTriggerSource` 是纯 `StrEnum`，无业务逻辑或 durable 行为依赖。此导入是计划驱动的权衡，不是实现偏差。

**建议:** 后续 slice 可考虑将 `ContextCompactionTriggerSource` 提取到 `dayu/host/durable/_compact_types.py` 或共享 contract 位置，消除向上依赖。当前不阻塞 Slice 1。

---

### MEDIUM

#### M1 — 校验辅助函数跨模块重复

`_require_positive_int` 与 `_require_non_negative_int` 在 `context_policy.py`（第 201-230 行）和 `context_budget.py`（第 515-544 行）有完全相同的实现。

**证据:**

```python
# context_policy.py:201-214
def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")

# context_budget.py:515-528 — 逐字相同
def _require_positive_int(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
```

`_require_non_negative_int` 同理。CLAUDE.md 要求"重复逻辑必须抽取"。当前两处均为模块级私有 helper，调用点少，但后续 slice 若继续扩展校验逻辑，重复会扩散。

**建议:** 后续 slice 可统一到 `dayu/host/_public_validation` 或新建 shared validation helper 模块。当前不阻塞。

#### M2 — `count_committed_events_by_run_and_type` fail-closed 边界未覆盖测试

`event_log.py:487-544` 定义的 fail-closed 行为（payload 损坏、`trigger_source` 缺失、`trigger_source` 非法字符串）在测试中未覆盖。

**证据:** `tests/host/test_context_budget.py:202-230` 的 `test_count_committed_context_compaction_events_by_trigger_source` 只测试正常路径（两条事件，一条 PROACTIVE → 返回 1）。以下场景未覆盖：

- payload JSON 损坏（`HostDurableError` 期望）
- payload 中 `trigger_source` 键缺失（`HostDurableError` 期望）
- payload 中 `trigger_source` 值不是合法 enum（`HostDurableError` 期望）
- payload 中 `trigger_source` 值为空字符串（`HostDurableError` 期望）

**建议:** Slice 4（proactive pre-dispatch orchestration）接入时补充 fail-closed 测试。当前不阻塞 Slice 1。

#### M3 — `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 常量未参与实际计算

`context_budget.py:29` 定义 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = 0.8`，但软阈值实际计算使用 `1 - policy.safety_margin_ratio`（`_soft_threshold_tokens` 第 361 行）。该常量仅出现在 `_estimator_digest` 的 constants 段（第 473 行）。

**证据:**

```python
# context_budget.py:29 — 定义但未用于计算
DEFAULT_INPUT_SOFT_THRESHOLD_RATIO = 0.8

# context_budget.py:361 — 实际计算不使用该常量
ratio = 1 - policy.safety_margin_ratio
return floor(input_budget_tokens * ratio)
```

如果 `DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO` 被修改而未同步更新 `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO`，两者将不一致，但估算结果仍正确（由 safety margin 驱动）。digest 中记录的 `default_input_soft_threshold_ratio` 会误导为 0.8。这不是正确性 bug——软阈值计算逻辑正确——但 digest 的可复现性有轻微损伤。

**建议:** 后续 slice 可改为从 `1 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO` 推导或直接删除该常量。当前不阻塞。

---

### LOW

#### L1 — `StaticContextBudgetProvider` 未测试

`context_policy.py:133-158` 定义的 `StaticContextBudgetProvider` 无对应测试。其 `__post_init__` 类型校验和 `context_budget_policy()` 方法未被覆盖。

#### L2 — `_require_ratio` 接受 `int` 值

`context_policy.py:242` 的 `_require_ratio` 接受 `int | float`（过滤 bool 后）。`ContextBudgetPolicy.safety_margin_ratio` 字段类型标注为 `float`，但运行时传入 `0`（int）不会触发校验失败。pyright 应能捕获该类型错误，但运行时防御略宽松。

**证据:**

```python
# context_policy.py:242
if isinstance(value, bool) or not isinstance(value, int | float):
    raise TypeError(f"{field_name} must be float")
```

#### L3 — 极端 `safety_margin_ratio` 导致 `soft_threshold_tokens=0` 未测试

`safety_margin_ratio` 接近 1.0 且 `input_budget_tokens` 较小时，`soft_threshold_tokens` 可能为 0，触发 `BudgetEstimate.__post_init__` 的 `ValueError`。该 fail-closed 路径未被测试覆盖。例如 `context_window_size=260, reserved_output_tokens=4, safety_margin_ratio=0.999` → `input_budget=256, soft=floor(256*0.001)=0`。

#### L4 — Tool schema 估算路径无独立测试

`_estimate_json_tokens` 与 `DEFAULT_ESTIMATOR_TOOL_SCHEMA_OVERHEAD_TOKENS` 的组合估算仅在 JSON fragment 路径间接覆盖（`test_explicit_hard_threshold_overrides_minimum_protection` 测试了 `json_fragments`）。tool schema 路径（带额外 +16 tokens overhead）无独立断言。

#### L5 — Estimator digest 中的 policy `hard_threshold_tokens` 可能为 None

`_estimator_digest` 的 policy 段记录 `policy.hard_threshold_tokens` 原始值（可能为 `None`），而 estimate 段记录计算后的有效值。digest 可复现性依赖调用方理解 `None` 语义。

---

### INFO

#### I1 — `UsageObservation` 在 Slice 1 无消费者

`context_budget.py:213-273` 定义的 `UsageObservation` 类型完整且校验充分，但在 Slice 1 无代码路径消费它。这是按计划的正向设计——为后续 slice 提供 typed observation 类型。

#### I2 — `ContextBudgetProvider` protocol 未在 Slice 1 使用

`context_policy.py:120-130` 定义的 `ContextBudgetProvider` Protocol 未被任何 Slice 1 代码消费。`HostLocalExecutionOptions.context_budget_policy` 直接使用 `ContextBudgetPolicy | None` 值而非 provider。按计划"prefer passing the typed ContextBudgetPolicy value"，这是正确选择。

#### I3 — README 未更新

实现 review artifact 解释了理由：Slice 1 未改变用户可执行 workflow、CLI 命令或 production dispatch 行为。`HostLocalExecutionOptions.context_budget_policy` 当前仅为可选 typed composition boundary。同意该决策。

#### I4 — `DEFAULT_INPUT_SOFT_THRESHOLD_RATIO` 实为 `1 - DEFAULT_CONTEXT_SAFETY_MARGIN_RATIO`

这两个模块常量存在数学约束关系（和为 1），但代码中无显式关联。若未来独立修改其中一个，可能产生语义不一致。

---

## Residual Risks

1. **跨层导入固化风险:** 若后续 slice 扩展 `ContextCompactionTriggerSource` 增加 durable 相关行为，`event_log.py` 的向上依赖会更显著。建议在 Slice 2 或 4 前解决。
2. **Conservative estimator 精度:** 常量 `CHARS_PER_TOKEN=3`、`JSON_BYTES_PER_TOKEN=3`、`MESSAGE_OVERHEAD_TOKENS=12` 是保守上界。在真实多轮场景中可能过度触发 compaction。后续 tokenizer adapter 应在不改变 policy truth source 的前提下替换估算器。
3. **Fail-closed 测试债务:** `count_committed_events_by_run_and_type` 的 fail-closed 边界测试（M2）若延迟到 Slice 4 才补，可能在 proactive/reactive orchestration 开发时引入回归风险。
4. **`safety_margin_tokens` 语义与 hard threshold 关系:** 当前实现中 `safety_margin_tokens = input_budget - soft_threshold`，是 soft threshold 上方的安全空间。部分调用方可能误解为 hard threshold 上方的保护空间。文档已清晰，但未来消费者需注意该语义。
5. **Orphan artifact 文件 (non-P10 scope):** 计划中已声明 Phase 11 负责 startup recovery scan。Slice 1 无此风险。

---

## 验证摘要

| 检查项 | 状态 |
|--------|------|
| Host budget 真源仅来自 typed policy | PASS |
| 不从 Engine / metadata / extra payload / provider overflow 读取预算 | PASS |
| Usage observation 不改变 EventLog payload / threshold | PASS |
| EventLog helper 在同一 transaction fail-closed 统计 | PASS |
| 默认阈值和 estimator 常量有测试覆盖 | PASS (有 L3/L4 小缺口) |
| 无边界错误 | PASS |
| 中文 docstring | PASS |
| 无 Any/object 弱类型签名 | PASS |
| 无 getattr/hasattr/lazy import | PASS |
| 无兼容 wrapper | PASS |
| README 决策合理 | PASS |
