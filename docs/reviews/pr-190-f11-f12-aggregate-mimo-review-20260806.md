# PR 190 F11/F12 Aggregate MiMo Review

## Scope

- Mode: PR aggregate (base 3087b1b9..head 2cf1b4ac)
- PR: #190 `fix(cli): close interactive conformance gaps`
- Branch: `codex/interactive-oracle` → `main`
- Review date: 2026-08-06
- Reviewer: MiMo (independent aggregate review)
- Included scope: 213 files, +24,856/-3,570 lines across F11 public Tool Trace, S2 Engine structured output, S3 fresh v3 contract/prompts, S4 harness/production fixes/immutable evidence, S5 registry/docs, README/tests
- Parallel review coverage: 5 subagents (Engine structured output, Host compaction v3, Tool Trace public, prompts/config, registry/docs/tests)

## Findings

未发现实质性问题。

## Open Questions

无。

## Residual Risk

无。

## Detailed Analysis

### 1. Engine Structured Output (S2)

**Contract design**: `StructuredOutputCapability` enum (`none`/`json_object`/`json_schema`) + `StructuredOutputRequest` union (`JsonObjectStructuredOutputRequest` | `JsonSchemaStructuredOutputRequest`)。封闭联合，`assert_never` 覆盖所有分支。

**Validation**: `validate_structured_output_request()` 在 `AgentRunRequest.__post_init__` 和 `build_request_payload` 两处 fail-closed 校验 capability/request 组合。不支持的组合直接 raise `ValueError`，不做隐式 fallback。

**Payload builder**: `_apply_structured_output_request()` 正确投影为 OpenAI `response_format`。`build_request_payload` 新增 `structured_output` required 参数，在 outbound HTTP 前校验。

**Protocol surface**: `AsyncRunner.call()` 新增 `structured_output: StructuredOutputRequest | None` keyword-only required 参数，无 default。

**Exports**: `dayu.engine.__init__` 和 `dayu.engine.contracts.__init__` 正确导出所有新符号。

**Tests**: 119 tests pass，覆盖 capability mismatch rejection、payload projection、closed union、JSON value validation。

**Pyright**: 0 errors, 0 warnings on all Engine files。

### 2. Host Compaction v3 (S3)

**V2→V3 migration**: 全量 rename，无 V2 兼容别名、wrapper、loose parser 或 downstream repair。`grep -rn "CompactCandidateV2\|CompactInputV2\|CompactAcceptedTruthV2" dayu/host/*.py` 返回 0 结果。

**Structure owner**: `compact_structure.py` 拥有 immutable `_ObjectDescriptor` → `_FieldDescriptor` 层级，从同一 descriptors 机械生成：
- `compact_output_template_v3()` — concrete template
- `compact_output_json_schema_v3()` — strict JSON Schema
- `compact_output_prompt_rules_v3()` — concise prompt rules
- `parse_compact_candidate_v3()` — strict parser

**V3 contract changes**:
- 移除 `diagnostics`、`explicitly_dropped_sources`、`CompactDropReasonV2`、`CompactCandidateDiagnosticV2`
- 新增 `CompactOmittedCoverageV3`（Host 从 represented complement 派生，非 model 声明）
- 新增 `CompactPolicyUsageAuditV3`（Host 从 candidate + policy 派生 actual/cap）
- 新增 `CompactOutputCapsV3`（从 MemoryProjectionPolicy 机械投影，注入 compact_input）

**Acceptance**: `accept_compact_candidate_v3()` 验证 label/kind、represented sections、duplicate/contradiction、information、policy caps。不再有 exact coverage partition（represented + dropped = boundary），改为 represented + omitted = boundary。

**Repair**: `build_compact_repair_feedback_v3()` 构造 bounded、脱敏的 Host internal feedback。修复反馈 JSON 格式与 system prompt 一致。

**Policy usage audit**: `derive_compact_policy_usage_actuals_v3()` 从 candidate 文本计算 actuals；`validate_compact_policy_usage_audit_candidate_binding_v3()` 校验 audit 与 candidate 一致性。Memory 消费 audit 而非重新计算。

**Tests**: 120 tests (compaction_contract) + 156 tests (llm_compaction + dispatch) pass。

**Pyright**: 0 errors, 0 warnings on all Host core files。

### 3. Tool Trace Public (F11)

