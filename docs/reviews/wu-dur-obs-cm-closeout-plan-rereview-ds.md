# Plan Fix Re-review: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01

**Reviewer**: AgentDS (plan fix re-review gate)
**Date**: 2026-06-05
**Fixed plan artifact**: `docs/host/wu-dur-obs-cm-closeout-plan.md`
**Plan fix artifact**: `docs/reviews/wu-dur-obs-cm-closeout-plan-fix-codex.md`
**Controller adjudication**: `docs/reviews/wu-dur-obs-cm-closeout-plan-review-controller-adjudication.md`
**Original review**: `docs/reviews/wu-dur-obs-cm-closeout-plan-review-ds.md`
**Design source**: `docs/host/design.md`
**Control doc**: `docs/host/issues-implementation-control.md`
**Review stance**: plan fix re-review — only verify accepted findings are fixed; do not expand scope.

---

## Verdict: pass

- **Unfixed/partial findings**: 0
- **New blocking findings**: 0
- **Residual risks / open questions**: 3

---

## Accepted Findings Fix Verification

### A1. Slice 0 contract shape too abstract — 已修复

**Original concern**: The plan listed five conceptual areas to write back to `design.md` but did not specify concrete typed field lists, digest canonicalization rules, inline-vs-ref boundary, or projector metadata semantics.

**Fix verification**:

The fixed plan adds a consolidated contract appendix (lines 226-377) with six typed contract tables:

| Contract | Lines | Has field name | Has type | Has requiredness | Has semantics | Has digest/ref boundary | Has validation rule |
|---|---|---|---|---|---|---|---|
| `RunnerCallInputAssemblyManifest` | 246-272 | yes | yes | yes | yes | yes | yes |
| `RunnerCallMessageEntry` | 278-293 | yes | yes | yes | yes | yes | yes |
| `ProjectorMetadata` | 295-304 | yes | yes | yes | yes | yes | yes |
| `ToolCallArgumentsAtom` | 306-323 | yes | yes | yes | yes | yes | yes |
| Tool Trace signal contract | 329-343 | yes | yes | yes | yes | yes | yes |
| `RunnerCallReconstructionDiagnostic` | 347-358 | yes | yes | yes | yes | yes | yes |

Each of the four original gaps is addressed:
- **Consolidated field list**: no longer scattered across sections; each contract is a self-contained table.
- **Payload descriptor vs inline boundary**: defined as `arguments_storage_kind: "inline_json" | "payload_descriptor"`, threshold references `payload_inline_threshold_bytes` from design.md §13.1 (line 240 of plan; verified against design.md lines 1435-1444).
- **Projector metadata schema**: `ProjectorMetadata` table (lines 295-304) defines `projector_id` as "closed string enum", not a raw Python module path.
- **Role sequence digest algorithm**: defined at line 262 as `computed from canonical UTF-8 string role0\nrole1\n... over allowed roles`.

**Verdict**: 已修复.

---

### A2. inline-vs-ref and storage-form decisions unresolved — 已修复

**Original concern**: Arguments storage and runner-call manifest storage form were not decided, leaving divergent truth boundaries to implementation.

**Fix verification**:

1. **Tool-call arguments storage**: `ToolCallArgumentsAtom` table (lines 306-323) defines `arguments_storage_kind` as `"inline_json" | "payload_descriptor"`, with threshold from `payload_inline_threshold_bytes`. `arguments_inline_json` and `arguments_payload_ref` are mutually exclusive conditional fields.

2. **Runner-call manifest storage form**: Lines 236-244 define a composite form:
   - Canonical event `RUNNER_CALL_INPUT_ASSEMBLED` as audit/reconstruction event with no Run/Attempt state side effect.
   - Manifest body stored via payload descriptor kind `runner_call_input_manifest`, with the same `payload_inline_threshold_bytes` threshold.
   - Full rendered messages only as derived artifact kind `runner_call_projection_artifact`.

3. **Payload descriptor kinds** explicitly named at lines 240-241: `tool_call_arguments_json`, `tool_call_semantic_query_text`, `runner_call_input_manifest`, `runner_call_projection_artifact`, `compactor_input_projection`.

4. **Run state truth boundary**: Line 243 explicitly states manifest "不得作为 canonical event hot payload" for full messages; lines 243-244 declare the manifest "is not Run state truth and must not drive recovery, memory projection or lifecycle transitions."

