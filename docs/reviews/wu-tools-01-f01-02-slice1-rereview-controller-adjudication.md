# WU-TOOLS-01-F01-02 Slice 1 Re-Review Controller Adjudication

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | Slice 1 re-review controller adjudication |
| slice | Slice 1 - Fins Awaiting Tools Token Bridge |
| fix artifact | `docs/reviews/wu-tools-01-f01-02-slice1-fix-codex.md` |
| re-review artifacts | `docs/reviews/wu-tools-01-f01-02-slice1-rereview-mimo.md`; `docs/reviews/wu-tools-01-f01-02-slice1-rereview-ds.md` |
| date | 2026-06-08 |

## Controller Decision

Slice 1 re-review passed. The accepted code review findings were fixed and the slice can proceed to accepted slice commit.

## Final Finding Status

| Finding | Final status | Evidence |
|---|---|---|
| S1-F1 unused `_create_queued_job` dead helper | 已修复 | Both reviewers verified no remaining `_create_queued_job` reference and no wrapper bypassing the create/checkpoint/submit invariant. |
| S1-F2 create-before-submit cancellation left non-terminal `CANCELLING` job | 已修复 | Both reviewers verified the branch now returns `CANCELLED` via existing `_save_cancelled(...)` and does not submit executor work. |
| S1-F3 tests asserted exact checkpoint count | 已修复 | Both reviewers verified tests assert observable `CANCELLED`, `cancellation_requested`, and no executor operations instead of exact call count. |
| S1-F4 cancellation token test double metadata inconsistency | 已修复 | Both reviewers verified the token records cancellation state and returns consistent reason / requested time after cancellation is observed. |

## Validation

Validation recorded by implementation and fix artifacts, and independently checked by reviewers:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q` passed with 48 tests and only existing `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright` passed with 0 errors.

## Residual Risks

| ID | 状态 | Owner / Destination | 下一步 |
|---|---|---|---|
| S1-R1 | deferred-with-owner | WU-WAIT-03 or independent Host awaiting activation design WU | Broader Host awaiting accept / cross-process orphan window remains outside Slice 1. |
| S1-R2 | accepted limitation | WU-TOOLS-01-F01-02 closeout | Submit-after-start synchronous I/O cannot be physically preempted by Host token; background observes durable Fins job cancel. |
| S1-R3 | covered by later approved slice | Slice 2 / Slice 3 / Slice 4 | Web / Doc / Fins read token propagation remains for later approved slices. |

## Gate Result

Proceed to accepted slice commit for Slice 1.
