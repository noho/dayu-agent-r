# WU-TOOL-01 Slice 3 Code Review — DeepReview Artifact

- **Review gate**: code review (deep review)
- **Branch**: `fix/wu-tool-01-attempt-scoped-duplicate-governance`
- **Approved plan**: `docs/host/wu-tool-01-attempt-scoped-duplicate-governance-plan.md`
- **Review scope**: 当前未提交 Slice 3 改动
- **Reviewer**: DeepReview specialist; 只审查，不改文件
- **Date**: 2026-06-01

---

## Findings

### Finding 1 — BLOCKING: `_diagnostic_refs_for_duplicate` 使用 `decision.message` 而非 `decision.diagnostic_message`，违反 approved plan 7.11

- **严重度**: Blocking（违反 approved plan 明确的 must 约束）
- **文件**: `dayu/host/tool_runtime.py:2545-2550`
- **证据**:

当前代码（Slice 3 diff 引入的变更）：

```python
# dayu/host/tool_runtime.py:2545-2550
if duplicate_decision.message is None:
    raise ValueError("duplicate decision requires message")
ref = self._diagnostic_emitter.emit(
    ToolTraceDiagnosticRecord(
        reason_code=_duplicate_reason_code(duplicate_decision.kind),
        message=duplicate_decision.message,
    )
)
```

Slice 2 状态（正确实现）：

```python
if duplicate_decision.diagnostic_message is None:
    raise ValueError("duplicate decision requires diagnostic_message")
ref = self._diagnostic_emitter.emit(
    ToolTraceDiagnosticRecord(
        reason_code=_duplicate_reason_code(duplicate_decision.kind),
        message=duplicate_decision.diagnostic_message,
    )
)
```

- **根因分析**:

`DuplicateDecision` 有两个语义不同的 message 字段（`dayu/host/tool_duplicate_governance.py:254-277`）：

| 字段 | 语义 | 默认值（HARD_STOP 场景） |
|---|---|---|
| `message` | 具体治理动作提示，供 policy decision / governed failure outcome 使用 | `"duplicate tool call hard-stopped by Host governance"` |
| `diagnostic_message` | attempt-scope 诊断说明，供 diagnostic record 使用 | `"duplicate tool call governed by attempt-local ToolRuntime index"` |

`_decision_for_accepted_entry`（`tool_duplicate_governance.py:489-498`）正确地将两者分别填充：

```python
return DuplicateDecision(
    ...
    message=self._policy.messages.message_for(decision),       # 治理动作消息
    diagnostic_message=self._policy.messages.attempt_scope_diagnostic,  # attempt-scope 诊断
)
```

但 `_diagnostic_refs_for_duplicate` 绕过 `diagnostic_message`，取用 `message`，使诊断记录丢失 attempt-scope 语境，退化为复述治理动作消息。

- **Approved plan 约束**:

Plan 7.11 原文：

> Diagnostic emitter message for duplicate must use `policy.messages.attempt_scope_diagnostic` and include a structured metadata path if `ToolTraceDiagnosticRecord` already supports only reason/message; if it does not support metadata, the EventLog `TOOL_CALL_GOVERNED` payload is the canonical machine-readable scope and diagnostic message must be human-readable attempt-scoped text from typed messages.

Stop condition（Slice 3）：

> Stop if existing `ToolTraceDiagnosticRecord` lacks structured metadata and adding metadata would expand tool trace contract broadly. In that case, keep diagnostic message typed/configured and rely on `TOOL_CALL_GOVERNED.payload.duplicate_scope` as the machine-readable source.

`ToolTraceDiagnosticRecord` 确实只有 `reason_code` / `message` 无 metadata，但 plan 明确要求此时 diagnostic message 必须使用 `attempt_scope_diagnostic`，而非回退到 `decision.message`。

- **设计依据评估**:

