# WU-WAIT-01 Slice 2 Code Review Controller Adjudication

## Scope

- Work unit: WU-WAIT-01 / issue-89
- Gate: Slice 2 code review
- Implementation artifact: `docs/reviews/wu-wait-01-slice2-implementation-codex.md`
- Code review artifacts:
  - `docs/reviews/code-review-20260621-231602.md` (AgentDS)
  - `docs/reviews/code-review-20260621-231811.md` (AgentMiMo)
- Base: accepted Slice 1 commit `6f919bb7`

## Findings Judgment

### S2-CR-F01: missing request id is encoded as the literal `"missing"`

- Source: AgentDS F01.
- Judgment: accepted.
- Controller severity: medium.
- Direct evidence:
  - `dayu/service/wait_callback_endpoint.py` returns the literal `"missing"` when both `X-Dayu-Callback-Request-Id` and body `request_id` are absent.
  - `WaitCallbackCompletionEnvelope.request_id` is a non-optional string and is used as a trace/correlation field.
- Rationale:
  - Missing request id is not an auth classification problem and should not be passed to the Host adapter as an indistinguishable sentinel.
  - A caller that explicitly sends `request_id="missing"` would be indistinguishable from the missing-field case.
  - Service transport mapper owns the route/header/body contract and should fail closed before constructing the Host envelope.
- Required fix:
  - If both header and body request id are missing, return a Service-layer 400 response without calling the adapter.
  - Use a deterministic diagnostic code such as `missing_request_id`.
  - Preserve header-over-body priority when request id is present.
  - Add tests for missing request id and body fallback request id.

### S2-CR-F02: fail-closed mapper branches need direct tests

- Sources:
  - AgentDS F02.
  - AgentMiMo findings 1-4.
- Judgment: accepted.
- Controller severity: medium for non-POST and non-object body; low for unknown outcome kind and invalid timestamp.
- Direct evidence:
  - Non-POST method, non-object body, unknown outcome kind, invalid timestamp, and unsupported cancelled reason currently rely on generic code paths without direct tests.
- Rationale:
  - These are not current production behavior bugs, but they are branch-level fail-closed behavior in the new Service boundary.
  - The mapper is a protocol boundary; regression tests should cover its rejection branches, not only happy path and a single malformed shape.
- Required fix:
  - Add tests proving non-POST returns `transport_rejected` without adapter invocation.
  - Add tests proving non-object body returns `malformed_payload` without adapter invocation.
  - Add tests proving unknown outcome kind returns `malformed_payload` without adapter invocation.
  - Add tests proving invalid timestamp returns `malformed_payload` without adapter invocation.
  - Add tests proving unsupported cancelled reason returns `malformed_payload` without adapter invocation.
  - Add tests proving `run=None` response omits `run_id` and `run_status`.

## Rejected / Deferred Findings

- Header casing, duplicate headers, empty content-type, authorization claim malformed shape, payload ref malformed shape, and provider status ref malformed shape are accepted as residual low-priority test gaps, not current fix blockers. Existing helper paths are covered indirectly by generic validation and may be expanded in later Web route hardening if needed.
- Non-Bearer Authorization handling is not accepted as a current finding. The mapper intentionally passes credential material to the injected adapter/authenticator for classification and does not echo it in the response.

## Required Next Gate

Dispatch AgentCodex for fix gate.

Allowed scope:

- `dayu/service/wait_callback_endpoint.py`
- `tests/service/test_wait_callback_endpoint.py`
- `docs/reviews/wu-wait-01-slice2-fix-codex.md`
- README only if behavior/documentation changes require it, which is not expected for this narrow fix.

Non-goals:

- Do not add a real HTTP route.
- Do not change Host callback contract or Slice 1 code unless the Service fix proves impossible.
- Do not introduce Web framework dependencies.
- Do not modify durable state, Host durable modules, issue-90 poller logic, or issue-92 physical cancel logic.

Required validation:

- `pytest tests/service/test_wait_callback_endpoint.py tests/service/test_import_boundary.py tests/service/test_weak_typing_guard.py -q`
- `pytest tests/host/test_wait_callback.py tests/host/test_resolve_wait_command.py tests/host/test_wait_cancel_late_result.py tests/host/test_package_exports.py tests/host/test_import_boundary.py -q`
- `pyright`
- `git diff --check`
