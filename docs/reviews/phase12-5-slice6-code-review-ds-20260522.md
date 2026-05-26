# Phase 12.5 Slice 6 Code Review: RunInputBuilder Rendering And Compaction Request Wiring

- **Review type**: adversarial contract review (smoke / adversarial / correctness / stability / maintainability)
- **Reviewed scope**: uncommitted workspace changes against HEAD=1f37435
- **Design source of truth**: `docs/host/design.md`
- **Control document**: `docs/host/implementation-control.md`
- **Plan**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- **Review date**: 2026-05-22
- **Reviewer**: DS (DeepReview Agent)

---

## Summary

Slice 6 does three things correctly at the structural level: (1) it replaces digest-only fact rendering with `claim_text` + `evidence_refs`, (2) it injects minimum preserve continuity block at the correct position, and (3) it wires evidence envelope reads into both proactive and reactive CompactionRequest construction paths. The review found 1 critical duplication issue, 3 high-severity findings, 3 medium findings, and 2 low findings. No findings are correctness-blocking for the slice contract, but the critical duplication should be resolved before merging.

---

## Finding 1 [CRITICAL] — Identical Code Duplicated in `dispatch.py` and `engine_ingest.py`

**Files**: `dayu/host/dispatch.py:289–388`, `dayu/host/engine_ingest.py:366–484`

**Evidence**: The following five private constructs are identically copy-pasted between both modules:

| Construct | dispatch.py lines | engine_ingest.py lines |
|---|---|---|
| `_PAYLOAD_FIELD_*` constants (5 fields) | 185–191 | 210–214 |
| `_CompactionRequestEvidenceInputs` dataclass | 293–302 | 366–375 |
| `_compaction_request_evidence_inputs()` | 3240–3288 | 2988–3036 |
| `_accepted_evidence_envelope_from_event()` | 3291–3316 | 3039–3064 |
| `_evidence_backed_fact_refs_from_compacted_event()` | 3319–3363 | 3067–3111 |
| `_required_text_list()` | 3366–3388 | 3114–3136 |

**Why this matters**: The project's coding constraints require "重复逻辑必须抽取" (duplicated logic must be extracted). Any bug fix or logic change to the bounded EventLog read must be applied identically in two files. Divergence here is a correctness risk: if one path drifts, proactive and reactive compaction requests will carry different evidence inputs, breaking the contract parity required by plan §4.2.

**Fix direction**: Extract the shared constructs into one of:
- `dayu/host/context_events.py` (already imports `AcceptedEvidenceEnvelope` and hosts `CONTEXT_COMPACTED` payload builders), or
- `dayu/host/compaction.py` (already owns `CompactionRequest` and imports `AcceptedEvidenceEnvelope`), or
- a new private module `dayu/host/_compaction_evidence.py`.

Field constants `_PAYLOAD_FIELD_ACCEPTED_EVIDENCE_ENVELOPE`, `_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES`, `_PAYLOAD_FIELD_PRESERVED_FACT_REFS`, `_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_REFS`, `_PAYLOAD_FIELD_CANDIDATE_ID` are also used in `run_input.py` (line 114–117), `memory.py`, and `tool_runtime.py` (line 159). Consolidating them into a single `dayu/host/_compact_payload_fields.py` or adding them to `context_events.py` would reduce the risk of key name drift across modules.

**Severity rationale**: Critical because it violates an explicit project constraint and creates an active divergence risk. The duplicated logic is semantically identical today, but codebases drift.

---

## Finding 2 [HIGH] — `_evidence_backed_fact_refs_from_compacted_event` Returns `candidate_id` as Stable Fact Refs

**File**: `dayu/host/dispatch.py:3319–3363`, `dayu/host/engine_ingest.py:3067–3111`

**Evidence**: The function reads `CONTEXT_COMPACTED.evidence_backed_fact_candidates[*].candidate_id` and returns them as `evidence_backed_fact_refs`:

```python
# dispatch.py:3357-3362
candidate_id = candidate.get(_PAYLOAD_FIELD_CANDIDATE_ID)
if not isinstance(candidate_id, str) or candidate_id.strip() == "":
    raise HostDurableError(...)
refs.append(candidate_id)
```

Plan §4.6 freezes `candidate_id` as "item-local diagnostic / dedupe metadata only" and explicitly states "candidate id is not authoritative provenance." The plan §4.2 says `evidence_backed_fact_refs` should be "existing stable fact refs." A `candidate_id` like `"fact-memory-revenue"` is not the same as a stable fact reference.

