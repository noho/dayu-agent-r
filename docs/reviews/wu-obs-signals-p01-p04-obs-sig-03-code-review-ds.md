# WU-OBS-SIGNALS-01 OBS-SIG-03 Code Review — AgentDS

## Scope

- Work unit: `WU-OBS-SIGNALS-01`
- Slice: `OBS-SIG-03 / P03 Structured Failure Metadata`
- Agent: AgentDS (code review gate)
- Implementation report: `docs/reviews/wu-obs-signals-p01-p04-obs-sig-03-implementation-codex.md`
- Design truth: `docs/host/design.md`, `docs/engine/design.md`
- Accepted plan: `docs/host/wu-obs-signals-p01-p04-plan.md` (OBS-SIG-03 / P03 section)
- Control document: `docs/host/issues-implementation-control.md`

Reviewed files (from git diff):

- `dayu/host/tool_runtime.py` — `ToolAcceptResult.failure_metadata`, `_failure_metadata_from_outcome`, `_bounded_failure_text`, `_BoundedFailureText`, `_validate_failure_metadata_signal`, `_validate_candidate_failure_metadata`
- `dayu/host/engine_ingest.py` — `_provider_protocol_failure_metadata`, `failure_metadata` in provider protocol error payload
- `dayu/host/tool_trace.py` — `_optional_failure_metadata_signal`, `_validate_failure_metadata_variant`, `_context_compaction_failed_failure_metadata`, `_context_compaction_attempt_rejected_failure_metadata`, closed-union constants
- `dayu/host/README.md` — one sentence addition
- `tests/README.md` — one sentence addition
- `tests/host/test_tool_trace_projection.py` — failure metadata projection/malformed/hot-cold tests
- `tests/host/test_engine_ingest_mapping.py` — provider protocol error mapping test
- `tests/host/test_toolruntime_executor.py` — tool failed/cancelled/policy blocked producer tests, bounded text tests
- `tests/host/test_toolruntime_accept_barrier.py` — payload presence tests for failure_metadata
- `docs/host/issues-implementation-control.md` — gate status update only

Not changed (verified via diff):

- `tests/host/test_context_compact_events.py` — unchanged; context compaction failure_metadata is derived in projection, not from new payload fields
- SQLite schema files — unchanged; `trace_summary_json` reused
- `dayu/engine/` — no files touched; Engine public contract unchanged
- `dayu/host/context_budget.py` — no changes

## Findings

### F1 [LOW] `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS` 常量在 producer 与 projection 层重复定义

**Evidence:**
- `dayu/host/tool_runtime.py` line ~239: `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`
- `dayu/host/tool_trace.py` line ~168: `_TRACE_SIGNAL_BOUNDED_TEXT_MAX_CHARS = 512`

**Impact:** 如果未来需调整 bounded text 上限，需同时修改两个文件。当前两边值一致（均为 512），暂不造成运行时分歧。

**Suggestion:** 可考虑将常量提升至 `dayu/runtime/` 或 `dayu.host.contracts` 单一定义点。但此时 producer (`tool_runtime.py`) 与 consumer/projection (`tool_trace.py`) 处在 Host 包内不同模块，不属于跨层重复。当前不做修改是可接受的。

**Risk:** 低。如果未来在其中一个模块修改而忘记另一个，会导致 producer 产生的 bounded text 通过 projection 验证（因为两边都用 512 上限，producer 截断到 512 的文本在 projection 验证时也 ≤512），但语义不一致（一个按新上限截断，另一个按旧上限验证）。短期不构成实际问题。

### F2 [LOW] `_text_sha256` 测试辅助函数在两处测试文件重复定义

**Evidence:**
- `tests/host/test_tool_trace_projection.py` lines ~1627-1631: 定义 `_text_sha256`
- `tests/host/test_toolruntime_executor.py` lines ~1482-1489: 定义 `_text_sha256`
- `tests/host/test_toolruntime_accept_barrier.py` lines ~1600-1612: 也定义了 `_text_sha256`

**Impact:** 测试代码中三处相同逻辑重复，维护成本轻微增加。

**Suggestion:** 可提取至 `tests/host/` 下的共享 conftest 或 fixture helper，但属于测试代码质量优化，非阻塞。