**Verdict**: 已修复.

---

### A3. limited-signal / mismatch diagnostic shape undefined — 已修复

**Original concern**: WU-OBS-P00, F02, and F01 all rely on limited-signal as fallback but had no shared typed shape.

**Fix verification**:

1. `RunnerCallReconstructionDiagnostic` (lines 347-358) is a fully typed contract with:
   - `status`: `"complete" | "limited_signal" | "mismatch"` (closed enum, line 349)
   - `reason`: `DiagnosticReason` (conditional, line 350)
   - `missing_atom_kind`: closed string enum (line 351)
   - `missing_ref_kind`: closed string enum (line 352)
   - `observed_count` / `expected_count`: for count mismatch (lines 354-355)
   - `observed_digest` / `expected_digest`: for digest mismatch (lines 356-357)
   - `consumer_boundary`: `"tool_trace_query" | "analyzer_fixture" | "compact_evidence_projection" | "public_smoke"` (line 358)

2. `DiagnosticReason` closed enum (line 360) has 13 values covering all known failure modes: `missing_runner_call_manifest`, `missing_projection_artifact`, `missing_tool_call_arguments_atom`, `missing_semantic_query_atom`, `missing_compactor_manifest`, `missing_memory_snapshot_body`, `unsupported_projector_version`, `message_count_mismatch`, `role_sequence_digest_mismatch`, `input_projection_digest_mismatch`, `payload_digest_mismatch`, `unresolvable_ref`, `provider_specific_atom_deferred`.

3. Slice 4 (lines 528) and Slice 5 (lines 557) both reference consuming this typed shape.

**Verdict**: 已修复.

---

### A4. runner_call_kind incomplete and overlapping — 已修复

**Original concern**: The original 5-value enum (`ordinary_agent`, `tool_loop_continuation`, `forced_answer`, `length_continuation`, `context_compaction`) was missing retry/replay/resume/initial-vs-followup distinctions, and had overlap between `tool_loop_continuation` and `forced_answer`.

**Fix verification**:

1. The fixed plan separates classification into two orthogonal dimensions:
   - `RunnerCallKind` (line 274): `initial_user_dispatch`, `followup_user_dispatch`, `tool_result_continuation`, `post_compaction_dispatch`, `compactor_proposal` — 5 non-overlapping business kinds.
   - `RunnerCallTriggerReason` (line 276): `initial_user_input`, `followup_user_input`, `tool_results_available`, `force_answer_after_tool_limit`, `finish_reason_length_continuation`, `host_retry`, `host_replay`, `host_resume`, `context_compaction_completed`, `context_compaction_repair_attempt`, `context_compaction_retry_attempt` — 11 trigger reasons.

2. Coverage check:
   - **tool-call roundtrip**: `tool_result_continuation` + `tool_results_available` ✓
   - **compact 后 follow-up**: `post_compaction_dispatch` + `context_compaction_completed` ✓
   - **compactor internal**: `compactor_proposal` + compaction trigger reasons ✓
   - **retry/replay/resume**: `host_retry`, `host_replay`, `host_resume` as trigger reasons ✓
   - **forced answer**: `force_answer_after_tool_limit` as trigger reason ✓
   - **length continuation**: `finish_reason_length_continuation` as trigger reason ✓

3. The original overlap problem is resolved: `forced_answer` is now a trigger reason, not a kind. A call that is both a tool_loop_continuation and forced-answer would have kind=`tool_result_continuation`, trigger=`force_answer_after_tool_limit` — unambiguous.

4. The naming concern (original DS B2 item 4) is addressed: `length_continuation` renamed to `finish_reason_length_continuation` as trigger reason; the kind `tool_result_continuation` uses business semantics.

**Verdict**: 已修复.

---

### A5. Compactor internal runner-call identity ambiguous — 已修复

**Original concern**: The plan said "parented to session/run and compaction operation id" without clarifying which `run_id` is parent vs self.

**Fix verification**:

1. `CompactorRunnerCallIdentity` table (lines 362-374) explicitly separates:
   - `parent_host_run_id`: Host admitted user Run (must equal manifest `host_run_id`)
   - `parent_session_id`: parent Session (must equal manifest `session_id`)
   - `compaction_operation_id`: Host context governance operation id
   - `compactor_engine_run_id`: self Engine/runner id for the compactor proposal call, explicitly noted "must not be treated as Host admitted user Run id"

