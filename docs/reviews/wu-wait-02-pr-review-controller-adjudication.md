# WU-WAIT-02 PR Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-02 / GitHub issue #90
- Gate: PR review / fix / re-review
- Draft PR: https://github.com/noho/dayu-agent-r/pull/165
- Branch: `work/wu-wait-02-issue-90`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`

## Review Artifacts

- DS PR review: `docs/reviews/pr-165-review-20260701-164627.md`
- MiMo PR review: `docs/reviews/pr-165-review-20260701-164858.md`
- AgentCodex fix artifact: `docs/reviews/wu-wait-02-pr-review-fix-codex.md`
- DS re-review: `docs/reviews/pr-165-re-review-20260701-170000.md`
- MiMo re-review: `docs/reviews/pr-165-re-review-20260701-170022.md`

## Controller Judgment

DS Finding 01 is accepted and fixed in the current gate.

- Finding: `_abandon_cancelled_wait` could call `adapter.abandon_wait(record)` successfully and then skip durable `poll_abandoned_at` marking if lifecycle close happened before the mark transaction.
- Decision: accepted.
- Fix status: fixed.
- Evidence: `dayu/host/wait_adapter.py` removed the post-abandon lifecycle gate skip, while preserving the pre-adapter shutdown skip, adapter-outside-transaction invariant, and claim-based CAS durable mark.
- Verification: both re-review artifacts mark the finding as fixed and report no new material finding.

DS Finding 02 is rejected as a non-material maintainability note for this PR review gate.

- Finding: schema version moved from branch-internal v17 to v18 without a source comment.
- Decision: rejected-with-reason.
- Reason: v17 was an unmerged slice-internal intermediate state inside this PR branch, not a released or persisted schema version. The project schema rule for this work unit is fresh-schema-only with exact current `HOST_SCHEMA_VERSION = 18`; git history and gate artifacts already preserve the branch-internal sequence. Adding production comments for an unshipped intermediate version would add maintenance text without changing runtime, schema, or operator behavior.

MiMo F01-F06 are classified as non-blocking review notes / design confirmations. They do not require current code changes.

## Validation

Controller reran the required validation after the fix:

- `source .venv/bin/activate && pytest tests/host/test_wait_adapter_polling.py tests/host/test_wait_poller_runtime.py -q`
  - Result: `25 passed`
- `source .venv/bin/activate && pytest tests/host/test_durable_schema.py tests/host/test_wait_record_state.py tests/host/test_open_host_runtime.py tests/host/test_resolve_wait_command.py tests/host/test_public_lifecycle_smoke.py -q`
  - Result: `86 passed`
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed with no output

Total affected tests after PR review fix: 111 passed.

## Residual Risks

- External abandon after stale-claim CAS conflict can still be retried by a new owner. Owner: future adapter / WU-WAIT-03 if a provider requires stronger external cancel idempotency. Rationale: preserving claim CAS authority is the correct current Host invariant; this risk existed before the PR review fix and is not caused by the lifecycle gate ordering bug.
- Synchronous adapter calls cannot be forcibly killed by Python. Owner: adapter implementation / future provider integration. Current Host behavior records diagnostics and waits for in-flight calls during close.
- Missing adapter retry is capped-delay indefinite retry. Owner: WU-WAIT-03 / provider lifecycle and operator visibility.
- UI / Service production E2E smoke remains assigned to WU-WAIT-04 after WU-WAIT-02 and WU-WAIT-03.
- GitHub PR checks are not configured for this branch; local validation is the current gate evidence.

No unclassified blocking residual risk remains for WU-WAIT-02.

## Decision

PR review / fix / re-review gate passes. Create accepted PR review commit, push it to draft PR 165, then proceed to `draft-PR-pass` and `final closeout`.
