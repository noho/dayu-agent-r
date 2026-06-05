# Adversarial Plan Review: WU-DUR-P01 / WU-OBS-P00 / WU-CM-01-F02 / WU-CM-01-F01

**Reviewer**: AgentDS (planreview gate)
**Date**: 2026-06-05
**Plan artifact**: `docs/host/wu-dur-obs-cm-closeout-plan.md`
**Design source**: `docs/host/design.md`
**Control doc**: `docs/host/issues-implementation-control.md`
**Review stance**: adversarial plan review

---

## Verdict: pass-with-findings

- **Blocking findings**: 5
- **Non-blocking findings**: 7
- **Residual risks / open questions**: 4

---

## Blocking Findings

### B1. Slice 0 design contract writeback lacks concrete contract shape

**Severity**: blocking
**Expected ruling**: accepted (with mandatory amendment before implementation dispatch)

**Evidence**:

Plan Slice 0 (line 228-250) lists five conceptual areas to write back to `design.md`:

1. runner-call input manifest contract in EventLog / canonical event matrix
2. `TOOL_CALL_REQUESTED` payload contract extension (arguments ref/digest + semantic query atom)
3. RunInputBuilder manifest fields, source refs, role sequence digest, projector metadata
4. compactor internal runner call manifest in Context Governance / compact chapter
5. Tool Trace signal contract

But the plan does **not** specify:

- The **typed field list** for each new contract. For example, the plan says `RunnerCallInputAssemblyManifest` should include `runner_call_index`, `runner_call_kind`, `message_count`, `message_role_sequence_digest`, etc. — but these are listed across multiple sections (line 158-162, 197-199, 203-205), not consolidated into a single contract shape.
- The **payload descriptor vs inline boundary** for arguments: when does `arguments_payload_ref` apply vs inline? The plan says "大 arguments 走 payload descriptor" (line 272) but doesn't define "大" in terms of `payload_inline_threshold_bytes` or any other typed policy. Design.md line 1437-1442 already defines the inline threshold mechanism — Slice 0 must explicitly reference this existing policy, not re-derive it.
- The **projector metadata schema**: plan says `projector_id`, `schema_version`, `projector_digest` but doesn't specify whether `projector_id` is a human-readable string, a module path (which would violate AGENTS.md LLM-facing constraints), or a typed enum.
- The **role sequence digest algorithm**: plan mentions `message_role_sequence_digest` repeatedly but never defines the canonicalization rule (e.g., `sha256("system|user|assistant|tool|assistant")` or per-message digest chain). Without this, different projectors could produce different digests for the same logical message sequence.

**Why blocking**: Slice 0 is the **only** design gate before 7 implementation slices. If the contract written to `design.md` is underspecified, each implementation slice will make independent decisions about field names, digest algorithms, and payload boundaries — creating exactly the kind of "同源缺口" (same-origin gap) the plan aims to close. The plan itself says "plan review 必须裁决 design contract 足够具体" (line 250) — this review cannot confirm sufficiency without a concrete contract shape.

**Suggested fix**: Before implementation dispatch, amend Slice 0 to include a concrete contract appendix in the plan (or write it directly to design.md and reference it here). At minimum, specify:
- The exact typed field list for `RunnerCallInputAssemblyManifest` (not scattered across sections)
- The digest canonicalization rule for role sequence
- The inline-vs-ref threshold for tool arguments, referencing design.md §13.1
- The projector metadata field semantics (what each field means, not just its name)

---

### B2. `runner_call_kind` enumeration has semantic gaps and overlap

**Severity**: blocking
**Expected ruling**: accepted (must resolve before implementation)

**Evidence**:

Plan line 159 defines `runner_call_kind` values:
```text
ordinary_agent, tool_loop_continuation, forced_answer, length_continuation, context_compaction
```

Problems:

1. **Missing kinds**: The plan's own motivation section (line 35) says three paths must be covered: "tool-call roundtrip、compact 后 follow-up、Host-owned compactor internal runner call." But `runner_call_kind` doesn't distinguish:
   - `initial_run` vs `followup_run` (both would be `ordinary_agent`)
   - `retry` / `replay` runner calls (WU-DUR-P01 control doc line 732 mentions retry/replay)
   - `resume` runner calls from `WAITING`/`RECOVERING`