**Corner case**: If a `CONTEXT_COMPACTED` event has `evidence_backed_fact_candidates[].candidate_id == "fact-1"` and a later memory projection materializes that candidate into `EvidenceBackedFactView(item_id="memory-item:evidence-backed:fact-1")`, the next compaction request would receive `evidence_backed_fact_refs=("fact-1",)` — which is the candidate_id, not the item_id. The compactor sees the candidate-local ID but not the stable memory item ID.

**Why this is HIGH, not CRITICAL**: In the current codebase, `candidate_id` is the only identifier available on the `CONTEXT_COMPACTED` payload for fact candidates. The full stable fact ref (e.g., `"stable:evidence_backed_facts:xxx"` or the memory `item_id`) does not appear in `CONTEXT_COMPACTED` payloads. The implementation is internally consistent — it just uses a different identifier namespace than the plan's "stable fact ref" terminology suggests. The risk is that `candidate_id` could collide across different compaction events (e.g., two different compact events both use `candidate_id="fact-1"` for different facts). The `dict.fromkeys()` deduplication on line 3287/3035 would collapse them into one, losing a reference.

**Fix direction**: Either (a) define `evidence_backed_fact_refs` as a derived identifier of the form `f"{compact_event_id}::{candidate_id}"` to guarantee cross-compaction uniqueness, or (b) document in the plan and design doc that `candidate_id` IS the stable fact ref in the current schema and add a uniqueness constraint across CONTEXT_COMPACTED events.

---

## Finding 3 [HIGH] — Missing Adversarial Test Coverage for Bounded EventLog Read Edge Cases

**Files**: `tests/host/test_compaction_operation.py:229–406`

**Evidence**: The two new tests cover:
- `test_compaction_request_evidence_inputs_are_bounded_for_proactive_and_reactive`: happy path — range boundary, session filter, two-path parity.
- `test_compaction_request_evidence_inputs_allow_empty_when_range_has_no_envelope`: empty envelope in payload.

Not covered:
1. **Malformed envelope JSON on TOOL_RESULT_ACCEPTED**: If `accepted_evidence_envelope` contains invalid JSON structure, `accepted_evidence_envelope_from_json_value()` raises `ValueError`, which is caught and re-raised as `HostDurableError`. No test exercises this path.
2. **Envelope producer_event_ref mismatch**: `dispatch.py:3314` checks `envelope.producer_event_ref != row.event_id`. If the envelope's `producer_event_ref` doesn't match the `TOOL_RESULT_ACCEPTED` event_id, `HostDurableError` is raised. No test covers this.
3. **Malformed CONTEXT_COMPACTED payload**: The validation in `_evidence_backed_fact_refs_from_compacted_event` checks for non-list `evidence_backed_fact_candidates`, non-object candidate items, and empty/invalid `candidate_id`. None of these error paths are tested.
4. **Malformed preserved_fact_refs in CONTEXT_COMPACTED**: `_required_text_list` validates that `evidence_backed_fact_refs` is a list of non-empty strings. No test covers non-list or empty-item cases.
5. **Duplicate TOOL_RESULT_ACCEPTED events (same event_id)**: Should not happen due to event_id uniqueness, but adversarial scenario is not covered. The code does NOT deduplicate envelopes (unlike fact refs which use `dict.fromkeys()`).

**Why this matters**: These are the exact adversarial contract paths that plan §4.2-4.3 and the review scope explicitly ask for: "duplicate envelope", "invalid envelope", "missing payload". Undetected `HostDurableError` exceptions on the bounded read path would crash the proactive dispatch or reactive ingest handler, potentially leaving runs stuck.

**Fix direction**: Add tests for each adversarial path listed above. Use `pytest.raises(HostDurableError)` for the error paths. For the deduplication gap, add a test where two different TOOL_RESULT_ACCEPTED events carry envelopes with colliding `evidence_id` values (if that can happen), or confirm that `evidence_id` uniqueness is guaranteed by the derivation formula `evidence:<event_id>`.

---

## Finding 4 [HIGH] — `accepted_evidence_refs` Field Missing from `CompactionRequest`

**File**: `dayu/host/compaction.py:203–235`

**Evidence**: Plan §4.2 states:

