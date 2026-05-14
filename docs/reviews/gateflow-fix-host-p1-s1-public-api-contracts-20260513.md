## Work Gate

fix

## Work Unit

Host Phase 1 公共契约与 runtime 基础设施

## Assigned Slice

Slice 1: `dayu.host` public API typed contracts

## Source Review Artifacts

- `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-controller-adjudication-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-mimo-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md`

## Controller-Accepted Finding IDs

- D3
- D4

## Per-Finding Fix Status

- D3: fixed
  - Added focused tests for `CancelRunRequest` and `CancelSessionRunsRequest` rejecting a non-graceful runtime value supplied via `typing.cast(CancelMode, "force")`.
- D4: fixed
  - Replaced the sampled frozen / slots assertion with a public Host dataclass type list that covers every exported Host dataclass type and asserts `is_dataclass`, frozen dataclass params, and non-empty `__slots__`.

## Finding Title Status Updates

- `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md`
  - Finding 3 title updated to `已修复`.
  - Finding 4 title updated to `已修复`.
- `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-mimo-20260513.md`
  - Not updated: MiMo review did not contain D3 / D4 headings to mark fixed.

## Changed Files

- `tests/host/test_public_contracts.py`
- `docs/reviews/gateflow-implementation-host-p1-s1-public-api-contracts-20260513.md`
- `docs/reviews/gateflow-code-review-host-p1-s1-public-api-contracts-ds-20260513.md`
- `docs/reviews/gateflow-fix-host-p1-s1-public-api-contracts-20260513.md`

## Validation

- command:
  - `source .venv/bin/activate && pytest tests/host -q`
  - result: passed, `16 passed in 0.08s`
- command:
  - `source .venv/bin/activate && python -m pyright dayu/host tests/host`
  - result: passed, `0 errors, 0 warnings, 0 informations`
- command:
  - `git diff --check`
  - result: passed, no whitespace errors

## Plan Deviation

- none. The fix only expands test coverage and updates Gateflow artifacts within the controller-approved file scope.

## New Risks Or Open Questions

- none.

## Residual Risks And Uncovered Areas

- risk: Host command path still does not consume these request / snapshot types.
  - classification: accepted as covered by a later slice in the approved plan
  - owner or destination: Host Phase 后续 command path / durable store slices
- risk: runtime lane / filelock and Host tooling options remain unimplemented.
  - classification: accepted as covered by later slices in the approved plan
  - owner or destination: Phase 1 later slices

## Stop Condition Status

none hit

## Artifact Path

docs/reviews/gateflow-fix-host-p1-s1-public-api-contracts-20260513.md
