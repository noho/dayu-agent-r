# WU-TOOLS-01-F08 Plan Review Controller Adjudication

## Metadata

- Work unit: `WU-TOOLS-01-F08`
- Gate: plan review adjudication
- Date: 2026-06-11
- Controller: AgentController
- Reviewed artifacts:
  - `docs/reviews/wu-tools-01-f08-plan-review-mimo.md`
  - `docs/reviews/wu-tools-01-f08-plan-review-ds.md`
  - `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`

## Verdict

Plan requires a narrow fix gate.

Both reviewers agree the goal, naming decision, affected files, no-compatibility rule, and single-slice structure are sound. The plan should be tightened before implementation so the implementation agent cannot treat the Fins registry behavior test as optional.

## Finding Adjudication

| ID | Source | Controller decision | Required action |
|---|---|---|---|
| F08-PR-MIMO-01 | MiMo 01: Fins test file marked optional despite required behavior proof | accepted | Update the plan so `tests/fins/test_processor_registry.py` is mandatory unless direct code evidence before implementation proves an existing focused file is a better home. The plan must require a focused Fins registry behavior test, not allow implementation to skip it. |
| F08-PR-MIMO-02 | MiMo 02: Fins test full ordering assertion may be brittle | accepted | Update the plan to prefer a `name -> (class, priority)` mapping / priority-bucket assertion for Fins registry, and avoid hard-coding full list order except where order itself is the behavior under test. |
| F08-PR-DS-01 | DS F1: docs/host historical plan artifact old-name boundary not explicit | accepted | Clarify that `docs/host/issues-implementation-control.md` is the only `docs/host` control target for old-name cleanup; historical plan artifacts may keep old references as immutable process history unless they are current stable control state. |
| F08-PR-DS-02 | DS F2: focused tests vs existing pipeline tests relationship unclear | accepted | Add a short explanation that focused registry tests are contract tests and existing pipeline tests are integration coverage; they are complementary and focused tests do not replace pipeline tests. |
| F08-PR-DS-03 | DS F3: full `tests/fins` may be noisy | deferred-with-owner | Implementation closeout must distinguish rename regressions from pre-existing heavy fixture/environment failures if full `tests/fins` is run. No plan blocker; focused tests remain the primary proof for this WU. |

## Fix Scope

AgentCodex plan-fix gate may edit only:

- `docs/host/wu-tools-01-f08-documents-processor-registry-naming-plan.md`
- `docs/reviews/wu-tools-01-f08-plan-fix-codex.md`

No production code, tests, README, staging, commit, push, or implementation.

## Re-Review Requirement

After fix, MiMo and DS should perform focused plan re-review against this adjudication.
