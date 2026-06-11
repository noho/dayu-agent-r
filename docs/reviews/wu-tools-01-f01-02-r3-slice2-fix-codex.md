# WU-TOOLS-01-F01-02-R3 Slice 2 Fix - Codex

## Scope

- Gate: fix after code review
- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 2, Web Native Tools
- Accepted findings fixed: `S2-CR-01` through `S2-CR-04`
- Explicit non-goals honored: no Doc / Fins / Host / Engine / Service / ToolRuntime changes; legacy adapter directory not deleted; no commit created.

## First-Principles Judgment

The accepted findings are valid and scoped. `search_web` provider exhaustion is a business-level unavailability condition, not an implementation crash, so collapsing it into `execution_error` loses useful recovery semantics for the LLM and Host consumers. The Playwright cancellation docstring mismatch is a maintenance defect. The `provider.py.__all__` export exposes a migrated config type through a second public path. The provider lock test already had a reliable final no-overlap assertion, but its mid-assertion relied on arbitrary sleep and did not prove scheduling state.

## Changes

- Added `WebSearchProviderUnavailableError` for exhausted search providers and mapped it at the native `search_web` callable boundary to `ToolFailedOutcome(error="search_provider_unavailable")`.
- Added a non-empty LLM-readable recovery hint for provider-unavailable search failures.
- Updated the provider exhaustion test to drive Tavily, Serper and DuckDuckGo failures through the real provider fallback path, with fake API keys to make the `auto` candidate order deterministic.
- Updated `_try_playwright_fallback` docstring to declare `WebToolCancelledError` on Playwright cancellation.
- Removed `WebToolsConfig` from `dayu.tools.web.provider.__all__`; the local import remains only for config parsing.
- Reworked the Web provider lock concurrency test to replace arbitrary sleep with a controlled `asyncio.to_thread` substitute, proving the second business body does not enter while the first holds the provider lock.

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py` - passed, 17 tests.
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py` - passed, 35 tests, 3 third-party `edgar` deprecation warnings.
- `source .venv/bin/activate && pyright` - passed, 0 errors.
- `git diff --check` - passed.

## README Decision

`tests/README.md` was read because this fix updates Web provider tests. Its Web tools section already states these tests must remain deterministic and use monkeypatch / fixtures instead of live network requests. The fix follows that rule and does not introduce a new test layer or command, so no README update is needed.

## Residual Risk

- Real Tavily / Serper success paths remain dependent on external credentials and are outside this fix gate.
- Legacy adapter deletion remains owned by later approved slice work.
