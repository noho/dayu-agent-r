# Gateflow Plan: Compact Rejected Attempt Diagnostic Artifact

- Gate: plan
- Work unit: Conversation Memory compact rejected attempt diagnostic artifact
- Design doc: `docs/host/conversation-memory-smoke-compact-followup.md`
- Baseline: current clean commit on `wu-cm-12-conversation-memory-drift`
- Decision: proceed with a narrow observability-only implementation
- Artifact path: `docs/reviews/wu-cm-compact-rejected-diagnostic-plan-20260619-124435.md`

## Goal / Motivation / Success Signal

Goal: when a compact proposal attempt is rejected before a proposal manifest exists, especially during `material_pack -> compact input -> previous_compacted_view` parsing, persist a durable diagnostic artifact that can identify and recover the offending material block without placing raw material text in EventLog canonical payloads or any LLM-facing material.

Motivation: long25 failures with `proposal_manifest_ref=null` and `ValueError: previous reference continuity text is invalid` cannot currently identify `material_pack.previous_compacted_view` or the raw `REFERENCE_CONTINUITY` block text. The existing smoke/log layer can mark `log_insufficient`, but durable truth lacks a ref to the failing material.

Success signals:

- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payloads can carry optional diagnostic artifact ref/digest/stage/block locator fields.
- A material projection failure writes a payload descriptor whose `metadata_json.descriptor_kind` is `compaction_rejected_attempt_diagnostic`.
- The artifact JSON contains enough DEBUG-only material to reconstruct the failing `previous_compacted_view`, including raw `REFERENCE_CONTINUITY` block text.
- EventLog canonical payload contains only small structured refs, digests, stage, parser/validator, exception summary, and block locator fields; it never contains raw block text.
- Compact accept/reject/fallback/tier behavior is unchanged.
- Focused tests cover artifact creation, descriptor metadata, EventLog redaction, artifact readback, and proposal-manifest-missing failure branch.

## Non-Goals / Scope Boundary

- Do not fix the parser root cause in `dayu/host/compact_material.py`.
- Do not relax parser, validator, accept barrier, source-label rules, current-input-anchor rules, or fallback policy.
- Do not change compact success/failure decisions or fallback tier behavior.
- Do not write raw block text into EventLog payload, memory projection, compact LLM input, ordinary RunInput, or any LLM-facing material.
- Do not add a parallel storage system.
- Do not bypass `LocalArtifactStore.write_artifact_bytes()` or `PayloadStore.write_payload_descriptor_for_artifact()`.
- Do not change durable SQL schema. `descriptor_kind` is metadata in `payload_descriptors.metadata_json`; define any new kind/media/schema strings in the owning Host module unless implementation evidence shows a cross-module constant is needed.

## Design Alignment

- `docs/host/design.md` says rejected proposal content, transient artifacts, or diagnostic payloads must not enter Conversation Memory or accepted compacted view, and large diagnostic payloads should be artifact-backed.
- `RUNNER_CALL_INPUT_ASSEMBLED` manifests are written before proposal runner calls and cannot exist for prepare/material projection failures.
- `CONTEXT_COMPACTION_ATTEMPT_REJECTED` is a Host governance diagnostic fact. Extending it with optional diagnostic artifact refs preserves EventLog as an index and keeps raw diagnostic content in artifact storage.
- `current_input_anchor` remains readable-but-not-citable. This work does not affect compact candidate source label validation.

## First-Principles Judgment and Code Evidence

The work unit is valid because the failing material and the rejected attempt identity are available on the same call path, but no durable writer currently records them.

Direct evidence:

- `run_compaction_operation()` catches proposal preparation/execution failures and creates `CompactionAttemptRejected`, but the summary currently only carries `diagnostic_refs`, runner summary refs, and optional proposal manifest ref/digest.
- `_prepare_compactor_proposal()` calls `conversation_compact_input_vnext_from_material_pack(request.material_pack)` before manifest recording for prepared compactor paths and in the generic path before `compactor.compact()`.
- `_previous_compacted_references_vnext()` iterates `block.text.splitlines()` for `REFERENCE_CONTINUITY`; `_parse_previous_reference_continuity_text()` raises `ValueError("previous reference continuity text is invalid")`.
- `build_context_compaction_attempt_rejected_payload()` already centralizes canonical rejected attempt payload shape, so optional diagnostic ref fields belong there.
- `DurableCompactorProposalManifestRecorder` already demonstrates the correct storage pattern: `LocalArtifactStore.write_artifact_bytes()` followed by `PayloadStore.write_payload_descriptor_for_artifact()` inside a Host transaction.