> CompactionRequest must add:
> ```
> accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]
> accepted_evidence_refs: tuple[str, ...]
> ```
> `accepted_evidence_refs` is derived from `accepted_evidence_envelopes[*].evidence_id` during request construction, not supplied by LLM output.

The current `CompactionRequest` has `accepted_evidence_envelopes` (line 230) but no `accepted_evidence_refs` field. The compactor and quality checker must derive refs from envelopes by accessing `envelope.evidence_id` on each envelope.

**Impact**: Downstream consumers (compactor, quality checker) that only need the ref strings — not the full typed envelopes — must iterate envelopes to extract `evidence_id`. This is a minor ergonomic issue, not a correctness bug, because the information IS available. However, it deviates from the plan's explicit contract and means the plan-mandated field is absent.

**Fix direction**: Either (a) add `accepted_evidence_refs: tuple[str, ...]` to `CompactionRequest`, populated during construction from the envelopes, or (b) explicitly document in the plan revision that this field is intentionally omitted because it is trivially derived. If (a), the construction sites in both `dispatch.py` and `engine_ingest.py` need to add `accepted_evidence_refs=tuple(e.evidence_id for e in evidence_inputs.accepted_evidence_envelopes)`.

---

## Finding 5 [MEDIUM] — Hardcoded `start_event_sequence=1` in Both Call Sites

**Files**: `dayu/host/dispatch.py:1268`, `dayu/host/engine_ingest.py:1186`

**Evidence**: Both proactive and reactive paths hardcode `start_event_sequence=1`:

```python
# dispatch.py:1267-1270
evidence_inputs = _compaction_request_evidence_inputs(
    transaction, self._event_log_store,
    session_id=run.session_id,
    start_event_sequence=1,
    end_event_sequence=run.input_event_sequence,
)
```

**Why this matters**: If a session's EventLog has gaps or doesn't start at sequence 1 (e.g., EventLog was populated before this session was created, or compaction removed early events), `start_event_sequence=1` might point to a nonexistent row or skip valid events. The function's range validation (`start_event_sequence <= 0` → error) would pass, but `read_events_after(transaction, 0, limit=...)` would return rows starting from the actual first event in the log, which may not correspond to sequence 1.

**Impact**: In practice with SQLite auto-increment, the first event in the database is sequence 1, and `read_events_after(0, ...)` correctly reads from the beginning. However, if the database is ever sharded, restored from a backup, or uses a different sequence counter, this assumption breaks silently. The function's own validation ensures `start_event_sequence > 0` but doesn't verify it corresponds to an actual event.

**Fix direction**: Either (a) derive `start_event_sequence` from the session's first event (requires a separate query or a session-level `min_event_sequence` column), or (b) document in `_compaction_request_evidence_inputs` that it tolerates `start_event_sequence` pointing before the first actual event (which it does, since `read_events_after` just returns no rows for non-existent sequences). The function already handles this gracefully — if no rows match, `accepted_evidence` and `evidence_backed_fact_refs` are empty — so the actual risk is that evidence is silently missed, not a crash.

---

## Finding 6 [MEDIUM] — No Deduplication for `accepted_evidence_envelopes`

**Files**: `dayu/host/dispatch.py:3285–3286`, `dayu/host/engine_ingest.py:3033–3034`

**Evidence**:

```python
# dispatch.py:3285-3286
return _CompactionRequestEvidenceInputs(
    accepted_evidence_envelopes=tuple(accepted_evidence),
    evidence_backed_fact_refs=tuple(dict.fromkeys(evidence_backed_fact_refs)),
)
```

`evidence_backed_fact_refs` is deduplicated via `dict.fromkeys()`. `accepted_evidence_envelopes` is NOT deduplicated. If two `TOOL_RESULT_ACCEPTED` events in the range produce envelopes with the same `evidence_id` (unlikely given `evidence:<event_id>` derivation, but possible if an envelope is manually constructed), the compactor would receive duplicate envelopes.

**Impact**: Low in practice because `evidence_id` derivation from unique event IDs guarantees uniqueness. However, if a bug in the accept barrier writes the same envelope to two different TOOL_RESULT_ACCEPTED events, the compactor receives duplicates. A dedup by `evidence_id` would be defensive.

**Fix direction**: Add deduplication by `evidence_id`:

