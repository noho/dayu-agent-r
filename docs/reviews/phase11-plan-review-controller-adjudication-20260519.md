# Phase 11 Plan Review Controller Adjudication

## Gate

Phase 11. Host Lifecycle / Recovery / Multi-process Hardening plan review adjudication.

## Inputs

- Plan artifact: `docs/host/phase11-host-lifecycle-recovery-plan.md`
- MiMo review: `docs/reviews/phase11-plan-review-mimo-20260519.md`
- DS review: `docs/reviews/phase11-plan-review-ds-20260519.md`
- Design truth: `docs/host/design.md` §1, §2, §10, §17, §27, §27.1
- Control truth: `docs/host/implementation-control.md` Phase 11

Both independent reviews returned PASS with blocking count = 0.

## Controller Decision

Overall decision: plan is directionally accepted, but must receive one plan-hardening fix pass before accepted plan commit.

基于 design_doc 的设计目标和第一性原理，Phase 11 的 plan 必须让 implementation agent 在 recovery truth source、positive orphan proof、startup classification、RunInputBuilder truth boundary 和 multi-process safety 上没有可自行发明的空间。Non-blocking findings that remove ambiguity from those boundaries should be accepted as plan hardening before implementation.

## Findings

### MiMo F1 / DS A2: process_start_token entropy

Decision: accepted for current plan fix.

Rationale: positive orphan proof depends on process identity not being confused with predictable diagnostic ids. The plan already requires an unguessable token; specifying `uuid4().hex` or equivalent high-entropy stdlib generation prevents implementation drift without changing public API or schema.

Required fix: update Slice 1 exact changes to require high-entropy stdlib token generation, separate from `host_instance_id`, and forbid timestamp / handle-id derived tokens.

### MiMo F2 / DS 2-U: WAITING recovery observation fallback

Decision: accepted for current plan fix.

Rationale: design_doc says `WAITING` remains `WAITING`; that does not mean startup scan should silently ignore lack of adapter observation. A diagnostic-only fallback preserves EventLog truth and avoids state mutation while making stuck WAITING visible.

Required fix: update Slice 2 to require diagnostic-only fallback when wait adapter observation is unavailable or wake fails, with no Run / Attempt state mutation and no Attempt creation.

### MiMo F3: heartbeat background task failure mode

Decision: accepted for current plan fix.

Rationale: heartbeat stale alone is not orphan proof, but silent heartbeat task death can still cause noisy suspect diagnostics or delayed recovery. The plan should require heartbeat task failures to be observable and lifecycle-safe.

Required fix: update Slice 1 to require heartbeat loop exception handling, structured diagnostic logging, and best-effort current-instance `stopping` mark on fatal heartbeat task exit; do not mark other instances.

### MiMo F4: RECOVERING cancel idempotency scope

Decision: accepted for current plan fix.

Rationale: recovery cancel must preserve P10.5 public command semantics. Explicitly tying idempotency replay to `(run_id, client_request_id)` prevents session-scope replay from affecting later Runs.

Required fix: update Slice 4 to state `cancel_run` idempotency scope remains `(run_id, client_request_id)` and `cancel_session_runs` scope remains `(session_id, client_request_id)` with per-run result stability.

### MiMo F5: recovery dispatch count EventLog scan boundary

Decision: accepted for current plan fix.

Rationale: EventLog remains the truth source, but the implementation should not leave an unbounded vague scan in a startup loop. A typed filtered read helper scoped by `run_id` and event type keeps the truth source durable without premature schema changes.

Required fix: update Slice 2 to require a typed EventLog helper filtered by `run_id` and canonical `RUN_STARTED` events, counting only payloads with `start_reason=recovery`.

### DS 1-U: RunInputBuilder canonical-fact hardening

Decision: accepted for current plan fix.

Rationale: recovery correctness depends on rebuilding from canonical facts rather than projection freshness. If RunInputBuilder needs hardening, implementation should know the allowed ownership boundary before hitting Slice 3.

Required fix: add Slice 3 exact change allowing necessary typed RunInputBuilder / dispatch-path hardening to ensure recovery messages are built from canonical facts and payload descriptors, not projection or memory truth; if files outside the stated ownership boundary are needed, stop and return to Controller.

### MiMo F6: Slice 2 / Slice 3 both touching run_transition.py

Decision: rejected as no-action for current plan fix.

Rationale: the plan already sequences slices S2 before S3, and both changes belong to the same state-transition owner. This is not a correctness ambiguity as long as implementation remains sequential.

Required fix: none.

## Required Plan Fix Scope

Allowed file for the plan fix:

- `docs/host/phase11-host-lifecycle-recovery-plan.md`

The fix must not modify source code, tests, README files, design truth, or control doc. If the plan fix discovers a new blocking question, it must stop and report it.

## Next Gate

Next gate: Phase 11 plan fix by AgentCodex, followed by two-way plan re-review.