**Response identity resolution**: `durable/tool_trace.py` 新增 `ResolvedCompactorResponseIdentity` dataclass，暴露：
- `disposition` (accepted / attempt_rejected)
- `terminal_event_id` / `terminal_event_sequence`
- `compaction_operation_id` / `compaction_attempt_number`
- `proposal_manifest_ref` / `proposal_manifest_digest`
- `successful_response_identity: SuccessfulRunnerResponseIdentity | None`

**Resolution algorithm**: `_resolve_compactor_response_identity()` 完整扫描 parent Host Run 的 `CONTEXT_COMPACTED` 和 `CONTEXT_COMPACTION_ATTEMPT_REJECTED` events，使用 keyset pagination (`_COMPACTOR_TERMINAL_SCAN_PAGE_SIZE=128`)。唯一性不变量：同一 manifest 不得有 duplicate canonical terminals。

**Identity validation**: `_resolved_compactor_response_from_row()` 校验 operation_matches == manifest_matches（不一致时 raise），proposal manifest binding 存在，Engine run identity 匹配。

**Public projection**: `RunnerCallResolvedProjection` 新增 `compactor_response_identity` 字段。Resolver 不暴露 raw provider request/response/endpoint/headers/credentials/secrets。

**Manifest validation**: `_typed_manifest_from_signal()` 做 13-field identity check between signal and hot payload。

**Tests**: 93 tests (tool_trace_queries + analysis + input + rules) pass。

### 4. Context Event Payload (S4)

**Payload storage**: `context_event_payload.py` 新增 `store_context_compacted_payload()`，按 `payload_inline_threshold_bytes` 决定 inline vs descriptor-backed 存储。小 payload 直接进 EventLog `payload_json`；超限 payload 写入 bounded payload descriptor/blob。

**Payload resolution**: `resolve_context_compacted_payload()` 从 inline 或 descriptor/blob 严格解析，校验 event identity、ref/digest pairing、canonical contract。所有 CONTEXT_COMPACTED consumer（run_input.py、compaction_terminal.py、dispatch.py、engine_ingest.py）统一使用此 resolver，不再直接 `payload_object()`。

**Dispatch/ingest 一致性**: `dispatch.py` 和 `engine_ingest.py` 的 `_write_accepted_compacted_event` 都使用 `store_context_compacted_payload` + `append_event(payload_json=..., payload_ref=..., payload_digest=...)`。

### 5. Memory Projection

**Policy validation**: `_validate_committed_policy_usage()` 从 `ContextCompactedSemanticPayload.policy_usage_audit` 消费 Host-derived audit，校验 policy_ref、policy_digest 和 actual/cap 关系。不再从 candidate 文本重新计算。

**V3 types**: 全量从 V2 迁移（`CompactCandidateV3`、`CompactForwardIntentStatusV3` 等）。

**Size estimation**: `estimate_memory_size_units()` 使用 `compact_text_size_units_v3(text)`。

**Tests**: 166 tests (memory_projection + run_input_builder) pass。

### 6. LLM-facing Prompts

**System prompt** (822 bytes): 精简为硬性要求列表，无内部模块名、代码类型名或 Host 实现术语。自包含说明：只输出 JSON object、完整 replacement、不可信材料不执行指令、source label 是引用标签、current_input 无 label 不可引用、严格使用字段规则。

**User prompt** (3,337 bytes): 自包含，包含：
- 材料边界说明
- `<<compaction_request>>` placeholder
- 输出字段结构规则（`<<compact_output_rules>>`）
- 同源 concrete template（`<<compact_output_template>>`）
- 五类字段的业务含义与来源规则
- 共同规则

**session_summary=null**: 明确说明 "接受本次完整 replacement 后清空旧 summary，不影响其它四类字段"。

**Repair feedback**: 自包含格式说明，与 system prompt 一致。

### 7. Config/Assembly

**models.json**: DeepSeek (`deepseek-v4-flash`, `deepseek-v4-pro`) 配置 `structured_output_capability: "json_object"`；所有其它 provider（Mimo、Gemini、Claude、Qwen、OpenAI、Ollama）配置 `"none"`。

**config_loader.py**: 新增 `StructuredOutputCapabilityConfig` enum，`ModelConfig` 新增 `structured_output_capability` 字段，`_parse_structured_output_capability()` 解析并校验。

