# Phase 12.5 Slice 5 Code Review: Memory Projection Materialization

- **Review agent**: Deep Review (no code modification)
- **Baseline**: `e2a7332` gateflow: accept phase 12.5 slice 4
- **Reviewed changes**: 5 files, +935/-334 lines (uncommitted)
- **Design source of truth**: `docs/host/design.md` §24, §25
- **Plan**: `docs/reviews/phase12-5-implementation-ready-plan-20260522.md` §7 Slice 5
- **Date**: 2026-05-22

---

## Findings

### Finding 1 — HIGH — `_validate_compacted_payload_for_memory_projection` 可能掩盖非 fact candidate 验证错误

- **File**: `dayu/host/memory.py:1384-1417`
- **Severity**: HIGH
- **Category**: Correctness — error masking

**Evidence**:

```python
try:
    validate_context_compacted_payload(event.payload)
    return (), True
except ValueError as exc:
    patched_payload = dict(event.payload)
    patched_payload[_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES] = []
    try:
        validate_context_compacted_payload(patched_payload)
    except ValueError:
        raise exc  # <-- reraise original, potentially masking real error
```

**Problem**: The two-pass validation relies on the fact that if the patched payload (with empty fact candidates) fails, then the original error is reraised. However, if the original `ValueError` was raised due to fact candidates (e.g., "evidence_refs must point to accepted evidence") AND the patched payload also fails due to an unrelated non-fact field (e.g., "episode_summary_candidate missing title"), the function reraises the original fact-candidate error. The real blocking issue (missing episode summary title) is masked. The caller sees a fact-candidate error and may misdiagnose the root cause.

**Impact**: During development, this can waste debugging time. In production, if `validate_context_compacted_payload` validation order changes, the raised error message may become misleading. This does not silently accept invalid data — the payload IS rejected — but the error message may point to the wrong field.

**Fix suggestion**: Capture both exceptions and prefer the non-fact-candidate error when both fail:

```python
except ValueError as exc:
    patched_payload = dict(event.payload)
    patched_payload[_PAYLOAD_FIELD_EVIDENCE_BACKED_FACT_CANDIDATES] = []
    try:
        validate_context_compacted_payload(patched_payload)
    except ValueError as non_fact_exc:
        # non-fact field is also invalid — raise the clearer error
        raise non_fact_exc from exc
    # Only fact candidates were the problem — diagnostic path
    ...
```

Alternatively, combine both messages: `raise ValueError(f"compact payload invalid: {exc}; after clearing fact candidates: {non_fact_exc}") from exc`.

---

### Finding 2 — MEDIUM — `_evidence_backed_facts_from_compacted_event` 缺少 claim_text 长度上限防御

- **File**: `dayu/host/memory.py:1420-1484`
- **Severity**: MEDIUM
- **Category**: Defense-in-depth

**Evidence**: The compaction layer enforces `MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS = 2000` in `EvidenceBackedFactCandidate.__post_init__` (`dayu/host/compaction.py:757-761`). However, `_evidence_backed_facts_from_compacted_event` reads raw JSON from the event payload and passes `claim_text` directly to `EvidenceBackedFactView`, whose `__post_init__` only checks `_require_non_empty(self.claim_text, "claim_text")` with no upper bound.

```python
# memory.py:1457
claim_text = _required_str(candidate, _PAYLOAD_FIELD_CLAIM_TEXT)
facts.append(
    EvidenceBackedFactView(
        ...
        claim_text=claim_text,  # <-- no max_chars enforcement at this layer
        ...
    )
)
```

**Impact**: If a bug in `validate_context_compacted_payload` or a future code path bypasses the compaction-layer `EvidenceBackedFactCandidate` constructor, an oversized `claim_text` can enter the memory snapshot. The snapshot would then contain a fact with unbounded text, potentially exceeding the memory budget silently.

**Fix suggestion**: Add a bounded check in `_evidence_backed_facts_from_compacted_event` before constructing `EvidenceBackedFactView`, or in `EvidenceBackedFactView.__post_init__` itself:

```python
if len(claim_text) > MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS:
    raise ValueError(f"claim_text exceeds {MAX_EVIDENCE_BACKED_FACT_CLAIM_TEXT_CHARS} chars")
```

Same consideration applies to minimum preserve item `text` vs `MAX_MINIMUM_PRESERVE_ITEM_TEXT_CHARS` in `_minimum_preserve_items_from_compacted_event` (`memory.py:1604-1610`). The `_bounded_patch_text` helper provides truncation but not explicit length rejection.

---

