# Phase 15 S2 Code Review Controller Adjudication

## Gate

Phase 15 S2 code review adjudication.

Reviewed artifacts:
- `docs/reviews/phase15-s2-code-review-mimo-20260529.md`
- `docs/reviews/phase15-s2-code-review-ds-20260529.md`

Implementation artifact:
- `docs/reviews/phase15-s2-implementation-codex-20260529.md`

## Controller Conclusion

S2 implementation is broadly correct and within scope, but several findings must be fixed before S2 closeout. Most importantly, projection checkpoint/failure reset must enforce the plan's rebuildable-consumer criterion in this slice, not defer it to S5, because S2 owns the delete matrix helper and its FK-safe reset semantics.

## Accepted Findings

### S2-ADJ-001 accepted — projection checkpoint reset lacks rebuildable consumer filter

Source: `docs/reviews/phase15-s2-code-review-ds-20260529.md` F11.

Decision: accepted.

Reason: The approved plan explicitly says projection checkpoint/failure reset is allowed only for rebuildable projection/sink consumers. Resetting every consumer whose checkpoint references target EventLog could erase non-rebuildable governance/diagnostic state or hide an unsupported durable dependency.

Required fix:
- Add an explicit allowed consumer set for purge reset.
- Delete checkpoint/failure rows only when their consumer id is in that set and the referenced EventLog belongs to the purged Session.
- If a non-allowed consumer checkpoint/failure references a target EventLog row, return/raise a durable inconsistency or equivalent `HostDurableError` before EventLog deletion rather than silently resetting it.
- Add focused tests for allowed reset and unsupported consumer rejection/rollback.

### S2-ADJ-002 accepted — redundant target run id reads

Source: `docs/reviews/phase15-s2-code-review-mimo-20260529.md` FINDING-1.

Decision: accepted.

Reason: This is a low-risk maintainability fix inside a hot transaction helper. Caching the run id tuple avoids repeated identical queries and reduces chances of later divergence.

Required fix:
- Cache `_read_target_run_ids(...)` result in `_build_purge_precondition_digest(...)`.

### S2-ADJ-003 accepted — missing blank lines between top-level definitions

Source: `docs/reviews/phase15-s2-code-review-mimo-20260529.md` FINDING-2.

Decision: accepted.

Reason: The fix is mechanical, local, and reduces style churn before later reviews.

Required fix:
- Add the missing top-level blank lines identified by the reviewer.

### S2-ADJ-004 accepted — non-terminal rejection should assert tombstone absence

Source: `docs/reviews/phase15-s2-code-review-mimo-20260529.md` FINDING-5.

Decision: accepted.

Reason: The design requires invalid-state purge to be atomic and not leave tombstone/replay state. The existing open-session test asserts this; non-terminal Run rejection should prove the same invariant.

Required fix:
- Add tombstone absence assertion for non-terminal Run rejection tests.

### S2-ADJ-005 accepted — idempotency records outside purge session-fact scope should be preserved

Source: `docs/reviews/phase15-s2-code-review-mimo-20260529.md` FINDING-7.

Decision: accepted.

Reason: S2 deliberately deletes a broader-than-literal set of old command idempotency rows via `_SESSION_FACT_SCOPE_KINDS`. A preservation test for out-of-scope idempotency rows is cheap evidence that the guard is correct.

Required fix:
- Seed an idempotency record outside `_SESSION_FACT_SCOPE_KINDS` and assert purge preserves it.

## Rejected Findings

### S2-REJ-001 rejected — full parent+child non-terminal matrix test

Source: `docs/reviews/phase15-s2-code-review-mimo-20260529.md` FINDING-3.

Decision: rejected-with-reason.

Reason: `_enforce_no_non_terminal_runs(...)` reads `host_runs` by status across the whole Session; the existing parametrized single-run test proves all non-terminal statuses reject, and the full matrix success test proves parent/child terminal chains delete correctly. Adding a second full matrix non-terminal fixture is not required for S2 correctness and would mainly expand brittle test setup.

### S2-REJ-002 rejected — closed Session with zero Runs test

Source: `docs/reviews/phase15-s2-code-review-mimo-20260529.md` FINDING-4.

Decision: rejected-with-reason.

Reason: This is not a demonstrated bug in the delete matrix. If public command wiring later exposes a valid close-with-zero-runs workflow gap, S3 can add coverage at the public command boundary. It does not block S2.

## Deferred Findings

None.

## Next Gate

Phase 15 S2 fix. Fix agent may modify only:
- `dayu/host/durable/purge.py`
- `tests/host/test_purge_session.py`
- `docs/reviews/phase15-s2-fix-codex-20260529.md`

No public command wiring, audit JSONL writing, cold artifact GC, commit, push, or PR work is authorized in this fix gate.