**Risk:** 极低。测试辅助函数逻辑简单（两行代码），不易出错。

### F3 [INFO] `budget_after_attempted_compact` 在 failure_metadata 派生中使用 `_optional_int`，plan 示例中为必填

**Evidence:**
- Plan spec (`docs/host/wu-obs-signals-p01-p04-plan.md` P03 `context_compaction_attempt_rejected` variant): `"budget_after_attempted_compact": 180`
- Implementation (`dayu/host/tool_trace.py`): `_optional_int(payload, _FIELD_BUDGET_AFTER_ATTEMPTED_COMPACT)`

**Impact:** plan 示例显示该字段存在且为 180，但实现将其视为 optional（可为 null）。如果 context compaction attempt rejected payload 中该字段缺失，projection 会产出 `null`，下游 analyzer 需处理 null。这与 plan 的"null 表示不可用"语义一致。

**Analysis:** Plan 未明确标注该字段为必填（其它字段如 `failure_category`、`repairable`、`next_policy_decision` 也未显式标注 required/optional）。`_optional_int` 处理缺失时的 null 是合理的——某些 compact attempt rejected 场景可能没有 budget after attempt。这符合 signal contract 中"null 表示不可用"的总体设计。

**Risk:** 极低。若 analyzer 依赖该字段做预算推理且预期始终有值，需直接查询 context compaction payload 原始字段而非依赖投影。当前实现已通过 `_optional_int` 做了防御性处理。

### F4 [INFO] Bounded text validation 在 producer 侧只校验 digest 格式，不校验摘要匹配

**Evidence:**
- `dayu/host/tool_runtime.py` `_validate_bounded_text_fields`: 调用 `is_sha256_digest(digest)` 校验格式，但不重新计算原始文本的 sha256 并比对
- `dayu/host/tool_trace.py` `_validate_bounded_text_field`: 同样只校验格式

**Impact:** 如果 producer 有 bug 导致 truncated text 的 digest 错误（例如 digest 了 truncated text 而非 full original），该错误不会被 producer 侧或 projection 侧的 validator 检测到。validator 只校验了格式正确性，非语义正确性。

**Analysis:** 这是设计上的有意限制——projection 侧没有 full original text，无法重新计算 digest 做比对；producer 侧 `_bounded_failure_text` 在同一函数内同时计算 bounded text 与 digest，出错概率极低。且 validator 并不持有 full original text（在 bounded text 已被 truncated 的场景下 full original 已不可恢复），强制要求 producer 侧做 digest recomparison 需要在 bounded 之前保存 full original，会改变数据流。

**Risk:** 极低。当前 producer (`_bounded_failure_text`) 在同一函数内原子性地计算 bounded value 与 digest，不存在中间状态不一致的可能。

## Open Questions

**Q1:** 当 `policy_decision.kind` 不为 `ALLOW` 且 `outcome` 为 `ToolCompletedOutcome`（治理拒绝时构造的合成 outcome）时，`_failure_metadata_from_outcome` 返回 `policy_blocked`。当前逻辑正确（policy 检查先于 outcome 类型判断），但需确认在 future 如果 policy 拒绝路径改变了合成 outcome 的类型（例如改用 ToolFailedOutcome），此处逻辑是否仍然正确。当前不构成任何问题。

**Q2:** `diagnostic_refs` 已从 `ToolTraceDiagnosticRef` 类型安全读取——所有三个 failure_kind variant producer 路径都复用同一个 `diagnostic_ref_ids` 变量。但 policy_blocked 路径（`policy_decision.kind is not ALLOW`）同样使用了该 `diagnostic_ref_ids`，它来自调用方传入的 `diagnostic_refs: tuple[ToolTraceDiagnosticRef, ...]`，而非从 outcome 本身的 diagnostic 信息派生。需确认 policy_blocked 场景下该入参是否始终包含相关 governance diagnostic refs。从代码证据看（`_tool_fact_accept_candidate` 调用点 line ~5672），`diagnostic_refs` 由 caller 在同一上下文中构造，包含 governance 相关 refs，当前实现是正确的。

## Residual Risk