2. Additional identity fields: `compaction_attempt_number`, `compaction_request_digest`, `compactor_input_projection_ref`.

3. Relationship to `CONTEXT_COMPACTED` clarified at lines 376-377: "Accepted compact events reference the accepted proposal manifest; rejected attempts reference their manifest through typed diagnostics. Neither path turns rejected proposal content into memory or compact truth."

4. `accepted_context_compacted_event_ref` and `rejected_attempt_diagnostic_ref` provide the bidirectional links between compactor manifest and compact events.

**Verdict**: 已修复.

---

### A6. WU-CM-01-F02 motivation overstated — 已修复

**Original concern**: The plan framed the problem as complete tool identity loss, but `EvidenceReadableItem.tool_name` is already a required field in design.md (line 2659).

**Fix verification**:

1. Goal #3 (line 19) now reads: "改善 compact evidence material 的 `query_text`。`EvidenceReadableItem.tool_name` 在设计中已存在；真实缺口是 `query_text` 缺少 durable arguments / semantic query 的业务可读表达，不能把问题表述成完全缺失 tool identity."

2. Success signal F02 (line 37): "`evidence_material[*].tool_name` 继续承担工具身份；`query_text` 不再退化为裸 `tool_call_id=...`，而是来自 durable arguments 或 optional semantic query."

3. Slice 5 (line 556): "渲染 bounded business-readable query：优先 `semantic_query_text`，否则 `tool_name` + normalized arguments JSON。`tool_name` 已由 `EvidenceReadableItem.tool_name` 承担身份，query_text 的职责是补足 arguments / semantic query."

4. Verified against design.md lines 2657-2662: `EvidenceReadableItem.tool_name: str` is indeed required, `query_text?: str` is optional. The fix accurately narrows scope.

**Verdict**: 已修复.

---

### A7. Slice 0 design review sub-gate missing — 已修复

**Original concern**: Only the plan review validated Slice 0 sufficiency, but Slice 0 produces actual `design.md` changes that no one reviews before Slice 1-7 dispatch.

**Fix verification**:

1. Slice 0.5 (lines 407-424) defines an explicit design review sub-gate:
   - Artifact path: `docs/reviews/wu-dur-obs-cm-closeout-design-review.md`
   - Review owner: phaseflow 总控派发的 design reviewer
   - 6 concrete acceptance criteria (lines 416-422)
   - Stop condition: "该 artifact 未给出 pass / accepted verdict 前，Slice 1-7 不得派发；若 review 判定需要超出 design.md 当前原则的新架构决策，本 work unit group 标记 blocked"

2. The acceptance criteria cover: contract shape equivalence, inline-vs-ref clarity, kind/trigger coverage, compactor identity, Engine vs Host ownership, and LLM-facing boundary.

3. This sub-gate effectively prevents un-reviewed code slices from being dispatched.

**Verdict**: 已修复.

---

## Specific Cross-checks

### Consolidated contract appendix completeness

All six contract tables include the five required columns: field name, type, requiredness, business/Host semantics, digest/ref boundary, and validation rule. No field is missing any of these dimensions.

### Inline/ref threshold

Defined at lines 240-241 and 315-317: the threshold reuses `payload_inline_threshold_bytes` from design.md §13.1. Below threshold → `inline_json`; above threshold → `payload_descriptor` with descriptor kind `tool_call_arguments_json`. The plan correctly references the existing design.md policy rather than re-deriving it.

### Payload descriptor kind

Five kinds explicitly named at lines 240-241: `tool_call_arguments_json`, `tool_call_semantic_query_text`, `runner_call_input_manifest`, `runner_call_projection_artifact`, `compactor_input_projection`. Each appears in the relevant contract table.

### Runner-call manifest storage form

Lines 236-244 define the composite form: canonical event `RUNNER_CALL_INPUT_ASSEMBLED` (with hot payload for identity/status only) + payload descriptor/artifact for manifest body + optional derived artifact for full rendered messages. The `RUNNER_CALL_INPUT_ASSEMBLED` hot payload fields are enumerated at line 244. Run state non-truth boundary is explicit.

### Limited-signal/mismatch diagnostic shape typed

