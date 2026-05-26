# PR 68 Post-Draft Fullrepo Fix Controller Adjudication

- **Date**: 2026-05-26
- **PR**: https://github.com/noho/dayu-agent-r/pull/68
- **Branch**: `feat/phase-12-5-conversation-memory-optimize`
- **Gate**: post-draft fullrepo review fix / re-review
- **Reviewed artifacts**:
  - `docs/reviews/pr-68-postdraft-fullrepo-review-ds-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-review-mimo-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-fix-codex-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-fix-rereview-ds-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-fix-rereview-mimo-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-validation-fix-codex-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-validation-fix-rereview-ds-20260526.md`
  - `docs/reviews/pr-68-postdraft-fullrepo-validation-fix-rereview-mimo-20260526.md`

## Verdict

PASS. Accepted post-draft fullrepo findings have been fixed and re-reviewed. No remaining blocking finding is accepted for the current gate.

## Accepted Findings Fixed

### B1 — Standard governed dispatch record owner starts as NULL

Accepted and fixed.

Production fix: `HostDispatchScheduler._start_governed_in_transaction` now writes `self._host_instance_identity.host_instance_id` into `StartGovernedRunInput.owner_host_instance_id` when the dispatch record is created. This closes the commit-after-start / before-waiting crash window where recovery could only see `owner_host_instance_id=NULL`.

Re-review status: PASS in both DS and MiMo re-review artifacts.

### B2 — WAITING_FOR_LANE / DISPATCHING owner uses handle id

Accepted and fixed.

Production fix: `_mark_waiting_for_lane` and `_mark_dispatching_after_recheck` now write `self._host_instance_identity.host_instance_id` instead of `self._host_handle_id`.

Regression proof: the new tests intentionally use different handle id and host instance id, then assert the durable owner equals the instance id and does not equal the handle id.

Re-review status: PASS in both DS and MiMo re-review artifacts.

## Findings Not Accepted For This Gate

### B3 — Governance rejected Run should not be FAILED

Not accepted as a blocking fix in this gate.

Direct evidence:

- `docs/host/implementation-control.md:2531-2534` explicitly records hard threshold / compaction failure as attempt-free `RUN_FAILED` closeout.
- `fail_unstarted_run_in_transaction` persists a `RUN_FAILED` event with `reason` and payload fields carrying the governance reason, error code, and message.

Introducing `RunStatus.REJECTED` would be a schema/state-machine change outside this post-draft fix scope and is not required to repair B1/B2.

## Validation Fix

The fullrepo re-review also exposed a separate validation failure in `tests/runtime/test_scene_assets_migration.py`: the new `smoke_host_public_conversation_memory` manifest followed the same ordinary smoke scene pattern as `smoke_host_public_multiturn`, but the migration test inventory did not include it.

Fix: `tests/runtime/test_scene_assets_migration.py` now lists `smoke_host_public_conversation_memory` with `max_iterations=20`.

Re-review status: PASS in both DS and MiMo validation-fix re-review artifacts. The manifest was not changed because `allow_tool_calls` is an allowed current-schema field and matches the existing public multiturn smoke manifest.

## Validation Reviewed

Fix agent and reviewers reported:

- `pytest tests/host/test_dispatch_scheduler.py tests/host/test_recovery_dispatch.py tests/host/test_recovery_scan.py tests/host/test_run_attempt_transitions.py -q` — 95 passed.
- focused owner regression tests — 2 passed.
- `pytest tests/runtime/test_scene_assets_migration.py -q` — 6 passed.
- `pytest tests/runtime/test_scene_prepare.py tests/runtime/test_smoke_host_public_multiturn_assembly.py tests/service/test_host_assembly.py -q` — 58 passed.
- `python -m pyright dayu/ tests/ utils/` — 0 errors, 0 warnings, 0 informations.

MiMo's fullrepo review attempted the full `tests/` suite and reported 1089/1090 passed with one external-network-dependent failure. That failure is not tied to the accepted fixes.

## Residual Tracking

Remaining non-blocking residuals stay tracked:

- governance rejection terminal taxonomy can be revisited as a future schema/state-machine design change;
- scheduler and recovery production-hardening items from the fullrepo review remain low-severity residuals;
- smoke pressure dead branch and test guard expansion remain low-severity cleanup items.