**R1: 历史 trace 行无 `failure_metadata` 字段。** 这是预期的 limited signal 状态。当前 Tool Trace projection 只在 payload 包含 `failure_metadata` 时投影；旧 trace 行的 `trace_summary` 中不含该 key。Analyzer 必须以 "missing key = limited signal" 处理，不得推断为 "no failure"。这与 P02 `tool_timing` 的旧 trace 兼容设计一致。

**R2: Context compaction payload 字段变更的影响。** `_context_compaction_failed_failure_metadata` 与 `_context_compaction_attempt_rejected_failure_metadata` 从 context compaction payload 直接读取字段。如果未来 context compaction payload schema 变更（字段重命名或移除），这些 projection 函数会通过 `_required_text`/`_required_bool` 等 fail closed（HostDurableError），不会静默产出错误数据。但如果新增类型化 failure 原因需要 express 在 failure_metadata 中，则需要更新这两个派生函数。

**R3: `cancel_message` 始终非 null 在类型化 `ToolCancelledOutcome` 中成立，但 null 处理保留。** 当前实现中 `ToolCancelledOutcome.message` 始终为非 null（类型约束），但 `_bounded_failure_text` 和所有 validator 都正确处理了 null case。如果未来 `ToolCancelledOutcome` 类型变更为允许 null message，实现已经兼容。

## Scope Creep Assessment

**无 scope creep 发现。**

逐项检查：

| 检查项 | 状态 | 证据 |
|--------|------|------|
| 不新增 Engine public contract | ✅ | `dayu/engine/` 无任何变更 |
| 不修改 SQLite schema | ✅ | SQLite schema 文件无变更；`trace_summary_json` 复用 |
| 不修改 ToolRuntime execution/governance 语义 | ✅ | 仅 additive payload 字段，不改变 accept/execute/scheduling |
| 不提前实现 P04/analyzer taxonomy | ✅ | diff 中无 `partial_tool_call_signal` 生产代码；无 analyzer 模块 |
| 不修改 Run/Attempt 状态迁移 | ✅ | 所有新增 payload 字段不影响状态机分支 |
| 不修改 memory/recovery/resume | ✅ | 无相关代码变更 |
| 不编写 prompt-based diagnostics | ✅ | 无 prompt 文件变更 |

所有变更严格限制在 OBS-SIG-03 scope 内：

1. **Producer**: `TOOL_RESULT_ACCEPTED` payload 加入 `failure_metadata`（tool_runtime.py）
2. **Producer**: `PROVIDER_PROTOCOL_ERROR` payload 加入 `failure_metadata`（engine_ingest.py）
3. **Projection**: Tool Trace 消费并 validate `failure_metadata`（tool_trace.py）
4. **Projection**: Context compaction 事件派生 `failure_metadata`（tool_trace.py）
5. **Tests**: 覆盖上述所有路径
6. **README**: 仅按约束更新已实现的 Host/test boundary 一句话

## Architecture Alignment

### Host Design Alignment (`docs/host/design.md`)

| 设计约束 | 遵守情况 | 证据 |
|----------|---------|------|
| EventLog canonical fact 是治理真源（§13, line 1355-1369） | ✅ | `failure_metadata` 是 additive payload 字段，不是新 fact type |
| Tool Trace 是 EventLog 派生 projection，不是 durable truth（§14.1, line 1654） | ✅ | failure_metadata 只投影到 `trace_summary_json`，不进 recovery/resume/memory |
| Projection signal 只用于 trace/diagnostic（§13, line 1369） | ✅ | `PROVIDER_PROTOCOL_ERROR` 的 failure_metadata 走 diagnostic event class |
| Tool Trace hot summary 可保存 error code、policy decision、duration、diagnostic refs（§14.1, line 1658） | ✅ | failure_metadata 字段全部匹配该描述 |
| Context Governance 不直接写 tool trace（§Context Governance, line 3118） | ✅ | Context compaction failure_metadata 由 Tool Trace projection 从 EventLog payload 派生，不由 Context Governance 写入 |

### Engine Design Alignment (`docs/engine/design.md`)

