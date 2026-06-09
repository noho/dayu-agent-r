# WU-TOOLS-01-F01-02 Slice 1 Code Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | Slice 1 code review controller adjudication |
| slice | Slice 1 - Fins Awaiting Tools Token Bridge |
| implementation artifact | `docs/reviews/wu-tools-01-f01-02-slice1-implementation-codex.md` |
| review artifacts | `docs/reviews/wu-tools-01-f01-02-slice1-code-review-mimo.md`; `docs/reviews/wu-tools-01-f01-02-slice1-code-review-ds.md` |
| date | 2026-06-08 |

## Controller Decision

Slice 1 code review found no correctness blocker in the main cancellation path, but the review findings identify small current-slice fixes that should be applied before accepted slice commit.

Gate result: proceed to fix gate.

## Findings Adjudication

| Finding | 来源 | 裁决 | 原因 | Fix / Owner |
|---|---|---|---|---|
| S1-F1 `_create_queued_job` became dead private code | AgentMiMo 001; AgentDS F1 | accepted | The method is now unused and can mislead future callers into bypassing the new create/checkpoint/submit invariant. Removing it is low-risk and aligned with the no compatibility/dead helper constraint. | Current fix gate; AgentCodex removes the method and verifies no references. |
| S1-F2 create-after-cancel leaves a no-runner `CANCELLING` job | AgentMiMo 002; AgentDS F2 | accepted | The plan allowed `cancelling/cancelled`, but current code has a simple in-scope terminalization path via existing `CANCELLED` state and `_save_cancelled`; using it avoids leaving a known orphan for the local create-before-submit cancel branch without changing Host/Engine contract or adding a state machine. | Current fix gate; AgentCodex terminalizes this branch to `CANCELLED`, preserving no-submit behavior. |
| S1-F3 runtime tests assert exact checkpoint call count | AgentMiMo 003; AgentDS F3 | accepted | Exact `check_count == 2` is unnecessarily brittle. Behavior assertions should prove no submit and durable cancellation, not exact helper call count. | Current fix gate; AgentCodex relaxes/removes exact count assertion. |
| S1-F4 `_CancelOnSecondCheckToken` does not fully model cancellation metadata | AgentDS F4 | accepted | Test double should implement the public protocol coherently once cancelled, even if current production code only calls `is_cancelled()`. | Current fix gate; AgentCodex stores cancelled state and returns reason / requested_at coherently. |

## Required Fix

AgentCodex must:

- remove unused `_create_queued_job` or route through it only if it owns the full create/checkpoint/submit invariant; preferred fix is removal;
- change the create-after-submit checkpoint cancellation branch to return a `CANCELLED` job start record using existing Fins job store state and without submitting background work;
- update tests so required behavior expects `CANCELLED` for the create-before-submit cancel branch, with `cancellation_requested=True`, no executor operation, and no exact `check_count == 2` assertion;
- update `_CancelOnSecondCheckToken` so once cancellation has been observed, `cancel_reason()` and `requested_at()` reflect the cancellation consistently;
- update implementation artifact or add a fix artifact documenting the changes and validation.

## Residual Risks

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| S1-R1 | deferred-with-owner | WU-WAIT-03 or independent Host awaiting activation design WU | The broader awaiting accept orphan window remains deferred; this fix only closes the local create-before-submit cancel branch. |
| S1-R2 | accepted limitation | WU-TOOLS-01-F01-02 later slices / closeout | Submit-after-start synchronous I/O cannot be physically preempted by Host token; background still observes durable job cancel. |
| S1-R3 | covered by later approved slice | Slice 2 / Slice 3 / Slice 4 | Web / Doc / Fins read token propagation is intentionally not part of Slice 1. |

## Gate Result

Proceed to fix gate. After fix, dispatch Slice 1 re-review to verify S1-F1 through S1-F4.
