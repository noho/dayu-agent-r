# WU-TOOLS-01-F03 Slice 2 Fix Gate - AgentCodex

## Scope

- Work unit: `WU-TOOLS-01-F03 Web CI Smoke Generation`
- Slice: Slice 2 fix gate only
- Agent: AgentCodex
- Date: 2026-06-10
- Boundary: only addressed accepted code review findings; did not enter re-review, Slice 3, commit, push, or PR.

## Changed Files

- `utils/smoke_web_ci.py`
- `tests/tools/web/test_smoke_web_ci.py`
- `docs/reviews/wu-tools-01-f03-fix-slice2-codex.md`

## Findings Fixed

| Finding | Fix |
|---|---|
| Exit code `0` / `1` / `2` literals carried semantic meaning | Added `_EXIT_OK`, `_EXIT_LOCAL_FAILURE`, and `_EXIT_SCHEMA_OR_INFRA_FAILURE`; replaced semantic exit-code literals in smoke classification, summary aggregation, skip summary, and error returns. Tests still assert numeric external contract values. |
| Inline `not_opted_in` bucket | Added `_BUCKET_NOT_OPTED_IN` and used it in `_skipped_summary`. |
| `_STDIO_PREFIX_CHARS` and `_prefix_text` dead code | Removed both unused definitions. |
| Opt-in Slice 2 execution with no local cases lacked explicit summary signal | Added a Slice 2 skip item with bucket `local_fixture_attached_by_slice3`, explaining that local HTML/PDF fixture smoke is attached by Slice 3. This is only added from the opt-in `_execute_smoke` path; non-opt-in `_skipped_summary` semantics remain unchanged. |
| External schema validation used HTML-level requirements without local explanation | Added `_external_diagnostic_schema_gap()` with a localized docstring explaining that external diagnostic-only artifacts intentionally require only requests/fetch facts, not PDF-specific fields. |

## Deferred Findings

- Docling exception type names remain deferred to Slice 3 or Slice 5 per controller adjudication.
- Default timeout literals remain deferred to Slice 3 or Slice 5 per controller adjudication.
- Dataclass docstring convention remains unchanged.
- Run label date format remains unchanged.

## Tests Updated

- Added `test_opted_in_without_local_cases_reports_slice3_fixture_skip` to lock the opt-in/no-local-case Slice 2 summary signal.
- Extended the external-limit test to assert the Slice 2 local fixture skip signal is present while external cases remain diagnostic-only.

## Validation Results

- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py tests/tools/web/test_diagnose_web_access.py -q`
  - Result: passed, `25 passed in 0.36s`
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: passed, `0 errors, 0 warnings, 0 informations`
- `git diff --check`
  - Result: passed

## README Decision

- `tests/README.md` was checked because this fix updated `tests/tools/web/test_smoke_web_ci.py`.
- No README update was made. Existing `tests/tools/web/` guidance already requires deterministic Web tests with monkeypatch/fixture substitutes and no live network; this fix does not add a new test layer or change that boundary.

## Residual Risks

- Slice 2 still does not execute local HTML/PDF fixture smoke by design; the summary now makes that intermediate state explicit.
- Real local fixture server, PDF bytes, and Docling route verification remain Slice 3 work.
- External URLs remain diagnostic-only and do not affect local gate exit code, as required.