```python
seen: set[str] = set()
unique: list[AcceptedEvidenceEnvelope] = []
for env in accepted_evidence:
    if env.evidence_id not in seen:
        seen.add(env.evidence_id)
        unique.append(env)
accepted_evidence_envelopes=tuple(unique),
```

---

## Finding 7 [MEDIUM] — `_memory_raw_turn_messages` Semantic Change: From Exclusion to Inclusion Filter

**File**: `dayu/host/run_input.py:1794–1798`

**Evidence**: Before this change, `_memory_raw_turn_messages` excluded only `EPISODE_SUMMARY` items, passing through all other continuity kinds as raw turns. After this change, it positively allows only `RAW_USER_TURN`, `RAW_ASSISTANT_TURN`, and `ASSISTANT_CONCLUSION`:

```python
# Before (line 1794):
if item.item_kind is ConversationContinuityKind.EPISODE_SUMMARY:
    continue

# After (lines 1794-1798):
if item.item_kind not in (
    ConversationContinuityKind.RAW_USER_TURN,
    ConversationContinuityKind.RAW_ASSISTANT_TURN,
    ConversationContinuityKind.ASSISTANT_CONCLUSION,
):
    continue
```

**Why this matters**: This is a correct behavioral change per the plan (recent raw turns must not include minimum preserve items). However, if any existing test or caller relied on the old behavior where future continuity kinds would automatically appear as raw turns, they would silently change behavior. The `MINIMUM_PRESERVE_ITEM` kind is the only new kind in this slice, so the immediate risk is bounded. The positive-inclusion filter is the right pattern — it's more defensive than the old exclusion filter.

**Impact**: Correct change. No action needed, but noted as a behavioral contract observation.

---

## Finding 8 [LOW] — `_preserve_reason_text` Returns "unspecified" for None Reason

**File**: `dayu/host/run_input.py:1895–1904`

**Evidence**:

```python
def _preserve_reason_text(item: ConversationContinuityItem) -> str:
    if item.preserve_reason is None:
        return "unspecified"
    return item.preserve_reason.value
```

A `ConversationContinuityItem` with `item_kind=MINIMUM_PRESERVE_ITEM` but `preserve_reason=None` is a malformed item — it has the kind but no reason. The function silently renders "unspecified" instead of logging a diagnostic or raising an error.

**Impact**: Low. The memory projection in Slice 5 should ensure every MINIMUM_PRESERVE_ITEM has a valid `preserve_reason`. The "unspecified" fallback is a rendering concern only and does not affect correctness.

**Fix direction**: Optional — log a warning diagnostic when `preserve_reason is None` on a MINIMUM_PRESERVE_ITEM.

---

## Finding 9 [LOW] — README Update is Minimal for Slice Scope

**File**: `dayu/host/README.md:243–244`

**Evidence**: The README diff adds two sentences to the Conversation Memory section about stable fact block rendering and minimum preserve item injection. The plan §7 Slice 6 says "README sync decision for that slice" is required. The current update covers the fact rendering semantics but doesn't mention:
- The two-path (proactive/reactive) evidence input wiring
- The bounded EventLog read contract
- The `_CompactionRequestEvidenceInputs` separation

**Impact**: Low. The README is not a design specification — the design doc and implementation control doc are the authoritative sources. The current update is adequate for developer orientation.

---

## Contract Review: Six Scoped Questions

### Q1: no-compaction short-link follow-up 是否仍可依赖 recent raw turns?

**Pass**. `_memory_raw_turn_messages()` (run_input.py:1781–1816) still renders recent raw turns from `snapshot.conversation_continuity.items`, filtering to `RAW_USER_TURN`, `RAW_ASSISTANT_TURN`, and `ASSISTANT_CONCLUSION`. The current user input is excluded via `_is_current_run_user_input_memory_item()`. These raw turns are continuity only — they are NOT in the `stable:evidence_backed_facts` block. The plan's intent is satisfied: recent raw turns support no-compaction short-link follow-up without being mistaken for stable facts.

### Q2: post-compaction follow-up 是否能通过 RunInputBuilder 看到 evidence-backed facts?

