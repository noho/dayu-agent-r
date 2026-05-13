# Gateflow Code Review — Host P0 S1 Engine Context Compaction

- Work gate: `code review`
- Work unit: Host Phase 0 / P0 - Engine Context Compaction Event 语义前置
- Assigned slice: `P0-S1 engine-contract-unknown-budget`
- Approved plan path: `docs/host/phase0-engine-context-compaction-plan.md`
- Accepted plan commit: `866f6f5`
- Implementation artifact: `docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`
- Review date: 2026-05-13
- Reviewer: mimo

## Review Scope

- `dayu/engine/contracts/engine_events.py`
- `dayu/engine/contracts/agent_run.py`
- `dayu/engine/agent.py`
- `tests/engine/test_engine_event_contract.py`
- `tests/engine/test_agent_phase2.py`
- `tests/engine/runners/openai/test_http_error_event.py`
- `docs/reviews/gateflow-implementation-host-p0-s1-engine-context-compaction-20260513.md`

## Review Methodology

逐文件审查所有变更，对照 approved plan §4 (Contract Changes)、§5 (Implementation Decisions)、§6 (Slice P0-S1 exact allowed changes) 和 §7 (Expected assertions)，同时检查项目约束（类型安全、Engine/Host 边界、docstring 规范、兼容性代码禁令）。

## Findings

### 01-已修复-[低]-ContextBudgetSnapshot 类型级未禁止零值

**文件**: `dayu/engine/contracts/agent_run.py:33-48`

`ContextBudgetSnapshot` dataclass 允许 `prompt_tokens=0, completion_tokens=0, total_tokens=0` 构造。虽然 plan §4.1 明确说"P0 不要求在 `ContextBudgetSnapshot` dataclass 类型级禁止零值"，且"禁止的是把 `0/0/0` 当作 unknown sentinel"，但当前实现没有在 docstring 或 `__post_init__` 中给出任何零值合法语义说明。

**影响**: 低。Plan 明确豁免了此项，且当前生产代码和测试均不构造零值 snapshot。未来调用方如果传入真实零值 snapshot（例如 completion_tokens=0 的 usage report），语义是"真实零"而非 unknown，当前类型设计已支持此语义。

**建议**: 可在 `ContextBudgetSnapshot` docstring 中补一句："数值为零时仍表示真实快照，不等同于 unknown。" 但不阻塞本次 review。

**controller decision status**: pending-controller-decision

---

### 02-未修复-[低]-reason 字段保持自由字符串

**文件**: `dayu/engine/contracts/engine_events.py:269`

`ContextCompactionRequestedData.reason` 仍为 `str`，未收窄为 `StrEnum`。Plan §10 Non-Blocking Risks #1 已识别此风险并归为 Host Phase 5 / Phase 10 处理。

**影响**: 低。当前 Engine 私有常量 `_ERROR_CONTEXT_COMPACTION_REQUIRED` 已保证 reason 字符串稳定，且 `RunFailedData.error_code` 同为字符串契约。Host ingest 若需 typed mapping，属于 Phase 5 职责。

**controller decision status**: pending-controller-decision

---

## Conformance Check Against Approved Plan

### Plan §4.1 最终表达

| 要求 | 状态 |
|------|------|
| `budget_state: ContextBudgetSnapshot \| None` | ✅ `engine_events.py:268` |
| 字段必填，无默认值 | ✅ `engine_events.py:188-189` 测试确认 `default is MISSING` |
| `None` 是唯一 unknown 表达 | ✅ docstring 明确 |
| 不用 `0/0/0` 或 sentinel | ✅ 生产代码和当前测试无旧 sentinel |
| `ContextBudgetSnapshot` 只表示真实快照 | ✅ `agent_run.py:33-48` docstring 已清理 |

### Plan §4.2 保留的诊断事实

| 要求 | 状态 |
|------|------|
| `reason` 继续使用 `context_compaction_required` | ✅ `agent.py:1249` |
| `provider_request_id` 从 Runner 透传 | ✅ `agent.py:1250` → test `test_context_overflow_http_error_maps_to_compaction_required_fact:580` |
| `iteration_completed` 携带 `provider_request_id` | ✅ test line 582 |
| terminal `RunFailedData.provider_request_id` 保留 | ✅ test line 586 |
| `usage_reported` 独立，overflow 不合成 usage | ✅ 事件序列中无 usage |

### Plan §4.3 Error Semantics

| 要求 | 状态 |
|------|------|
| Engine 不 compact / retry | ✅ 无相关代码 |
| `recoverable=True` for `context_compaction_required` | ✅ `agent.py:1243`, test line 587 |

### Plan §4.4 State Semantics

| 要求 | 状态 |
|------|------|
| `context_compaction_requested` 非终态 | ✅ 不在 `TERMINAL_ENGINE_EVENT_TYPES` |
| 事件序列: `iteration_started → context_compaction_requested → iteration_completed → run_failed` | ✅ test line 571-576 |

### Plan §5.1 Target APIs And Types

| 要求 | 状态 |
|------|------|
| 保留 `EngineEventType.CONTEXT_COMPACTION_REQUESTED` wire value | ✅ `engine_events.py:46` |
| 保留 `RunnerHTTPErrorCode.CONTEXT_LENGTH_EXCEEDED` | ✅ runner error test line 262 |
| 保留 `ContextBudgetSnapshot` 导出 | ✅ `agent_run.py:197` |

### Plan §5.2 Ownership Boundaries

| 要求 | 状态 |
|------|------|
| Engine 不做 proactive context governance | ✅ |
| Engine 不做 compact / retry / tokenizer | ✅ |
| Host 状态迁移不在 Engine | ✅ |

