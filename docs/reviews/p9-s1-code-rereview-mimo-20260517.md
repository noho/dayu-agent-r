# P9-S1 Code Re-Review: Durable Memory Contracts and Schema

- **Reviewer**: P9-S1 code reviewer (mimo)
- **Date**: 2026-05-17
- **Branch**: `feat/host-p9-conversation-memory`
- **Previous artifact**: `docs/reviews/p9-s1-code-review-mimo-20260517.md`
- **Review scope**: updated workspace changes after fix for B1, N2, and DS C2

## Verification Results (independent)

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py` = 21 passed (was 20, +1 new test)
- `pyright dayu/host/memory.py dayu/host/durable/memory.py tests/host/test_memory_projection.py` = 0 errors
- `git diff --check` = clean

## Accepted Findings Verification

### B1. Snapshot digest includes non-deterministic `recorded_at` — FIXED

**Fix**: `_snapshot_digest_json_value` (memory.py:813) now uses `_memory_diagnostic_digest_json_value` instead of `memory_diagnostic_to_json_value`.

**New function** `_memory_diagnostic_digest_json_value` (memory.py:829-844) only includes deterministic fields:
- `event_sequence`
- `item_id`
- `message`
- `policy_digest`
- `reason`

Excluded: `diagnostic_id`, `recorded_at`. This matches the design requirement that non-deterministic timestamps must not enter digest input.

**New test** `test_snapshot_digest_ignores_nondeterministic_diagnostic_fields` (test_memory_projection.py:505-568):
- Creates two snapshots with different `diagnostic_id` ("diagnostic-a" vs "diagnostic-b"), different `recorded_at` ("2026-05-16..." vs "2026-05-17..."), and different `built_at` ("2026-05-16..." vs "2026-05-17...")
- Same semantic diagnostic content (same `reason`, `message`, `event_sequence`, `item_id`, `policy_digest`)
- Asserts `calculate_memory_snapshot_digest(first) == calculate_memory_snapshot_digest(second)`
- Correctly validates that non-deterministic fields are excluded from digest

**Verdict**: B1 RESOLVED.

### N2. Missing `ConversationContinuityItem` claim status rejection test — FIXED

**Fix**: `test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` (test_memory_projection.py:571-609) now iterates over all three reserved statuses (`CONFLICTED`, `STALE`, `SUPERSEDED`) and tests both:
- `WorkingAssumptionView` rejection (all 3 statuses)
- `ConversationContinuityItem` rejection (all 3 statuses)

This covers the full 3×2 matrix (6 test assertions), up from the original 2 assertions.

**Verdict**: N2 RESOLVED.

### N1. `MemoryIncludedReason` / `MemoryExcludedReason` naming divergence

Not addressed (non-blocking, acceptable for Slice 1). No change needed.

### N3. `MemoryDiagnostic.recorded_at` type allows `None` but durable write requires non-empty

Not addressed (non-blocking, type surface issue). No change needed.

## DS C2 Concern: `snapshot_id` in `conversation_memory_snapshot_to_json_value`

The durable JSON serialization (`conversation_memory_snapshot_to_json_value`) includes `snapshot_id` in its output. This is correct — `snapshot_id` is part of the durable storage representation and must be persisted. It is correctly excluded from `_snapshot_digest_json_value` (the digest-specific function). The two functions serve different purposes:
- `conversation_memory_snapshot_to_json_value`: full durable representation (includes `snapshot_id`, `built_at`, `snapshot_digest`)
- `_snapshot_digest_json_value`: digest-only input (excludes `snapshot_id`, `built_at`, `snapshot_digest`, `diagnostic_id`, `recorded_at`)

No issue found.

## New Blocking Issues

None.

## Re-review Scope Check

| Item | Status |
|------|--------|
| B1 fix verified | RESOLVED |
| N2 fix verified | RESOLVED |
| DS C2 concern checked | NO ISSUE |
| No new blocking issues | CONFIRMED |
| Tests pass (21/21) | CONFIRMED |
| pyright clean | CONFIRMED |
| git diff --check clean | CONFIRMED |

## Remaining Non-blocking Findings

- **N1**: `MemoryIncludedReason`/`MemoryExcludedReason` naming divergence from plan (acceptable for S1)
- **N3**: `MemoryDiagnostic.recorded_at` type allows `None` but durable write requires non-empty (type surface issue)

## Verdict

**PASS** — All blocking findings resolved. No new blocking issues.

## Remaining Blocking Findings Count

**0**
