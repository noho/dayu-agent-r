# WU-TOOL-02 Aggregate Deepreview — AgentDS

## Scope 与 Reviewed Inputs

- **Review scope**: 当前分支 `refactor/wu-tool-02-accept-candidate-cleanup` 相对 `main` 的完整 diff
- **Work unit**: WU-TOOL-02 Accept Candidate Structure Cleanup
- **设计真源**: `docs/host/design.md`
- **总控真源**: `docs/host/host-core-followup-implementation-control.md`
- **Approved plan**: `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md`
- **Reviewed files**:
  - Production: `dayu/host/tool_runtime.py` (+665/-302 lines)
  - Tests: `test_toolruntime_accept_barrier.py`, `test_toolruntime_executor.py`, `test_toolruntime_duplicate_governance.py`, `test_toolruntime_diagnostics.py`, `test_toolruntime_truncation_fetch_more.py`
  - Read-only verification: `dayu/host/tool_trace.py`, `dayu/host/memory.py`, `dayu/host/compaction_evidence.py`, `dayu/host/compact_material.py` (zero changes — confirmed by git diff)
  - Awaiting path: `dayu/host/waiting.py` (untouched — `ToolAwaitingAcceptCandidate` is separate type, out of scope per plan)

## Review Method

按 deepreview 方法执行：
1. 从 change intent 与 approved plan 建立 review map
2. 对关键真实路径做直接代码走读：producer → candidate validation → accept barrier → EventLog payload → ack → projection consumers
3. 执行 adversarial failure pass
4. AGENTS.md / architecture boundary check
5. Overcoupling / structural clarity check
6. Tests coverage judgment

## Finding 1: No blocking findings

**Severity**: 无

经过完整代码走读、adversarial failure pass、架构边界检查和测试覆盖审查，本轮 WU-TOOL-02 改动没有 blocking finding。

## Finding 2 (non-blocking): `_tool_result_payload` 中 governed payload 的 `else None` 缩进变更

**Severity**: 非阻塞

**Evidence**: `dayu/host/tool_runtime.py:3520` 附近，diff 显示：
```diff
-            else None
+                else None
```

这是 diff 中的缩进调整（从 12 空格变为 16 空格），原因是 `if governed is not None` 分支增加了 `_event_ref_json` 调用的换行。语义无变化，EventLog payload 不变。

**建议**: 无需修改。确认该行是纯格式化变更。

## Finding 3 (non-blocking): `_validate_tool_accept_duplicate_governance` 中对 `duplicate_decision_message` 做了双重校验

**Severity**: 非阻塞

**Evidence**: `dayu/host/tool_runtime.py:3959-3984`：
```python
_require_optional_non_empty_text(
    duplicate.duplicate_decision_message,
    field_name="duplicate_decision_message",
)
...
if duplicate.duplicate_decision_message is None:
    raise ValueError("duplicate decision requires duplicate_decision_message")
```

`_require_optional_non_empty_text` 对 `None` 通过，但后面 `if ... is None: raise` 再次拦截 `None`。两段逻辑各自有效且不冲突：前者拦截空字符串，后者拦截 `None`。行为等价于旧代码中 `if ... is None: raise` + `_require_non_empty_text(...)` 的组合。

**建议**: 当前实现正确，但可读性略低。若后续维护时想要更清晰，可在 `_require_optional_non_empty_text` 后直接做 `None` 检查，去掉后者。不改不影响正确性。

## Finding 4 (non-blocking): `_validate_tool_accept_duplicate_governance` 中 ALLOW 决策要求 `duplicate_scope` 和 `duplicate_decision_message` 非空

**Severity**: 非阻塞

**Evidence**: `dayu/host/tool_runtime.py:3974-3979`：
```python
if duplicate.duplicate_scope is None:
    raise ValueError("duplicate decision requires duplicate_scope")
if duplicate.duplicate_decision_message is None:
    raise ValueError("duplicate decision requires duplicate_decision_message")
```

这两个检查对 `DuplicateDecisionKind.ALLOW` 同样生效，即 ALLOW 决策也必须携带 scope 和 message。这与旧 `_validate_duplicate_fields` 行为一致（旧代码也未对 ALLOW 豁免 scope/message 检查）。测试 `test_duplicate_allow_does_not_append_governed_event` 构造了带 scope/message 的 ALLOW duplicate，验证通过。

**建议**: 不需要修改。若未来想要 ALLOW 不强制 scope/message，需单独设计并修改 plan。

## Adversarial Failure Pass

