# WU-CM-06-S1 Implementation Report

## Scope

- Work unit: WU-CM-06 Terminal Summary Text Policy Convergence
- Slice: S1 Policy Matrix Tests
- Implementer: AgentCodex
- Branch: `work/cm-05-06-08-09`

## Changes

- Added `tests/host/test_read_api_terminal_policy.py` to cover read API EventLog row -> HostEvent projection for `RUN_FAILED`, `RUN_CANCELLED`, and `RUN_LOST`; all non-success projections keep `final_answer=None` even when payload contains misleading `final_answer` or `content` fields.
- Extended `tests/host/test_terminal_summary_payload.py` with source-selection policy tests:
  - overlong allowed text is preserved by the helper;
  - inline `RUN_SUCCEEDED.final_answer` wins over terminal summary artifact content;
  - incomplete terminal summary descriptors do not fall back to bare `content` or `summary_text`;
  - malformed terminal summary descriptor fields raise `HostDurableError`.
- Strengthened `tests/host/test_engine_ingest_mapping.py::test_empty_final_answer_closes_failed_without_run_succeeded` to assert empty final answer governance failure payloads do not carry displayable `content` or `final_answer`.
- Strengthened `tests/host/test_memory_projection.py` to assert assistant terminal text remains selected-recent-window continuity with `MemoryIncludedReason.SELECTED_RECENT_WINDOW` and does not become evidence-backed fact memory.
- Added a direct memory consumer test showing descriptor hydration is not performed by `build_conversation_memory_snapshot_from_events(...)`; hydration remains owned by durable projection / run-input adapters.

## Validation

- `source .venv/bin/activate && pytest tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py -q`: 94 passed.
- `source .venv/bin/activate && python -m pyright dayu/ tests/ utils/`: 0 errors, 0 warnings, 0 informations.

## Fix Gate Update 2026-06-12

- Fix gate: completed.
- Addressed `docs/reviews/code-review-20260612-161139.md` Finding 001 by renaming the durable memory projection hydration test to make the adapter ownership explicit.
- Addressed `docs/reviews/code-review-20260612-161139.md` Finding 002 by adding malformed `terminal_summary_digest` coverage.
- Validation after fix: `pytest tests/host/test_terminal_summary_payload.py tests/host/test_read_api_terminal_policy.py tests/host/test_engine_ingest_mapping.py tests/host/test_memory_projection.py -q` passed with 95 tests.
- Validation after fix: `python -m pyright dayu/ tests/ utils/` reported 0 errors, 0 warnings, 0 informations.

## README Decision

- `tests/README.md`: not updated. This slice adds focused assertions inside the existing `tests/host/` layer and does not add a new test layer, command, or maintenance rule.
- `dayu/host/README.md`: not triggered because no `dayu/host/` production code changed.

## Residual Risk

- S1 is test-only. The remaining WU-CM-06 production-facing cleanup is Slice 2 docstring convergence in `dayu/host/terminal_summary_payload.py` and `dayu/host/_terminal_answer.py`.
