# WU-SEMANTIC-OWNERSHIP-01 P3-E Plan Review (AgentDS)

## Review Metadata

- **Review target**: `docs/host/wu-semantic-ownership-01-p3-e-tool-result-wait-fins-contracts-plan.md`
- **Work unit**: WU-SEMANTIC-OWNERSHIP-01 P3-E — Tool result, accepted status, wait callback, and Fins direct stream contracts
- **Reviewer**: AgentDS (adversarial plan review)
- **Date**: 2026-07-11
- **Conclusion**: **pass-with-risks** (5 material findings, 0 blocking)

## Scope Reviewed

Plan artifact claiming 6 accepted source findings, 3 implementation slices, and `ready-for-plan-review` status. Review covers:

- Source finding disposition vs code facts
- Slice coherence and mechanical split risk
- Architecture boundaries: contracts → Host accepted projection → Service callback mapper → Fins direct runtime → Engine LLM projection
- Overengineering risk: no resolver framework, no Fins ledger, no schema migration
- Implementation readiness: exact files, exact tests, validation commands, README triggers, propagation audit
- Test gaps and stop conditions

## Context Read

| Source | Status |
|---|---|
| `AGENTS.md` | Read full |
| `docs/host/design.md` | Read key sections (design goals, layering, ToolRuntime/TruncationManager, projection boundaries) |
| `docs/engine/design.md` | Read full (ToolExecutionOutcome, tool result envelope, Engine projection of hint) |
| `docs/host/issues-implementation-control.md` | Searched P3-E entry point |
| `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md` P3-E section | Read full |
| `docs/reviews/wu-semantic-ownership-01-p3-e-goal-confirmation.md` | Read full |
| Target plan | Read full |

**Code facts verified:**

| File | Verification |
|---|---|
| `dayu/contracts/tool_result.py:63-106` | Confirmed: `ToolResultSuccess` no `__post_init__`; `ToolResultFailure.__post_init__` only checks error/message/hint, not `ok is False` |
| `dayu/service/wait_callback_endpoint.py:542-564` | Confirmed: `isinstance(raw, str)` branch fabricates `WaitAdapterKey("callback")` |
| `dayu/host/accepted_result_projection.py:390-460` | Confirmed: `_accepted_status` falls back to `_status_from_raw_outcome` when typed status fields absent |
| `dayu/host/accepted_result_projection.py:439-460` | Confirmed: `_status_from_raw_outcome` reconstructs status from `kind` or `result.ok` |
| `dayu/fins/ingestion_runtime.py:2698-2717` | Confirmed: duplicate RESULT → `continue`; missing RESULT → `_direct_missing_result_event` |
| `dayu/service/fins_direct.py:497-510` | Confirmed: duplicate → `FinsDirectUsageError`; missing → `_missing_result_event` (synthetic failure) |
| `dayu/host/tool_runtime.py:7465-7562` | Confirmed: `_truncation_failure(hint=reason_code)`, `_governed_failure_outcome(hint=policy_decision.reason_code)`, `_accept_failure_outcome(hint="accept_rejected:...")`, `_awaiting_accept_failure_outcome(hint=...)` with `_hint_with_diagnostic_refs` |
| `dayu/engine/agent.py:430-446` | Confirmed: `_project_tool_failure_for_llm` writes `result.hint` into LLM-facing tool message JSON |
| `dayu/cli/commands/fins.py:96` | Discovered: existing `FinsDirectStreamContractViolation(RuntimeError)` |

## Assumptions Tested

1. **All 6 findings have direct code evidence** → **PASS**. Each finding maps to verified code paths.
2. **3 slices are semantically coherent, not mechanically split** → **PASS with notes**. S1 (envelope + hint) and S2 (callback + projection) are independent; S3 (Fins RESULT) is independent of S1/S2. However, S2 couples callback transport validation with accepted status projection — these are different owner boundaries but share a validation gate, which is acceptable for a 3-slice plan.
3. **No resolver framework, Fins ledger, or schema migration introduced** → **PASS**. Plan explicitly rejects these in non-goals.
4. **Implementation readiness: exact files, tests, validation** → **PASS with notes**. All files exist; test files exist; validation commands are concrete. Minor gaps noted in findings.
5. **Architecture boundaries correctly mapped** → **PASS**. Each fix lands at its semantic owner or direct upstream.
6. **Propagation audit criteria are complete** → **PASS with notes**. The 4 `rg` checks are concrete, but consumer test verification for UNKNOWN status is underspecified (Finding 5).

## Findings

### 1. 未修复-中-S2 accepted status LOST→UNKNOWN 语义迁移未确认 diagnostic 覆盖