## Affected Files / Modules

Expected code changes:

- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`

Expected tests:

- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`

Docs decision:

- Check README triggers after implementation.
- Likely update `docs/host/conversation-memory-smoke-compact-followup.md` with implementation status only.
- Update `dayu/host/README.md`, root `README.md`, or `tests/README.md` only if their own Agent update constraints and reader responsibilities are triggered by the final diff.

Explicitly avoid unless proven necessary:

- `dayu/host/durable/schema.py`
- `dayu/host/compact_material.py`
- compactor prompt/config
- accept barrier / memory projection semantics

## Contract / Schema / State-Machine Changes

Canonical EventLog payload contract:

Extend `build_context_compaction_attempt_rejected_payload()` with optional fields:

- `diagnostic_artifact_ref: str | None`
- `diagnostic_artifact_digest: str | None`
- `failure_stage: str | None`
- `diagnostic_suffix: str | None`
- `parser_or_validator: str | None`
- `exception_class: str | None`
- `exception_message: str | None`
- `offending_block_section: str | None`
- `offending_block_kind: str | None`
- `offending_block_label: str | None`
- `offending_block_ordinal: int | None`
- `offending_block_text_digest: str | None`
- `offending_block_text_length: int | None`
- `material_pack_digest: str | None`

Validator invariants:

- `diagnostic_artifact_ref` and `diagnostic_artifact_digest` must be both null or both non-null.
- If `diagnostic_artifact_digest` is non-null, it must be a SHA-256 digest.
- Text summary fields, if present, must be non-empty text.
- `offending_block_ordinal`, if present, must be non-negative.
- `exception_message` must be produced with the existing safe exception redaction/truncation helper, not with raw `str(exc)`.
- EventLog payload must not contain raw block text. No field named `text`, `raw_block_text`, `block_text`, or equivalent will be added to the canonical payload.

Stable `failure_stage` values for this work unit:

- `material_pack_to_compact_input`: compact material pack could not be projected into compact input before a proposal manifest existed.
- `previous_compacted_view_parse`: offending material is localized to previous compacted view parsing, including `REFERENCE_CONTINUITY` parse failures.
- `proposal_execution`: proposal runner call or prepared proposal execution failed after material projection; artifact creation is optional when a proposal manifest already exists.

Stage classification algorithm:

- If the safe exception message is exactly `previous reference continuity text is invalid` and at least one previous `REFERENCE_CONTINUITY` block exists, use `previous_compacted_view_parse` and `parser_or_validator="previous_reference_continuity"`.
- Else if `proposal_manifest_reference is None`, use `material_pack_to_compact_input` and `parser_or_validator="conversation_compact_input_vnext_from_material_pack"`.
- Else use `proposal_execution` and `parser_or_validator="compactor_proposal_execution"`.
- If offending block detection cannot localize a single block, keep the stage from this algorithm and set `offending_block` fields to null while preserving previous-view locator summaries in the artifact.

Artifact descriptor contract:

- Payload descriptor `payload_ref`: stable and identifiable, using a unique diagnostic event id such as `compaction-diagnostic:<event-compaction-rejected-diagnostic-uuid>`. Do not use only `<operation-id>:<attempt-number>` because proactive recovery tiers can reuse operation id and attempt number.
- Descriptor metadata:
  - `descriptor_kind: "compaction_rejected_attempt_diagnostic"`
  - `schema_version: "compaction_rejected_attempt_diagnostic.v1"`
  - `event_type: "CONTEXT_COMPACTION_ATTEMPT_REJECTED"`
  - `diagnostic_event_id`
  - `compaction_operation_id`
  - `compaction_attempt_number`
  - `compaction_request_digest`
  - `failure_stage`
  - `failure_category`
  - `exception_class`
  - `parser_or_validator`
  - `contains_raw_material: true`
  - `confidential: true`

Artifact media type:

- `application/vnd.dayu.compaction-rejected-attempt-diagnostic+json`

Artifact JSON schema v1:

- `schema_version`
- `event_type`
- `session_id`
- `host_run_id`
- `attempt_id`
- `execution_id`
- `input_snapshot_cursor`
- `memory_snapshot_cursor`
- `compaction_operation_id`
- `compaction_attempt_number`
- `failure_stage`
- `failure_category`
- `parser_or_validator`
- `exception_class`
- `exception_message`
- `diagnostic_suffix`
- `proposal_manifest_ref`
- `proposal_manifest_digest`
- `material_pack_digest`
- `compaction_request_digest`
- `contains_raw_material`
- `confidential`
- `previous_compacted_view`: list of compact material block JSON, including raw `text`
- `material_pack_summary`
  - `trace_material_count`
  - `evidence_material_count`
  - `answer_material_count`
  - `current_input_anchor_digest`
  - `current_input_anchor_length`
- `offending_block`
  - `section`
  - `kind`
  - `block_label`
  - `ordinal`
  - `path`
  - `content_digest`
  - `text_digest`
  - `text_length`
  - `source_labels`
  - `canonical_source_refs`
  - `raw_text`
- `all_previous_compacted_view_blocks`: locator summaries for all previous blocks

State-machine invariant:

- `run_compaction_operation()` must not write durable diagnostic artifacts directly because it runs outside the caller's rejected-event transaction.
- `run_compaction_operation()` may only construct an in-memory diagnostic body/summary on proposal failure branches and attach it to `CompactionAttemptRejected`.
- Durable artifact bytes, payload descriptor, and `CONTEXT_COMPACTION_ATTEMPT_REJECTED` EventLog payload must be prepared in the caller append helper (`dispatch.py` and `engine_ingest.py`) immediately before appending the rejected event. Descriptor insert and EventLog append share the same SQLite transaction.
- Diagnostic artifact write failure is best-effort: catch, log a warning with structured context, and append the rejected attempt event without `diagnostic_artifact_ref`.
- Diagnostic artifact write failure must not turn a rejected attempt into accepted compact, dispatch fallback, a different tier, or a different failure category.
- If artifact bytes are written but descriptor/event transaction later rolls back, an artifact-file-only orphan is acceptable and follows existing local artifact write tradeoffs; descriptor-without-event should be avoided by sharing the EventLog transaction.
- `CONTEXT_COMPACTION_FAILED` does not need a duplicate diagnostic artifact field in this work unit. Trace path is: failed event `operation_id` -> same-operation `CONTEXT_COMPACTION_ATTEMPT_REJECTED` rows -> `diagnostic_artifact_ref` -> `payload_descriptors` -> artifact JSON.

## Implementation Decisions

1. Add diagnostic dataclasses in `compaction_operation.py`.
   - `CompactionRejectedAttemptDiagnostic`: in-memory artifact body plus EventLog summary fields; may contain raw previous-view text and must never be projected to LLM-facing material.
   - `CompactionRejectedAttemptDiagnosticReference`: persisted ref/digest plus the same safe summary fields after the caller writes artifact/descriptor.
   - Summary fields: failure stage, diagnostic suffix, parser/validator, exception class/message, offending block section/kind/label/ordinal/text digest/text length, material pack digest, compaction request digest.

2. Add pure diagnostic body builder helpers in `compaction_operation.py`.
   - Method shape: `_compaction_rejected_attempt_diagnostic(request, compaction_operation_id, compaction_attempt_number, failure_category, diagnostic_suffix, exception, proposal_manifest_reference) -> CompactionRejectedAttemptDiagnostic | None`.
   - Called from both proposal failure catch branches before `_attempt_rejected()`.
   - Prepared compactor `prepare_compactor_proposal_run_input()` failures land in the generic `except Exception` branch because that call occurs before `_CompactorProposalExecutionError` wrapping; this branch must be covered.
   - For cancellation, quality rejection, and hard-threshold rejection, do not create material diagnostic artifacts.

3. Add durable diagnostic write helpers in `dispatch.py` and `engine_ingest.py`.
   - Reuse `LocalArtifactStore.write_artifact_bytes()` and `PayloadStore.write_payload_descriptor_for_artifact()`.
   - Write artifact bytes and descriptor immediately before `EventLogStore.append_event()` for `CONTEXT_COMPACTION_ATTEMPT_REJECTED`.
   - Descriptor insert and rejected EventLog append must share the caller's current SQLite transaction.
   - If durable diagnostic write fails, log a warning and continue appending the rejected event without diagnostic artifact ref/digest.