以下场景逐一验证：

### 1. EventLog payload key stability

- **`TOOL_CALL_REQUESTED`**: payload key 完全不变 (`_tool_call_requested_event_request`, line 3204-3232)。所有值从子结构读取。
- **`TOOL_CALL_GOVERNED`**: payload key 完全不变 (`_append_tool_call_governed_if_needed`, line 3300-3370)。新增 `duplicate.duplicate_key if duplicate is not None else None` 访问模式安全。
- **`TOOL_RESULT_ACCEPTED`**: payload key 完全不变 (`_tool_result_payload`, line 3471-3530)。所有值从子结构读取。
- **`accepted_evidence_envelope`**: shape 不变，字段从 `candidate.call`, `candidate.idempotency`, `candidate.result` 读取。

**结论**: EventLog 写入的 JSON payload 与重构前完全一致。下游 projection consumers 不会感知变化。

### 2. Event ID derivation stability

`_tool_accept_event_plan` (line 3160-3185) 的 `digest_input` dict key/value 与重构前完全相同：
- `session_id`, `run_id`, `attempt_id`, `execution_id` → `candidate.identity.*`
- `iteration_id`, `tool_call_id` → `candidate.call.*`
- `accept_idempotency_key`, `semantic_input_digest` → `candidate.idempotency.*`
- `tool_fact_kind` → `candidate.tool_fact_kind`

**结论**: event id 派生稳定，不会造成已有 event id 变化。

### 3. Idempotency scope stability

`_accept_idempotency_scope` (line 3070-3078) 的 scope_id 组合不变：`f"{candidate.identity.attempt_id}:{candidate.call.tool_call_id}"`，idempotency_key 仍是 `candidate.idempotency.accept_idempotency_key`。

**结论**: accept idempotency 行为不变。

### 4. Reuse path correctness

- `_tool_fact_reuse_accept_candidate` (line 5103-5141): 构造 `result=None`, `governance.duplicate` 承载 reuse 字段
- `_validate_reuse_candidate` (line 4240-4262): 校验 `candidate.result is not None` 时 reject，等价于旧代码分别检查 `payload_ref`, `payload_digest`, `raw_tool_outcome` 非空
- `_append_tool_result_if_needed` (line 3314-3316): `REUSE` 时直接返回 None，不写 `TOOL_RESULT_ACCEPTED`
- `_accepted_ack_from_rows` (line 3795-3800): `result_digest` 通过 `_ack_result_digest` 回退到 `semantic_input_digest`

**结论**: reuse 路径语义完全保持。

### 5. Duplicate governance correctness

- `_should_append_governed_event` (line 3659-3679): 对 ALLOW duplicate 正确跳过 governed event；通过 `candidate.governance.duplicate is not None` 守卫后才访问 `.duplicate_decision`，无 NPE 风险。
- `_append_tool_call_governed_if_needed` (line 3240-3300): `duplicate_key`, `duplicate_decision`, `duplicate_scope`, `reuse_prior_event_refs` 均通过 `duplicate is not None` 守卫后访问。
- `_validate_duplicate_governed_candidate` (line 4188-4223): `duplicate = candidate.governance.duplicate` 提取，logic 与旧代码等价。

**结论**: duplicate governance 语义不变。

### 6. `_candidate_result` crash safety

`_candidate_result` (line 4270-4287) 在 `candidate.result is None` 时抛出 ValueError。所有调用点验证：

| 调用点 | REUSE guard | 安全 |
|--------|-------------|------|
| `_tool_result_payload_plan` (line 3373) | Called via `_append_tool_result_if_needed`, which returns None for REUSE | ✅ |
| `_tool_result_payload` (line 3473) | Called from `_tool_result_payload_plan` | ✅ |
| `_accepted_evidence_envelope` (line 3581) | Called from `_tool_result_payload` | ✅ |
| `_require_raw_tool_outcome` (line 4273) | Guarded by `if candidate.result is None: raise` | ✅ |
| `ToolFactAcceptCandidate.__post_init__` (line 600) | Guarded by `if self.tool_fact_kind is ToolFactKind.COMPLETED` | ✅ |
| `_validate_result_fact_policy` (line 4231) | Guarded by `if candidate.result is None: raise` | ✅ |

**结论**: `_candidate_result` 在所有调用点都有 REUSE guard 或 result None guard，不会意外崩溃。

### 7. Plain governed error vs duplicate governed error 区分