- **位置**: S2 Implementation details, `_accepted_status` 改动
- **问题类型**: 状态机漏洞 / 契约缺失
- **当前写法**: Plan 要求 `_accepted_status` 只消费 `payload` 和 `diagnostics`，删除 `_status_from_raw_outcome`；LOST 仅由 `"result_payload_unavailable" in diagnostics or "event_payload_unavailable" in diagnostics` 触发。
- **反例/失败场景**: 当前代码 `project_accepted_tool_result:203` 中 `raw_outcome = result_payload.get(_FIELD_RAW_TOOL_OUTCOME) if result_payload is not None else None`。当 `result_payload` 为 `None` 时，`raw_outcome` 为 `None`，当前 `_accepted_status:411-412` 返回 `LOST`。若 `_result_payload` 在 `result_payload=None` 时未产生 `result_payload_unavailable` diagnostic（例如因 payload resolution 内部路径差异），则 LOST 会退化为 UNKNOWN，丢失 durable 语义精度。
- **为什么有问题**: 从"有 raw outcome → LOST"迁移到"只有 diagnostics → LOST"是语义收缩，需要验证 `_result_payload` 在所有 `result_payload=None` 的路径上都产出了对应 diagnostic。Plan 没有显式确认这一覆盖。
- **直接证据**:
  - `dayu/host/accepted_result_projection.py:203`: `raw_outcome = result_payload.get(...) if result_payload is not None else None`
  - `dayu/host/accepted_result_projection.py:411-412`: `if raw_outcome is None: return AcceptedToolResultStatus.LOST`
  - `dayu/host/accepted_result_projection.py:193-199`: `result_payload, result_diagnostics = _result_payload(...)` — 需要验证 `result_payload=None` 时 `result_diagnostics` 必然包含 `result_payload_unavailable`。
- **影响**: 实施 Agent 可能漏掉某个 `result_payload=None` 但不产生 diagnostic 的路径，导致 LOST 语义被 UNKNOWN 替代，下游消费者（evidence/memory/compact）对数据丢失的感知降级。
- **建议改法和验证点**:
  - 在 S2 实施前，先读取 `_result_payload` 实现，确认 `result_payload=None` 的所有出口都 append 了 `result_payload_unavailable`。
  - 或者保留 `raw_outcome is None and "result_payload_unavailable" not in diagnostics and "event_payload_unavailable" not in diagnostics → LOST` 作为显式 safeguard，并在测试中覆盖此路径。
  - 测试 `test_accepted_status_raw_outcome_none_no_diagnostics_returns_lost`（或确认现有等价覆盖）。
- **修复风险**: 低。只需要补一行 safeguard 或确认已有 diagnostic 覆盖。
- **严重程度**: 中

### 2. 未修复-低-S3 RESULT 缓冲 stop condition 缺少可操作的诊断标准

- **位置**: S3 Stop conditions
- **问题类型**: 不可直接实施
- **当前写法**: "If buffering RESULT until producer done causes a real direct producer to block indefinitely after emitting result, stop and fix producer termination at Fins runtime owner; do not return to 'yield result then ignore later protocol errors'."
- **反例/失败场景**: 实施 Agent 遇到 producer hang 时，stop condition 只说"stop and fix producer termination"，但没有给出判断标准（什么算 hang？timeout 多少？）也没有给出修复方向（加 producer-side done signal？加 timeout wrapper？改 producer contract？）。实施 Agent 可能自行引入 timeout 或信号机制，偏离 plan 的最小改动原则。
- **为什么有问题**: Stop condition 应该给出可验证的判定标准和修复边界，否则实施 Agent 可能过度修复或修复不足。
- **直接证据**: Plan S3 stop conditions 段落。
- **影响**: 实施 Agent 在遇到阻塞 producer 时可能引入超出 P3-E scope 的 producer lifecycle 改动。
- **建议改法和验证点**:
  - 明确：如果在现有测试 suite 和 smoke 中没有 hang，则认为本 stop condition 不触发，记录为 residual risk。
  - 如果触发：在 `_run_direct_stream` 加 producer-done 后的 drain timeout（如 5s），超时时 log diagnostic 并 raise `FinsDirectStreamProtocolError`，而非静默等待。
  - 补充：实施 artifact 中记录当前所有 direct producer 在 emit RESULT 后是否立即 return，作为本 risk 的关闭证据。
- **修复风险**: 低。在 plan 中补一段判定标准即可。
- **严重程度**: 低

