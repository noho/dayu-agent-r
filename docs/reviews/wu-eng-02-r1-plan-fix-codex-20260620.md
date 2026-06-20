# WU-ENG-02-R1 Plan Fix: AgentCodex

- Work unit: WU-ENG-02-R1
- Gate: plan-fix
- Agent: AgentCodex
- Date: 2026-06-20
- Plan artifact: `docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md`
- Review inputs:
  - `docs/reviews/plan-review-20260620-210618.md`
  - `docs/reviews/plan-review-20260620-210656.md`

## Summary Of Plan Edits

Updated the plan so implementation no longer has to choose between competing diagnostic designs. The plan now requires the minimal public-contract path: append a bounded diagnostic suffix at Host public projection boundaries for live watcher and outbox fallback, without changing durable terminal payload `message`, payload digest, or public dataclass shapes.

The plan also makes Python runner log visibility mandatory on the existing `runner.http.response` log line, keeps provider request id extraction limited to current `x-request-id`, removes `diagnostic_ref` fallback overdesign, and requires baseline assembly tests before changing the Service default.

## Accepted Finding Mapping

1. Terminal diagnostic visibility must converge to minimal public-contract path.
   - Changed sections:
     - `1. Goal / Motivation / Success Signal`
     - `6. Contract / Schema / State-Machine / Public Interface Changes`
     - `7. Implementation Decisions / Decision 7`
     - `8. Small Implementation Slices / Slice 4`
     - `9. Tests / Validation Commands And Expected Assertions`
     - `11. Risks / Open Questions`
   - Plan now requires suffix formatting at Host public projection boundaries only, with no durable terminal payload or payload digest mutation.

2. Live watcher and outbox fallback are independent projection paths.
   - Changed sections:
     - `6. Contract / Schema / State-Machine / Public Interface Changes`
     - `8. Small Implementation Slices / Slice 4`
     - `9. Tests / Validation Commands And Expected Assertions`
   - Plan now requires a shared private Host projection helper and tests for both paths when `provider_request_id=None` and `client_correlation_id` exists.

3. Python runner log visibility is mandatory.
   - Changed sections:
     - `1. Goal / Motivation / Success Signal`
     - `7. Implementation Decisions / Decision 4`
     - `8. Small Implementation Slices / Slice 2`
     - `9. Tests / Validation Commands And Expected Assertions`
   - Plan now requires passing `client_correlation_id` into the private attempt method and adding it to the existing `runner.http.response` line at the same level, with no new log point or extra line.

4. Provider request id header allowlist is speculative.
   - Changed sections:
     - `1. Goal / Motivation / Success Signal`
     - `7. Implementation Decisions / Decision 5`
     - `8. Small Implementation Slices / Slice 2`
     - `10. Docs / README Decision`
     - `11. Risks / Open Questions`
     - `12. Stop Conditions`
   - Plan now keeps current `x-request-id` extraction only and explicitly excludes tracing / infrastructure headers from `provider_request_id`.

5. Tool Trace `diagnostic_ref=None` is valid.
   - Changed sections:
     - `7. Implementation Decisions / Decision 6`
     - `8. Small Implementation Slices / Slice 3`
     - `11. Risks / Open Questions`
   - Plan now says to keep `diagnostic_ref=None` when no raw payload ref or provider request id exists, and not to fake provider ids or diagnostic refs.

6. Slice 1 needs baseline assembly tests before default change.
   - Changed sections:
     - `8. Small Implementation Slices / Slice 1`
   - Plan now requires running baseline assembly tests before changing the default and classifying post-change failures as expected behavior changes or regressions.

## Validation Performed

- `git diff --check`
  - Result: passed with no output.
- `rg -n "[ \t]+$" docs/host/host-issues/wu-eng-02-r1-provider-debugging-correlation-plan.md docs/reviews/wu-eng-02-r1-plan-fix-codex-20260620.md`
  - Result: no matches; command exited 1 because `rg` reports no matches with exit code 1.

No pytest or pyright was run because this fix gate changed only Markdown planning artifacts and did not modify production code or tests.

## Remaining Residual Risks

None for the plan-fix gate.

Implementation residual risks remain documented in the plan, including provider rejection of `X-Client-Request-Id` and exact README update decisions after code changes.
