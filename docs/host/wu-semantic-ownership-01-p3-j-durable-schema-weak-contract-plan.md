# WU-SEMANTIC-OWNERSHIP-01 P3-J Durable Schema And Weak-Contract Plan

## 0. Plan Gate Scope

- Work unit: `WU-SEMANTIC-OWNERSHIP-01 / P3-J - Host durable schema and weak-contract hardening backlog`
- Gate: `plan`
- Role: AgentCodex
- Artifact path: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- Design sources: `docs/host/design.md`, `docs/engine/design.md`
- Control source: `docs/host/issues-implementation-control.md`
- Goal confirmation: `docs/reviews/wu-semantic-ownership-01-p3-j-goal-confirmation.md`
- Source adjudication: `docs/reviews/wu-semantic-ownership-01-fullrepo-deepreview-round2-controller-adjudication.md`
- Source review snippets:
  - `docs/reviews/repo-review-20260710-091608.md`: AgentDS finding 5, finding 20
  - `docs/reviews/2026-07-10-semantic-ownership-drift-review.md`: SS-1, SS-2, SS-3, SS-4, SS-6, SS-7, SS-8, SS-9, SS-11, SS-12

Preflight evidence:

- Branch: `phaseflow/host-issues-control`
- Existing external dirty / untracked files observed before this plan:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `docs/cli_ci.md`
  - `docs/cli_ci_oracles.json`
  - `docs/cli_ci_scenarios.json`
  - `docs/reviews/code-review-20260710-135625.md`
  - `docs/reviews/code-review-20260710-141049.md`
- This plan must not modify, format, delete, stage, or rely on those files.

## 1. First-Principles Judgment

The motivation is valid, but the source findings are not equally severe.

Host durable state is the recovery and governance truth boundary. If durable facts such as EventLog event type, run queue policy, idempotency scope, descriptor kind, or terminal status are accepted as unconstrained text, an invalid durable row can later be interpreted differently by projection, recovery, read APIs, audit, memory, or LLM-facing input assembly. The correct fix must land at the owner boundary: typed input validation, durable schema constraints, row decoders, and shared projection helpers.

The motivation is over-broad for findings that only observe generic representation choices. `HostRow` column strings, generic metadata JSON, memory snapshot digest duplication, and the old `verified_fact` scanner branch are not defects unless current code proves a concrete wrong public output or LLM-facing stale input path. Current code already has typed metadata entries, fail-closed row decoders, memory snapshot cursor checks, digest integrity checks, and explicit old-kind rejection. P3-J must not become a whole-store rewrite.

## 2. Goal / Motivation / Success Signal

Goal:

- Harden high-value Host durable closed sets and weak contracts where current code proves the legal value set and the owner boundary is clear.
- Reject or defer broad weak-contract observations when current code does not prove a real owner-boundary failure path.
- Remove or re-own ownerless legacy runtime config exposure.

Motivation:

- Host is the truth owner for Session / Run / Attempt / EventLog / admission / projection / memory / read output governance.
- Engine only emits typed single-run events and does not own Host durable schema.
- Durable schema and row decoder behavior must fail closed on invalid durable facts before invalid values can reach public read output or LLM-facing input.

Success signals:

- Every P3-J source finding is classified as `accepted`, `rejected-with-reason`, `deferred-with-owner`, or `needs-more-evidence` with current-code evidence.
- Accepted closed sets have one Python owner and, where legal sets are fixed rather than operation-extensible, fresh-schema DDL `CHECK` coverage.
- Durable row decoders return typed values or fail closed instead of re-exposing invalid strings.
- Public / LLM-facing projections consume the same typed owner or owner helper, not local raw-string copies.
- Legacy config filename exposure is removed from `dayu.runtime.ConfigLoader` or moved to an explicit owner with tests.
- Affected tests and pyright pass.
- README trigger checks are recorded.

## 3. Owner Boundary And Propagation Audit Requirements

### 3.1 Durable Event Type

Owner:

- `dayu/host/lifecycle_events.py` remains the single Host EventLog event type owner for P3-J.
- The owner must preserve the existing lifecycle category semantics instead of flattening every value into one undifferentiated enum:
  - keep `HostRunEventType` and `HostAttemptEventType` as the run / attempt lifecycle categories;
  - add owner-owned category enums for admission / command request events, tool / wait events, context governance events, runner-input events, engine diagnostic events, and preview events;
  - add aggregate helpers such as `parse_host_event_type(value: str) -> HostEventType`, `serialize_host_event_type(value: HostEventType) -> str`, `all_host_event_type_values() -> tuple[str, ...]`, and category-specific value helpers for DDL / EventLog filters.
- P3-J must not create a second `event_types.py` owner unless it also moves every category enum and helper there in the same slice. A re-export from `lifecycle_events.py` solely to preserve old imports is prohibited.

Propagation requirements:

- Producers: Host modules that append `EventLogAppendRequest`.
- Validation: `EventLogAppendRequest` validation and EventLog row decoder.
- Persistence: `dayu/host/durable/schema.py` fresh-schema `event_log.event_type` `CHECK`.
- Projection / public output: first event-type slice only redirects consumers that must compile against the typed append / row decoder contract. Consumer-wide local constant cleanup is not required to reject invalid writes and must not be treated as a prerequisite for the first event-type closure.
- LLM-facing output: memory and RunInputBuilder benefit from EventLog append / row-decoder rejection because illegal committed event types cannot be returned as valid `EventLogRow` values. Broader import cleanup may be a later slice / later work unit only if review finds a concrete consumer drift.

### 3.2 Run Queue Policy And Execution Target

Owner:

- `queue_policy`: new `dayu/host/queue_policy.py` Host contract owner with `RunQueuePolicy` and parse / serialize helpers. `AdmissionPolicy` is not the owner and must be deleted if source scan confirms it has no external production consumers.
- `execution_target`: deployment / Service execution configuration resolves the target identifier; Host stores and propagates the resolved non-empty identifier. P3-J must not invent a global closed set for deployment-specific target ids.

Propagation requirements:

- Producers: `StartRunRequest`, `SubmitFollowupRequest` path, admission, retry / replay / queue promotion.
- Validation: public request validation and durable row insert validation.
- Persistence: `host_runs.queue_policy` fresh-schema `CHECK`; `execution_target` remains non-empty unless a design source defines a closed set.
- Projection / public output: dispatch snapshot and run snapshots must preserve the same resolved target text; queue policy must round-trip through the typed owner.

### 3.3 RunResult Terminal Status

Owner:

- Run status enum and terminal-status helper in Host state / lifecycle contract.

Propagation requirements:

- Producers: minimal read model projection from terminal EventLog facts.
- Validation: `RunResultRow` constructor / validator and row decoder.
- Persistence: `host_run_results.terminal_status` existing `CHECK`.
- Public output: any consumer of `RunResultRow` must receive a typed `RunStatus` or consume a single serializer helper. No consumer should reparse raw strings.

### 3.4 Idempotency Scope / Result Kind

Owner:

- `dayu.host.durable.idempotency` owns typed idempotency scope / result kind parsing and row validation.
- P3-J deliberately does not add fresh-schema DDL `CHECK` constraints for `idempotency_records.scope_kind` or `idempotency_records.result_kind`. Current direct evidence shows the values are Host operation-driven and extend when new Host commands or wait/tool operations are added; a DDL closed set would turn ordinary command extension into schema migration work without proving a stronger durable invariant.

Propagation requirements:

- Producers: admission, session lifecycle, waiting, purge, and any Host command using `IdempotencyScope` or `IdempotencyResultRef`.
- Validation: `IdempotencyScope` and `IdempotencyResultRef`.
- Persistence: no P3-J DDL `CHECK`; Python-level typed validation and row decoder fail-closed behavior are the owner boundary.
- Projection / public output: replay / conflict helpers compare enum values or owner helper outputs, not naked strings.

### 3.5 Payload Descriptor Kind

Owner:

- Durable payload descriptor metadata contract, implemented as a single typed owner in or next to `dayu/host/durable/schema.py` so current descriptor constants and schema-related media type constants do not split.
- `compaction_rejected_attempt_diagnostic` is included in the descriptor kind legal set as a compaction diagnostic descriptor owned by `dayu/host/compaction_operation.py` as producer and the descriptor-kind owner as value contract. It is not excluded as ad hoc metadata.

Propagation requirements:

- Producers: tool runtime, RunInputBuilder, compaction operation, engine ingest, and any payload writer that sets descriptor kind.
- Validation: producer-side payload write helpers reject missing / unknown descriptor kind before writing metadata. `payload_resolution` validates the caller's expected descriptor kind by parsing that expected kind and then checking missing / mismatched descriptor metadata; it must not become a second global unknown-kind owner for unrelated descriptors.
- Persistence: descriptor kind remains inside `metadata_json`, but the value must be written and checked through the same typed owner.
- Projection / LLM-facing output: payload resolution for LLM-facing runner input projection and tool schema snapshots must fail closed on mismatched typed descriptor kind.

### 3.6 Conversation Memory Freshness

Owner:

- Conversation Memory projection owns snapshot cursor / digest.
- RunInputBuilder owns pre-dispatch freshness checks before memory reaches LLM-facing input.

Propagation requirements:

- Producers: memory projection writes snapshots and projection checkpoint in the same transaction where required.
- Validation: snapshot row decoder validates digest, item kinds, cursor, and checkpoint event identity.
- Persistence: snapshot row stores cursor columns and snapshot JSON.
- LLM-facing output: RunInputBuilder must reject or repair stale / damaged / ahead snapshots before building `AgentRunRequest.messages`.

### 3.7 Legacy Runtime Config Names

Owner:

- `dayu.runtime.ConfigLoader` owns current runtime config filenames only.
- If old filename guard remains necessary for `dayu-cli init`, the CLI init asset copier owns that defensive guard, not ConfigLoader's public API.

Propagation requirements:

- Producers: `dayu-cli init` asset selection.
- Validation: init must reject old top-level config assets if they ever appear in the copied config set.
- Persistence: no durable state.
- Public / docs output: no runtime public API should expose old config names as an ongoing compatibility surface.

### 3.8 Code-Generation Baselines And Ordering Decisions

#### 3.8.1 EventLog Event Type Baseline

The first implementation slice must start from this baseline and complete the exact source-scan table before editing code. The baseline is intentionally grouped by lifecycle category; implementation must not replace it with one flat enum.

| Category | Current production values |
|---|---|
| Run lifecycle | `RUN_ACCEPTED`, `RUN_QUEUED`, `RUN_STARTED`, `RUN_WAITING`, `RUN_CANCELLING`, `RUN_RECOVERING`, `RUN_SUCCEEDED`, `RUN_FAILED`, `RUN_CANCELLED`, `RUN_LOST` |
| Attempt lifecycle | `ATTEMPT_STARTED`, `ATTEMPT_RUNNING`, `ATTEMPT_SUCCEEDED`, `ATTEMPT_FAILED`, `ATTEMPT_CANCELLED`, `ATTEMPT_SUSPENDED`, `ATTEMPT_STEERED`, `ATTEMPT_LOST` |
| Admission / command request | `USER_INPUT_ACCEPTED`, `STEER_REQUESTED`, `RETRY_REQUESTED`, `REPLAY_REQUESTED`, `CANCEL_REQUESTED`, `RESUME_REQUESTED` |
| Tool / wait | `TOOL_CALL_REQUESTED`, `TOOL_CALL_GOVERNED`, `TOOL_RESULT_ACCEPTED`, `TOOL_AWAITING`, `TOOL_CALLS_BATCH_READY`, `TOOL_CALLS_BATCH_DONE`, `WAIT_LATE_RESULT_REJECTED` |
| Context governance | `CONTEXT_COMPACTION_REQUESTED`, `CONTEXT_COMPACTED`, `CONTEXT_COMPACTION_FAILED`, `CONTEXT_COMPACTION_ATTEMPT_REJECTED` |
| Runner input / usage | `RUNNER_CALL_INPUT_ASSEMBLED`, `RUNNER_CALL_INPUT_ITERATION_LINKED`, `USAGE_REPORTED` |
| Engine / provider diagnostic | `ENGINE_EVENT_REJECTED`, `ENGINE_EVENT_DIAGNOSTIC`, `HOST_LIFECYCLE_DIAGNOSTIC`, `PROVIDER_DIAGNOSTIC`, `PROVIDER_PROTOCOL_ERROR` |
| Preview-only Engine events | `ITERATION_STARTED`, `CONTENT_COMPLETED`, `ITERATION_COMPLETED`, `REASONING_DELTA` |

Exact scan rules before code edits:

```bash
rg -n '_EVENT_TYPE_[A-Z0-9_]+\s*=\s*"|event_type\s*=\s*"|event_type="\w|CONTEXT_COMPACTION_[A-Z_]+\s*=\s*"' dayu/host
rg -n '_host_event_type\(EngineEventType\.|EngineEventType\.[A-Z_]+|event\.type\.value\.upper' dayu/host/engine_ingest.py
rg -n 'event_type\s*=\s*"[^"]*\.|event_type="\w|TYPE_A|TEST_EVENT|host\.test' tests/host
```

Implementation must update the table in the implementation artifact with every production append-path value found by the first two scans. Values found only in tests are not production legal values unless the test proves a real Host append path. Lowercase dotted test values such as `host.test`, `host.artifact.accepted`, and `host.payload.accepted` are arbitrary fixtures and must not be added to the production legal set without a current production append path.

