# PR #48 Controller Adjudication

## Scope

- PR: #48 `feat/host-phase-1` -> `main`
- PR URL: https://github.com/noho/dayu-agent-r/pull/48
- Review artifacts:
  - `docs/reviews/pr-48-review-20260514-0753.md`
  - `docs/reviews/pr-48-review-20260514-0800.md`
- Controller role: adjudicate AgentDS / AgentMiMo PR review findings and decide required fixes before PR closeout.

## Controller Summary

PR #48 is architecturally aligned with Host Phase 1. The review round found no design blocker and no cross-layer violation. Several findings are valid quality gaps. One filelock correctness finding and three coverage / documentation findings are accepted for fix before merge.

## Findings Adjudication

### A1. `RuntimeFileLockToken.release()` partial failure leaves token unreleased after underlying lock release

- Source: `pr-48-review-20260514-0800.md` finding 001.
- Severity: medium.
- Decision: accepted for fix.
- Rationale: if the third-party release succeeds and marker restoration fails, the OS-level lock is already released. Leaving `RuntimeFileLockToken.released=False` violates the wrapper's idempotent release contract and makes retry behavior misleading. Because the lock marker is explicitly not a Host governance truth source, marker restoration failure must not make the token appear unreleased after the underlying lock has been released.
- Required fix:
  - Mark the token released immediately after successful third-party release.
  - Keep marker restoration best-effort and do not let marker failure turn a successfully released token back into a release failure.
  - Add a focused test that simulates marker restoration failure after underlying release and asserts `released=True` plus idempotent second `release()`.

### A2. `RuntimeFileLock.__exit__` may mask context body exception if release fails

- Source: `pr-48-review-20260514-0753.md` finding 1.
- Severity: low.
- Decision: not accepted for mandatory PR fix.
- Rationale: `__exit__` currently documents that release failure can raise `RuntimeFileLockError`. If both the context body and release fail, Python keeps the body exception in exception context when `__exit__` raises, so the original exception is not fully unrecoverable. Suppressing release failure without a logging / diagnostic path would hide an infrastructure cleanup failure. This PR should not add a new exception-priority policy that was not part of the accepted filelock contract.
- Follow-up: no tracking item required unless a later phase defines a broader runtime cleanup diagnostic policy.

### A3. `RunSnapshot` source relation consistency has no failure-path tests

- Source: `pr-48-review-20260514-0800.md` finding 002.
- Severity: medium as coverage gap for public contract invariants.
- Decision: accepted for fix.
- Rationale: these are public snapshot invariants. The implementation exists, but tests must pin both invalid combinations so future contract refactors cannot silently weaken them.
- Required fix:
  - Add tests for `source_run_id=None` with `source_run_relation=RETRY`.
  - Add tests for `source_run_id` present with `source_run_relation=None`.

### A4. `FollowupSnapshot` behavior consistency has no failure-path tests

- Source: `pr-48-review-20260514-0800.md` finding 003.
- Severity: medium as coverage gap for public contract invariants.
- Decision: accepted for fix.
- Rationale: queue / steer shape is a public contract boundary and must be locked by tests.
- Required fix:
  - Add tests for steer without `target_run_id`.
  - Add tests for steer with `queued_run_id`.
  - Add tests for queue with `target_run_id`.
  - Add tests for queue without `queued_run_id`.

### A5. `dayu/README.md` places implemented filelock under design-requirement paragraph

- Source: `pr-48-review-20260514-0800.md` finding 004.
- Severity: low.
- Decision: accepted for fix.
- Rationale: `dayu.runtime.filelock` is implemented in Phase 1 and should be listed alongside `lane` under current runtime capabilities. `ToolsDiscovery` and `ScenePrepare` remain deferred boundary concepts.
- Required fix:
  - Move the filelock description into the current `dayu.runtime` capabilities section.
  - Leave `ToolsDiscovery` / `ScenePrepare` in the deferred design-boundary section.

### A6. Lane validation / close idempotency tests missing

- Source: `pr-48-review-20260514-0800.md` finding 005.
- Severity: low.
- Decision: accepted for fix.
- Rationale: these checks are simple but public runtime API behavior. Adding tests is low-risk and improves Phase 1 confidence.
- Required fix:
  - Add `LaneOwner` validation test for empty `owner_id` and invalid `pid`.
  - Add negative acquire timeout test.
  - Add double `LaneController.close()` idempotency test.

### A7. Duplicate `_require_non_empty` / `_require_optional_non_empty` in `api.py` and `tooling.py`

- Source: `pr-48-review-20260514-0753.md` finding 2.
- Severity: info.
- Decision: not accepted for PR fix.
- Rationale: the duplication is small, private to two Host public-contract modules, and avoids introducing a new internal helper module solely for two functions. The project guidance favors abstraction when it removes meaningful complexity; this does not meet that threshold in Phase 1.
- Follow-up: no action unless future Host modules create a third copy or validation semantics diverge.

## Required Fix Scope

Allowed production files:

- `dayu/runtime/filelock.py`
- `dayu/README.md`

Allowed test files:

- `tests/runtime/test_filelock.py`
- `tests/runtime/test_lane.py`
- `tests/host/test_public_contracts.py`

Allowed review artifact files:

- `docs/reviews/pr-48-review-20260514-0753.md`
- `docs/reviews/pr-48-review-20260514-0800.md`
- `docs/reviews/pr-48-controller-adjudication-20260514.md`
- implementation/fix artifact for the accepted PR review fixes.

No Engine / Fins / Service / UI changes are allowed.

## Required Validation After Fix

- `source .venv/bin/activate && pytest tests/runtime/test_filelock.py tests/runtime/test_lane.py tests/host/test_public_contracts.py -q`
- `source .venv/bin/activate && pytest tests/host tests/runtime -q`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
- `git diff --check`

## Residual Items

- No accepted design blocker remains after the required fixes.
- CI is not reported on the PR; local pytest and pyright remain the validation source until CI exists for this branch.