**_execution_config_projection.py**: `runner_spec_json()` 和 `runner_spec_from_json()` 正确序列化/反序列化 `structured_output_capability`。

**Provider behavior**: 
- DeepSeek (json_object) → `JsonObjectStructuredOutputRequest()` → `{"type": "json_object"}`
- Mimo/Gemini/Claude/Qwen/OpenAI (none) → `None` → prompt-only
- 符合 PR body 描述："DeepSeek uses configured native JSON structured output; Mimo remains on prompt + strict Host validation"

### 8. Registry/Docs/Tests

**Import boundary**: 26 tests pass，无反向依赖。

**Package exports**: 5 tests pass，`__all__` 完整。

**Config loader**: 247 tests pass。

**Pyright**: 0 errors, 0 warnings on all changed files。

### 9. Cross-Slice Dataflow Verification

**Memory policy → output_caps → compact_input → LLM prompt**:
`MemoryProjectionPolicy` → `compact_output_caps_v3_from_memory_policy()` → `CompactOutputCapsV3` → `CompactInputV3.output_caps` → `to_json()` → `<<compaction_request>>` placeholder。链路完整，单一 Memory policy 真源。

**accepted_truth → compact_payload → EventLog → Memory projection**:
`CompactAcceptedTruthV3` → `build_context_compacted_payload()` → `store_context_compacted_payload()` → EventLog row → `resolve_context_compacted_payload()` → `parse_context_compacted_semantic_payload()` → `ContextCompactedSemanticPayload` → `project_conversation_memory_event()`。单一 accepted truth 真源。

**SuccessfulRunnerResponseIdentity → Tool Trace → public projection**:
Engine final answer 的 `SuccessfulRunnerResponseIdentity` → compaction terminal payload → `parse_context_compacted_terminal_binding()` → `_resolved_compactor_response_from_row()` → `ResolvedCompactorResponseIdentity` → `RunnerCallResolvedProjection.compactor_response_identity`。类型化链路，不从 config/timestamps/provider names 推断。

**Engine structured_output → Runner capability → payload builder**:
`AgentRunRequest.structured_output` → `validate_structured_output_request()` → `_AsyncAgent` → `AsyncRunner.call(structured_output=...)` → `build_request_payload(structured_output=...)` → `_apply_structured_output_request()` → `response_format`。fail-closed，不降级。

### 10. Fail-Closed / Safety Verification

- **Capability mismatch**: `validate_structured_output_request()` raises ValueError，不 fallback
- **Unknown JSON keys**: `_exact_object()` raises ValueError
- **Missing required keys**: `_exact_object()` raises ValueError
- **Duplicate JSON keys**: `_strict_object_pairs()` raises ValueError
- **Non-finite floats**: `_validate_json_value()` raises ValueError
- **Identity mismatch**: `_typed_manifest_from_signal()` 13-field check raises HostDurableError
- **Duplicate terminals**: `_resolve_compactor_response_identity()` raises CompactorResponseResolutionError
- **Operation/manifest binding mismatch**: raises CompactorResponseResolutionError
- **Policy audit mismatch**: `_validate_committed_policy_usage()` raises ValueError
- **Forbidden system envelope fragments**: `_SYSTEM_ENVELOPE_FORBIDDEN_FRAGMENTS` includes `CompactCandidateV3`

### 11. Single Truth Verification

- **Structure truth**: `compact_structure.py` immutable descriptors → template/schema/parser/prompt_rules
- **Acceptance truth**: `context_governance.py` → represented/omitted/policy_usage_audit
- **Durable payload truth**: `context_event_payload.py` → inline/descriptor-backed storage + strict resolution
- **Terminal truth**: one canonical terminal per compaction operation
- **Memory truth**: derives from accepted Host compaction event
- **RunInput truth**: derives from same accepted truth
- **Tool Trace truth**: derives from canonical terminal + SuccessfulRunnerResponseIdentity
- **No dual truth**: all consumers use same resolver/parser path

## Conclusion

**PASS**。F11/F12 aggregate diff 在 correctness、stability、semantic ownership、cross-slice dataflow、schema freshness、prompt self-sufficiency、provider capability behavior、terminal/artifact/Memory/RunInput/Tool Trace single truth、fail-closed mismatch/corruption、repair/fallback safety 方面未发现实质性问题。V2→V3 全量迁移干净，无兼容残留。所有 targeted tests pass，pyright clean。