`_validate_governed_error_candidate` (line 4164-4185):
- `policy_decision.kind is GOVERNED_ERROR` 且无 prior refs → 早期返回（plain governed error）
- 否则进入 `_validate_duplicate_governed_candidate`（duplicate governed error）

**结论**: 两条路径正确分流，不会将 plain governed error 误判为 duplicate governed error。

### 8. `LOST` fact kind 防御

`ToolFactAcceptCandidate.__post_init__` (line 615):
```python
else:
    raise ValueError("unsupported tool_fact_kind")
```

`LOST` 会落入 else 分支并 fail-fast。plan 明确 `LOST` 不在支持范围。

**结论**: 防御正确。

### 9. Awaiting path 隔离

- `dayu/host/waiting.py`: 无 diff（git diff main...HEAD 无输出）
- `_tool_awaiting_accept_candidate` (line 5144): 无 diff
- `ToolAwaitingAcceptCandidate` 是独立类型，无需修改

**结论**: awaiting path 完全隔离。

### 10. Projection consumers 隔离

- `dayu/host/tool_trace.py`, `memory.py`, `compaction_evidence.py`, `compact_material.py`: 零 diff
- 相关测试文件 (`test_tool_trace_projection.py`, `test_tool_trace_queries.py`, `test_memory_projection.py`, `test_compaction_operation.py`, `test_llm_compaction.py`): 零 diff
- 121 个 projection 测试全通过

**结论**: projection consumers 完全不受影响。

## AGENTS.md / Architecture Boundary Check

### 分层边界

| 检查项 | 状态 |
|--------|------|
| `dayu.runtime` 未被 import | ✅ 未引入新 import |
| Host 内部类型未升级为 public API | ✅ 子结构均为模块级，未加入 `__all__` 或 re-export |
| 无反向依赖（Engine → Host） | ✅ 无 Engine 文件被改动 |
| EventLog 消费者未被修改 | ✅ tool_trace/memory/compaction 零 diff |
| Service/UI 层不受影响 | ✅ Host public API 未变 |

### 编码硬约束

| 检查项 | 状态 |
|--------|------|
| 所有新增 dataclass 有完整中文 docstring | ✅ 7 个子结构 + 组合根均有完整 docstring |
| 所有新增函数有完整中文 docstring | ✅ 所有 validator、producer helper、accessor 均有 docstring |
| 无 `Any` / `object` / 无类型签名 | ✅ 全量 pyright 0 errors |
| 禁止兼容 wrapper/facade/re-export | ✅ 无旧字段 property（grep 验证），无 re-export |
| 禁止 extra payload | ✅ 所有字段均为显式类型字段 |
| 禁止 god dataclass | ✅ 超宽 candidate 已拆分为 7 个职责清晰子结构 |
| 无魔法数字/字符串 | ✅ 常量使用模块级 `_CONST` 或枚举 |
| 模块级私有辅助函数 | ✅ 所有 validator/accessor 均为模块级函数 |

### 类型签名

| 检查项 | 状态 |
|--------|------|
| `raw_tool_outcome: JsonValue` | ✅ `JsonValue` 类型别名包含 `None`，等价于旧 `JsonValue \| None` |
| `duplicate_decision: DuplicateDecisionKind` (非 Optional) | ✅ `ToolAcceptDuplicateGovernance` 必含 decision |
| `duplicate_scope: DuplicateGovernanceScope \| None` | ✅ ALLOW 的 scope 可为 None？否，validator 检查 reject None — 但类型允许。属于 runtime-check 强于类型约束的防御设计 |
| `reuse_prior_event_refs: tuple[HostEventRef, ...]` | ✅ 空元组表示无 prior refs |

## Overcoupling / Structural Clarity Check

### 职责分离

| 子结构 | 职责 | 内聚度 |
|--------|------|--------|
| `ToolAcceptIdentity` | Session/Run/Attempt/Execution 身份 | 高 — 仅 4 个身份字段 |
| `ToolAcceptCall` | 工具调用 metadata 与 digest | 高 — 仅 6 个工具调用字段 |
| `ToolAcceptResult` | Outcome/payload/truncation/raw outcome | 高 — 仅 5 个结果字段 |
| `ToolAcceptDuplicateGovernance` | Duplicate key/decision/scope/message/prior refs | 高 — 仅 5 个治理字段 |
| `ToolAcceptGovernance` | Policy decision + 工具幂等 key + duplicate | 中 — 组合 policy 与 duplicate，职责边界清晰 |
| `ToolAcceptIdempotency` | Accept idempotency key + semantic digest | 高 — 仅 2 个字段 |
| `ToolAcceptDiagnostics` | 诊断引用 | 低 — 仅 1 个字段，但按 plan 允许保留为独立子结构 |