### Plan §6 Slice P0-S1 Exact Allowed Changes

| 文件 | 允许变更 | 实际变更 | 状态 |
|------|----------|----------|------|
| `engine_events.py` | `budget_state` 改类型 + docstring | ✅ 已改 | ✅ |
| `agent_run.py` | 删除 `0/0/0` docstring | ✅ 已清理 | ✅ |
| `agent.py` | overflow 分支改 `budget_state=None` | ✅ 已改 | ✅ |
| `test_engine_event_contract.py` | 断言 `None` 合法 + 真实 snapshot 合法 | ✅ 已覆盖 | ✅ |
| `test_agent_phase2.py` | 断言 `budget_state is None` + event ordering | ✅ 已覆盖 | ✅ |
| `test_http_error_event.py` | Runner overflow event-path 测试 | ✅ 已新增 | ✅ |

### Plan §6 Non-Goals (Must NOT Do)

| 禁令 | 状态 |
|------|------|
| 不新增 `UnknownBudget` dataclass / enum / wrapper | ✅ |
| 不提供兼容构造器或兼容 re-export | ✅ |
| 不把预算 unknown 放入 `metadata` | ✅ |
| 不修改 Runner classifier 信号矩阵 | ✅ |
| 不改 Host 代码 | ✅ |

### Plan §7 Expected Assertions

| 预期断言 | 状态 |
|----------|------|
| `budget_state=None` 合法 | ✅ `test_engine_event_contract.py:191-196` |
| `budget_state=ContextBudgetSnapshot(1000, 500, 1500)` 合法 | ✅ `test_engine_event_contract.py:197-213` |
| `ContextBudgetSnapshot(0,0,0)` 不作 unknown sentinel | ✅ 无旧 sentinel 构造 |
| 事件序列正确 | ✅ test line 571-576 |
| `provider_request_id` 透传到三个事件 | ✅ tests line 580, 582, 586 |
| `error_code == "context_compaction_required"` + `recoverable` | ✅ test line 585, 587 |
| Runner HTTP overflow → `CONTEXT_LENGTH_EXCEEDED` + `provider_request_id` + `FinishReason.ERROR` | ✅ test line 262-293 |

### Sentinel Check

```bash
rg -n "ContextBudgetSnapshot\(|prompt_tokens=0|completion_tokens=0|total_tokens=0|0/0/0|占位快照" dayu tests
```

**Production code (`dayu/`)**: 无命中。
**Tests (`tests/`)**: 仅 `ContextBudgetSnapshot(` 在 `test_engine_event_contract.py:199,209`，均为真实非零 snapshot (1000, 500, 1500)。无旧 sentinel。

## Engine/Host Boundary Check

- Engine 仅产出 reactive diagnostic event + recoverable terminal，不实施治理。
- `ContextCompactionRequestedData` 不含 Host policy / estimator / tokenizer 引用。
- `RunFailedData.recoverable=True` 仅标记 Engine 侧可恢复语义，不承诺 Host 恢复行为。
- `EngineRunOutcomeFailed` 正确透传 `provider_request_id` 和 `recoverable`，供 Host 决策。

## Type Safety Check

- `budget_state: ContextBudgetSnapshot | None` 类型正确，pyright 通过。
- 无 `object`、`Any`、无类型参数。
- 所有 dataclass 字段均有显式类型。
- `EngineEventData` TypeAlias 联合包含 `ContextCompactionRequestedData`。

## Event Ordering Check

`test_context_overflow_http_error_maps_to_compaction_required_fact` 验证：

1. `ITERATION_STARTED`
2. `CONTEXT_COMPACTION_REQUESTED` (budget_state=None, provider_request_id="req_context")
3. `ITERATION_COMPLETED` (provider_request_id="req_context")
4. `RUN_FAILED` (error_code="context_compaction_required", provider_request_id="req_context", recoverable=True)

事件顺序正确，`context_compaction_requested` 非终态，`run_failed` 为唯一终态。

## provider_request_id Preservation Check

从 Runner HTTP error 到 Engine terminal 全链路：

1. `RunnerHTTPErrorData.provider_request_id` → `ContextCompactionRequestedData.provider_request_id` (`agent.py:1250`)
2. `RunnerDoneData.provider_request_id` → `IterationCompletedData.provider_request_id` (`agent.py:1280`)
3. `RunFailedData.provider_request_id` (`agent.py:1241`)

测试均断言 `"req_context"` 一致透传。

## recoverable run_failed Semantics Check

- `agent.py:1243`: `recoverable=True` 仅用于 `CONTEXT_LENGTH_EXCEEDED` 路径。
- 其它 HTTP error 路径 (`agent.py:1254-1259`): `recoverable=False`。
- `test_agent_phase2.py:587`: `assert terminal.data.recoverable`。
- `test_agent_phase2.py:536`: 普通 HTTP error 不标记 recoverable（事件序列中无 `CONTEXT_COMPACTION_REQUESTED`）。

recoverable 语义正确隔离。

## Conclusion

**Pass.** 无 blocking findings。实现完全符合 approved plan 的所有要求和预期断言。

两个低严重度 findings 均为 plan 已识别的非阻塞风险，不阻塞 P0-S1 交付。

## Summary

| 指标 | 结果 |
|------|------|
| 结论 | **pass** |
| Findings 总数 | 2 |
| 严重 | 0 |
| 高 | 0 |
| 中 | 0 |
| 低 | 2 |
| Blocking findings | 0 |

## Artifact Path

`docs/reviews/gateflow-code-review-host-p0-s1-engine-context-compaction-mimo-20260513.md`
