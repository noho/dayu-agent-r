# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S2 code-review fix controller validation

## Scope

- Gate: R3-E Slice S2 code-review fix controller validation.
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md`.
- Accepted findings under validation:
  - `R3-E-S2-CR-F01`
  - `R3-E-S2-CR-F02`
  - `R3-E-S2-CR-F03`

## Controller validation

All accepted current-scope findings are fixed and ready for independent re-review.

### R3-E-S2-CR-F01

Status: fixed.

Evidence:

- `tests/tools/web/test_web_tools_provider.py::test_identity_body_exact_decoded_limit_and_limit_plus_one` covers a response with no `Content-Encoding`.
- Exact decoded limit returns the original body.
- Limit-plus-one raises `_FetchBodyLimitExceeded`.
- The test asserts `limit_kind == "decompressed"` and `observed_bytes == decoded_limit + 1`, proving decoded cap rather than wire cap owns the failure.

### R3-E-S2-CR-F02

Status: fixed.

Evidence:

- `dayu/tools/web/web_playwright_backend.py::_materialize_bounded_page_projection` logs a debug message in the full-text `page.evaluate(_FULL_PAGE_TEXT_SCRIPT)` exception branch and preserves the existing `page_text = html` fallback.
- The log message does not include URL, HTML, headers, raw exception text, or other sensitive response material.
- `tests/tools/web/test_web_tools_provider.py::test_playwright_full_text_failure_logs_debug_and_falls_back_to_html` injects a full-text evaluate error, confirms HTML fallback, confirms the second evaluate call happened after preflight/content, and asserts the debug log record.
- No S3 diagnostic schema, durable payload, storage-state, or smoke oracle field was added.

### R3-E-S2-CR-F03

Status: fixed.

Evidence:

- `dayu/tools/web/web_playwright_backend.py` now defines `_BROWSER_DOM_TOO_LARGE_REASON`, `_BROWSER_TEXT_TOO_LARGE_REASON`, and `_BROWSER_RESOURCE_BUDGET_FAILURE_REASONS`.
- `_BrowserResourceBudgetExceeded`, `_browser_budget_failure`, DOM/text preflight failures, full projection failures, and Markdown length failure all use the shared reason constants/set.
- Stable reason values remain `browser_dom_too_large` and `browser_text_too_large`; behavior is unchanged.

## Validation rerun

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k "identity or playwright or body or decompress or resource_budget"`
  - Result: `44 passed, 2 skipped, 74 deselected`.
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`
  - Result: `118 passed, 2 skipped`.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && git diff --check`
  - Result: pass.

## Scope audit

- Rejected `R3-E-S2-CR-F04` remains unchanged: infra-only/header single signals stay `SUSPECTED`, not `CONFIRMED`.
- Rejected `R3-E-S2-CR-F05` remains unchanged: probe GET still only reads headers and closes the lease.
- Deferred `R3-E-S2-CR-F06` remains assigned to S3: diagnostic budget fixture ownership was not changed.
- No S3 diagnostic schema/storage/smoke, S4 Documents bounded source, Host/Engine/Fins, aggregate gate, or tool-security implementation was added.

## Decision

Controller validation: PASS for S2 code re-review entry.
