# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Review-Fix Controller Validation

## Scope

- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-review-fix-codex.md`
- Accepted review findings:
  - DS-F01 Playwright URL safety exception/projection parity.
  - DS-F02 redirect hop history participates in meta-refresh loop prevention.
  - DS-F03 body-limit exception context must not read unbounded `response.content`.

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/fins/test_fmp_company_info_resolver.py tests/engine/runners/openai/test_retry_backoff.py -q`
  - Result: `118 passed, 1 skipped`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.
- Source scan:
  - `rg -n "falls_back_to_first|return results\\[0\\]|allow_redirects=True|fallback to first|first symbol" dayu/fins/resolver/fmp_company_info.py dayu/tools/web tests/fins/test_fmp_company_info_resolver.py`
  - Result: no matches.

## Decision

Ready for Batch A re-review.

## Residual Risk

- Live browser smoke remains not run; deterministic Playwright process/projection tests cover the owner semantics.

