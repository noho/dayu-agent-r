# P9-S1 Code Review: Durable Memory Contracts and Schema

- **Reviewer**: P9-S1 code reviewer (mimo)
- **Date**: 2026-05-17
- **Branch**: `feat/host-p9-conversation-memory`
- **Review scope**: workspace uncommitted changes
- **Design truth**: `docs/host/design.md` §23/§24/§26
- **Control truth**: `docs/host/implementation-control.md` Phase 9
- **Plan truth**: `docs/host/phase9-conversation-memory-plan.md` Slice 1

## Files Reviewed

| File | Lines | Verdict |
|------|-------|---------|
| `dayu/host/memory.py` | ~1406 | CONDITIONAL PASS |
| `dayu/host/durable/memory.py` | ~710 | PASS |
| `dayu/host/durable/schema.py` | ~974 | PASS |
| `tests/host/test_memory_projection.py` | ~535 | PASS |
| `tests/host/test_durable_schema.py` | ~714 | PASS |
| `docs/host/implementation-control.md` status update | ~3 lines | PASS |

## Verification Results (independent)

- `pytest tests/host/test_memory_projection.py tests/host/test_durable_schema.py` = 20 passed
- `pytest tests/host/test_weak_typing_guard.py` = 1 passed
- `pyright dayu/host tests/host` = 0 errors
- `git diff --check` = clean

## Blocking Findings

### B1. Snapshot digest includes non-deterministic `recorded_at`

**Severity**: Correctness / Stability
**File**: `dayu/host/memory.py:807-810`
**Evidence**: `_snapshot_digest_json_value` includes diagnostics via `memory_diagnostic_to_json_value` (line 808), which emits `recorded_at` (line 732). `recorded_at` is a timestamp set at write time.

**Design requirement** (`phase9-conversation-memory-plan.md` §4.7):
> "`built_at`、`updated_at`、projection 写入时间等非确定性字段不得进入 digest input。"

**Impact**: In Slice 2+ when diagnostics are populated, rebuilding the same EventLog + policy at different times will produce different `recorded_at` values, breaking the invariant "同一 EventLog + 同一 policy 生成稳定 snapshot digest" (`design.md` §24 invariants). The empty snapshot path in Slice 1 is unaffected because diagnostics are always empty.

**Fix guidance**: `_snapshot_digest_json_value` should either:
- Strip `recorded_at` and `diagnostic_id` from each diagnostic before including in digest, or
- Use a dedicated `_snapshot_digest_diagnostic_json_value` that only includes deterministic diagnostic fields (`reason`, `message`, `event_sequence`, `item_id`, `policy_digest`).

## Non-blocking Findings

### N1. `MemoryIncludedReason` / `MemoryExcludedReason` naming divergence from plan

**Severity**: Minor
**File**: `dayu/host/memory.py:68-86`

The plan §4.8 specifies `PINNED_STATE_REQUIRED`, `VERIFIED_FACT_REQUIRED`, `WORKING_ASSUMPTION_REQUIRED`, etc. The implementation uses `PINNED_STATE`, `TOOL_VERIFIED_FACT`, `WORKING_ASSUMPTION`, `BUDGET_LIMIT`, `POLICY_EXCLUDED`. These are semantically reasonable simplifications but diverge from the accepted plan's naming.

**Recommendation**: Acceptable for Slice 1 contracts. If downstream consumers (trace, audit) reference these names, naming should stabilize before Slice 2.

### N2. Missing `ConversationContinuityItem` claim status rejection test

**Severity**: Minor (test completeness)
**File**: `tests/host/test_memory_projection.py:502-534`

`test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` tests `WorkingAssumptionView` rejection of `CONFLICTED` and `ConversationContinuityItem` rejection of `STALE`. Per the plan §4.2, P9 must not synthesize `CONFLICTED`, `STALE`, or `SUPERSEDED`. The test should also verify:
- `ConversationContinuityItem` rejection of `CONFLICTED` and `SUPERSEDED`
- `WorkingAssumptionView` rejection of `STALE` and `SUPERSEDED`

The Python contracts do enforce this (both require `ASSUMPTION`), but test coverage is partial.

### N3. `MemoryDiagnostic.recorded_at` type allows `None` but durable write requires non-empty

**Severity**: Minor (type surface)
**File**: `dayu/host/memory.py:446` vs `dayu/host/durable/memory.py:539`

`MemoryDiagnostic.recorded_at: str | None` allows `None`, but `_insert_memory_diagnostic` calls `_require_non_empty_text(recorded_at)` which rejects `None`. The error message ("must be non-empty") is slightly misleading for a `None` input. This is not a runtime bug since all construction paths provide a value, but the type surface is misleading.

## Scope Compliance

### Slice 1 boundary (no越界)

| Slice 2+ item | Present in S1? | Status |
|---------------|---------------|--------|
| Projection consumer | No | CORRECT |
| RunInputBuilder provider | No | CORRECT |
| Memory repair path | No | CORRECT |
| Stable layer / history pool builder | No | CORRECT |
| After-commit catch-up hook | No | CORRECT |

### Design compliance

| Requirement | Status |
|-------------|--------|
| `snapshot_digest` excludes `built_at`, `snapshot_id`, `snapshot_digest` | PASS |
| `snapshot_digest` excludes `recorded_at` / non-deterministic timestamps | **FAIL (B1)** |
| Verified facts only accept TOOL provenance | PASS (contract enforces) |
| P9 does not synthesize CONFLICTED/STALE/SUPERSEDED | PASS (contract enforces) |
| `PinnedStateView.open_questions` not duplicated in WorkingAssumption | PASS |
| `OpaqueMemoryRef.ref_kind` Host-neutral only | PASS |
| No business-specific fields in contracts | PASS |
| No `dayu.fins` / `dayu.engine` / `dayu.service` / `dayu.ui` imports | PASS |
| No `Any` / `object` / untyped signatures | PASS |
| Chinese docstrings complete | PASS |
| Schema v6 / fresh bootstrap / no old compat | PASS |
| FK/CHECK constraints correct | PASS |
| Snapshot + checkpoint same transaction | PASS |
| ON DELETE CASCADE for items/diagnostics | PASS |
| `MEMORY_PROJECTION_TABLES` merged into `HOST_DURABLE_TABLES` | PASS |
| Index design matches plan | PASS |

