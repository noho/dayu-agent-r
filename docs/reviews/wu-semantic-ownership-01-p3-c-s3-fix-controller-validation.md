# WU-SEMANTIC-OWNERSHIP-01 P3-C S3 Fix Controller Validation

## Verdict

PASS. `P3-C-S3-CR-F01` is fixed and `P3-C-S3-CR-F02` is correctly rejected as a non-defect.

## Validation Commands

- `source .venv/bin/activate && python -m pytest tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py -q`
  - Result: `227 passed`
- `source .venv/bin/activate && python -m pytest tests/host/test_context_compact_events.py tests/host/test_compaction_contract.py tests/host/test_context_budget.py tests/host/test_compaction_operation.py tests/host/test_llm_compaction.py tests/host/test_compact_material.py tests/host/test_compact_pipeline.py tests/host/test_memory_projection.py tests/host/test_accepted_result_projection.py tests/host/test_run_input_builder.py tests/host/test_tool_trace_projection.py tests/host/test_public_compact_smoke.py -q`
  - Result: `449 passed, 1 skipped`
- `source .venv/bin/activate && python -m pytest tests/host/test_import_boundary.py tests/host/test_weak_typing_guard.py -q`
  - Result: `25 passed`
- `source .venv/bin/activate && python -m pyright dayu/host/evidence.py dayu/host/accepted_result_projection.py dayu/host/memory.py dayu/host/durable/memory.py dayu/host/compact_material.py dayu/host/compact_pipeline.py dayu/host/run_input.py tests/host/test_accepted_result_projection.py tests/host/test_memory_projection.py tests/host/test_compact_material.py tests/host/test_run_input_builder.py`
  - Result: `0 errors, 0 warnings, 0 informations`
- `source .venv/bin/activate && python -m pyright`
  - Result: `0 errors, 0 warnings, 0 informations`
- coverage command for `dayu.host.evidence`, `accepted_result_projection`, `memory`, `durable.memory`, `compact_material`, `compact_pipeline`, and `run_input`
  - Result: total `89.39%`; all files >= 80%

## Source Scans

- canonical import scan: no Host/test consumer imports accepted evidence material, renderer, or fallback text from `accepted_result_projection`.
- old mismatch string / `str(exc)` scan: zero matches.
- old private renderer scan: zero matches.
- consumer envelope re-parse scan in memory, durable memory, compact material, and run input: zero matches.
- Tool Trace diff: empty.
- `git diff --check`: pass.

## Owner Boundary Audit

- Producer: ToolRuntime / Host accept barrier durable facts.
- Projection owner: `accepted_result_projection` converts accepted facts into `AcceptedToolResultProjection`, including `llm_material`.
- LLM material / renderer owner: `dayu.host.evidence`.
- Consumers: durable memory, Conversation Memory, compact material, compact pipeline, and RunInput consume the typed projection/material; they do not parse rendered text or reopen accepted evidence envelopes.
- Persistence and projection remain same-source: durable payload, memory, compact material, fallback RunInput, and LLM-facing text all derive from the same accepted evidence projection and leaf renderer.