Test fixture migration order:

1. Replace arbitrary event type fixtures before enabling DDL rejection. Generic EventLog / projection tests should use a legal low-risk value such as `USER_INPUT_ACCEPTED` or `RUN_ACCEPTED` according to the tested class filter; lifecycle tests should use the lifecycle value relevant to the assertion.
2. Keep arbitrary values only in tests whose purpose is invalid event-type rejection, and rename them to self-evident illegal values such as `INVALID_TEST_EVENT_TYPE`.
3. Then add owner parser / serializer, update `EventLogAppendRequest` validation and row decoder, and finally add fresh-schema DDL `CHECK`.
4. Add invalid append and mutated-row decoder tests after the DDL / decoder closure exists.

Known fixture hotspots from current scan:

| Arbitrary value | Current hotspot | Migration direction |
|---|---|---|
| `TYPE_A` | `tests/host/test_event_log_store.py`, `tests/host/test_projection_runner.py`, `tests/host/test_projection_checkpoint.py`, `tests/host/test_durable_concurrency_matrix.py`, `tests/host/test_public_event_stream.py`, `tests/host/test_durable_schema.py` | Use `USER_INPUT_ACCEPTED` for generic canonical rows unless the assertion requires a more specific lifecycle value. |
| `host.test` | `tests/host/test_event_log_store.py` helper default | Use `USER_INPUT_ACCEPTED`; add separate invalid rejection case with `INVALID_TEST_EVENT_TYPE`. |
| `TEST_EVENT` | `tests/host/test_durable_connection.py`, `tests/host/test_durable_transaction.py`, `tests/host/test_state_schema.py`, `tests/host/test_purge_session.py`, `tests/host/test_wait_record_state.py` | Use `USER_INPUT_ACCEPTED` for generic durable rows or the lifecycle value asserted by the test. |
| lowercase dotted storage fixtures | `tests/host/test_artifact_store.py`, `tests/host/test_storage_orphan_proof.py`, `tests/host/test_payload_store.py` | Use a legal Host event type while keeping storage-specific ids / refs unchanged. |

#### 3.8.2 Queue Policy Baseline

`RunQueuePolicy` legal values are exactly:

- `queue`
- `reject`
- `attach_active`

Implementation order:

1. Add `dayu/host/queue_policy.py` with `RunQueuePolicy`, parser, serializer, and legal-value helper.
2. Update `dayu/host/admission.py` to import and consume `RunQueuePolicy`.
3. Delete `AdmissionPolicy`; do not alias, re-export, or keep a facade.
4. Update public request validation / durable row validation and add `host_runs.queue_policy` fresh-schema `CHECK`.
5. Run residual scans:

```bash
rg -n 'AdmissionPolicy' dayu tests
rg -n 'RunQueuePolicy\s*=|AdmissionPolicy\s*=|from dayu\.host\.admission import AdmissionPolicy' dayu tests
```

Both scans must prove there is no production `AdmissionPolicy` reference and no compatibility re-export.

#### 3.8.3 Idempotency Validation Strategy

P3-J chooses Python-level typed validation only and intentionally omits DDL `CHECK` for idempotency scope / result kind.

Current production baseline for tests and owner helpers:

| Kind | Current values |
|---|---|
| Scope | `ensure_session`, `create_session`, `close_session`, `start_run`, `submit_followup_queue`, `submit_followup_steer`, `retry_run`, `replay_run`, `cancel_run`, `cancel_session_runs`, `tool_fact_accept`, `tool_awaiting_accept`, `wait_resolution`, `wait_late_rejection`, `purge_session` |
| Result | `session`, `run`, `tool_fact_accept_ack`, `tool_awaiting_accept_ack`, `wait_resolution`, `wait_late_rejection_diagnostic`, `purge_tombstone` |

Tests must assert:

- constructors / store insert paths reject unknown typed values before write;
- row decoder rejects manually-mutated unknown values if the implementation exposes typed records;
- fresh schema still has no `scope_kind IN (...)` or `result_kind IN (...)` DDL `CHECK`;
- adding a new Host command kind requires updating the Python owner and its tests, not schema DDL.

#### 3.8.4 Descriptor Kind Baseline

Current descriptor kind legal values:

| Descriptor kind | Owner / producer |
|---|---|
| `tool_call_arguments_json` | ToolRuntime accepted tool-call argument payload descriptor |
| `tool_call_semantic_query_text` | ToolRuntime readable semantic query payload descriptor |
| `runner_call_input_manifest` | RunInputBuilder / Engine ingest / compaction operation runner-call manifest descriptor |
| `runner_call_input_projection` | RunInputBuilder / Engine ingest LLM-facing input projection descriptor |
| `selected_tool_schema_snapshot` | RunInputBuilder selected tool schema snapshot descriptor |
| `compactor_input_projection` | Compaction operation compactor input projection descriptor |
| `compaction_rejected_attempt_diagnostic` | Compaction operation diagnostic descriptor for rejected compaction attempts |

Implementation order:

1. Add descriptor-kind owner helpers next to the existing schema constants.
2. Update payload producer helpers to write descriptor metadata through the owner and reject unknown descriptor kinds before write.
3. Update `payload_resolution` only to parse expected kinds and fail closed on missing / mismatched descriptor metadata for the expected descriptor. It must not maintain an independent all-known-kind list.
4. Add tests for producer-side unknown-kind rejection and consumer-side expected-kind mismatch separately.

## 4. Current Code Direct Evidence And Source Finding Disposition

Disposition counts by source item plus split subfinding:

- `accepted`: 6
- `rejected-with-reason`: 6
- `deferred-with-owner`: 1
- `needs-more-evidence`: 0

### AgentDS 5 - Memory Snapshot Upsert Has No Version / Staleness Detection

Disposition: `rejected-with-reason`.

Current evidence:

- `dayu/host/durable/memory.py:655-679` still uses `ON CONFLICT(snapshot_id) DO UPDATE`.
- `dayu/host/memory.py:1091-1112` still derives stable snapshot id from `(session_id, consumer_id, policy_digest)`.
- However current snapshot schema includes cursor fields: `dayu/host/memory.py:245-275`, `dayu/host/memory.py:883-935`, and `dayu/host/durable/schema.py:905-924`.
- `dayu/host/durable/memory.py:701-725` writes memory snapshot and advances projection checkpoint in one transaction.
- `dayu/host/run_input.py:1059-1096` checks required cursor, lag, ahead state, and inline repair before exposing memory to LLM input.
- `dayu/host/run_input.py:1098-1138` converts missing / damaged snapshot reads to `MemoryProjectionRepairRequired`.
- `dayu/host/run_input.py:1140-1177` verifies snapshot cursor points to the actual EventLog row and session.
- `dayu/host/run_input.py:3075-3090` compares latest compact ref and memory ref before building the combined input.
- Tests already cover missing / damaged / lag / future snapshot behavior in `tests/host/test_run_input_builder.py:2566`, `2570`, `2962`, `2994`, `3515`, `3531`, `3547`.

