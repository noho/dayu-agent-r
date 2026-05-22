# Phase 12.2 Service Assembly Re-review Controller Adjudication

## Scope

- Work unit: Phase 12.2 service assembly helper follow-up.
- Design source: `docs/host/design.md`.
- Control source: `docs/host/implementation-control.md`.
- Plan artifact: `docs/reviews/phase12-2-service-assembly-plan-codex-20260522.md`.
- Implementation artifact: `docs/reviews/phase12-2-service-assembly-implementation-codex-20260522.md`.
- Initial review artifacts:
  - `docs/reviews/phase12-2-service-assembly-code-review-mimo-20260522.md`
  - `docs/reviews/phase12-2-service-assembly-code-review-ds-20260522.md`
- Re-review artifacts:
  - `docs/reviews/phase12-2-service-assembly-rereview-mimo-20260522.md`
  - `docs/reviews/phase12-2-service-assembly-rereview-ds-20260522.md`

Excluded pre-existing artifacts, per user instruction:

- `docs/reviews/repo-review-20260522-070034.md`
- `docs/reviews/repo-review-20260522-070045.md`

## Review Summary

AgentMiMo initial review concluded `PASS`, blocking finding count = 0.

AgentDS initial review concluded `PASS_WITH_FINDINGS`, blocking finding count = 0, with two low findings:

- DS Finding 1: `_agent_fallback_mode_from_config` manually mapped `force_answer` / `raise_error` instead of using `AgentFallbackMode(value)`.
- DS Finding 2: root `README.md` contains pre-existing dead links.

Controller adjudication:

- Accepted DS Finding 1 as a current-scope narrow fix because it is in the new `dayu.service.host_assembly` helper and reducing duplicated enum mapping improves maintainability without changing public contracts.
- Deferred DS Finding 2 as out of scope because the dead links existed before this Phase 12.2 work unit and are unrelated to Service assembly correctness. The root README was not changed for that finding.

## Fix Summary

AgentCodex fixed DS Finding 1:

- `dayu/service/host_assembly.py`: `_agent_fallback_mode_from_config` now returns `AgentFallbackMode(value)`.
- `tests/service/test_host_assembly.py`: added focused coverage for `force_answer`, `raise_error`, and invalid fallback value rejection.
- `docs/reviews/phase12-2-service-assembly-implementation-codex-20260522.md`: appended the fix addendum.

## Re-review Summary

AgentMiMo re-review concluded `PASS`, blocking finding count = 0.

AgentDS re-review concluded `PASS`, blocking finding count = 0.

Both re-reviews confirmed DS Finding 1 is fixed and no new blocker was introduced.

## Controller Validation

Controller re-ran the target validation after the fix:

- `pytest tests/runtime -q`: 208 passed.
- `pytest tests/engine/test_config_models.py tests/engine/test_provider_extension_config_adapter.py -q`: 11 passed.
- `pytest tests/service -q`: 3 passed.
- `pytest tests/host/test_public_open_host_multiturn_smoke.py tests/host/test_public_tool_wiring_smoke.py tests/host/test_public_compact_smoke.py -q`: 8 passed.
- `python utils/smoke_host_public_multiturn.py --help`: exit 0.
- `python -m pyright dayu/contracts dayu/runtime dayu/engine dayu/host dayu/service tests/runtime tests/engine tests/host tests/service utils/smoke_host_public_multiturn.py`: 0 errors.
- `git diff --check`: clean.

## Decision

Phase 12.2 service assembly helper follow-up is accepted.

The current work unit reaches local PASS: implementation, initial review, accepted fix, re-review, controller adjudication, and validation are complete. Remaining non-blocking item is the pre-existing root README dead-link cleanup, deferred outside this work unit.
