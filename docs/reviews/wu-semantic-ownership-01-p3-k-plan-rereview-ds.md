# WU-SEMANTIC-OWNERSHIP-01 P3-K Plan Re-Review — AgentDS

## Review Metadata

- **Reviewer**: AgentDS
- **Re-review target**: `docs/host/wu-semantic-ownership-01-p3-k-test-harness-semantic-coupling-plan.md` (fixed plan)
- **Re-review scope**: P3-K plan fix only — verify PF-01..PF-04 are closed and rejected item is respected
- **Re-review date**: 2026-07-11
- **Original plan review artifacts**:
  - `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-ds.md`
- **Controller adjudication**: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-review-controller-adjudication.md`
- **Plan fix artifact**: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-fix-codex.md`

---

## Accepted Fix Verification

### PF-01: S1 resume-guidance assertion ownership — CLOSED ✓

**Controller requirement**: Distinguish dynamic owner-derived content from production-owned guidance constants; ban vague substring checks; make shared helper optional only if justified.

**Verification against fixed plan S1**:

- **Lines 147-148**: Helper `_assert_resume_guidance_semantics(content, *, tool_name, status, result_text)` separates dynamic values (tool name, status, result text) as explicit parameters — these are owner-derived from the wait completion projection/payload, not hardcoded prose.
- **Lines 148-151**: Explicitly distinguishes two assertion classes: (a) dynamic owner-derived content assertions, (b) named production-owned guidance semantics (intro + no-repeat instruction).
- **Line 151**: "The helper must assert the named production-owned guidance semantics, not vague keyword substrings" — directly addresses the MiMo 01 concern about vague substring checks.
- **Lines 151-152**: Handles both cases for production guidance: if stable public constants exist → assert constants directly; if constants are private → keep exact expected fragments with docstring documenting owner relationship. This correctly handles the code reality — the production guidance strings at `run_input.py:3524,3528` are inline literals, not named module-level constants. The helper will use exact fragments with owner documentation.
- **Lines 152-157**: Lists 5 concrete assertion categories: prior-wait-completed intro semantics, dynamic tool name, dynamic completion status, dynamic result payload, no-repeat instruction semantics.
- **Lines 158-159**: Internal leakage negative assertions preserved.
- **Line 161**: "Do not add `tests/host/llm_text_assertions.py` unless at least two test modules need the same assertion helper with the same owner semantics. For the current `test_run_input_builder.py` resume guidance case, prefer a file-local private helper." — shared helper is optional only if cross-file reuse justifies it.
- **Lines 177-182**: Completion signal explicitly covers the resume guidance helper ownership boundary.

**Direct evidence from code**:
- `run_input.py:3524`: guidance intro is an inline string literal `"上一轮被等待中断的外部工具步骤已经完成。"`, not a named constant.
- `run_input.py:3528`: no-repeat instruction is an inline string literal, not a named constant.

**Verdict**: PF-01 is fully addressed. The plan now clearly separates dynamic from production-owned guidance, bans vague substring checks, and makes the shared helper optional only when cross-module reuse justifies it. ✓

---

### PF-02: S2 raw SQL helper final disposition list — CLOSED ✓

**Controller requirement**: Enumerate each TF-2 raw SQL helper with one final disposition; correct `read_by_host_instance_id` → `read_host_instance`; verify checkpoint helper names; update S2 completion signal to target exact-replaceable SQL only.

**Verification against fixed plan S2**:

- **Lines 205-213**: Full enumeration of 8 raw SQL helpers with final dispositions:

  | Helper | Disposition | Evidence |
  |---|---|---|
  | `public_smoke_support.py::_diagnostic_event_type_count` | keep as diagnostic-only | cross-Run count, no run-scoped production equivalent |
  | `recovery_support.py::force_owner_pid_missing_and_heartbeat_stale` | keep as fault-injection-only | production liveness APIs must not fabricate missing pid/stale heartbeat |
  | `recovery_support.py::force_memory_projection_lag` | keep as fault-injection-only | production checkpoint helpers reject backwards movement |
  | `recovery_support.py::event_type_count` | keep as diagnostic-only | same cross-Run reason as `_diagnostic_event_type_count` |
  | `recovery_support.py::projection_checkpoint_sequence` | **replace** via `read_projection_checkpoint(...)` | exact owner helper exists |
  | `stress_support.py::read_latest_event_sequence` | keep as diagnostic-only | global MAX aggregate, no production equivalent |
  | `stress_support.py::read_event_log_count` | keep as diagnostic-only | global count, no production equivalent |
  | `stress_support.py::read_host_instances` | keep as diagnostic-only | all-instance view, `read_host_instance` is single-id only |

- **Line 213**: References `HostInstanceLivenessStore.read_host_instance(transaction, host_instance_id)` — the correct method name. Confirmed: `dayu/host/durable/liveness.py:164,344` defines `read_host_instance`, not `read_by_host_instance_id`.
- **Lines 207-208, 224-226**: Checkpoint helpers verified: `read_projection_checkpoint(transaction, consumer_id)` at `projection.py:87`, `ensure_projection_checkpoint(transaction, consumer_id, *, now)` at `projection.py:117`, `advance_projection_checkpoint(transaction, consumer_id, *, event_sequence, event_id, now)` at `projection.py:152`. `force_memory_projection_lag` correctly classified as fault-injection-only because production helpers reject backwards checkpoint movement.
- **Lines 250-253**: Completion signal now reads: "Only exact-replaceable raw SQL is removed: for the current S2 scope, `projection_checkpoint_sequence(...)` is the expected replacement. Remaining raw SQL is explicitly diagnostic-only or fault-injection-only in helper names / docstrings, and each retained helper has the final disposition listed above. No production helper is added solely for tests."

**Verdict**: PF-02 is fully addressed. All 8 helpers have explicit dispositions, the incorrect API name is corrected, checkpoint helpers are verified, and the completion signal correctly targets only the one exact-replaceable helper. ✓

---

### PF-03: S3 ControllableCancellationToken contract tightened — CLOSED ✓

**Controller requirement**: Open default construction; explicit `request_cancel`; no constructor-as-cancelled; no external `.trigger()`; explicit Service handling; mandatory focused helper contract tests.

**Verification against fixed plan S3**:

- **Lines 282-284**: "`ControllableCancellationToken()` must always construct an open token: `is_cancelled()` is `False`, `cancel_reason()` is `None`, and `requested_at()` is `None`." — open by default ✓
- **Lines 284-285**: "There must be no constructor-as-cancelled semantics. Existing `StubCancellationToken(reason="...")` style call sites must become explicit two-step setup: construct an open token, then call `request_cancel("...")`." — explicitly bans the current `StubCancellationToken(reason="cancelled")` pattern where `__init__` immediately sets `_requested_at = datetime.now(UTC)` when reason is not None ✓
- **Line 285**: "`requested_at()` must return timezone-aware UTC `datetime`." — eliminates the naive `datetime.now()` from `FakeCancellationToken` ✓
- **Lines 287-288**: Mutation method is `request_cancel(reason: str = "test_cancelled")`, must transition token from open to cancelled, preserve first reason/timestamp, be idempotent ✓
- **Lines 288-289**: "Optional aliases such as `trigger()` are allowed only inside the canonical helper, only if they call `request_cancel(...)` with identical semantics, and only after all external call sites have migrated away from `.trigger(...)`." — no external `.trigger()` ✓
- **Lines 295-296**: "Default decision: use `ControllableCancellationToken()` for the existing never-cancelled Service pass-through tests; because it is open by default, callers can leave it unmutated." — explicit Service handling ✓
- **Lines 296-297**: "A local stub is allowed only if the test explicitly needs a non-mutable observation object. If retained, it must be named as an open observation stub, must have no `request_cancel` / `trigger` mutation method, and must not encode cancellation semantics beyond the `CancellationToken` observation protocol." — narrow, well-defined escape hatch ✓
- **Lines 327-333**: "Add or migrate a focused helper contract test for `ControllableCancellationToken` covering: construction starts open; `request_cancel("reason")` transitions to cancelled and exposes exact reason; `requested_at()` after cancellation is timezone-aware UTC; repeated `request_cancel(...)` calls are idempotent." — mandatory focused contract test ✓
- **Lines 335-343**: Completion signals cover all requirements: one protocol-faithful token, no naive datetime fake, Service uses canonical open token or documents stub, focused helper contract test, no external `.trigger()` ✓

