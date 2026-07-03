# WU-WAIT-03 Plan Review — AgentMiMo

**Reviewer**: AgentMiMo
**Timestamp**: 20260703-110108
**Plan artifact**: `docs/host/wu-wait-03-external-job-lifecycle-plan.md`
**Review gate**: plan review
**Design sources**: `docs/host/design.md`, `docs/engine/design.md`
**Control doc**: `docs/host/issues-implementation-control.md`

---

## 1. Reviewed Target and Scope

Plan artifact `docs/host/wu-wait-03-external-job-lifecycle-plan.md` covering:
- Typed lifecycle result union for `WaitPollAdapter.abandon_wait`
- Wait poller cancelled wait path handling for applied / unsupported / noop results
- Fins adapter mapping to new lifecycle result contract
- 2 implementation slices

## 2. Assumptions Tested

| # | Assumption | Verdict |
|---|---|---|
| A1 | Host cancellation correctness already established; gap is adapter contract expressiveness | **Confirmed** — code evidence in `cancel_waiting_run_in_transaction` and `_abandon_cancelled_wait` |
| A2 | `abandon_wait` return type change from `None` to typed union is safe | **Confirmed** — current callers discard return value; Protocol change is compatible |
| A3 | `WaitPollLastOutcome` enum extension is additive and safe | **Confirmed** — `StrEnum` serialization in `state.py` handles unknown values via `_deserialize_str_enum` |
| A4 | No new durable schema needed | **Confirmed** — existing `poll_last_outcome`, `poll_abandoned_at` fields suffice |
| A5 | Engine boundary not violated | **Confirmed** — Engine design §12 explicitly states Engine does not own external job lifecycle |
| A6 | 2 slices are sufficient | **Confirmed** — follows control doc Slice 切分原则 for small cross-module cleanup |

## 3. Findings

### Finding 01: `WaitPollLastOutcome` new enum values lack serialization roundtrip evidence

- **位置**: Contract / Schema section, "Add `WaitPollLastOutcome` values only if needed"
- **问题类型**: 契约缺失
- **当前写法**: Plan says "If adding `WaitPollLastOutcome.ABANDON_UNSUPPORTED` / `ABANDON_NOOP`, update serialize / deserialize validation and row invariant checks in `dayu/host/durable/state.py`"
- **反例/失败场景**: `deserialize_wait_poll_last_outcome` calls `_deserialize_str_enum` which validates against enum members. If new values are added to the enum but old DB rows contain `ABANDONED` (which remains), no issue. But if implementation adds the values to enum without verifying `_validate_wait_poll_fields` accepts them, pyright or runtime validation could reject rows with new outcome values.
- **为什么有问题**: Plan is code-generation-ready on the contract level but the "if adding" phrasing makes the enum extension optional, which could lead to inconsistent implementations. The implementation agent needs to know definitively whether to add these values.
- **直接证据**: `state.py:176-186` — `WaitPollLastOutcome` enum. `state.py:678-701` — serialize/deserialize functions. `state.py:5726-5729` — `_validate_wait_poll_fields` checks `isinstance(row.poll_last_outcome, WaitPollLastOutcome)`.
- **影响**: Low — implementation agent may hesitate on whether to add enum values. The "if adding" language is ambiguous but not blocking since the plan does specify the state-machine transitions for each case.
- **建议改法和验证点**: Remove "if adding" / "only if needed" conditional language. Commit to adding `ABANDON_UNSUPPORTED` and `ABANDON_NOOP` since the plan already specifies state-machine transitions for them. Or explicitly state they are deferred.
- **修复风险**: 低
- **严重程度**: 低
- **裁决建议**: `accepted` — minor clarification, does not block implementation

### Finding 02: `_abandon_cancelled_wait` durable write path for unsupported/noop not fully specified