`RunnerCallReconstructionDiagnostic` (lines 347-358) is a fully typed contract. `DiagnosticReason` (line 360) is a closed enum with 13 values. Both `status` and `consumer_boundary` are closed enums. No free-text or `Any` fields.

### Runner call classification

`RunnerCallKind` (5 values) and `RunnerCallTriggerReason` (11 values) are semantically disjoint. The original overlap (tool_loop_continuation vs forced_answer) is resolved by moving forced-answer to trigger reason. Coverage includes all paths from the original motivation: tool-call roundtrip, compact follow-up, compactor internal, plus retry/replay/resume, forced answer, and length continuation.

### Compactor parent/self identity

`CompactorRunnerCallIdentity` (lines 362-374) explicitly separates `parent_host_run_id` (parent user Run) from `compactor_engine_run_id` (self compactor Engine run). Relationship to `CONTEXT_COMPACTED` clarified at lines 376-377.

### F02 motivation narrowed

Goal #3, success signal F02, and Slice 5 all correctly frame the gap as arguments/semantic query rather than total tool identity loss. `EvidenceReadableItem.tool_name` is acknowledged as already present.

### Slice 0.5 gate

Slice 0.5 (lines 407-424) has artifact path, review owner, 6 acceptance criteria, and a hard stop condition blocking Slice 1-7 dispatch. The acceptance criteria are concrete and verifiable.

---

## New Findings

No new blocking findings. The fix did not introduce any blocking risks beyond those already covered by the residual risks section and the Slice 0.5 design review gate.

---

## Residual Risks / Open Questions

### RR1. `RunnerCallTriggerReason` compatibility matrix not specified

The plan defines 5 kinds and 11 trigger reasons but does not specify which trigger reasons are valid for each kind. The validation rule on `runner_call_trigger_reason` (line 258) says "value must be compatible with `runner_call_kind`" but the compatibility rules are not enumerated. Example: is `host_resume` compatible with `compactor_proposal`? Is `force_answer_after_tool_limit` compatible with `initial_user_dispatch`?

**Risk**: Implementation may invent different compatibility rules for different slices.
**Mitigation**: Slice 0.5 acceptance criteria include verifying "RunnerCallKind / trigger reason classification 覆盖...且无语义重叠." The design reviewer should request the compatibility matrix if needed.
**Severity**: low — can be resolved during Slice 0 design writeback.

### RR2. Provider-specific tool_calls / reasoning_content decision deferred to Slice 0.5

Lines 291-293 define `provider_tool_calls_digest` and `reasoning_content_digest` as optional/nullable, with the decision about whether typed Engine contracts exist deferred to Slice 0.5 design review. If the design reviewer cannot determine the current Engine contract state, these fields may remain in limbo.

**Risk**: Slice 2 implementation may need these fields but the design review may not have the implementation knowledge to decide.
**Mitigation**: The contract already defines the fallback — if no typed Engine contract exists, the fields are absent and a `provider_specific_atom_deferred` diagnostic reason is available. This is a clean deferral, not a gap.
**Severity**: low.

### RR3. Chunked evidence behavior described but not contract-level

Line 558 defines chunking behavior: "同一个 tool_call_requested_event_ref 被切成 E1.1 / E1.2 等 evidence chunks 时，各 chunk 使用同一个 base query_text." This is a behavioral description in Slice 5, not a contract field in the appendix. The `EvidenceReadableItem` in design.md does not currently model chunk identity.

**Risk**: Chunk identity and query_text deduplication may be implemented inconsistently.
**Mitigation**: The scope is within a single function (`_readable_query_text()`) and Slice 5 has a focused chunking test. The risk is contained.
**Severity**: low.

---

## Completion Report

- **Artifact path**: `docs/reviews/wu-dur-obs-cm-closeout-plan-rereview-ds.md`
- **Verdict**: pass
- **Unfixed/partial findings**: 0
- **New blocking findings**: 0
- **Residual risks**: 3 (all low severity, mitigated by Slice 0.5 design review gate)

The fixed plan is code-generation-ready. All seven accepted findings (A1-A7) are fully fixed. The consolidated contract appendix provides concrete typed shapes that implementation can code against without inventing field names, types, digest algorithms, or ref boundaries. The Slice 0.5 design review sub-gate provides a hard checkpoint between design writeback and code implementation. The three residual risks are all low-severity and can be resolved during Slice 0/Slice 0.5 without plan amendment.