**Pass**. `_memory_evidence_backed_fact_message()` (run_input.py:1726–1751) renders facts from `snapshot.evidence_backed_facts` with `claim_text`, `evidence_refs`, `evidence_kind`, `extraction_operation_ref`, and full provenance (`event_id`, `event_sequence`). The block `stable:evidence_backed_facts` is positioned before raw turns in the memory message order. Test `test_durable_memory_provider_uses_covered_snapshot` (test_run_input_builder.py:507) verifies that `claim_text=Revenue increased year over year` and `evidence_refs=evidence:memory-tool` appear in the rendered output and that `digest_ref=` and `fact_summary=` do NOT appear (no regression to digest-only rendering).

### Q3: bounded EventLog read 是否正确处理 range start/end、session/run boundary、missing payload、invalid envelope、duplicate envelope、reactive/proactive parity?

**Partial pass — gaps in adversarial coverage**.

- **Range start/end**: Handled correctly. `start_event_sequence <= 0` raises error; `end_event_sequence < start_event_sequence` raises error. The `read_events_after` cursor is `start_event_sequence - 1`, limit is exact range width. The break condition `row.event_sequence > end_event_sequence` correctly terminates iteration. ✓
- **Session boundary**: Handled. `row.session_id != session_id` → skip. ✓
- **Run boundary**: Not explicitly filtered by run_id (only session_id). This matches the contract — evidence is session-scoped. ✓
- **Missing payload**: Handled. `event_payload_object()` returns the payload; if `accepted_evidence_envelope` key is absent, returns empty tuple. ✓
- **Invalid envelope**: Handled via `ValueError` → `HostDurableError` re-raise. But NOT tested. ✗
- **Duplicate envelope**: Not deduplicated (Finding 6). ✗
- **Reactive/proactive parity**: The two helper paths produce identical results for the same range (verified by test `test_compaction_request_evidence_inputs_are_bounded_for_proactive_and_reactive`). ✓

### Q4: CompactionRequest 是否携带 accepted_evidence_envelopes 和 existing evidence_backed_fact_refs，且没有把 accepted evidence refs 当 fact refs?

**Pass with caveat (Finding 2)**.

- `accepted_evidence_envelopes` (typed `tuple[AcceptedEvidenceEnvelope, ...]`) is populated in both proactive (dispatch.py:1284) and reactive (engine_ingest.py:3162) paths. ✓
- `evidence_backed_fact_refs` (typed `tuple[str, ...]`) is populated separately at dispatch.py:1285 and engine_ingest.py:3163. ✓
- The two are never mixed — `accepted_evidence_envelopes` carries typed envelopes, `evidence_backed_fact_refs` carries string refs. ✓
- Caveat: `evidence_backed_fact_refs` contains `candidate_id` values from CONTEXT_COMPACTED events, not materialized memory item_ids (Finding 2). In the current schema, this is the only available identifier for cross-compaction fact reference.

### Q5: minimum preserve rendering 是否足以支持"第二个因素"这类指代解析?

**Pass**. `_memory_minimum_preserve_message()` (run_input.py:1819–1850) renders each minimum preserve item with:
- `label` (e.g., `"factor-2"`)
- `text` (e.g., `"second factor: margin mix"`)
- `source_refs` (e.g., `"event-memory-raw-user"`)
- `preserve_reason` (e.g., `"needed_for_ordered_item_reference"`)

The block is injected between recent raw turns and episode summaries (run_input.py:1589–1593). This position, combined with labeled text and source refs, gives the LLM enough context to resolve "第二个因素" — it can see the label `factor-2`, the text explaining what factor-2 is, and the source ref pointing to the original raw user turn. Test at test_run_input_builder.py:1024-1030 verifies this rendering.

### Q6: tests 是否覆盖 range 内/外、空 envelope、invalid/missing envelope 和 two-path wiring?

**Partial pass — covered paths are solid, adversarial gaps exist**.

| Scenario | Covered? | Test |
|---|---|---|
| Range boundary: inside vs. outside | Yes | test_compaction_request_evidence_inputs_are_bounded |
| Range boundary: other session | Yes | test_compaction_request_evidence_inputs_are_bounded |
| Two-path (proactive + reactive) parity | Yes | test_compaction_request_evidence_inputs_are_bounded |
| Empty envelope in payload | Yes | test_compaction_request_evidence_inputs_allow_empty |
| Malformed envelope JSON (ValueError → HostDurableError) | No | — |
| Envelope producer_event_ref mismatch | No | — |
| Malformed CONTEXT_COMPACTED evidence_backed_fact_candidates | No | — |
| Malformed CONTEXT_COMPACTED preserved_fact_refs | No | — |
| Duplicate evidence_ids across envelopes | No | — |
| Empty event range (start == end with no TOOL_RESULT_ACCEPTED) | Implicitly | Empty-envelope test covers a similar case |