### 3. 未修复-低-S3 新增 `FinsDirectStreamProtocolError` 与已有 CLI `FinsDirectStreamContractViolation` 命名冲突未处理

- **位置**: S3 Implementation details, `dayu.fins.direct_events` 新增
- **问题类型**: 架构边界 / 契约缺失
- **当前写法**: Plan 在 `dayu/fins/direct_events.py` 新增 `FinsDirectStreamProtocolError(ValueError)`，但未提及 `dayu/cli/commands/fins.py:96` 已有 `FinsDirectStreamContractViolation(RuntimeError)`。
- **反例/失败场景**: 实施 Agent 可能：
  - 保留两个语义相近但不同名的类型，导致代码库中同一概念有两种表达。
  - 在 CLI 同时 catch 两个类型，增加复杂度。
  - 不确定是否应该用新类型替换旧 CLI 类型。
- **为什么有问题**: 同一协议违反对应两个不同异常类型，违反"同一语义复用同一 source-of-truth"原则。CLI `FinsDirectStreamContractViolation` 的用途（当前在 `dayu/cli/commands/fins.py:736` raise）是"Service stream 结束但没有 terminal result"，与 S3 的 `MISSING_RESULT` 语义完全重叠。
- **直接证据**:
  - `dayu/cli/commands/fins.py:96`: `class FinsDirectStreamContractViolation(RuntimeError)`
  - `dayu/cli/commands/fins.py:736`: `raise FinsDirectStreamContractViolation(...)`
- **影响**: 实施 Agent 可能产生命名不一致或重复异常类型。
- **建议改法和验证点**:
  - 明确：S3 新 `FinsDirectStreamProtocolError` 是 Fins protocol owner 的唯一 typed error；CLI 的 `FinsDirectStreamContractViolation` 应在 S3 中删除或用新类型替代。
  - 如果 CLI 需要额外的 CLI-level context（如 exit code mapping），可在 CLI 层 catch `FinsDirectStreamProtocolError` 并映射，不保留独立异常类型。
  - 在 S3 allowed files 中显式列出 `dayu/cli/commands/fins.py`（当前只列在"only if CLI tests assert synthetic missing-result output"）。
- **修复风险**: 低。Plan 中补一句 disposition 即可。
- **严重程度**: 低

### 4. 未修复-低-S1 `_hint_with_diagnostic_refs` 移除后相关常量清理未显式覆盖

- **位置**: S1 Implementation details
- **问题类型**: 不可直接实施
- **当前写法**: Plan 说"remove `_hint_with_diagnostic_refs` if it becomes unused"。
- **反例/失败场景**: S1 将 `_awaiting_accept_failure_outcome` 的 hint 改为 `None` 后，`_hint_with_diagnostic_refs` 失去唯一调用方。但相关的模块级常量 `_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR` (line 276)、`_TOOL_RUNTIME_HINT_SECTION_SEPARATOR` (line 275)、`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY` (line 274) 也会成为死代码。如果实施 Agent 只删除函数而保留常量，pyright 可能不报 unused private constant，留下 dead code。
- **为什么有问题**: 死代码违反项目"禁止兼容性代码"约束；这些常量是 hint 格式的专属基础设施，hint 清理后无保留理由。
- **直接证据**:
  - `dayu/host/tool_runtime.py:274-276`: 三个 hint 格式常量
  - `dayu/host/tool_runtime.py:7496-7512`: `_hint_with_diagnostic_refs` 函数
  - Plan S1 只提及函数，未提及常量。
- **影响**: 遗留无引用的格式常量，后续维护者可能误读为仍在使用。
- **建议改法和验证点**:
  - S1 implementation details 中显式列出：删除 `_hint_with_diagnostic_refs`、`_TOOL_RUNTIME_DIAGNOSTIC_REF_SEPARATOR`、`_TOOL_RUNTIME_HINT_SECTION_SEPARATOR`、`_TOOL_RUNTIME_DIAGNOSTIC_REFS_HINT_KEY`（确认无其他引用后）。
  - 或者接受"if unused"判断覆盖常量，但需要实施 Agent 在实施 artifact 中显式报告每个常量的引用扫描结果。
- **修复风险**: 低。
- **严重程度**: 低

### 5. 未修复-中-UNKNOWN accepted status propagation audit 缺少消费者测试覆盖清单