Reasoning:

- The source finding's original failure claim was that RunInputBuilder cannot detect stale memory. Current code has cursor, checkpoint, digest, missing/damaged/ahead/lag checks and repair-required behavior.
- Upsert is a storage strategy, not itself a current correctness defect, because the stable row carries a cursor and the LLM-facing consumer checks freshness before use.
- No P3-J implementation slice should add append-only memory history or broad snapshot versioning without new direct failure evidence.

### AgentDS 20 - `_LEGACY_CONFIG_FILES` Compatibility Fossil Has No Owner / Expiry

Disposition: `accepted`.

Current evidence:

- `dayu/runtime/config_loader.py:27-29` defines `_LEGACY_CONFIG_FILES = {"llm_models.json", "run.json"}`.
- `dayu/runtime/config_loader.py:896-903` exposes `legacy_config_file_names()` as a public runtime function.
- `dayu/cli/commands/init.py:26` imports `legacy_config_file_names()` and `dayu/cli/commands/init.py:213-218` uses it to reject legacy assets.
- `tests/runtime/test_config_loader.py:795-806` uses the public function to assert legacy files are not read.
- Host design states current config schema does not keep old `llm_models.json` / `run.json` compatibility paths.

Implementation direction:

- Remove legacy filename exposure from `dayu.runtime.config_loader`.
- If CLI still needs a fail-closed init guard, move the legacy filename set into `dayu/cli/commands/init.py` as a CLI-local guard with tests.
- Tests should use current config filenames from `config_file_names()` and direct current-schema assertions; they must not keep a runtime public helper solely for old names.

### SS-1 - EventLog `event_type` Is Naked String Without Closed-Set Validation

Disposition: `accepted`.

Current evidence:

- `dayu/host/durable/event_log.py:62-90` has `EventLogAppendRequest.event_type: str`.
- `dayu/host/durable/event_log.py:104-137` has `EventLogRow.event_type: str`.
- `dayu/host/durable/event_log.py:1123-1128` validates only non-empty event type text.
- `dayu/host/durable/schema.py:312-345` defines `event_log.event_type TEXT NOT NULL` with no legal-set `CHECK`.
- Event type constants remain distributed, for example:
  - lifecycle owner has run / attempt enums in `dayu/host/lifecycle_events.py:17-93`.
  - admission defines event type constants in `dayu/host/admission.py:147-153`.
  - run transition defines event type constants in `dayu/host/durable/run_transition.py:94-103`.
  - context events define context event constants in `dayu/host/context_events.py:23-32`.
  - tool trace / read API keep local event type sets in `dayu/host/tool_trace.py:90-105` and `dayu/host/read_api.py:97-113`.
- Existing tests rely on arbitrary event types such as `TYPE_A`, `host.test`, and `TEST_EVENT` in `tests/host/test_event_log_store.py` and `tests/host/test_state_schema.py`, proving the durable store currently accepts non-production event names.

Implementation direction:

- Add a single Host EventLog legal-set owner and route all production event type values through it.
- Add Python validation and fresh-schema `CHECK`.
- Update tests to use real legal event types or lower-level fixtures that explicitly test invalid event rejection.

### SS-2 - `execution_target` / `queue_policy` Are Naked Strings

Disposition:

- `queue_policy`: `accepted`.
- `execution_target`: `deferred-with-owner`.

Current evidence:

- Public request shape still has `StartRunRequest.execution_target: str` and `queue_policy: str` in `dayu/host/api.py:1780-1818`.
- `RunRow.execution_target` and `RunRow.queue_policy` are strings in `dayu/host/durable/state.py:260-286`.
- `run_row_from_host_row()` decodes both as required text only in `dayu/host/durable/state.py:1229-1230`.
- `_validate_run_for_insert()` only checks both fields are non-empty in `dayu/host/durable/state.py:5237-5238`.
- `host_runs.execution_target` and `host_runs.queue_policy` have no `CHECK` in `dayu/host/durable/schema.py:490-491`.
- `AdmissionPolicy` already expresses the `queue_policy` legal set in `dayu/host/admission.py:179-184`, and `_parse_admission_policy()` validates `queue`, `reject`, and `attach_active` in `dayu/host/admission.py:3423-3434`.

Reasoning:

- `queue_policy` has a provable Host-owned legal set and should be moved to a typed public / durable owner with DDL coverage.
- `execution_target` is an already-resolved deployment target id. Current design does not define a global closed set, and tests use varied target ids such as `projection-target`, `target-ingest`, and `local-default`. A DDL closed set would invent deployment semantics not present in the design source.

Deferred owner for `execution_target`:

- Service / composition root execution configuration owns the legal catalog of execution targets if a future work unit wants closed-set target validation.
- P3-J must keep Host validation to non-empty resolved target text and must not add a hard-coded target catalog.

### SS-3 - `RunResultRow.terminal_status` Stores `str` Rather Than `RunStatus`

Disposition: `accepted`.

Current evidence:

- `RunResultRow.terminal_status: str` is defined in `dayu/host/durable/read_model.py:43-62`.
- `_validate_run_result()` calls `_terminal_status_from_text()` but keeps the row field as text in `dayu/host/durable/read_model.py:313-324`.
- `_run_result_from_host_row()` validates through `_terminal_status_from_text()` and immediately serializes back to `.value` in `dayu/host/durable/read_model.py:400-405`.
- `_terminal_status_from_text()` already returns a typed `RunStatus` and rejects invalid or non-terminal values in `dayu/host/durable/read_model.py:454-468`.
- DDL already has terminal status `CHECK` in `dayu/host/durable/schema.py:848-854`.

Implementation direction:

- Change the Python row surface to carry `RunStatus` at the durable read-model boundary.
- Provide one serializer for SQLite writes and for public text where text is required.
- Update consumers and tests that compare string status to consume `.value` only at presentation / public JSON boundaries.

### SS-4 - `host_run_results` Projection Lacks Expiry Coordination

Disposition: `rejected-with-reason`.

Current evidence:

- `insert_run_result_if_absent()` is insert-only by design and documents why it does not replace terminal identity in `dayu/host/durable/read_model.py:138-161`.
- Same terminal event replay returns duplicate; different terminal event for the same run raises `HostDurableError` in `dayu/host/durable/read_model.py:153-161`.
- `MinimalReadModelProjection.apply_event()` projects terminal results only for terminal event types from `run_status_for_terminal_event()` in `dayu/host/read_model.py:116-142`.
- Repair can reset and rebuild read model rows from EventLog, as tested in `tests/host/test_projection_read_model.py:980-1088`.
- Repair failure preserves checkpoint and resumes from last committed checkpoint, as tested in `tests/host/test_projection_read_model.py:1200-1250`.

