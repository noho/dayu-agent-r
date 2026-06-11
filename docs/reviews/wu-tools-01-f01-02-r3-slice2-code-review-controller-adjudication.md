# WU-TOOLS-01-F01-02-R3 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 2, Web Native Tools
- Gate: code review
- Implementation artifact: `docs/reviews/wu-tools-01-f01-02-r3-slice2-implementation-codex.md`
- MiMo review: `docs/reviews/wu-tools-01-f01-02-r3-slice2-code-review-mimo.md`
- DS review: `docs/reviews/wu-tools-01-f01-02-r3-slice2-code-review-ds.md`

## Controller Verification Before Adjudication

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py`: 17 passed
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py`: 35 passed; third-party `edgar` deprecation warnings only
- `source .venv/bin/activate && pyright`: 0 errors
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|LegacySyncToolCallable|adapt_collected_tools|tool_cancelled" dayu/tools/web tests/tools/web/test_web_tools_provider.py`: no matches
- `git diff --check`: passed

## Reviewer Conclusions

- MiMo: `pass-with-findings`
- DS: `pass-with-findings`

Both reviewers confirm Slice 2 removes Web production dependency on the legacy adapter, preserves core `search_web` / `fetch_web_page` schema and config behavior, and maps Host cancellation to `ToolCancelledOutcome(reason="host_cancelled")`.

## Accepted Findings For Fix

### S2-CR-01: `search_web` Provider Failure Is Over-Flattened To `execution_error`

- Source: MiMo finding 002; DS finding F1.
- Severity: medium.
- Decision: accepted.
- Evidence: `_call_search_web` catches non-cancellation exceptions and routes them through `_unexpected_failed_outcome(error="execution_error")`. This means the expected business case "all search providers unavailable" is indistinguishable from an unexpected implementation failure.
- Required fix: add a Web search business failure type or equivalent typed result and map `RuntimeError` from exhausted providers to a stable business error code, e.g. `search_provider_unavailable`, with an LLM-readable message and recovery hint. Keep genuine unexpected exceptions as `execution_error`.
- Required test: update or add a `search_web` failure test that asserts the provider-unavailable path returns the new stable business error code and non-empty hint.

### S2-CR-02: `_try_playwright_fallback` Docstring Hides Cancellation Raise

- Source: MiMo finding 001; DS finding F2.
- Severity: low.
- Decision: accepted.
- Evidence: `_try_playwright_fallback` catches Playwright `CancelledError` and calls `_raise_fetch_cancelled(...)`, which raises `WebToolCancelledError`, while the docstring says `Raises: 无。`.
- Required fix: update the docstring to declare `WebToolCancelledError` for Playwright cancellation. No behavior change required.

### S2-CR-03: `provider.py.__all__` Re-exports `WebToolsConfig`

- Source: MiMo finding 003; DS finding F3.
- Severity: low.
- Decision: accepted.
- Evidence: `WebToolsConfig` is now defined in `web_tools.py`, while `provider.py` still lists it in `__all__`. The project rules reject compatibility re-export paths.
- Required fix: remove `WebToolsConfig` from `provider.py.__all__`; keep the local import only for `_parse_config`.

### S2-CR-04: Web Provider Lock Test Has A Timing-Weak Mid-Assertion

- Source: DS finding F4.
- Severity: low.
- Decision: accepted as test hardening.
- Evidence: `test_web_provider_serializes_search_and_fetch_business` uses `await asyncio.sleep(0.05)` before a mid-assertion. The final assertion still validates no overlap, but the mid-assertion does not prove the fetch task attempted to enter the lock.
- Required fix: replace or supplement the timing-based assertion with deterministic coordination showing the fetch callable has reached the business boundary only after the search business releases the provider lock. Keep the test free of arbitrary sleeps where practical.

## Rejected / Deferred Findings

No reviewer finding is rejected in this adjudication.

Deferred residual risks remain outside this slice:

- Real external URL fetch smoke and Tavily / Serper success paths require configured external environment and remain owned by the Web CI diagnostics / smoke follow-up.
- Legacy adapter directory deletion remains Slice 4.

## Required Fix Gate

AgentCodex should implement `S2-CR-01` through `S2-CR-04` only, update `docs/reviews/wu-tools-01-f01-02-r3-slice2-fix-codex.md`, and run:

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py`
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py`
- `source .venv/bin/activate && pyright`
- `git diff --check`
