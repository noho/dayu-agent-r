# WU-TOOL-02 Aggregate Deepreview — AgentMiMo

## Scope 与 Reviewed Inputs

- **分支**: `refactor/wu-tool-02-accept-candidate-cleanup` vs `main`
- **Work unit**: WU-TOOL-02 Accept Candidate Structure Cleanup
- **Reviewed files**:
  - `dayu/host/tool_runtime.py` — 主要 production 改动
  - `tests/host/test_toolruntime_accept_barrier.py`
  - `tests/host/test_toolruntime_executor.py`
  - `tests/host/test_toolruntime_duplicate_governance.py`
  - `tests/host/test_toolruntime_diagnostics.py`
  - `tests/host/test_toolruntime_truncation_fetch_more.py`
  - `docs/host/host-core-followup-implementation-control.md` — 总控进展记录
  - `docs/host/wu-tool-02-accept-candidate-cleanup-plan.md` — approved plan
- **Read-only verified**: `dayu/host/tool_trace.py`, `dayu/host/compaction_evidence.py`, `dayu/host/compact_material.py`, `dayu/host/memory.py` — 无改动，确认只消费 EventLog payload
- **验证**: 206 affected tests passed, full pyright 0 errors, payload consumer regression tests 121 passed

## Findings

### Finding 01 (Low): `_validate_tool_accept_duplicate_governance` 对 ALLOW 决策校验更严格

**位置**: `dayu/host/tool_runtime.py` lines 4034-4037

**证据**: 旧 `_validate_duplicate_fields` 在 `duplicate_decision is None` 时直接 `return`，不要求 `duplicate_scope` 和 `duplicate_decision_message`。新 `_validate_tool_accept_duplicate_governance` 无条件要求所有 decision（含 ALLOW）提供 `duplicate_scope` 和 `duplicate_decision_message`。

**影响**: 类型签名 `duplicate_scope: DuplicateGovernanceScope | None` 暗示可选，但 validator 实际要求非空。producer `_tool_accept_duplicate_governance_from_decision` 总是从 `DuplicateDecision` 对象填充这些字段，因此运行时不会触发此 stricter validation。属于类型语义与校验语义的轻微不一致。

**风险**: 低。Host 内部类型，producer 保证填充，不会产生运行时回归。

**建议**: 非阻塞。可选择在后续 cleanup 中对齐类型签名（移除 `| None`）或放宽 validator（对 ALLOW 跳过 scope/message 检查）。当前不阻塞 merge。

### Finding 02 (Low): `_tool_result_payload` 内 `else None` 缩进不一致

**位置**: `dayu/host/tool_runtime.py` line 3521

**证据**:
```python
        "tool_call_governed_event_ref": (
            _event_ref_json(_event_ref_from_row(governed))
            if governed is not None
                else None   # <-- 4 spaces extra indent vs sibling expressions
        ),
```

**影响**: 纯风格问题，不影响运行时行为，pyright 已通过。

**建议**: 非阻塞。可在后续 cleanup 中统一缩进。

### Finding 03 (Low): `ToolFactKind.LOST` fail-fast 无显式测试

**位置**: `dayu/host/tool_runtime.py` line 614-615

**证据**: `ToolFactAcceptCandidate.__post_init__` 的 `else` 分支对 LOST（及其它未支持 kind）抛出 `ValueError("unsupported tool_fact_kind")`，但无测试覆盖此路径。此为 pre-existing gap，非本 work unit 引入。

**影响**: LOST fail-fast 行为通过代码审查可确认正确，但缺乏回归保护。

**建议**: 非阻塞。可在后续 work unit 补充 `ToolFactKind.LOST` negative test。

## Adversarial Failure Pass

### Producer -> Candidate Validation -> Accept Barrier -> EventLog Payload -> Ack -> Projection Consumers

**Producer 路径**:
- `_tool_fact_accept_candidate()`: 正确构造子结构组合根，所有 digest 派生输入语义不变。
- `_tool_fact_reuse_accept_candidate()`: 正确构造无 `result` 的 REUSE candidate，`prior_outcome_digest` 仅用于 digest 派生和 idempotency key，不存储在 candidate 上。
- `_tool_accept_duplicate_governance_from_decision()`: 从 `DuplicateDecision` 正确映射到 `ToolAcceptDuplicateGovernance`。

