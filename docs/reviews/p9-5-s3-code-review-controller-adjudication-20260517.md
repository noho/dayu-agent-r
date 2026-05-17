# P9.5 S3 Code Review Controller Adjudication

## Gate

- Work unit: P9.5 Pre-P10 Cross-Repository Hardening PR.
- Slice: S3 Host Public Error Taxonomy And Command Handle Encapsulation.
- Implementation artifact: `docs/reviews/p9-5-s3-host-public-error-command-handle-implementation-20260517.md`.
- Review artifact: `docs/reviews/p9-5-s3-code-review-mimo-20260517.md`.
- DS review status: unavailable. DS was assigned the same S3 read-only review twice, then a narrowed immediate-artifact prompt, but remained in long thinking and did not produce `docs/reviews/p9-5-s3-code-review-ds-20260517.md`. Controller stops waiting to avoid blocking the phase indefinitely.

## Controller Decision

S3 is accepted.

The motivation is valid: public Host command/read facades are the Service/UI-facing boundary, so durable/internal failures must be translated into the public `HostApiError` taxonomy there, and a closed `HostCommandHandle` must fail before any durable/admission side effect. This directly supports `docs/host/design.md` by keeping Host lifecycle and governance as the strong constraint boundary.

## Findings Adjudication

### MiMo F1 — `_run_read` / `_run_write` double durable error conversion

- Severity: Info.
- Decision: Accepted as non-blocking observation; no code change required.
- Rationale: `_transaction_runner()` converts durable errors raised while obtaining the runner, while `_run_read()` / `_run_write()` convert durable errors raised by the transaction body execution. Since `HostApiError` is not a `HostDurableError`, the outer handlers do not double-convert already public errors. The split is readable enough for this slice and preserves the public boundary.

### MiMo F2 — `resolve_wait` closed guard is implicit through `_transaction_runner()`

- Severity: Info.
- Decision: Accepted as non-blocking observation; no code change required.
- Rationale: `resolve_wait` obtains `transaction_runner` through `host._transaction_runner()`, whose first step is `_raise_if_closed()`. The guard therefore executes before durable/admission access. Adding another explicit guard would be stylistic only and is not required to satisfy S3.

### MiMo F3 — generic fallback for several durable subtypes

- Severity: Info.
- Decision: Accepted as residual risk; no code change required.
- Rationale: S3 is not adding public error codes. Mapping unknown or non-public durable subtypes to `INTERNAL_ERROR(retryable=False)` is the conservative public-boundary behavior. Future durable subtypes that require caller-visible handling must be added to the same private mapping helper.

## Validation

Controller reran:

- `source .venv/bin/activate && pytest tests/host/test_command_handle.py tests/host/test_package_exports.py tests/host/test_public_contracts.py tests/host/test_public_session_api.py tests/host/test_public_run_api.py`
  - Result: 69 passed.
- `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - Result: 0 errors, 0 warnings, 0 informations.
- `git diff --check`
  - Result: clean.

## Accepted State

- Blocking findings: 0.
- Required fixes: 0.
- README decision: `dayu/host/README.md` was checked by implementation agent; current public-facade closed-handle behavior and package-root internal boundary descriptions remain accurate, so no README update is required.
- S3 may proceed to accepted slice commit.
