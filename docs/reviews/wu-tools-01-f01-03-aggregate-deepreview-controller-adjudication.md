# WU-TOOLS-01-F01-03 Aggregate Deepreview Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Gate: aggregate deepreview
- Deepreview artifacts:
  - `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-ds.md`
- Fix artifact:
  - `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-rereview-mimo.md`
  - `docs/reviews/wu-tools-01-f01-03-aggregate-deepreview-rereview-ds.md`

## Verdict

`accepted`

Aggregate deepreview is accepted after fix and re-review. The accepted deepreview commit is `1b14444c`.

## Findings

### MiMo F1: `durable job record` in LLM-facing start-failed messages

- Decision: accepted
- Severity: medium, non-blocking
- Fix: replaced model-visible messages in download, preprocess and upload tools with business-readable Chinese messages that say the task failed to start and the task record could not be saved.
- Re-review: MiMo and DS confirmed fixed.

### MiMo F2: `Fins ingestion runtime` in LLM-facing start-failed hints

- Decision: accepted
- Severity: medium, non-blocking
- Fix: replaced model-visible hints in download, preprocess and upload tools with a user-actionable instruction to check Fins workspace storage permissions or contact an administrator.
- Re-review: MiMo and DS confirmed fixed.

### MiMo observations

- Concrete storage factory imports in pipeline factory functions are accepted as assembly/factory code and are not blocking.
- Deferred test-matrix and cleanup observations remain quality debt, not correctness blockers. They are either already tracked by Issue #129 / WAIT follow-up scope or are non-blocking cleanup candidates.

### DS findings

- DS aggregate deepreview returned `pass` with no new findings.

## Validation

Controller validation after the fix:

- `source .venv/bin/activate && pytest tests/fins/test_fins_ingestion_tools.py -q`
  - Result: `29 passed, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed
- Targeted scan for `durable job record|Fins ingestion runtime` in the affected tool and test files:
  - Result: no matches

## Residual Risks

- Crash recovery and prepare/activate hardening for awaiting external jobs remain tracked by Issue #129, including `start_upload`.
- Physical external-job cancellation beyond cooperative `request_cancel(...)` remains tracked by WAIT/Issue #92 scope.
- Broader upload runtime failure-path matrix remains a deferred hardening item from Slice 4 and does not block WU completion.

No active unowned residual risk remains for this work unit.