**Candidate Validation 路径**:
- 子结构 `__post_init__` 正确校验内部 invariant（identity 非空、call digest 格式、result digest/payload_ref 一致性、governance policy 类型、idempotency key/digest、diagnostics ref 类型）。
- 组合根 `__post_init__` 正确校验跨结构 fact-kind 约束：COMPLETED/FAILED/CANCELLED 要求 result、REUSE 禁止 result、GOVERNED_ERROR 要求 governed policy。
- `_candidate_result()` 和 `_candidate_reuse_prior_event_refs()` 辅助函数正确处理 None 分支。

**Accept Barrier 路径**:
- `_accept_idempotency_scope()`: 改读 `candidate.identity.attempt_id`、`candidate.call.tool_call_id`、`candidate.idempotency.accept_idempotency_key`，scope_id 格式不变。
- `_read_accept_context()` / `_invalid_accept_context_reason()`: 改读 `candidate.identity.*`，校验逻辑不变。
- `_candidate_payload_descriptor_exists()`: 正确处理 `result is None`（reuse）时直接返回 `True`。

**EventLog Payload 路径**:
- `_tool_accept_event_plan()`: digest_input key/value 完全不变，仅改读取路径。
- `_tool_call_requested_event_request()`: payload key 完全不变。
- `_append_tool_call_governed_if_needed()`: payload key 完全不变，duplicate governance 字段正确从 `candidate.governance.duplicate` 读取。
- `_tool_result_payload()`: payload key 完全不变，所有字段正确从子结构读取。
- `_tool_event_request()`: row identity、source、actor、idempotency key 不变。

**Accepted Evidence Envelope 路径**:
- `_accepted_evidence_envelope()`: 改读 `candidate.call.*`、`candidate.idempotency.*`、`candidate.result.*`，envelope shape 不变。

**Accepted Ack 路径**:
- `_accepted_ack_from_rows()`: 改读 `candidate.diagnostics.diagnostic_refs`、`_candidate_reuse_prior_event_refs()`。
- `_ack_result_digest()`: 正确处理 `candidate.result is not None` 时取 `result.outcome_digest`，否则回退 `idempotency.semantic_input_digest`。
- `_rejected_ack()`: 改读 `candidate.diagnostics.diagnostic_refs`。

**结论**: 全路径读取迁移正确，EventLog payload key、event id 派生、accepted evidence envelope、idempotency scope 语义均不变。

### Idempotency / Duplicate Governance 语义

- 同 key + 同 semantic digest 仍返回既有 ack 且不重复写 facts：accept barrier 测试覆盖。
- duplicate scope 仍为 attempt-scoped：duplicate governance 测试覆盖。
- reuse 仍只写 requested + governed，不写 result：accept barrier 和 duplicate governance 测试覆盖。
- DURABLE_MISSING 仍不携带 prior refs：duplicate governance 测试覆盖（4 个 DURABLE_MISSING 场景）。

### Awaiting 路径隔离

- `ToolAwaitingAcceptCandidate` 仍为独立类型（来自 `dayu.host.tool_awaiting_accept`），不受本 work unit 影响。
- executor 测试中对 awaiting candidate 的字段访问（`candidate.tool_call_id`、`candidate.semantic_input_digest`）属于 `ToolAwaitingAcceptCandidate`，非 `ToolFactAcceptCandidate`。

## AGENTS.md / Architecture Boundary Check

- **类型签名**: 无 `Any`、`object`、无类型参数或无类型返回值。所有新增 dataclass 字段严格类型化。✅
- **中文 docstring**: 所有新增 dataclass、`__post_init__`、validation helper 均提供完整中文 docstring。✅
- **分层边界**: 改动仅在 `dayu/host/tool_runtime.py` 内部，未引入跨层依赖。✅
- **runtime 边界**: 未修改 `dayu.runtime`。✅
- **禁止兼容 wrapper**: 无旧字段 property facade、兼容 re-export 或兼容 wrapper。✅
- **禁止 extra payload**: 显式字段未塞入 extra payload。✅
- **禁止 god dataclass**: `ToolFactAcceptCandidate` 收敛为 7 个 typed 子结构的组合根，每个子结构职责清晰。✅
- **README 触发规则**: 无 README 修改。内部 dataclass 拆分不触发 README 更新。✅

## Overcoupling / Structural Clarity Check

