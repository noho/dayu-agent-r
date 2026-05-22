# Phase 12.5 Slice 2 Code Review — Accepted Evidence Envelope In Tool Accept Path

- **Reviewer**: AgentMiMo (independent code review)
- **Date**: 2026-05-22
- **Branch**: feat/phase-12-5-conversation-memory-optimize
- **Scope**: Uncommitted diff only
- **Plan**: docs/reviews/phase12-5-implementation-ready-plan-20260522.md
- **Accepted Slice 1**: 04b758d

## Files Reviewed

| File | Lines changed |
|------|--------------|
| `dayu/host/evidence.py` | +516 (new) |
| `dayu/host/tool_runtime.py` | +61 |
| `dayu/host/memory.py` | −9 / +4 |
| `tests/host/test_toolruntime_accept_barrier.py` | +64 |
| `tests/host/test_memory_projection.py` | −105 / +44 |

## Verification

- `pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_memory_projection.py` → **47 passed**
- `pyright dayu/host/evidence.py dayu/host/tool_runtime.py dayu/host/memory.py` → **0 errors**

## Findings

### F1 — LOW: `candidate.payload_ref` accessed without guard in `_accepted_evidence_envelope`

**File**: `dayu/host/tool_runtime.py:3552-3555`

`_accepted_evidence_envelope` accesses `candidate.payload_ref.payload_ref` with a conditional, but `candidate.payload_ref` itself could be `None`. The ternary `candidate.payload_ref.payload_ref if candidate.payload_ref is not None else None` is correct — it guards the access. This is safe.

**Verdict**: No issue. Ternary guard is correct.

### F2 — LOW: `_accepted_evidence_envelope` called before `append_event`

**File**: `dayu/host/tool_runtime.py:3473-3477`

The envelope is constructed before the event is persisted. The `result_event_id` is passed in as a deterministic pre-computed id, so the envelope's `evidence_id` and `producer_event_ref` will be consistent with the eventual stored event. If `append_event` fails, the envelope is discarded with the transaction. This is safe.

**Verdict**: No issue. Envelope construction is transactionally safe.

### F3 — INFO: REUSE path correctly skips envelope construction

**File**: `dayu/host/tool_runtime.py:3467`

The `if candidate.tool_fact_kind is ToolFactKind.REUSE: return None` guard at line 3467 means REUSE candidates never reach the envelope construction code. This is correct — REUSE does not write a new event, so no envelope is needed.

**Verdict**: No issue. Correct by design.

### F4 — INFO: JSON codec round-trip is strict

**File**: `dayu/host/evidence.py:250-302`

`accepted_evidence_envelope_from_json_value` uses `_require_exact_keys` on all three levels (envelope, tool_query, result_ref). Partial or extra fields raise `ValueError`. The test `test_accepted_evidence_envelope_codec_rejects_partial_object` confirms this. Codec is sound.

**Verdict**: No issue. Strict codec is correct.

### F5 — INFO: memory.py `pass` is correct for slice scope

**File**: `dayu/host/memory.py:1147-1150`

The `TOOL_RESULT_ACCEPTED` branch now does `pass` instead of calling `_evidence_backed_fact_from_projection_event`. This matches the controller-approved scope: "memory.py may only disable direct TOOL_RESULT_ACCEPTED fact projection; no CONTEXT_COMPACTED materialization." The comment explains the deferral clearly.

**Verdict**: No issue. Matches approved scope.

## Scope Compliance Checklist

| Requirement | Status |
|------------|--------|
| `accepted_evidence_envelope` JSON contract in TOOL_RESULT_ACCEPTED payload | PASS |
| `evidence_id` derived deterministically as `evidence:<event_id>` | PASS |
| Non-REUSE only (no envelope for REUSE candidates) | PASS |
| No business source/locator parsing in evidence module | PASS |
| No direct fact materialization from TOOL_RESULT_ACCEPTED in memory.py | PASS |
| No fallback fact | PASS |
| No public API / Engine / Fins / Service scope creep | PASS |
| Tests adequate (codec, envelope in payload, memory projection) | PASS |
| Pyright clean | PASS |

## Conclusion

**PASS** — No blocking findings. The implementation correctly introduces the `AcceptedEvidenceEnvelope` typed contract in `evidence.py`, embeds it in the `TOOL_RESULT_ACCEPTED` event payload via `tool_runtime.py`, and disables direct fact materialization in `memory.py`. All tests pass, pyright is clean, and the scope matches the approved plan.