Implementation artifact 的理由是："保证配置化 duplicate message 同时出现在 policy decision、governed failure outcome 与 diagnostic record"。但这恰好是 plan 明确禁止的同质化——plan 要求 diagnostic 承载 attempt-scope 语境，与 policy action message 分离。`DuplicateDecision` 已为此设计了独立字段，基础设施已就绪，绕过它没有设计依据。

- **影响**:
  1. 诊断记录无法区分"这次 duplicate 是 attempt-scoped 决策"——这恰恰是 WU-TOOL-01 的核心目的。
  2. 用户配置 `attempt_scope_diagnostic` 自定义值后，该值被完全忽略，只出现在 `_duplicate_decision_json` 的 `diagnostic_message` JSON 字段中，从未被 `_diagnostic_refs_for_duplicate` 消费。
  3. 当 `decision.message` 和 `decision.diagnostic_message` 有不同配置值时，diagnostic record 错误地报告了治理动作消息。

- **修复方向**: 将 `_diagnostic_refs_for_duplicate` 改回使用 `duplicate_decision.diagnostic_message`（即恢复 Slice 2 的正确行为），同时修复关联测试断言。

---

### Finding 2 — BLOCKING: 测试 `test_candidate_and_ack_carry_duplicate_diagnostic_refs` 断言 diagnostic message 为 hard_stop message，与 plan 7.11 冲突

- **严重度**: Blocking（由 Finding 1 派生，测试与 plan 要求不一致）
- **文件**: `tests/host/test_toolruntime_diagnostics.py:188-219`
- **证据**:

```python
# line 188
configured_message = "配置化 hard stop duplicate message"
# line 197-198
messages=DuplicateGovernanceMessages(hard_stop=configured_message),
# line 219
assert diagnostics.records[0].message == configured_message
```

- **分析**:

`configured_message` 是 hard_stop 治理动作消息。按 plan 7.11，diagnostic record 的 message 应该使用 `attempt_scope_diagnostic`。当前测试断言 diagnostic record message 等于配置的 hard_stop 消息，验证的是错误行为。

正确断言应为：
- `diagnostics.records[0].message` 等于 `DuplicateGovernanceMessages().attempt_scope_diagnostic`（默认值）或显式配置的 `attempt_scope_diagnostic` 值。
- policy decision message、governed failure outcome message 继续使用配置的 hard_stop 消息（这部分当前测试已覆盖，正确）。

---

### Finding 3 — NON-BLOCKING: `_diagnostic_refs_for_duplicate` 的 null guard 与使用字段不一致

- **严重度**: Non-blocking（实现正确性无影响，但逻辑不自洽）
- **文件**: `dayu/host/tool_runtime.py:2545-2546`
- **证据**:

```python
if duplicate_decision.message is None:
    raise ValueError("duplicate decision requires message")
```

- **分析**:

对于非 ALLOW decision，`message` 总是由 `message_for()` 或 `prior_accept_missing` 填充，不可能为 `None`，所以当前 guard 不会误触发。但如果按 Finding 1 修复回 `diagnostic_message`，guard 应同步改为检查 `diagnostic_message`，保持自洽。此外，`diagnostic_message` 在 `_decision_for_accepted_entry` 中总是填充为 `attempt_scope_diagnostic`，也不为 `None`，语义正确。

---

### Finding 4 — NON-BLOCKING: `_duplicate_decision_json` 包含 `diagnostic_message` 字段，但该值在当前 flow 中仅出现在 JSON payload，不被任何 diagnostic path 消费

- **严重度**: Non-blocking（信息未丢失，仅冗余保留）
- **文件**: `dayu/host/tool_runtime.py:5136`
- **分析**: `_duplicate_decision_json` 在 `diagnostic_message` 字段写入了 `decision.diagnostic_message`。这是正确的 JSON 序列化——即使 `_diagnostic_refs_for_duplicate` 没有用它，JSON payload 仍是完整机器可读真源。不构成 bug，但它佐证了 Finding 1：基础设施已完整支持两个独立消息字段，仅 diagnostic path 的消费侧未正确使用。

