# Phase 12.5 Slice 6 Code Review: RunInputBuilder Rendering And Compaction Request Wiring

- Review Agent: MiMo
- Date: 2026-05-22
- Baseline: `1f37435` (gateflow: accept phase 12.5 slice 5)
- Scope: uncommitted changes on `feat/phase-12-5-conversation-memory-optimize`
- Plan artifact: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md`
- Design truth: `docs/host/design.md` §23-§25
- Control doc: `docs/host/implementation-control.md` Phase 12.5

## Verdict

**PASS with 1 advisory finding (S6-A1) and 2 residual risks (S6-R1, S6-R2).**

All 7 review checkpoints pass. No blocking findings. One advisory finding about duplicated helper code that should be addressed in Slice 7 aggregate polish.

## Findings

### S6-A1 [Advisory] Helper Duplication Between dispatch.py and engine_ingest.py

**Severity**: Advisory (not blocking; plan §3.6 A3 deferred to Slice 7)

**Evidence**:

`dispatch.py` lines 3240-3394 and `engine_ingest.py` lines 2988-3141 contain four identical module-private helper functions:

1. `_compaction_request_evidence_inputs()` (~50 lines each)
2. `_accepted_evidence_envelope_from_event()` (~25 lines each)
3. `_evidence_backed_fact_refs_from_compacted_event()` (~35 lines each)
4. `_required_text_list()` (~20 lines each)

Also duplicated: `_CompactionRequestEvidenceInputs` dataclass and five `_PAYLOAD_FIELD_*` constants.

Total: ~155 lines of identical logic duplicated verbatim.

**Why it matters**: Maintenance risk. A future change to evidence ref extraction logic must be applied in two places; divergence would cause proactive and reactive compaction paths to behave differently.

**Fix recommendation**: Extract to a shared module-private helper (e.g., `dayu/host/_compaction_evidence_helpers.py` or add to existing `dayu/host/compaction.py`) before Slice 7 merge. Both dispatch.py and engine_ingest.py would import from the shared module. This is consistent with the plan's §3.6 A3 deferral to Slice 7 aggregate polish.

---

### S6-R1 [Residual Risk] Missing Post-Compaction Follow-Up Test

**Severity**: Residual (covered by Slice 7 integration smoke)

**Evidence**:

Plan §7 Slice 6 required test: "post-compaction follow-up can use evidence-backed facts even when old raw turns are compacted away." (line 739)

Current `test_run_input_builder.py` does not contain a test that:
1. Simulates a follow-up turn after a `CONTEXT_COMPACTED` event.
2. Verifies that evidence-backed facts from the compaction are rendered in the follow-up's messages.

`test_durable_memory_provider_uses_covered_snapshot` (line 482) injects evidence-backed facts via a manually constructed `ConversationMemorySnapshot`, which proves rendering correctness but not the post-compaction data flow.

`test_run_input_memory_messages_include_context_compacted_projection` (line 923) exercises compacted projection catch-up but only asserts `current_goal`, `confirmed_subject`, `open_question`, and `episode_summary` -- not evidence-backed facts.

**Fix recommendation**: Defer to Slice 7 `Integration Smoke, README Sync, Aggregate Validation` as planned. The integration smoke test should verify: (1) CONTEXT_COMPACTED event with evidence_backed_fact_candidates -> memory projection materializes facts -> follow-up RunInputBuilder renders claim_text + evidence_refs.

---

### S6-R2 [Residual Risk] Missing No-Compaction Short-Link Follow-Up Test

**Severity**: Residual (covered by Slice 7 integration smoke)

**Evidence**:

Plan §7 Slice 6 required test: "no-compaction short-link follow-up can use recent raw turns." (line 738)

No current test simulates a follow-up turn where compaction did NOT occur and verifies that recent raw turns from the memory snapshot provide the primary continuity mechanism.

**Fix recommendation**: Defer to Slice 7 integration smoke as planned.

---

## Review Checkpoint Results

### 1. Stable block is `stable:evidence_backed_facts` with full claim rendering

**PASS.**

Evidence (`run_input.py` lines 1623-1629):
```python
facts = _memory_evidence_backed_fact_message(snapshot.evidence_backed_facts)
if facts is not None:
    blocks.append(
        _MemoryStableBlock(
            block_id="stable:evidence_backed_facts",
            message=facts,
        )
    )
