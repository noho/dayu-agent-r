# WU-TOOLS-01-F01-03 Final Closeout - Controller

## Scope

- Work unit: `WU-TOOLS-01-F01-03`
- PR: `https://github.com/noho/dayu-agent-r/pull/131`
- Branch: `phase/wu-tools-01-f01-03`
- Final gate: `draft-PR-pass`

## Status

Draft PR #131 is open and remains draft.

Accepted PR review commit:

- `8f016ac3 gateflow: accept WU-TOOLS-01-F01-03 PR review`

## What Landed

- Production SEC/CN/HK download runtime migration using shared `DefaultFinsRuntime` / `FinsIngestionRuntime`.
- Production SEC/CN upload runtime migration using shared runtime and migrated OLD upload workflow logic.
- `start_fins_upload` awaiting tool, `financial-upload-tools` provider, upload path allowlist validation, Fins wait adapter binding and Service assembly recognition.
- Default disabled upload provider config and README updates.
- Issue #129 tracking update for `start_upload` prepare/activate hardening.
- LLM-facing tool failure/cancel messages were cleaned up during aggregate and PR review gates.

## Validation

Final relevant validation already recorded in Slice 6 and review gates:

- `pytest tests/fins tests/service/test_host_assembly.py tests/tools/test_combined_tools_acceptance.py -q`
  - Result: `294 passed, 1 skipped, 3 warnings`
- `python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
- PR review fix validation:
  - `pytest tests/fins/test_fins_ingestion_tools.py -q`: `29 passed, 3 warnings`
  - `python -m pyright dayu/ tests/ utils/`: `0 errors`
  - `git diff --check`: passed

GitHub checks:

- `gh pr checks 131 --repo noho/dayu-agent-r`
  - Result: no checks reported on the branch.

## Residual Risks

- Issue #129 tracks two-phase prepare/activate hardening for awaiting external jobs, including `start_upload`.
- Issue #92 / WAIT scope tracks physical external-job cancellation beyond cooperative `request_cancel(...)`.
- Broader upload runtime failure-path matrix remains deferred hardening from Slice 4.
- Real Docling integration coverage remains opt-in via `DAYU_RUN_DOCLING_UPLOAD_INTEGRATION=1`.

No active unowned residual risk remains.

## Next Entry Point

After PR #131 merge decision, continue with `WU-TOOLS-01-F02` unless the user asks to address a PR comment or CI result first.