---

## Verification Per Plan Checklist

### Q1: TOOL_CALL_GOVERNED payload 是否保留 duplicate_scope

**结论: 正确，已覆盖。**

- `_tool_call_governed_event_request`（`tool_runtime.py:3116-3118`）正确写入：
  ```python
  "duplicate_scope": _duplicate_scope_json(candidate.duplicate_scope),
  ```
- `_duplicate_scope_json`（`tool_runtime.py:3695-3704`）输出 `{"kind": "attempt", "attempt_id": "..."}`。
- 测试覆盖：
  - `test_event_sequence_monotonic_and_reuse_has_canonical_governance_only`（`test_toolruntime_accept_barrier.py:504-508`）断言 `duplicate_scope.kind == "attempt"` 且 `attempt_id` 等于 candidate attempt。
  - `test_duplicate_governed_matrix_produces_diagnostics`（`test_toolruntime_duplicate_governance.py:533-535`）断言 `candidate.duplicate_scope.kind == "attempt"` 且 `attempt_id == _ATTEMPT_ID`。

### Q2: tool_trace.py 是否正确透传 duplicate_scope

**结论: 正确，cold/hot trace 一致，无类型收窄问题。**

- `_FIELD_DUPLICATE_SCOPE` 常量定义（`tool_trace.py:78`）。
- `_trace_summary` 签名新增 `duplicate_scope: JsonValue | None` 参数并写入 summary dict（`tool_trace.py:774`）。
- `_extract_canonical_trace` 从 `TOOL_CALL_GOVERNED` payload 提取 `duplicate_scope`（`tool_trace.py:482`）：
  ```python
  duplicate_scope=_json_value_or_none(payload, _FIELD_DUPLICATE_SCOPE),
  ```
- `_extract_diagnostic_trace` 与 `_extract_usage_trace` 传 `duplicate_scope=None`，语义正确。
- Cold line 构造（`_build_cold_line:711`）写入 `_FIELD_TRACE_SUMMARY: extracted.trace_summary`，hot row（`_build_hot_row:652`）同样写入 `trace_summary=extracted.trace_summary`，cold/hot 一致。
- 类型安全：`_json_value_or_none` 返回 `JsonValue`，`_trace_summary` 参数类型为 `JsonValue | None`，无 Mapping 收窄问题。
- 测试覆盖：`test_tool_call_chain_projects_hot_rows_and_cold_lines`（`test_tool_trace_projection.py:352-355`、`389-394`）分别断言 hot row 和 cold line 中的 `trace_summary["duplicate_scope"]`。

### Q3 (关键重点): approved plan 7.11 要求 diagnostic 使用 attempt_scope_diagnostic，diff 改为使用 decision.message

**结论: Blocking plan 偏离。详见 Finding 1。**

诊断 emitter message 从 `diagnostic_message`（`= attempt_scope_diagnostic`）改为 `message`（`= hard_stop / hint / etc.` 治理动作消息）没有充分设计依据，且直接违反 approved plan 7.11 的 must 约束。`decision.message` 是具体治理动作提示（如 "hard-stopped by Host governance"），`diagnostic_message` 是 attempt-scope 诊断说明（如 "governed by attempt-local ToolRuntime index"）。两者语义不同，plan 要求 diagnostic path 使用后者。

### Q4: 配置化 duplicate message 测试是否正确断言 policy decision / governed failure outcome / diagnostic 各自的 message

**结论: 部分错误。详见 Finding 2。**

`test_candidate_and_ack_carry_duplicate_diagnostic_refs` 正确断言了：
- `governed_candidate.policy_decision.message == configured_message`（hard_stop message → policy decision ✓）
- `governed_outcome.result.message == configured_message`（hard_stop message → failure outcome ✓）

但错误断言了：
- `diagnostics.records[0].message == configured_message`（hard_stop message → diagnostic ✗）

