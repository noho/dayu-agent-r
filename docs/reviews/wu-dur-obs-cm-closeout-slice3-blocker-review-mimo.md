# WU-DUR-P01 Slice 3 Blocker Review — AgentMiMo

## verdict

**blocker-accepted**

## evidence checked

### 1. Codex blocker artifact

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-codex.md`

### 2. Plan contract

- `docs/host/wu-dur-obs-cm-closeout-plan.md` Slice 3 section (lines 490-517)
- Allowed files: `dayu/host/llm_compaction.py`, `dayu/host/compact_payload.py`, `dayu/host/compact_artifact.py`, `dayu/host/context_events.py`, `dayu/host/engine_ingest.py`, `tests/host/test_llm_compaction.py`, `tests/host/test_compaction_operation.py`, `tests/host/test_public_compact_smoke.py`

### 3. Design contract (compactor_proposal / manifest / payload)

- `docs/host/design.md:1435` (13.1 Payload): `RUNNER_CALL_INPUT_ASSEMBLED` manifest body uses descriptor kind `runner_call_input_manifest`; compactor LLM proposal input projection uses kind `compactor_input_projection`
- `docs/host/design.md:1506` (13.3 Canonical Event Matrix): `RUNNER_CALL_INPUT_ASSEMBLED` hot payload fields; `CONTEXT_COMPACTED` / `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload fields
- `docs/host/design.md:2575` (23.1 Runner-call Input Assembly Manifest): `RunnerCallInputAssemblyManifest` contract, `CompactorRunnerCallIdentity` required when `runner_call_kind == "compactor_proposal"`
- `docs/host/design.md:1543` (13.3): `TOOL_CALL_REQUESTED` payload contract with `ToolCallArgumentsAtom`

### 4. Production source code (read-only verification)

- `dayu/host/compaction_operation.py` — full read (560 lines)
- `dayu/host/dispatch.py` — lines 1-100, 1130-1260, 1520-1680, 1920-1980
- `dayu/host/llm_compaction.py` — full read (910 lines)
- `dayu/host/context_events.py` — full read (853 lines)
- `dayu/host/durable/schema.py` — grep for `compactor_input_projection` / `COMPACTOR` (no matches); grep for `RUNNER_CALL_INPUT_MANIFEST` (constants present at lines 225-231)

## findings

### F1. Proposal manifest generation point is outside allowed files — confirmed

`run_compaction_operation()` in `compaction_operation.py:113` owns the `attempt_number` counter (line 139) and the proposal loop. `_compact_candidate()` at line 330 calls `compactor.compact(request, cancellation_token)` at line 344. The manifest must be generated at this point because:

- `attempt_number` is only known inside the loop
- The rendered `CompactionRequest` and compactor Engine run id are available here
- The design contract requires the manifest to exist **before** the proposal call

`LLMContextCompactor.compact()` in `llm_compaction.py:197` receives only `CompactionRequest` and `CancellationToken`. It constructs `AgentRunRequest` at line 334 with `attempt_id=None` and `execution_id=None`. It has no access to `attempt_number`, Host transaction, payload store, or artifact root.

**Conclusion**: The manifest cannot be durably generated within allowed files. `llm_compaction.py` could compute manifest *data* (prompts, run id, compact input digest), but cannot write it as a durable payload descriptor or artifact.

### F2. Durable event writes are outside allowed files — confirmed

`_execute_proactive_compaction()` in `dispatch.py:1150` calls `run_compaction_operation()` at line 1170 outside any transaction, then opens a transaction at line 1182 to write result facts:

- `_append_compaction_attempt_rejected_event()` at `dispatch.py:1933` writes `CONTEXT_COMPACTION_ATTEMPT_REJECTED` with no proposal manifest ref parameter
- `_append_compacted_event()` at `dispatch.py:1533` writes `CONTEXT_COMPACTED` with no accepted proposal manifest ref parameter
- `build_context_compacted_payload()` in `context_events.py:249` has no `accepted_proposal_manifest_ref` parameter
- `build_context_compaction_attempt_rejected_payload()` in `context_events.py:514` has no rejected proposal manifest ref parameter

**Conclusion**: Even if manifest data were produced in `llm_compaction.py`, threading it into durable EventLog facts requires modifying `dispatch.py` and `context_events.py`. The `context_events.py` is in allowed files but `dispatch.py` is not.

### F3. Result dataclasses lack manifest ref fields — confirmed

