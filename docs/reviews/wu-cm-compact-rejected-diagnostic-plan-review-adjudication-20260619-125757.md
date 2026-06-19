# Plan Review Adjudication: Compact Rejected Attempt Diagnostic Artifact

- Gate: plan review fix/adjudication
- Work unit: Compact rejected attempt diagnostic artifact
- Plan: `docs/reviews/wu-cm-compact-rejected-diagnostic-plan-20260619-124435.md`
- Formal planreview artifacts:
  - AgentDS: `docs/reviews/plan-review-20260619-125333.md`
  - AgentMiMo: `docs/reviews/plan-review-20260619-125457.md`
- Superseded/manual reference artifacts:
  - `docs/reviews/plan-review-agent-ds-20260619-125047.md`
  - `docs/reviews/plan-review-agent-mimo-20260619-125047.md`
- Decision: accepted findings fixed in plan
- Artifact path: `docs/reviews/wu-cm-compact-rejected-diagnostic-plan-review-adjudication-20260619-125757.md`

## Context

The first Agent review dispatch was a manual read-only prompt and did not invoke `/planreview`. That did not satisfy the gateflow plan review gate. I reran both AgentMiMo and AgentDS with the Claude `/planreview` skill. The formal artifacts listed above are the authoritative plan review inputs for this gate. The manual artifacts remain only as historical reference and are superseded by the formal `/planreview` artifacts.

## Findings Adjudication

### DS-F1: Independent durable recorder transaction can create descriptor/EventLog orphan window

- Status: accepted
- Fix: plan no longer uses a durable recorder inside `run_compaction_operation()`.
- Updated plan:
  - operation layer only builds in-memory diagnostic body/summary;
  - durable artifact bytes, descriptor, and rejected EventLog payload are handled by caller append helpers;
  - descriptor insert and rejected EventLog append share the same SQLite transaction;
  - artifact-file-only orphan after SQL rollback is explicitly accepted as an existing local artifact tradeoff.
- Re-review focus: ensure no plan text still requires `DurableCompactionRejectedAttemptDiagnosticRecorder` or a `run_compaction_operation()` recorder parameter.

### DS-F2 / Mimo-F2: Offending block detection mirrors parser logic and may drift

- Status: accepted with bounded mitigation
- Fix: plan now requires a diagnostic-only docstring if implementation mirrors parser checks and tests for the current error message. It also allows direct reuse of the parser if implementation chooses that path.
- Reason not fully eliminated: this work unit cannot modify parser/root cause semantics. Diagnostic localization for the current failure is sufficient, and future parser changes must update the diagnostic mirror.
- Residual risk classification: assigned to later production parser/root-cause work unit if parser protocol changes.

### DS-F3 / Mimo-F1: `failure_stage` values defined but classification algorithm missing

- Status: accepted
- Fix: plan now defines stable `failure_stage` values and a classification algorithm:
  - exact safe message `previous reference continuity text is invalid` + reference block -> `previous_compacted_view_parse`;
  - no proposal manifest -> `material_pack_to_compact_input`;
  - manifest present/proposal execution -> `proposal_execution`.
- Re-review focus: ensure implementation no longer needs to invent stage mapping.

### DS-F4: raw text in diagnostic artifact needs data sensitivity handling

- Status: accepted with bounded mitigation
- Fix: plan keeps raw text because it is required by user acceptance criteria, but now limits raw material to `previous_compacted_view`/offending block, avoids full trace/evidence/answer raw sections, and marks metadata/artifact as `contains_raw_material=true` and `confidential=true`.
- Residual risk classification: accepted in current slice as a diagnostic artifact access-control concern; artifact root access is already operator/local filesystem level.

### DS-F5: recovery tiers reuse operation/attempt identity

- Status: accepted
- Fix: plan no longer uses `<operation-id>:<attempt-number>` as the sole payload ref. It uses a unique diagnostic event id in `payload_ref` and adds `compaction_request_digest` to metadata/artifact for disambiguation.
- Reason not adding `recovery_tier`: current request objects do not carry an explicit recovery tier, and adding it would widen production state. `compaction_request_digest` plus unique diagnostic id is enough for this work unit.

### DS-F6 / Mimo-F3: tests miss recorder/storage failure, null localization, reactive wiring

- Status: accepted
- Fix: plan tests now require:
  - best-effort artifact write failure path;
  - null offending-block localization path;
  - durable write helper readback and EventLog redaction;
  - proactive and reactive append helper coverage where practical, with residual risk documented if reactive setup is too broad.

### Mimo-F2: prepared compactor prepare failure branch not explicit

- Status: accepted
- Fix: plan now explicitly states `prepare_compactor_proposal_run_input()` failures happen before `_CompactorProposalExecutionError` wrapping and must be covered in the generic `except Exception` branch.

### Mimo-F4: `diagnostic_suffix` not in EventLog payload

- Status: accepted
- Fix: plan adds optional `diagnostic_suffix` to EventLog payload contract and logging fields so payload can align with existing `diagnostic_refs`.

### Mimo-F5: `CompactMaterialBlock` serialization unspecified

- Status: accepted
- Fix: plan now requires existing `CompactMaterialBlock.to_json()` and forbids adding a new serializer or modifying `compact_material.py`.

## Residual Risks

- Parser root cause remains unresolved: assigned to later production memory compact failure work unit.
- Parser-diagnostic mirror drift: assigned to later production parser/root-cause work if parser protocol changes.
- Artifact-file-only orphan after SQL rollback: accepted storage lifecycle residual; descriptor-without-event should be avoided by sharing the rejected EventLog transaction.
- long25 may still fail: assigned to later production compact failure work unit; this work only improves observability.

## Completion Status

Accepted findings have been addressed in the plan artifact. Proceed to re-review gate with AgentMiMo and AgentDS using `/planreview`.