- 子结构职责边界清晰：`ToolAcceptIdentity`（执行身份）、`ToolAcceptCall`（工具调用）、`ToolAcceptResult`（结果）、`ToolAcceptDuplicateGovernance`（重复治理）、`ToolAcceptGovernance`（治理总）、`ToolAcceptIdempotency`（幂等）、`ToolAcceptDiagnostics`（诊断）。
- 组合根 `ToolFactAcceptCandidate` 仅做组合和跨结构约束校验，不承担子结构内部校验。
- producer helper `_tool_accept_duplicate_governance_from_decision()` 正确隔离了 `DuplicateDecision` 到 `ToolAcceptDuplicateGovernance` 的映射逻辑。
- 测试 helper（`_candidate_identity`、`_candidate_call`、`_allow_governance`、`_candidate_idempotency`、`_required_result`、`_required_duplicate`）避免了重复超宽构造参数。
- 无反向依赖：子结构不引用上层类型。

## Tests and Validation Coverage Judgment

**覆盖矩阵**:

| 场景 | 测试文件 | 状态 |
|---|---|---|
| 普通 COMPLETED result | accept_barrier | ✅ |
| 大 payload SQLite descriptor | accept_barrier | ✅ |
| missing payload descriptor 拒绝 | accept_barrier | ✅ |
| payload descriptor digest mismatch 拒绝 | accept_barrier | ✅ |
| idempotency conflict | accept_barrier | ✅ |
| invalid attempt / stale execution 拒绝 | accept_barrier | ✅ |
| reuse (requested + governed only) | accept_barrier + duplicate | ✅ |
| duplicate allow 不写 governed | accept_barrier | ✅ |
| FAILED/CANCELLED 携带 prior refs 拒绝 | accept_barrier | ✅ |
| duplicate governed matrix (hint/require_justification/hard_stop) | duplicate | ✅ |
| duplicate governed missing prior refs 拒绝 | duplicate | ✅ |
| duplicate governed policy mismatch 拒绝 | duplicate | ✅ |
| duplicate governed reason mismatch 拒绝 | duplicate | ✅ |
| duplicate governed message mismatch 拒绝 | duplicate | ✅ |
| governed error allow policy 拒绝 | duplicate | ✅ |
| require_justification with valid argument | duplicate | ✅ |
| require_justification without argument -> hint | duplicate | ✅ |
| plain policy rejection 不携带 duplicate prior refs | duplicate | ✅ |
| cross_attempt same_run duplicate | duplicate | ✅ |
| fresh toolruntime same_attempt in-memory reuse | duplicate | ✅ |
| concurrent reuse waits for owner | duplicate | ✅ |
| DURABLE_MISSING (rejected/timed_out/exception/cancellation) | duplicate | ✅ |
| duplicate candidate missing message 拒绝 | duplicate | ✅ |
| diagnostics 在 candidate/ack/hint 中不丢失 | diagnostics | ✅ |
| truncation cursor hint | truncation | ✅ |
| fetch_more single-use | truncation | ✅ |
| oversized tool result | executor | ✅ |
| side_effect missing idempotency key | executor | ✅ |
| runtime timeout governed failure | executor | ✅ |
| pre-cancelled context governed failure | executor | ✅ |
| no tool scope rejects model tool call | executor | ✅ |
| batch mixed accept outcomes | executor | ✅ |
| payload consumer regression (tool trace, memory, compaction) | projection tests | ✅ |

**未覆盖**:
- `ToolFactKind.LOST` fail-fast（pre-existing gap，见 Finding 03）

## Residual Risks / Uncovered Areas

1. **`ToolFactKind.LOST` 无显式测试**: 代码正确 fail-fast，但无回归保护。低风险。
2. **`_validate_tool_accept_duplicate_governance` 对 ALLOW 的 stricter validation**: 运行时不会触发（producer 保证填充），但类型签名暗示可选。低风险。
3. **缩进风格不一致**: `_tool_result_payload` 中 `else None` 缩进偏移。零风险。

## Final Verdict

**pass-with-nonblocking-notes**

三个 low severity findings 均为非阻塞：
- Finding 01: ALLOW duplicate governance validation stricter than old code，但 producer 保证填充，无运行时回归风险。
- Finding 02: 缩进风格不一致，不影响行为。
- Finding 03: LOST fail-fast 缺乏测试，pre-existing gap。

核心目标达成：
- `ToolFactAcceptCandidate` 已收敛为内部 typed composition root，无旧字段 facade/wrapper/re-export。
- producer、accept barrier、EventLog payload、ack、projection consumers 一致读取新子结构。
- EventLog event type、payload key、event id 派生、accepted evidence envelope、idempotency scope 语义不变。
- 未违反 AGENTS.md 任何硬约束。
- 206 affected tests passed，full pyright 0 errors。