### Finding 3 — MEDIUM — Snapshot read path 对每行 item_kind 执行 SQL 查询

- **File**: `dayu/host/durable/memory.py:941-972`
- **Severity**: MEDIUM
- **Category**: Performance / Architecture

**Evidence**: `_validate_snapshot_item_kinds` performs `SELECT item_kind FROM host_memory_items WHERE snapshot_id = ?` on every snapshot read path (`read_memory_snapshot`, `read_latest_memory_snapshot`, `read_latest_memory_snapshot_at_or_before`). This adds a SQL round-trip on the hot read path.

```python
def _snapshot_row_from_host_row(transaction, row):
    ...
    _validate_snapshot_digest(snapshot)
    _validate_snapshot_item_kinds(transaction, snapshot.snapshot_id)  # extra SQL query
    return MemorySnapshotRow(...)
```

**Analysis**: For bounded memory items per snapshot (typically < 100 rows), this query is cheap. The read path is not on the critical Engine loop. However, the CHECK constraint in `schema.py` already rejects `verified_fact` at write time, and the JSON-level checks in `conversation_memory_snapshot_from_json_value` / `_evidence_backed_fact_from_json_value` already reject old keys/shapes at parse time. The SQL item_kind scan is the third layer of defense, which is robust but has diminishing returns.

