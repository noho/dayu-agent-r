# WU-CM-01-F03 Implementation Report - AgentCodex

## Implementation Verdict

ready

## Changed Files

- `dayu/host/terminal_summary_payload.py`
- `dayu/host/_terminal_answer.py`
- `dayu/host/run_input.py`
- `dayu/host/durable/memory.py`
- `dayu/host/memory.py`
- `dayu/host/compaction_evidence.py`
- `tests/host/test_terminal_summary_payload.py`
- `tests/host/test_memory_projection.py`
- `tests/host/test_run_input_builder.py`
- `tests/host/test_compaction_operation.py`
- `tests/host/test_compact_material.py`
- `dayu/host/README.md`

`docs/host/issues-implementation-control.md` was already dirty before implementation and was not modified.

## Key Behavior Changes

- Replaced the old assistant summary helper contract with pure field readers:
  - `PayloadTextReadPolicy`
  - `assistant_final_answer_text_from_run_payload(...)`
  - `terminal_summary_content_text_from_payload(...)`
- Added `_terminal_answer.assistant_final_answer_continuity_text(...)` as the transaction-aware resolver because placing durable payload resolution in `terminal_summary_payload.py` caused an import cycle during test collection.
- Assistant final answer continuity now reads only:
  - non-empty `RUN_SUCCEEDED.final_answer`
  - digest-checked terminal summary artifact `content`
- `RUN_SUCCEEDED.content`, `summary_text`, nested `summary`, payload refs, digests and event ids are not assistant final answer fallback sources.
- Run input and durable memory projection merge hydrated terminal artifact content into transient `final_answer`, not `content`, without rewriting canonical EventLog payload.
- Memory selected assistant items are skipped when no final answer continuity text exists.
- Compaction assistant history / answer material is generated only from final answer continuity.
- Removed the dead run input helper chain:
  - `_successful_run_continuity_messages`
  - `_successful_run_message_pair`
  - `_continuity_message_from_event`

## Validation

Passed:

```bash
source .venv/bin/activate && pytest \
  tests/host/test_terminal_summary_payload.py \
  tests/host/test_memory_projection.py \
  tests/host/test_run_input_builder.py \
  tests/host/test_compaction_operation.py \
  tests/host/test_compact_material.py \
  tests/host/test_engine_ingest_mapping.py
```

Result: `197 passed`.

Passed:

```bash
source .venv/bin/activate && pyright
```

Result: `0 errors, 0 warnings, 0 informations`.

Passed:

```bash
rg -n "assistant_summary_from_payload|PayloadSummaryTextPolicy" dayu tests
rg -n "STRICT_ALLOW_EMPTY|_successful_run_continuity_messages|_successful_run_message_pair|_continuity_message_from_event" dayu tests
```

Result: no matches.

Checked:

```bash
rg -n "summary_text" dayu/host/run_input.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compaction_evidence.py
```

Result: remaining matches are accepted compact Session Summary, snapshot JSON, compact candidate reading, or user/evidence ref fallback helpers; no assistant final answer fallback path reads `summary_text`.

## README Decision

- Updated `dayu/host/README.md` because it still described old terminal summary / assistant summary continuity semantics.
- Did not update `tests/README.md`; inspected matches describe broad test coverage and do not contradict the new implementation.

## Residual Risks / Open Questions

- No blocking open questions.
- `_terminal_answer.py` exists only because the transaction-aware resolver would create an import cycle inside `terminal_summary_payload.py`; this is an implementation boundary choice, not a compatibility seam.