4. Offending block detection.
   - For `ValueError("previous reference continuity text is invalid")`, choose the first `previous_compacted_view` block with `kind == REFERENCE_CONTINUITY` that contains a line that fails the known parse contract.
   - Keep this helper diagnostic-only; do not change parser behavior. If the implementation mirrors parser checks instead of calling the private parser, its docstring must state which parser contract it mirrors and tests must cover the current error message.
   - If no exact block is identified, still write the artifact with `offending_block=null` and all previous block locator summaries.
   - Serialize previous view blocks with existing `CompactMaterialBlock.to_json()`; do not add a new serializer or modify `compact_material.py`.

5. Extend `CompactionAttemptRejected`.
   - Add one optional field: `diagnostic: CompactionRejectedAttemptDiagnostic | None`.
   - `_attempt_rejected()` must accept `diagnostic` and store it directly. Do not flatten the diagnostic into many top-level dataclass fields.
   - The caller append helper converts `diagnostic` into `CompactionRejectedAttemptDiagnosticReference` only after artifact/descriptor persistence succeeds.

6. Extend logging.
   - Update `_log_rejected_attempt()` to include fields from `rejected.diagnostic` when present: `failure_stage`, `diagnostic_suffix`, `parser_or_validator`, `exception_class`, `offending_block_kind`, `offending_block_label`, `offending_block_ordinal`, `offending_block_text_digest`, `offending_block_text_length`, and `material_pack_digest`.
   - Caller append helpers log durable persistence summaries including `diagnostic_artifact_ref` and `diagnostic_artifact_digest` when persistence succeeds.
   - INFO/VERBOSE log prints structure only, never raw text.

7. Wire proactive and reactive callers.
   - In `_append_compaction_attempt_rejected_event()`, persist `rejected.diagnostic` if present and pass optional persisted diagnostic fields into the context event builder.
   - In `engine_ingest.py`, apply the same write-and-payload flow in the reactive rejected event append path.
   - No new `run_compaction_operation()` recorder parameter is needed after this plan fix.

8. Do not update `dayu/host/durable/schema.py` initially.
   - The new descriptor kind is metadata, not a SQL schema or table contract.
   - Revisit only if existing code requires centralized constants for payload descriptor kind validation.

## Implementation Slices

### Slice 1: Core Diagnostic Artifact Contract and Operation Recorder

Allowed files:

- `dayu/host/compaction_operation.py`
- `dayu/host/context_events.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_context_compact_events.py`

Exact allowed changes:

- Add optional rejected payload diagnostic fields and validator checks.
- Add diagnostic dataclasses, artifact body helpers, block locator helpers, payload ref helper, and safe logging fields.
- Call the diagnostic body builder only in both proposal failure branches.
- Extend tests with a material projection failure scenario that produces a diagnostic ref.

Data flow:

`run_compaction_operation()` catches projection exception -> builds diagnostic suffix -> pure helper builds in-memory diagnostic body/summary -> `_attempt_rejected()` stores `rejected.diagnostic` -> caller rejected-event append helper persists artifact/descriptor in its EventLog transaction -> context event builder serializes small fields from the persisted diagnostic reference.

Tests:

- `test_attempt_rejected_payload_builder_and_validator` updated for optional diagnostic artifact pair.
- New validator negative test: diagnostic ref/digest pair must be paired; digest must be SHA-256.
- New operation test:
  - Build a `CompactionRequest` whose `previous_compacted_view` has an invalid `REFERENCE_CONTINUITY` block text.
  - Run `run_compaction_operation()` with `max_attempts=1`.
  - Assert rejected attempt has `proposal_manifest_ref is None`, `diagnostic` present, failure stage `previous_compacted_view_parse`, and offending block locator fields are present.
  - Assert artifact JSON includes raw `previous_compacted_view` but only non-raw summary/counts/digests for trace/evidence/answer/current anchor.
- New durable write helper test:
  - Persist `rejected.diagnostic` through the append helper or a focused helper under the same transaction shape.
  - Read descriptor from SQLite and artifact file from artifact root; assert descriptor metadata kind and artifact JSON contains raw offending block text.
  - Build EventLog payload from persisted reference and assert raw block text is absent from payload serialization.