| 设计约束 | 遵守情况 | 证据 |
|----------|---------|------|
| Engine 只表达 provider context overflow（§15, line 487-501） | ✅ | 无 Engine 变更 |
| ToolExecutionOutcome 是封闭联合（§10, line 320-335） | ✅ | `_failure_metadata_from_outcome` 对四种 outcome 类型全覆盖（含 TypeError for awaiting/unknown） |
| EngineEvent 不含 session_id/run_id（§14） | ✅ | `ProviderProtocolErrorData.error_code` 来源于 Engine event data，不是 Host 注入 |
| Engine 不计算 Host budget（§15） | ✅ | Context compaction failure_metadata 中的 budget 字段由 Tool Trace 从已有 Host payload 派生，不穿过 Engine |

### Plan Alignment (`docs/host/wu-obs-signals-p01-p04-plan.md` P03 section)

| Plan Requirement | 实现状态 | 验证 |
|-----------------|---------|------|
| closed union: 6 variants | ✅ | `tool_failed`, `tool_cancelled`, `policy_blocked`, `provider_protocol_error`, `context_compaction_attempt_rejected`, `context_compaction_failed` 全部实现 |
| `policy_block_reason` only from `reason_code` | ✅ | `_failure_metadata_from_outcome` 使用 `policy_decision.reason_code`；无 message 文本解析 |
| `provider_error_code` from Engine event data, not raw payload | ✅ | `_provider_protocol_failure_metadata` 使用 `data.error_code`；测试验证 raw payload 不同代码不覆盖 |
| Cancellation 不混入 `tool_failed` | ✅ | `failure_kind="tool_cancelled"` 独立 variant；测试显式断言 `!= "tool_failed"` |
| Successful → `failure_metadata=null` | ✅ | `ToolCompletedOutcome` + ALLOW policy → `None`；`_validate_candidate_failure_metadata` 强制 COMPLETED 为 null |
| `repair_hint`, `cancel_message`, `cancel_hint` 512 char bounded | ✅ | `_bounded_failure_text` 截断到 512；`*_truncated` + `*_sha256` 完整实现 |
| Full original UTF-8 sha256 digest | ✅ | `hashlib.sha256(value.encode('utf-8')).hexdigest()` with `sha256:` prefix |
| 不保存 full tool failure message body | ✅ | `tool_failed` variant 不含 `message` 字段；测试断言 `"message" not in metadata` |
| Context compaction 从 existing payload fields 派生 | ✅ | `_context_compaction_failed_failure_metadata` 和 `_context_compaction_attempt_rejected_failure_metadata` 均从 EventLog payload 读取 |
| 不改变 context event payload schema | ✅ | context compaction 相关 payload 构建代码无变更 |
| Malformed fields → HostDurableError fail closed | ✅ | 测试覆盖 unknown kind、signal source mismatch、over-length bounded text |
| Hot/cold 同源 | ✅ | 测试断言 cold JSONL `trace_summary` 与 hot `trace_summary` 一致 |

### LLM-facing 语义约束 (AGENTS.md)

| 约束 | 检查 |
|------|------|
| 不在 tool schema 中暴露内部模块名/Host 实现术语 | ✅ | failure_metadata 无 schema 暴露给 LLM（只在 diagnostic/trace 中使用） |
| 不暴露裸 event_id/digest/cursor 作为业务事实 | ✅ | `diagnostic_refs` 标记为 diagnostic provenance；无 LLM-facing prompt 变更 |
| 不在 diagnostic 中伪装业务事实 | ✅ | `failure_metadata` 是 Tool Trace read-only signal，不进入 compact material 或 evidence |

## Test Coverage Assessment

### 覆盖矩阵

