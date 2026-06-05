# WU-DUR-P01 Slice 3 Implementation - Codex

## status

blocker

## changed files

- `docs/reviews/wu-dur-obs-cm-closeout-slice3-implementation-codex.md`

No production code was changed.

## direct evidence

Slice 3 requires a production runner-call manifest before the compactor proposal call and requires accepted/rejected compact events to reference the proposal manifest.

The actual proposal attempt loop is in `dayu/host/compaction_operation.py`, which is outside the allowed file set:

- `run_compaction_operation()` owns `attempt_number` and calls `_compact_candidate()` inside the proposal loop (`dayu/host/compaction_operation.py:113`, `dayu/host/compaction_operation.py:139`, `dayu/host/compaction_operation.py:172`).
- `_compact_candidate()` is the direct call to `compactor.compact(request, cancellation_token)` (`dayu/host/compaction_operation.py:332`, `dayu/host/compaction_operation.py:344`).

The durable write owner for compact accepted / rejected EventLog facts is `dayu/host/dispatch.py`, also outside the allowed file set:

- `_execute_proactive_compaction()` calls `run_compaction_operation()` outside the transaction, then opens a new transaction to write compact result facts (`dayu/host/dispatch.py:1150`, `dayu/host/dispatch.py:1170`, `dayu/host/dispatch.py:1182`).
- Rejected attempts are appended in dispatch from `result.rejected_attempts` (`dayu/host/dispatch.py:1205`, `dayu/host/dispatch.py:1933`, `dayu/host/dispatch.py:1967`).
- Accepted `CONTEXT_COMPACTED` is appended in dispatch and currently has no parameter for accepted proposal manifest ref (`dayu/host/dispatch.py:1242`, `dayu/host/dispatch.py:1540`, `dayu/host/dispatch.py:1618`).

`dayu/host/llm_compaction.py` cannot produce the required durable manifest by itself:

- `LLMContextCompactor.compact()` receives only `CompactionRequest` and `CancellationToken`, and returns only `ConversationCompactOutputVNext` (`dayu/host/llm_compaction.py:197`).
- It builds and runs the Engine request without a durable transaction, payload store, artifact root, operation id, or proposal attempt number (`dayu/host/llm_compaction.py:212`, `dayu/host/llm_compaction.py:216`, `dayu/host/llm_compaction.py:334`).
- The compactor Engine request is intentionally not a Host admitted Run: `attempt_id=None`, `execution_id=None`, and an internal `context-compactor-*` run id (`dayu/host/llm_compaction.py:334`, `dayu/host/llm_compaction.py:337`).

The compact event payload builders currently do not accept proposal manifest refs:

- `build_context_compacted_payload()` has no accepted proposal manifest ref parameter (`dayu/host/context_events.py:252`, `dayu/host/context_events.py:285`).
- `build_context_compaction_attempt_rejected_payload()` accepts runner summary refs and diagnostic refs, but the operation result does not carry manifest refs to pass here (`dayu/host/context_events.py:514`, `dayu/host/context_events.py:540`).

The stable descriptor kind required by design is also not present in the schema constants available to this gate:

- `dayu/host/durable/schema.py` has `runner_call_input_manifest` constants, but no `compactor_input_projection` descriptor kind constant (`dayu/host/durable/schema.py:225`, `dayu/host/durable/schema.py:228`, `dayu/host/durable/schema.py:231`).
- `dayu/host/durable/schema.py` is not in the Slice 3 allowed file set.

## blocker reason

The Slice 3 exact changes cannot be implemented production-grade within the allowed files.

Required production data flow crosses files explicitly disallowed for editing:

1. The proposal manifest must be generated before each proposal call, at the point where `attempt_number`, `CompactionRequest`, compactor Engine run id, and rendered prompt messages are known. That point is `dayu/host/compaction_operation.py` plus the `LLMContextCompactor` request construction path.
2. The manifest must be durable and referenced by accepted/rejected compact facts. Durable EventLog writes and compact result fact assembly occur in `dayu/host/dispatch.py`.
3. `CONTEXT_COMPACTED` and `CONTEXT_COMPACTION_ATTEMPT_REJECTED` payload contracts need typed manifest refs so accepted/rejected attempts can reference their proposal manifests. That requires changing the data carried by `CompactionOperationResult` / `CompactionAttemptRejected` and the dispatch event append calls.
4. The `compactor_input_projection` descriptor kind needs a single truth source. Adding it properly belongs in `dayu/host/durable/schema.py`, which is not allowed in this gate.

Implementing only in `llm_compaction.py` would require a test-private bridge, global side channel, fake manifest, or non-durable preview-only artifact. That would violate the hard constraints: no fake manifest, analyzer must not rerun material selection, and accepted/rejected compact events must reference durable proposal manifest refs.

## tests / pyright / diff-check

- Required pytest: not run because no code implementation was made.
- `pyright`: not run because no code implementation was made.
- `git diff --check`: run after writing this artifact; result recorded in final response.

## README sync

No README update. Stable behavior did not change.

## remaining risks

- Slice 3 remains unimplemented until the allowed file set is expanded to include at least `dayu/host/compaction_operation.py`, `dayu/host/dispatch.py`, and likely `dayu/host/durable/schema.py`.
- Recommended reslice: add a production `CompactorProposalManifestRecorder` owned by dispatch/governance, thread proposal manifest refs through `CompactionOperationResult` / `CompactionAttemptRejected`, and extend compact event payload builders with accepted/rejected proposal manifest refs.

## ready for code review

no
