# Code Review: Host Phase 1 Slice 1 — `dayu.host` Public API Typed Contracts

## Review Metadata

- **Reviewer**: AgentMiMo
- **Review Gate**: code review
- **Work Unit**: Host Phase 1 公共契约与 runtime 基础设施
- **Assigned Slice**: Slice 1: `dayu.host` public API typed contracts
- **Approved Plan**: `docs/host/phase1-public-contract-runtime-plan.md`
- **Implementation Artifact**: `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`
- **Accepted Plan Commit**: 34b1b41
- **Diff Scope**: uncommitted workspace changes after controller state commit 1255da8
- **Review Date**: 2026-05-13

## Review Scope

Files reviewed:

- `dayu/host/__init__.py`
- `dayu/host/api.py`
- `tests/host/__init__.py`
- `tests/host/test_package_exports.py`
- `tests/host/test_public_contracts.py`
- `tests/host/test_import_boundary.py`
- `tests/host/test_weak_typing_guard.py`
- `dayu/host/README.md`
- `dayu/README.md`
- `tests/README.md`
- `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`

## Validation Re-Run

- `pytest tests/host -q`: **14 passed in 0.08s**
- `python -m pyright dayu/host tests/host`: **0 errors, 0 warnings, 0 informations**

## Review Checklist

### 1. Public API Type List Completeness

**Status: PASS**

Plan Slice 1 requires 35 public types. Implementation in `dayu/host/api.py` provides exactly 35 types:

| Category | Types | Count |
|----------|-------|-------|
| Status / enum | `SessionStatus`, `RunStatus`, `AttemptStatus`, `FollowupBehavior`, `CancelMode`, `WaitResolutionSource`, `SourceRunRelation`, `HostApiErrorCode` | 8 |
| Context / input | `OperationContext`, `AuthorizationClaim`, `HostCallContext`, `HostMetadataEntry`, `HostInput`, `SessionSlotRef`, `HostStreamCursor` | 7 |
| Command handle | `HostCommandFacet` | 1 |
| Requests | `EnsureSessionRequest`, `CreateSessionRequest`, `CloseSessionRequest`, `PurgeSessionRequest`, `StartRunRequest`, `CancelRunRequest`, `CancelSessionRunsRequest`, `SubmitFollowupRequest`, `RetryRunRequest`, `ReplayRunRequest`, `ResolveWaitRequest` | 11 |
| Snapshots / stream | `TerminalResultSummary`, `OutboxSummary`, `SessionSnapshot`, `RunSnapshot`, `FollowupSnapshot`, `PurgeSessionResult`, `HostEventView`, `HostEventStream` | 8 |
| Error | `HostApiError` | 1 |

No types are missing. No extra types are added.

### 2. Exports Consistency

**Status: PASS**

- `dayu/host/api.py` `__all__`: 35 symbols — matches plan exactly.
- `dayu/host/__init__.py` `__all__`: 35 symbols — identical set.
- `dayu/host/__init__.py` re-exports all symbols directly from `dayu.host.api` via explicit import.
- `tests/host/test_package_exports.py` asserts `frozenset(host.__all__) == EXPECTED_EXPORTS` and `frozenset(api.__all__) == EXPECTED_EXPORTS` and verifies identity (`vars(host)[name] is vars(api)[name]`).

### 3. Frozen Dataclass / Slots

**Status: PASS**

All 25 dataclass types use `@dataclass(frozen=True, slots=True)`. `test_dataclasses_are_frozen_and_slots()` verifies `is_dataclass`, `__slots__` presence, and `FrozenInstanceError` on mutation.

`HostApiError` correctly uses a plain class (Exception subclass) — not a dataclass — which is the plan-required exception.

`HostCommandFacet` is a `Protocol` — not a dataclass — which is correct per plan.

### 4. Enum Values Stability

**Status: PASS**

All 8 enums use `enum.StrEnum`. `test_status_and_error_enum_values_are_stable()` exhaustively verifies every member name and value for all 8 enums. Values are stable snake_case strings matching the plan specification.

### 5. `HostMetadataEntry.value` Uses `JsonValue`

**Status: PASS**

`HostMetadataEntry.value: JsonValue` — correctly imports from `dayu.contracts.json_value`.

### 6. `HostCommandFacet` Minimal Shape

**Status: PASS**

`HostCommandFacet(Protocol)` exposes only `@property def host_handle_id(self) -> str: ...`. No store, policy, tool runtime, or other Host implementation details.

### 7. Validation Rules

**Status: PASS**

All plan-required validation rules are implemented in `__post_init__` methods using module-level private helpers:

| Rule | Implementation | Test Coverage |
|------|---------------|---------------|
| Empty id / name / reason | `_require_non_empty` | `test_empty_id_validation_failure_path` |
| Negative cursor | `_require_non_negative` | `test_invalid_cursor_validation_failure_path` |
| STEER requires `target_run_id` | Conditional check | `test_steer_requires_target_run_id` |
| QUEUE rejects `target_run_id` | Conditional check | `test_queue_rejects_target_run_id` |
| `bind_slot=True` requires scope + slot_key | Conditional check | `test_bind_slot_requires_scope_and_slot_key` |
| Cancel mode GRACEFUL only | `_require_graceful_cancel` | Implicit via enum design |
| Metadata key non-empty | `_require_metadata_entries` | `test_metadata_key_validation_failure_path` |

### 8. No `Any` / `object` / Untyped Signatures

**Status: PASS**

`tests/host/test_weak_typing_guard.py` performs AST-level scanning of all `dayu/host/` source files and rejects:
- `Any` / `object` in annotations
- Missing parameter annotations (except `self` / `cls`)
- Missing return annotations (except `__init__`)
- Bare builtin generics (`dict`, `list`, `tuple`, `set`, `frozenset` without type parameters)

All production code and test code signatures are fully typed.

### 9. Import Boundary

**Status: PASS**

`tests/host/test_import_boundary.py` scans all `.py` files under `dayu/host/` via AST and asserts no import of `dayu.engine`, `dayu.fins`, `dayu.service`, or `dayu.ui`.

Actual imports in `dayu/host/api.py`: only `dataclasses`, `enum`, `typing`, and `dayu.contracts.json_value` — all allowed.

### 10. Chinese Docstrings

**Status: PASS**

All modules, classes, functions, and `__post_init__` methods have Chinese docstrings. Class docstrings include field semantics. Validation helpers document `:param`, `:returns`, `:raises`.

### 11. README Accuracy

**Status: PASS**

- `dayu/host/README.md`: Documents current public types, validation rules, architecture boundary, and non-goals. No future implementation details leaked.
- `dayu/README.md`: `dayu.host` section correctly states current exported type categories and non-goals. No future plans documented as current capability.
- `tests/README.md`: `tests/host/` section accurately describes current test coverage and running commands.

### 12. Implementation Artifact Accuracy

**Status: PASS**

The implementation artifact at `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md` correctly reports:
- Changed files match actual changes
- Plan items implemented match actual code
- Validation results match re-run results (14 passed, 0 pyright errors)
- Non-goals are correctly listed
- Residual risks are appropriately classified as later slices

## Findings

### Finding 1 — Minor: `CreateSessionRequest` validates scope/slot_key when `bind_slot=False`

- **Severity**: Minor (non-blocking)
- **File**: `dayu/host/api.py:488-494`
- **Description**: When `bind_slot=False`, the `__post_init__` still calls `_require_optional_non_empty` on `scope` and `slot_key`. This means empty strings (e.g., `scope=""`) are rejected even when the caller explicitly opts out of slot binding. The plan states "bind_slot=False 时二者可以为 None" — the implementation is stricter than required by also rejecting empty strings.
- **Impact**: No functional impact. The implementation is more defensive than the plan minimum. Empty strings are semantically invalid for these fields regardless of `bind_slot`, so the extra validation is arguably correct behavior.
- **Test Gap**: `test_bind_slot_requires_scope_and_slot_key` only tests the `bind_slot=True` path. No test verifies behavior when `bind_slot=False` with empty-string scope/slot_key.
- **Recommendation**: Accept as-is. The stricter validation is a reasonable design choice. No action required.

## Architecture Boundary Verification

- `dayu.host` does not import `dayu.engine`, `dayu.fins`, `dayu.service`, or `dayu.ui`: **VERIFIED**
- `dayu.host.api` only imports from `dataclasses`, `enum`, `typing`, `dayu.contracts.json_value`: **VERIFIED**
- No Engine, Fins, Service, or UI files were modified: **VERIFIED**
- No durable store, EventLog, dispatch record, policy provider, runtime lane, runtime filelock, HostToolingOptions, or ToolBundle options were created: **VERIFIED**

## Summary

| Metric | Value |
|--------|-------|
| Finding 数量 | 1 |
| Blocking finding 数量 | 0 |
| Tests passing | 14/14 |
| Pyright errors | 0 |
| Plan compliance | Full |

## Recommendation

**Proceed to user confirmation.** No blocking findings. The single minor finding (stricter-than-plan validation on `CreateSessionRequest` when `bind_slot=False`) is acceptable as defensive behavior and does not require remediation.

The implementation faithfully executes the approved plan Slice 1 scope: all 35 public types are present, correctly structured, properly validated, fully tested, and accurately documented. Import boundaries are clean. No architecture violations detected.