### 组合根清晰度

`ToolFactAcceptCandidate` 现在是稳定的 7 字段组合根：
```python
identity: ToolAcceptIdentity
call: ToolAcceptCall
tool_fact_kind: ToolFactKind
result: ToolAcceptResult | None
governance: ToolAcceptGovernance
idempotency: ToolAcceptIdempotency
diagnostics: ToolAcceptDiagnostics
```

替换了原来的 24 个扁平字段。每个子结构自主校验内部 invariant，组合根校验跨子结构 fact-kind 约束。

### 无循环依赖

所有子结构均为 frozen dataclass，无互相引用：
- `ToolAcceptGovernance` → `ToolAcceptDuplicateGovernance` (单向)
- 其余子结构之间无引用关系

### Validation 分层

- **子结构层** (`__post_init__` → `_validate_tool_accept_*`): 校验内部 invariant
- **组合根层** (`ToolFactAcceptCandidate.__post_init__` → fact-kind validators): 校验跨结构约束

分层清晰，无重复校验。

### 消费者耦合度

所有 EventLog payload consumer 现通过 `candidate.identity.*`, `candidate.call.*`, `candidate.result.*`, `candidate.governance.*`, `candidate.idempotency.*`, `candidate.diagnostics.*` 访问字段，不再通过扁平 candidate 访问。字段语义通过子结构名称自文档化。

## Tests and Validation Coverage Judgment

### 测试覆盖矩阵

| 场景 | 测试 | 状态 |
|------|------|------|
| Ordinary COMPLETED result | `test_tool_result_accepted_payload_carries_accepted_evidence_envelope` | ✅ |
| Large payload cold storage | `test_tool_result_accepted_large_payload_uses_sqlite_payload_descriptor` | ✅ |
| Missing payload descriptor | `test_accept_rejects_missing_payload_descriptor_before_writing_events` | ✅ |
| Payload descriptor digest mismatch | `test_accept_rejects_payload_descriptor_digest_mismatch` | ✅ |
| Idempotency conflict | `test_same_accept_key_with_different_digest_returns_idempotency_conflict` | ✅ |
| Invalid attempt / stale execution | `test_invalid_attempt_and_stale_execution_reject_without_tool_facts` | ✅ |
| Event sequence monotonic | `test_event_sequence_monotonic_and_reuse_has_canonical_governance_only` | ✅ |
| Duplicate ALLOW skips governed | `test_duplicate_allow_does_not_append_governed_event` | ✅ |
| Non-reuse rejects prior reuse refs | `test_non_reuse_fact_rejects_prior_reuse_refs` | ✅ |
| Duplicate governance normalization | `test_duplicate_key_normalizes_arguments_deterministically` | ✅ |
| Duplicate key excludes index | `test_duplicate_key_excludes_index_in_iteration` | ✅ |
| Allow duplicate executes all | `test_allow_duplicate_decision_executes_and_accepts_each_call` | ✅ |
| Reuse references prior refs | `test_reuse_references_prior_refs_without_second_result_fact` | ✅ |
| Duplicate governed matrix | `test_duplicate_governed_matrix_produces_diagnostics` | ✅ |
| Governed validation rejects | 6 negative tests covering missing prior refs, policy/reason/message mismatch, allow policy | ✅ |
| Cross-attempt fresh duplicate | `test_cross_attempt_same_run_duplicate_executes_fresh_without_prior_refs` | ✅ |
| Fresh handle in-memory reset | `test_fresh_toolruntime_handle_same_attempt_is_in_memory_non_durable_reset` | ✅ |
| Concurrent reuse waiter | `test_same_attempt_concurrent_reuse_waits_for_owner_accept` | ✅ |
| Plain policy rejection | `test_plain_policy_rejection_does_not_carry_duplicate_prior_refs` | ✅ |
| Diagnostics on candidate/ack | `test_candidate_and_ack_carry_duplicate_diagnostic_refs` | ✅ |
| Truncation + fetch_more | `test_truncated_result_exposes_only_cursor_and_scope_token`, `test_fetch_more_dispatches_as_normal_tool_and_is_single_use` | ✅ |
| All projection consumers | 121 tests, all pass | ✅ |

### 覆盖缺口（非阻塞）

