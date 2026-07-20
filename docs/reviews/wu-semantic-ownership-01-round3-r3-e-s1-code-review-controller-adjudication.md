# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Code Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E`
- Slice: S1 Web egress and response ownership
- Implementation artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-implementation-codex.md`
- Controller validation: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-controller-validation.md`
- Code review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-ds.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-fix-codex.md`
- Re-review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-rereview-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-rereview-ds.md`

## Review Results

AgentMiMo verdict: pass.

- Findings: 1 low/cosmetic observation about diagnostic `session.close()` placement.
- Blocking findings: 0.

AgentDS verdict: pass-with-findings.

- Findings: 1 low material resource-lifecycle bug.
- `F-01`: `_build_requests_profile` request-exception path returned before closing its local `requests.Session`.
- Blocking findings: 0.

Controller decision: accept `R3-E-S1-CR-F01` for fix. The DS finding proves a concrete unreachable cleanup path, and it subsumes MiMo's related low observation.

## Fix And Re-Review

`R3-E-S1-CR-F01` fix:

- Moved `session.close()` before `return profile` in the `(requests.RequestException, RuntimeError)` handler.
- Removed unreachable duplicate cleanup/return.
- Added `test_requests_profile_closes_session_on_request_exception` with `_SessionCloseSpy` to verify the diagnostic local Session closes exactly once on request exceptions.

Re-review:

- AgentMiMo verdict: pass; `R3-E-S1-CR-F01` closed; new findings 0; blocking questions 0.
- AgentDS verdict: pass; `R3-E-S1-CR-F01` closed; new findings 0; blocking questions 0.

## Controller Validation

Final controller validation after the fix:

```text
source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k 'url or egress or redirect or response or peer or playwright'
38 passed, 1 skipped, 27 deselected

source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q -k 'url or egress or redirect or request_exception'
6 passed, 17 deselected

source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py -q
88 passed, 1 skipped

source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations

git diff --check
exit 0, no output
```

## Scope Boundary

S1 remains limited to:

- Web egress policy and target authorization.
- Target-bound requests/urllib3 transport and response lease ownership.
- Redirect re-authorization and response close paths.
- Playwright public-direct typed unavailable gate.
- Diagnostic raw requests egress/lease wiring.

S1 does not close:

- S2 Web resource budget, codec/DOM cap, challenge/fallback, or DuckDuckGo parser shape-drift.
- S3 diagnostic schema v2, storage-state lifecycle, or smoke oracle.
- S4 Documents bounded source/read/list/search.
- Fins upload/download policy, broad tool-security framework, or LLM-facing upload/download security schema.

## README Decision

No README update in S1. The accepted R3-E plan defers `dayu/config/README.md` and `tests/README.md` updates until the relevant S2-S4 behavior exists and aggregate validation can describe the accepted test/config surface.

## Decision

S1 is accepted locally. Proceed to accepted S1 commit, then R3-E Slice S2 implementation.

## Stop Status

All S1 code-review findings are fixed and re-reviewed. No known S1 material defect remains.