| 测试场景 | 测试文件 | 断言要点 |
|---------|---------|---------|
| tool_failed producer (repair_hint null/512/513) | `test_toolruntime_executor.py::test_tool_runtime_produces_tool_failed_failure_metadata` | `failure_kind="tool_failed"`, bounded text, `message` NOT in metadata |
| tool_cancelled producer (message/hint bounded) | `test_toolruntime_executor.py::test_tool_runtime_produces_tool_cancelled_failure_metadata` | `failure_kind="tool_cancelled"`, `!= "tool_failed"`, bounded text 三字段 |
| policy_blocked producer (reason_code only) | `test_toolruntime_executor.py::test_tool_runtime_produces_policy_blocked_failure_metadata` | `policy_block_reason="tool_idempotency_key_required"`, 完全值比较 |
| provider_protocol_error mapping | `test_engine_ingest_mapping.py::test_provider_protocol_error_is_diagnostic_without_state_change` | `provider_error_code="invalid_stream"` from Engine data; raw payload uses different code |
| context_compaction_failed projection | `test_tool_trace_projection.py::test_tool_trace_derives_context_pressure_from_compaction_failed_payload` | 完整 failure_metadata 字段比较 |
| context_compaction_attempt_rejected projection | `test_tool_trace_projection.py::test_tool_trace_derives_context_pressure_from_compaction_rejected_payload` | 完整 failure_metadata 字段比较 |
| All variant projection (tool_failed/cancelled/policy_blocked) | `test_tool_trace_projection.py::test_tool_trace_projects_failure_metadata_variants` | hot/cold 一致性，cancelled != tool_failed |
| provider_protocol_error projection | `test_tool_trace_projection.py::test_tool_trace_projects_provider_protocol_failure_metadata` | hot/cold 一致性 |
| malformed failure_metadata fail closed | `test_tool_trace_projection.py::test_tool_trace_rejects_malformed_failure_metadata_signal` | unknown kind → HostDurableError; source mismatch → HostDurableError; over-length → HostDurableError |
| successful result failure_metadata=null | `test_toolruntime_accept_barrier.py::test_tool_result_accepted_payload_carries_accepted_evidence_envelope` | `payload["failure_metadata"] is None` |
| failed/cancelled/governed_error payload presence | `test_toolruntime_accept_barrier.py::test_failed_cancelled_and_governed_error_are_accepted_as_result_facts` | 三种 fact kind 的 failure_metadata 正确性 |
| cold JSONL matches hot summary | 所有 projection 测试 | `_cold_trace_summary(cold_lines, N) == row.trace_summary` |

### 覆盖缺口

| 缺口 | 严重度 | 说明 |
|------|--------|------|
| Context compaction payload 字段缺失/malformed 的 fail-closed 测试 | LOW | `_context_compaction_failed_failure_metadata` 和 `_context_compaction_attempt_rejected_failure_metadata` 依赖于 `_required_text`/`_required_bool`/`_required_int` 的 fail-closed 行为。这些 helper 在已有的 context compaction pressure 测试中被间接覆盖，但没有专门针对 failure_metadata 派生路径的 malformed payload 测试。由于这两个派生函数只是读取已有 payload 字段而不做额外解析，风险极低。 |
| `ToolAwaitingOutcome` 走 `_failure_metadata_from_outcome` 的 TypeError 路径 | LOW | 该路径在正常运行中不可达（awaiting outcome 不走 accept barrier 的 failure_metadata 路径），但缺少显式单元测试覆盖 TypeError 分支 |
| Repair hint 为 null 但 `repair_hint_truncated=True` 的 malformed 测试 | LOW | `_validate_bounded_text_fields` 和 `_validate_bounded_text_field` 都会检查此非法状态，但未在 parametrized malformed 测试中覆盖 |

### 覆盖率估计

基于对修改文件的函数级分析，OBS-SIG-03 相关新增代码的测试覆盖率估计 ≥90%：

- 所有 6 个 failure_kind variant 的 nomial path 均有测试
- Bounded text 三个关键边界（null/512/513）均有测试
- Malformed 路径覆盖了 3 类关键错误
- Hot/cold 一致性在所有 variant 上验证
- Consumer impact（successful result null）已覆盖

## Validation

### 自动化验证

```bash
# 测试
source .venv/bin/activate && pytest \
  tests/host/test_tool_trace_projection.py \
  tests/host/test_engine_ingest_mapping.py \
  tests/host/test_context_compact_events.py \
  tests/host/test_toolruntime_executor.py \
  tests/host/test_toolruntime_accept_barrier.py -q
```

**Result: 185 passed in 1.13s** ✅

```bash
# 类型检查
source .venv/bin/activate && pyright
```

**Result: 0 errors, 0 warnings, 0 informations** ✅

### 手动验证