### Host boundary

| Boundary | Status |
|----------|--------|
| No import of `dayu.fins` | PASS |
| No business原文 saved | PASS |
| No company/business_line/technology_release in schema | PASS |
| `HostNeutralRefKind` is Host-neutral enum | PASS |
| Contracts don't expose business-specific fields | PASS |

## Schema Review

- `HOST_SCHEMA_VERSION` bumped from 5 to 6: CORRECT.
- Three new tables: `host_memory_snapshots`, `host_memory_items`, `host_memory_diagnostics`: CORRECT.
- All tables have proper PRIMARY KEY.
- `host_memory_items` FK to `host_memory_snapshots(snapshot_id) ON DELETE CASCADE`: CORRECT.
- `host_memory_diagnostics` FK to `host_memory_snapshots(snapshot_id) ON DELETE CASCADE`: CORRECT.
- `host_memory_items` FK to `event_log(event_id)` and `event_log(event_sequence)`: CORRECT.
- `host_memory_snapshots` CHECK for cursor consistency (sequence=0 -> event_id IS NULL): CORRECT.
- `host_memory_items` CHECK for `included_reason IS NULL OR excluded_reason IS NULL`: CORRECT.
- `host_memory_items` CHECK for payload_ref/payload_digest pairing: CORRECT.
- `item_kind` CHECK allows all `ConversationContinuityKind` values plus `verified_fact` and `working_assumption`: CORRECT.
- `claim_status` CHECK allows all 6 `MemoryClaimStatus` values (including reserved ones for issue 39): CORRECT.
- Indexes cover session/cursor/policy lookup, session/sequence/kind lookup, session/reason/recorded_at lookup: CORRECT.
- No outbox or purge tables created: CORRECT.

## Durable Memory Read/Write Review

- `write_memory_snapshot`: writes snapshot content + items + diagnostics in single transaction; does NOT advance checkpoint. CORRECT.
- `write_memory_snapshot_with_checkpoint`: calls `write_memory_snapshot` then advances checkpoint. Both in same transaction (caller's responsibility). CORRECT.
- `read_memory_snapshot` / `read_latest_memory_snapshot`: transaction-scoped reads. CORRECT.
- `_replace_memory_items`: DELETE + INSERT pattern within transaction. CORRECT.
- `_validate_snapshot_digest`: recalculates digest on read and write, raises `HostDurableError` on mismatch. CORRECT.
- All functions accept `HostTransaction` (caller-owned), do not create their own transactions. CORRECT.

## Test Coverage Assessment

| Plan requirement | Test | Status |
|-----------------|------|--------|
| Schema creates memory tables/indexes | `test_memory_projection_tables_and_indexes_are_created` | PASS |
| HOST_SCHEMA_VERSION fresh bootstrap | `test_fresh_db_creates_foundation_phase8_and_memory_tables` | PASS |
| Typed contract rejects empty id | `test_typed_contracts_reject_invalid_ids_cursor_and_verified_fact` | PASS |
| Verified fact non-TOOL rejected | `test_typed_contracts_reject_invalid_ids_cursor_and_verified_fact` | PASS |
| PinnedStateView.open_questions not in WorkingAssumption | `test_pinned_state_open_questions_are_not_duplicated` | PASS |
| OpaqueMemoryRef Host-neutral only | `test_host_neutral_ref_kind_rejects_business_specific_kind` | PASS |
| No business-specific fields | `test_memory_contracts_do_not_expose_business_specific_fields` | PASS |
| MemoryDiagnostic durable round-trip | `test_memory_diagnostic_contract_round_trips_through_durable_store` | PASS |
| P9 doesn't synthesize CONFLICTED/STALE/SUPERSEDED | `test_p9_contracts_do_not_synthesize_conflict_stale_or_superseded` | PARTIAL (N2) |
| Empty snapshot create + read | `test_empty_event_log_snapshot_can_be_created_and_read` | PASS |
| Snapshot + checkpoint rollback together | `test_snapshot_and_checkpoint_rollback_together` | PASS |
| Schema rejects invalid rows | `test_memory_schema_constraints_reject_invalid_rows` | PASS |
| No future sink tables | `test_schema_does_not_create_unowned_future_sink_tables` | PASS |
| Schema mismatch rejects | `test_schema_mismatch_raises_structured_error` | PASS |
| Bootstrap idempotent | `test_bootstrap_is_idempotent_for_matching_schema` | PASS |
| WAL persists | `test_wal_persists_on_second_independent_connection` | PASS |
| Schema constraints explicit | `test_schema_constraints_are_explicit` | PASS |
| Projection constraints reject invalid | `test_projection_schema_constraints_reject_invalid_rows` | PASS |
| FK parent key works | `test_event_sequence_is_sqlite_foreign_key_parent_key` | PASS |

## Verdict

**CONDITIONAL PASS** — 1 blocking finding (B1), 3 non-blocking findings.

B1 is a correctness issue that will break digest stability in Slice 2 when diagnostics are populated. It should be fixed before or during Slice 2 implementation. The fix is localized to `_snapshot_digest_json_value` in `dayu/host/memory.py`.

## Blocking Findings Count

**1** (B1: snapshot digest includes non-deterministic `recorded_at`)
