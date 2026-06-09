# WU-TOOLS-01-F01-02 Slice 1 Fix - AgentCodex

## Metadata

| 项目 | 值 |
|---|---|
| work unit | WU-TOOLS-01-F01-02 |
| gate | fix after Slice 1 code review |
| slice | Slice 1 - Fins Awaiting Tools Token Bridge |
| accepted plan commit | `af3ac6b8` |
| implementation artifact | `docs/reviews/wu-tools-01-f01-02-slice1-implementation-codex.md` |
| controller adjudication | `docs/reviews/wu-tools-01-f01-02-slice1-code-review-controller-adjudication.md` |
| date | 2026-06-08 |

## First-Principles Judgment

Accepted findings are valid and limited to Slice 1. The create-before-submit cancel branch had already created a durable Fins job but intentionally skipped background submit; leaving that job in non-terminal `cancelling` meant no runner existed to perform later terminalization. The correct local fix is to use the existing Fins job store terminal state `cancelled` in that branch, without adding a state machine or changing Host / Engine contracts.

## Fixes

| Finding | Fix |
|---|---|
| S1-F1 unused `_create_queued_job` | Removed the unused private helper and kept only the start-lock-owned queued record creation helper. The required `rg` command has no matches in the allowed code/test files. |
| S1-F2 no-runner `CANCELLING` job after create-before-submit cancel | `start_download` and `start_preprocess` now call existing `_save_cancelled(start.record)` when the post-create checkpoint observes cancellation. The branch returns a `CANCELLED` `FinsIngestionJobStart` and does not submit executor work. |
| S1-F3 brittle exact checkpoint count assertion | Runtime tests no longer assert `token.check_count == 2`; they assert durable state, `cancellation_requested`, and empty executor operations. |
| S1-F4 incoherent `_CancelOnSecondCheckToken` metadata | The test token now records a cancelled state once observed. After that point `cancel_reason()` returns `host-cancelled` and `requested_at()` returns a stable aware timestamp. |

## README Decision

- `dayu/fins/README.md`: read the `Agent更新约束【必须遵守】` section. The current runtime behavior changed from create-before-submit `cancelling` to terminal `cancelled`, so the Fins runtime cancellation description was updated.
- `tests/README.md`: read the current testing handbook scope. The runtime test coverage description was updated from create-before-submit `job cancelling` to `job cancelled`.

## Validation

- `rg "def _create_queued_job|_create_queued_job\\(" dayu/fins/ingestion_runtime.py tests/fins/test_fins_ingestion_runtime.py`
  - Result: passed; no matches.
- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py tests/fins/test_fins_ingestion_runtime.py -q`
  - Result: passed; `48 passed, 3 warnings in 2.01s`.
  - Warnings are existing `edgar` dependency deprecation warnings.
- `source .venv/bin/activate && pyright`
  - Result: passed; `0 errors, 0 warnings, 0 informations`.

## Residual Risks

| ID | 状态 | 说明 |
|---|---|---|
| S1-R1 | deferred | Broader Host awaiting accept orphan window remains outside Slice 1 and stays assigned to WU-WAIT-03 or an independent Host awaiting activation design work unit. |
| S1-R2 | accepted limitation | Submit-after-start synchronous I/O still cannot be physically preempted by Host token; background jobs continue to observe durable Fins job cancellation. |
| S1-R3 | out of scope | Web / Doc / Fins read token propagation remains for later approved slices. |

## Scope Guard

No review, commit, push, PR, merge, Host / Engine contract change, Web / Doc / Fins read slice change, control document edit, or review artifact edit was performed in this fix gate.