| 检查项 | 方法 | 结果 |
|--------|------|------|
| `provider_error_code` 来自 Engine data 非 raw payload | 阅读 `_provider_protocol_failure_metadata` + 测试 raw payload code 为 `"raw_payload_code_must_not_win"` 而 assertion 为 `"invalid_stream"` | ✅ |
| `policy_block_reason` 来自 `reason_code` 非文本解析 | 阅读 `_failure_metadata_from_outcome` line ~6135 | ✅ |
| Cancellation 不混入 tool_failed | 测试 `assert metadata["failure_kind"] != "tool_failed"` + `assert metadata["failure_kind"] == "tool_cancelled"` | ✅ |
| Successful → null | `_failure_metadata_from_outcome`: `ToolCompletedOutcome` + ALLOW → `None`; `_validate_candidate_failure_metadata(COMPLETED, None)` → requires null | ✅ |
| Full message body 不保存 | `tool_failed` variant 不含 `message` 字段; 测试 `assert "message" not in metadata` | ✅ |
| Bounded text 三字段完整性 | `_bounded_failure_text`: null → (None, None, False); non-null → (value[:512], sha256, len>512) | ✅ |
| Context compaction 从 existing payload 派生 | `_context_compaction_failed_failure_metadata` 和 `_context_compaction_attempt_rejected_failure_metadata` 均只读取 payload 字段，不增加新 payload 字段 | ✅ |
| SQLite schema 不变 | `git diff --stat` 中无 schema 文件; `trace_summary_json` 复用 | ✅ |
| Engine contract 不变 | `dayu/engine/` 无变更 | ✅ |
| ToolRuntime governance 语义不变 | 只增加 `failure_metadata` additive 字段; 无 execution/scheduling 变更 | ✅ |
| Hot/cold 同源 | 所有 projection 测试 assert `_cold_trace_summary(...) == row.trace_summary` | ✅ |

### README 检查

| README | 约束检查 | 变更 | 判定 |
|--------|---------|------|------|
| `dayu/host/README.md` | 按 §Agent更新约束：只写当前已实现内容，不写未来计划/过程状态。变更为一句话描述 tool trace 投影 context pressure/tool timing/failure metadata signal。符合约束。 | ✅ | 正确 |
| `tests/README.md` | 无显式 Agent更新约束章节。按 AGENTS.md 默认规则，变更为一句话描述测试覆盖范围含 failure metadata signal。符合"当前已存在"原则。 | ✅ | 正确 |
| `dayu/engine/README.md` | 无 `dayu/engine/` 修改，不触发 | N/A | 正确 |
| `dayu/README.md` | 无分层边界变化，不触发 | N/A | 正确 |

## Verdict

**PASS with findings** (2 LOW, 2 INFO)

### Summary

OBS-SIG-03 implementation correctly adds structured failure metadata to Tool Trace signals for all six closed-union variants. The implementation faithfully follows the accepted plan:

1. **Root cause / motivation**: All failure metadata fields are sourced from durable typed facts (`ToolResultFailure.error`, `ToolCancelledOutcome.reason`, `ToolPolicyDecision.reason_code`, `ProviderProtocolErrorData.error_code`) and existing context compaction payload fields. No text parsing, no raw payload inference, no free-form message body storage.

2. **Closed union**: All six `failure_kind` variants are implemented with correct variant-specific fields. Unknown kinds fail closed via `HostDurableError` at projection boundary.

3. **Bounded text**: `repair_hint`, `cancel_hint`, `cancel_message` are properly bounded at 512 Python string characters with full original UTF-8 sha256 digest and `*_truncated` flags. Full failure message body is not stored.

4. **Provider protocol error**: `provider_error_code` comes from Engine `ProviderProtocolErrorData.error_code`, not raw provider payload. Test explicitly proves this.

5. **Layer discipline**: No SQLite schema change, no Engine public contract change, no ToolRuntime governance/execution semantic change. No P04 or analyzer taxonomy pre-implementation.

6. **Tests**: 185 tests pass, 0 pyright errors. All six variants, bounded text boundaries, malformed fail-closed, successful null, hot/cold consistency, and consumer impact are covered.

7. **README**: Both `dayu/host/README.md` and `tests/README.md` updates are minimal, factual, and within their respective update constraints.

The four findings (F1-F4) are all LOW or INFO severity and none require blocking changes before proceeding to the next gate.