**Verdict**: PF-03 is fully addressed. The `ControllableCancellationToken` contract is defined with explicit state transitions, no constructor-as-cancelled backdoor, no external `.trigger()`, and mandatory focused contract tests. ✓

---

### PF-04: README no-update branch explicit — CLOSED ✓

**Controller requirement**: Add explicit "if none of the README trigger conditions apply, record `tests/README.md: no update needed`" branch.

**Verification against fixed plan Section 6**:

- **Line 356**: "If none of those README trigger conditions apply, the implementation artifact must explicitly record `tests/README.md: no update needed`." — explicit no-update branch ✓

**Verdict**: PF-04 is fully addressed. The README trigger decision now has a complete if/else semantic — implementation always knows what to record. ✓

---

## Rejected Item Verification

**Controller rejected**: DS open question about adding `test_dispatch_scheduler.py` to S3 validation — reason: the file has its own scheduler cancellation tokens and baseline compaction previous-view failures unrelated to TF-4.

**Verification against fixed plan**:

- **Line 83-84** (Important accepted-scope limits): "P3-K must not include unrelated known failures such as baseline `tests/host/test_dispatch_scheduler.py` compaction previous-view failures unless same-path evidence appears during implementation."
- **Line 398** (Non-goals): "No attempt to fix unrelated baseline failures, including known `test_dispatch_scheduler.py` compaction previous-view failures, unless same-path evidence appears."
- **Lines 317-324** (S3 focused validation): Does NOT include `test_dispatch_scheduler.py`.

**Verdict**: Rejected item is respected. No `test_dispatch_scheduler.py` requirement was added. ✓

---

## New Material Findings

None. The fixed plan addresses all four accepted PFs completely. No new ambiguity, contradiction, or material gap was introduced by the fixes.

### Minor observation (not a material finding)

The S2 `projection_checkpoint_sequence` replacement (line 210) says to use `read_projection_checkpoint(transaction, _MEMORY_CONSUMER_ID)` through the "Host durable store transaction runner." The plan does not spell out the exact mechanism for obtaining a `HostTransaction` in `recovery_support.py`, but this is an implementation detail within normal bounds — `recovery_support.py` already uses durable store fixtures, so the transaction access pattern is established. This is not a plan defect.

---

## Final Plan Re-Review Conclusion

**PASS**

All four accepted fixes (PF-01 through PF-04) are verified closed with direct evidence from the fixed plan text:

- **PF-01** (S1 resume-guidance assertion ownership): ✓ CLOSED
- **PF-02** (S2 raw SQL helper disposition list, correct API reference, checkpoint classification, completion signal): ✓ CLOSED
- **PF-03** (S3 ControllableCancellationToken contract: open default, explicit request_cancel, no external trigger, Service handling, mandatory tests): ✓ CLOSED
- **PF-04** (README no-update branch explicit): ✓ CLOSED

The rejected item (`test_dispatch_scheduler.py` as required S3 validation) is respected.

No new material findings. The fixed plan is code-generation-ready for the implementation gate.

---

## Output Artifact

- **Path**: `docs/reviews/wu-semantic-ownership-01-p3-k-plan-rereview-ds.md`
- **Completion report**: PASS — PF-01..PF-04 are all closed; no new material finding.
