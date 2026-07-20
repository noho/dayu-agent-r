# WU-SEMANTIC-OWNERSHIP-01 P3-J Plan Fix - AgentCodex

## Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: plan fix
- Agent: AgentCodex
- Updated plan: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Controller adjudication: `docs/reviews/wu-semantic-ownership-01-p3-j-plan-review-controller-adjudication.md`

## Fix Summary

The plan now keeps the validated source-finding dispositions unchanged:

- `accepted`: 6
- `rejected-with-reason`: 6
- `deferred-with-owner`: 1
- `needs-more-evidence`: 0

The implementation plan is re-sliced into four independently reviewable closures:

1. `S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure`
2. `S2 - Queue Policy Owner And RunResult Terminal Row Surface`
3. `S3 - Idempotency And Descriptor Kind Weak-Contract Closure`
4. `S4 - Legacy Config Exposure Re-Ownership`

The plan explains why 4 slices are justified despite the control-doc small-cleanup default of 1-3 slices: EventLog DDL / fixture migration, queue policy + terminal-status typing, idempotency + descriptor validation, and runtime legacy config cleanup have separate owner boundaries and rollback surfaces.

## Accepted Finding Fixes

### P3-J-PF-01 - Reduce event_type blast radius and split S1

Status: fixed.

Plan locations:

- `## 3.1 Durable Event Type`
- `## 3.8.1 EventLog Event Type Baseline`
- `## 5. Implementation Slices`
- `### S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure`
- `### S2 - Queue Policy Owner And RunResult Terminal Row Surface`

Result:

- EventLog event type closure is now its own S1.
- S1 is limited to owner, append validation, row decoder, fresh-schema DDL, and required fixture migration.
- Consumer-wide redirection is explicitly non-goal unless required for typed append / row decoder compilation.
- Queue policy and RunResult terminal status moved to S2.

### P3-J-PF-02 - Make event type owner and legal set code-generation-ready

Status: fixed.

Plan locations:

- `## 3.1 Durable Event Type`
- `## 3.8.1 EventLog Event Type Baseline`
- `### S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure`

Result:

- Owner is explicitly `dayu/host/lifecycle_events.py` for P3-J.
- Plan preserves run / attempt lifecycle categories and requires additional category enums rather than one flat enum.
- Current production event type baseline is pre-enumerated by category.
- Exact pre-edit source scan rules are specified.
- Arbitrary test event types such as `TYPE_A`, `host.test`, `TEST_EVENT`, and lowercase dotted storage fixtures have a migration strategy and ordering before DDL rejection.

### P3-J-PF-03 - Remove queue_policy alias ambiguity and define the single owner

Status: fixed.

Plan locations:

- `## 3.2 Run Queue Policy And Execution Target`
- `## 3.8.2 Queue Policy Baseline`
- `### S2 - Queue Policy Owner And RunResult Terminal Row Surface`

Result:

- Alias option is removed.
- Single owner is `dayu/host/queue_policy.py` with `RunQueuePolicy`.
- Legal values are exactly `queue`, `reject`, and `attach_active`.
- Plan requires deleting `AdmissionPolicy` if scan confirms no external production consumers.
- Residual `AdmissionPolicy` and compatibility re-export scans are required.

### P3-J-PF-04 - Resolve descriptor kind diagnostic ownership and consumer fail-closed boundary

Status: fixed.

Plan locations:

- `## 3.5 Payload Descriptor Kind`
- `## 3.8.4 Descriptor Kind Baseline`
- `### S3 - Idempotency And Descriptor Kind Weak-Contract Closure`

Result:

- Descriptor kind baseline now lists all current values, including `compaction_rejected_attempt_diagnostic`.
- Diagnostic descriptor is assigned to compaction operation as producer and descriptor-kind owner as value contract.
- Producer-side unknown descriptor rejection is separated from consumer expected-kind validation.
- `payload_resolution` is no longer instructed to become a second global unknown-kind owner.

### P3-J-PF-05 - Decide idempotency DDL CHECK strategy before implementation

Status: fixed.

Plan locations:

- `## 3.4 Idempotency Scope / Result Kind`
- `## 3.8.3 Idempotency Validation Strategy`
- `### S3 - Idempotency And Descriptor Kind Weak-Contract Closure`

Result:

- Plan chooses Python-level typed validation only.
- Fresh-schema DDL `CHECK` for idempotency `scope_kind` / `result_kind` is explicitly omitted.
- Reason is recorded: values are Host operation-driven and extend with new Host commands / wait / tool operations.
- Tests must assert typed validation and intentional DDL omission.

### P3-J-PF-06 - Clarify admission.py sequencing across S1/S2

Status: fixed.

Plan locations:

- `### S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure`
- `### S2 - Queue Policy Owner And RunResult Terminal Row Surface`
- `### S3 - Idempotency And Descriptor Kind Weak-Contract Closure`

Result:

- S1 may touch `admission.py` only for event-type append validation needs.
- S2 owns queue policy changes in `admission.py` and explicitly forbids idempotency constant refactor.
- S3 owns idempotency scope / result kind changes in `admission.py` and explicitly forbids S2 queue-policy / terminal-status refactor.

## Updated Plan Controls

- Allowed files are now scoped per slice.
- Tests and source scans are now scoped per slice and in the aggregate matrix.
- README checks now cover S1/S2/S3 Host README triggers and S4 config/root README triggers.
- Stop conditions are now slice-local and no longer defer accepted plan decisions to implementation.
- Completion report format now includes the plan-fix artifact and updated slice summary.

## Follow-up Residual Wording Cleanup

After controller/user spot-check, two stale `Implementation direction` bullets were found in the source finding disposition section and fixed in the plan:

- `SS-6 - scope_kind / result_kind`: removed the old "add fresh-schema CHECK only if implementation audit confirms no intentionally open extension point" wording. The section now matches PF-05: P3-J uses Python-level typed validation only, explicitly omits `scope_kind` / `result_kind` DDL `CHECK`, records the operation-driven extension reason, and requires tests for typed rejection plus DDL omission.
- `SS-7 - Descriptor Kind`: removed the old "payload_resolution fails closed on absent / unknown / mismatched values" wording. The section now matches PF-04: producer/write helpers reject unknown descriptor kinds, while `payload_resolution` parses the caller expected kind and fails closed only on missing or mismatched metadata without maintaining a second all-known-kind owner.

## Unfixed Items

None. All controller-accepted plan findings P3-J-PF-01 through P3-J-PF-06 are fixed in the updated plan.

## Validation

Documentation-only plan fix. No code, tests, README, commits, pushes, or re-review gate actions were performed.
