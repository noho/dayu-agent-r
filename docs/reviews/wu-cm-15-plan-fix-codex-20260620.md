# WU-CM-15 Plan Fix Artifact

## Gate

- Gate: plan fix.
- Agent: AgentCodex.
- Date: 2026-06-20.

## Work Unit And Scope

- Work unit: WU-CM-15 Conversation memory public smoke reactive compact and fallback coverage.
- Scope executed: update the accepted plan artifact only to address accepted plan review findings.
- Scope boundaries preserved:
  - no implementation;
  - no code, test, README, or control-doc edits;
  - no commit, push, PR, merge, or re-review;
  - no Host / Engine public API, durable schema, EventLog canonical semantic, provider contract, production state-machine, or production-only hook change.

## Plan Artifact Updated

- `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`

## Review And Adjudication Sources Used

- `docs/reviews/plan-review-20260620-102108.md`
- `docs/reviews/plan-review-20260620-102145.md`
- `docs/reviews/wu-cm-15-plan-review-adjudication-20260620.md`
- Consistency sources read:
  - `docs/host/design.md`
  - `docs/engine/design.md`

## Accepted Findings Addressed

- Fallback pressure mechanism: the plan now requires the fallback suite to use existing smoke pressure helpers or an explicit long prompt pattern, assert effective pressure between the active soft and hard thresholds, and require `requested_proactive >= 1` so fallback coverage cannot pass without an actual proactive compact request.
- Deterministic worker injection path: the plan now specifies calling `compose_open_host_options(...)` normally, then using `dataclasses.replace(...)` on the assembled `OpenHostOptions` to replace only `worker_factory` with a smoke-local `LocalEngineWorkerFactory`, without modifying Host or Service assembly APIs.
- `fallback_input_window` audit support: the plan now pre-authorizes extending `CompactFailedOperationAudit` or an equivalent smoke-local audit object with bounded `selected_block_ids`, `dropped_block_ids`, and `current_input_ref` fields.
- Synthetic helper test data shape: the plan now specifies reactive helper tests using `CompactAuditSummary` with requested/compacted reactive counts and zero failed reactive count, and fallback helper tests using a failed-operation audit with `fallback_action="dispatch"`, bounded fallback window fields, no accepted compact for the same operation, and a failure case for missing `requested_proactive`.
- Compactor stub location: the plan now records the controller decision to keep minimal deterministic compactor stubs smoke-local in `utils/smoke_host_public_conversation_memory_scenarios.py`, not import tests from runtime `utils/`, and not add production seams.
- Request capture mechanism: the plan now requires deterministic workers to record every `AgentRunRequest` and `AttemptDispatchSnapshot` inside `LocalEngineWorker.accept(snapshot, request)` before returning a handle.
- S2/S3 shared infrastructure: the plan now states S2 builds reusable deterministic worker, request/snapshot capture, and compactor stub context manager infrastructure that S3 must reuse rather than duplicating worker implementations.

## Validation Commands And Results

Commands run after the plan fix:

```bash
git diff --check
```

Result: passed with no output.

```bash
git diff --no-index --check -- /dev/null docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md
```

Result: no whitespace diagnostics. Exit code was `1`, which is expected for a no-index comparison between `/dev/null` and an existing untracked file because the files differ; there were no whitespace error lines.

Required validation after writing this durable artifact:

```bash
git diff --check
```

Result: to be run immediately after artifact creation.

Controller follow-up result: passed with no output.

## Files Changed

- `docs/host/host-issues/wu-cm-15-public-smoke-reactive-fallback-plan.md`
- `docs/reviews/wu-cm-15-plan-fix-codex-20260620.md`

## Remaining Open Questions

- None.

## Residual Risks

- The implementation plan still carries the known risk of smoke-local patching at the private compactor runner boundary. The plan keeps this bounded to deterministic smoke suites and retains the stop condition to avoid adding a production seam.
- The fallback suite remains sensitive to effective context policy thresholds. The plan now requires explicit soft/hard threshold assertions and `requested_proactive >= 1` so this risk becomes visible during implementation validation.