- **位置**: Propagation audit completion criteria / S2 Tests
- **问题类型**: 测试缺口
- **当前写法**: Propagation audit 第三条："Tests prove result details may still be extracted from raw outcome while status stays typed / unknown." S2 tests 列出了 `test_projection_maps_raw_result_ok_false_and_extracts_details` 的更新，但没有列出哪些下游消费者需要新增 UNKNOWN 测试。
- **反例/失败场景**: 当 accepted status 从 raw outcome fallback (FAILED) 变为 UNKNOWN 时，下游消费者可能：
  - Evidence builder 可能对 UNKNOWN 工具结果做不同处理（跳过 vs 展示）。
  - Memory projection 可能把 UNKNOWN 工具结果归类到错误的 memory section。
  - Compact material 可能不包含 UNKNOWN 状态工具结果，导致上下文缺失。
  - Outbox / read model 可能对 UNKNOWN 结果展示异常。
  这些消费者当前可能依赖 raw outcome fallback 给出的 COMPLETED/FAILED 判断，改为 UNKNOWN 后会暴露隐式依赖。
- **为什么有问题**: 项目要求"修复完成前必须做一次 propagation audit"。Plan 的 propagation audit 只验证 source-level grep（`_status_from_raw_outcome` 不存在），但没有测试层面的 propagation audit：哪些下游测试会因为 UNKNOWN 而失败，或需要更新断言。
- **直接证据**: Plan propagation audit completion criteria（4 条 `rg` 命令），全部是 source scan，不包含下游消费者测试验证。
- **影响**: 实施 Agent 可能在 S2 完成后发现 evidence/memory/compact/outbox 测试失败，需要跨 slice 修复，违反 S2 non-goal "Do not change raw outcome result detail rendering except where tests must decouple status from raw outcome" 的意图。
- **建议改法和验证点**:
  - 在 S2 测试中增加一条：先运行 `pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_evidence.py tests/host/test_compact.py -q`（或等价的下游消费者测试），确认 UNKNOWN 不会导致非 projection 测试失败。
  - 如果某个消费者测试对 UNKNOWN 敏感，在 S2 implementation details 中显式列出该测试文件的更新范围。
  - Propagation audit 增加一条：确认 evidence/memory/compact 消费者对 `AcceptedToolResultStatus.UNKNOWN` 有显式处理路径，不会假设 status 只能是 COMPLETED/FAILED/CANCELLED/GOVERNED_ERROR/LOST。
- **修复风险**: 中。可能需要调整下游消费者测试断言，但不应调整消费者业务逻辑（UNKNOWN 应被优雅处理）。
- **严重程度**: 中

## Open Questions

无 blocking open question。Goal confirmation 中的 hint 实查已有结论（Finding disposition 中已确认 governance reason/diagnostic refs 进入 hint 的直接证据）。

## Residual Risks

| Risk | Severity | Suggested Tracking |
|---|---|---|
| S1: 移除 hint 后 `message` 字段可能不够 actionable，LLM 恢复能力下降 | 低 | S1 stop condition 已覆盖。实施 artifact 需报告受影响 message 的可读性评估。 |
| S2: 外部 callback caller 仍发送裸字符串 provider_status_ref 时，会收到 `malformed_payload` 而非静默接受 | 低 | 这是有意的 contract hardening。实施 artifact 需记录 breaking change。 |
| S3: RESULT 缓冲改变 event yield 顺序，如果存在依赖 RESULT 先于后续 PROGRESS 的消费者则行为变化 | 低 | 当前所有 direct stream 消费者（CLI/Service）都期望 RESULT 为终态；buffer 不会改变有效顺序。实施 artifact 需确认。 |
| S3: `_direct_missing_result_event` 删除后，如果存在未发现的调用方 | 低 | 已验证只有一处调用（`ingestion_runtime.py:2717`）。 |
| UNKNOWN status 对 evidence/memory/compact 消费者的影响未在 plan 中显式覆盖 | 中 | 见 Finding 5。建议 P3-E 实施 artifact 中补充 consumer impact report。 |

## Conclusion

**pass-with-risks**

Plan 的 6 个 source finding 均有直接代码证据支持；3 个 slice 语义独立、边界清晰；架构映射正确，每处修复落在 semantic owner 或直接上游；没有过度设计（无 resolver framework、无 Fins ledger、无 schema migration）。文件清单、测试文件、验证命令均具体可执行。

5 个 material finding 中无 blocker：Finding 1（LOST→UNKNOWN 覆盖）和 Finding 5（UNKNOWN 消费者测试）是需要在实施中验证的中等风险；Finding 2-4 是低风险的 plan 补全项。所有 finding 均可在 plan 中通过补充说明解决，不需要重写 slice 结构。

建议 plan 在进入 implementation gate 前吸收 Finding 1-4 的补全，Finding 5 可以作为实施 artifact 的验证 checklist 项而非 plan 修改项。
