# A2 Code Re-Review Controller Adjudication

- **Date**: 2026-05-14
- **Gate**: full repository review fix work unit A2
- **Scope**: Host instance liveness lifecycle hardening
- **Source adjudication**: `docs/reviews/repo-review-controller-adjudication-20260514.md`
- **Implementation artifact**: `docs/reviews/repo-review-fix-a2-host-liveness-lifecycle-hardening-20260514.md`
- **Review artifacts**:
  - `docs/reviews/repo-review-code-review-a2-host-liveness-lifecycle-hardening-mimo-20260514.md`
  - `docs/reviews/repo-review-code-review-a2-host-liveness-lifecycle-hardening-glm-20260514.md`
- **Re-review artifacts**:
  - `docs/reviews/repo-review-code-re-review-a2-host-liveness-lifecycle-hardening-mimo-20260514.md`
  - `docs/reviews/repo-review-code-re-review-a2-host-liveness-lifecycle-hardening-glm-20260514.md`

## Decision

A2 is accepted.

The initial implementation fixed the terminal-state lifecycle defects and rowcount
checks, then review identified three improvements:

- heartbeat must not silently move `STOPPING` back to `RUNNING`;
- terminal rows must also reject `mark_current_instance_stopped()`;
- register rowcount-zero classification needed direct coverage.

The review-fix resolved all three items. Heartbeat now accepts only `RUNNING` source
rows. Explicit `register_current_instance()` still preserves the existing
`STOPPING -> RUNNING` re-registration behavior. `STOPPED` and `CRASHED_SUSPECTED`
cannot be moved through register, heartbeat, stopping, or stopped paths. Register,
heartbeat, and status mark rowcount-zero paths now have focused identity drift tests.

No recovery, lease/fencing, takeover, dispatch owner, Phase 11 scan, or crash
classifier implementation was added.

## Review Decisions

- **MiMo initial review**:
  - `mark_current_instance_stopped()` terminal path missing test: accepted and fixed.
  - `_raise_liveness_update_conflict()` fallback classification note: accepted as
    non-blocking defensive branch, no code change required.
- **GLM initial review**:
  - heartbeat `STOPPING -> RUNNING`: accepted and fixed.
  - `mark_current_instance_stopped()` terminal path missing test: accepted and fixed.
  - register rowcount-zero test missing: accepted and fixed.
- **MiMo re-review**: pass, no new finding.
- **GLM re-review**: pass, no new finding.

## Validation Evidence

Reviewer validation:

- MiMo initial: `pytest tests/host/test_host_instance_liveness.py -q` -> 14 passed.
- MiMo re-review: `pytest tests/host/test_host_instance_liveness.py -q` -> 16 passed.
- MiMo re-review: pyright on touched files -> 0 errors.
- GLM initial: `pytest tests/host/test_host_instance_liveness.py -q` -> 14 passed.
- GLM re-review: `pytest tests/host/test_host_instance_liveness.py -q` -> 16 passed.
- GLM re-review: pyright on touched files -> 0 errors.

Controller validation:

- `pytest tests/host/test_host_instance_liveness.py -q` -> 16 passed.
- `pytest tests/host -q` -> 207 passed.
- `python -m pyright dayu/host tests/host` -> 0 errors.
- `git diff --check` -> passed.

## Residual Risk

No blocking A2 residual risk remains.

Tracked non-blocking residuals:

- `mark_current_instance_stopped()` is not idempotent for an already `STOPPED` row;
  it raises `HostInstanceLifecycleConflictError`. If Phase 11 shutdown/recovery paths
  require repeated stopped marking to be absorbed, that phase must make an explicit
  design decision.
- `_IdentityDriftTransaction` is a focused test wrapper around `execute` and
  `fetchone`; it intentionally does not model the whole transaction surface.

## Next Work Unit

After the A2 accepted commit, continue with A6 Host digest/helper dedupe unless the
controller records a different queue order.
