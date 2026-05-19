# Phase 11 Plan Fix — AgentCodex 2026-05-19

## Scope

Fix target:

- `docs/host/phase11-host-lifecycle-recovery-plan.md`

Review inputs:

- `docs/reviews/phase11-plan-review-controller-adjudication-20260519.md`
- `docs/reviews/phase11-plan-review-mimo-20260519.md`
- `docs/reviews/phase11-plan-review-ds-20260519.md`

本次只修 plan artifact；未修改 source、tests、README、design doc、control doc，未提交，未 push，未进入 implementation。

## Changed File

- `docs/host/phase11-host-lifecycle-recovery-plan.md`

## Per-finding Status

| Finding | Controller decision | Fix status |
| --- | --- | --- |
| MiMo F1 / DS A2: `process_start_token` entropy | Accepted | Fixed. Slice 1 now requires `uuid4().hex` or equivalent stdlib high-entropy random value, generated separately from `host_instance_id`, and forbids timestamp / handle-id / pid derived tokens. |
| MiMo F2 / DS 2-U: `WAITING` observation fallback | Accepted | Fixed. Slice 2 now requires diagnostic-only fallback when wait adapter observation is unavailable, unsupported, or wake fails; no Run / Attempt mutation and no Attempt creation. |
| MiMo F3: heartbeat task failure mode | Accepted | Fixed. Slice 1 now requires heartbeat loop exception handling, structured diagnostic logging, and best-effort current-instance `STOPPING` mark on fatal heartbeat task exit, without touching other instances. |
| MiMo F4: RECOVERING cancel idempotency scope | Accepted | Fixed. Slice 4 now explicitly scopes `cancel_run` to `(run_id, client_request_id)` and `cancel_session_runs` to `(session_id, client_request_id)`, with per-run result stability limited to Runs in the original session-scope result. |
| MiMo F5: recovery dispatch count helper boundary | Accepted | Fixed. Slice 2 now requires a typed EventLog helper filtered by `run_id` and canonical `RUN_STARTED`, counting only payloads with `start_reason=recovery`. |
| DS 1-U: RunInputBuilder canonical-fact hardening | Accepted | Fixed. Slice 3 now allows necessary typed hardening inside RunInputBuilder / dispatch path, forbids projection/memory/read-model truth, and adds a stop condition if files outside Slice 3 allowed files are needed. |
| MiMo F6: Slice 2 / Slice 3 both touching `run_transition.py` | Rejected as no-action | No action, per Controller adjudication. |

## Validation

- Passed: `git diff --check`
- Passed: trailing-whitespace sanity check on the two touched markdown artifacts.

## New Risks / Open Questions

- No new blocking questions.
- Existing working tree has unrelated tracked changes in `docs/host/design.md` and `docs/host/implementation-control.md`; this fix did not modify those files.
- The plan artifact is currently untracked in git status, so normal tracked-file diff output does not show its content unless it is added later by the controller/owner.

## Conclusion

PLAN_FIX_COMPLETE
