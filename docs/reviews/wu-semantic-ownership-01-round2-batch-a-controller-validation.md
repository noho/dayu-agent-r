# WU-SEMANTIC-OWNERSHIP-01 Round 2 Batch A Controller Validation

## Scope

- Batch: A - Web/Doc/FMP boundary safety plus OpenAI retry count.
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round2-batch-a-implementation-codex.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-round2-controller-adjudication.md`

## Changed Files Observed

- `dayu/tools/web/web_fetch_orchestrator.py`
- `dayu/tools/web/web_playwright_backend.py`
- `dayu/tools/web/web_tools.py`
- `dayu/tools/doc_tools.py`
- `dayu/fins/resolver/fmp_company_info.py`
- `dayu/engine/runners/openai/retry_policy.py`
- `tests/tools/web/test_web_tools_provider.py`
- `tests/tools/test_doc_tools_provider.py`
- `tests/fins/test_fmp_company_info_resolver.py`
- `tests/engine/runners/openai/test_retry_backoff.py`
- `dayu/engine/README.md`
- `dayu/fins/README.md`
- `tests/README.md`

## Validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/test_doc_tools_provider.py tests/fins/test_fmp_company_info_resolver.py tests/engine/runners/openai/test_retry_backoff.py -q`
  - Result: `114 passed, 1 skipped`.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`
  - Result: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`
  - Result: pass.
- Source scan:
  - `rg -n "falls_back_to_first|return results\\[0\\]|allow_redirects=True|fallback to first|first symbol" dayu/fins/resolver/fmp_company_info.py dayu/tools/web tests/fins/test_fmp_company_info_resolver.py`
  - Result: no matches.

## Controller Decision

Batch A is ready for code review. No controller-side validation blocker found.

## Residual Risk

- Real browser / network smoke was not executed in controller validation. Review should pay attention to production Playwright route/navigation behavior and requests-stream body handling.
- Batch B/C/D/E remain unstarted.