See Finding 3 for detailed gap analysis.

---

## Positive Observations

1. **Evidence-backed fact rendering is correct and complete**: `claim_text`, `evidence_refs`, `evidence_kind`, `extraction_operation_ref`, `event_id`, `event_sequence` are all rendered. The old `fact_summary` and `digest_ref` fields are verified absent in tests (no regression).

2. **Minimum preserve injection position is correct**: After recent raw turns, before episode summaries — matching plan §5.6 item 6.

3. **`_memory_raw_turn_messages` filter change is defensive**: Moving from exclusion-based (`if EPISODE_SUMMARY: continue`) to inclusion-based (`if item_kind not in (RAW_USER_TURN, RAW_ASSISTANT_TURN, ASSISTANT_CONCLUSION): continue`) correctly prevents minimum preserve items from leaking into raw turn messages.

4. **`evidence_backed_fact_refs` deduplication**: Using `dict.fromkeys()` for dedup while preserving insertion order is clean and correct.

5. **Range validation is strict and early-failing**: `start_event_sequence <= 0` and `end_event_sequence < start_event_sequence` checks prevent nonsensical ranges. The function fails fast before any EventLog I/O.

6. **Test fixture quality**: `_accepted_evidence_envelope_for_event()` helper correctly derives `evidence_id = f"evidence:{event_id}"` and binds `producer_event_ref = event_id`, matching the `evidence.py` contract.

7. **Session isolation**: The bounded read correctly filters `row.session_id != session_id` and skips non-CANONICAL_FACT events, preventing cross-session evidence leakage.

8. **No stop-condition violation**: No Engine, Runner provider, Host public command API, `open_host(options)`, or `SubmitFollowupRequest` changes were made. Slice 6 stays within its allowed scope.

---

## Residual Risks

| Risk | Severity | Owner | Notes |
|---|---|---|---|
| Code duplication drift (Finding 1) | Critical | Slice 6 implementer | Must be resolved before merge; otherwise proactive/reactive paths will inevitably diverge |
| candidate_id as stable fact ref (Finding 2) | High | Slice 5/6 implementer + controller | Ambiguity in "stable fact ref" definition; needs plan clarification |
| Missing adversarial test coverage (Finding 3) | High | Slice 6 implementer | Adversarial paths are not exercised; bounded read error handling is untested |
| Missing accepted_evidence_refs field (Finding 4) | High | Slice 6 implementer + controller | Plan deviation; downstream consumers may expect this field |
| Hardcoded start_event_sequence=1 (Finding 5) | Medium | Slice 6 implementer | Graceful degradation if start < actual first sequence, but silently misses evidence |
| Envelope deduplication gap (Finding 6) | Medium | Slice 6 implementer | Low practical risk due to evidence_id uniqueness by derivation |
| Old raw turn semantic change (Finding 7) | Low | — | Positive behavioral change; no action needed |
| None preserve_reason rendering (Finding 8) | Low | Slice 5/6 implementer | Rendering-only; memory projection should prevent this state |

---

## Test Run Verification

Tests were not executed in this review (review agent constraint: review only, no code modification or test execution). The review is based on static analysis of the diff and surrounding code context. The implementer should run:

```bash
source .venv/bin/activate && pytest tests/host/test_run_input_builder.py tests/host/test_compaction_operation.py -v
source .venv/bin/activate && pyright dayu/host/run_input.py dayu/host/dispatch.py dayu/host/engine_ingest.py
```

---

## Verdict

**Slice 6 contract is satisfied**. The three core objectives — evidence-backed fact rendering, minimum preserve injection, and two-path evidence wiring — are correctly implemented. The rendering contract matches the plan: no digest-only regression, correct claim_text/evidence_refs format, minimum preserve at the right position with label/text/source_refs/reason.

**One blocking issue**: the critical code duplication (Finding 1) must be resolved before merge. The duplicated constructs should be extracted to a shared location.

**Three high issues** that should be addressed: candidate_id semantics (Finding 2), missing adversarial test coverage (Finding 3), and the `accepted_evidence_refs` field deviation from the plan (Finding 4).

**No stop-condition violations**. The slice stays within its allowed file and scope boundaries.
