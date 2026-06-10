# WU-TOOLS-01-F01-02-R3 Slice 2 Implementation - Codex

## Gate / Scope

- Gate: implementation
- Work unit: `WU-TOOLS-01-F01-02-R3`
- Slice: Slice 2 Web Native Tools
- Scope: `dayu/tools/web/provider.py`, `dayu/tools/web/web_tools.py`, `dayu/tools/web/web_search_providers.py`, `tests/tools/web/test_web_tools_provider.py`
- Non-goals honored: no Host / Engine / Service / ToolRuntime / Fins / Doc changes; legacy adapter directory not deleted; no commit created.

## First-principles judgment

The motivation is valid. Web provider discovery was still collecting OLD declarations and adapting them through `dayu.tools._legacy_adapter`, while current runtime discovery expects providers to expose native `ToolDefinition` and async `ToolCallable`. That adapter path also projected Host token cancellation as failed `tool_cancelled` instead of `ToolCancelledOutcome(host_cancelled)`, so fixing only the exception mapper would preserve the wrong production dependency.

## Changes

- Replaced Web discovery adapter flow with native `build_web_tool_definitions(config: WebToolsConfig)`.
- Moved `WebToolsConfig` to `web_tools.py` so provider parsing can pass one typed config object to the native builder.
- Preserved provider id/version/source refs and provider config fields:
  - `provider`
  - `request_timeout_seconds`
  - `max_search_results`
  - `fetch_truncate_chars`
  - `allow_private_network_url`
  - `playwright_channel`
  - `playwright_storage_state_dir`
- Preserved Web schema names, parameter fields, descriptions, display names, tags, truncate specs and success return shapes.
- Preserved deterministic provider fallback and fetch pipeline behavior; the existing requests / content probe / Docling / Playwright fallback logic remains the business path.
- Added one provider-level `asyncio.Lock()` shared by `search_web` and `fetch_web_page`; lock is acquired after schema validation and pre-cancel checks, before provider/fetch business work.
- Replaced Web legacy cancellation errors with Web-local cancellation signals that are caught inside native callable boundaries and returned as `ToolCancelledOutcome(reason="host_cancelled")`.
- Kept ordinary search / network / fetch failures as `ToolFailedOutcome`.
- Updated Web tests for native schema audit, pre-cancel, provider-attempt cancel, Playwright cancel, provider config projection, private URL policy, Playwright config projection, truncation, failure projection and shared provider lock concurrency.

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py` - passed, 17 tests.
- `source .venv/bin/activate && pytest tests/tools/web/test_smoke_web_ci.py` - passed, 35 tests, 3 third-party deprecation warnings from `edgar`.
- `source .venv/bin/activate && pyright` - passed, 0 errors.
- `rg "_legacy_adapter|LegacyToolDeclarationCollector|LegacySyncToolCallable|adapt_collected_tools|tool_cancelled" dayu/tools/web tests/tools/web/test_web_tools_provider.py` - no matches.
- Extra local smoke: `source .venv/bin/activate && python utils/smoke_web_ci.py --external-limit 0 --include-playwright --run-label slice2-native-web` - passed. Local HTML, PDF, browser fallback and local assembly config passed; external URL cases were intentionally skipped with `--external-limit 0`; search provider diagnostics were diagnostic-only, with missing Tavily / Serper keys classified as provider-key-missing and DuckDuckGo passing.

## Docs / README decision

`tests/README.md` was read. This slice changes Web provider tests, but the README still describes the broader tools test inventory and the legacy adapter remains until later Slice 4. The user also constrained allowed files to Web code/tests plus this artifact. No README was modified in Slice 2.

## Residual risks

- Real external URL fetch smoke was not run in this slice because the extra smoke used `--external-limit 0` to keep validation deterministic. Owner: existing Web CI diagnostics / smoke follow-up.
- Real Tavily and Serper provider success paths were not validated because API keys were not configured in the environment; smoke classified those cases as diagnostic-only provider-key-missing. Owner: provider-configured Web CI environment.
- Legacy adapter deletion remains for later approved Slice 4; this slice only removes Web production dependency.

## Completion status

Slice 2 implementation complete. No blocking open questions.