2. **Overlap between `tool_loop_continuation` and `forced_answer`**: Are these disjoint? A forced answer after tool loop is still a "continuation." The kind should clarify whether these are mutually exclusive or composable (e.g., a single runner call can be both `tool_loop_continuation` and trigger `forced_answer`).

3. **`forced_answer` is a provider/Runner concern, not a Host semantic**: `finish_reason=length` triggers continuation; `forced_answer` is not a standard Engine event type. The plan references it without defining what Host event produces it.

4. **`length_continuation` naming**: The design.md uses `finish_reason=length` as Engine terminology. Host-facing contracts should use business semantics, not Engine internal constants. Compare: `context_compaction` is a business term; `length_continuation` is an Engine implementation detail projected to Host.

**Why blocking**: An incomplete or overlapping kind enum means the manifest can't reliably answer "what kind of runner call was this?" — which is the primary purpose of the manifest. If the kind is wrong, the manifest is wrong.

**Suggested fix**: Define `runner_call_kind` as a closed enum grounded in Host business semantics, not Engine event names. Map each kind to the Host event(s) that trigger it. Ensure the three required paths (tool-call roundtrip, compact follow-up, compactor internal) and all continuation variants are covered without overlap.

---

### B3. Compactor internal runner call `run_id` semantics are ambiguous

**Severity**: blocking
**Expected ruling**: accepted (must clarify in Slice 0 design writeback)

**Evidence**:

Plan line 203-205:
> Treat compactor proposal call as `runner_call_kind=context_compaction`, parented to session/run and compaction operation id, not as a Host admitted user Run.

But control doc WU-DUR-P01 evidence (line 718) shows:
> Engine log 中 `context-compactor:vnext` run `context-compactor-vnext-10e0d9ae533d4673a430cedddac55b5d`

The Engine **creates a real run** for the compactor (it has a `run_id`). The plan says this is "not a Host admitted user Run" — which is correct at the Host admission layer. But the manifest must record:
- The **Engine-level `run_id`** (used to locate the Engine call)
- The **parent Host `run_id`** (for traceability to the user Run that triggered compaction)
- The **compaction operation id** (for linking to `CONTEXT_COMPACTION_REQUESTED` / `CONTEXT_COMPACTED`)

The plan says "parented to session/run and compaction operation id" but doesn't clarify which `run_id` is the parent and which is the self id in the manifest. This ambiguity will cause implementation drift between Slice 2 (runner-call manifest) and Slice 3 (compactor internal call manifest).

Additionally, design.md does not currently model the compactor Engine run as a first-class concept. The Context Governance section (line 2860-2909) describes compaction as an orchestration concern but doesn't define the compactor's own runner call identity in the EventLog / canonical event matrix. Slice 0 must add this.

**Why blocking**: If the manifest can't unambiguously link a compactor runner call to its parent user Run, the analyzer (WU-OBS-P00) can't trace compaction provenance, and the manifest fails its primary purpose.

**Suggested fix**: In Slice 0, define a `CompactorRunnerCallIdentity` with explicit `compactor_engine_run_id`, `parent_host_run_id`, and `compaction_operation_id` fields. Add this to the design.md Context Governance chapter as a stable contract.

---

### B4. `EvidenceReadableItem.query_text` design.md contract already has `tool_name` — plan overstates the gap

**Severity**: blocking
**Expected ruling**: accepted (narrow the scope claim in plan)

**Evidence**:

Design.md line 2657-2662 defines:
```text
EvidenceReadableItem
  source_label: PromptLocalLabel
  tool_name: str          # <-- REQUIRED, not optional
  query_text?: str        # <-- optional
  response_text: str
  source_note?: str
```

The plan (line 38, 208-212, 381-395) repeatedly frames the problem as `query_text` degrading to `tool_call_id=...`, implying the LLM has no tool context. But `tool_name` is **already required** in the LLM-facing material. The LLM already knows *which tool was called*.