Reasoning:

- A terminal Run result is immutable once committed. Insert-only behavior is the owner-level invariant, not a stale projection defect.
- P3-A closed terminal source-of-truth work; P3-J should not reopen lifecycle terminal semantics without new direct current-code evidence.

### SS-6 - `scope_kind` / `result_kind` Are Naked Strings

Disposition: `accepted`.

Current evidence:

- `IdempotencyScope.scope_kind: str`, `IdempotencyResultRef.result_kind: str`, and `IdempotencyRecord.result_kind: str` are defined in `dayu/host/durable/idempotency.py:29-80`.
- Validation only checks non-empty text in `dayu/host/durable/idempotency.py:234-255`.
- DDL has `scope_kind TEXT NOT NULL` and `result_kind TEXT NOT NULL` with no `CHECK` in `dayu/host/durable/schema.py:363-372`.
- Production legal values are visible in current code:
  - admission operations and result kinds in `dayu/host/admission.py:161-169`.
  - waiting scopes and result kinds in `dayu/host/waiting.py:122-131`.
  - purge scope and result kind in `dayu/host/durable/purge.py:66-72`.
  - session lifecycle operations and session result kind in `dayu/host/durable/session_lifecycle.py:63-69`.

Implementation direction:

- Add typed idempotency scope / result kind owners in the idempotency durable module.
- Convert production callers to typed values.
- P3-J must use Python-level typed validation only and must not add fresh-schema `CHECK` for `scope_kind` / `result_kind`.
- Reason: current values are Host operation-driven and extend with new Host commands, wait operations, or tool operations; making them DDL-closed would turn ordinary Host command extension into schema migration work without proving a stronger durable invariant.
- Tests must assert constructor / insert / row-decoder rejection for illegal typed values and also assert fresh schema does not introduce `scope_kind IN (...)` or `result_kind IN (...)` DDL `CHECK`.

### SS-7 - Descriptor Kind Constants Are Naked Strings

Disposition: `accepted`.

Current evidence:

- Descriptor kind constants live as raw strings in `dayu/host/durable/schema.py:206-261`.
- Payload descriptor metadata is generic JSON in `dayu/host/durable/schema.py:286-306`.
- Payload descriptor writes accept untyped `metadata: Mapping[str, JsonValue]` in `dayu/host/durable/payload.py:68-89` and `dayu/host/durable/payload.py:430-461`.
- `payload_resolution` validates descriptor kind by reading `metadata.get("descriptor_kind")` and comparing with expected string in `dayu/host/payload_resolution.py:331-339`.
- Producers set descriptor kind through literal metadata dicts in `dayu/host/tool_runtime.py`, `dayu/host/run_input.py`, `dayu/host/engine_ingest.py`, and `dayu/host/compaction_operation.py`.

Implementation direction:

- Introduce a typed descriptor kind owner.
- Payload writer metadata should be constructed through a helper that writes `descriptor_kind` from the typed owner and rejects unknown descriptor kinds before write.
- `payload_resolution` should parse the caller-provided expected descriptor kind and fail closed only when descriptor metadata is missing or mismatched for that expected kind.
- `payload_resolution` must not maintain an all-known descriptor-kind registry or become a second global owner for unknown descriptor rejection.

### SS-8 - `HostRow` Uses Column Strings

Disposition: `rejected-with-reason`.

Current evidence:

- `HostRow` stores `columns: tuple[str, ...]` and `values: tuple[SQLiteScalar, ...]` in `dayu/host/durable/transaction.py:102-124`.
- `_build_host_row()` derives column names from `cursor.description` in `dayu/host/durable/transaction.py:473-483`.
- Row decoder helpers already fail closed on missing columns and invalid types, for example `dayu/host/durable/state.py:894-1043`.
- Individual durable row decoders document `HostRowDecodeError` fail-closed behavior, for example `run_row_from_host_row()` in `dayu/host/durable/state.py:1186-1192`.

Reasoning:

- This is a generic internal row representation, not a business semantic owner.
- Replacing all column strings with generated row schemas would be a whole-store rewrite and is explicitly out of P3-J scope.
- Accepted slices may add typed decoding for specific high-value fields, but must not introduce a generic ORM or broad HostRow replacement.

### SS-9 - `metadata_json` Is Opaque JSON Blob

Disposition: `rejected-with-reason`.

Current evidence:

- `SessionRow.metadata_json` and `SessionSlotRow.metadata_json` are durable strings in `dayu/host/durable/state.py:222-243`.
- Public input metadata is typed as `tuple[HostMetadataEntry, ...]` in `dayu/host/api.py:1329-1348`, `dayu/host/api.py:1639-1665`, and `dayu/host/api.py:1678-1719`.
- `HostMetadataEntry` docstring explicitly states metadata is neutral and cannot carry explicit request fields.
- `session_lifecycle` canonicalizes metadata JSON and digest through `_metadata_json()` / `_metadata_digest()` in `dayu/host/durable/session_lifecycle.py:450-480`.
- Tests enforce metadata does not become a per-run escape hatch and rejects empty metadata keys in `tests/host/test_public_contracts.py:828-846` and `tests/host/test_public_contracts.py:1105-1116`.

Reasoning:

- Current code has a public typed metadata entry boundary and canonical JSON persistence. The finding does not show a concrete public / LLM-facing wrong semantic path.
- Do not replace neutral metadata with a bespoke schema unless a future work unit defines a specific metadata semantic owner.

### SS-11 - Memory Snapshot Digest Double-Write

Disposition: `rejected-with-reason`.

Current evidence:

- The memory snapshot row stores `snapshot_digest` and `snapshot_json` in `dayu/host/durable/schema.py:905-918`.
- The snapshot object also carries `snapshot_digest` in `dayu/host/memory.py:883-915`.
- `_snapshot_with_digest()` computes the digest from canonical snapshot content and writes it back in `dayu/host/memory.py:2236-2261`.
- `_snapshot_json_value(..., include_digest=True)` includes digest in serialized JSON, while `_snapshot_digest_json_value()` excludes it from the canonical digest input in `dayu/host/memory.py:2264-2305`.
- The durable integrity scanner compares canonical digest, JSON embedded digest, and row digest in `dayu/host/durable/memory.py:1395-1406`.

Reasoning:

- This is intentional storage-level integrity redundancy. Current code uses the duplication to detect row / JSON mismatch.
- Removing one copy would reduce corruption detection and is not justified by a current semantic drift failure.