按 plan 7.11，diagnostic record message 应为 `attempt_scope_diagnostic`，而非 hard_stop message。

### Q5: accept barrier 测试是否证明 prior refs 来自 attempt-local accepted entry

**结论: 正确。**

`test_event_sequence_monotonic_and_reuse_has_canonical_governance_only`（`test_toolruntime_accept_barrier.py:468-514`）：
- 先创建 completed candidate 并 accept，得到 `first.tool_result_event_ref`
- 再创建 reuse candidate，传入 `prior_ref=first.tool_result_event_ref`
- 断言 governed payload 中的 `reuse_prior_event_refs == [first.tool_result_event_ref]`

prior refs 来自同 Attempt 同 test scope 内的 accept barrier 返回的 `tool_result_event_ref`，不通过 EventLog 读取或重建。这证明了 "prior refs 只能从 `_AttemptDuplicateGovernanceState` 同 scope accepted entry 产生" 的不变性。

### Q6: 是否引入 durable ledger / EventLog 重建 / schema change / 兼容 wrapper / Any/object / README 越界

**结论: 均未发现。**

- **Durable duplicate ledger**: 不存在。`InMemoryAttemptDuplicateGovernance` 纯内存，不写 SQLite。
- **EventLog 重建 duplicate refs**: 不存在。prior refs 来自 `_AttemptDuplicateGovernanceState` 内存 entries，不从 EventLog 读取。
- **Schema change**: 不存在。无 SQLite DDL 变更。
- **兼容 wrapper/re-export**: 未发现。`tool_runtime.py` 中的 imports 全部来自 `dayu.host.tool_duplicate_governance` 真源模块。
- **Any/object/无类型签名**: 未发现。所有新增/修改函数均有完整类型注解。
- **README 越界**: Slice 3 未修改 README，按 plan 和 artifact 声明，README sync 由 Slice 4 处理。

---

## Open Questions

1. **Slice 3 将 `_diagnostic_refs_for_duplicate` 从 `diagnostic_message` 改为 `message` 是否有未被记录的讨论或隐式设计理由？** 当前只能从 implementation artifact 的 "保证配置化 duplicate message 同时出现在 policy decision、governed failure outcome 与 diagnostic record" 推测动机，但这条理由与 plan 7.11 明确要求 diagnostic 使用独立 `attempt_scope_diagnostic` 的设计冲突。

2. **是否有计划在 Slice 4 修复此问题？** 如果 Slice 3 的变更是临时性的（为让测试通过后再在 Slice 4 回归），需明确记录；否则应视为 Slice 3 需要修复的 blocking 缺陷。

---

## Verification

```bash
source .venv/bin/activate
python -m pytest tests/host/test_toolruntime_diagnostics.py \
  tests/host/test_toolruntime_accept_barrier.py \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_toolruntime_duplicate_governance.py -v
# Result: 52 passed

source .venv/bin/activate && pyright
# Result: 0 errors, 0 warnings, 0 informations
```

---

## Conclusion

| Category | Count | Details |
|---|---|---|
| Blocking findings | **2** | Finding 1 + Finding 2（后者是前者的测试侧表现） |
| Non-blocking findings | 2 | Finding 3（null guard 自洽性）、Finding 4（冗余字段） |
| Open questions | 2 | 变更动机解释、Slice 4 修复计划 |

**Remaining blocking findings: 2**

Slice 3 的 `tool_trace.py` 变更、accept barrier 测试补充、TOOL_CALL_GOVERNED payload duplicate_scope 保留、duplicate_scope 测试补充——均实现正确。但 `_diagnostic_refs_for_duplicate` 从 Slice 2 正确使用 `diagnostic_message` 回退到使用 `message`，是明确的 plan 偏离，需要修复后才能通过 code review gate。

修复范围预计极小：`tool_runtime.py` 一处变更（`_diagnostic_refs_for_duplicate` 两个位置）+ `test_toolruntime_diagnostics.py` 一处断言调整，不涉及其它文件或新契约。
