# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Implementation - AgentCodex

## Scope

- Gate: implementation / fix.
- Batch: Batch A - Web/Doc/FMP Boundary Safety plus low-coupling OpenAI retry policy fix.
- Accepted findings fixed:
  - `145711-01` Web private-network policy bypass by redirects, meta refresh, and browser navigation.
  - `145711-09` `search_files` symlink containment bypass.
  - `145711-10` FMP resolver first fuzzy result company identity injection.
  - `145711-11` `fetch_web_page` missing pre-conversion body limits.
  - `150304-05` OpenAI retry off-by-one / retry-count contract hardening.

## Changed Files

- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_tools.py`
- `tests/tools/web/test_web_tools_provider.py`
- `dayu/tools/doc_tools.py`
- `tests/tools/test_doc_tools_provider.py`
- `dayu/fins/resolver/fmp_company_info.py`
- `tests/fins/test_fmp_company_info_resolver.py`
- `dayu/engine/runners/openai/retry_policy.py`
- `tests/engine/runners/openai/test_retry_backoff.py`
- `dayu/engine/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

## Owner Decisions

- Web URL safety remains owned by Web fetch transport. The same predicate now validates the initial URL, each HTTP redirect hop, final response URL, meta refresh target, Playwright route request URL, and Playwright page URL after navigation/settle.
- Web body limits remain owned by Web fetch transport. Requests main fetch now reads `stream=True` responses through bounded wire bytes, then bounded decompressed bytes, before HTML/Docling conversion.
- Doc file access remains owned by Doc tools. `search_files` now receives allowed roots at the business owner boundary and re-resolves each candidate with `strict=True` before processor or line-scan reads.
- FMP company identity remains owned by `FmpCompanyInfoResolver`. `search-symbol` must contain an exact normalized symbol match before company identity is returned; no exact match raises `FmpCompanyInfoResolutionError`, allowing Service's existing ticker-only fallback.
- OpenAI retry semantics remain owned by retry policy. `max_retries` is fixed as retry count after first failure; `max_retries=0` means no retry after attempt 1 failure.

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/fins/test_fmp_company_info_resolver.py tests/engine/runners/openai/test_retry_backoff.py -q`
  - Result: `114 passed, 1 skipped`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: passed.
- Source scan:
  - No `return results[0]`, first-result fuzzy FMP fallback, or `allow_redirects=True` remains in touched owner files.
  - Remaining `response.content` reads in `web_fetch_orchestrator.py` occur after `_materialize_response_body()` has populated bounded content.

## README Decision

- Updated `dayu/engine/README.md` for `RunnerSpec.max_retries` retry-count semantics.
- Updated `dayu/fins/README.md` for FMP exact ticker identity requirement.
- Updated `tests/README.md` for new Web redirect/meta/body and Doc symlink containment regression coverage.

## Residual Risk

- Playwright live-browser behavior was covered with deterministic route-level regression, not a live browser smoke. Existing optional live browser cleanup smoke remains environment-gated.
- Web body wire-byte accounting relies on `requests` raw stream for production responses; focused tests use real `requests.Response` plus `urllib3.HTTPResponse` raw stream to cover that boundary.

## Stop Status

Batch A implementation and required validation are complete. Batch B/C/D/E were not started.