### SS-12 - Legacy `verified_fact` Special Case

Disposition: `rejected-with-reason`.

Current evidence:

- Fresh schema only allows current memory item kinds and excludes `verified_fact` in `dayu/host/durable/schema.py:930-941`.
- The integrity scanner reports old `verified_fact` rows as unsupported in `dayu/host/durable/memory.py:1440-1472`.
- Snapshot row read validation rejects old or unknown item kinds in `dayu/host/durable/memory.py:1520-1555`.

Reasoning:

- The old kind is not accepted by fresh schema. The remaining branch is fail-closed diagnostic / corruption detection, not compatibility reading.
- Project policy forbids old database compatibility migration unless explicitly requested. P3-J must not add migration or compatibility support here.

## 5. Implementation Slices

The fixed plan uses 4 implementation slices. This intentionally exceeds the small-cleanup default upper bound of 3 because controller-accepted finding P3-J-PF-01 proves the former S1 coupled three different owner closures and made the first event-type slice too broad. The extra gate cost is justified by the control-doc slice principles: EventLog DDL rejection has independent schema/test-fixture blast radius; queue policy and RunResult terminal status have separate owner boundaries; idempotency / descriptor kind touches admission and payload producers; legacy config cleanup is runtime/CLI rather than Host durable schema. Four slices keep each review focused on one failure / rollback surface and avoid a single implementation agent carrying all schema churn at once.

No slice is allowed to implement broad whole-store migration, old DB compatibility reads, downstream special-case branches, test-fixture masking, cross-layer reverse dependencies, or generic ORM / HostRow replacement.

### S1 - EventLog Event Type Append / Decoder / Fresh-Schema Closure

Purpose:

- Create a code-generation-ready Host EventLog event-type legal set while preserving lifecycle categories.
- Reject invalid event types at append request validation, row decoding, and fresh-schema DDL.
- Migrate arbitrary EventLog test fixtures before DDL rejection is enabled.

Allowed files / modules:

- `dayu/host/lifecycle_events.py`
- `dayu/host/durable/event_log.py`
- `dayu/host/durable/schema.py`
- Production append-path modules only when needed to pass typed values into `EventLogAppendRequest`:
  - `dayu/host/admission.py`
  - `dayu/host/durable/run_transition.py`
  - `dayu/host/context_events.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/tool_runtime.py`
  - `dayu/host/waiting.py`
  - `dayu/host/durable/session_lifecycle.py`
  - `dayu/host/compaction_operation.py`
  - `dayu/host/run_input.py`
- Tests with arbitrary EventLog fixture types or EventLog schema assertions:
  - `tests/host/test_lifecycle_events.py`
  - `tests/host/test_event_log_store.py`
  - `tests/host/test_projection_runner.py`
  - `tests/host/test_projection_checkpoint.py`
  - `tests/host/test_durable_concurrency_matrix.py`
  - `tests/host/test_durable_schema.py`
  - `tests/host/test_state_schema.py`
  - `tests/host/test_durable_connection.py`
  - `tests/host/test_durable_transaction.py`
  - `tests/host/test_public_event_stream.py`
  - storage fixture tests only if their arbitrary lowercase event type hits the DDL check.

Concrete allowed changes:

- Extend `dayu/host/lifecycle_events.py` into the single category-preserving EventLog type owner described in 3.1 and 3.8.1.
- Add owner helpers for parse / serialize / full legal values / category legal values.
- Update `EventLogAppendRequest` validation and `EventLogRow` decoding to reject unknown event types through the owner. Text may remain the persisted SQLite representation; typed parsing must happen before returning a valid row.
- Add fresh-schema `event_log.event_type CHECK (...)` generated from `all_host_event_type_values()`.
- Migrate arbitrary test event types according to 3.8.1 before enabling DDL rejection.
- Add invalid append and mutated-row decoder tests.

Non-goals:

- No queue policy change, no RunResult terminal-status change, no idempotency change, no descriptor-kind change.
- No consumer-wide redirection of every local event-type comparison. Redirect only code that must compile or pass typed append / row-decoder validation.
- No closed set for EventLog payload schema.
- No old database migration.

Stop conditions:

- Stop if source scan finds a production append path whose event type is intentionally open-ended by design.
- Stop if the legal-set table cannot be made exhaustive without changing Host design sources.
- Stop if adding DDL `CHECK` would require broad consumer redirection unrelated to invalid write rejection.

Tests / validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_lifecycle_events.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_durable_schema.py -q
pytest tests/host/test_state_schema.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_public_event_stream.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Additional source scans:

```bash
rg -n '_EVENT_TYPE_[A-Z0-9_]+\s*=\s*"|event_type\s*=\s*"|event_type="' dayu/host tests/host
rg -n 'TYPE_A|TEST_EVENT|host\.test|event_type\s*=\s*"[^"]*\.' tests/host dayu/host
```

README trigger check:

- `dayu/host/README.md` must be checked because EventLog durable schema semantics change.
- `tests/README.md` must be checked if the fixture migration changes durable/projection test maintenance guidance.

Completion report format:

- `slice`: `S1`
- `changed files`
- `event type owner structure`
- `production event type table after scan`
- `fixture migration summary`
- `DDL CHECK status`
- `tests run`
- `pyright result`
- `README decision`
- `source scans`
- `residual risks`

### S2 - Queue Policy Owner And RunResult Terminal Row Surface

Purpose:

- Make `queue_policy` a single Host-owned typed contract with fresh-schema DDL rejection.
- Delete `AdmissionPolicy` rather than aliasing it.
- Make `RunResultRow.terminal_status` typed at the durable read-model row boundary.

Allowed files / modules:

- `dayu/host/queue_policy.py`
- `dayu/host/api.py`
- `dayu/host/admission.py`
- `dayu/host/durable/state.py`
- `dayu/host/durable/run_transition.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/read_model.py`
- Tests:
  - `tests/host/test_admission_queue.py`
  - `tests/host/test_public_run_api.py`
  - `tests/host/test_state_schema.py`
  - `tests/host/test_durable_schema.py`
  - `tests/host/test_projection_read_model.py`
  - focused tests that compare `RunResultRow.terminal_status` or invalid `queue_policy`.

Concrete allowed changes:

- Add `RunQueuePolicy` owner with exactly `queue`, `reject`, `attach_active`.
- Change request / durable validation to parse through the owner and serialize only at SQLite / public JSON text boundaries.
- Delete `AdmissionPolicy` and update admission code to consume `RunQueuePolicy` directly.
- Add `host_runs.queue_policy CHECK (...)`.
- Leave `execution_target` as non-empty resolved deployment target text.
- Change `RunResultRow.terminal_status` to `RunStatus` and use one serializer for SQLite / public text. Keep the existing `host_run_results.terminal_status` DDL `CHECK`.

