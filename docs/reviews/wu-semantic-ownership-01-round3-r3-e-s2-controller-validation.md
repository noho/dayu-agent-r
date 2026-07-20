# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S2 controller validation

## Scope

- Gate: R3-E Slice S2 implementation controller validation.
- Slice objective: Web resource budget owner, bounded HTTP/search/browser materialization, challenge decision owner, and DuckDuckGo response-shape owner.
- Validated artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-implementation-codex.md`.
- This validation does not close S3 diagnostic schema/storage/smoke work, S4 Documents bounded source work, aggregate deepreview, or final closeout.

## Changed files reviewed

- `dayu/tools/web/web_resource_budget.py`
- `dayu/tools/web/provider.py`
- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_challenge_detection.py`
- `dayu/tools/web/web_search_providers.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/web/web_tool_projection_text.py`
- `utils/diagnose_web_access.py`
- `dayu/config/README.md`
- `tests/tools/web/test_web_tools_provider.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-implementation-codex.md`

## Controller judgment

S2 implementation is ready for independent code review. Direct source inspection confirms that the current Web tool production paths now route the S2 semantics through owner-level contracts rather than downstream repair:

- `WebResourceBudget` owns the complete resource budget and rejects partial/unknown/non-positive/bool configuration values.
- HTTP response materialization reads wire bytes through streamed chunks, applies decoded caps through bounded codec layers, rejects unsupported bounded encodings instead of whole-body fallback, and writes only bounded body bytes back to `requests.Response`.
- Tavily, Serper, and DuckDuckGo fixed endpoint calls use `stream=True`, `allow_redirects=False`, and shared bounded search response materialization before JSON/HTML parsing.
- Playwright page projection executes bounded DOM/text preflight before `page.content()` and performs post-projection length checks.
- Challenge handling uses `BotChallengeDecision` plus `challenge_fallback_action`; caller-side `challenge_detected && status allowlist` decision ownership is no longer present in Web tool paths.
- DuckDuckGo parsing distinguishes known result shape, explicit no-results text, challenge/login/anomaly shape, and response-shape drift.

## Validation rerun

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k 'body or decompress or warmup or playwright or challenge or duckduckgo or resource_budget'`
  - Result: `62 passed, 2 skipped, 54 deselected`.
- `source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q -k 'challenge or egress or redirect'`
  - Result: `2 passed, 21 deselected`.
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`
  - Result: `116 passed, 2 skipped`.
- `source .venv/bin/activate && PYTEST_PLUGINS=numpy,multiprocessing.connection pytest tests/tools/web/test_web_tools_provider.py -q --cov=dayu.tools.web.web_resource_budget --cov=dayu.tools.web.web_challenge_detection --cov=dayu.tools.web.web_search_providers --cov-report=term-missing`
  - Result: `116 passed, 2 skipped`.
  - Coverage: `web_resource_budget.py 100%`, `web_challenge_detection.py 90%`, `web_search_providers.py 87%`, total `89%`.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `source .venv/bin/activate && git diff --check`
  - Result: pass.
- `git diff --check -- <S2 tracked files>`
  - Result: pass.
- `git diff --no-index --check /dev/null dayu/tools/web/web_resource_budget.py`
  - Result: no whitespace output. Exit code 1 is expected because the new file differs from `/dev/null`.
- `git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-implementation-codex.md`
  - Result: no whitespace output. Exit code 1 is expected because the new file differs from `/dev/null`.

## Source scans

- `rg -n "gzip\\.decompress|brotli\\.decompress|zstd.*decompress|page\\.content\\(|outerHTML|innerHTML|textContent|innerText|challenge_detected.*http_status|resource_budget" dayu/tools/web tests/tools/web utils/diagnose_web_access.py dayu/config/README.md`
  - Expected production hits only: `page.content()` in `web_playwright_backend.py` after bounded preflight; `innerText` in the post-preflight full text script; `resource_budget` owner/consumer/tests/docs.
  - Expected test hits: forbidden-token assertions and owner tests.
  - Existing S3-scoped diagnostic hit: `utils/diagnose_web_access.py` still has pre-existing `page.content()` in diagnostic browser sampling. This is not fixed in S2 and remains assigned to S3 diagnostic bounded source work.
- `rg -n "requests\\.(get|post|request|head)|session\\.(get|post|request|head)|Session\\(\\)|allow_redirects|stream=True|iter_content|raw\\.stream" dayu/tools/web utils/diagnose_web_access.py`
  - Search provider endpoint calls use `stream=True` and `allow_redirects=False`.
  - Shared HTTP session and diagnostic script matches are outside the S2 fixed endpoint response owner path or pre-existing S3 diagnostic scope.
- `rg -n "challenge_detected|BotChallengeDecision|challenge_fallback_action|detect_bot_challenge" dayu/tools/web utils/diagnose_web_access.py tests/tools/web/test_web_tools_provider.py`
  - Web tool callers use `BotChallengeDecision` and `challenge_fallback_action`.
  - `utils/diagnose_web_access.py` retains the existing v1 `challenge_detected` boolean field, now derived from `BotChallengeDecision.CONFIRMED`; no S3 schema migration was implemented.

## Residual classification

- Chromium-internal DOM construction before preflight remains a browser runtime resource residual. Owner: future browser sandbox/resource-lane work, not a S2 correctness blocker.
- `utils/diagnose_web_access.py` still contains existing unbounded browser page sampling via `page.content()`. Owner: R3-E S3 diagnostic/schema/storage/smoke slice.
- `diagnostic_error_chars` and `diagnostic_events` are present in the typed budget but not consumed by S2 production paths. Owner: R3-E S3.
- DuckDuckGo strict HTML shape may fail closed when the provider changes. Owner: Web search provider maintenance; this is the intended fail-closed behavior.
- Brotli remains unsupported rather than bounded. Owner: Web codec owner if a bounded streaming API is later introduced; restoring whole-body `brotli.decompress` is not allowed.

## Decision

Controller validation: PASS for S2 code review entry.

No controller-side blocker found. Proceed to AgentMiMo and AgentDS S2 code review.
