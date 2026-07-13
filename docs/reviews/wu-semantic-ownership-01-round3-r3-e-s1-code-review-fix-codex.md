# WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E Slice S1 Code Review Fix — AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 Round3 R3-E`
- Slice: S1 Web egress and response ownership
- Review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-mimo.md`
  - `docs/reviews/wu-semantic-ownership-01-round3-r3-e-s1-code-review-ds.md`

This fix only addresses S1 code-review findings. It does not enter S2/S3/S4 and does not implement unrelated tool-security work.

## Accepted Findings

### `R3-E-S1-CR-F01` — `_build_requests_profile` request-exception path did not close its local Session

- Source: AgentDS F-01.
- Severity: low.
- Decision: accepted.
- Correct owner: `utils/diagnose_web_access.py` diagnostic raw requests profile lifecycle.
- Root cause: the `(requests.RequestException, RuntimeError)` handler returned `profile` before calling `session.close()`, leaving the local `requests.Session` cleanup statement unreachable.

AgentMiMo reported a related low finding about the `session.close()` placement being hard to read. The DS finding proves a concrete unreachable cleanup bug, so this fix closes both observations.

## Changes

- Moved `session.close()` before `return profile` in the request-exception branch of `_build_requests_profile`.
- Added `_SessionCloseSpy` and `_raise_diagnostic_request_exception` test helpers in `tests/tools/web/test_diagnose_web_access.py`.
- Added `test_requests_profile_closes_session_on_request_exception` to prove the local diagnostic Session is closed exactly once on request exceptions.

## Validation

```text
source .venv/bin/activate && pytest tests/tools/web/test_diagnose_web_access.py -q -k 'url or egress or redirect or request_exception'
6 passed, 17 deselected

source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py -q -k 'url or egress or redirect or response or peer or playwright'
38 passed, 1 skipped, 27 deselected

source .venv/bin/activate && pytest tests/tools/web/test_web_tools_provider.py tests/tools/web/test_diagnose_web_access.py -q
88 passed, 1 skipped

source .venv/bin/activate && pyright
0 errors, 0 warnings, 0 informations

git diff --check
exit 0, no output
```

## README Decision

No README update. The fix is a diagnostic cleanup-path correction and one focused test; it does not change provider config, user-facing CLI workflow, or the planned S1-S4 aggregate README trigger.

## Stop Status

`R3-E-S1-CR-F01` is fixed locally. Proceed to S1 code-review re-review by AgentMiMo and AgentDS.
