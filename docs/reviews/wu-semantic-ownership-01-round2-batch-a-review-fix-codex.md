# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Review Fix - Codex

## Scope

- Gate: code-review fix gate
- Batch: A only
- Accepted findings fixed: DS-F01, DS-F02, DS-F03
- Rejected findings intentionally unchanged: DS-F04, DS-F05
- Excluded: Batch B/C/D/E, control docs, commits, pushes

## Changed Files

- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_tools.py`
- `tests/tools/web/test_web_tools_provider.py`
- `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-codex.md`

## Fixed Findings

### DS-F01

Playwright URL safety now uses the same `_FetchUrlSafetyError` owner exception as the requests and meta-refresh paths.
The Playwright worker process preserves `blocked_url` and `blocked_stage` in its structured error payload, and the parent process reconstructs `_FetchUrlSafetyError` instead of collapsing the failure to a generic `RuntimeError`.
`_fetch_and_convert_with_playwright` re-raises URL safety failures so `web_tools.py` projects the same `permission_denied` failure and safety diagnostics as the requests path.

### DS-F02

`_request_with_safe_redirects` now returns the visited URL history alongside the final response and redirect hop count.
`_fetch_and_convert_content` merges that history into the meta-refresh `visited_urls` set before resolving any meta refresh target, so a meta refresh target that points back to an HTTP redirect hop is treated as an already visited URL.

### DS-F03

`_FetchBodyLimitExceeded` construction no longer calls `_build_fetch_content_runtime_context`, which can read `response.content`.
Body-limit failures now use `_build_fetch_body_limit_runtime_context`, which only copies status, URL, headers, and an optional bounded caller-provided body excerpt.

## Validation

- `source .venv/bin/activate && pytest -q tests/tools/web/test_web_tools_provider.py -k 'redirect_to_private or meta_refresh_to_private or meta_refresh_treats_redirect_hop or body_limit or playwright_route_blocks_private or playwright_url_safety or fetch_playwright_url_safety'`
  - Result: 8 passed, 37 deselected
- `source .venv/bin/activate && pytest -q tests/tools/web/test_web_tools_provider.py`
  - Result: 44 passed, 1 skipped
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: 0 errors, 0 warnings, 0 informations
- `git diff --check`
  - Result: passed

## Docs Decision

`tests/README.md` was checked because `tests/` changed. No README update was required because this fix adds tests inside an existing Web tools provider test layer and does not create a new test layer, command, workflow, or user-facing behavior.

## Residual Risk

- Live browser smoke remains outside this fix gate; deterministic Playwright process and projection tests cover the URL safety semantics without requiring a real browser.
- Optional Playwright warmup remains best-effort. URL safety failures from required Playwright navigation paths propagate as `_FetchUrlSafetyError`; blocked subresource requests continue to abort at the route boundary rather than failing the whole page.

## Completion Status

Accepted DS findings are fixed and validated. No Batch B/C/D/E files, control docs, commits, or pushes were touched.
