# WU-TOOLS-01-F01-03 Draft PR Readiness - Controller

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- Branch: `phase/wu-tools-01-f01-03`
- Gate: `ready-to-open-draft-PR`
- Design sources: `docs/host/design.md`; `docs/engine/design.md`
- Plan source: `docs/host/wu-tools-01-f01-03-production-fins-ingestion-plan.md`
- Control source: `docs/host/issues-implementation-control.md`

## Summary

WU-TOOLS-01-F01-03 is ready for a draft PR.

Implemented scope:

- Migrated OLD SEC downloader behavior into NEW shared Fins runtime path.
- Migrated OLD CN/HK downloader behavior into NEW shared Fins runtime path.
- Migrated OLD SEC/CN upload workflow behavior into NEW shared Fins runtime path.
- Added production upload long-transaction path: `start_upload` creates a durable Fins job and returns awaiting outcome through `start_fins_upload`.
- Added `financial-upload-tools` provider, upload path allowlist validation, Fins wait adapter upload binding, Service assembly recognition, and default disabled config.
- Updated README facts and Issue #129 tracking for future prepare/activate hardening.

Non-goals preserved:

- No Host/Engine public contract changes.
- No OLD downloader or upload workflow business-rule rewrite.
- No separate CLI/CI/tool business logic.
- No upload-specific private activation workaround.

## Accepted Commits

- Accepted plan: `6f519cea`
- Slice 1 accepted: `8f11fac9`
- Slice 2 accepted: `0a2ec16c`
- Slice 3 accepted: `97442f6a`
- Slice 4 accepted: `bb74fa1d`
- Slice 5 accepted: `2504df4c`
- Slice 6 closeout: `0566fb29`
- Accepted aggregate deepreview: `1b14444c`
- Deepreview control update: `6f302ca6`

## Validation

- `source .venv/bin/activate && pytest tests/fins tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q`
  - Result: `294 passed, 1 skipped, 3 warnings`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- Aggregate deepreview fix validation:
  - `pytest tests/fins/test_fins_ingestion_tools.py -q`: `29 passed, 3 warnings`
  - `python -m pyright dayu/ tests/ utils/`: `0 errors`
  - `git diff --check`: passed

## Residual Risks

- Issue #129 tracks two-phase prepare/activate hardening for awaiting external jobs, now including `start_upload`.
  - Tracking comment: `https://github.com/noho/dayu-agent-r/issues/129#issuecomment-4659131069`
- Physical cancellation beyond cooperative `request_cancel(...)` remains owned by WAIT/Issue #92 scope.
- Broader upload runtime failure-path matrix remains deferred hardening from Slice 4.

No unowned residual risk blocks draft PR creation.

## Draft PR Recommendation

Create a draft PR for branch `phase/wu-tools-01-f01-03` against `main`, then proceed to PR review gate.