`CompactionOperationResult` at `compaction_operation.py:94` has fields: `accepted_candidate`, `quality_result`, `rejected_attempts`, `failure_reason`, `budget_after_attempted_compact`. No proposal manifest ref field.

`CompactionAttemptRejected` at `compaction_operation.py:72` has fields: `attempt_number`, `failure_category`, `repairable`, `runner_attempt_summary_refs`, `diagnostic_refs`, `next_policy_decision`, `budget_after_attempted_compact`. No proposal manifest ref field.

Threading manifest refs through these dataclasses requires modifying `compaction_operation.py`, which is outside allowed files.

### F4. Schema constant missing — confirmed

`schema.py` has `RUNNER_CALL_INPUT_MANIFEST_DESCRIPTOR_KIND` at line 225 and `RUNNER_CALL_INPUT_MANIFEST_SCHEMA_VERSION` at line 228, but no `compactor_input_projection` descriptor kind constant. `schema.py` is not in the Slice 3 allowed file set.

The design contract at `design.md:1449` specifies: "compactor LLM proposal 输入投影使用 payload descriptor / artifact kind `compactor_input_projection`". A stable constant is needed.

### F5. No alternative path within allowed files

I considered whether `llm_compaction.py` could generate manifest data and return it through a side channel:

- **Extension of `ConversationCompactOutputVNext`**: This is the compact *output* schema, not a manifest carrier. Mixing manifest metadata into compact output violates separation of concerns and the design contract.
- **Module-level registry / global side channel**: Explicitly forbidden by blocker constraints and project coding hard constraints (no global side effects, no hidden state).
- **Returning manifest data from `compact()` as a tuple**: Would change the `ContextCompactor` protocol interface (defined in `compaction.py`), which cascades to `compaction_operation.py` (outside allowed files) and all callers.
- **Generating manifest in `engine_ingest.py`**: `engine_ingest.py` handles Engine event ingestion, not Host governance events. The compactor proposal call is not a Host-admitted Run and does not flow through Engine event pipeline.

**Conclusion**: No production-grade path exists within allowed files. Every approach either requires modifying files outside the allowed set or violates the hard constraints (no fake manifest, no side channel, no preview-only artifact).

### F6. Reslice recommendation evaluation

The codex recommends: "add a production `CompactorProposalManifestRecorder` owned by dispatch/governance, thread proposal manifest refs through `CompactionOperationResult` / `CompactionAttemptRejected`, and extend compact event payload builders with accepted/rejected proposal manifest refs."

This correctly identifies the necessary owner changes:

| File | Required change | Currently allowed? |
|---|---|---|
| `dayu/host/compaction_operation.py` | Add manifest ref fields to `CompactionOperationResult` / `CompactionAttemptRejected`; call manifest generation | No |
| `dayu/host/dispatch.py` | Implement `CompactorProposalManifestRecorder`; thread manifest refs into EventLog writes | No |
| `dayu/host/durable/schema.py` | Add `compactor_input_projection` descriptor kind constant | No |
| `dayu/host/context_events.py` | Extend payload builders with proposal manifest ref parameters | Yes |
| `dayu/host/llm_compaction.py` | Construct manifest data during `AgentRunRequest` build | Yes |

The reslice recommendation is directionally correct but could be more specific about:

1. Whether `CompactorProposalManifestRecorder` should be a new class in `dispatch.py` or a helper in a separate governance module
2. The exact field additions to `CompactionOperationResult` and `CompactionAttemptRejected` (e.g., `accepted_proposal_manifest_ref: str | None`, `proposal_manifest_refs: tuple[str, ...]`)
3. How `attempt_number` reaches the manifest generation point (currently only in `run_compaction_operation` loop)

## recommended next gate

1. **Expand allowed file set** for the resliced Slice 3 to include at minimum: `dayu/host/compaction_operation.py`, `dayu/host/dispatch.py`, `dayu/host/durable/schema.py`
2. **Define exact field additions** to `CompactionOperationResult` and `CompactionAttemptRejected` for proposal manifest refs
3. **Define the `CompactorProposalManifestRecorder` interface**: where it lives, what it receives, how it writes durable manifest
4. **Extend `build_context_compacted_payload()` and `build_context_compaction_attempt_rejected_payload()`** with typed proposal manifest ref parameters
5. **Add `compactor_input_projection` constant** to `schema.py`
6. **Update Slice 3 tests** to assert proposal manifest ref presence in compact events

## ready for controller adjudication

yes