1. **子结构直接单元测试**: 新子结构 (`ToolAcceptIdentity`, `ToolAcceptCall`, `ToolAcceptResult`, etc.) 的 `__post_init__` validator 没有独立单元测试。它们通过组合根路径间接覆盖。考虑到子结构是 Host 内部类型且已有类型系统保护，当前覆盖可接受。

2. **`raw_tool_outcome is None` 场景**: `_require_raw_tool_outcome` 对 `result.raw_tool_outcome is None` 的分支没有直接测试。所有测试都构造了非 None 的 raw_tool_outcome。

3. **`ToolAcceptDiagnostics` 空 tuple 校验**: 所有测试使用空 `diagnostic_refs=()` 或有非空值，没有直接测试 `ToolAcceptDiagnostics(diagnostic_refs=(wrong_type,))` 的 reject 路径。pyright 类型检查已覆盖此路径。

### 测试质量

- 测试 helper 重构质量高：`_candidate_identity()`, `_candidate_call()`, `_allow_governance()`, `_candidate_idempotency()` 消除了重复构造参数
- 测试内新增 `_required_result()`, `_required_duplicate()` 等 accessor，可读性优于裸 `assert candidate.result is not None`
- Negative validation tests 使用 `replace()` + 子结构组合正确表达"修改哪个子结构"的意图
- Duplicate governance 测试文件新增 `_candidate_duplicate()`, `_candidate_duplicate_decision()`, `_candidate_duplicate_scope()` helper，与 `test_toolruntime_accept_barrier.py` 中的 helper 风格一致

## Old Field Residual Check

使用正则 `candidate\.(session_id|run_id|attempt_id|execution_id|outcome_digest|payload_digest|...)` 搜索：

| 文件 | 结果 |
|------|------|
| `dayu/host/tool_runtime.py` | **0 hits** — 完全迁移 |
| `dayu/host/waiting.py` | N hits — 全部为 `ToolAwaitingAcceptCandidate`（独立类型，非本 WU 范围） |
| `tests/host/test_toolruntime_*.py` | 0 hits on `ToolFactAcceptCandidate`；`test_toolruntime_executor.py` 的 hit 为 `ToolAwaitingAcceptCandidate` |
| `tests/host/test_wait_awaiting_accept.py` | N hits — 全部为 `ToolAwaitingAcceptCandidate` |

**结论**: `ToolFactAcceptCandidate` 所有旧扁平字段访问已完全迁移。无残留、无 facade、无 property 转发。

## Residual Risks / Uncovered Areas

1. **`ToolAcceptGovernance` 的子结构 `duplicate: ToolAcceptDuplicateGovernance | None` 在 ALLOW 决策时要求 scope/message 非空** — 当前所有构造点正确提供这些值，但不排除未来有人构造只有 `duplicate_key` 而无 scope/message 的 ALLOW candidate。validator 会 reject，行为正确。

2. **`JsonValue` 类型包含 `None`，`raw_tool_outcome: JsonValue` 类型上允许 None** — 运行时 `_require_raw_tool_outcome` 检查了 `is None`，但类型系统无法区分"非 None 的 JsonValue"与"可能是 None 的 JsonValue"。如需更精确的类型，可定义 `NonNullJsonValue`。当前设计合理，不需要为此引入新类型。

3. **测试 helper 重复** — `_accepted_ack` helper 在 `test_toolruntime_accept_barrier.py`, `test_toolruntime_duplicate_governance.py`, `test_toolruntime_diagnostics.py`, `test_toolruntime_truncation_fetch_more.py` 四个文件中各自定义。这是 pre-existing 问题，非本次重构引入。

## Final Verdict

**pass-with-nonblocking-notes**

理由：
- 所有 206 个受影响测试 + 121 个 projection 测试全部通过
- pyright 0 errors
- `ToolFactAcceptCandidate` 已收敛为内部 typed composition root，无旧字段 facade/wrapper/re-export
- Producer → candidate validation → accept barrier → EventLog payload → ack → projection consumers 全链路正确读取新子结构
- EventLog event type、payload key、event id 派生、accepted evidence envelope、idempotency scope、duplicate governance、reuse、wait、retry 语义保持不变
- Projection consumers 零改动
- Awaiting path 零改动
- AGENTS.md 分层边界、编码硬约束、类型签名全部满足
- 测试覆盖充分，覆盖普通 result、failed/cancelled、plain governed error、duplicate governed error、reuse、diagnostics、truncation、payload consumers
- Adversarial failure pass 无发现
- 3 个 non-blocking notes：次要代码风格/可读性事项，不影响正确性或 maintainability