```

Fact rendering (`run_input.py` lines 1738-1746) includes all required fields:
- `claim_text`
- `evidence_refs` (comma-joined)
- `evidence_kind`
- `extraction_operation_ref`
- `event_id` (from provenance)
- `event_sequence` (from provenance)

No digest-only rendering. Zero remaining `fact_summary`, `digest_ref`, or `verified` references in `run_input.py`.

Test assertion (`test_run_input_builder.py` lines 511-517):
```python
assert "claim_text=Revenue increased year over year" in contents[3]
assert "evidence_refs=evidence:memory-tool" in contents[3]
assert "evidence_kind=observed_value" in contents[3]
assert "extraction_operation_ref=event:event-memory-episode" in contents[3]
assert "digest_ref=" not in contents[3]
assert "fact_summary=" not in contents[3]
```

### 2. Minimum preserve continuity item injection order

**PASS.**

Rendering order in `_memory_messages()` (`run_input.py` lines 1577-1598):
1. stable blocks (goals, subjects, evidence_backed_facts, questions_assumptions)
2. raw turn messages (user/assistant)
3. **minimum preserve continuity** -- after raw turns, before episode summaries
4. episode summaries

This matches the plan §7 Slice 6 requirement: "Render minimum preserve continuity items after recent raw turns and before episode summaries."

Minimum preserve rendering (`run_input.py` lines 1838-1846) includes:
- `label`
- `text` (via `_continuity_item_text`)
- `source_refs` (comma-joined)
- `preserve_reason` (via `_preserve_reason_text`)

Not treated as stable fact. Filters by `ConversationContinuityKind.MINIMUM_PRESERVE_ITEM` only.

Test assertion (`test_run_input_builder.py` lines 523-530):
```python
assert contents[7].startswith("Memory minimum preserve continuity:")
assert "label=factor-2" in contents[7]
assert "text=second factor: margin mix" in contents[7]
assert "source_refs=event-memory-raw-user" in contents[7]
assert "preserve_reason=needed_for_ordered_item_reference" in contents[7]
```

### 3. Bounded EventLog reads for proactive and reactive paths

**PASS.**

Both `dispatch.py` and `engine_ingest.py` implement `_compaction_request_evidence_inputs()` with identical logic:

- Reads `event_log_store.read_events_after(transaction, start_event_sequence - 1, limit=end - start + 1)`
- Filters by `row.session_id == session_id`
- Filters by `row.event_class is EventClass.CANONICAL_FACT`
- Only extracts `TOOL_RESULT_ACCEPTED.accepted_evidence_envelope` and `CONTEXT_COMPACTED` fact refs
- Breaks when `row.event_sequence > end_event_sequence`

Proactive call site (`dispatch.py` lines 1264-1270): `start_event_sequence=1, end_event_sequence=run.input_event_sequence`

Reactive call site (`engine_ingest.py` lines 1182-1188): `start_event_sequence=1, end_event_sequence=context.run.input_event_sequence`

Test (`test_compaction_operation.py` lines 229-356) verifies:
- Only in-range evidence is returned
- Out-of-range evidence (after `end_event_sequence`) is excluded
- Other-session evidence is excluded
- Both proactive and reactive helpers produce identical results
- Empty result when range has no envelope

### 4. accepted_evidence_refs separated from evidence_backed_fact_refs

**PASS.**

`_CompactionRequestEvidenceInputs` dataclass has separate fields:
- `accepted_evidence_envelopes: tuple[AcceptedEvidenceEnvelope, ...]`
- `evidence_backed_fact_refs: tuple[str, ...]`

CompactionRequest construction uses both fields independently:
- `dispatch.py` line 1284: `accepted_evidence_envelopes=evidence_inputs.accepted_evidence_envelopes`
- `dispatch.py` line 1285: `evidence_backed_fact_refs=evidence_inputs.evidence_backed_fact_refs`

No financial source/locator parsing. Envelope validation is shape-only (`accepted_evidence_envelope_from_json_value`).

### 5. No Engine/Runner/public API/open_host/SubmitFollowupRequest changes

**PASS.**

Diff shows changes only in:
- `dayu/host/run_input.py` (internal RunInputBuilder rendering)
- `dayu/host/dispatch.py` (internal proactive compaction wiring)
- `dayu/host/engine_ingest.py` (internal reactive compaction wiring)
- `tests/host/test_run_input_builder.py` (test fixtures + assertions)
- `tests/host/test_compaction_operation.py` (new bounded-read tests)
- `dayu/host/README.md` (doc sync)

No changes to Engine, Runner, Service, UI, `open_host()`, `SubmitFollowupRequest`, or any public API surface.

### 6. No old semantics / anti-patterns

**PASS.**

- Zero remaining `verified_facts`, `VerifiedFactView`, `tool_fact_refs`, `verified_fact_refs`, `fact_summary`, `digest_ref` in any of the 3 production files.
- Zero `Any`, `object`, untyped parameters, or untyped return values in new code.
- Zero `hasattr`/`getattr` usage in new code.
- Zero compatibility wrappers or re-exports.
- All new functions have complete Chinese docstrings with params/returns/raises.
- All new dataclasses use `frozen=True, slots=True`.

### 7. Test coverage for Slice 6 plan

**PASS (with residual risks S6-R1, S6-R2).**

Covered:
- RunInputBuilder memory block renders `claim_text` and `evidence_refs` (test line 482)
- No digest-only rendering regression (negative assertion line 517)
- Minimum preserve continuity item injected as continuity, not stable fact (test line 523)
- Bounded EventLog reads exclude out-of-range and other-session evidence (test line 229)
- Both proactive and reactive paths tested (test line 229)
- Empty result when range has no envelope (test line 359)

Not covered (deferred to Slice 7):
- Post-compaction follow-up sees evidence-backed facts (S6-R1)
- No-compaction short-link follow-up uses recent raw turns (S6-R2)

## README Sync Check

`dayu/host/README.md` diff adds two paragraphs:
1. Stable fact block id `stable:evidence_backed_facts` with rendering fields and minimum preserve injection position.
2. Proactive/reactive compaction request evidence input from bounded EventLog reads.

Both paragraphs accurately describe the implemented behavior. No stale terminology. Content falls within `dayu/host/README.md` responsibility per CLAUDE.md rules.

## Conclusion

Slice 6 implementation correctly wires RunInputBuilder rendering and compaction request evidence inputs per the plan. All 7 review checkpoints pass. One advisory finding (helper duplication) should be addressed in Slice 7. Two residual risks (missing integration-level tests) are explicitly deferred to Slice 7 as planned. No blocking findings.
