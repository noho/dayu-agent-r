# WU-SEMANTIC-OWNERSHIP-01 P3-J Plan Re-Review Controller Adjudication

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01`
- Sub-WU: `P3-J - Host durable schema and weak-contract hardening backlog`
- Fixed plan artifact: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Plan fix artifact: `docs/reviews/wu-semantic-ownership-01-p3-j-plan-fix-codex.md`
- Original plan review artifacts:
  - `docs/reviews/wu-semantic-ownership-01-p3-j-plan-review-mimo.md`
  - `docs/reviews/plan-review-20260711-092745.md`
- Re-review artifacts:
  - `docs/reviews/plan-review-20260711-094945.md`
  - `docs/reviews/plan-review-20260711-094944.md`

## Re-Review Verdicts

| Reviewer | Conclusion | PF-01..PF-06 | New material findings | Blocking open questions |
|---|---:|---:|---:|---:|
| AgentMiMo | PASS | fixed | 0 | 0 |
| AgentDS | PASS | fixed | 0 | 0 |

## Controller Decision

The P3-J plan is accepted as code-generation-ready.

Controller-accepted plan findings `P3-J-PF-01` through `P3-J-PF-06` are all closed:

- `P3-J-PF-01`: EventLog event-type work is narrowed to append / row-decoder / fresh-schema closure, and former S1 is split.
- `P3-J-PF-02`: Event type owner structure, production baseline, source scans, fixture migration, and DDL ordering are code-generation-ready.
- `P3-J-PF-03`: Queue policy alias ambiguity is removed; `RunQueuePolicy` is the single planned owner and `AdmissionPolicy` deletion / no-re-export scans are required.
- `P3-J-PF-04`: Descriptor kind diagnostic ownership is explicit, including `compaction_rejected_attempt_diagnostic`; producer unknown-kind rejection is separated from consumer expected-kind mismatch validation.
- `P3-J-PF-05`: Idempotency scope/result kind strategy is decided as Python-level typed validation only; DDL `CHECK` is intentionally omitted.
- `P3-J-PF-06`: `admission.py` ownership is sequenced across S1/S2/S3 and cross-slice preemption is prohibited.

## Accepted Implementation Slices

P3-J proceeds with four implementation slices:

1. `S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure`
2. `S2 - Queue Policy Owner And RunResult Terminal Row Surface`
3. `S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
4. `S4 - Legacy Config Exposure Re-Ownership`

The four-slice structure is accepted despite the control document's small-cleanup default of one to three slices because the first review proved the former S1 had excessive blast radius. The fixed plan now follows semantic owner boundaries and isolates schema/test-fixture, queue/read-model, idempotency/descriptor, and runtime config risks.

## Residual Risks

- S1 may still miss a production EventLog event type if source scans are incomplete. This is mitigated by pre-edit scan commands, a production baseline table, and S1 stop conditions.
- S1 fixture migration can introduce false positives. This is mitigated by the explicit fixture hotspot table and migration order before DDL rejection.
- S2 must prove `AdmissionPolicy` has no external production consumers before deletion. This is mitigated by required scans and stop conditions.
- S3 idempotency and descriptor baselines must be verified against current production producers during implementation. This is mitigated by source scans and slice-local stop conditions.
- Memory freshness and immutable `host_run_results` dispositions remain accepted/rejected as validated by both reviewers; no implementation work is assigned to those findings in P3-J unless new direct current-code evidence emerges.

## Next Gate

Next gate is accepted plan commit, then P3-J S1 implementation by AgentCodex.