- **位置**: State-machine changes section, "WaitPoller cancelled wait path"
- **问题类型**: code-generation-ready 不足
- **当前写法**: Plan says for unsupported/noop: "mark no further lifecycle retry, using `poll_last_outcome=ABANDON_UNSUPPORTED` if added" / "mark lifecycle terminal diagnostic and stop retrying"
- **反例/失败场景**: Current `_abandon_cancelled_wait` in `wait_adapter.py:921-932` calls `mark_wait_record_poll_abandoned` which writes `poll_abandoned_at` and sets `poll_last_outcome=ABANDONED`. For unsupported/noop, the implementation agent needs to know: should it reuse `mark_wait_record_poll_abandoned` (which hardcodes `ABANDONED`), or create a new durable write function that writes `poll_abandoned_at` with a different outcome?
- **为什么有问题**: The current `mark_wait_record_poll_abandoned` in `state.py:2202-2260` hardcodes `serialize_wait_poll_last_outcome(WaitPollLastOutcome.ABANDONED)`. If the implementation agent needs to write `ABANDON_UNSUPPORTED` or `ABANDON_NOOP` as the outcome while still setting `poll_abandoned_at`, they need either a new function or a parameterized version.
- **直接证据**: `state.py:2239-2250` — SQL hardcodes `poll_last_outcome = ?` with `serialize_wait_poll_last_outcome(WaitPollLastOutcome.ABANDONED)`. `wait_adapter.py:922-928` — `_MarkWaitRecordAbandonedOperation` calls this function.
- **影响**: Medium — implementation agent must design a new durable write path or generalize the existing one. This is a design decision that should be in the plan, not left to the implementer.
- **建议改法和验证点**: Plan should specify: (1) generalize `mark_wait_record_poll_abandoned` to accept a `WaitPollLastOutcome` parameter, or (2) create `mark_wait_record_poll_terminal` that accepts outcome + `poll_abandoned_at`. The plan's invariant "poll_abandoned_at or equivalent terminal lifecycle marker only applies to status=cancelled" suggests option (1) is preferred.
- **修复风险**: 低
- **严重程度**: 中
- **裁决建议**: `accepted` — implementation agent needs this design decision to be code-generation-ready

### Finding 03: Fins `abandon_wait` error handling for non-TRANSIENT errors maps to implicit noop