The actual gap is narrower: the LLM doesn't know the **arguments** (what parameters the tool was called with), which could help it understand *why* the tool returned specific results. The plan's own code evidence (`_readable_query_text()` at compaction_evidence.py:264) confirms the current output is `tool_call_id={envelope.tool_call_id}` — but this function outputs to `query_text`, not `tool_name`. The `tool_name` comes from a separate projection path.

The plan should not claim that LLM-facing material is reduced to "just tool_call_id" when `tool_name` is already present. The gap is specifically about **arguments visibility**, not complete tool identity loss.

**Why blocking**: The plan's motivation section is evidence for the total scope of Slice 5. If the gap is narrower than claimed, the scope of Slice 5 should be adjusted accordingly. Overstating the gap risks over-implementation (adding more projection logic than needed) or misdirected test assertions.

**Suggested fix**: Update the plan to clarify that `tool_name` is already present in `EvidenceReadableItem`, and Slice 5 specifically addresses the **arguments** gap in `query_text`. The stop condition (line 395) is still valid — but the motivation text should be precise about what's actually missing.

---

### B5. No verification mechanism for Slice 0 completeness before implementation proceeds

**Severity**: blocking
**Expected ruling**: accepted (add a design review sub-gate)

**Evidence**:

Plan line 250:
> Stop condition：若 design.md 不能容纳该 contract 或出现架构争议，停止进入 implementation。

Plan line 252:
> 无代码测试；plan review 必须裁决 design contract 足够具体。

This means the **only** validation of Slice 0 is this plan review. But:

