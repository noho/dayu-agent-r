# WU-CM-15 Plan Review Adjudication

## Scope

- Work unit: WU-CM-15 Conversation memory public smoke reactive compact and fallback coverage.
- Gate: plan review adjudication.
- Plan artifact: `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`.
- Review artifacts:
  - `docs/reviews/plan-review-20260620-102108.md` (AgentMiMo).
  - `docs/reviews/plan-review-20260620-102145.md` (AgentDS).

## Controller Decision

Both reviews conclude `pass-with-risks`. There is no blocker and no finding challenges the work unit direction: WU-CM-15 remains a smoke coverage hardening task and must not modify Host / Engine public API, durable schema, EventLog canonical semantics, provider contract, or production state machine.

The findings are accepted as plan-readiness fixes because they identify places where the implementation Agent would otherwise have to make design choices during implementation. The next gate is plan fix by AgentCodex.

## Finding Adjudication

| Review finding | Decision | Required plan fix |
|---|---|---|
| MiMo 001 / DS F-04: fallback pressure mechanism underspecified | accepted | Specify the fallback suite pressure mechanism: use existing smoke pressure helpers or an explicit long prompt pattern, assert the effective pressure sits between soft and hard thresholds, and require `requested_proactive >= 1` for fallback dispatch coverage. |
| MiMo 002 / DS F-01: deterministic worker injection path underspecified | accepted | Specify that deterministic suites replace assembled `OpenHostOptions.worker_factory` with a smoke-local `LocalEngineWorkerFactory` by using `dataclasses.replace(...)` after `compose_open_host_options(...)`; do not modify Host / Service assembly APIs. |
| MiMo 003: `fallback_input_window` assertion needs audit infrastructure | accepted | Pre-authorize extending `CompactFailedOperationAudit` or an equivalent smoke-local audit object to carry bounded `fallback_input_window` fields: `selected_block_ids`, `dropped_block_ids`, and `current_input_ref`. |
| MiMo 004: synthetic helper test data shape unspecified | accepted | Specify minimal synthetic data for helper tests: reactive tests use `CompactAuditSummary`; fallback tests use a `CompactAuditReport` / failed-operation audit with `fallback_action="dispatch"`, a non-empty fallback window, and no accepted compact for the same operation. |
| DS F-02: compactor stub location unspecified | accepted | Specify the location choice. Controller preference: keep minimal deterministic compactor stubs smoke-local in `utils/smoke_host_public_conversation_memory_scenarios.py`; do not make runtime `utils/` depend on `tests/`, and do not add production seams. |
| DS F-03: request capture mechanism unspecified | accepted | Specify that the deterministic worker records every `AgentRunRequest` and `AttemptDispatchSnapshot` inside `LocalEngineWorker.accept(snapshot, request)` before returning the handle. |
| DS F-05: S2 and S3 shared worker infrastructure not called out | accepted | Specify that S2 creates shared deterministic worker/request-capture/compactor-stub infrastructure reused by S3, avoiding duplicate worker implementations. |

## Deferred / Rejected

None. The listed residual risks remain non-blocking only if the plan fix records their stop conditions clearly.

## Next Gate

- Gate: fix.
- Agent: AgentCodex.
- Allowed write: `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`.
- Expected result: updated plan artifact addressing all accepted findings, followed by plan re-review.
