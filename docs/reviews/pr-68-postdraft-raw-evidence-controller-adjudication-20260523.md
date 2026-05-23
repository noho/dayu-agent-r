# PR 68 Post-Draft Raw Evidence Fix Controller Adjudication

Date: 2026-05-23

Gate: Phase 12.5 PR 68 post-draft raw evidence compaction fix

## Verdict

PASS.

Controller accepts the post-draft fix that removes `result_preview` from the active evidence contract and makes compaction fact extraction consume compact-range raw context with Host-minted evidence id anchors.

## Review Inputs

- MiMo review: `docs/reviews/pr-68-postdraft-raw-evidence-review-mimo-20260523.md`
- DS review: `docs/reviews/pr-68-postdraft-raw-evidence-review-ds-20260523.md`

## Adjudication

- `result_preview` deletion: accepted. Active production code, Host tests, `docs/host/design.md`, `dayu/host/README.md`, and `tests/README.md` no longer contain the old contract.
- Raw evidence input: accepted. `TOOL_RESULT_ACCEPTED` persists `raw_tool_outcome`, `collect_compaction_request_evidence_inputs(...)` builds `CompactRawContextItem`, and `LLMContextCompactor` renders `compact_raw_context` with adjacent accepted evidence refs.
- Evidence id authority: accepted. Canonical `evidence_id` remains Host-minted at the accept barrier and LLM compaction can only cite rendered refs.
- Cancellation hardening: accepted. The previous `_NeverCancelledToken` regression remains closed; compaction calls receive Host lifecycle cancellation tokens.
- DS F3 / F4: accepted and fixed in this gate. Added direct tests for missing `raw_tool_outcome` fail-closed behavior and `RUN_SUCCEEDED` assistant conclusion raw context collection.
- DS F1: accepted as residual production hardening. Raw evidence aggregate prompt budget guard belongs to the Context Governance hardening owner; it is not a correctness blocker for deleting preview.
- DS F2: deferred. Current V1 has one evidence id per accepted tool-result item, so item-level multi-evidence disambiguation is not required in this gate.
- DS F5: accepted as non-blocking. The current helper consumes EventLog rows through the existing ordered EventLog read contract; explicit ordering documentation or defensive sorting can be handled with future hardening if that store contract changes.

## Validation

- `pytest tests/host/test_compaction_operation.py -q`: 18 passed
- `pytest tests/host/test_llm_compaction.py tests/host/test_compaction_contract.py tests/host/test_compaction_operation.py tests/host/test_compact_artifact_store.py tests/host/test_toolruntime_accept_barrier.py tests/host/test_toolruntime_executor.py tests/host/test_dispatch_scheduler.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py tests/host/test_run_input_builder.py -q`: 262 passed
- `pyright dayu tests`: 0 errors, 0 warnings, 0 informations
- `git diff --check`: clean

## Residuals

- Raw evidence aggregate prompt budget guard remains a production hardening item.
- Large-session memory rebuild performance remains a production hardening item.
- Real financial tool provider integration must continue to ensure accepted tool results form accepted evidence envelopes without Host interpreting Fins locator semantics.