1. This review evaluates the **plan**, not the **actual design.md changes** (which haven't been written yet).
2. The plan says "Slice 0: Design Contract Writeback" — but the plan itself is the plan, not the writeback. The actual design.md changes will be made by the implementation agent in Slice 0.
3. There is no sub-gate between Slice 0 completion and Slice 1-7 dispatch. If Slice 0 produces an insufficient design.md contract, all 7 implementation slices will build on an unstable foundation.

The control doc (WU-DUR-P01 line 724) reinforces this concern:
> 实施前必须先把 EventLog 补字段的稳定 contract 写回 `docs/host/design.md`

"实施前" implies a verification step between writeback and implementation. The plan doesn't define this step.

**Why blocking**: Without a design review sub-gate after Slice 0, the entire implementation chain rests on an unchecked design contract. This is the single highest-risk architectural decision in the plan.

**Suggested fix**: Add an explicit design review sub-gate after Slice 0: the implementation agent writes design.md changes, then a design reviewer (AgentDS or equivalent) verifies the contract is concrete, consistent, and covers all paths before Slice 1-7 are dispatched. The plan should list concrete acceptance criteria for this sub-gate.

---

## Non-blocking Findings

### N1. Prompt rewrite (Slice 6) is sequenced too late

**Severity**: non-blocking
**Expected ruling**: accepted (consider reordering)

**Evidence**:

Plan Slice 6 (line 397-422) rewrites compactor prompt to remove `Host-owned context compaction`, `ConversationCompactOutputVNext`, `vNext 字段`. This has **zero dependency** on Slices 1-5 (durable atoms, manifest, trace signals). It's a pure text change to `dayu/config/prompts/scenes/conversation_compaction*.md`.

Current prompt evidence:
- `conversation_compaction.md:3`: "你是 Host-owned context compaction 组件" — exposes Host implementation identity
- `conversation_compaction.md:14`: "输出必须完全符合 `ConversationCompactOutputVNext` schema" — exposes Python type name
- `conversation_compaction_user.md:52`: "顶层必须只输出上述 vNext 字段" — exposes migration term

These violate AGENTS.md LLM-facing constraints and the design.md §24.2 hard boundary (line 2582-2594).

**Why non-blocking**: The dependency order is correct (Slice 6 doesn't block earlier slices), but reordering it earlier (e.g., as Slice 1 or parallel to Slice 1) would reduce risk of late discovery that prompt rewrite requires more than text substitution.

**Suggested fix**: Move Slice 6 to Slice 1 (or run it in parallel with Slice 1). If the rewrite reveals that the compactor prompt's internal terminology is more deeply embedded (e.g., in test fixtures, smoke assertions, or compact material assembly), those can be addressed early rather than discovered at the end.

---

### N2. `IterationStartedData` extension: digest fields vs Engine contract boundary

**Severity**: non-blocking
**Expected ruling**: accepted (note in implementation)

**Evidence**:

Plan line 158:
> 扩展 Engine `IterationStartedData` 以包含 runner-call identity 与轻量校验字段

Current `IterationStartedData` (engine_events.py:57-67):
```python
@dataclass(frozen=True, slots=True)
class IterationStartedData:
    iteration_id: str
    iteration_index: int
    message_count: int
```

The plan wants to add `runner_call_index`, `message_role_sequence_digest`, `message_input_manifest_ref`, `input_projection_digest`. But:

1. `IterationStartedData` is emitted by Engine, not Host. Engine doesn't understand Host durable refs, projector metadata, or manifest concepts. Adding Host-semantic fields to an Engine contract violates design.md line 40: "Engine 不读取 Host durable store，不理解 Host policy."
2. The digest computation requires knowing the message serialization format. Engine has the raw messages but doesn't know which projector version Host will use.
3. `message_input_manifest_ref` is a Host durable ref — Engine cannot generate it.

**Suggested approach**: Either (a) Engine emits only the raw data it has (`message_count`, `iteration_id`) and Host computes digests/manifest on the Host side during ingest, or (b) Engine emits a lightweight `runner_call_identity` with only `runner_call_index` and lets Host attach the rest via a separate Host-side event. Option (a) is more consistent with the architecture.

**Why non-blocking**: This can be resolved during Slice 2 implementation by choosing the right contract boundary. The plan's intent is correct; the concern is about which layer owns which fields.

---

### N3. `TOOL_CALL_REQUESTED` existing `semantic_input_digest` field is not discussed

**Severity**: non-blocking
**Expected ruling**: deferred-with-owner (needs clarification from WU-DUR-P01 implementer)

**Evidence**:

Current `TOOL_CALL_REQUESTED` payload (tool_runtime.py:3268-3284) already includes:
```python
"semantic_input_digest": candidate.idempotency.semantic_input_digest,
```

The plan says (line 161):
> 若引入 semantic query，使用 typed 字段，不使用 extra payload。

But `semantic_input_digest` already exists. The plan doesn't explain:
- What `semantic_input_digest` currently contains (a digest of what?)
- Whether the proposed "semantic query" is the **preimage** of this digest (i.e., we have the digest but not the text)
- Whether the fix is to store the semantic query **text** alongside the digest, or to replace the digest with text

If `semantic_input_digest` is a digest of a semantic query that was never persisted, then the durable atom gap is: we have the digest but lost the preimage. The fix would be to persist the preimage text. The plan should state this explicitly.

**Why non-blocking**: The implementation can resolve this by reading the `semantic_input_digest` computation path. But the plan should acknowledge the existing field and state whether it's being extended or replaced.

---

### N4. Manifest "不内联完整 messages" constraint needs a positive test

**Severity**: non-blocking
**Expected ruling**: accepted (add test case in Slice 2)

**Evidence**:

Plan invariants (line 199, 301):
> Manifest 不内联完整 messages。

This is a critical constraint — if violated, EventLog becomes a messages dump store (the exact anti-pattern the plan condemns). But the plan's test list for Slice 2 (line 306-309) doesn't include a focused test that **asserts manifest payload size is bounded** or that **manifest does not contain full message text**.

The tests listed are:
- `test_engine_event_contract.py`
- `test_agent_phase3_tool_call.py`
- `test_engine_ingest_mapping.py`
- `test_run_input_builder.py`

None of these explicitly test "manifest payload does not exceed N bytes" or "manifest fields do not include raw message content."

**Suggested fix**: Add a focused test in Slice 2 that asserts the manifest payload size is bounded (e.g., < 4KB for any single manifest) and that message text is not inlined.

---

### N5. WU-OBS-P00 "signal contract" deliverable is vague

**Severity**: non-blocking
**Expected ruling**: accepted (clarify deliverable format)

**Evidence**:

Plan Goal #2 (line 18):
> WU-OBS-P00：定义 Runner call input reconstruction signals

Control doc WU-OBS-P00 target (line 782):
> 定义 Tool Trace analyzer 所需的 runner-call input reconstruction signal contract。

But neither the plan nor the control doc specifies whether this signal contract is:
- A Python `Protocol` / `typing.Protocol` class
- A dataclass / TypedDict
- A design.md section
- A JSON schema
- A combination of the above

The plan's Slice 4 (Tool Trace Reconstruction Signal Projection, line 342-367) says it will add fields to hot/cold trace projection. But "consuming the signal contract" (Slice 4) is different from "defining the signal contract" (Slice 0 design.md writeback). The plan should clarify which slice produces the contract and in what form.

**Suggested fix**: Specify that the signal contract is defined in design.md (Slice 0) as a typed schema, and Slice 4 implements the projection that populates those fields. The contract should include field names, types, nullability, and digest semantics.

---

### N6. Test coverage for `_readable_query_text()` chunking behavior is underspecified

**Severity**: non-blocking
**Expected ruling**: accepted (add test specification)

**Evidence**:

Plan line 380:
> 增加 chunking 同源测试，确保 `E1.1` / `E1.2` query text 稳定且不过度重复。

But the plan doesn't define:
- What "稳定" means — same query_text for all chunks of the same tool result? Or different?
- What "不过度重复" means — max character count? Max repetition ratio?
- Whether chunk query_text should include chunk-specific context (e.g., "part 1 of 3") or be identical

The control doc WU-CM-01-F02 (line 504) adds:
> 同一 tool result 被切成 `E1.1`、`E1.2` 等 evidence chunks 时，各 chunk 的 query text 应保持同源、稳定、简洁，不因 chunk 数量重复注入大段参数文本。

This is more specific but still doesn't define "稳定" operationally.

**Suggested fix**: Define the expected chunking behavior in the test specification: e.g., "all chunks from the same tool call MUST have identical query_text" or "chunks MAY append chunk index but MUST NOT repeat the full arguments JSON."

---

### N7. Fresh schema only — no migration path for existing smoke DB files

**Severity**: non-blocking
**Expected ruling**: deferred-with-owner (smoke test owner)

**Evidence**:

Plan line 166-168:
> Fresh schema only. Add columns or payload descriptor kinds for runner-call manifest refs/digests and tool-call arguments payload refs as needed.
> No compatibility read path for old DB. Tests create fresh schema.

Smoke tests (e.g., `utils/smoke_host_public_conversation_memory.py`) may create durable DB files at configured paths. If those paths already contain old-schema DBs from previous runs, the fresh schema approach could fail on open. The plan doesn't mention whether smoke scripts need to be updated to clean up old DBs or use unique paths.

**Why non-blocking**: This is a test hygiene concern, not an architecture concern. Smoke scripts typically use temporary directories. But if any smoke persists DBs across runs, it will break.

**Suggested fix**: In Slice 7, add a note to verify smoke scripts use `tempfile.mkdtemp()` or equivalent for their workspace paths, or explicitly clean up before running.

---

## Residual Risks / Open Questions

### R1. Provider-specific `assistant tool_calls` projection may need typed extension

Plan line 513: "Provider-specific assistant tool_calls projection 可能涉及 `reasoning_content` / provider state，必须沿 Engine provider contract 做 typed 扩展，不能用 dict bag."

The current `ToolCallRequestedData` (engine_events.py:111-127) already has typed `arguments: Mapping[str, JsonValue]` and `provider_state: ToolCallProviderState | None`. The risk is not about ToolCallRequestedData but about the **assistant message** that contains `tool_calls` — which is projected by Engine, not Host. If different providers serialize `tool_calls` differently, the Host-side durable atom may need provider-specific deserialization. This is correctly identified as a risk but not scoped into any slice. **Recommendation**: Add a note to Slice 2 that if provider-specific tool_calls serialization is discovered during implementation, it should be tracked as a follow-up WU rather than expanding scope.

### R2. Historical memory snapshot cursor unavailability

Control doc WU-DUR-P01 (line 719):
> `host_memory_snapshots` 当前只保留 latest snapshot row；该 smoke 完成后 snapshot cursor 已推进到 269，无法直接读取 round2 dispatch 时 cursor=121 的 historical memory read model。

The plan acknowledges that memory snapshots are ephemeral (latest only) and must be reconstructed from EventLog. But the manifest approach means the manifest records **which cursor was used**, not the snapshot content. If the snapshot content can't be reconstructed (because it requires replaying EventLog through the current projector version), the manifest is correct but not useful for historical verification.

**Recommendation**: This is a known limitation correctly scoped as "limited-signal." The plan should explicitly state that historical memory snapshot reconstruction is out of scope for this work unit group, and that the manifest records the cursor for traceability even when the snapshot content is not recoverable.

### R3. `CONTEXT_COMPACTED` already records compact artifact ref — is the compactor manifest redundant?

Design.md line 2899 says `CONTEXT_COMPACTED` payload must record:
> compact artifact ref, accepted attempt number, accepted candidate digest, prompt-local label mapping refs, source boundary refs, quality check result, budget after compact 与 projection signal.

The plan wants to **additionally** record a `context_compaction` runner-call manifest with system prompt asset digest, user template digest, compaction request projection artifact/digest, etc. Some of these overlap with `CONTEXT_COMPACTED` payload fields.

**Recommendation**: Slice 0 must clarify the relationship: does the compactor manifest **complement** `CONTEXT_COMPACTED` (adding fields the canonical event doesn't have) or **duplicate** it? If complementary, the design.md should show both and explain why they're separate.

### R4. Role sequence digest may differ between Host and Engine views

The plan says `message_role_sequence_digest` should be computed from "actual runner call input" (line 302). But Engine's view of messages (which includes Engine-injected tool results, guidance, etc.) may differ from Host's RunInputBuilder output. If Host computes the digest from RunInputBuilder output and Engine computes it from the actual `messages` list passed to the provider, they could diverge.

**Recommendation**: In Slice 0, specify whether the digest is computed by Host (from RunInputBuilder output) or by Engine (from the actual messages list). If by Engine, the digest field should be in an Engine event, consumed by Host ingest. If by Host, the digest is a projection and may not match the actual provider input 1:1.

---

## Completeness Checklist

| Check | Status | Notes |
|-------|--------|-------|
| Slice 0 design contract writeback sufficiently concrete | FAIL | See B1, B5 |
| Durable tool-call arguments atom typed, verifiable, no extra payload | CONDITIONAL | See B4, N3 |
| Runner-call input assembly manifest covers all paths | CONDITIONAL | See B2, B3 |
| WU-OBS-P00 only defines signal contract, not full analyzer | PASS | Correctly scoped |
| WU-CM-01-F02 depends on durable atoms, not prompt/behavior guessing | PASS | Correctly gated |
| WU-CM-01-F01 verified through public smoke/focused tests | CONDITIONAL | See N4, N7 |
| Tests, pyright, README triggers sufficient | CONDITIONAL | See N4, N6 |
| EventLog not degraded to messages dump store | PASS | Invariants are correct |
| Tool Trace / memory snapshot not reverse-become truth | PASS | Correctly constrained |
| LLM-facing prompt/material doesn't expose internal terms | PASS | Slice 6 addresses this |
| Schema/state/public contract changes written to design.md first | CONDITIONAL | See B1, B5 |

---

## Summary for Controller Adjudication

The plan correctly identifies the root cause (durable atom gaps cause a chain of correctness failures across observability, compact quality, and smoke verification), correctly scopes the work (no full analyzer, no messages dump store, no reverse truth), and correctly sequences by dependency (design -> atoms -> manifest -> trace -> compact -> prompt -> smoke).

Five blocking findings must be resolved before implementation dispatch:
1. **B1**: Slice 0 must specify concrete contract shapes, not just conceptual areas
2. **B2**: `runner_call_kind` enum must be complete and non-overlapping
3. **B3**: Compactor internal runner call `run_id` parent/self semantics must be explicit
4. **B4**: Plan motivation should accurately reflect that `tool_name` is already in LLM-facing material
5. **B5**: A design review sub-gate must be inserted between Slice 0 and Slice 1-7

These are all resolvable through plan amendment — none requires architectural redesign. The plan's core thesis (close the durable-atom-to-smoke correctness chain) is sound.
