# PR 50 Re-review Controller Adjudication

- **PR**: https://github.com/noho/dayu-agent-r/pull/50
- **fix commit**: `16668ac fix host phase3 pr review findings`
- **date**: 2026-05-14
- **re-review inputs**:
  - `docs/reviews/pr-50-re-review-mimo-20260514.md`
  - `docs/reviews/pr-50-re-review-ds-20260514.md`
- **controller adjudication**: `docs/reviews/pr-50-controller-adjudication-20260514.md`
- **fix artifact**: `docs/reviews/pr-50-fix-20260514.md`

## Decision

PR 50 review loop is accepted. No blocking findings remain.

Both AgentMiMo and AgentDS confirmed:

- `PR50-C-001` fixed: post-commit wakeup no longer prevents durable queue promotion; queue wakeup `RuntimeError` is best-effort after promotion; dispatch wakeup `RuntimeError` after promotion no longer masks the committed promotion result.
- `PR50-C-002` fixed: `git diff --check main...HEAD` passes after the whitespace cleanup commit.
- `PR50-C-003` fixed: `_require_event_sequence` now reads through `EventLogStore.read_event_by_id` and no longer imports `TABLE_EVENT_LOG` into `dayu.host.admission`.

Both re-reviewers also confirmed the rejected findings are consistent with the controller adjudication. Controller basis is `docs/host/design.md` plus the design goals in `docs/host/implementation-control.md`; Phase 3 plan and tests are treated only as corroborating evidence:

- follow-up queue digest intentionally excludes `resolved_execution_target` because `SubmitFollowupRequest` does not own an execution target in the design, while `StartRunRequest` does;
- `attach_active` does not get a new EventLog fact in PR 50 because the design does not freeze an attach-active canonical event shape, and inventing one during PR fix would overdesign Phase 3;
- `internal_terminal_closeout` idempotency is deferred to the later EngineEvent ingest owner;
- reject policy intentionally writes no EventLog row and no idempotency record;
- future Attempt statuses in schema are intentional design alignment;
- broad failure-path testing requests are hardening items, not PR blockers.

## Verification

AgentMiMo:

- `pytest tests/host -q`: 160 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: passed
- `git diff --check main...HEAD`: passed

AgentDS:

- `pytest tests/host -q`: 160 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: passed
- `git diff --check main...HEAD`: passed

Controller status:

- Accepted fix commit has been pushed to PR branch.
- Re-review artifacts are ready to be committed and pushed.
- Remaining residual items continue to be owned by later phases as recorded in `docs/host/implementation-control.md`; specifically, Phase 4 must clarify any public audit/read-model representation for `attach_active` before changing EventLog semantics.

## Gate Result

PR 50 is controller-accepted after PR review fix and re-review. No additional code changes are required for this review loop.
