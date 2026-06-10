# WU-TOOLS-01-F03 Slice 1 Fix Gate - AgentCodex

## Scope

- Gate: fix gate only for WU-TOOLS-01-F03 Slice 1.
- Input review artifacts:
  - `docs/reviews/wu-tools-01-f03-code-review-slice1-mimo.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice1-ds.md`
  - `docs/reviews/wu-tools-01-f03-code-review-slice1-controller-adjudication.md`
  - `docs/reviews/wu-tools-01-f03-implementation-slice1-codex.md`
  - `docs/host/wu-tools-01-f03-web-ci-smoke-plan.md`
- Boundary: did not enter re-review, next slice, commit, push, or PR.

## Changed Files

- `utils/diagnose_web_access.py`
- `tests/tools/web/test_diagnose_web_access.py`
- `docs/reviews/wu-tools-01-f03-fix-slice1-codex.md`

## Findings Fixed

- DS Finding 1 / controller accepted required action:
  - Changed `_DIAGNOSTIC_SCHEMA_REVISION` from `2` to `1`.
  - Updated deterministic test assertion in `test_cli_single_mode_writes_deterministic_json` from `2` to `1`.
  - Rationale: this is the first explicit diagnostic revision marker for `web-diagnostics-v1`; starting at `2` implied an undocumented revision 1.

## Localized Accepted-Low Notes

- Added a short comment near schema constants:
  - `schema_version` identifies the diagnostics artifact schema.
  - `diagnostic_schema_version` / `diagnostic_schema_revision` are explicit F03 smoke validation markers for the same artifact.
- Added a clarifying comment near `_observed_failing_path_from_payload` fallback:
  - the fallback is only for existing comparison buckets;
  - newly added buckets must be checked before being treated as a real failing path.

## Findings Deferred

- DS Finding 2 (`_DOCLING_DEPENDENCY_EXCEPTION_TYPES` subclass matching):
  - Deferred per controller adjudication.
  - No evidence in this fix gate requires changing dependency exception classification.
- MiMo Finding 1 / DS Finding 3 behavior change for bucket-as-path fallback:
  - Behavior intentionally unchanged in this fix gate.
  - Only added the localized comment allowed by adjudication and user instructions.
- MiMo Finding 2 dataclass docstring convention:
  - Not changed. It is accepted-low and outside the user-specified optional localized fixes.
- DS Finding 4 duplicate schema field value:
  - Addressed only with the schema constants comment; no schema field behavior changed.

## Validation Results

- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q`
  - Result: `19 passed in 0.38s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`
  - Note: pyright also printed a version update notice (`v1.1.409 -> v1.1.410`), not a type-check diagnostic.
- `git diff --check`
  - Result: passed with no whitespace errors.

## Residual Risks

- Slice 1 still only emits diagnostics observed facts and Docling invocation evidence; smoke pass/fail/skip classification remains for later slices.
- `_observed_failing_path_from_payload` retains its existing fallback behavior. The new comment documents the synchronization requirement for future comparison buckets, but does not enforce it.
- No live Web, real browser, provider availability, or external-site stability risk is closed by this fix gate.

## Completion Status

Fix gate complete. Stopped after writing this artifact; no commit, push, PR, re-review, or next-slice work was performed.
