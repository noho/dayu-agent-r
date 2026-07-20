# WU-SEMANTIC-OWNERSHIP-01 P3-J Plan Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-J - Host durable schema and weak-contract hardening backlog`
- Plan artifact: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Plan review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-plan-review-mimo.md`
  - `docs/reviews/plan-review-20260711-092745.md`

## Review Verdicts

| Reviewer | Conclusion | Material findings | Blocking open questions |
|---|---:|---:|---:|
| AgentMiMo | pass-with-risks | 5 | 0 |
| AgentDS | pass-with-risks | 8 | 5 |

## Controller Decision

The plan is not accepted for implementation yet. Source finding dispositions are mostly validated by both reviewers, but the plan must be fixed before implementation because S1 and S2 still push material design decisions into implementation and risk broad schema churn.

The controller accepts the following merged plan fixes.

## Accepted Plan Fixes

### P3-J-PF-01 - Reduce event_type blast radius and split S1

Sources:

- AgentDS 2-1
- AgentMiMo F3

Decision:

- Accepted.
- The current S1 combines EventLog event type closure, queue policy typing, and RunResult terminal status typing. That is too broad for one implementation/review cycle.
- Plan must split S1 into smaller semantic closures. The preferred direction is:
  - EventLog event type append/row-decoder/fresh-schema closure as its own slice.
  - Queue policy typed owner plus RunResult terminal-status row surface as a separate slice, unless plan gives a stronger reason to split them further.
- EventLog consumer-wide redirection must not be required in the first event-type slice unless the plan proves it is needed to enforce invalid write rejection. Consumer cleanup may be limited to call paths required by typed append/row-decoder boundaries and test compilation.

Required plan changes:

- Rewrite implementation slices to reflect the smaller closure.
- Explain why the final slice count is acceptable under the control doc slice budget.
- Update allowed files, tests, stop conditions, and completion report format per slice.

### P3-J-PF-02 - Make event type owner and legal set code-generation-ready

Sources:

- AgentDS 2-6, 2-8
- AgentMiMo F1, F5

Decision:

- Accepted.
- Plan must not leave the production EventLog legal set and category structure for the implementation agent to invent.
- The owner may be a single module with category enums and a shared helper; it does not have to be one flat enum. The plan must preserve existing lifecycle run/attempt category semantics unless it proves a safer alternative.

Required plan changes:

- Define the chosen event type owner structure at plan level.
- Pre-enumerate the current production event type baseline, or define an exact source-scan-derived table that the implementation agent must complete before code changes.
- Add a test-fixture migration strategy for arbitrary test event types such as `TYPE_A`, `host.test`, and `TEST_EVENT`.
- Specify implementation ordering: migrate fixtures and owner helpers before DDL rejection is enabled, then add invalid-event rejection tests.

### P3-J-PF-03 - Remove queue_policy alias ambiguity and define the single owner

Sources:

- AgentDS 2-2
- AgentMiMo F2

Decision:

- Accepted.
- The plan's "alias" option conflicts with the project ban on compatibility re-export / wrapper patterns.

Required plan changes:

- Delete the alias option.
- State the single queue policy owner explicitly.
- If `AdmissionPolicy` has no external production consumers, require deleting it and updating admission to consume the new owner directly.
- Add a source scan validation proving no residual `AdmissionPolicy` production references remain and no compatibility re-export is introduced.

### P3-J-PF-04 - Resolve descriptor kind diagnostic ownership and consumer fail-closed boundary

Sources:

- AgentDS 2-3, 2-5
- AgentMiMo residual risk on descriptor diagnostic kinds

Decision:

- Accepted.
- The current plan identifies possible ad hoc diagnostic descriptor kinds but pushes the decision into S2 implementation. That is not code-generation-ready.
- Consumer-side fail-closed behavior should validate missing/mismatched expected descriptor kind. Unknown-kind rejection belongs at producer/write-helper validation unless the consumer is explicitly reading an untrusted generic descriptor without an expected kind.

Required plan changes:

- List current descriptor kind baseline including diagnostic kinds such as `compaction_rejected_attempt_diagnostic`.
- Assign each listed kind to an owner or explicitly exclude it with reason.
- Clarify producer-side validation versus consumer expected-kind validation.
- Remove or rewrite the broad "payload_resolution fails closed on unknown" requirement if it would make the consumer a second global owner.

### P3-J-PF-05 - Decide idempotency DDL CHECK strategy before implementation

Sources:

- AgentDS 2-4
- AgentMiMo F4

Decision:

- Accepted.
- Current evidence suggests idempotency scope/result kind may be operation-driven and therefore extensible by future Host commands. The plan cannot leave DDL CHECK inclusion to implementation audit without a decision rule.

Required plan changes:

- State whether S2 adds Python-level typed validation only, or also adds fresh-schema DDL checks.
- If DDL checks remain planned, explain why the legal set is closed enough and document the extension rule for future Host commands.
- If DDL checks are omitted, explicitly record that decision and the reason, and adjust tests accordingly.

### P3-J-PF-06 - Clarify admission.py sequencing across S1/S2

Sources:

- AgentDS 2-7

Decision:

- Accepted.
- Both event/queue policy work and idempotency work touch `dayu/host/admission.py`. The plan must avoid cross-slice ownership ambiguity.

Required plan changes:

- Assign `admission.py` changes by semantic owner per slice.
- State that one slice must not preemptively refactor idempotency constants or event constants owned by a later slice.

## Rejected Or Non-Blocking Review Observations

- AgentMiMo and AgentDS both validate the plan's core source-finding dispositions. No fix is required for the rejected dispositions on memory freshness, immutable `host_run_results`, `HostRow`, metadata JSON, memory digest redundancy, or legacy `verified_fact` diagnostics unless plan fix work uncovers new direct current-code evidence.
- Existing-database migration risk remains non-blocking because project policy is fresh schema unless the task explicitly requires old DB compatibility.

## Next Gate

Next gate is plan fix by AgentCodex.

AgentCodex must update the plan artifact in place and produce a fix artifact:

- Updated plan: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-plan-fix-codex.md`

The plan remains unaccepted until AgentMiMo and AgentDS re-review the fixed plan.
