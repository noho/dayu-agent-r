# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Controller Validation

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E`
- Slice: S1 Web egress and response ownership
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md`
- Plan: `docs/host/wu-semantic-ownership-01-round3-r3-e-web-doc-egress-resource-plan.md`

This validation covers the S1 implementation only. It does not validate or close S2 Web resource/challenge/search, S3 diagnostics/storage-state/smoke oracle, or S4 Documents bounded source.

## Controller Corrections

AgentCodex reported pyright passing, but controller re-run found `normalized_url` possibly unbound in `dayu/tools/web/web_tools.py` after the invalid-URL error projection. Root cause: `_raise_fetch_failure()` is not typed as `NoReturn`, so pyright could not prove the branch exits.

Controller fix:

- Added an explicit unreachable `AssertionError` after the `_raise_fetch_failure()` call in the invalid URL branch.
- Replaced two newly introduced inline resolver lambdas in `tests/tools/web/test_diagnose_web_access.py` with `_resolve_example_public_address()` to keep the new test owner typed and named.

These fixes are local to S1 and do not change the accepted ownership design.

## Validation Commands

```text
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k 'url or egress or redirect or response or peer or playwright'
38 passed, 1 skipped, 27 deselected

source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q -k 'url or egress or redirect'
5 passed, 17 deselected

source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py -q
87 passed, 1 skipped

source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations

git diff --check
exit 0, no output

git diff --no-index --check /dev/null dayu/tools/web/web_egress_policy.py
no whitespace diagnostics

git diff --no-index --check /dev/null docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md
no whitespace diagnostics
```

## Propagation Audit

```text
rg -n "_is_safe_public_url|_validate_url_safety|_is_private_or_local_host|socket\.getaddrinfo|allow_redirects=True|session\.(get|post|head|request|send)\(|requests\.(get|post|head|request)\(" dayu/tools/web utils/diagnose_web_access.py
```

Observed hits:

- `dayu/tools/web/web_egress_policy.py`: owner-owned DNS resolution.
- `dayu/tools/web/web_http_session.py`: target-bound `_send_authorized_request`.
- `dayu/tools/web/web_search_providers.py`: three fixed provider endpoint calls, left to S2 search resource/parser owner.

```text
rg -n "response\.close\(|_close_response_safely|AuthorizedResponseLease|_request_with_safe_redirects" dayu/tools/web utils/diagnose_web_access.py
```

Observed hits are the new lease owner, its callers, and explicit close calls inside `AuthorizedResponseLease` / `_send_authorized_request` cleanup.

```text
rg -n "page\.goto\(|route\.continue_|browser_egress_policy_unavailable|allows_private_network" dayu/tools/web/web_playwright_backend.py utils/diagnose_web_access.py
```

Observed hits keep `page.goto` / `route.continue_` behind `allows_private_network` gates; public direct browser path returns `browser_egress_policy_unavailable`.

## README Decision

No README update in S1. The accepted R3-E plan defers `tests/README.md` and `dayu/config/README.md` decisions until the relevant S2-S4 behavior exists and the aggregate state is accepted.

## Tool-Security Boundary

S1 implements current-scope Web egress and response lifetime ownership. It does not add a repository-wide tool-security framework, Fins upload/download policy, LLM-facing upload/download security schema, browser proxy/sandbox framework, or Host/Engine lifecycle changes.

## Stop Status

Controller validation passes after the local pyright/control-flow correction. Proceed to S1 implementation code review by AgentMiMo and AgentDS.
