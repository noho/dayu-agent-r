# Controller Adjudication: Host P3-S6 Multiprocess Tests And Documentation Sync

- **gate**: code review adjudication
- **work unit**: Host Phase 3 Session / Run / Attempt 状态机与 Admission
- **slice**: P3-S6 Multiprocess Tests And Documentation Sync
- **review artifact**: `docs/reviews/gateflow-code-review-host-p3-s6-multiprocess-docs-mimo-20260514.md`
- **adjudication date**: 2026-05-14

## Decision

P3-S6 code review accepted. No blocking finding was accepted by controller.

AgentMiMo reviewed the implementation artifact, new multiprocess tests, Host README update and tests README update. Validation passed:

- `pytest tests/host/test_admission_multiprocess.py -q`: 6 passed
- `pytest tests/host/test_admission_multiprocess.py tests/host -q`: 157 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: passed

Controller independently reran:

- `pytest tests/host/test_admission_multiprocess.py tests/host -q`: 157 passed
- `python -m pyright dayu/host tests/host`: 0 errors
- `git diff --check`: passed

## Findings

### NB-1: `_duplicate_followup_worker` docstring spelling

- **review severity**: non-blocking
- **controller decision**: rejected-as-current-slice-action
- **reason**: This is a documentation style nit in a test helper and does not weaken P3-S6 correctness, phase boundary, validation strength or README accuracy. It does not justify a fix loop for this slice.
- **owner**: none for Phase 3. A future broad test docstring cleanup may address it if such cleanup is otherwise opened.

### NB-2: cancel/promotion race test uses low-level transition seed helper

- **review severity**: non-blocking / residual risk
- **controller decision**: accepted-as-deferred-risk
- **reason**: P3-S6 is scoped to durable multiprocess invariants and is allowed to use internal transition helpers. The test directly verifies first-committer-wins on the queued Run row and confirms the losing path does not leave contradictory EventLog facts. Public Host command facade behavior is explicitly Phase 4 scope and should not be pulled into Phase 3.
- **owner**: Phase 4 Host Public API Command Path owner.
- **tracking action**: Phase 4 must add API-level coverage for queued cancel versus promotion race once public command facade wiring exists.

## Residual Risks

- SQLite multiprocess tests still depend on local SQLite file locking and OS scheduling. Current process count, busy timeout and retry policy are acceptable for correctness coverage without turning this slice into performance hardening.
- P3-S6 verifies the internal durable race directly. Public facade race behavior remains a Phase 4 tracking item and must not be treated as completed by this slice.

## Gate Result

P3-S6 may proceed to accepted slice commit. After that commit, Phase 3 must enter aggregate deepreview. Per controller rule and user correction, ordinary reviews used AgentMiMo only; the upcoming aggregate deepreview must be run by AgentMiMo and AgentDS simultaneously.