Non-goals:

- No event-type owner edits except incidental imports left by S1.
- No idempotency `_OPERATION_*` or result-kind refactor in `admission.py`; those belong to S3.
- No compatibility alias, wrapper, or re-export for `AdmissionPolicy`.
- No closed set for `execution_target`.

Stop conditions:

- Stop if source scan finds production consumers importing `AdmissionPolicy` outside `dayu/host/admission.py`; report the consumer and owner decision instead of aliasing.
- Stop if queue policy typing requires public API semantics beyond the three existing values.

Tests / validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_admission_queue.py tests/host/test_public_run_api.py tests/host/test_state_schema.py tests/host/test_durable_schema.py tests/host/test_projection_read_model.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Additional source scans:

```bash
rg -n 'AdmissionPolicy' dayu tests
rg -n 'queue_policy="[^"]+"|queue_policy = "[^"]+"' dayu/host tests/host
```

README trigger check:

- `dayu/host/README.md` must be checked because Host public request / durable run row queue policy contract changes.
- `tests/README.md` must be checked if new queue-policy test guidance is added.

Completion report format:

- `slice`: `S2`
- `changed files`
- `queue_policy owner`
- `AdmissionPolicy deletion scan`
- `terminal_status row surface`
- `tests run`
- `pyright result`
- `README decision`
- `source scans`
- `residual risks`

### S3 - Idempotency And Descriptor Kind Weak-Contract Closure

Purpose:

- Add Python-level typed validation for idempotency scope / result kind without DDL `CHECK`.
- Add typed descriptor-kind producer validation and expected-kind consumer validation.
- Keep `admission.py` sequencing clean: only idempotency constants move here, never S2 queue-policy owner work.

Allowed files / modules:

- `dayu/host/durable/idempotency.py`
- `dayu/host/admission.py`
- `dayu/host/durable/session_lifecycle.py`
- `dayu/host/waiting.py`
- `dayu/host/tool_runtime.py`
- `dayu/host/durable/purge.py`
- `dayu/host/durable/schema.py`
- `dayu/host/durable/payload.py`
- `dayu/host/payload_resolution.py`
- Descriptor producers:
  - `dayu/host/run_input.py`
  - `dayu/host/engine_ingest.py`
  - `dayu/host/compaction_operation.py`
- Tests:
  - `tests/host/test_idempotency_store.py`
  - `tests/host/test_durable_schema.py`
  - `tests/host/test_payload_store.py`
  - `tests/host/test_purge_session.py`
  - `tests/host/test_wait_record_state.py`
  - `tests/host/test_toolruntime_accept_barrier.py`
  - `tests/host/test_run_input_builder.py`
  - `tests/host/test_engine_ingest_mapping.py`
  - `tests/host/test_compaction_operation.py`
  - `tests/host/test_package_exports.py` only if exported constants change.

Concrete allowed changes:

- Add typed idempotency owner values listed in 3.8.3.
- `IdempotencyScope`, `IdempotencyResultRef`, and decoded `IdempotencyRecord` must validate through the owner or carry typed values.
- Do not add DDL `CHECK` for `scope_kind` or `result_kind`; tests must assert this omission intentionally.
- Add descriptor kind owner helpers for the 3.8.4 baseline.
- Payload metadata producer helpers must write descriptor kind through the owner and reject unknown descriptor kinds before write.
- `payload_resolution` parses the expected descriptor kind and fails closed on missing or mismatched descriptor metadata. Unknown descriptor rejection for all descriptors belongs to producer-side validation, not this consumer.

Non-goals:

- No generic metadata schema migration.
- No typed wrapper for every payload metadata key.
- No purge redesign.
- No idempotency DDL closure.
- No S2 queue-policy or terminal-status refactor.
- No compatibility for rows with old illegal idempotency or descriptor kinds.

Stop conditions:

- Stop if a current idempotency value is produced from an external plugin / non-Host caller not covered by the owner table.
- Stop if a descriptor kind outside 3.8.4 is found on a production producer path; update the owner table or report why it is not a descriptor-kind semantic.

Tests / validation commands:

```bash
source .venv/bin/activate
pytest tests/host/test_idempotency_store.py tests/host/test_durable_schema.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py -q
pytest tests/host/test_toolruntime_accept_barrier.py tests/host/test_run_input_builder.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Additional source scans:

```bash
rg -n 'scope_kind=|result_kind=|_OPERATION_|_IDEMPOTENCY_RESULT_KIND|_WAIT_.*SCOPE_KIND|_WAIT_.*RESULT_KIND|PURGE_IDEMPOTENCY|_TOOL_FACT_ACCEPT_' dayu/host tests/host
rg -n 'descriptor_kind|DESCRIPTOR_KIND|_DIAGNOSTIC_DESCRIPTOR_KIND|metadata=\{' dayu/host tests/host
rg -n 'scope_kind TEXT NOT NULL CHECK|result_kind TEXT NOT NULL CHECK' dayu/host/durable/schema.py
```

README trigger check:

- `dayu/host/README.md` must be checked because Host durable idempotency and payload descriptor contracts may change.
- `tests/README.md` must be checked if test grouping or maintenance guidance changes.

Completion report format:

- `slice`: `S3`
- `changed files`
- `idempotency typed owner and DDL omission evidence`
- `descriptor legal set`
- `producer-side unknown rejection`
- `consumer expected-kind validation`
- `admission.py sequencing confirmation`
- `tests run`
- `pyright result`
- `README decision`
- `source scans`
- `residual risks`

### S4 - Legacy Config Exposure Re-Ownership

Purpose:

- Remove runtime public exposure of removed config file names.
- Preserve only the narrow current-schema guard needed by `dayu-cli init`, if still needed after code audit.

Allowed files / modules:

- `dayu/runtime/config_loader.py`
- `dayu/cli/commands/init.py`
- `tests/runtime/test_config_loader.py`
- `tests/cli/test_init_command.py`
- `tests/host/test_package_exports.py` only if exports are affected.
- `dayu/config/README.md` only if the implementation changes documented config behavior.
- Root `README.md` only if user-visible init/config behavior changes.

Concrete allowed changes:

- Delete `legacy_config_file_names()` from runtime public surface if no current production caller outside CLI needs it.
- Delete `_LEGACY_CONFIG_FILES` from `ConfigLoader` if runtime no longer owns legacy diagnostics.
- Move a private `_LEGACY_CONFIG_FILE_NAMES` or equivalent into `dayu/cli/commands/init.py` only for init asset fail-fast.
  - The CLI guard should apply to top-level copied config assets. It must not create a broad prompt-asset filename ban unless current code already has that intended behavior and tests cover it.
- Update runtime tests so they assert current config files are loaded and old files are ignored by absence from `config_file_names()` / direct current loader behavior, not by importing a legacy public helper.
- Update CLI init tests to assert old files are not generated and, if the guard remains, that old top-level config assets are rejected.

Non-goals:

- No old config compatibility read.
- No workspace migration.
- No changes to current config schema.
- No provider / model config migration.
- No README expansion unless user-visible behavior or documented config responsibilities change.

Stop conditions:

- Stop and report if another production module depends on `legacy_config_file_names()` for a non-CLI runtime diagnostic path.
- Stop if removing the public helper would break a documented public API that design sources still require.

Tests / validation commands:

```bash
source .venv/bin/activate
pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Additional source scans:

```bash
rg -n 'legacy_config_file_names|_LEGACY_CONFIG_FILES|llm_models\\.json|run\\.json' dayu tests docs README.md
```

README trigger check:

- `dayu/config/README.md` must be checked because config loader public behavior changes, but it likely needs no update if it already states old `llm_models.json` / `run.json` are deleted and not read.
- Root `README.md` must be checked only if `dayu-cli init` user-visible behavior or config file list changes. Expected decision: no update if behavior remains "old files are not generated/read".
- `tests/README.md` must be checked only if test command guidance changes.

Completion report format:

- `slice`: `S4`
- `changed files`
- `legacy exposure decision`
- `remaining old-name references and why`
- `tests run`
- `pyright result`
- `README decision`
- `residual risks`

## 6. Explicit Prohibitions

Implementation agents must not:

- Add broad whole-store migrations.
- Add compatibility reads for old DB rows or old config files.
- Add downstream fallback, special-case branches, loose parsing, or test-only shims to mask invalid durable facts.
- Use `hasattr` / `getattr` to avoid typing owner boundaries.
- Put explicit public parameters into metadata / extra payload.
- Introduce reverse dependencies such as runtime importing Host, Host importing Service, or Engine importing Host.
- Replace `HostRow` globally, introduce an ORM, or rewrite the durable store outside accepted fields.
- Change Fins semantic test harness coupling; that belongs to P3-K.
- Reopen P3-A lifecycle terminal-source work or P3-C memory typed-material work without new direct evidence.

## 7. README Checks

Plan artifact creation itself does not require README updates because it only adds this `docs/host/` plan file.

Implementation README checks:

- `dayu/host/README.md`: check in S1, S2, and S3 because `dayu/host/` durable contracts, EventLog semantics, queue policy, idempotency, and descriptor owner boundaries may change.
- `dayu/README.md`: check only if cross-layer boundary wording or public package relationships change. Expected no update for owner-boundary hardening that stays inside Host.
- `dayu/config/README.md`: check in S4 because runtime config loader public helper removal touches config semantics. Expected no update if old files remain deleted / unread and current schema list is unchanged.
- Root `README.md`: check in S4 only if CLI init user-visible behavior changes. Expected no update if behavior remains no old config generation.
- `tests/README.md`: check any slice that adds a new stable command group or changes test maintenance guidance. Expected no update if tests are only added to existing Host / runtime / CLI files.

## 8. Pyright And Affected Test Matrix

Required after each implementation slice:

```bash
source .venv/bin/activate
python -m pyright dayu/ tests/ utils/
git diff --check
```

S1 focused matrix:

```bash
source .venv/bin/activate
pytest tests/host/test_lifecycle_events.py tests/host/test_event_log_store.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_projection_read_model.py -q
pytest tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_durable_connection.py tests/host/test_durable_transaction.py tests/host/test_public_event_stream.py -q
```

S2 focused matrix:

```bash
source .venv/bin/activate
pytest tests/host/test_admission_queue.py tests/host/test_public_run_api.py tests/host/test_state_schema.py tests/host/test_durable_schema.py tests/host/test_projection_read_model.py -q
```

S3 focused matrix:

```bash
source .venv/bin/activate
pytest tests/host/test_idempotency_store.py tests/host/test_durable_schema.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py -q
pytest tests/host/test_run_input_builder.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py -q
```

S4 focused matrix:

```bash
source .venv/bin/activate
pytest tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q
```

Aggregate validation after all accepted slices:

```bash
source .venv/bin/activate
pytest tests/host/test_lifecycle_events.py tests/host/test_event_log_store.py tests/host/test_projection_runner.py tests/host/test_projection_checkpoint.py tests/host/test_durable_schema.py tests/host/test_state_schema.py tests/host/test_projection_read_model.py tests/host/test_admission_queue.py tests/host/test_public_run_api.py tests/host/test_idempotency_store.py tests/host/test_payload_store.py tests/host/test_purge_session.py tests/host/test_wait_record_state.py tests/host/test_run_input_builder.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_engine_ingest_mapping.py tests/host/test_compaction_operation.py tests/runtime/test_config_loader.py tests/cli/test_init_command.py -q
python -m pyright dayu/ tests/ utils/
git diff --check
```

Optional broad Host safety matrix if S1 event-type owner redirection touches many consumers:

```bash
source .venv/bin/activate
pytest tests/host -q
```

## 9. Blocking Open Questions

None for entering implementation. Slice-local stop conditions are:

- S1 must stop if current production EventLog event types cannot be made exhaustive without a design-source update.
- S2 must stop if `AdmissionPolicy` has production consumers outside `admission.py` and deletion would require a broader public-contract decision.
- S3 must stop if idempotency scope / result kind is produced by external non-Host callers not covered by the owner table, or if a descriptor producer writes a kind outside the baseline.

`execution_target` closed-set validation is deferred to the Service / composition-root execution configuration owner. P3-J must not implement it.

## 10. Completion Report Format For Implementation Gate

Each implementation slice must report:

- `artifact path`
- `slice`
- `changed files`
- `owner boundary implemented`
- `source finding dispositions touched`
- `tests run`
- `pyright result`
- `README decision`
- `source scans`
- `residual risks`
- `blocking open questions`

Plan gate completion report:

- artifact path: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`
- plan-fix artifact path: `docs/reviews/wu-semantic-ownership-01-p3-j-plan-fix-codex.md`
- source finding dispositions count: accepted 6, rejected-with-reason 6, deferred-with-owner 1, needs-more-evidence 0
- proposed slices: S1 EventLog Event Type Append / Decoder / Fresh-Schema Closure; S2 Queue Policy Owner And RunResult Terminal Row Surface; S3 Idempotency And Descriptor Kind Weak-Contract Closure; S4 Legacy Config Exposure Re-Ownership
- blocking open questions: none for implementation entry; slice-local stop conditions recorded
- plan-fix files changed: `docs/host/wu-semantic-ownership-01-p3-j-durable-schema-weak-contract-plan.md`, `docs/reviews/wu-semantic-ownership-01-p3-j-plan-fix-codex.md`