**Residual risk**: Acceptable. This is belt-and-suspenders validation. If it becomes a performance concern, it can be made conditional (e.g., only on first read after a snapshot write, or only when the snapshot JSON itself doesn't contain old keys).

---

### Finding 4 — LOW — `conversation_memory_snapshot_from_json_value` only checks key presence, not value semantics

- **File**: `dayu/host/memory.py:2918-2919`
- **Severity**: LOW
- **Category**: Validation completeness

**Evidence**:

```python
if "verified_facts" in mapping:
    raise ValueError("old verified_facts snapshot key is not supported")
```

This rejects any JSON object containing the key `"verified_facts"`, even if the value is `null` or `[]`. This is correct "fail closed" behavior per the plan — no silent acceptance of old keys. However, the check does not distinguish between a maliciously crafted payload and a genuinely old snapshot. The error message is clear enough for debugging.

**Residual risk**: None. This is the intended behavior.

---

### Finding 5 — LOW — `_evidence_backed_fact_from_json_value` old shape detection 可更完整

- **File**: `dayu/host/memory.py:2993-2994`
- **Severity**: LOW
- **Category**: Validation completeness

**Evidence**:

```python
if "fact_summary" in mapping or "evidence_anchor" in mapping:
    raise ValueError("old evidence-backed fact JSON shape is not supported")
```

Old fact JSON always contained both `"fact_summary"` and `"claim_status"`. The check catches `"fact_summary"` and `"evidence_anchor"`, which covers the old shape completely. An old fact JSON with only `"claim_status"` (without `"fact_summary"`) is impossible in practice. The check is sufficient.

**Residual risk**: None for practical purposes. The `_required_str(mapping, "claim_text")` call immediately after would fail on any old JSON that somehow bypasses the check, producing a clear error.

---

## Dimension-by-Dimension Assessment

### 1. Run1 compact accepted evidence → CONTEXT_COMPACTED candidates → durable memory → next snapshot

**Verdict**: CLOSED. The chain is:

1. `TOOL_RESULT_ACCEPTED` → `pass` (no fact generation; `memory.py:1184-1188`)
2. `CONTEXT_COMPACTED` → `_validate_compacted_payload_for_memory_projection` → `_evidence_backed_facts_from_compacted_event` → facts with `HOST_PROJECTION` provenance (`memory.py:1200-1218`)
3. `write_memory_snapshot` → durable rows with `evidence_backed_fact` item kind (`durable/memory.py:684-712`)
4. `_replace_item_by_id` for next snapshot continuity (`memory.py:1212-1214`)

Provenance is correctly anchored to the `CONTEXT_COMPACTED` event (`memory.py:1444: provenance.event_id = event.event_id`). `extraction_operation_ref` is `event:<compact_event_id>`. `candidate_id` is local-only diagnostic metadata. `test_durable_roundtrip_uses_evidence_backed_facts_and_item_kind` validates the full roundtrip.

No gap found.

### 2. EvidenceBackedFactView provenance — only from accepted compact output

**Verdict**: CONFIRMED. 

- `TOOL_RESULT_ACCEPTED` → `pass` (line 1188): no fact generation
- `USER_INPUT_ACCEPTED` → raw user turn continuity only (line 1195-1196)
- `RUN_SUCCEEDED` → assistant conclusion continuity only (line 1198-1199)
- `CONTEXT_COMPACTED` → fact materialization (line 1210)

Tests confirm:
- `test_invalid_source_refs_do_not_create_tool_result_fact`: TOOL_RESULT_ACCEPTED → zero facts
- `test_projection_ignores_reserved_claim_status_from_payload`: no reserved statuses propagated
- `test_recent_raw_turns_support_followup_without_becoming_stable_fact`: raw turns are not stable facts
- `test_episode_summary_does_not_replace_evidence_anchor`: (existing test) summary is not fact

No gap found.

### 3. Minimum preserve enters durable/snapshot continuity, not stable facts

**Verdict**: CONFIRMED.

- Minimum preserve candidates materialize as `ConversationContinuityItem(item_kind=MINIMUM_PRESERVE_ITEM)` with `claim_status=ASSUMPTION` (`memory.py:1614`)
- They enter `conversation_continuity.items`, not `evidence_backed_facts`
- Schema.py: `minimum_preserve_item` added to CHECK constraint (`schema.py:746-747`): fresh-schema addition, no backward compat
- `_validate_snapshot_item_kinds`: `MINIMUM_PRESERVE_ITEM` is an allowed kind (via `ConversationContinuityKind`)
- `test_minimum_preserve_candidates_create_continuity_items_only` confirms zero facts and correct continuity materialization

`ConversationContinuityItem` new fields (`label`, `source_refs`, `preserve_reason`) are properly validated in `__post_init__` and serialized in JSON codec. No untyped extra payload.

No gap found.

### 4. Old verified snapshot/key/item kind — fail closed

**Verdict**: CONFIRMED. Three layers of defense:

| Layer | Location | Mechanism |
|-------|----------|-----------|
| Snapshot JSON key | `memory.py:2918` | Rejects `"verified_facts"` key |
| Fact JSON shape | `memory.py:2993` | Rejects `"fact_summary"` / `"evidence_anchor"` keys |
| Durable item kind | `durable/memory.py:967-969` | Rejects `"verified_fact"` item kind on read |

Tests cover:
- `test_old_snapshot_verified_facts_key_fails_closed`: JSON-level rejection with clear error message
- `test_old_durable_verified_fact_item_kind_fails_closed`: Item-level rejection via PRAGMA bypass simulation

No compatibility reads, aliases, or migration fallback present. No silent skip.

**Note on compact artifact v1 / old durable read path**: The `_validate_snapshot_item_kinds` check runs on ALL snapshot reads, not just new ones. If an old durable snapshot with `verified_fact` items exists in the database (pre-migration), it will fail to read. This is the intended "new schema start" behavior. Operational migration of old data is explicitly out of scope per the plan §11.

**Residual risk**: Acceptable. The plan explicitly states "Existing old durable snapshots are not compatible" and "Old durable snapshots / item rows fail closed by design."

### 5. max_evidence_backed_facts, dedupe/ordering, diagnostics

**Verdict**: ACCEPTABLE with one note.

- **Budget**: `_limit_evidence_backed_facts` (`memory.py:2074-2098`) drops from the beginning (oldest by insertion order), keeps last N. Diagnostic records budget enforcement.
- **Dedup**: `_replace_item_by_id` deduplicates by `(event_sequence, candidate_id)` within a compact event. Cross-compact-event deduplication is deferred to later phases (plan §11).
- **Ordering**: Item position is preserved on replace (`_replace_item_by_id` replaces in-place). New items append. This means older facts are evicted first under budget pressure.
- **Diagnostics**: Invalid/missing fact candidates produce `EVIDENCE_BACKED_FACT_CANDIDATE_INVALID` diagnostic, no fallback fact. Budget overflow produces a generic diagnostic.

**Note**: `_limit_evidence_backed_facts` does not distinguish between facts from different compact events when dropping. If facts are semantically related (e.g., all from one compact episode), dropping the oldest may orphan more recent related facts. This is behavioral, not a bug — the plan doesn't require semantic grouping.

### 6. Test coverage — S2-D1 post-compaction fact reuse

**Verdict**: ADEQUATE for Slice 5 scope.

Tests added/modified in this slice:

| Test | Coverage |
|------|----------|
| `test_context_compacted_fact_candidates_materialize_evidence_backed_facts` | Facts from compact, claim_text + evidence_refs, provenance from compact event, candidate_id is not authoritative provenance |
| `test_context_compacted_summary_can_reference_same_event_materialized_fact` | Summary confirmed_fact_refs covers newly materialized facts |
| `test_context_compacted_invalid_fact_candidates_record_diagnostic_only` | Invalid candidates → diagnostic only, no fallback fact |
| `test_context_compacted_missing_fact_candidates_record_diagnostic_only` | Missing field → diagnostic only |
| `test_minimum_preserve_candidates_create_continuity_items_only` | Minimum preserve → continuity, zero facts |
| `test_recent_raw_turns_support_followup_without_becoming_stable_fact` | Raw turns remain continuity after compact |
| `test_durable_roundtrip_uses_evidence_backed_facts_and_item_kind` | Durable write → read roundtrip, new keys and item kinds |
| `test_old_snapshot_verified_facts_key_fails_closed` | Old JSON key → ValueError |
| `test_old_durable_verified_fact_item_kind_fails_closed` | Old item kind → HostDurableError |
| `test_invalid_source_refs_do_not_create_tool_result_fact` | Updated: TOOL_RESULT_ACCEPTED → zero facts |
| `test_projection_ignores_reserved_claim_status_from_payload` | Updated: removed stale evidence_backed_facts assertion |

For S2-D1 (post-compaction fact reuse), `test_durable_roundtrip_uses_evidence_backed_facts_and_item_kind` provides the roundtrip path. Explicit post-compaction multi-event fact reuse integration test is assigned to Slice 7 (integration smoke).

---

## Unchanged but affected code audit

- `MemoryProducerKind.TOOL` remains in the enum (`memory.py:144`) but is only used in defensive assertions (working assumption and continuity items reject TOOL producer). No evidence-backed fact uses TOOL producer_kind. This is architectural — TOOL remains valid for other parts of the system.

- `MemoryClaimStatus.EVIDENCE_BACKED` is used as a hardcoded constant in `_insert_evidence_backed_fact_item` (`durable/memory.py:702`), not from `item.claim_status`. The `EvidenceBackedFactView` no longer has a `claim_status` field. This is correct.

- `_PAYLOAD_REF_PREFIX` and `_TOOL_CALL_REF_PREFIX` were removed from `memory.py` (lines 228-229 in old code). Search confirms no remaining references to these removed constants in `memory.py`.

---

## Design Contract Adherence

| Contract | Status |
|----------|--------|
| `EvidenceBackedFactView` only from CONTEXT_COMPACTED | ✅ |
| `TOOL_RESULT_ACCEPTED` → no fact | ✅ |
| Provenance from compact event id/sequence | ✅ |
| `candidate_id` is NOT authoritative provenance | ✅ |
| No neutral fallback fact | ✅ |
| Invalid candidates → diagnostic only | ✅ |
| Minimum preserve → continuity only, never facts | ✅ |
| Old `verified_facts` key rejected | ✅ |
| Old `verified_fact` item kind rejected | ✅ |
| No compatibility aliases/fallbacks | ✅ |
| Schema change is fresh, no old compat | ✅ |
| `max_evidence_backed_facts` budget enforced | ✅ |
| Durable roundtrip uses new keys/kinds | ✅ |

---

## Residual Risks

1. **Finding 1 (HIGH)**: Error masking in two-pass validation. Low probability in production (both fact and non-fact errors simultaneously are rare), but debugging cost is real. Recommended fix before Slice 7 integration.

2. **Finding 2 (MEDIUM)**: Missing bounded text enforcement at memory projection layer. Relies entirely on compaction-layer `EvidenceBackedFactCandidate` constructor. If a future code path injects raw JSON into the compact payload without going through the typed constructor, oversized text can enter the snapshot.

3. **Finding 3 (MEDIUM)**: Extra SQL query on snapshot read path. Acceptable for current scale; document as a performance note.

4. **Cross-compact-event deduplication**: Not implemented. Multiple compact events covering the same evidence could produce duplicate facts with different item_ids. The plan defers this to later phases. Not a Slice 5 issue.

5. **Old durable data migration**: Out of scope per plan §11. If old `verified_fact` item rows exist in the database, all snapshot reads will fail. This is intentional "new schema start" behavior, but the failure mode is a hard error, not a graceful migration. Operations must be aware.

---

## Verdict

**Slice 5 is code-review pass with 1 HIGH finding that should be fixed before Slice 7 integration.** The remaining 2 MEDIUM findings are defense-in-depth improvements that can be addressed in this slice or deferred with explicit acceptance. All design contracts are correctly implemented. The test coverage meets Slice 5 requirements. No silent data corruption, no backward compatibility leaks, no untyped extra payload, no neutral fallback fact generation.
