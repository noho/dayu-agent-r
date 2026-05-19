# PR 65 Manual Deepreview-All Controller Adjudication - 2026-05-20

## Scope

- PR: `https://github.com/noho/dayu-agent-r/pull/65`
- Gate: manual post-draft `deepreview --all` closure.
- Manual review artifacts:
  - `docs/reviews/repo-review-20260520-060834.md`
  - `docs/reviews/repo-review-20260520-060858.md`
- Fix artifact: `docs/reviews/pr-65-manual-deepreview-all-fix-codex-20260520.md`
- Re-review artifacts:
  - `docs/reviews/pr-65-manual-deepreview-all-rereview-mimo-20260520.md`
  - `docs/reviews/pr-65-manual-deepreview-all-rereview-ds-20260520.md`

## Verdict

PASS.

The two manual all-repo reviews found several real hardening opportunities, but only a bounded subset was current-blocking for PR 65. The current-blocking findings have been fixed and independently re-reviewed by AgentMiMo and AgentDS. Both re-reviews report PASS with no blocking or high finding in the fix diff.

## Current-Fix Adjudication

Accepted and fixed:

- `0834-F1`: awaiting timeout diagnostic refs type mismatch. Fixed by keeping awaiting timeout refs as string ids through `_accept_awaiting_with_retry`.
- `0834-F5`: `CLEAR` plus empty open questions incorrectly counted as retained. Fixed in `context_governance.py`.
- `0834-F7`: duplicate `ALLOW` appended a spurious governed event. Fixed in `tool_runtime.py`.
- `0858-F1`: startup scan did not wake inert `ACCEPTED` / `QUEUED` Runs, including the proactive compaction crash window. Fixed by post-commit queue-promotion wakeups.
- `0858-F8`: non-429 `Retry-After` lacked a cap. Fixed in `retry_policy.py`.
- `0858-F9`: non-stream HTTP 200 provider error objects lost provider details. Fixed in `non_stream_parser.py`.
- `0858-F10`: `ATTACH_ACTIVE` rejected `ACCEPTED` active Runs. Fixed in `admission.py` without adding a public interface.

Rejected as stale, non-defect, or not current-blocking:

- `0858-F4` WAITING cancel is stale: current `admission.py` already routes `RunStatus.WAITING` to `_cancel_waiting(...)`, which calls `cancel_waiting_run_in_transaction(...)`.
- `0858-F7` recovery dispatch count is accepted P11 design: current policy intentionally allows one automatic startup recovery dispatch per Run before LOST closeout.
- `0858-F3` compaction budget is not solely ref-id length: current estimator takes the max of typed fragment tokens and preserved share from pre-compact budget. Precision hardening is not a PR 65 blocker.
- `0834-F2` release-token cancellation finding overstates the path: `_release_token` already catches `RuntimeLaneError` after outer cancellation and intentionally does not mark a token released if DB release failed.

Deferred with owner:

- PID reuse identity proof, recovery scan batching, EventLog physical corruption tolerance, dispatcher closeout retries, projection repair filtering, and structural simplification remain Phase 15 production hardening risks unless a future phase narrows them earlier.
- Audit / tool trace durability and terminal delivery observability remain Phase 13 projection responsibilities.
- Broader Engine / Host class and module size cleanup remains non-blocking structural debt; it does not change the frozen Host public interface.

## Verification

- AgentCodex focused validation: 128 focused tests passed, pyright over changed Host / Engine scopes reported 0 errors, and `git diff --check` was clean.
- AgentMiMo re-review: PASS; verified 9 scope items and reported no substantive issue.
- AgentDS re-review: PASS; verified the 7 current-fix items plus README synchronization and reported no substantive issue.
- Controller full validation after re-review caught two stale integration-test expectations for duplicate `ALLOW`; AgentCodex updated only `tests/host/test_phase6_toolruntime_integration.py`.
- AgentMiMo and AgentDS both confirmed in follow-up that the test-only update does not change their PASS verdict and introduces no blocker.
- Final validation: `tests/engine/runners/openai -q` 214 passed; `tests/host -q` 795 passed / 1 skipped; `python -m pyright dayu/ tests/ utils/` 0 errors; `git diff --check` clean.

## Residual Risk

Residual risks are non-blocking and already assigned to later phase owners above. No Host public interface or contract was added, removed, or reshaped in this loop.

## Conclusion

The manual post-draft `deepreview --all` loop is closed to PASS for PR 65 after current fixes and independent re-review.
