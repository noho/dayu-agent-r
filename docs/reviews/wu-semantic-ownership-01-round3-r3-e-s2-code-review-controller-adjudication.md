# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E S2 code review controller adjudication

## Scope

- Gate: R3-E Slice S2 code review adjudication.
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-ds.md`
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-implementation-codex.md`
- Controller validation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-controller-validation.md`

## Review summary

- AgentMiMo: PASS, zero material findings.
- AgentDS: PASS with findings, six findings.

S2 remains a production-high slice because it changes Web tool resource, codec, challenge, search-provider, and LLM-facing failure behavior. Accepted findings require a fix gate and independent re-review before S2 can be accepted.

## Finding adjudication

| Finding | Source | Decision | Controller rationale | Required action |
|---|---|---|---|---|
| R3-E-S2-CR-F01 | DS-01 | accepted | Identity/no-content-encoding body is part of the same decoded cap owner contract as gzip/deflate/zstd. Current tests let wire cap trigger first and do not prove unencoded body over decoded cap is rejected. | Add owner-level tests for unencoded identity body exact-limit and limit-plus-one decoded cap behavior. |
| R3-E-S2-CR-F02 | DS-02 | accepted-narrowed | A failed post-preflight full text extraction should not be silently unobservable. S3 owns durable diagnostic fields, so S2 should not add schema or public diagnostic markers, but S2 can add owner-local debug logging and a focused test. | Add debug log in the fallback branch of `_materialize_bounded_page_projection`; keep fallback behavior and do not add S3 schema/diagnostic payload fields. |
| R3-E-S2-CR-F03 | DS-03 | accepted | Browser budget failure reason is a sealed semantic value and should not be duplicated across validator/projection call sites. The fix is low-risk and keeps S2 owner contract cleaner. | Extract a single module-level reason set and constants; use them in `_BrowserResourceBudgetExceeded`, `_browser_budget_failure`, and current call sites. |
| R3-E-S2-CR-F04 | DS-04 | rejected-with-reason | The accepted plan explicitly states ordinary infrastructure header is not sufficient for `confirmed`, while `suspected` is allowed to enter bounded diagnostic rather than blocked behavior. `challenge_fallback_action` treats `none` and `suspected` as `CONTINUE`, so no fallback bug exists. S3 may decide how to display suspected diagnostics, but S2 must not change the accepted decision lattice without new evidence. | No S2 code change. Keep current tests asserting infra/header single signal is only `SUSPECTED`, not `CONFIRMED`. |
| R3-E-S2-CR-F05 | DS-05 | rejected-with-reason | Reviewer evidence concludes the GET probe path is correct: it uses `stream=True`, reads only headers, and response lease close releases the response. The docstring already states this owner behavior. | No code change. |
| R3-E-S2-CR-F06 | DS-06 | deferred-with-owner | Diagnostic budget fields are present in the complete S2 typed config but are intentionally not consumed until S3. Test fixture defaults for those fields become material only when S3 implements diagnostic projection. | Owner: R3-E S3 diagnostic projection/storage/smoke slice. Revisit `_resource_budget` and `_resource_budget_json` fixture ownership there. |

## Required fix scope

AgentCodex must fix only `R3-E-S2-CR-F01` through `R3-E-S2-CR-F03`.

Allowed files:

- `dayu/tools/web/web_playwright_backend.py`
- `tests/tools/web/test_web_tools_provider.py`
- `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s2-code-review-fix-codex.md`

The fix must not implement S3 diagnostic schema/storage/smoke, S4 Documents bounded source, tool-security policy, Host/Engine/Fins changes, or aggregate gate work.

## Required validation

- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k 'identity or playwright or body or decompress or resource_budget'`
- `source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q`
- `source .venv/bin/activate && pyright`
- `source .venv/bin/activate && git diff --check`

## Decision

Proceed to S2 code-review fix gate.