- **位置**: Slice 2, Fins adapter behavior specification
- **问题类型**: 契约缺失
- **当前写法**: Plan lists: valid handle → applied, corrupt token → noop, TRANSIENT_UNAVAILABLE → re-raise. But does not explicitly state the mapping for non-TRANSIENT `FinsObservationPollError` during `cancel_observation` or `abandon_observation`.
- **反例/失败场景**: Current code in `fins/ingestion/wait_adapter.py:155-157` catches `FinsObservationPollError` and only re-raises if `TRANSIENT_UNAVAILABLE`. All other error kinds are silently swallowed (returns `None`). After the contract change, the implementation agent needs to decide: return `Noop` (since the error was non-fatal and we're being best-effort) or re-raise (to let the poller retry)?
- **为什么有问题**: The plan's state-machine says "exception → release claim with ABANDON_ERROR backoff; no poll_abandoned_at". But the current Fins adapter swallows non-TRANSIENT errors silently. The implementation agent must decide whether to change this behavior.
- **直接证据**: `fins/ingestion/wait_adapter.py:152-157` — `except FinsObservationPollError as exc: if exc.error_kind is FinsObservationPollErrorKind.TRANSIENT_UNAVAILABLE: raise` (other errors silently ignored).
- **影响**: Low — the current behavior is "silent noop" which is reasonable for best-effort cleanup. But the plan should explicitly state this mapping.
- **建议改法和验证点**: Add explicit mapping: "Non-TRANSIENT `FinsObservationPollError` during cancel/abandon → return `Noop(reason=error_kind.value)` since best-effort cleanup already attempted partial work."
- **修复风险**: 低
- **严重程度**: 低
- **裁决建议**: `accepted` — minor clarification for code-generation readiness

### Finding 04: `WaitPollOnceResult.abandoned` semantics may need extension for unsupported/noop

- **位置**: Slice 1, "Update _abandon_cancelled_wait" section
- **问题类型**: 契约缺失
- **当前写法**: Plan says unsupported/noop results "mark lifecycle terminal diagnostic and stop retrying" but does not specify whether these increment the `abandoned` counter in `WaitPollOnceResult`.
- **反例/失败场景**: Current `_abandon_cancelled_wait` returns `(1, 0, 0, 0)` for successful abandon (abandoned=1). For unsupported/noop, should the poller also count them as `abandoned`? Or introduce a new counter? The `WaitPollerDiagnosticsSnapshot` aggregates these counters.
- **为什么有问题**: `WaitPollOnceResult` is a public contract within the Host module. Changing its semantics (what counts as "abandoned") affects diagnostics and test assertions.
- **直接证据**: `wait_adapter.py:306-327` — `WaitPollOnceResult` dataclass with `abandoned: int` field. `wait_adapter.py:931` — returns `(1, 0, 0, 0)` for successful abandon.
- **影响**: Low — diagnostics contract change, not correctness-critical. But should be specified.
- **建议改法和验证点**: Plan should specify: unsupported/noop lifecycle results increment `abandoned` counter (since the wait record is terminally marked), or introduce `lifecycle_terminal` as a separate counter.
- **修复风险**: 低
- **严重程度**: 低
- **裁决建议**: `accepted` — minor diagnostics contract clarification

## 4. Open Questions

None — all findings are actionable within the plan scope.

## 5. Residual Risks

| Risk | Owner | Destination |
|---|---|---|
| Real providers may not support physical cancel | Provider-specific adapter owners | #92 / #87 |
| Poller disabled deployments skip external lifecycle | Service/composition deployment | WU-WAIT-04 |
| Running Fins operations only observe cooperative cancel at checkpoints | Fins provider/runtime owners | Current WU |

## 6. Architecture Boundary Review

**Verdict: Pass**

- Host/Engine boundary strictly maintained: Engine does not own wait/cancel/poll/external lifecycle (confirmed by `docs/engine/design.md` §12)
- Host command cancel path does not do provider I/O (confirmed by `cancel_waiting_run_in_transaction` in `run_transition.py`)
- `resolve_wait(...)` remains the only late result path (confirmed by plan invariant and existing code)
- No new public Host API, Engine contract, durable schema, provider capability registry, or second watchdog introduced

## 7. Best-Practice Review

**Verdict: Pass**

- Typed union for adapter results is the right pattern (closed union, not `Any` or `object`)
- Reuses existing poller/backoff infrastructure
- Chinese docstrings required per project convention
- No `Any`, `object`, untyped parameters introduced

## 8. Optimal-Solution Review

**Verdict: Pass**

- The plan is the minimal solution that addresses the root cause: adapter contract expressiveness
- Alternatives considered and rejected: new public Host API (over-engineering), provider capability registry (over-engineering), durable schema changes (unnecessary)
- The approach of extending the existing adapter Protocol with a typed return is the most maintainable path

## 9. Overengineering Review

**Verdict: Pass**

- No unnecessary abstractions, layers, builders, wrappers, protocols, migrations, or generalization
- The `WaitExternalJobLifecycleAction` enum with `CANCEL`, `REVOKE`, `ABANDON` is slightly forward-looking but justified by the issue title "physical cancel / revoke / abandon"
- No new durable tables, columns, or schema

## 10. Overcoupling Review

**Verdict: Pass**

- Slice 1 (Host contract) and Slice 2 (Fins adapter) are cleanly separated by the Protocol boundary
- No cross-layer coupling introduced
- Changes are localized to adapter contract + poller handling + provider mapping

---

## Final Plan Review Conclusion

**Verdict: `pass-with-findings`**

**Blocking findings**: 0

**Non-blocking findings**: 4
- F01: `WaitPollLastOutcome` conditional language (低)
- F02: Durable write path for unsupported/noop not fully specified (中)
- F03: Fins non-TRANSIENT error mapping implicit (低)
- F04: `WaitPollOnceResult.abandoned` counter semantics for new outcomes (低)

**Residual risks**: 3 (all deferred-with-owner, consistent with plan non-goals)

**Summary**: Plan is code-generation-ready for the core contract and state-machine changes. The 4 findings are clarifications that would improve implementation precision but do not block the plan. F02 (durable write path) is the most substantive — the implementation agent needs to know whether to generalize `mark_wait_record_poll_abandoned` or create a new function. The plan's overall design is sound, correctly scoped, and aligned with Host/Engine boundaries.

---

## Artifact Output

- **Output file**: `docs/reviews/wu-wait-03-plan-review-mimo.md`
- **Files modified**: Only this review artifact. No changes to plan, production code, tests, control doc, or other files.