- New best-effort failure test:
  - Force artifact write failure and assert the rejected event payload omits diagnostic artifact ref/digest while the rejected attempt remains observable.
- New null-localization test:
  - Use a projection failure not localized to a single previous block and assert `offending_block` fields are null while previous block locator summaries remain in the artifact body.

Stop condition:

- If artifact cannot be written using existing `LocalArtifactStore` + `PayloadStore` without production behavior changes, stop and report.

### Slice 2: Proactive / Reactive EventLog Wiring and Logging

Allowed files:

- `dayu/host/dispatch.py`
- `dayu/host/engine_ingest.py`
- `tests/host/test_compaction_operation.py` or existing dispatch/engine ingest tests if a narrower integration assertion is available

Exact allowed changes:

- Add helper functions to persist rejected diagnostic artifacts near existing compact artifact writer logic.
- Persist and pass `CompactionAttemptRejected.diagnostic` fields into `build_context_compaction_attempt_rejected_payload()`.
- Add or update one focused integration-style test if existing unit tests do not prove EventLog payload wiring.

Data flow:

Proactive/reactive compact operation result -> rejected attempt diagnostic body -> append helper writes artifact/descriptor in the rejected EventLog transaction -> `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload optional diagnostic artifact fields -> SQLite EventLog row indexes artifact descriptor by ref/digest.

Tests:

- Prefer unit-level assertion that a rejected attempt with diagnostic fields builds an event payload through append helper without raw text.
- Cover both proactive append helper and reactive append helper if practical. If reactive setup is too broad, document residual risk and ensure the shared payload-building helper is tested.

Stop condition:

- If wiring requires changing compact state transitions, fallback decisions, or accepted compact artifact behavior, stop and report.

### Slice 3: Docs / README Decision

Allowed files:

- `docs/host/conversation-memory-smoke-compact-followup.md`
- `dayu/host/README.md` only if its Agent update constraints require it
- `README.md` only if root README reader-facing troubleshooting changes require it
- `tests/README.md` only if tests README constraints require it

Exact allowed changes:

- Add implementation status noting rejected attempt diagnostic artifacts.
- Document how to trace from EventLog payload fields to `payload_descriptors` and then artifact JSON, if a README responsibility clearly covers this.
- Do not describe future issue 80 eval or production parser fix as completed.

Tests:

- None for docs.

Stop condition:

- If README scopes do not cover this operator/debug detail, do not modify README and record no-trigger decision.

## Validation Commands

Required after implementation:

```bash
source .venv/bin/activate && pytest tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py
source .venv/bin/activate && pyright dayu/host/compaction_operation.py dayu/host/context_events.py dayu/host/dispatch.py dayu/host/engine_ingest.py tests/host/test_compaction_operation.py tests/host/test_context_compact_events.py
```

If integration tests are modified, include the exact affected test file in pytest.

Long smoke:

- Not required for this work unit because the target is deterministic artifact/payload behavior and long25 calls real LLM paths. If not run, closeout must state this explicitly.

## Risks / Open Questions

- Residual risk assigned to later work unit: the actual previous reference continuity parser root cause remains unresolved.
- Residual risk assigned to later work unit: long25 may still fail with `CONTEXT_COMPACTION_FAILED`; this work should make the failure materially easier to diagnose.
- Residual risk assigned to storage lifecycle maintenance: if artifact bytes are written and the SQL transaction later rolls back, artifact-file-only orphans may remain; descriptor-without-event should be avoided by sharing the rejected EventLog transaction.
- No blocking open questions at plan time.

## Why This Is Not Over-Designed

- Avoids a new durable recorder protocol after review found a separate transaction would create descriptor/EventLog consistency risk; the operation layer only builds an in-memory diagnostic body.
- Reuses existing content-addressed artifact store and payload descriptor table.
- Does not add new SQL tables, external indexes, storage roots, LLM-facing material, or parser behavior.
- Keeps EventLog as a compact index and puts raw DEBUG material only in a diagnostic artifact.

## Completion Report Format

Final closeout must state:

- Changed files.
- New diagnostic artifact descriptor fields and EventLog payload fields.
- How to trace from EventLog / SQLite to artifact JSON.
- Validation command results.
- Remaining risks, especially production compact parser failure and long25 not being fixed by this work.
