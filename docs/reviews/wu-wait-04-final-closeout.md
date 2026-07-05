# WU-WAIT-04 Final Closeout

## Scope

- Work unit: WU-WAIT-04 UI / Service production-grade awaiting E2E smoke
- Draft PR: https://github.com/noho/dayu-agent-r/pull/171
- Branch: `phaseflow/host-issues-control`
- Accepted plan commit: `35d947ea`
- Accepted S1 commit: `503b2cf5`
- Accepted S2 commit: `d3bdb2c3`

## What Changed

- Added Service / Fins assembly support for production wait poll adapter registry wiring from enabled awaiting provider configs.
- Added a public-contract-only Service entrypoint awaiting smoke:
  - submits through `submit_entrypoint_turn_and_wait`;
  - observes `WAITING` via Service activity and public `host.get_run(...)`;
  - releases wait recovery through production wait poller policy and public wait poll adapter registry;
  - receives the same Run terminal through the Service live terminal path;
  - verifies public outbox terminal backfill with `host.read_outbox_terminal_items(...)`.
- Updated `tests/README.md` to document the new Service entrypoint awaiting smoke coverage.
- Recorded plan, implementation, controller validation, code review, and controller adjudication artifacts under `docs/reviews/`.

## Public Contract Boundary

- The S2 smoke does not import `dayu.engine.agent`, `_AsyncAgent`, durable wait storage, dispatch rows, scheduler internals, ToolRuntime internals, manual wait resolution APIs, or test-private wait id bridges.
- `EngineEvent` is used only as the public `LocalWorkerHandle.events() -> AsyncIterator[EngineEvent]` protocol payload required by the public Host local worker contract.
- Behavioral assertions stay at Host / Service public API level.

## What Was Verified

- `source .venv/bin/activate && pytest tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
  - Result: `1 passed, 3 warnings`.
- `source .venv/bin/activate && pytest tests/service/test_host_assembly.py tests/service/test_entrypoint_runtime_awaiting_smoke.py -q`
  - Result: `55 passed, 3 warnings`.
- `source .venv/bin/activate && pyright`
  - Result: `0 errors, 0 warnings, 0 informations`.
- Forbidden-path grep for durable wait rows, dispatch rows, scheduler internals, ToolRuntime internals, manual resolve, `dayu.engine.agent`, and `_AsyncAgent`
  - Result: no matches.
- Weak typing grep for `Any`, `object`, `type: ignore`, pyright suppressions, `hasattr`, and `getattr`
  - Result: only JSON tool schema `"type": "object"` matched, which is allowed by AGENTS.
- `git diff --check`
  - Result: passed with no output.
- `gh pr checks 171 --repo noho/dayu-agent-r`
  - Result: no checks reported on branch `phaseflow/host-issues-control`.

Warnings are existing third-party `edgar` deprecation warnings.

## Review And Finding Status

- Plan review:
  - Initial review artifacts: `docs/reviews/plan-review-20260705-201401.md`, `docs/reviews/plan-review-20260705-201420.md`.
  - Controller adjudication: `docs/reviews/wu-wait-04-plan-review-controller-adjudication.md`.
  - Fix artifact: `docs/reviews/wu-wait-04-plan-fix-codex.md`.
  - Re-review artifacts: `docs/reviews/plan-review-20260705-202521.md`, `docs/reviews/plan-review-20260705-202539.md`.
  - Re-review adjudication: `docs/reviews/wu-wait-04-plan-rereview-controller-adjudication.md`.
- S1 implementation:
  - Implementation report: `docs/reviews/wu-wait-04-s1-implementation-codex.md`.
  - Controller validation: `docs/reviews/wu-wait-04-s1-controller-validation.md`.
  - Code review artifacts: `docs/reviews/code-review-20260705-203716.md`, `docs/reviews/code-review-20260705-203801.md`.
  - Controller adjudication: `docs/reviews/wu-wait-04-s1-code-review-controller-adjudication.md`.
  - No accepted findings.
- S2 implementation:
  - Implementation report: `docs/reviews/wu-wait-04-s2-implementation-codex.md`.
  - Controller validation: `docs/reviews/wu-wait-04-s2-controller-validation.md`.
  - Code review artifacts: `docs/reviews/code-review-20260705-210415.md`, `docs/reviews/code-review-20260705-210446.md`.
  - Controller adjudication: `docs/reviews/wu-wait-04-s2-code-review-controller-adjudication.md`.
  - No accepted findings.

## Residual Risk Reconciliation

- Callback endpoint E2E is not covered by this smoke. The accepted plan deliberately chose the poller path because ordinary UI / Service flow has no public wait id discovery contract for callback completion.
- Real Fins external systems are not exercised by S2. S1 and existing Service assembly tests cover production Fins wait poll adapter assembly; S2 covers the public entrypoint and production wait recovery workflow with deterministic tool and poll adapter fixtures.
- No active WU-WAIT-04 residual risk remains that requires current-code changes.

## PR And Closeout Status

- Draft PR #171 is open at https://github.com/noho/dayu-agent-r/pull/171.
- PR body intentionally has no `Closes` footer because WU-WAIT-04 is a dependent smoke work unit, not an independent GitHub issue owner.
- Do not mark ready, merge, close issues, request reviewers, or delete the branch without explicit authorization.

## Next Entry Point

WU-WAIT-04 is at `final-closeout-pass`. After the user / maintainer handles PR #171, pull the latest `main` and select the next backlog work unit from `docs/host/issues-implementation-control.md`.
