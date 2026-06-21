# WU-WAIT-01 Slice 2 Code Re-review Controller Adjudication

## Scope

- Work unit: WU-WAIT-01 / issue-89
- Gate: Slice 2 code re-review
- Fix artifact: `docs/reviews/wu-wait-01-slice2-fix-codex.md`
- Prior adjudication: `docs/reviews/wu-wait-01-slice2-code-review-controller-adjudication.md`
- Re-review artifacts:
  - `docs/reviews/code-review-20260621-232753.md` (AgentMiMo)
  - `docs/reviews/code-review-20260621-232916.md` (AgentDS)
- Base: accepted Slice 1 commit `6f919bb7`

## Controller Judgment

Both re-review lanes passed. S2-CR-F01 and S2-CR-F02 are closed. No material correctness, architecture, stability, or maintainability finding remains for Slice 2.

## Accepted Finding Closure

### S2-CR-F01

- Status: closed.
- Evidence:
  - Service mapper checks request id before Host envelope construction.
  - If both header and body request id are missing, the mapper returns 400 with `diagnostic_code="missing_request_id"` and does not call the adapter.
  - `_request_id_from_transport(...)` no longer returns the literal `"missing"`.
  - Tests cover missing request id rejection, body fallback request id, and header priority.

### S2-CR-F02

- Status: closed.
- Evidence:
  - Tests cover non-POST method rejection without adapter invocation.
  - Tests cover non-object body malformed payload without adapter invocation.
  - Tests cover unknown outcome kind malformed payload without adapter invocation.
  - Tests cover invalid timestamp malformed payload without adapter invocation.
  - Tests cover unsupported cancelled reason malformed payload without adapter invocation.
  - Tests cover `run=None` response omitting `run_id` and `run_status`.

## Residual Risk

- Non-object body with missing request id header returns generic `malformed_payload` rather than `missing_request_id`. Controller classifies this as non-blocking because the body itself is malformed, the request fails closed with 400, and the adapter is not called.
- Header casing, duplicate headers, empty content type, authorization claim malformed sub-shapes, payload ref malformed sub-shapes, and provider status ref malformed sub-shapes remain low-priority residual test gaps for future Web route hardening. Current helper validation fail-closes these inputs and import boundary tests guard the main layering risk.
- Slice 2 intentionally does not implement a real HTTP route, secret backend, HMAC/bearer verifier, production poller, or physical cancel path.

## Required Next Gate

Slice 2 may enter accepted slice commit gate.

Required validation before commit:

- `pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q`
- `pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
- `pyright`
- `git diff --check`
